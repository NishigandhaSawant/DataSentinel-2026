# DataSentinel — Complete Project Knowledge Base

> **AI INSTRUCTION:** Read this file FIRST. It contains everything you need to understand this project
> without reading every source file. Only dive into specific files when you need implementation details.

---

## 1. What is DataSentinel?

DataSentinel is an AI-powered, autonomous data quality & anomaly detection platform. Users upload a dataset (CSV/JSON/Excel/Parquet) and the system:

1. **Scans for PII** (emails, phones, SSNs) → optional SHA-256 pseudonymisation
2. **Detects anomalies** using 5 parallel ML models with ensemble voting
3. **Explains why** each anomaly was flagged (SHAP, causal DAG, counterfactuals)
4. **Generates AI insights** with statistical profiling + LLM narratives
5. **Cleans data** using multi-strategy engine (drop/quarantine/winsorize/mask/impute)
6. **Queries data** via natural language → SQL (Groq LLM + DuckDB)
7. **Exports** quality reports and cleaned datasets

---

## 2. Tech Stack

### Backend (Python 3.11+)
| Package | Version | Purpose |
|---------|---------|---------|
| FastAPI | 0.115 | Async REST API with auto OpenAPI docs |
| Polars | 1.27 | High-perf DataFrame engine (Rust-based, 10-100x faster than Pandas) |
| scikit-learn | 1.6 | Isolation Forest, LOF, KNNImputer |
| SHAP | 0.46 | Per-row feature attribution explainability |
| DuckDB | 1.2 | In-process SQL engine for NL queries |
| Groq SDK | latest | LLM inference (Llama 3.3 70B on Groq LPU hardware) |
| XGBoost | — | Threat scoring with hist booster |
| SlowAPI | 0.1.9 | Rate limiting middleware |
| Pandas | 2.2 | Excel parsing & compatibility layer |

### Frontend (TypeScript)
| Package | Version | Purpose |
|---------|---------|---------|
| Next.js | 16 | React framework with App Router & SSR |
| React | 19 | UI component library |
| Three.js | 0.183 | 3D particle visualizations |
| @react-three/fiber | 9.6 | React renderer for Three.js |
| GSAP | 3.15 | Scroll-driven cinematic animations |
| Lenis | 1.3 | Butter-smooth scroll engine |
| Framer Motion | 12 | Page transitions & micro-animations |
| Recharts | 3.8 | Data visualization charts |
| Tailwind CSS | 4 | Utility-first CSS framework |
| Axios | 1.14 | HTTP client with interceptors |

---

## 3. Architecture (5 Layers)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: PRESENTATION — Next.js 16 + React 19             │
│  3D Landing (Three.js+GSAP) → Upload → PII Modal →         │
│  Detection Dashboard → AI Insights → Smart Cleaning →      │
│  Compare View → Visualizer (Recharts) → NL Query (SSE) →   │
│  Export & Report                                            │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2: API GATEWAY — FastAPI 0.115                       │
│  Rate Limiter (SlowAPI) | Auth Guard (API Key) |            │
│  CORS Middleware | Session Manager (UUID) | Background Tasks│
├─────────────────────────────────────────────────────────────┤
│  LAYER 3: MULTI-AGENT AI ENGINE CORE                        │
│  Anomaly Detection: IF + LOF + ECOD + LNN + LSTM            │
│  Reasoning: NOTEARS DAG + XGBoost + DiCE + Neuro-Symbolic   │
│  Intelligence: NLP Bridge + RL Cleaner + Active Learning    │
│  Services: PII Scanner + DuckDB Query + Viz + Quality       │
├─────────────────────────────────────────────────────────────┤
│  LAYER 4: DATA & STORAGE                                    │
│  Polars DataFrames | Parquet Sessions | JSONL Audit Trail |  │
│  Business Dictionary (RAG) | Model Cache (Joblib)           │
├─────────────────────────────────────────────────────────────┤
│  LAYER 5: EXTERNAL SERVICES                                 │
│  Groq Cloud LPU (Llama 3.3 70B) | PostgreSQL (Live DB)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Data Pipeline Flow

```
UPLOAD → PII VAULT → ANOMALY DETECTION → AI INSIGHTS → SMART CLEANING → QUERY & EXPLORE → EXPORT
```

