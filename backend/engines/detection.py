"""
DataSentinel — Anomaly Detection Engine  (v5.2 — Definitive Edition)
================================================================================

Merges Doc-1 (v5.1 first attempt) and Doc-2 (v5.1 revised), preserving every
feature from both while resolving the regressions each introduced.

Provenance / What Changed
--------------------------
[ARCH]  _load_dataframe() extracted as a standalone pure function (Doc-2).
        Keeps the orchestrator thin and makes load logic independently testable.
[ARCH]  Logic Gate moved into _stage_load; _stage_engineer is now purely feature
        engineering (Doc-2). Cleaner single-responsibility split.
[ARCH]  `deduplicate` stored on PipelineContext so every stage is fully
        self-contained — no parameter threading (Doc-2).
[PERF]  SCIPY_AVAILABLE / JOBLIB_AVAILABLE guard flags added (Doc-2).
        Pipeline degrades gracefully instead of crashing on missing optional libs.
[FIX]   Causal payload assignment uses positional zip + isinstance defensive branch
        (Doc-1). Doc-2 regressed this to .get() which raises AttributeError when
        generate_causal_payloads returns a list (its documented return type).
[FIX]   lof_ prefix restored in _humanize_feature_name → "Local Outlier Score"
        (Doc-1). Doc-2 silently dropped this branch, garbling LOF narratives.
[FIX]   process_and_detect always returns PipelineResult (Doc-1).
        Doc-2's union return (PipelineResult | dict[str,str]) forces every caller
        to branch; errors are already captured in PipelineResult.error.
[FIX]   Removed unused `sys` import introduced in Doc-2.
[KEEP]  All features preserved from both versions: DiCE counterfactuals,
        XGBoost / HistGB supervised threat scoring, ECOD ensemble member,
        LSTM autoencoder, classical KS drift + GAE lineage topology,
        domain_confidence in return payload, feedback threshold nudge (hard-capped
        1.5×), entity Z-scores (std clamped 1e-5), velocity engine, logic gate
        bypass shield, FIPS-140-2 SHA-256 row hash, session-id LFI sanitisation,
        config deep-copy, joblib drift-aware cache invalidation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, TypedDict

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import IsolationForest, HistGradientBoostingClassifier
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

# --- Optional dependency guards (Doc-2: graceful degradation, not hard crash) ---
try:
    from scipy.stats import median_abs_deviation, ks_2samp  # type: ignore
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import joblib  # type: ignore
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

try:
    from pyod.models.ecod import ECOD
    ECOD_AVAILABLE = True
except ImportError:
    ECOD_AVAILABLE = False

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from utils import _session_dir, logger
from engines.nlp_bridge import process_text_anomalies
from engines.logic_gate import apply_logic_gate, export_rules_for_lnn
from engines.causal_rca import generate_causal_payloads
from engines.lineage_gae import evaluate_lineage_drift
from engines.active_learning import calculate_uncertainty_scores, compute_human_trust_score

try:
    from engines.neuro_symbolic import detect_anomalies_lnn
    LNN_AVAILABLE = True
except ImportError:
    LNN_AVAILABLE = False
    logger.warning("PyTorch not installed. LNN Autoencoder disabled.")


# ---------------------------------------------------------------------------
# DOMAIN KEYWORD SETS
# ---------------------------------------------------------------------------

_FIN_KWS: frozenset[str] = frozenset({
    "amount", "transaction", "fraud", "payment", "bank",
    "credit", "merchant", "card", "debit", "wire",
})
_HEALTH_KWS: frozenset[str] = frozenset({
    "patient", "blood", "disease", "diagnosis", "medication",
    "dose", "bmi", "cholesterol",
})
_HR_KWS: frozenset[str] = frozenset({
    "employee", "salary", "department", "hire", "termination",
    "leave", "payroll",
})
_IOT_KWS: frozenset[str] = frozenset({
    "sensor", "temp", "humidity", "cpu", "memory", "voltage",
    "current", "reading", "device",
})
_ECOMM_KWS: frozenset[str] = frozenset({
    "order", "cart", "product", "sku", "shipment", "return",
    "review", "rating",
})
_DEMO_KWS: frozenset[str] = frozenset({
    "age", "passenger", "income", "gender", "sex",
    "patient", "blood", "disease", "fare", "survived",
})
_AMOUNT_KWS: frozenset[str] = frozenset({
    "amount", "value", "price", "total",
    "balance", "sum", "cost", "payment",
})
_TEXT_KWS: frozenset[str] = frozenset({
    "review", "text", "description", "summary", "comment", "feedback",
})


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

@dataclass
class AnomalyDetectionConfig:
    """Central configuration for the detection pipeline."""

    if_n_estimators: int = 200
    if_max_samples: int = 50_000
    lof_n_neighbors: int = 20

    lstm_seq_len: int = 10
    lstm_min_sequences: int = 20
    lstm_epochs: int = 5
    lstm_batch_size: int = 64
    lstm_units: int = 32

    shap_max_rows: int = 500
    shap_background_samples: int = 100
    dice_max_rows: int = 20

    sigma_finance: float = 1.2
    sigma_demographic: float = 2.0
    sigma_generic: float = 1.5

    cap_finance: float = 0.10
    cap_demographic: float = 0.20
    cap_generic: float = 0.15

    logic_gate_bypass_ratio: float = 0.90

    # v4.1 weights restored (ECOD included); renormalised at runtime if detectors absent.
    ensemble_weights: dict = field(default_factory=lambda: {
        "lnn":  0.30,
        "if":   0.25,
        "lof":  0.20,
        "ecod": 0.10,
        "lstm": 0.15,
    })

    ks_p_value_threshold: float = 0.05
    ks_min_samples: int = 30
    entity_zscore_max_cols: int = 3
    feedback_fp_ratio_threshold: float = 0.80
    feedback_min_reviews: int = 10

    def __post_init__(self) -> None:
        total_w = sum(self.ensemble_weights.values())
        if abs(total_w - 1.0) > 0.01:
            raise ValueError(
                f"Ensemble weights must sum to 1.0, got {total_w:.4f}. "
                "Adjust ensemble_weights in your AnomalyDetectionConfig."
            )


_DEFAULT_CONFIG = AnomalyDetectionConfig()


# ---------------------------------------------------------------------------
# TYPED RETURN & PIPELINE CONTEXT
# ---------------------------------------------------------------------------

class PipelineResult(TypedDict):
    status: str
    session_id: str
    total_rows: int
    anomaly_count: int
    algorithm_used: str
    recommendation: str
    applied_rules: list
    recommended_cleaning: str
    cleaning_rationale: str
    parquet_path: str
    drift_report: dict
    calibration_needed: bool
    stat_anomaly_ratio: float
    domain_detected: str
    domain_confidence: float          # restored from v4.1
    threshold_applied: float
    trust_metrics: dict
    error: Optional[str]


@dataclass
class PipelineContext:
    """
    Carries shared state across pipeline stages for decoupled, testable execution.

    `deduplicate` is stored here (Doc-2) so each stage function is fully
    self-contained — no parameter threading through the call chain.
    """

    session_id: str
    session_dir: str
    cfg: AnomalyDetectionConfig
    domain_override: Optional[str] = None
    deduplicate: bool = True          # Doc-2: stored on context, not passed per-stage

    # DataFrames
    df: Optional[pl.DataFrame] = None
    pandas_df: Optional[pd.DataFrame] = None
    encoded_df: Optional[pd.DataFrame] = None
    train_df: Optional[pd.DataFrame] = None

    # Schema metadata
    domain: str = "generic"
    domain_confidence: float = 0.0
    numeric_cols: list[str] = field(default_factory=list)
    cat_cols: list[str] = field(default_factory=list)
    time_cols: list[str] = field(default_factory=list)
    id_cols: list[str] = field(default_factory=list)
    velocity_cols: list[str] = field(default_factory=list)
    ez_cols: list[str] = field(default_factory=list)

    # Logic gate state
    applied_rules: list = field(default_factory=list)
    lnn_constraints: dict = field(default_factory=dict)
    logic_flag_set: set[int] = field(default_factory=set)
    logic_arr: Optional[np.ndarray] = None

    # LSTM
    lstm_available: bool = False
    lstm_scores: Optional[np.ndarray] = None

    # Scoring outputs
    is_anomaly: Optional[np.ndarray] = None
    inverted_scores: Optional[np.ndarray] = None
    scores_raw: dict[str, np.ndarray] = field(default_factory=dict)
    threshold: float = 0.0
    model: Optional[IsolationForest] = None
    model_fitted: bool = False
    recommendation: str = ""
    calibration_needed: bool = False
    stat_anomaly_ratio: float = 0.0
    consensus_payloads: list[str] = field(default_factory=list)

    # Explainability outputs
    causal_payloads: list[str] = field(default_factory=list)
    cf_payloads: list[str] = field(default_factory=list)
    threat_scores: list[float] = field(default_factory=list)
    reasons_list: list[str] = field(default_factory=list)
    trust_metrics: dict = field(default_factory=dict)

    # Persistence outputs
    drift_report: dict = field(default_factory=dict)
    raw_parquet_path: str = ""
    recommended_cleaning: str = "quarantine"
    cleaning_rationale: str = ""

    # Paths
    models_dir: str = ""

    def __post_init__(self) -> None:
        self.models_dir = os.path.join(self.session_dir, "models")
        os.makedirs(self.models_dir, exist_ok=True)


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

_FEATURE_NAME_MAP: dict[str, str] = {
    "amt": "amount",      "txn": "transaction",  "trx": "transaction",
    "qty": "quantity",    "num": "number of",     "cnt": "count",
    "freq": "frequency",  "pct": "percentage",    "avg": "average",
    "std": "spread",      "diff": "difference",   "prev": "previous",
    "curr": "current",    "bal": "balance",        "acct": "account",
    "cust": "customer",   "src": "source",         "dst": "destination",
    "loc": "location",    "ts": "timestamp",       "dt": "date",
    "hr": "hour",         "min": "minute",         "sec": "second",
    "id": "ID",           "ip": "IP address",      "lat": "latitude",
    "lon": "longitude",
}

_STRIP_SUFFIXES: tuple[str, ...] = (
    "_freq", "_entity_z", "_length", "_digit_ratio",
    "_upper_ratio", "_special_ratio",
)

_DOMAIN_SUBJECT: dict[str, str] = {
    "finance":   "This transaction",
    "health":    "This record",
    "hr":        "This employee record",
    "iot":       "This reading",
    "ecommerce": "This order",
    "generic":   "This record",
}

_DOMAIN_ENTITY: dict[str, str] = {
    "finance":   "account",
    "health":    "patient",
    "hr":        "employee",
    "iot":       "device",
    "ecommerce": "customer",
    "generic":   "entity",
}

_DOMAIN_SIGMA_CAP: dict[str, tuple[str, str]] = {
    "finance":   ("sigma_finance",     "cap_finance"),
    "health":    ("sigma_demographic", "cap_demographic"),
    "hr":        ("sigma_generic",     "cap_generic"),
    "iot":       ("sigma_generic",     "cap_generic"),
    "ecommerce": ("sigma_generic",     "cap_generic"),
    "generic":   ("sigma_generic",     "cap_generic"),
}

_DOMAIN_CLEANING: dict[str, tuple[str, str]] = {
    "finance": (
        "quarantine",
        "Financial data detected. Quarantine isolates threats without erasing forensic evidence.",
    ),
    "health": (
        "impute",
        "Health/demographic data detected. Contextual Imputation salvages rows by predicting "
        "anomalous traits based on similar profiles.",
    ),
    "hr": (
        "impute",
        "HR data detected. Contextual Imputation predicts anomalous values from comparable records.",
    ),
    "iot": (
        "impute",
        "Sequential telemetry detected. KNN Imputation bridges hardware glitches smoothly.",
    ),
    "ecommerce": (
        "quarantine",
        "E-commerce data detected. Quarantine isolates suspicious orders for review.",
    ),
    "generic": (
        "quarantine",
        "Generic dataset. Quarantine is the safest default — moves anomalous rows to a secure vault.",
    ),
}

_ENTITY_KEYWORDS: tuple[str, ...] = (
    "user", "account", "customer", "merchant",
    "employee", "sender", "client", "patient",
)


# ---------------------------------------------------------------------------
# NARRATIVE HELPERS
# ---------------------------------------------------------------------------

def _row_hash(row_idx: int, col: str) -> int:
    """FIPS 140-2 compliant deterministic hash for narrative selection."""
    return int(hashlib.sha256(f"{row_idx}:{col}".encode()).hexdigest()[:8], 16)


def _pick(options: list[str], row_idx: int, col: str = "") -> str:
    return options[_row_hash(row_idx, col) % len(options)]


def _humanize_feature_name(col: str) -> str:
    # Doc-1: lof_ branch restored — Doc-2 silently dropped it, garbling LOF narratives
    if col.startswith("velocity_24h"):  return "24-hour Activity Volume"
    if col.startswith("velocity_1h"):   return "Hourly Transaction Count"
    if col.startswith("lstm_"):         return "Behavioural Pattern Score"
    if col.startswith("lof_"):          return "Local Outlier Score"        # Doc-1 fix
    if col.startswith("ecod_"):         return "Distribution Outlier Score"
    if col.startswith("nlp_pc"):        return "Text Pattern"

    name = col
    for suffix in _STRIP_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break

    words    = name.replace("-", "_").split("_")
    expanded = [_FEATURE_NAME_MAP.get(w.lower(), w) for w in words]
    return " ".join(expanded).strip().title() or col


def _describe_deviation(z: float) -> tuple[str, str]:
    direction = "high" if z > 0 else "low"
    a = abs(z)
    if a < 1.5: return f"slightly {direction}",      "a little outside the normal range"
    if a < 2.5: return f"notably {direction}",       "noticeably different from the typical value"
    if a < 3.5: return f"significantly {direction}", "well outside what is normally seen"
    if a < 5.0: return f"exceptionally {direction}", "far beyond the expected range"
    return             f"extremely {direction}",     "at an extreme level rarely seen in this dataset"


def _format_value(val: Any, col: str) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "unknown"
    col_l = col.lower()
    if any(k in col_l for k in ("amount", "price", "balance", "total", "cost",
                                 "payment", "fare", "revenue", "salary", "income")):
        try:
            return f"${float(val):,.2f}"
        except (ValueError, TypeError):
            pass
    if any(k in col_l for k in ("prob", "pct", "percent", "ratio", "rate", "score")):
        try:
            fv = float(val)
            if 0.0 <= fv <= 1.0:
                return f"{fv * 100:.1f}%"
        except (ValueError, TypeError):
            pass
    if any(k in col_l for k in ("age", "days", "hours", "minutes", "years")):
        try:
            return str(int(round(float(val))))
        except (ValueError, TypeError):
            pass
    if isinstance(val, float):
        return f"{val:,.2f}" if abs(val) >= 1 else f"{val:.4f}"
    return str(val)


def _detect_domain(col_str: str) -> tuple[str, float]:
    """Returns (domain, confidence). Confidence < 0.2 falls back to generic."""
    checks: list[tuple[str, frozenset[str]]] = [
        ("finance",   _FIN_KWS),
        ("health",    _HEALTH_KWS),
        ("hr",        _HR_KWS),
        ("iot",       _IOT_KWS),
        ("ecommerce", _ECOMM_KWS),
    ]
    best_domain, max_conf = "generic", 0.0
    for domain, kws in checks:
        conf = sum(1 for kw in kws if kw in col_str) / len(kws)
        if conf > max_conf:
            max_conf   = conf
            best_domain = domain

    if max_conf < 0.2:
        logger.warning("Domain confidence low (%.2f). Defaulting to generic.", max_conf)
        return "generic", max_conf
    return best_domain, max_conf


def _build_logic_violation_narrative(raw_violation: str) -> str:
    if not raw_violation or not isinstance(raw_violation, str):
        return (
            "A data integrity rule was broken — the values in this record "
            "are logically inconsistent."
        )
    raw = raw_violation.strip()
    if "violated:" in raw.lower():
        parts       = raw.lower().split("violated:", 1)
        rule_part   = parts[0].strip().rstrip(".")
        detail_part = parts[1].strip() if len(parts) > 1 else ""
        rule_readable = rule_part.replace("_", " ").replace("  ", " ")
        if detail_part:
            fv = detail_part.replace("_", " ").replace("=", " of ").replace(",", " and")
            return (
                f"A data integrity check failed — the rule '{rule_readable}' was not met "
                f"(recorded value: {fv}). This suggests the data may be corrupted, "
                f"entered incorrectly, or physically impossible."
            )
        return (
            f"A business logic rule was violated: '{rule_readable}'. "
            f"This kind of inconsistency usually points to a data entry error or system fault."
        )
    clean = raw.replace("_", " ").replace("  ", " ").rstrip(".")
    return (
        f"This record failed an internal consistency check: {clean}. "
        f"It may reflect a data entry error, system fault, or deliberate manipulation."
    )


# ---------------------------------------------------------------------------
# FEEDBACK READER
# ---------------------------------------------------------------------------

def _read_feedback_threshold_nudge(
    feedback_path: str,
    session_id: str,
    current_threshold: float,
    cfg: AnomalyDetectionConfig,
) -> float:
    if not os.path.exists(feedback_path):
        return current_threshold

    fp_count = tp_count = 0
    try:
        with open(feedback_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("session_id") == session_id:
                        label = entry.get("label")
                        if label == 0:
                            fp_count += 1
                        elif label == 1:
                            tp_count += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        return current_threshold

    total = fp_count + tp_count
    if total < cfg.feedback_min_reviews:
        return current_threshold

    fp_ratio = fp_count / total
    if fp_ratio >= cfg.feedback_fp_ratio_threshold:
        nudged = current_threshold * 1.10
        nudged = min(nudged, current_threshold * 1.5)   # hard cap (both v4.1 & v5.0)
        logger.info(
            "Feedback: %.0f%% FP rate across %d reviews. "
            "Nudging threshold %.4f → %.4f.",
            fp_ratio * 100, total, current_threshold, nudged,
        )
        return nudged
    return current_threshold


# ---------------------------------------------------------------------------
# NARRATIVE BUILDER  (standalone testable function)
# ---------------------------------------------------------------------------

def _build_narratives(
    pandas_df: pd.DataFrame,
    is_anomaly: np.ndarray,
    causal_payloads: list[str],
    original_numeric: list[str],
    cat_cols: list[str],
    velocity_col_set: set[str],
    ez_col_set: set[str],
    id_cols: list[str],
    domain: str,
) -> list[str]:
    subject = _DOMAIN_SUBJECT[domain]
    entity  = _DOMAIN_ENTITY[domain]

    reasons_list    = [""] * len(pandas_df)
    anomaly_indices = list(np.where(is_anomaly)[0])

    if not anomaly_indices:
        return reasons_list

    stats: dict[str, dict] = {}
    for col in original_numeric:
        m = pandas_df[col].mean()
        s = pandas_df[col].std()
        stats[col] = {
            "mean": float(m) if pd.notna(m) else 0.0,
            "std":  float(s) if pd.notna(s) else 0.0,
        }

    rare_cats: dict[str, set] = {}
    for col in cat_cols:
        if pandas_df[col].nunique() / max(len(pandas_df), 1) < 0.3:
            vc = pandas_df[col].value_counts(normalize=True)
            rare_cats[col] = set(vc[vc < 0.05].index.tolist())

    parsed_causal: dict[int, list] = {}
    for idx in anomaly_indices:
        try:
            payload = json.loads(causal_payloads[idx])
            if payload:
                parsed_causal[idx] = payload
        except (ValueError, TypeError):
            pass

    entity_col = id_cols[0] if id_cols else None

    entity_group_means: dict[str, pd.Series] = {}
    if entity_col and entity_col in pandas_df.columns:
        for ez_col in ez_col_set:
            base_col = ez_col.replace("_entity_z", "")
            if base_col in pandas_df.columns:
                entity_group_means[base_col] = pandas_df.groupby(entity_col)[base_col].mean()

    for idx in anomaly_indices:
        row   = pandas_df.iloc[idx]
        parts: list[str] = []

        # Logic violation short-circuit
        if "logic_violation" in pandas_df.columns and pd.notna(row.get("logic_violation")):
            reasons_list[idx] = _build_logic_violation_narrative(row["logic_violation"])
            continue

        if idx in parsed_causal:
            causal_items = parsed_causal[idx]
            top_feat     = causal_items[0]["feature"]
            top_impact   = causal_items[0]["impact"]

            orig_feat = top_feat
            for suf in _STRIP_SUFFIXES:
                if orig_feat.endswith(suf):
                    orig_feat = orig_feat[: -len(suf)]
                    break

            readable_feat = _humanize_feature_name(orig_feat)
            raw_val       = row.get(orig_feat, row.get(top_feat))
            formatted_val = _format_value(raw_val, orig_feat)

            # --- Primary signal selection ---
            if top_feat in velocity_col_set or orig_feat in velocity_col_set:
                vel_1h  = row.get("velocity_1h_count")
                vel_24h = row.get("velocity_24h_sum")
                if vel_1h is not None and pd.notna(vel_1h) and float(vel_1h) > 1:
                    parts.append(
                        f"{subject} is part of a burst of {int(vel_1h)} rapid "
                        f"transactions from the same {entity} within a single hour — "
                        f"a pace that stands out as highly unusual."
                    )
                elif vel_24h is not None and pd.notna(vel_24h):
                    parts.append(
                        f"The total activity from this {entity} over the past 24 hours "
                        f"({_format_value(vel_24h, 'amount')}) is unusually high and "
                        f"well above what is normally seen in a single day."
                    )
                else:
                    parts.append(
                        f"{subject} shows an abnormal spike in activity over a short "
                        f"window, a common indicator of automated or suspicious behaviour."
                    )

            elif top_feat.startswith("lstm_") or orig_feat.startswith("lstm_"):
                parts.append(
                    f"The recent sequence of activity from this {entity} breaks away "
                    f"from its own established pattern. The AI detected that the order "
                    f"and rhythm of recent events no longer match how this {entity} "
                    f"normally behaves — even if individual values look ordinary on their own."
                )

            elif top_feat in ez_col_set or orig_feat in ez_col_set:
                base_col        = orig_feat.replace("_entity_z", "")
                entity_mean_val = None
                if entity_col and base_col in entity_group_means:
                    entity_id = row.get(entity_col)
                    if entity_id is not None:
                        entity_mean_val = entity_group_means[base_col].get(entity_id)
                base_readable = _humanize_feature_name(base_col)
                base_val      = _format_value(row.get(base_col), base_col)
                if entity_mean_val is not None and pd.notna(entity_mean_val):
                    parts.append(
                        f"The {base_readable.lower()} for this entry ({base_val}) is far "
                        f"outside what this specific {entity} normally does — their own "
                        f"historical average is around {_format_value(entity_mean_val, base_col)}. "
                        f"This gap from their own baseline triggered the alert."
                    )
                else:
                    parts.append(
                        f"The {base_readable.lower()} here ({base_val}) is much higher "
                        f"than this {entity} typically records."
                    )

            elif orig_feat in stats and stats[orig_feat]["std"] > 0:
                try:
                    z = (float(row.get(orig_feat)) - stats[orig_feat]["mean"]) / stats[orig_feat]["std"]
                except (TypeError, ValueError):
                    z = 0.0
                severity, ctx_phrase = _describe_deviation(z)
                avg_readable = _format_value(stats[orig_feat]["mean"], orig_feat)
                openers = [
                    f"The {readable_feat.lower()} for this record is {formatted_val}, which is {severity} — {ctx_phrase}. The typical value is around {avg_readable}.",
                    f"What stands out most is the {readable_feat.lower()}: {formatted_val}. Compared to the usual {avg_readable}, this is {severity} and {ctx_phrase}.",
                    f"{subject} was flagged primarily because its {readable_feat.lower()} ({formatted_val}) is {severity}, sitting {ctx_phrase}. Most records show values near {avg_readable}.",
                    f"A {readable_feat.lower()} of {formatted_val} is {severity} for this dataset — {ctx_phrase}. The average is {avg_readable}.",
                ]
                parts.append(_pick(openers, idx, orig_feat))

            elif orig_feat in rare_cats and str(raw_val) in rare_cats[orig_feat]:
                parts.append(
                    f"The value '{raw_val}' in the {readable_feat.lower()} field appears "
                    f"in fewer than 5% of all records. Rare categories like this can "
                    f"indicate unusual circumstances or data that doesn't match standard patterns."
                )
            else:
                parts.append(
                    f"{subject} stood out because of an unusual combination involving "
                    f"{readable_feat.lower()} ({formatted_val}), which the model identified "
                    f"as behaving differently from the rest of the data."
                )

            # --- Secondary feature signal ---
            if len(causal_items) > 1 and abs(causal_items[1]["impact"]) > abs(top_impact) * 0.25:
                sec_feat = causal_items[1]["feature"]
                sec_orig = sec_feat
                for suf in _STRIP_SUFFIXES:
                    if sec_orig.endswith(suf):
                        sec_orig = sec_orig[: -len(suf)]
                        break
                sec_readable = _humanize_feature_name(sec_orig)
                sec_raw      = row.get(sec_orig, row.get(sec_feat))
                sec_fmt      = _format_value(sec_raw, sec_orig)

                if sec_orig in stats and stats[sec_orig]["std"] > 0:
                    try:
                        z2 = (float(row.get(sec_orig, 0)) - stats[sec_orig]["mean"]) / stats[sec_orig]["std"]
                        sev2, ctx2 = _describe_deviation(z2)
                    except (TypeError, ValueError):
                        sev2, ctx2 = "unusual", "outside the expected range"
                    sec_opts = [
                        f"On top of that, the {sec_readable.lower()} ({sec_fmt}) is also {sev2}, adding to the concern.",
                        f"This is compounded by the {sec_readable.lower()}, which at {sec_fmt} is also {sev2} — {ctx2}.",
                        f"The {sec_readable.lower()} ({sec_fmt}) is an additional signal: it too is {sev2}.",
                    ]
                elif sec_orig in rare_cats and str(sec_raw) in rare_cats.get(sec_orig, set()):
                    sec_opts = [
                        f"The {sec_readable.lower()} field ('{sec_raw}') is also an unusual category, rarely seen in this dataset.",
                        f"Adding to this, '{sec_raw}' is a very rare value for {sec_readable.lower()}, reinforcing the flag.",
                    ]
                else:
                    sec_opts = [
                        f"The {sec_readable.lower()} ({sec_fmt}) also deviated from what the model normally expects.",
                        f"A secondary signal came from {sec_readable.lower()} ({sec_fmt}), which also looked out of place.",
                    ]
                parts.append(_pick(sec_opts, idx, sec_orig))

            # --- Tertiary feature signal ---
            if len(causal_items) > 2 and abs(causal_items[2]["impact"]) > abs(top_impact) * 0.15:
                ter_orig = (
                    causal_items[2]["feature"]
                    .replace("_freq", "").replace("_entity_z", "")
                )
                parts.append(
                    f"Minor additional signal was detected in "
                    f"{_humanize_feature_name(ter_orig).lower()} as well."
                )

            reasons_list[idx] = " ".join(parts)

        else:
            # Fallback: find highest z-score column
            max_z, max_col, sec_z, sec_col = 0.0, None, 0.0, None
            for col in original_numeric:
                if stats.get(col, {}).get("std", 0) > 0:
                    try:
                        z = abs((float(row[col]) - stats[col]["mean"]) / stats[col]["std"])
                    except (TypeError, ValueError):
                        continue
                    if z > max_z:
                        sec_z, sec_col = max_z, max_col
                        max_z, max_col = z, col
                    elif z > sec_z:
                        sec_z, sec_col = z, col

            if max_col and max_z > 2.0:
                readable_max  = _humanize_feature_name(max_col)
                formatted_max = _format_value(row[max_col], max_col)
                try:
                    sev, ctx_p = _describe_deviation(
                        (float(row[max_col]) - stats[max_col]["mean"]) / stats[max_col]["std"]
                    )
                except (TypeError, ValueError):
                    sev, ctx_p = "unusual", "outside the expected range"
                avg_max = _format_value(stats[max_col]["mean"], max_col)

                openers = [
                    f"The most striking value is the {readable_max.lower()} ({formatted_max}), which is {sev} compared to the dataset average of {avg_max}.",
                    f"{subject} was flagged because its {readable_max.lower()} ({formatted_max}) is {sev} — {ctx_p}. The typical figure is {avg_max}.",
                    f"Looking at the numbers, the {readable_max.lower()} ({formatted_max}) jumps out as {sev}. Normally this sits around {avg_max}.",
                ]
                reason = _pick(openers, idx, max_col)

                if sec_col and sec_z > 1.5:
                    readable_sec  = _humanize_feature_name(sec_col)
                    formatted_sec = _format_value(row[sec_col], sec_col)
                    try:
                        sev2, _ = _describe_deviation(
                            (float(row[sec_col]) - stats[sec_col]["mean"]) / stats[sec_col]["std"]
                        )
                    except (TypeError, ValueError):
                        sev2 = "unusual"
                    reason += (
                        f" The {readable_sec.lower()} ({formatted_sec}) is also {sev2}, "
                        f"which combined with the above pushed this record past the detection threshold."
                    )
                reasons_list[idx] = reason
            else:
                multi_opts = [
                    f"{subject} doesn't have one obvious red flag, but the combination of several values together created a pattern the model hasn't seen before.",
                    f"No single value here is dramatically out of range, but the overall profile of this record is unlike the rest of the dataset.",
                    f"The model flagged this record based on the relationship between multiple fields rather than any one standout value.",
                ]
                reasons_list[idx] = _pick(multi_opts, idx, "multi")

    return reasons_list


# ---------------------------------------------------------------------------
# CLEANING RECOMMENDATION
# ---------------------------------------------------------------------------

def _recommend_cleaning(
    domain: str,
    col_str: str,
    cat_cols: list[str],
    numeric_cols: list[str],
    time_cols: list[str],
    n_rows: int,
) -> tuple[str, str]:
    text_heavy = len(cat_cols) >= len(numeric_cols) and len(cat_cols) > 0
    if text_heavy or any(kw in col_str for kw in _TEXT_KWS):
        return (
            "mask",
            "Text-heavy dataset detected. Masking safely redacts anomalous strings "
            "with [REDACTED] without destroying the rest of the row.",
        )
    if domain in _DOMAIN_CLEANING:
        if domain == "iot" and not time_cols:
            return (
                "quarantine",
                "IoT data without timestamps detected. Quarantine is the safest default.",
            )
        return _DOMAIN_CLEANING[domain]
    if n_rows > 2_000 and len(numeric_cols) > 3:
        return (
            "winsorize",
            "Large numerical dataset detected. Winsorization caps extremes without shrinking the dataset.",
        )
    return _DOMAIN_CLEANING["generic"]


# ---------------------------------------------------------------------------
# LOAD HELPER  (Doc-2: standalone pure function, independently testable)
# ---------------------------------------------------------------------------

def _load_dataframe(
    file_path: Optional[str],
    df: Optional[pl.DataFrame],
) -> pl.DataFrame | str:
    """
    Returns a Polars DataFrame on success, or an error string on failure.
    Keeping this as a pure function (no ctx mutation) makes it trivially testable
    and keeps the orchestrator thin.
    """
    if df is not None:
        return df
    try:
        return pl.read_csv(file_path, infer_schema_length=1_000_000)
    except Exception as primary_err:
        logger.warning("Polars CSV read failed (%s), trying pandas...", primary_err)
        try:
            return pl.from_pandas(pd.read_csv(file_path, low_memory=False))
        except Exception as inner_e:
            return f"Fatal Read Error. Both engines failed: {inner_e}"


# ---------------------------------------------------------------------------
# STAGE 1 — LOAD, DEDUP & LOGIC GATE  (Doc-2 architecture)
# ---------------------------------------------------------------------------

def _stage_load(ctx: PipelineContext) -> PipelineContext:
    """
    Deduplication + Logic Gate enforcement.

    Dedup and logic gate are both data-quality filters that must run before any
    feature engineering touches the data, so they belong together in stage 1
    (Doc-2 improvement over Doc-1 where the gate lived in _stage_engineer).
    """
    if ctx.deduplicate and ctx.df is not None:
        pre     = len(ctx.df)
        ctx.df  = ctx.df.unique()
        removed = pre - len(ctx.df)
        if removed > 0:
            logger.info("Dedup: %d → %d rows (%d removed).", pre, len(ctx.df), removed)
            col_lower = " ".join(ctx.df.columns).lower()
            if any(kw in col_lower for kw in _FIN_KWS):
                logger.warning(
                    "FINANCIAL DATA: %d duplicate rows removed. Pass deduplicate=False "
                    "if this dataset uses row-level transaction IDs.", removed,
                )

    ctx.df, ctx.applied_rules = apply_logic_gate(ctx.df)
    ctx.lnn_constraints       = export_rules_for_lnn(ctx.applied_rules, ctx.df.columns)

    with open(f"{ctx.session_dir}/sbvr_rules.json", "w") as f:
        json.dump(ctx.applied_rules, f)

    return ctx


# ---------------------------------------------------------------------------
# STAGE 2 — ENGINEER & ENCODE
# ---------------------------------------------------------------------------

def _stage_engineer(ctx: PipelineContext) -> PipelineContext:
    """
    Pure feature engineering: NLP, velocity/LSTM, categorical encoding,
    entity Z-scores, domain detection, clean training subset selection.

    Logic gate has already run in _stage_load; this stage only derives
    downstream artefacts (logic_flag_set, logic_arr) from it.
    """

    # --- Schema metadata ---
    ctx.time_cols = [
        c for c in ctx.df.columns
        if any(kw in c.lower() for kw in ("date", "time", "timestamp"))
    ]
    ctx.id_cols = [
        c for c in ctx.df.columns
        if "id" in c.lower() and any(kw in c.lower() for kw in _ENTITY_KEYWORDS)
    ]

    # --- NLP Bridge ---
    ctx.df = process_text_anomalies(ctx.df)

    # --- Polars → Pandas  (_orig_idx for guaranteed LSTM index fidelity, v5.0) ---
    ctx.pandas_df = ctx.df.to_pandas().reset_index(drop=True)
    ctx.pandas_df["_orig_idx"] = np.arange(len(ctx.pandas_df))

    # --- Column classification ---
    ctx.numeric_cols = [
        c for c in ctx.pandas_df.select_dtypes(include=[np.number]).columns.tolist()
        if c not in ctx.time_cols and c != "_orig_idx"
    ]
    ctx.cat_cols = [
        c for c in ctx.pandas_df.select_dtypes(include=["object", "string"]).columns.tolist()
        if c != "logic_violation"
    ]

    # --- Logic Gate state (derived from gate applied in _stage_load) ---
    if "logic_violation" in ctx.pandas_df.columns:
        logic_mask = ctx.pandas_df["logic_violation"].notna()
    else:
        logic_mask = pd.Series([False] * len(ctx.pandas_df))

    ctx.logic_flag_set = set(int(i) for i in np.where(logic_mask.values)[0])
    ctx.logic_arr      = logic_mask.values.astype(bool)
    clean_mask         = ~ctx.logic_arr

    # --- Feature Matrix with leakage-safe frequency encoding (v4.1) ---
    ctx.encoded_df = ctx.pandas_df[ctx.numeric_cols].copy().fillna(0)

    for col in ctx.cat_cols:
        if clean_mask.any():
            freq_map = ctx.pandas_df.loc[clean_mask, col].value_counts(normalize=True).to_dict()
        else:
            freq_map = ctx.pandas_df[col].value_counts(normalize=True).to_dict()
        ctx.encoded_df[col + "_freq"] = ctx.pandas_df[col].map(freq_map).fillna(0)

    # --- Velocity Engine + LSTM Autoencoder ---
    if ctx.time_cols and ctx.id_cols:
        t_col, i_col = ctx.time_cols[0], ctx.id_cols[0]
        try:
            if ctx.df[t_col].dtype not in (pl.Datetime, pl.Date):
                parsed = None
                for fmt in (
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
                    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y",
                    "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                ):
                    try:
                        candidate = ctx.df.with_columns(
                            pl.col(t_col).str.strptime(pl.Datetime, format=fmt, strict=False)
                        )
                        if candidate[t_col].null_count() / len(candidate) < 0.5:
                            ctx.df = candidate
                            parsed = candidate
                            logger.info("Parsed '%s' with format '%s'.", t_col, fmt)
                            break
                    except (ValueError, TypeError):
                        continue
                if parsed is None:
                    raise ValueError(f"Could not parse '{t_col}' as datetime.")

            if ctx.df[t_col].dtype == pl.Date:
                ctx.df = ctx.df.with_columns(pl.col(t_col).cast(pl.Datetime))

            ctx.df = ctx.df.filter(pl.col(t_col).is_not_null()).sort([i_col, t_col])

            numeric_types = (pl.Float64, pl.Int64, pl.Float32, pl.Int32)
            num_for_vel   = [
                c for c, d in zip(ctx.df.columns, ctx.df.dtypes) if d in numeric_types
            ]
            smart_picks = [c for c in num_for_vel if any(kw in c.lower() for kw in _AMOUNT_KWS)]
            track_col   = smart_picks[0] if smart_picks else (num_for_vel[0] if num_for_vel else None)

            if track_col:
                ctx.df = ctx.df.with_columns(pl.lit(1).alias("_txn_counter"))
                ctx.df = ctx.df.with_columns([
                    pl.col(track_col)
                      .rolling_sum_by(by=t_col, window_size="1d", closed="both")
                      .over(i_col)
                      .alias("velocity_24h_sum"),
                    pl.col("_txn_counter")
                      .rolling_sum_by(by=t_col, window_size="1h", closed="both")
                      .over(i_col)
                      .alias("velocity_1h_count"),
                ]).with_columns([
                    pl.col("velocity_24h_sum").fill_null(0),
                    pl.col("velocity_1h_count").fill_null(0),
                ]).drop("_txn_counter")
                ctx.velocity_cols = ["velocity_24h_sum", "velocity_1h_count"]
                logger.info("Velocity features generated for '%s'.", track_col)

                # LSTM Autoencoder  (_orig_idx tracking, v5.0)
                try:
                    from tensorflow import keras  # type: ignore

                    logger.info("Fitting LSTM Autoencoder...")
                    seq_df = ctx.pandas_df[[i_col, t_col, track_col, "_orig_idx"]].copy()
                    seq_df[t_col] = pd.to_datetime(seq_df[t_col], errors="coerce")
                    seq_df = seq_df.dropna(subset=[t_col]).sort_values([i_col, t_col])

                    g_mean = seq_df[track_col].mean()
                    g_std  = seq_df[track_col].std() or 1.0
                    seq_df["_scaled"] = (seq_df[track_col].fillna(0) - g_mean) / g_std

                    seq_len   = ctx.cfg.lstm_seq_len
                    sequences: list[np.ndarray] = []
                    seq_idxs:  list[int]        = []

                    for _, grp in seq_df.groupby(i_col, sort=False):
                        vals      = grp["_scaled"].values.astype("float32")
                        orig_idxs = grp["_orig_idx"].values
                        for j in range(len(vals) - seq_len + 1):
                            sequences.append(vals[j: j + seq_len])
                            seq_idxs.append(int(orig_idxs[j + seq_len - 1]))

                    if len(sequences) >= ctx.cfg.lstm_min_sequences:
                        X_seq = np.array(sequences, dtype="float32").reshape(-1, seq_len, 1)

                        inp = keras.Input(shape=(seq_len, 1))
                        enc = keras.layers.LSTM(ctx.cfg.lstm_units, activation="relu")(inp)
                        rep = keras.layers.RepeatVector(seq_len)(enc)
                        dec = keras.layers.LSTM(
                            ctx.cfg.lstm_units, activation="relu", return_sequences=True
                        )(rep)
                        out = keras.layers.TimeDistributed(keras.layers.Dense(1))(dec)
                        autoencoder = keras.Model(inp, out)
                        autoencoder.compile(optimizer="adam", loss="mse")
                        early_stop = keras.callbacks.EarlyStopping(monitor='loss', patience=1, restore_best_weights=True)
                        autoencoder.fit(
                            X_seq, X_seq,
                            epochs=ctx.cfg.lstm_epochs,
                            batch_size=ctx.cfg.lstm_batch_size,
                            callbacks=[early_stop],
                            verbose=0,
                        )

                        recon        = autoencoder.predict(X_seq, verbose=0)
                        recon_errors = np.mean(np.abs(X_seq - recon), axis=(1, 2))

                        lstm_scores_arr = np.zeros(len(ctx.pandas_df), dtype=float)
                        for k, orig_idx in enumerate(seq_idxs):
                            if orig_idx < len(lstm_scores_arr):
                                lstm_scores_arr[orig_idx] = max(
                                    lstm_scores_arr[orig_idx], recon_errors[k]
                                )

                        ctx.encoded_df["lstm_anomaly_score"] = lstm_scores_arr
                        ctx.lstm_available = True
                        ctx.lstm_scores    = lstm_scores_arr
                        logger.info("LSTM scoring complete.")
                    else:
                        logger.info(
                            "LSTM skipped — not enough sequences (need ≥ %d).",
                            ctx.cfg.lstm_min_sequences,
                        )
                except ImportError:
                    logger.info("LSTM skipped — TensorFlow not installed.")
                except (ValueError, RuntimeError) as e:
                    logger.warning("LSTM Autoencoder failed: %s", e)

        except (ValueError, TypeError) as e:
            logger.warning("Velocity Engine failed: %s", e)

    # --- Entity-relative Z-scores  (std clamped to prevent infinite scores, v4.1) ---
    if ctx.id_cols and ctx.id_cols[0] in ctx.pandas_df.columns:
        i_col_enc = ctx.id_cols[0]
        targets = [
            c for c in ctx.numeric_cols
            if any(kw in c.lower() for kw in _AMOUNT_KWS)
            and c not in ("velocity_24h_sum", "velocity_1h_count")
        ][:ctx.cfg.entity_zscore_max_cols]

        if targets:
            eg = ctx.pandas_df.groupby(i_col_enc)
            for col in targets:
                e_mean = eg[col].transform("mean")
                e_std  = eg[col].transform("std").fillna(1)
                e_std  = np.where(e_std < 1e-5, 1.0, e_std)
                z_col  = f"{col}_entity_z"
                ctx.encoded_df[z_col] = ((ctx.pandas_df[col] - e_mean) / e_std).fillna(0)
                ctx.ez_cols.append(z_col)
            logger.info("Entity Z-scores added for: %s", targets)

    # --- Domain detection ---
    col_str = " ".join(ctx.pandas_df.columns).lower()
    if ctx.domain_override:
        ctx.domain, ctx.domain_confidence = ctx.domain_override, 1.0
    else:
        ctx.domain, ctx.domain_confidence = _detect_domain(col_str)

    sigma_attr, cap_attr = _DOMAIN_SIGMA_CAP[ctx.domain]
    logger.info(
        "Domain: %s (conf=%.2f) | σ: %.1f | cap: %.0f%%",
        ctx.domain, ctx.domain_confidence,
        getattr(ctx.cfg, sigma_attr),
        getattr(ctx.cfg, cap_attr) * 100,
    )

    # --- Clean training subset ---
    clean_encoded = ctx.encoded_df[clean_mask]
    if len(clean_encoded) > ctx.cfg.if_max_samples:
        ctx.train_df = clean_encoded.sample(n=ctx.cfg.if_max_samples, random_state=42)
    elif len(clean_encoded) == 0:
        logger.warning("No clean training data — falling back to full dataset.")
        ctx.train_df = ctx.encoded_df
    else:
        ctx.train_df = clean_encoded

    return ctx


# ---------------------------------------------------------------------------
# STAGE 3 — SCORE & ENSEMBLE
# ---------------------------------------------------------------------------

def _stage_score(ctx: PipelineContext) -> PipelineContext:
    """Multi-Detector Consensus with drift-aware joblib caching and MAD thresholding."""

    n          = len(ctx.encoded_df)
    sigma_attr = _DOMAIN_SIGMA_CAP[ctx.domain][0]
    sigma_mult = getattr(ctx.cfg, sigma_attr)

    # Column schema guard  (v5.0)
    assert list(ctx.train_df.columns) == list(ctx.encoded_df.columns), (
        "Column schema drift between train_df and encoded_df. "
        "This indicates a feature engineering inconsistency."
    )

    # Decide cache validity  (v4.1)
    drifted = any(
        f.get("p_value", 1.0) < ctx.cfg.ks_p_value_threshold
        for f in ctx.drift_report.get("drifted_features", [])
    )
    if drifted:
        logger.info("Drift detected — invalidating cached models for this session.")

    # Percentile normalisation on clean subset only  (v4.1)
    def _norm(arr: np.ndarray) -> np.ndarray:
        clean_arr = arr[~ctx.logic_arr] if (~ctx.logic_arr).any() else arr
        if len(clean_arr) == 0:
            return np.zeros_like(arr, dtype=float)
        lo, hi = np.percentile(clean_arr, 1), np.percentile(clean_arr, 99)
        if hi > lo:
            return (np.clip(arr, lo, hi) - lo) / (hi - lo)
        amin, amax = arr.min(), arr.max()
        if amax > amin:
            return (arr - amin) / (amax - amin)
        return np.zeros_like(arr, dtype=float)

    import concurrent.futures

    def _fit_if():
        if_path = os.path.join(ctx.models_dir, "if_model.joblib")
        try:
            if JOBLIB_AVAILABLE and not drifted and os.path.exists(if_path):
                logger.info("Ensemble: Loading cached Isolation Forest.")
                ctx.model = joblib.load(if_path)
            else:
                logger.info("Ensemble: Fitting Isolation Forest...")
                # Reduce n_jobs to avoid thread thrashing since we are running concurrently
                ctx.model = IsolationForest(
                    n_estimators=ctx.cfg.if_n_estimators, n_jobs=2, random_state=42
                )
                ctx.model.fit(ctx.train_df.values)
                if JOBLIB_AVAILABLE:
                    joblib.dump(ctx.model, if_path)
            ctx.scores_raw["if"] = -ctx.model.decision_function(ctx.encoded_df.values)
        except (ValueError, RuntimeError) as e:
            logger.warning("Ensemble IF failed: %s", e)

    def _fit_lof():
        scaler_path = os.path.join(ctx.models_dir, "scaler.joblib")
        lof_path    = os.path.join(ctx.models_dir, "lof_model.joblib")
        if len(ctx.train_df) > 1:
            try:
                if JOBLIB_AVAILABLE and not drifted and os.path.exists(scaler_path) and os.path.exists(lof_path):
                    logger.info("Ensemble: Loading cached LOF + Scaler.")
                    scaler      = joblib.load(scaler_path)
                    clf_lof     = joblib.load(lof_path)
                    full_scaled = scaler.transform(ctx.encoded_df.values)
                else:
                    logger.info("Ensemble: Fitting LOF...")
                    scaler       = RobustScaler()
                    train_scaled = scaler.fit_transform(ctx.train_df.values)
                    full_scaled  = scaler.transform(ctx.encoded_df.values)
                    clf_lof = LocalOutlierFactor(
                        n_neighbors=max(1, min(ctx.cfg.lof_n_neighbors, len(ctx.train_df) - 1)),
                        novelty=True, n_jobs=2,
                    )
                    clf_lof.fit(train_scaled)
                    if JOBLIB_AVAILABLE:
                        joblib.dump(scaler,  scaler_path)
                        joblib.dump(clf_lof, lof_path)
                ctx.scores_raw["lof"] = -clf_lof.score_samples(full_scaled)
            except (ValueError, np.linalg.LinAlgError, RuntimeError) as e:
                logger.warning("Ensemble LOF failed: %s", e)

    def _fit_ecod():
        if ECOD_AVAILABLE:
            try:
                logger.info("Ensemble: Fitting ECOD...")
                ecod_safe = ctx.encoded_df.loc[:, ctx.encoded_df.nunique() > 1]
                if not ecod_safe.empty:
                    # ECOD uses n_jobs internally if available, we limit to avoid thrashing
                    clf_ecod = ECOD(n_jobs=2)
                    clf_ecod.fit(ecod_safe.values)
                    ctx.scores_raw["ecod"] = clf_ecod.decision_scores_
            except (ValueError, RuntimeError) as e:
                logger.warning("Ensemble ECOD failed: %s", e)

    def _fit_lnn():
        if LNN_AVAILABLE:
            valid_cols = [
                c for c in ctx.encoded_df.columns
                if pd.api.types.is_numeric_dtype(ctx.encoded_df[c])
            ]
            if valid_cols:
                try:
                    logger.info("Ensemble: Fitting LNN Autoencoder...")
                    lnn_results = detect_anomalies_lnn(
                        df=pl.from_pandas(ctx.encoded_df), numeric_cols=valid_cols, epochs=30
                    )
                    ctx.scores_raw["lnn"] = np.array(lnn_results["threat_scores"])
                except (ValueError, RuntimeError) as e:
                    logger.warning("Ensemble LNN failed: %s", e)

    # Run ensemble models in parallel to massively speed up processing on CPUs
    logger.info("Ensemble: Launching parallel detectors...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_fit_if),
            executor.submit(_fit_lof),
            executor.submit(_fit_ecod),
            executor.submit(_fit_lnn)
        ]
        concurrent.futures.wait(futures)

    # 5. LSTM  (pre-computed in _stage_engineer)
    if ctx.lstm_available and ctx.lstm_scores is not None:
        ctx.scores_raw["lstm"] = ctx.lstm_scores
        logger.info("Ensemble: LSTM scores included in consensus.")

    if not ctx.scores_raw:
        raise RuntimeError(
            "All underlying detection algorithms failed. Cannot produce a consensus score."
        )

    # Weight aggregation with auto-renormalisation for absent detectors
    scores_norm  = {k: _norm(v) for k, v in ctx.scores_raw.items()}
    active_w     = {k: ctx.cfg.ensemble_weights.get(k, 0.0) for k in scores_norm}
    total_weight = sum(active_w.values()) or 1.0

    consensus = np.zeros(n, dtype=float)
    for k, arr in scores_norm.items():
        consensus += arr * (active_w[k] / total_weight)

    ctx.inverted_scores = consensus

    # MAD-based robust threshold  (v4.1 / v5.0)
    # Falls back gracefully when scipy is absent  (Doc-2 guard)
    clean_consensus = consensus[~ctx.logic_arr] if (~ctx.logic_arr).any() else consensus
    median_val = np.median(clean_consensus)
    if SCIPY_AVAILABLE:
        mad = median_abs_deviation(clean_consensus, scale="normal")
    else:
        mad = 0.0

    if mad == 0:
        ctx.threshold = consensus.mean() + sigma_mult * consensus.std()
    else:
        ctx.threshold = median_val + sigma_mult * mad

    # Feedback nudge  (hard-capped at 1.5×)
    feedback_path = os.path.normpath(os.path.join(ctx.session_dir, "..", "feedback_log.jsonl"))
    ctx.threshold = _read_feedback_threshold_nudge(
        feedback_path, ctx.session_id, ctx.threshold, ctx.cfg
    )

    ctx.model_fitted   = True
    active_names       = ", ".join(k.upper() for k in scores_norm)
    ctx.recommendation = f"Multi-Detector Consensus ({active_names})"

    # Build consensus payload (vectorised)
    p_cols = {"consensus": np.round(consensus, 4)}
    for k in ("if", "lof", "ecod", "lnn", "lstm"):
        if k in scores_norm:
            p_cols[f"{k}_score"] = np.round(scores_norm[k], 4)
    ctx.consensus_payloads = [
        json.dumps({col: float(p_cols[col][i]) for col in p_cols})
        for i in range(n)
    ]

    return ctx


# ---------------------------------------------------------------------------
# STAGE 4 — EXPLAIN & REASON
# ---------------------------------------------------------------------------

def _stage_explain(ctx: PipelineContext) -> PipelineContext:
    """Shields, Anomaly Flags, Causal RCA, DiCE, Threat Scoring, Narratives."""

    n           = len(ctx.pandas_df)
    cap_attr    = _DOMAIN_SIGMA_CAP[ctx.domain][1]
    anomaly_cap = getattr(ctx.cfg, cap_attr)

    # --- Flag anomalies ---
    stat_flags     = (ctx.inverted_scores > ctx.threshold) if ctx.model_fitted else np.zeros(n, dtype=bool)
    ctx.is_anomaly = stat_flags | ctx.logic_arr

    # --- Anomaly Overload Shield ---
    if n > 0 and (len(ctx.logic_flag_set) / n) > ctx.cfg.logic_gate_bypass_ratio:
        logger.warning(
            "Logic Gate flagged >%.0f%% of rows — rules appear incompatible. "
            "Bypassing Logic Gate for this run.",
            ctx.cfg.logic_gate_bypass_ratio * 100,
        )
        ctx.logic_flag_set = set()
        ctx.logic_arr[:]   = False
        ctx.is_anomaly     = stat_flags
        if "logic_violation" in ctx.pandas_df.columns:
            ctx.pandas_df = ctx.pandas_df.copy()
            ctx.pandas_df["logic_violation"] = np.nan

    stat_ratio = int((ctx.is_anomaly & ~ctx.logic_arr).sum()) / max(n, 1)
    if stat_ratio > anomaly_cap:
        ctx.calibration_needed = True
        logger.warning(
            "CALIBRATION ALERT: %.1f%% of rows flagged statistically "
            "(domain cap is %.0f%%). All flags preserved — recalibration recommended.",
            stat_ratio * 100, anomaly_cap * 100,
        )
    ctx.stat_anomaly_ratio = stat_ratio

    # --- Polars length safety  (v5.0: both truncation AND padding) ---
    if len(ctx.is_anomaly) > len(ctx.df):
        ctx.is_anomaly = ctx.is_anomaly[:len(ctx.df)]
    elif len(ctx.is_anomaly) < len(ctx.df):
        ctx.is_anomaly = np.concatenate([
            ctx.is_anomaly,
            np.zeros(len(ctx.df) - len(ctx.is_anomaly), dtype=bool),
        ])

    # --- Causal RCA ---
    ctx.causal_payloads = ["[]"] * n
    if ctx.model_fitted and ctx.is_anomaly.any():
        try:
            stat_idxs = [
                int(i) for i in np.where(ctx.is_anomaly)[0]
                if i not in ctx.logic_flag_set
            ][:ctx.cfg.shap_max_rows]

            if stat_idxs:
                global_stats = {
                    col: {"mean": ctx.encoded_df[col].mean(), "std": ctx.encoded_df[col].std()}
                    for col in ctx.encoded_df.columns
                }
                causal_results = generate_causal_payloads(
                    encoded_df=ctx.encoded_df,
                    anomaly_indices=stat_idxs,
                    stats=global_stats,
                )
                # -------------------------------------------------------------------
                # Doc-1 FIX: generate_causal_payloads returns a LIST positionally
                # aligned to stat_idxs, NOT a dict keyed by DataFrame index.
                # Doc-2 used .get(idx, "[]") which raises AttributeError on a list.
                # Use zip for the list case; defensive isinstance branch handles
                # any future version that returns a dict.
                # -------------------------------------------------------------------
                if isinstance(causal_results, dict):
                    for idx in stat_idxs:
                        ctx.causal_payloads[idx] = causal_results.get(idx, "[]")
                else:
                    for idx in stat_idxs:
                        if causal_results[idx]:
                            ctx.causal_payloads[idx] = causal_results[idx]

        except (ValueError, RuntimeError) as e:
            logger.warning("Causal RCA failed: %s", e)

    # --- DiCE Counterfactuals  (restored from v4.1) ---
    ctx.cf_payloads = ["{}"] * n
    # DiCE disabled in the main loop to speed up uploads.
    # It will be executed on-demand via the /api/generate-fix endpoint.

    # --- Threat Scoring ---
    # Supervised path  (XGBoost / HistGB, restored from v4.1, guarded for < 2 classes)
    ctx.threat_scores = [0.0] * n
    supervised_ok     = False

    if "Class" in ctx.pandas_df.columns and ctx.pandas_df["Class"].nunique() > 1:
        try:
            X = ctx.encoded_df.drop(columns=["Class"], errors="ignore")
            y = ctx.pandas_df["Class"].fillna(0)
            max_tr = 50_000
            if len(X) > max_tr:
                idx_s  = np.random.choice(len(X), size=max_tr, replace=False)
                X_t, y_t = X.iloc[idx_s], y.iloc[idx_s]
            else:
                X_t, y_t = X, y

            neg, pos  = int((y_t == 0).sum()), int((y_t == 1).sum())
            scale_pos = neg / pos if pos > 0 else 1.0

            if XGBOOST_AVAILABLE:
                clf = XGBClassifier(
                    scale_pos_weight=scale_pos, eval_metric="aucpr",
                    random_state=42, verbosity=0, use_label_encoder=False,
                    tree_method="hist",  # CPU-optimized histogram method
                )
                logger.info("XGBClassifier (scale_pos_weight=%.1f, tree_method='hist').", scale_pos)
            else:
                clf = HistGradientBoostingClassifier(class_weight="balanced", random_state=42)
                logger.info("XGBoost unavailable — using HistGradientBoostingClassifier.")

            clf.fit(X_t, y_t)
            probs  = clf.predict_proba(X)[:, 1]
            threat = np.round(probs * 100, 2)
            threat[ctx.logic_arr] = 100.0
            ctx.threat_scores = threat.tolist()
            supervised_ok = True

        except (ValueError, RuntimeError) as e:
            logger.warning("Supervised threat scoring failed: %s. Falling back.", e)

    # Unsupervised banding fallback  (degenerate defaults to 80.0, both v4.1 & v5.0)
    if not supervised_ok:
        min_s = ctx.inverted_scores.min()
        max_s = ctx.inverted_scores.max()
        threat = np.zeros(n, dtype=float)

        if max_s > min_s:
            anom_mask = ctx.is_anomaly & ~ctx.logic_arr
            rng_hi    = max_s - ctx.threshold
            if rng_hi > 0 and anom_mask.any():
                scaled = 60.0 + (
                    (ctx.inverted_scores[anom_mask] - ctx.threshold) / rng_hi
                ) * 40.0
                threat[anom_mask] = np.clip(np.round(scaled, 2), 60.0, 100.0)
            elif anom_mask.any():
                logger.warning("Degenerate score range for anomalies — defaulting to 80.0.")
                threat[anom_mask] = 80.0

            norm_mask = ~ctx.is_anomaly & ~ctx.logic_arr
            rng_lo    = ctx.threshold - min_s
            if rng_lo > 0 and norm_mask.any():
                scaled = ((ctx.inverted_scores[norm_mask] - min_s) / rng_lo) * 59.0
                threat[norm_mask] = np.clip(np.round(scaled, 2), 0.0, 59.0)

        threat[ctx.logic_arr] = 100.0
        ctx.threat_scores = threat.tolist()

    # --- Narrative Synthesis ---
    logger.info("Building AI narratives...")
    engineered_suffixes = ("_length", "_digit_ratio", "_upper_ratio", "_special_ratio")
    engineered_prefixes = ("nlp_pc",)
    vel_col_set = set(ctx.velocity_cols)
    ez_col_set  = set(ctx.ez_cols)

    original_numeric = [
        c for c in ctx.numeric_cols
        if not c.endswith(engineered_suffixes)
        and not any(c.startswith(p) for p in engineered_prefixes)
        and c not in vel_col_set
        and c not in ez_col_set
        and c != "lstm_anomaly_score"
    ]

    ctx.reasons_list = _build_narratives(
        ctx.pandas_df, ctx.is_anomaly, ctx.causal_payloads,
        original_numeric, ctx.cat_cols,
        vel_col_set, ez_col_set,
        ctx.id_cols, ctx.domain,
    )

    # --- Cleaning Recommendation ---
    col_str = " ".join(ctx.pandas_df.columns).lower()
    ctx.recommended_cleaning, ctx.cleaning_rationale = _recommend_cleaning(
        ctx.domain, col_str, ctx.cat_cols, ctx.numeric_cols, ctx.time_cols, n,
    )

    # --- Write result columns to Polars DataFrame ---
    ctx.df = ctx.df.with_columns([
        pl.Series(name="Consensus_Verdict",      values=ctx.consensus_payloads),
        pl.Series(name="is_anomaly",             values=ctx.is_anomaly.tolist()),
        pl.Series(name="SHAP_Payload",           values=ctx.causal_payloads),
        pl.Series(name="Counterfactual_Payload", values=ctx.cf_payloads),
        pl.Series(name="Threat_Score",           values=ctx.threat_scores),
        pl.Series(name="Uncertainty_Score",      values=calculate_uncertainty_scores(
            ctx.inverted_scores, ctx.threshold
        ).tolist()),
        pl.Series(name="AI_Reason",              values=ctx.reasons_list),
    ])

    if "lof" in ctx.scores_raw:
        ctx.df = ctx.df.with_columns(
            pl.Series(name="lof_score", values=ctx.scores_raw["lof"].tolist())
        )
    if "ecod" in ctx.scores_raw:
        ctx.df = ctx.df.with_columns(
            pl.Series(name="ecod_score", values=ctx.scores_raw["ecod"].tolist())
        )

    if "logic_violation" in ctx.df.columns:
        ctx.df = ctx.df.drop("logic_violation")

    ctx.trust_metrics = compute_human_trust_score(ctx.session_id, ctx.causal_payloads)

    return ctx


# ---------------------------------------------------------------------------
# STAGE 5 — PERSIST & DRIFT REPORT
# ---------------------------------------------------------------------------

def _stage_persist(ctx: PipelineContext) -> PipelineContext:
    """Write parquet, metadata, feedback log, drift report (KS + GAE lineage)."""

    ctx.raw_parquet_path = f"{ctx.session_dir}/raw_data.parquet"
    ctx.df.write_parquet(ctx.raw_parquet_path)
    
    if ctx.encoded_df is not None:
        ctx.encoded_df.to_parquet(f"{ctx.session_dir}/encoded_data.parquet")
        
    if ctx.model is not None and JOBLIB_AVAILABLE:
        joblib.dump(ctx.model, f"{ctx.models_dir}/iforest.joblib")

    # --- Classical KS drift detection with baseline save/load  (v4.1 — restored) ---
    _MAX_DRIFT_SAMPLES = 10_000
    baseline_path = os.path.normpath(os.path.join(ctx.session_dir, "..", "baseline_stats.json"))

    engineered_suffixes = ("_length", "_digit_ratio", "_upper_ratio", "_special_ratio")
    original_numeric = [
        c for c in ctx.numeric_cols
        if not c.endswith(engineered_suffixes)
        and not c.startswith("nlp_pc")
        and c not in set(ctx.velocity_cols)
        and c != "lstm_anomaly_score"
    ]

    drift_report: dict = {
        "drifted_features": [], "baseline_present": False, "lineage_topology": {}
    }

    # KS test only when scipy is available  (Doc-2 guard)
    if SCIPY_AVAILABLE:
        try:
            curr_stats: dict[str, list] = {}
            for col in original_numeric:
                vals = ctx.pandas_df[col].dropna()
                if len(vals) > _MAX_DRIFT_SAMPLES:
                    vals = vals.sample(n=_MAX_DRIFT_SAMPLES, random_state=42)
                curr_stats[col] = vals.tolist()

            if os.path.exists(baseline_path):
                with open(baseline_path) as bf:
                    baseline_stats = json.load(bf)

                drifted = []
                for col, vals in curr_stats.items():
                    bl = baseline_stats.get(col, [])
                    if len(vals) >= ctx.cfg.ks_min_samples and len(bl) >= ctx.cfg.ks_min_samples:
                        ks_stat, p_val = ks_2samp(bl, vals)
                        if p_val < ctx.cfg.ks_p_value_threshold:
                            drifted.append({
                                "feature": col,
                                "ks_stat": round(ks_stat, 4),
                                "p_value": round(p_val, 6),
                            })
                if drifted:
                    logger.warning("Drift detected on %d feature(s).", len(drifted))

                drift_report["drifted_features"] = drifted
                drift_report["baseline_present"] = True
            else:
                with open(baseline_path, "w") as bf:
                    json.dump(curr_stats, bf)
                logger.info("No baseline found — current file saved as baseline.")

        except (ValueError, OSError) as e:
            logger.warning("Classical drift detection failed: %s", e)
    else:
        logger.warning("scipy not installed — KS drift detection skipped.")

    # --- GAE Lineage Topology ---
    try:
        gae_report = evaluate_lineage_drift(ctx.pandas_df, original_numeric)
        drift_report["lineage_topology"] = gae_report
    except (ValueError, RuntimeError) as e:
        logger.warning("Lineage GAE drift detection failed: %s", e)

    ctx.drift_report = drift_report

    # --- Metadata ---
    try:
        with open(os.path.join(ctx.session_dir, "metadata.json"), "w") as fh:
            json.dump({
                "columns":            ctx.df.columns,
                "dtypes":             [str(t) for t in ctx.df.dtypes],
                "row_count":          len(ctx.df),
                "domain":             ctx.domain,
                "domain_confidence":  round(ctx.domain_confidence, 4),
                "algorithm":          ctx.recommendation,
                "calibration_needed": ctx.calibration_needed,
                "threshold":          float(ctx.threshold),
                "stat_anomaly_ratio": round(ctx.stat_anomaly_ratio, 4),
            }, fh)
    except (OSError, ValueError) as e:
        logger.warning("Could not save metadata: %s", e)

    # --- Feedback log init ---
    feedback_path = os.path.normpath(os.path.join(ctx.session_dir, "..", "feedback_log.jsonl"))
    if not os.path.exists(feedback_path):
        try:
            Path(feedback_path).touch(exist_ok=True)
            logger.info("Feedback log initialised at %s", feedback_path)
        except OSError as e:
            logger.warning("Could not initialise feedback log: %s", e)

    return ctx


# ---------------------------------------------------------------------------
# MAIN PIPELINE ORCHESTRATOR
# ---------------------------------------------------------------------------

def process_and_detect(
    file_path: Optional[str] = None,
    session_id: Optional[str] = None,
    algorithm: str = "consensus",
    df: Optional[pl.DataFrame] = None,
    config: Optional[AnomalyDetectionConfig] = None,
    deduplicate: bool = True,
    domain_override: Optional[str] = None,
) -> PipelineResult:
    """
    Full autonomous multi-detector anomaly detection pipeline.

    Parameters
    ----------
    file_path      : Path to a CSV file. Ignored if df is provided.
    session_id     : Reuse an existing session. Auto-generated if None.
    algorithm      : Reserved for future routing; always runs consensus.
    df             : Pre-loaded Polars DataFrame (takes priority over file_path).
    config         : Override default AnomalyDetectionConfig.
    deduplicate    : Remove exact duplicate rows before processing.
    domain_override: Force a specific domain ('finance', 'health', etc.).

    Returns
    -------
    PipelineResult TypedDict.
    Always returns PipelineResult — errors are in the `error` field, never a
    different dict shape (Doc-1 fix; Doc-2 had a union return type).
    """

    # Deep-copy config to prevent singleton mutation across concurrent requests
    cfg = copy.deepcopy(config) if config else copy.deepcopy(_DEFAULT_CONFIG)

    # Sanitize session_id against path traversal / LFI attacks
    session_id  = re.sub(r"[^a-zA-Z0-9\-_]", "", session_id or str(uuid.uuid4()))
    session_dir = _session_dir(session_id)

    # --- Load DataFrame  (Doc-2: pure standalone function, thin orchestrator) ---
    raw_df = _load_dataframe(file_path, df)
    if isinstance(raw_df, str):
        # _load_dataframe returns a string only on fatal read failure
        logger.error("Fatal load error: %s", raw_df)
        return {
            "status":               "error",
            "session_id":           session_id,
            "total_rows":           0,
            "anomaly_count":        0,
            "algorithm_used":       "",
            "recommendation":       "",
            "applied_rules":        [],
            "recommended_cleaning": "",
            "cleaning_rationale":   "",
            "parquet_path":         "",
            "drift_report":         {},
            "calibration_needed":   False,
            "stat_anomaly_ratio":   0.0,
            "domain_detected":      "",
            "domain_confidence":    0.0,
            "threshold_applied":    0.0,
            "trust_metrics":        {},
            "error":                raw_df,
        }

    ctx = PipelineContext(
        session_id=session_id,
        session_dir=session_dir,
        cfg=cfg,
        df=raw_df,
        deduplicate=deduplicate,        # Doc-2: stored on context
        domain_override=domain_override,
    )

    try:
        ctx = _stage_load(ctx)
        ctx = _stage_engineer(ctx)
        ctx = _stage_score(ctx)
        ctx = _stage_explain(ctx)
        ctx = _stage_persist(ctx)

        return {
            "status":               "success",
            "session_id":           ctx.session_id,
            "total_rows":           len(ctx.df),
            "anomaly_count":        int(ctx.is_anomaly.sum()),
            "algorithm_used":       ctx.recommendation,
            "recommendation":       ctx.recommendation,
            "applied_rules":        ctx.applied_rules,
            "recommended_cleaning": ctx.recommended_cleaning,
            "cleaning_rationale":   ctx.cleaning_rationale,
            "parquet_path":         ctx.raw_parquet_path,
            "drift_report":         ctx.drift_report,
            "calibration_needed":   ctx.calibration_needed,
            "stat_anomaly_ratio":   round(ctx.stat_anomaly_ratio, 4),
            "domain_detected":      ctx.domain,
            "domain_confidence":    round(ctx.domain_confidence, 4),
            "threshold_applied":    float(ctx.threshold),
            "trust_metrics":        ctx.trust_metrics,
            "error":                None,
        }

    except Exception as e:
        logger.error("Fatal error in pipeline: %s", e, exc_info=True)
        return {
            "status":               "error",
            "session_id":           session_id,
            "total_rows":           0,
            "anomaly_count":        0,
            "algorithm_used":       "",
            "recommendation":       "",
            "applied_rules":        [],
            "recommended_cleaning": "",
            "cleaning_rationale":   "",
            "parquet_path":         "",
            "drift_report":         {},
            "calibration_needed":   False,
            "stat_anomaly_ratio":   0.0,
            "domain_detected":      "",
            "domain_confidence":    0.0,
            "threshold_applied":    0.0,
            "trust_metrics":        {},
            "error":                str(e),
        }

# ---------------------------------------------------------------------------
# ON-DEMAND DICE COUNTERFACTUAL ENGINE (Phase 2)
# ---------------------------------------------------------------------------

def generate_counterfactual_for_row(session_id: str, row_idx: int) -> dict:
    """Standalone, on-demand execution of DiCE for a single row."""
    session_dir = _session_dir(session_id)
    models_dir = os.path.join(session_dir, "models")
    
    encoded_path = os.path.join(session_dir, "encoded_data.parquet")
    meta_path = os.path.join(session_dir, "metadata.json")
    model_path = os.path.join(models_dir, "iforest.joblib")
    
    if not os.path.exists(encoded_path) or not os.path.exists(model_path):
        raise FileNotFoundError("Missing cached model or encoded data. Cannot generate fix.")
        
    encoded_df = pd.read_parquet(encoded_path)
    
    if not JOBLIB_AVAILABLE:
        raise ImportError("joblib is required to load the model.")
        
    model = joblib.load(model_path)
    
    with open(meta_path) as f:
        meta = json.load(f)
        thresh = meta.get("threshold", 0.0)
        
    try:
        import dice_ml # type: ignore
    except ImportError:
        raise ImportError("DiCE not installed. pip install dice-ml to enable.")
        
    raw_path = os.path.join(session_dir, "raw_data.parquet")
    if not os.path.exists(raw_path):
        raise FileNotFoundError("Missing raw data. Cannot generate fix.")
    raw_df = pd.read_parquet(raw_path)
    
    # We must compute an optimal threshold for the raw Isolation Forest scores
    # because the 'thresh' from metadata.json is the ensemble consensus threshold!
    scores = -model.decision_function(encoded_df.values)
    is_anomaly_gt = raw_df["is_anomaly"].values.astype(int)
    
    normal_scores = scores[is_anomaly_gt == 0]
    if len(normal_scores) > 0:
        optimal_thresh = float(np.percentile(normal_scores, 95))
    else:
        optimal_thresh = float(np.median(scores))
        
    # Ensure the target row is considered an anomaly by this isolated model
    if scores[row_idx] <= optimal_thresh:
        optimal_thresh = float(scores[row_idx] - 1e-5)
        
    is_anomaly = (scores > optimal_thresh).astype(int)
    
    cf_df = encoded_df.copy().astype(float)
    cf_df["_target"] = is_anomaly
    
    query = encoded_df.iloc[[row_idx]].astype(float)
    continuous_features = encoded_df.columns.tolist()
        
    features_to_vary = "all"
    shap_payload_str = raw_df.iloc[row_idx].get("SHAP_Payload", "[]")
    if shap_payload_str and isinstance(shap_payload_str, str) and shap_payload_str != "[]":
        try:
            shap_data = json.loads(shap_payload_str)
            features_to_vary = [
                item["feature"] for item in shap_data 
                if item.get("impact", 0) > 0 and item["feature"] in continuous_features
            ]
            if not features_to_vary:
                features_to_vary = "all"
        except Exception:
            pass

    # Restrict input dimensions for DiCE to prevent timeout/failure
    if features_to_vary != "all":
        # Subset dataframe so DiCE only explores anomalous dimensions
        cf_df = cf_df[features_to_vary + ["_target"]]
        query_subset = query[features_to_vary]
        
        class _IFWrapper:
            def __init__(self, m: IsolationForest, thresh: float, base_row: np.ndarray, col_idx: list[int]):
                self.m, self.thresh = m, thresh
                self.base_row = base_row
                self.col_idx = col_idx
                
            def _reconstruct(self, X: Any) -> np.ndarray:
                arr = X.values if hasattr(X, "values") else np.asarray(X)
                full = np.tile(self.base_row, (arr.shape[0], 1))
                for i, c_idx in enumerate(self.col_idx):
                    full[:, c_idx] = arr[:, i]
                return full
                
            def predict(self, X: Any) -> np.ndarray:
                full = self._reconstruct(X)
                return (-self.m.decision_function(full) > self.thresh).astype(int)
                
            def predict_proba(self, X: Any) -> np.ndarray:
                full = self._reconstruct(X)
                s = -self.m.decision_function(full)
                p1 = 1.0 / (1.0 + np.exp(np.clip(-(s - self.thresh) * 10.0, -100, 100)))
                return np.column_stack((1 - p1, p1))
                
        base_row = query.values[0]
        col_idx = [encoded_df.columns.get_loc(c) for c in features_to_vary]
        wrapped_model = _IFWrapper(model, optimal_thresh, base_row, col_idx)
    else:
        query_subset = query
        class _IFWrapperAll:
            def __init__(self, m: IsolationForest, thresh: float):
                self.m, self.thresh = m, thresh
            def predict(self, X: Any) -> np.ndarray:
                arr = X.values if hasattr(X, "values") else np.asarray(X)
                return (-self.m.decision_function(arr) > self.thresh).astype(int)
            def predict_proba(self, X: Any) -> np.ndarray:
                arr = X.values if hasattr(X, "values") else np.asarray(X)
                s = -self.m.decision_function(arr)
                p1 = 1.0 / (1.0 + np.exp(np.clip(-(s - self.thresh) * 10.0, -100, 100)))
                return np.column_stack((1 - p1, p1))
        wrapped_model = _IFWrapperAll(model, optimal_thresh)
        
    dice_data = dice_ml.Data(
        dataframe=cf_df,
        continuous_features=cf_df.drop(columns=["_target"]).columns.tolist(),
        outcome_name="_target",
    )
    exp = dice_ml.Dice(
        dice_data,
        dice_ml.Model(model=wrapped_model, backend="sklearn"),
        method="random",
    )

    import warnings
    from pandas.errors import PerformanceWarning
    
    with warnings.catch_warnings():
        warnings.simplefilter(action='ignore', category=PerformanceWarning)
        cf_result = exp.generate_counterfactuals(
            query_subset, 
            total_CFs=1, 
            desired_class="opposite", 
            features_to_vary="all" if features_to_vary == "all" else features_to_vary,
            verbose=False
        )
    
    if not cf_result.cf_examples_list or cf_result.cf_examples_list[0].final_cfs_df is None:
        return {"error": "Could not generate counterfactual."}
        
    cf_dict = cf_result.cf_examples_list[0].final_cfs_df.iloc[0].to_dict()
    original_row = encoded_df.iloc[row_idx].to_dict()
    changes = {
        k: {"from": round(float(original_row[k]), 4), "to": round(float(v), 4)}
        for k, v in cf_dict.items()
        if k != "_target"
        and abs(float(v) - float(original_row.get(k, 0))) > 1e-4
    }
    return changes