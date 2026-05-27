"""
DataSentinel — FastAPI Application
API routes, file upload handling, and session management.

Includes Active Learning feedback loops, RL Remediation triggers,
Smart Schema Versioning, and strict Session Purging.
"""

import os
import re
import json
import uuid
import shutil
from datetime import datetime, timezone
import io

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        import numpy as np
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj) if not np.isnan(obj) else None
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

# Load .env file before anything else reads environment variables
from dotenv import load_dotenv

load_dotenv()

# Bypass Loky/Joblib CPU counting bug on Windows
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "4")
# Prevent OpenMP and BLAS from spawning hundreds of threads
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import polars as pl
import shutil
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Query, Depends, Request, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from utils import (
    _session_dir,
    _BACKEND_DIR,
    logger,
    validate_session_id,
    cleanup_stale_sessions,
)
from schema import SchemaEnforcer
from auth import require_api_key, is_auth_enabled
from engines import (
    process_and_detect,
    generate_counterfactual_for_row,
    clean_dataset,
    get_viz_data,
    generate_insights,
    execute_natural_query_stream,
    confirm_and_execute_edit,
    generate_quality_report,
    scan_for_pii,
    pseudonymise_columns,
)

# --- RATE LIMITER (in-memory, per-IP) ----------------------------------------
limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

logger.info(
    "Auth: %s | Rate limiting: enabled",
    "ENABLED (DS_API_KEY is set)" if is_auth_enabled() else "DISABLED (no DS_API_KEY)",
)

# ── ACTIVE LEARNING FEEDBACK MODEL ───────────────────────────────────────────
class FeedbackRequest(BaseModel):
    row_index: int
    label: int  # 1 for True Positive (Confirm Anomaly), 0 for False Positive

@app.post("/api/feedback/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def submit_active_learning_feedback(request: Request, session_id: str, payload: FeedbackRequest):
    try:
        session_dir = _session_dir(session_id)
        feedback_path = os.path.join(session_dir, "feedback_log.jsonl")
        os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
        
        feedback_entry = {
            "session_id": session_id,
            "row_index": payload.row_index,
            "label": payload.label,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with open(feedback_path, "a") as f:
            f.write(json.dumps(feedback_entry) + "\n")
            
        return {"status": "success", "message": "Feedback recorded for RL/Threshold tuning."}
    except Exception as e:
        logger.error("Error saving feedback: %s", e)
        return JSONResponse(status_code=500, content={"error": "Failed to record feedback"})

# ── ON-DEMAND FIX GENERATION ─────────────────────────────────────────────────
class GenerateFixRequest(BaseModel):
    row_idx: int

@app.post("/api/generate-fix/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
def generate_fix(request: Request, session_id: str, payload: GenerateFixRequest):
    try:
        if not validate_session_id(session_id):
            return JSONResponse(status_code=400, content={"error": "Invalid session ID"})
            
        changes = generate_counterfactual_for_row(session_id, payload.row_idx)
        
        if "error" in changes:
            return JSONResponse(status_code=400, content=changes)
            
        return {"status": "success", "fix": changes}
    except Exception as e:
        logger.error("Error generating fix for %s: %s", session_id, e)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/session/{session_id}/delete")
@limiter.limit("60/minute")  # raised: rapid beacon retries must not be 429'd
def delete_session(request: Request, session_id: str):
    """
    Called via navigator.sendBeacon (or direct POST) from the frontend when the
    user triggers a session reset.  Deletes both the on-disk session directory
    AND the in-memory job_status entry so nothing leaks.

    NOTE: We compute the session path manually here instead of calling
    _session_dir() because _session_dir() calls os.makedirs() which would
    re-create an empty directory immediately after we just deleted it.
    """
    try:
        validate_session_id(session_id)  # raises ValueError on bad input

        # Build path without calling _session_dir (which re-creates the dir)
        session_dir = os.path.join(_BACKEND_DIR, "sessions", session_id)

        deleted_files = False
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir, ignore_errors=True)
            deleted_files = True
            logger.info("Session %s: on-disk data purged.", session_id)

        # Also evict the in-memory job status so stale progress data can't
        # bleed into a future session with the same ID (extremely unlikely but
        # correct to clean up).
        if session_id in job_status:
            del job_status[session_id]
            logger.info("Session %s: in-memory job_status evicted.", session_id)

        if deleted_files:
            return {"status": "success", "message": "Session fully purged"}
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})
    except Exception as e:
        logger.error("Error deleting session %s: %s", session_id, e)
        return JSONResponse(status_code=500, content={"error": "Failed to delete session"})

