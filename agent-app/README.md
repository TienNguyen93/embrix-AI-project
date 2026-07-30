# 🚀 Embrix AI Agent — Production Application (`agent-app`)

Welcome to **`agent-app`**! This directory contains the complete, production-ready Conversational Business Intelligence (BI) REST API server, Hybrid RAG engine, multi-model Gemini/Ollama rate-limiter pool, and evaluation benchmark suite. 

Visit [Walkthrough Documentation](documentation/WALKTHROUGH.md) for a complete system walkthrough. It may contains duplicate information from this README.

---

## 📂 Active Workspace Folder Structure (`agent-app/`)

```
agent-app/
├── app.py                      # FastAPI REST API Server Entry Point (Port 8000)
├── test_api.py                 # Integration Unit Tests for REST API Endpoints
├── .env.example                # Configuration & Free Tier API Quota Template
├── schema_snapshot.json        # Pre-cached Schema Metadata Snapshot (1,013 Tables)
├── WALKTHROUGH.md              # Beginner System Walkthrough & Architecture Guide
├── RATE_LIMITER_EXPLANATION.md # Detailed Sliding Window Rate Limiter Mechanics
├── RAG_EVALUATION_EXPLANATION.md # RAG Benchmark Evaluation Suite & Formulas
└── embrix/
    ├── agents/                 # Security Auditor & EXPLAIN Validation
    │   └── query_auditor.py    # Read-Only Enforcement & EXPLAIN Retry Loop
    ├── api/                    # REST API Endpoints & Execution Pipeline
    │   ├── schemas.py          # Pydantic DTO Request/Response Models
    │   └── pipeline.py         # End-to-End NL-to-SQL Execution Pipeline
    ├── eval/                   # RAG Evaluation Suite & Benchmark Dataset
    │   ├── benchmark_dataset.jsonl # 20-Case Gold Standard Dataset
    │   ├── evaluator.py        # Metrics Engine (Recall@K, Precision@K, MRR, Pass Rate)
    │   └── run_eval.py         # CLI Benchmark Suite Runner
    ├── llm/                    # Decoupled LLM Providers & Rate Limiter Pool
    │   ├── base.py             # BaseLLMProvider Interface & LLMResponse Object
    │   ├── rate_limiter.py     # Thread-Safe Multi-Quota Sliding Window Rate Limiter
    │   ├── gemini_pool.py      # Free Gemini Model Pool (3.1 Flash Lite, 3 Flash, 2.5 Flash Lite)
    │   ├── ollama_provider.py  # Local Ollama Provider (qwen3.5 / llama.cpp)
    │   └── factory.py          # Resilient Provider with Automatic Failover Circuit
    └── schema_store/           # Hybrid RAG Engine, Vector Store & Chunking
        ├── init_db.py          # Metadata DB Bootstrapper (pgvector / SQLite fallback)
        ├── chunker.py          # Parent (Table) + Child (Column) Chunking Strategy
        ├── enrichment.py       # Pre-Embedding Business Synonym & Taxonomy Enrichment
        ├── retrieval.py        # Hybrid RAG Engine (Dense Vector + Sparse GIN + RRF + FK Graph)
        └── models.py           # TableMetadata & ColumnMetadata Datatypes
```

---

## 🔄 Reused Components & Module Cross-References

`agent-app` combines architectural components across the workspace:

1. **Frontend React Web Interface**: Reused directly from **[`SQL-agentic-web-app/frontend/`]** (`App.jsx`, Recharts visualizer, model selector dropdown, Vite dev server on port `5173`).
2. **EXPLAIN Query Auditor**: Reused and upgraded from `Embrix-AI-agent/embrix/agents/query_auditor.py` into **[`agent-app/embrix/agents/query_auditor.py`]** for PostgreSQL `EXPLAIN` syntax validation and read-only protection.
3. **Schema Memory & Introspection**: Reused and enriched from `Embrix-AI-agent/embrix/schema_store/` into **[`agent-app/embrix/schema_store/`]** with `pgvector` HNSW vector distance support and SQLite fallback (`embrix_meta.db`).

