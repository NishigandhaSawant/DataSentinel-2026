"""
DataSentinel — Cleaning Engine  (v3 — Hardened Edition)
=========================================================

Changes from Godmode Edition
------------------------------
[FIX]   Mask action was a stub — now fully implemented: uses Polars
        when/then to replace string values in anomalous rows with [REDACTED]
        in a single vectorised pass. Identity columns (IDs) are preserved.

[FIX]   GDPR PII Scrubber was a stub — now implemented: detects PII columns
        by regex pattern on column names, pseudonymises strings with a
        SHA-256 prefix, and zeros numeric PII. Applied to ALL rows, not just
        anomalies, before the output file is written.

[FIX]   apply_rl_cleaning is now a lazy import inside the impute branch —
        a missing engines.rl_cleaner no longer crashes the entire module
        at startup. Returns a clear error instead.

[FIX]   RL result validation added — missing or wrong-typed cleaned_df
        surfaces a descriptive error rather than a bare KeyError. Also captures
        MDP reward scores.

[FIX]   drop and quarantine are now distinct actions:
        - drop   : removes anomalous rows, no recovery path.
        - quarantine: moves them to quarantined_data.parquet + a JSON audit
          sidecar with timestamp and row count. Forensic evidence preserved.

[FIX]   Winsorize now only modifies anomalous rows. Clean rows are never
        touched. Implemented via pl.when(mask).then(clip).otherwise(col) in
        a single vectorised pass — no split/concat, row order preserved.

[FIX]   Empty-DataFrame guard: warns and still writes a valid (empty) parquet
        rather than crashing downstream readers.

[FIX]   All path joins converted to os.path.join for cross-platform safety.

[PERF]  Column drop list is built once; a single df.drop() call replaces
        the previous multi-condition loop.

[PERF]  All per-column transformations (mask, winsorize, PII) are expressed
        as Polars expression lists and applied in one with_columns() call
        per action — avoids repeated full-DataFrame copies.

[AUDIT] Every action logs before/after row counts.
[AUDIT] Quarantine writes a JSON metadata sidecar for audit trail.
[AUDIT] Return dict includes rows_delta and pii_cols_scrubbed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

import polars as pl

from utils import _session_dir, logger


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

_ALWAYS_DROP: frozenset[str] = frozenset({
    "is_anomaly", "AI_Reason", "Threat_Score", "SHAP_Payload",
    "Counterfactual_Payload", "lof_score", "ecod_score", "lstm_anomaly_score",
})

_ENGINEERED_SUFFIXES: tuple[str, ...] = (
    "_freq", "_length", "_digit_ratio", "_upper_ratio", "_special_ratio",
)

_ENGINEERED_PREFIXES: tuple[str, ...] = ("nlp_pc",)

_VELOCITY_COLS: frozenset[str] = frozenset({"velocity_24h_sum", "velocity_1h_count"})

# Columns to protect from masking so anomalous rows remain traceable
_IDENTITY_COL_SUBSTRINGS: tuple[str, ...] = (
    "_id", "id_", "user", "account", "customer", "transaction",
)

# PII column name patterns — matched case-insensitively against column names
_PII_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bemail\b",          r"\bphone\b",         r"\bmobile\b",
        r"\bssn\b",            r"\bsocial.?security\b", r"\bpassport\b",
        r"\bdob\b",            r"\bdate.?of.?birth\b",  r"\bbirthday\b",
        r"\baddress\b",        r"\bpostcode\b",        r"\bzip.?code\b",
        r"\bip.?addr\b",       r"\bfirst.?name\b",    r"\blast.?name\b",
        r"\bfull.?name\b",     r"\bnational.?id\b",   r"\bnat.?id\b",
        r"\bdriv.?lic\b",      r"\bcard.?num\b",      r"\bcc.?num\b",
        r"\baccount.?num\b",
    )
)

_SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    {"drop", "quarantine", "winsorize", "mask", "impute"}
)


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

def _anomaly_mask(df: pl.DataFrame) -> pl.Series:
    """Return a boolean Series — True where is_anomaly is True."""
    if "is_anomaly" in df.columns:
        return df["is_anomaly"].cast(pl.Boolean)
    return pl.Series("is_anomaly", [False] * len(df), dtype=pl.Boolean)


def _build_cols_to_drop(df: pl.DataFrame) -> list[str]:
    """Collect internal/engineered column names that should be stripped on export."""
    return [
        c for c in df.columns
        if c in _ALWAYS_DROP
        or c in _VELOCITY_COLS
        or c.endswith(_ENGINEERED_SUFFIXES)
        or any(c.startswith(p) for p in _ENGINEERED_PREFIXES)
        or c.startswith("Score_CI")
    ]


def _detect_pii_columns(columns: list[str]) -> list[str]:
    """Return column names that match any known PII regex pattern."""
    return [c for c in columns if any(pat.search(c) for pat in _PII_PATTERNS)]


def _scrub_pii(df: pl.DataFrame, pii_cols: list[str]) -> pl.DataFrame:
    """
    Pseudonymise PII columns across all rows.

    - String columns  → SHA-256 hex prefix (12 chars) — one-way, consistent
      within a run so joins on the pseudonymised value still work.
    - Numeric columns → zeroed (e.g. SSN stored as int).
    """
    if not pii_cols:
        return df

    def _hash(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return hashlib.sha256(v.encode()).hexdigest()[:12]

    exprs = []
    for col in pii_cols:
        if col not in df.columns:
            continue
        dtype = df[col].dtype
        if dtype in (pl.Utf8, pl.String):
            exprs.append(
                pl.col(col)
                .map_elements(_hash, return_dtype=pl.Utf8)
                .alias(col)
            )
        elif dtype in pl.NUMERIC_DTYPES:
            exprs.append(pl.lit(0).cast(dtype).alias(col))

    return df.with_columns(exprs) if exprs else df


# ---------------------------------------------------------------------------
# CLEANING ACTIONS  (each returns (cleaned_df, report_dict))
# ---------------------------------------------------------------------------

def _action_drop(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Remove anomalous rows. No quarantine file — rows are gone."""
    mask = _anomaly_mask(df)
    cleaned = df.filter(~mask)
    dropped = int(mask.sum())
    logger.info("DROP: removed %d anomalous rows.", dropped)
    return cleaned, {"info": "Drop applied.", "rows_removed": dropped}


