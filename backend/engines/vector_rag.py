"""
DataSentinel — Vector RAG Engine (Planner Muscle Memory)
Uses ChromaDB and sentence-transformers to build a persistent Knowledge Graph
of historically approved SQL fixes.

PERFORMANCE: The SentenceTransformer model and ChromaDB collection are
loaded ONCE at module level via a threading lock, eliminating the ~35s
HuggingFace download on every remediation call.
"""

import os
import threading
from datetime import datetime, timezone
import chromadb
from chromadb.utils import embedding_functions

from utils import logger, _BACKEND_DIR

# Suppress HuggingFace symlink warnings on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_COLLECTION_NAME = "ds_fix_kb"
_KB_PATH = os.path.join(_BACKEND_DIR, "data", "vector_kb")

# ── Thread-safe singleton for model + collection ─────────────────────────────
_init_lock = threading.Lock()
_collection = None
_initialized = False


def _get_or_create_collection():
    """Thread-safe lazy singleton. Loads model + ChromaDB exactly once."""
    global _collection, _initialized
    if _initialized:
        return _collection

    with _init_lock:
        # Double-check inside the lock
        if _initialized:
            return _collection

        os.makedirs(_KB_PATH, exist_ok=True)

        logger.info("RAG: Loading SentenceTransformer model (one-time)...")
        sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        client = chromadb.PersistentClient(path=_KB_PATH)
        _collection = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=sentence_transformer_ef,
        )
        _initialized = True
        logger.info("RAG: Knowledge base ready (%d fixes stored).", _collection.count())
        return _collection


def upsert_approved_fix(sql: str, diagnostic_context: str, schema: str, session_id: str):
    """
    Embeds and stores an approved SQL fix into the Vector KB.
    """
    try:
        col = _get_or_create_collection()
        doc_id = f"fix_{session_id}_{int(datetime.now(timezone.utc).timestamp())}"

        document_text = f"Diagnostic: {diagnostic_context}\nSchema: {schema}"

        col.add(
            ids=[doc_id],
            documents=[document_text],
            metadatas=[{
                "sql": sql,
                "diagnostic_context": diagnostic_context,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        )
        logger.info("Upserted fix to RAG KB: %s", doc_id)
    except Exception as e:
        logger.error("RAG upsert failed: %s", e)


def get_rag_stats() -> dict:
    """Returns statistics about the Vector KB."""
    try:
        col = _get_or_create_collection()
        return {
            "total_fixes": col.count(),
            "collections": [_COLLECTION_NAME],
        }
    except Exception as e:
        logger.error("Failed to get RAG stats: %s", e)
        return {"total_fixes": 0, "collections": []}