---

## ⚡ Self-Correction & Live Database Query Error Resolution

### How Incorrect Column Names or SQL Errors Are Fixed Automatically:

When connected to a **LIVE PostgreSQL database connection**, the system activates the `QueryAuditor` feedback loop ([`query_auditor.py`]):

1. **Dry-Run `EXPLAIN` Check**: Before running queries, PostgreSQL performs a dry-run `EXPLAIN SELECT ...`.
2. **Error Capture & Feedback**: If the LLM generates a wrong column name (e.g. PostgreSQL returns `ERROR: column "bill_country" does not exist`), `QueryAuditor` catches the exact database error message.
3. **Automated Self-Correction**: The exact error traceback is fed directly back to the LLM:
   > *"Previous attempted SQL generated a database error: column 'bill_country' does not exist on table core_engine.coopeg_invoice_summary. Please fix the column name and return valid SQL."*
4. **Corrected SQL Execution**: The LLM corrects the column name on the spot and returns valid SQL without user intervention.

Furthermore, in live mode, **`pgvector`** dense vector similarity matches user terms (e.g. *"electricity consumption"*) directly to exact column chunks (e.g. `readingvalue`), preventing column guessing in the first place.

---

## 🧠 Multi-Model Free Tier Rate Limiter (`rate_limiter.py` & `gemini_pool.py`)

Tracks rolling sliding-window quotas to guarantee free API limits are never exceeded:

| Gemini Model | RPM (Req/Min) | TPM (Tokens/Min) | RPD (Req/Day) | Role |
| :--- | :---: | :---: | :---: | :--- |
| **`gemini-3.1-flash-lite`** | **`15`** | **`250,000`** | **`500`** | Primary Model |
| **`gemini-3-flash`** | **`5`** | **`250,000`** | **`20`** | Secondary Failover |
| **`gemini-2.5-flash-lite`** | **`10`** | **`250,000`** | **`20`** | Tertiary Failover |
| **`qwen3.5` (Local Ollama)** | **`Unlimited`** | **`Unlimited`** | **`Unlimited`** | Local 0-Cost Fallback |

---

## 💻 Step-by-Step Setup & How to Run

### Step 1: Environment Setup (Git Bash)
```bash
cd agent-app
git checkout API-enforce

# Create Python virtual environment
python -m venv venv

# Activate Python virtual environment (or appropriate activation command based on your OS)
source venv/Scripts/activate

# Clean dependencies
pip install sqlalchemy psycopg2-binary pydantic python-dotenv pandas tabulate fastapi uvicorn requests httpx
```

---

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill out the required fields in `.env`.
*(If using local SQLite fallback, no `META_DB_PASSWORD` is needed)*

---

### Step 3: Initialize Database Metadata Catalog
```bash
python -m embrix.schema_store.init_db
```

---

### Step 4: Launch Backend & Frontend

#### Terminal 1 — Start REST API Backend Server:
```bash
cd agent-app
python app.py
```
- API Server: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`

#### Terminal 2 — Start React Web UI:
```bash
cd SQL-agentic-web-app/frontend
npm run dev
```
- Web Application UI: `http://localhost:5173`

---

## 📄 Detailed Markdown Technical Guides
- **[WALKTHROUGH.md](agent-app/WALKTHROUGH.md)**: Beginner step-by-step system walkthrough and data flow.
- **[RATE_LIMITER_EXPLANATION.md](agent-app/RATE_LIMITER_EXPLANATION.md)**: Deep-dive technical explanation of the multi-quota Sliding Window Log algorithm.
- **[RAG_EVALUATION_EXPLANATION.md](agent-app/RAG_EVALUATION_EXPLANATION.md)**: Architectural guide for Recall@K, Precision@K, MRR, and EXPLAIN pass rate metrics.