def _action_quarantine(
    df: pl.DataFrame, session_dir: str
) -> tuple[pl.DataFrame, dict]:
    """
    Move anomalous rows to quarantined_data.parquet for analyst review.
    A JSON sidecar records the timestamp, row count, and file path for
    audit trail purposes. Clean rows are returned unchanged.
    """
    mask = _anomaly_mask(df)
    quarantined = df.filter(mask)
    cleaned = df.filter(~mask)
    report: dict = {"info": "Quarantine applied.", "quarantined_rows": len(quarantined)}

    if len(quarantined) > 0:
        q_path = os.path.join(session_dir, "quarantined_data.parquet")
        quarantined.write_parquet(q_path)
        report["quarantine_path"] = q_path

        # Audit sidecar
        meta_path = os.path.join(session_dir, "quarantine_meta.json")
        try:
            with open(meta_path, "w") as fh:
                json.dump(
                    {
                        "quarantined_at": datetime.now(timezone.utc).isoformat(),
                        "quarantined_rows": len(quarantined),
                        "parquet_path": q_path,
                    },
                    fh,
                    indent=2,
                )
        except OSError as e:
            logger.warning("Could not write quarantine audit sidecar: %s", e)

        logger.info("QUARANTINE: %d rows vaulted → %s.", len(quarantined), q_path)
    else:
        logger.info("QUARANTINE: no anomalous rows to vault.")

    return cleaned, report


