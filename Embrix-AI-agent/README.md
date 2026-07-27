# Embrix AI Agent (SQL Agent & RAG Core)

The **Embrix-AI-agent** directory contains the core engine for schema introspection, metadata storage, targeted vector retrieval (RAG), execution-based SQL validation (Query Auditor), and automated schema drift synchronization between **Antigravity / VSCode / Codex** and the **Embrix** PostgreSQL database.

---

## Cleaned Folder Structure

```
Embrix-AI-agent/
├── embrix/                         # Python package for schema store, agents & RAG
│   ├── cli.py                      # Unified 1-shot CLI query engine & token estimator
│   ├── agents/
│   │   └── query_auditor.py        # EXPLAIN dry-run auditor & self-correction retry loop
│   └── schema_store/
│       ├── models.py               # TableMetadata and SchemaSnapshot datatypes
│       ├── introspect.py           # Live DB catalog inspector
│       ├── store.py                # SchemaSnapshot persistence & accessors
│       ├── retrieval.py            # ChromaDB vector index & 1-hop FK expansion RAG
│       └── drift_sync.py           # Schema drift detector & auto-resync engine
├── scripts/                        # Schema enrichment utilities
│   ├── enrich_schema_descriptions.py  # LLM-based column/table description generator
│   └── fast_enrich_all.py             # Heuristic snapshot description generator
├── chroma_db/                      # ChromaDB persistent vector database directory
├── schema_snapshot.json            # Persisted JSON schema metadata store (1013 tables)
├── nl2sql_validation_plan.md       # Implementation blueprint for Schema Store & Auditor
├── schema_drift_workflow.md        # 3-trigger schema drift synchronization spec
├── .env & .env.template            # Environment variables configuration
└── README.md                       # Setup and running instructions for Embrix AI Agent
```

---

## Model & Execution Prerequisites

Depending on how you intend to run queries, review the prerequisites below:

### 🤖 1. For AI Chat Mode (VS Code, Antigravity, Codex)
- **Zero Local Model Setup Required!**
- The AI Assistant automatically uses its built-in cloud LLM (Gemini 3.6 Flash / Pro) in-memory to inspect `schema_snapshot.json`, generate SQL queries, and audit execution without requiring local Ollama setup or writing temporary `.py` files.

### 💻 2. For Local Terminal CLI Mode (`python -m embrix.cli`)
- Requires [Ollama](https://ollama.com/) running locally with **`qwen3.5`** (for SQL generation) and **`nomic-embed-text`** (for ChromaDB vector embeddings):
  ```bash
  ollama pull qwen3.5
  ollama pull nomic-embed-text
  ```

---

## Post-Clone Setup

### Step 1: Create & Activate Virtual Environment
Before installing dependencies, **create and activate a Python virtual environment**:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Git Bash:
source venv/Scripts/activate

# On PowerShell:
.\venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```bash
pip install sqlalchemy psycopg2-binary chromadb pydantic python-dotenv pandas tabulate
```

### Step 3: One-Time Initialization Task
Run the initialization task once after creating and activating the virtual environment:
```bash
python -m embrix.cli --init
```

---

## Schema Drift & Synchronization (`schema_drift_workflow.md`)

### When to Use Schema Drift Sync:
When the live PostgreSQL database schema changes (e.g., new tables added, columns modified, data types altered), `schema_snapshot.json` and ChromaDB embeddings must be resynced so queries don't generate outdated SQL.

### How to Use Schema Drift Sync:

#### 1. Manual On-Demand Resync (Terminal)
Run the drift detector directly to compare `schema_snapshot.json` with PostgreSQL catalog:
```bash
python -m embrix.schema_store.drift_sync
```

#### 2. Automated Server Triggers (Reference: `schema_drift_workflow.md`)
Refer to **[`schema_drift_workflow.md`](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/schema_drift_workflow.md)** for integrating automatic drift checking in long-running services:
- **Startup Trigger**: Checks schema drift once at server launch before serving user requests.
- **Scheduled Trigger**: Runs periodically (e.g., hourly via `APScheduler`) during background operation.
- **Reactive Trigger**: Fires automatically if `QueryAuditor` detects 2+ `EXPLAIN` query failures on the same table within 5 minutes.

---

## Asking Database Questions

Once initialized, ask any natural language question via terminal:
```bash
python -m embrix.cli "What are the unpaid invoices by country?"
```

Or ask the AI Assistant directly in chat without granting file creation permissions:
The assistant will immediately respond with:
- 💻 **Generated SQL Query**
- 📊 **Query Execution Results Table**
- 🔢 **Token Usage & Cost Calculation**