| Stage | Engine | What Happens |
|-------|--------|--------------|
| 1. Upload | `main.py` + `schema.py` | File parsed → Schema validation → Parquet storage |
| 2. PII Vault | `pii_scanner.py` | Regex + heuristic scan → Optional SHA-256 pseudonymisation |
| 3. Detection | `detection.py` + `logic_gate.py` + `nlp_bridge.py` | NLP features → Neuro-symbolic rules → 5 parallel models → SHAP → Threat scoring |
| 4. AI Insights | `insights.py` + `groq_client.py` | Statistical profiling → Groq LLM narrative generation |
| 5. Cleaning | `cleaning.py` | Drop/quarantine/winsorize/mask/KNN-impute → Save cleaned Parquet |
| 6. Query | `query.py` + DuckDB | NL → Groq generates SQL → DuckDB executes → Auto-correction (3 retries) |
| 7. Export | `quality.py` + `visualization.py` | Quality report → Chart aggregation → CSV download |

---

## 5. AI Engine Deep Dive

### 5.1 Anomaly Detection (5 Parallel Models)
All run via `ThreadPoolExecutor` and ensemble-vote:

| Model | How It Works |
|-------|-------------|
| **Isolation Forest** | Randomly partitions feature space; anomalies need fewer splits → low path-length score |
| **LSTM Autoencoder** | Learns normal sequential patterns; high reconstruction error = anomaly |
| **ECOD** | Empirical Cumulative Distribution — no distribution assumptions, robust to skew |
| **LOF** | Local Outlier Factor — compares point's local density to neighbors |
| **LNN** | Logical Neural Network enforcing domain constraints as soft logic gates |

Results → **XGBoost** (hist booster) → normalized threat score (0.0–1.0)

### 5.2 Explainability & Causal Reasoning
| Component | How It Works |
|-----------|-------------|
| **SHAP** | TreeExplainer — per-row, per-feature attribution values |
| **NOTEARS DAG** | Continuous DAG optimization — discovers causal column relationships |
| **DiCE** | Counterfactual examples: "If age were 34 instead of 134, this row would be normal" |

### 5.3 Adaptive Intelligence
| Component | How It Works |
|-----------|-------------|
| **RL Cleaner** (`rl_cleaner.py`) | Q-Learning agent selects optimal cleaning action per anomaly type |
| **Active Learning** (`active_learning.py`) | Uncertainty sampling for human review; feedback updates trust score |
| **Lineage GAE** (`lineage_gae.py`) | Graph AutoEncoder — drift in embeddings signals schema/distribution shift |
| **Neuro-Symbolic** (`logic_gate.py`) | Groq LLM generates Polars validation expressions from schema + samples |

### 5.4 Agentic Query Engine
| Component | How It Works |
|-----------|-------------|
| **NL → SQL** | User question + RAG context → Groq generates DuckDB SQL |
| **Self-Healing** | SQL error → sent back to Groq for correction (up to 3 retries) |
| **Vector RAG** (`vector_rag.py`) | TF-IDF + SVD vectorizes business dictionary; cosine similarity retrieval |
| **SSE Streaming** | Results stream token-by-token via Server-Sent Events |

---

## 6. Complete File Map

### Backend — `backend/`
| File | Size | Purpose |
|------|------|---------|
| `main.py` | 41KB | **All FastAPI routes** — upload, detect, clean, query, insights, export, PII, feedback, admin |
| `engines/detection.py` | 84KB | **Core detection** — IF + LSTM + SHAP + XGBoost + DiCE + ensemble pipeline |
| `engines/cleaning.py` | 18KB | Multi-strategy cleaning — drop, quarantine, winsorize, mask, KNN-impute |
| `engines/insights.py` | 19KB | Statistical profiling + Groq LLM narrative generation (OIA framework) |
| `engines/query.py` | — | NL → SQL translation via Groq + DuckDB execution + self-healing |
| `engines/logic_gate.py` | 7KB | Neuro-symbolic rule generation — Groq generates Polars validation expressions |
| `engines/lineage_gae.py` | 8KB | Graph AutoEncoder for column-relationship drift detection |
| `engines/causal_rca.py` | 6KB | NOTEARS continuous DAG discovery for root cause analysis |
| `engines/neuro_symbolic.py` | 5KB | Logical Neural Network constraints |
| `engines/active_learning.py` | 5KB | Uncertainty sampling + human trust calibration |
| `engines/rl_cleaner.py` | — | Q-Learning agent for optimal imputation strategy |
| `engines/vector_rag.py` | — | TF-IDF + SVD vector store for RAG business dictionary |
| `engines/nlp_bridge.py` | 3KB | NLP feature engineering (TF-IDF + SVD) for text columns |
| `engines/pii_scanner.py` | — | PII detection (regex + heuristic) & SHA-256 pseudonymisation |
| `engines/visualization.py` | — | Chart data aggregation (histograms, correlations, categorical) |
| `engines/quality.py` | — | Data quality report & health score generation |
| `schema.py` | 3KB | SchemaEnforcer — data contract validation |
| `groq_client.py` | 4KB | Centralized Groq LLM client with retry logic |
| `auth.py` | 2KB | API key authentication guard (constant-time comparison) |
| `utils.py` | 3KB | Session management, logging, audit trail utilities |