def _action_winsorize(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """
    Clip values in anomalous rows to the 5th/95th percentile bounds derived
    from clean (non-anomalous) rows. Clean rows are never modified.

    Implemented as a single vectorised with_columns() pass using
    pl.when(anomaly_mask).then(clip).otherwise(original) — no split/concat,
    row order is fully preserved.
    """
    mask = _anomaly_mask(df)
    anomaly_count = int(mask.sum())
    normal_rows = df.filter(~mask)

    numeric_cols = [
        c for c, dtype in zip(df.columns, df.dtypes)
        if dtype in pl.NUMERIC_DTYPES
        and c not in _ALWAYS_DROP
        and c not in _VELOCITY_COLS
        and c not in {"is_anomaly", "Threat_Score"}
    ]

    if anomaly_count == 0 or len(normal_rows) == 0:
        logger.warning(
            "WINSORIZE: %s — skipping.",
            "no anomalies flagged" if anomaly_count == 0 else "no clean baseline",
        )
        return df, {"info": "Winsorize skipped — insufficient data.", "cols_clipped": 0}

    clip_exprs = []
    clipped_cols: list[str] = []
    for col in numeric_cols:
        low = normal_rows[col].quantile(0.05)
        high = normal_rows[col].quantile(0.95)
        if low is None or high is None or low == high:
            continue
        # Only clip values in anomalous rows; clean rows pass through unchanged
        clip_exprs.append(
            pl.when(mask)
            .then(pl.col(col).clip(low, high))
            .otherwise(pl.col(col))
            .alias(col)
        )
        clipped_cols.append(col)

    cleaned = df.with_columns(clip_exprs) if clip_exprs else df
    logger.info(
        "WINSORIZE: clipped %d col(s) on %d anomalous rows.",
        len(clipped_cols), anomaly_count,
    )
    return cleaned, {
        "info": "Winsorize applied to anomalous rows only.",
        "cols_clipped": len(clipped_cols),
        "anomalous_rows_clipped": anomaly_count,
    }


def _action_mask(df: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """
    Replace string/text values in anomalous rows with [REDACTED].
    Identity columns (those whose names contain ID-like substrings) are
    preserved so flagged rows remain traceable. Numeric columns are untouched.

    Implemented as a single vectorised with_columns() pass.
    """
    mask = _anomaly_mask(df)
    anomaly_count = int(mask.sum())

    if anomaly_count == 0:
        return df, {"info": "Mask applied.", "anomalous_rows_masked": 0, "cols_masked": 0}

    # String columns that are not identity/traceability columns
    string_cols = [
        c for c, dtype in zip(df.columns, df.dtypes)
        if dtype in (pl.Utf8, pl.String)
        and not any(kw in c.lower() for kw in _IDENTITY_COL_SUBSTRINGS)
        and c not in _ALWAYS_DROP
    ]

    if not string_cols:
        logger.info("MASK: no maskable string columns found.")
        return df, {"info": "Mask applied.", "anomalous_rows_masked": anomaly_count, "cols_masked": 0}

    exprs = [
        pl.when(mask)
        .then(pl.lit("[REDACTED]"))
        .otherwise(pl.col(c))
        .alias(c)
        for c in string_cols
    ]

    cleaned = df.with_columns(exprs)
    logger.info(
        "MASK: redacted %d string col(s) across %d anomalous rows.",
        len(string_cols), anomaly_count,
    )
    return cleaned, {
        "info": "Mask applied.",
        "anomalous_rows_masked": anomaly_count,
        "cols_masked": len(string_cols),
        "cols_masked_list": string_cols,
    }


def _action_impute(df: pl.DataFrame, session_id: str) -> tuple[pl.DataFrame, dict]:
    """
    Delegate to the RL Autonomous Remediation Agent.
    Import is lazy so a missing engines.rl_cleaner does not crash the module.
    """
    try:
        from engines.rl_cleaner import apply_rl_cleaning  # noqa: PLC0415
    except ImportError:
        raise RuntimeError(
            "RL cleaner unavailable — install engines.rl_cleaner "
            "or choose a different action."
        )

    logger.info("Engaging RL Autonomous Remediation Agent...")
    rl_result = apply_rl_cleaning(df, session_id)

    if not isinstance(rl_result, dict):
        raise TypeError(
            f"RL cleaner returned {type(rl_result).__name__}; expected dict."
        )
    if "cleaned_df" not in rl_result:
        raise KeyError(
            "RL cleaner result is missing 'cleaned_df'. "
            f"Keys present: {list(rl_result.keys())}"
        )
    cleaned_df = rl_result["cleaned_df"]
    if not isinstance(cleaned_df, pl.DataFrame):
        raise TypeError(
            f"RL cleaner 'cleaned_df' is {type(cleaned_df).__name__}; "
            "expected pl.DataFrame."
        )

    # Capture the report and append the total RL reward
    report = rl_result.get("reclean_report", {"info": "RL cleaning complete."})
    if "total_reward" in rl_result:
        report["total_reward"] = rl_result["total_reward"]

    logger.info(
        "RL Agent complete. Rows: %d → %d. Total Reward: %.4f", 
        len(df), len(cleaned_df), rl_result.get("total_reward", 0.0)
    )
    return cleaned_df, report


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def clean_dataset(session_id: str, action: str = "drop") -> dict:
    """
    Apply an enterprise cleaning action to a previously detected dataset.

    Parameters
    ----------
    session_id : str
        Session produced by process_and_detect().
    action : str
        One of: ``"drop"``, ``"quarantine"``, ``"winsorize"``,
        ``"mask"``, ``"impute"``.

    Returns
    -------
    dict
        status, action_taken, original_rows, new_total, rows_delta,
        pii_cols_scrubbed, reclean_report, output_path — or "error" key
        on failure.
    """
    session_dir = _session_dir(session_id)
    raw_parquet_path = os.path.join(session_dir, "raw_data.parquet")

    if not os.path.exists(raw_parquet_path):
        return {"error": "Dataset not found. Run process_and_detect() first."}

    action = action.lower().strip()
    if action not in _SUPPORTED_ACTIONS:
        return {
            "error": (
                f"Unknown action '{action}'. "
                f"Choose from: {sorted(_SUPPORTED_ACTIONS)}."
            )
        }

    try:
        df = pl.read_parquet(raw_parquet_path)
    except Exception as e:
        return {"error": f"Failed to read dataset: {e}"}

    original_count = len(df)
    logger.info(
        "Cleaning | session=%s action=%s rows=%d", session_id, action, original_count
    )

    # ── GDPR PII SCRUB (all rows, all PII cols) ──
    pii_cols = _detect_pii_columns(df.columns)
    if pii_cols:
        logger.info(
            "PII scrubber: pseudonymising %d column(s): %s", len(pii_cols), pii_cols
        )
        try:
            df = _scrub_pii(df, pii_cols)
        except Exception as e:
            logger.error("PII scrubbing failed: %s", e, exc_info=True)
            return {"error": f"PII scrubbing failed: {e}"}

    # ── DISPATCH ──
    try:
        if action == "impute":
            cleaned_df, reclean_report = _action_impute(df, session_id)
        elif action == "drop":
            cleaned_df, reclean_report = _action_drop(df)
        elif action == "quarantine":
            cleaned_df, reclean_report = _action_quarantine(df, session_dir)
        elif action == "winsorize":
            cleaned_df, reclean_report = _action_winsorize(df)
        elif action == "mask":
            cleaned_df, reclean_report = _action_mask(df)
        else:
            return {"error": f"Unhandled action: {action}"}  # unreachable
    except Exception as e:
        logger.error("Cleaning action '%s' failed: %s", action, e, exc_info=True)
        return {"error": f"Cleaning failed during '{action}': {e}"}

    if len(cleaned_df) == 0:
        logger.warning(
            "Cleaning produced an empty DataFrame — were all rows anomalous?"
        )

    # ── STRIP INTERNAL / ENGINEERED COLUMNS ──
    cols_to_drop = _build_cols_to_drop(cleaned_df)
    if cols_to_drop:
        present = [c for c in cols_to_drop if c in cleaned_df.columns]
        cleaned_df = cleaned_df.drop(present)
        logger.info("Stripped %d internal column(s).", len(present))

    # ── PERSIST ──
    out_path = os.path.join(session_dir, "cleaned_data.parquet")
    try:
        cleaned_df.write_parquet(out_path)
    except Exception as e:
        logger.error("Failed to write cleaned dataset: %s", e)
        return {"error": f"Write failed: {e}"}

    logger.info(
        "Done | %d → %d rows (delta: -%d).",
        original_count, len(cleaned_df), original_count - len(cleaned_df),
    )

    return {
        "status":           "success",
        "action_taken":     action,
        "original_rows":    original_count,
        "new_total":        len(cleaned_df),
        "rows_delta":       original_count - len(cleaned_df),
        "pii_cols_scrubbed": pii_cols,
        "reclean_report":   reclean_report,
        "output_path":      out_path,
    }