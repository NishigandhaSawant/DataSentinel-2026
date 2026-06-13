# DataSentinel — AI Context File

> **Read this first.** This file provides a compact overview of the project so you don't need to read every file.

## What is this?

AI-powered data quality & anomaly detection platform. Upload a dataset → detect anomalies → get AI insights → clean data → query with natural language.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI 0.115, Polars, DuckDB, scikit-learn, SHAP, Groq (Llama 3.3 70B)
- **Frontend:** Next.js 16, React 19, TypeScript, Three.js, GSAP, Tailwind CSS 4, Recharts

## Key Files to Focus On

### Backend (Python)
- `backend/main.py` — All FastAPI routes (41KB, largest file)
- `backend/engines/detection.py` — Core anomaly detection (IF + LSTM + SHAP)
- `backend/engines/query.py` — NL → SQL via Groq + DuckDB
- `backend/engines/cleaning.py` — Multi-strategy data cleaning
- `backend/engines/insights.py` — Statistical profiling + LLM narratives
- `backend/engines/logic_gate.py` — Neuro-symbolic rule generation
- `backend/schema.py` — Data contract validation
- `backend/groq_client.py` — Groq LLM client
- `backend/utils.py` — Session management utilities

### Frontend (TypeScript/React)
- `frontend/src/app/page.tsx` — Landing page
- `frontend/src/app/[sessionId]/` — Dynamic session routes
- `frontend/src/components/` — All UI components
- `frontend/src/services/api.service.ts` — API client
- `frontend/src/types/api.ts` — TypeScript interfaces

## Files You Can Skip
- `package-lock.json` — Auto-generated, no value
- `*.png`, `*.ico` — Binary assets
- `public/DataSentinel_Project_Brief.md` — Redundant with README
- `backend/tests/` — Standard pytest test files (read only if asked about tests)

## Architecture (5 Layers)
1. **Presentation** — Next.js 16 + React 19 (Three.js 3D scenes)
2. **API Gateway** — FastAPI (rate limiting, auth, CORS, session management)
3. **AI Engine Core** — 5 parallel anomaly models + ensemble voting + XGBoost threat scoring
4. **Data Layer** — Polars DataFrames, Parquet session storage, JSONL audit trail
5. **External** — Groq Cloud LPU, optional PostgreSQL