### Frontend — `frontend/src/`
| File | Purpose |
|------|---------|
| `app/page.tsx` | Landing page with 3D scenes |
| `app/layout.tsx` | Root layout with SmoothScroller |
| `app/globals.css` | Global styles & Tailwind config |
| `app/[sessionId]/layout.tsx` | Session layout (nav bar) |
| `app/[sessionId]/SessionProvider.tsx` | Client-side state manager |
| `app/[sessionId]/upload/page.tsx` | File upload & schema validation |
| `app/[sessionId]/detect/page.tsx` | Detection results & RCA dashboard |
| `app/[sessionId]/insights/page.tsx` | Statistical & AI narratives |
| `app/[sessionId]/clean/page.tsx` | Multi-strategy data cleaning |
| `app/[sessionId]/compare/page.tsx` | Before/After data comparison |
| `app/[sessionId]/edit/page.tsx` | Inline data review & edit |
| `app/[sessionId]/visualize/page.tsx` | Analytics charts |
| `app/[sessionId]/query/page.tsx` | Natural language chat (SSE) |
| `app/[sessionId]/report/page.tsx` | Health scorecard & export |
| `components/landing/HeroLanding.tsx` | GSAP scroll-driven cinematic intro |
| `components/landing/PurificationCore.tsx` | Three.js data purification particles |
| `components/landing/NeuralCore.tsx` | Three.js neural network background |
| `components/landing/AmbientAurora.tsx` | CSS ambient aurora backdrop |
| `components/detection/Detection.tsx` | Anomaly results with SHAP visualizations |
| `components/insights/Insights.tsx` | AI-generated insights dashboard (37KB) |
| `components/query/Query.tsx` | NL query chat interface (33KB) |
| `components/clean/Clean.tsx` | Cleaning action panel |
| `components/compare/Compare.tsx` | Before/after dataset diff |
| `components/review-edit/ReviewEdit.tsx` | Data review & inline edit |
| `components/visualizer/Visualizer.tsx` | Charts (histograms, heatmaps) |
| `components/visualizer/VisualizerScatterPlot.tsx` | Scatter plots |
| `components/export-report/ExportReport.tsx` | Quality report export |
| `components/pii-modal/PIIModal.tsx` | PII detection & pseudonymisation modal |
| `components/ResetConfirmModal.tsx` | Session reset dialog |
| `components/SmoothScroller.tsx` | Lenis smooth scroll wrapper |
| `services/api.service.ts` | Axios instance with auth interceptor |
| `types/api.ts` | All TypeScript interfaces (zero `any` types) |
| `hooks/use-detection.ts` | Anomaly data fetching & feedback state |
| `hooks/use-compare.ts` | Before/after comparison data |
| `hooks/use-viz.ts` | Visualization data & tab state |
| `constants/config.ts` | API base URL & key configuration |

### Root Files
| File | Purpose |
|------|---------|
| `README.md` | 680-line comprehensive documentation |
| `CLAUDE.md` | This file — AI knowledge base |
| `.env.example` | Environment variable template |
| `.gitignore` | Git ignore rules |
| `.gitattributes` | GitHub zip export config |
| `docker-compose.yml` | Container orchestration |
| `export-for-ai.ps1` | Script to generate this bundle |
| `public/DataSentinel_Project_Brief.md` | 601-line academic project brief |
| `public/architecture.png` | System architecture diagram |

