<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/Polars-1.27-CD792C?style=flat-square" />
  <img src="https://img.shields.io/badge/DuckDB-1.2-FFF000?style=flat-square&logo=duckdb&logoColor=black" />
  <img src="https://img.shields.io/badge/Groq_Cloud-LPU_Inference-FF6B35?style=flat-square" />
  <img src="https://img.shields.io/badge/License-Portfolio-8B5CF6?style=flat-square" />
</p>

# DataSentinel

**AI-powered data quality and anomaly detection platform.**

Upload any CSV, JSON, or Excel file. DataSentinel runs anomaly detection, explains what it found, cleans your data, and lets you query it in plain English — all in one pipeline.

---

## What It Does

| Stage | Description |
|---|---|
| **Upload** | Accepts CSV, JSON, Excel. Validates schema contracts. Stores as Parquet. |
| **PII Scan** | Detects emails, phones, SSNs via regex + heuristics. SHA-256 pseudonymisation on request. |
| **Anomaly Detection** | Isolation Forest + LSTM Autoencoder + ECOD + LOF run in parallel. Ensemble voted. |
| **Explainability** | SHAP per-row feature attribution. NOTEARS causal DAG for root cause. DiCE counterfactuals. |
| **AI Insights** | Statistical profiling (nulls, skew, correlations) + Groq LLM narrative summary. |
| **Smart Cleaning** | Drop, quarantine, winsorize, mask, or KNN-impute. RL agent selects optimal strategy. |
| **Compare** | Side-by-side before/after diff of raw vs cleaned data. |
| **NL Query** | Type a question → Groq generates DuckDB SQL → executes → streams result via SSE. Self-heals on error. |
| **Visualize** | Histograms, correlation heatmaps, scatter plots via Recharts. |
| **Export** | Quality scorecard with health score + downloadable cleaned CSV. |

---

## Tech Stack

### Backend

| Package | Version | Role |
|---|---|---|
| FastAPI | 0.115 | Async REST API + SSE streaming |
| Polars | 1.27 | Primary DataFrame engine |
| Pandas | 2.2 | Excel parsing + compatibility |
| PyArrow | 26+ | Polars ↔ Pandas conversion |
| scikit-learn | 1.6 | Isolation Forest, LOF, KNN imputer |
| SHAP | 0.46 | Per-row explainability |
| XGBoost | 3.2 | Threat scorer (hist booster) |
| DuckDB | 1.2 | In-process analytical SQL |
| PyOD | 3.2 | ECOD anomaly detection |
| SciPy | ≥1.14 | KS-test drift detection |
| DiCE-ML | 0.12 | Counterfactual recommendations |
| PyTorch | 2.5 | LSTM Autoencoder |
| Sentence-Transformers | ≥3.0 | Embedding for RAG vector store |
| ChromaDB | ≥0.5 | Vector store backend |
| SlowAPI | 0.1.9 | Rate limiting |
| ReportLab | 4.3 | PDF quality report export |
| Uvicorn | 0.34 | ASGI server |

### Frontend

| Package | Version | Role |
|---|---|---|
| Next.js | 16 | React framework, App Router |
| React | 19 | UI |
| TypeScript | 5 | Strict typing, zero `any` |
| Tailwind CSS | 4 | Styling |
| Framer Motion | 12 | Page transitions & micro-animations |
| Three.js | 0.183 | 3D particle scenes on landing page |
| @react-three/fiber | 9.6 | React renderer for Three.js |
| GSAP | 3.15 | Scroll-driven animations |
| Lenis | 1.3 | Smooth scroll |
| Recharts | 3.8 | Charts & visualizations |
| Axios | 1.14 | HTTP client with auth interceptor |

### External Services

| Service | Purpose |
|---|---|
| **Groq Cloud** | LPU inference — SQL generation, insight narratives, logic rule synthesis |
| **PostgreSQL** *(optional)* | Live DB connect for real-time querying without data movement |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- A free [Groq API key](https://console.groq.com)

### 1. Clone

```bash
git clone https://github.com/NishigandhaSawant/DataSentinel-2026.git
cd DataSentinel-2026
```

### 2. Backend

```bash
cd backend

python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Create `backend/.env`:

```env
GROQ_API_KEY=gsk_your_key_here

# Optional — override active Groq models
GROQ_MODEL_FAST=qwen/qwen3.8-27b
GROQ_MODEL_REASONING=openai/gpt-oss-120b

# Optional — API key auth guard (leave blank for local dev)
# DS_API_KEY=your_secret_key

# Optional — custom PII hashing salt
# DS_PII_SALT=your_custom_salt
```

```bash
uvicorn main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger)
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

---

## Project Structure