# ── REINFORCEMENT LEARNING REMEDIATION ENGINE ──────────────────────────────────────────────────────
class KnowledgeRule(BaseModel):
    term: str
    logic: str
    description: str
    keywords: list[str]

@app.post("/api/knowledge/learn", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
def teach_agent(request: Request, payload: KnowledgeRule):
    dict_path = os.path.join(_BACKEND_DIR, "data", "business_dictionary.json")
    
    if not os.path.exists(dict_path):
        kb_data = {"version": "2.0.0", "knowledge_base": {"user_defined": []}}
    else:
        with open(dict_path, "r") as f:
            kb_data = json.load(f)
            
    if "user_defined" not in kb_data["knowledge_base"]:
        kb_data["knowledge_base"]["user_defined"] = []

    new_rule = {
        "term": payload.term,
        "keywords": payload.keywords,
        "logic": payload.logic,
        "description": payload.description
    }
    kb_data["knowledge_base"]["user_defined"].append(new_rule)

    os.makedirs(os.path.dirname(dict_path), exist_ok=True)
    with open(dict_path, "w") as f:
        json.dump(kb_data, f, indent=2)

    return {"status": "success", "message": f"Agent successfully learned the rule for '{payload.term}'."}

# ── LIVE DATABASE CONNECTOR ──────────────────────────────────────────────────
class DBConnectionRequest(BaseModel):
    uri: str  

@app.post("/api/connect-db/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
def connect_postgres(request: Request, session_id: str, payload: DBConnectionRequest):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    if not payload.uri.startswith(("postgres://", "postgresql://")):
        return JSONResponse(status_code=400, content={"error": "Only PostgreSQL URIs are supported in this version."})

    session_dir = _session_dir(session_id)
    config_path = os.path.join(session_dir, "db_config.json")

    with open(config_path, "w") as f:
        json.dump({"db_uri": payload.uri, "type": "postgres"}, f)

    return {"status": "success", "message": "PostgreSQL Database successfully linked."}

# ── AUDIT LOG ENDPOINT ───────────────────────────────────────────────────────
@app.get("/api/admin/audit-logs", dependencies=[Depends(require_api_key)])
@limiter.limit("30/minute")
def get_audit_logs(request: Request, limit: int = Query(100)):
    audit_file = os.path.join(_BACKEND_DIR, "logs", "audit_trail.jsonl")
    if not os.path.exists(audit_file):
        return {"logs": []}
        
    logs = []
    try:
        with open(audit_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        return {"logs": list(reversed(logs))[:limit]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to read logs: {str(e)}"})

# --- CORS --------------------------------------------------------------------
_ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "DataSentinel detection engine is online."}

@app.get("/api/health")
def health_check():
    from groq_client import check_groq_connectivity
    connected = check_groq_connectivity()
    return {"groq": connected, "engine": "Groq LPU Cloud"}


# ── SESSION PURGE ENDPOINT (FOR PAGE REFRESH) ────────────────────────────────
@app.delete("/api/session/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("30/minute")
def reset_session(request: Request, session_id: str):
    """
    Deletes the entire session directory. 
    Called by the frontend when the user refreshes the page to ensure a sterile environment.
    """
    try:
        validate_session_id(session_id)
        session_dir = _session_dir(session_id)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir, ignore_errors=True)
            logger.info(f"Session {session_id} successfully purged due to user refresh.")
            
        if session_id in job_status:
            del job_status[session_id]
            
        return {"status": "success", "message": "Session environment dumped and sterilized."}
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})


# ── BACKGROUND JOB PROCESSOR ─────────────────────────────────────────────────
job_status = {}
def update_job_status(session_id: str, status: dict):
    job_status[session_id] = status
    if len(job_status) > 1000:
        job_status.pop(next(iter(job_status)))

def process_background_job(session_id: str, df: pl.DataFrame, temp_file_path: str, is_temp_file: bool = True):
    try:
        update_job_status(session_id, {"status": "Processing: Ingesting dataset", "progress": 10})
        
        result = process_and_detect(df=df, file_path=temp_file_path, session_id=session_id)
        
        if isinstance(result, dict) and result.get("status") == "error":
            error_msg = result.get("error") or "Detection pipeline failed with an unknown error."
            logger.error("Pipeline error for session '%s': %s", session_id, error_msg)
            update_job_status(session_id, {"status": "error", "error": error_msg})
            return

        if isinstance(result, dict) and result.get("session_id"):
            _meta_path = os.path.join(
                _session_dir(result["session_id"]), "detection_meta.json"
            )
            try:
                with open(_meta_path, "w") as _mf:
                    json.dump(
                        {
                            "drift_report": result.get("drift_report"),
                            "recommendation": result.get("recommendation"),
                            "trust_metrics": result.get("trust_metrics"),
                            "recommended_cleaning": result.get("recommended_cleaning"),
                            "cleaning_rationale": result.get("cleaning_rationale"),
                        },
                        _mf,
                        cls=NumpyEncoder
                    )
            except Exception as e:
                import traceback
                with open("DUMP_ERROR.txt", "w") as errf:
                    errf.write(traceback.format_exc())
                logger.error(f"Failed to save detection_meta: {e}")

        update_job_status(session_id, {"status": "completed", "progress": 100, "result": result})
    except Exception as e:
        logger.error(f"Background job failed: {str(e)}")
        update_job_status(session_id, {"status": "error", "error": str(e)})
    finally:
        if is_temp_file and temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/api/status/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def get_status(request: Request, session_id: str):
    if session_id not in job_status:
        try:
            validate_session_id(session_id)
            meta_path = os.path.join(_session_dir(session_id), "detection_meta.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                return {
                    "status": "completed",
                    "progress": 100,
                    "result": {
                        "recommended_cleaning": meta.get("recommended_cleaning"),
                        "cleaning_rationale": meta.get("cleaning_rationale"),
                        "recommendation": meta.get("recommendation"),
                        "drift_report": meta.get("drift_report"),
                        "trust_metrics": meta.get("trust_metrics"),
                    }
                }
        except Exception:
            pass
            
        return JSONResponse(status_code=404, content={"error": "Session/Job not found"})
    return job_status[session_id]


# ── SMART UPLOAD ENDPOINT ────────────────────────────────────────────────────
@app.post("/api/upload/", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def upload_csv(
    request: Request, 
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None)  # Intercept existing session_id from frontend
):
    # Clean up stale sessions (>24h old) in the background
    background_tasks.add_task(cleanup_stale_sessions, 24)

    os.makedirs(os.path.join(_BACKEND_DIR, "temp_uploads"), exist_ok=True)
    safe_filename = os.path.basename(file.filename or "upload.bin")
    if not safe_filename:
        safe_filename = "upload.bin"
    temp_file_path = os.path.join(_BACKEND_DIR, "temp_uploads", safe_filename)

    try:
        MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
        
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": f"File too large ({int(content_length) // (1024*1024)} MB). Maximum upload size is 500 MB."}
            )

        size = 0
        with open(temp_file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    f.close()
                    os.remove(temp_file_path)
                    return JSONResponse(
                        status_code=413,
                        content={"error": f"File too large. Maximum upload size is 500 MB."}
                    )
                f.write(chunk)

        filename_lower = safe_filename.lower()
        df = None

        if filename_lower.endswith(".parquet"):
            try:
                df = pl.read_parquet(temp_file_path)
            except Exception as e:
                return JSONResponse(status_code=400, content={"error": f"Parquet parse failed: {str(e)}"})
        elif filename_lower.endswith((".xlsx", ".xls")):
            try:
                import pandas as pd
                df = pl.from_pandas(pd.read_excel(temp_file_path, engine="openpyxl"))
            except Exception as e:
                return JSONResponse(status_code=400, content={"error": f"Excel parse failed: {str(e)}"})
        elif filename_lower.endswith(".json"):
            try:
                import pandas as pd
                with open(temp_file_path, "r") as jf:
                    raw = json.load(jf)
                if isinstance(raw, list):
                    df = pl.from_pandas(pd.DataFrame(raw))
                elif isinstance(raw, dict):
                    for key in ["data", "records", "rows", "items"]:
                        if key in raw and isinstance(raw[key], list):
                            df = pl.from_pandas(pd.DataFrame(raw[key]))
                            break
                if df is None:
                    return JSONResponse(status_code=400, content={"error": "JSON must be an array of objects or {data: [...]}."})
            except Exception as e:
                return JSONResponse(status_code=400, content={"error": f"JSON parse failed: {str(e)}"})
        else:
            try:
                df = pl.read_csv(temp_file_path, infer_schema_length=1_000_000)
            except Exception:
                try:
                    import pandas as pd
                    df = pl.from_pandas(pd.read_csv(temp_file_path, low_memory=False))
                except Exception as inner_e:
                    return JSONResponse(status_code=400, content={"error": f"Fatal read error: {str(inner_e)}"})

        validation = SchemaEnforcer.validate(df, dataset_name=file.filename)
        if not validation["valid"]:
            return JSONResponse(
                status_code=400,
                content={"status": "rejected", "errors": validation["errors"]},
            )

        # ── SMART SCHEMA VERSION CONTROL (JACCARD SIMILARITY) ────────────────
        dataset_status = "first_upload"
        active_session_id = str(uuid.uuid4())

        if session_id:
            try:
                validate_session_id(session_id)
                session_dir = _session_dir(session_id)
                metadata_path = os.path.join(session_dir, "metadata.json")
                
                if os.path.exists(metadata_path):
                    with open(metadata_path, "r") as mf:
                        old_meta = json.load(mf)
                    
                    old_cols = set(old_meta.get("columns", []))
                    new_cols = set(df.columns)
                    
                    if old_cols and new_cols:
                        intersection = len(old_cols.intersection(new_cols))
                        union = len(old_cols.union(new_cols))
                        jaccard_sim = intersection / union
                        
                        if jaccard_sim >= 0.75:
                            dataset_status = "updated"
                            active_session_id = session_id
                            logger.info(f"Smart Upload: Schema similarity {jaccard_sim:.2f}. Updating session {active_session_id}.")
                        else:
                            dataset_status = "new"
                            logger.info(f"Smart Upload: Schema similarity {jaccard_sim:.2f}. Pivot detected. Purging old session.")
                            # Wipe the old session to prevent contamination
                            shutil.rmtree(session_dir, ignore_errors=True)
                            if session_id in job_status:
                                del job_status[session_id]
                            # active_session_id remains the newly generated UUID
            except Exception as e:
                logger.warning(f"Schema comparison failed: {e}")

        # ── DISPATCH BACKGROUND JOB ──────────────────────────────────────────
        update_job_status(active_session_id, {"status": "started", "progress": 0})
        background_tasks.add_task(process_background_job, active_session_id, df, temp_file_path, True)

        return {
            "session_id": active_session_id, 
            "status": "processing", 
            "dataset_status": dataset_status
        }

    except Exception as e:
        logger.error("Upload failed: %s", e)
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── DATA RETRIEVAL & OPERATION ROUTES ────────────────────────────────────────

@app.get("/api/pii-scan/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def pii_scan(request: Request, session_id: str):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    session_dir = _session_dir(session_id)
    raw_path = f"{session_dir}/raw_data.parquet"

    if not os.path.exists(raw_path):
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    df = pl.read_parquet(raw_path)
    findings = scan_for_pii(df)
    return {"findings": findings, "pii_detected": len(findings) > 0}


@app.post("/api/pseudonymise/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("60/minute")
def pseudonymise(request: Request, session_id: str, columns: list[str]):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    session_dir = _session_dir(session_id)
    raw_path = f"{session_dir}/raw_data.parquet"

    if not os.path.exists(raw_path):
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    df = pl.read_parquet(raw_path)
    df = pseudonymise_columns(df, columns)
    df.write_parquet(raw_path)

    result = process_and_detect(df=df, session_id=session_id)

    return {
        "status": "success",
        "pseudonymised_columns": columns,
        "message": f"Salted SHA-256 pseudonymisation applied to {len(columns)} columns.",
        "detection_result": result,
    }


@app.get("/api/data/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def get_data(
    request: Request,
    session_id: str,
    is_cleaned: bool = Query(False),
    only_anomalies: bool = Query(False),
    limit: int = Query(1000),
):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    session_dir = _session_dir(session_id)
    parquet_path = f"{session_dir}/cleaned_data.parquet" if is_cleaned else f"{session_dir}/raw_data.parquet"

    if not os.path.exists(parquet_path):
        return JSONResponse(status_code=404, content={"error": "Data not found"})

    df = pl.read_parquet(parquet_path)

    total_anomalies = 0
    if "is_anomaly" in df.columns:
        anomalies = df.filter(pl.col("is_anomaly") == True)
        if "Threat_Score" in anomalies.columns:
            anomalies = anomalies.sort("Threat_Score", descending=True)

        total_anomalies = len(anomalies)
        if only_anomalies:
            df = anomalies

    total_rows = len(df)
    if total_rows > limit:
        df = df.head(limit)

    detection_meta = {}
    meta_path = os.path.join(session_dir, "detection_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as mf:
                detection_meta = json.load(mf)
        except Exception:
            pass

    return {
        "data": df.to_dicts(),
        "total_anomalies": total_anomalies,
        "total_rows": total_rows,
        "drift_report": detection_meta.get("drift_report"),
        "recommendation": detection_meta.get("recommendation"),
    }


@app.post("/api/clean/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def clean_data(request: Request, session_id: str, action: str = Query("quarantine")):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    result = clean_dataset(session_id, action)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/api/compare/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def compare_data(request: Request, session_id: str):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    session_dir = _session_dir(session_id)
    raw_path = f"{session_dir}/raw_data.parquet"
    clean_path = f"{session_dir}/cleaned_data.parquet"

    if not os.path.exists(clean_path):
        return JSONResponse(status_code=400, content={"error": "No cleaned data found."})
    if not os.path.exists(raw_path):
        return JSONResponse(status_code=400, content={"error": "Raw dataset not found. Session may be corrupted."})

    df_raw = pl.read_parquet(raw_path)
    df_clean = pl.read_parquet(clean_path)

    is_dropped = len(df_clean) < len(df_raw)

    internal_cols = {"is_anomaly", "Threat_Score", "AI_Reason"}
    engineered_suffixes = ("_freq", "_length", "_digit_ratio", "_upper_ratio", "_special_ratio")
    engineered_prefixes = ("nlp_pc",)
    velocity_names = {"velocity_24h_sum", "velocity_1h_count"}

    cols_to_drop = [
        c for c in df_raw.columns
        if c in internal_cols
        or c.endswith(engineered_suffixes)
        or any(c.startswith(p) for p in engineered_prefixes)
        or c in velocity_names
    ]
    df_raw_clean_view = df_raw.drop([c for c in cols_to_drop if c in df_raw.columns])

    if is_dropped:
        return {
            "is_dropped": True,
            "original": [],
            "cleaned": [],
            "count": len(df_raw) - len(df_clean),
        }

    compare_cols = [c for c in df_clean.columns if c in df_raw_clean_view.columns]
    
    changed_mask = pl.lit(False)
    for col in compare_cols:
        diff = (df_raw_clean_view[col] != df_clean[col]).fill_null(False)
        null_diff = (df_raw_clean_view[col].is_null() != df_clean[col].is_null())
        changed_mask = changed_mask | diff | null_diff
        
    original_changed = df_raw_clean_view.filter(changed_mask)
    cleaned_changed = df_clean.filter(changed_mask)

    return {
        "is_dropped": False,
        "original": original_changed.head(50).to_dicts(),
        "cleaned": cleaned_changed.head(50).to_dicts(),
        "count": len(original_changed),
    }


@app.get("/api/viz/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def viz_data(request: Request, session_id: str):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    result = get_viz_data(session_id)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/api/insights/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
def insights(request: Request, session_id: str):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    result = generate_insights(session_id)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/api/report/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
def report(request: Request, session_id: str):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    result = generate_quality_report(session_id)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result

@app.get("/api/report/download/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
def download_report_pdf(request: Request, session_id: str):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    result = generate_quality_report(session_id)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
        
    try:
        from reportlab.pdfgen import canvas
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer)
        c.drawString(100, 800, "DataSentinel Quality Report")
        c.drawString(100, 780, f"Session ID: {session_id}")
        
        y = 750
        for key, value in result.items():
            if y < 100:
                c.showPage()
                y = 800
            if isinstance(value, dict):
                c.drawString(100, y, f"{key}:")
                y -= 20
                for k, v in value.items():
                    c.drawString(120, y, f"{str(k)}: {str(v)}")
                    y -= 20
            else:
                c.drawString(100, y, f"{str(key)}: {str(value)}")
            y -= 20
            
        c.save()
        buffer.seek(0)
        return StreamingResponse(
            buffer, 
            media_type="application/pdf", 
            headers={"Content-Disposition": f'attachment; filename="quality_report.pdf"'}
        )
    except ImportError:
        return JSONResponse(status_code=500, content={"error": "reportlab not installed."})
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to generate PDF."})


@app.get("/api/download/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def download_data(request: Request, session_id: str, source: str = Query("cleaned")):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    session_dir = _session_dir(session_id)

    if source == "quarantine":
        parquet_path = f"{session_dir}/quarantined_data.parquet"
        csv_filename = "quarantined_data.csv"
    else:
        parquet_path = f"{session_dir}/cleaned_data.parquet"
        csv_filename = "cleaned_data.csv"

    if not os.path.exists(parquet_path):
        return JSONResponse(status_code=404, content={"error": f"No {source} data found."})

    df = pl.read_parquet(parquet_path)

    internal_cols_set = {
        "is_anomaly", "Threat_Score", "AI_Reason", "SHAP_Payload", 
        "Counterfactual_Payload", "lof_score", "lstm_anomaly_score", "ecod_score",
        "Uncertainty_Score", "Consensus_Verdict"
    }
    engineered_suffixes = ("_freq", "_length", "_digit_ratio", "_upper_ratio", "_special_ratio")
    engineered_prefixes = ("nlp_pc",)
    velocity_names = {"velocity_24h_sum", "velocity_1h_count"}
    
    cols_to_drop = [
        c for c in df.columns
        if c in internal_cols_set
        or c.startswith("Score_CI")  
        or c.endswith(engineered_suffixes)
        or any(c.startswith(p) for p in engineered_prefixes)
        or c in velocity_names
    ]
    if cols_to_drop:
        df = df.drop([c for c in cols_to_drop if c in df.columns])

    buffer = io.BytesIO()
    df.write_csv(buffer)
    buffer.seek(0) 

    return StreamingResponse(
        buffer, 
        media_type="text/csv", 
        headers={"Content-Disposition": f'attachment; filename="{csv_filename}"'}
    )


@app.get("/api/quarantine/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
def get_quarantine(request: Request, session_id: str, limit: int = Query(1000)):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    session_dir = _session_dir(session_id)
    quarantine_path = f"{session_dir}/quarantined_data.parquet"

    if not os.path.exists(quarantine_path):
        return {"data": [], "count": 0}

    df = pl.read_parquet(quarantine_path)
    total_count = len(df)

    if total_count > limit:
        df = df.head(limit)

    return {"data": df.to_dicts(), "count": total_count}


@app.post("/api/query/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
async def query_data(
    request: Request,
    session_id: str,
    user_query: str = Query(...),
    mode: str = Query("explore"),
):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    is_edit = mode == "edit"
    return StreamingResponse(
        execute_natural_query_stream(session_id, user_query, is_edit=is_edit),
        media_type="text/event-stream"
    )

@app.post("/api/confirm-edit/{session_id}", dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
def confirm_edit(request: Request, session_id: str, sql_query: str = Query(...)):
    try:
        validate_session_id(session_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid session ID"})

    result = confirm_and_execute_edit(session_id, sql_query)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/api/samples")  
@limiter.limit("120/minute")
def list_samples(request: Request):
    data_dir = os.path.join(_BACKEND_DIR, "data")
    samples = []
    descriptions = {
        "fraud_transactions.csv": {
            "name": "Financial Fraud Transactions",
            "rows": 500,
            "anomalies": 25,
            "description": "Synthetic bank transactions with offshore fraud patterns.",
            "icon": "💳",
        },
        "patient_vitals.csv": {
            "name": "Patient Vitals Monitor",
            "rows": 300,
            "anomalies": 15,
            "description": "ICU sensor readings with equipment glitch anomalies.",
            "icon": "🏥",
        },
        "ecommerce_reviews.csv": {
            "name": "E-Commerce Reviews",
            "rows": 400,
            "anomalies": 20,
            "description": "Product reviews with bot-generated spam injected.",
            "icon": "🛒",
        },
    }
    for fname, meta in descriptions.items():
        fpath = os.path.join(data_dir, fname)
        if os.path.exists(fpath):
            samples.append({**meta, "filename": fname})
    return {"samples": samples}


@app.post("/api/load-sample/{filename}", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def load_sample(request: Request, filename: str, background_tasks: BackgroundTasks):
    allowed = {"fraud_transactions.csv", "patient_vitals.csv", "ecommerce_reviews.csv"}
    if filename not in allowed:
        return JSONResponse(status_code=400, content={"error": "Unknown sample file."})

    data_dir = os.path.join(_BACKEND_DIR, "data")
    file_path = os.path.join(data_dir, filename)

    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "Sample not found."})

    try:
        df = pl.read_csv(file_path, infer_schema_length=1_000_000)
        validation = SchemaEnforcer.validate(df, dataset_name=filename)
        if not validation["valid"]:
            return JSONResponse(
                status_code=400, content={"errors": validation["errors"]}
            )
        session_id = str(uuid.uuid4())
        update_job_status(session_id, {"status": "started", "progress": 0})
        
        background_tasks.add_task(process_background_job, session_id, df, file_path, False)
        
        return {"session_id": session_id, "status": "processing", "dataset_status": "first_upload"}
    except Exception as e:
        logger.error("Sample load failed: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})