---

## 7. API Reference

All endpoints at `http://localhost:8000`. Swagger docs at `/docs`.

### Core Pipeline
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/api/health` | Groq API connectivity check |
| `POST` | `/api/upload/` | Upload dataset (CSV/JSON/Excel/Parquet) with schema validation |
| `GET` | `/api/data/{session_id}` | Fetch rows (filters: `is_cleaned`, `only_anomalies`) |
| `POST` | `/api/clean/{session_id}` | Clean anomalies — drop/quarantine/winsorize/mask/impute |
| `GET` | `/api/compare/{session_id}` | Raw vs cleaned data diff |
| `GET` | `/api/viz/{session_id}` | Visualization aggregations |
| `GET` | `/api/insights/{session_id}` | AI insights with LLM narratives |
| `GET` | `/api/report/{session_id}` | Quality report with health score |
| `GET` | `/api/download/{session_id}` | Download cleaned CSV |

### Query System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/query/{session_id}` | NL query — streams via SSE (modes: explore/edit) |
| `POST` | `/api/confirm-edit/{session_id}` | Execute confirmed SQL mutation with audit |

### Privacy & Security
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/pii-scan/{session_id}` | Scan for PII (emails, phones, SSNs) |
| `POST` | `/api/pseudonymise/{session_id}` | SHA-256 pseudonymise PII columns |
| `GET` | `/api/quarantine/{session_id}` | View quarantined rows |
| `POST` | `/api/feedback/` | Submit human feedback on anomalies |

### Knowledge & Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/knowledge/learn` | Teach AI a business term |
| `POST` | `/api/connect-db/{session_id}` | Connect live PostgreSQL |
| `GET` | `/api/admin/audit-logs` | Immutable audit trail |
| `GET` | `/api/samples` | List sample datasets |
| `POST` | `/api/load-sample/{filename}` | Load sample through pipeline |

---

## 8. Security Model

| Layer | Implementation |
|-------|---------------|
| API Auth | Optional API key with constant-time comparison (`DS_API_KEY`) |
| PII Protection | Local-edge scanning — PII detected before data reaches LLM |
| Pseudonymisation | Salted SHA-256 hashing preserves relationships |
| Path Traversal | UUID-based session isolation — all paths validated |
| SQL Injection | DuckDB read-only for explore; whitelist-based mutation validation |
| File Upload | 50MB cap, extension whitelist, MIME validation |
| Rate Limiting | SlowAPI per-endpoint limits |
| Audit Trail | Immutable JSONL log of every AI mutation (SOC2-ready) |
| CORS | Configurable origin whitelist (default: localhost:3000) |

---

## 9. Environment Variables

### Backend (`backend/.env`)
| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | **Yes** | Groq Cloud API key |
| `DS_API_KEY` | No | API key for endpoint auth |
| `DS_PII_SALT` | No | Salt for PII SHA-256 hashing |
| `CORS_ORIGINS` | No | Comma-separated CORS origins |

### Frontend (`frontend/.env.local`)
| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | No | Backend URL (default: `http://127.0.0.1:8000`) |
| `NEXT_PUBLIC_API_KEY` | No | Must match `DS_API_KEY` |

---

## 10. Setup Instructions

```bash
# 1. Clone
git clone https://github.com/GhoshChinmay/DataSentinel.git
cd DataSentinel

# 2. Backend
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# 3. Create backend/.env with GROQ_API_KEY=gsk_your_key

# 4. Start backend
uvicorn main:app --reload    # → http://localhost:8000

# 5. Frontend (new terminal)
cd frontend
npm install
npm run dev                  # → http://localhost:3000
```

---

## 11. Key Design Decisions

- **5 parallel detection models** via `ThreadPoolExecutor` for max CPU throughput
- **NOTEARS** for continuous DAG optimization (true root cause, not marginal SHAP)
- **Active Learning** dynamically adjusts Human Trust Score based on operator feedback
- **Parquet** session storage with **Joblib**-cached models for instant reload
- **SSE streaming** for query results (no waiting for full response)
- **Zero `any` TypeScript** — strict type safety across all frontend code
- **Modular `engines/` package** — each AI capability in its own file