```
DataSentinel/
├── backend/
│   ├── main.py                  # FastAPI app & all route definitions
│   ├── groq_client.py           # Groq LLM client — retry & model fallback logic
│   ├── auth.py                  # Optional API key auth guard
│   ├── schema.py                # Data contract validation (SchemaEnforcer)
│   ├── utils.py                 # Session management, logging, audit trail
│   ├── engines/
│   │   ├── detection.py         # Isolation Forest + LSTM anomaly detection pipeline
│   │   ├── neuro_symbolic.py    # Logical Neural Network (LNN) constraints
│   │   ├── logic_gate.py        # AI-generated neuro-symbolic validation rules
│   │   ├── insights.py          # Statistical profiling + LLM narrative generation
│   │   ├── cleaning.py          # Drop / quarantine / winsorize / mask / impute
│   │   ├── rl_cleaner.py        # Q-Learning agent — selects optimal cleaning strategy
│   │   ├── active_learning.py   # Uncertainty sampling + human trust score
│   │   ├── causal_rca.py        # NOTEARS continuous DAG — root cause analysis
│   │   ├── pii_scanner.py       # PII detection & SHA-256 pseudonymisation
│   │   ├── query.py             # NL → SQL via Groq + DuckDB + self-healing retry
│   │   ├── vector_rag.py        # TF-IDF + SVD vector store for business dictionary
│   │   ├── nlp_bridge.py        # NLP feature engineering (TF-IDF + SVD)
│   │   ├── lineage_gae.py       # Graph AutoEncoder for schema drift detection
│   │   ├── visualization.py     # Chart data aggregation
│   │   └── quality.py           # Data quality report & health score
│   ├── data/                    # Built-in sample datasets
│   ├── tests/                   # Pytest unit & integration tests
│   ├── requirements.txt
│   └── .env
│
└── frontend/
    └── src/
        ├── app/
        │   ├── page.tsx                    # Landing page
        │   └── [sessionId]/               # Dynamic session routing
        │       ├── SessionProvider.tsx     # Client-side session state
        │       ├── layout.tsx             # Session nav bar
        │       ├── upload/page.tsx
        │       ├── detect/page.tsx
        │       ├── insights/page.tsx
        │       ├── clean/page.tsx
        │       ├── compare/page.tsx
        │       ├── edit/page.tsx
        │       ├── visualize/page.tsx
        │       ├── query/page.tsx
        │       └── report/page.tsx
        ├── components/                    # Per-page UI components
        ├── hooks/                         # Data fetching hooks
        ├── services/api.service.ts        # Axios instance + auth interceptor
        ├── types/api.ts                   # Shared TypeScript interfaces
        └── constants/config.ts            # API URL config
```

---

## API Reference

All endpoints at `http://localhost:8000`. Full docs at `/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/api/health` | Groq connectivity check |
| `POST` | `/api/upload/` | Upload dataset (CSV/JSON/Excel/Parquet) |
| `GET` | `/api/status/{session_id}` | Polling status of background processing |
| `GET` | `/api/data/{session_id}` | Fetch rows (filter: `is_cleaned`, `only_anomalies`) |
| `GET` | `/api/insights/{session_id}` | Statistical profile + AI narrative |
| `POST` | `/api/clean/{session_id}` | Clean anomalies (`drop`/`quarantine`/`winsorize`/`mask`/`impute`) |
| `GET` | `/api/compare/{session_id}` | Raw vs cleaned comparison |
| `GET` | `/api/viz/{session_id}` | Chart aggregations |
| `GET` | `/api/report/{session_id}` | Quality scorecard + health score |
| `GET` | `/api/download/{session_id}` | Download cleaned CSV |
| `POST` | `/api/query/{session_id}` | NL query — SSE stream (`explore` / `edit` mode) |
| `POST` | `/api/confirm-edit/{session_id}` | Execute confirmed SQL mutation |
| `GET` | `/api/pii-scan/{session_id}` | Scan for PII |
| `POST` | `/api/pseudonymise/{session_id}` | SHA-256 pseudonymise PII columns |
| `POST` | `/api/feedback/` | Human feedback on anomaly classifications |
| `POST` | `/api/knowledge/learn` | Teach AI a business term |
| `GET` | `/api/samples` | List built-in sample datasets |
| `POST` | `/api/load-sample/{filename}` | Load a sample through the full pipeline |
| `POST` | `/api/connect-db/{session_id}` | Connect live PostgreSQL DB |
| `GET` | `/api/admin/audit-logs` | Fetch immutable audit trail |

---

## Environment Variables

### `backend/.env`

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ | — | Groq Cloud API key |
| `GROQ_MODEL_FAST` | No | `qwen/qwen3.8-27b` | Model for fast/JSON tasks |
| `GROQ_MODEL_REASONING` | No | `openai/gpt-oss-120b` | Model for SQL & reasoning |
| `DS_API_KEY` | No | — | Enables API key auth guard |
| `DS_PII_SALT` | No | Built-in | Salt for SHA-256 PII hashing |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated CORS whitelist |

### `frontend/.env.local`

| Variable | Required | Default | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | No | `http://127.0.0.1:8000` | Backend API base URL |
| `NEXT_PUBLIC_API_KEY` | No | — | Must match `DS_API_KEY` if auth is on |

---

## Running Tests

```bash
# Backend
cd backend
venv\Scripts\activate
pytest -v

# Frontend — TypeScript check
cd frontend
npx tsc --noEmit
```

---

## Security

- **PII** is scanned locally before any data is sent to an LLM
- **SQL mutations** require explicit user confirmation before execution
- **File uploads** are capped at 50MB with extension + MIME validation
- **DuckDB explore** mode is read-only; mutations are whitelist-validated
- **Audit trail** — every AI-driven data change is logged to an immutable JSONL file
- **CORS** is restricted to configured origins
- **Rate limiting** via SlowAPI on all endpoints

---

## License

Portfolio / educational use.

---

Built with FastAPI · Next.js · Groq · Polars · DuckDB