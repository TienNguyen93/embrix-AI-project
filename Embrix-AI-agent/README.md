# Embrix AI Agent (SQL Agent & RAG Core)

The **Embrix-AI-agent** directory contains the core engine for schema introspection, metadata storage, targeted vector retrieval (RAG), execution-based SQL validation (Query Auditor), and automated schema drift synchronization between **Antigravity** and the **Embrix** PostgreSQL database.

---

## Folder Structure

```
Embrix-AI-agent/
├── embrix/                         # Python package for schema store, agents & RAG
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
├── schema_snapshot.json            # Persisted JSON schema metadata store
├── architecture.md                 # System architecture overview & Mermaid diagram
├── nl2sql_validation_plan.md       # Implementation blueprint for Schema Store & Auditor
├── schema_drift_workflow.md        # 3-trigger schema drift synchronization spec
├── sample_questions.md             # Curated benchmark business questions & SQL queries
├── flow_diagram.png                # Architecture flow diagram
├── fast-test.py                    # Direct PostgreSQL connection verification script
├── .env & .env.template            # Environment variables configuration
└── README.md                       # Setup and running instructions for Embrix AI Agent
```

---

## Setup & Prerequisites

1. **Python Environment**:
   Activate the project virtual environment:
   ```bash
   # On Git Bash:
   source ../venv/Scripts/activate

   # On PowerShell:
   ..\venv\Scripts\Activate.ps1
   ```

2. **Dependencies**:
   Ensure required packages are installed:
   ```bash
   pip install sqlalchemy psycopg2-binary chromadb pydantic python-dotenv apscheduler
   ```

3. **Ollama Models**:
   Ensure Ollama is running locally with `nomic-embed-text` and `qwen3:8b` (or `llama3.1`):
   ```bash
   ollama pull nomic-embed-text
   ollama pull qwen3:8b
   ```

---

## Workflow & Operations

### 1. Schema Introspection & Snapshot Generation
Inspect live PostgreSQL database schemas and build the initial `schema_snapshot.json`:
```bash
python -m embrix.schema_store.introspect
```

### 2. Schema Description Enrichment
Generate table and column business descriptions for un-described snapshot entities:
```bash
# Heuristic fast enrichment
python scripts/fast_enrich_all.py

# LLM-powered enrichment (Ollama)
python scripts/enrich_schema_descriptions.py [--force]
```

### 3. ChromaDB Vector Indexing & Targeted RAG Retrieval
Sync `schema_snapshot.json` entities into ChromaDB for vector retrieval with 1-hop Foreign Key expansion:
```python
from embrix.schema_store.retrieval import SchemaRetriever

retriever = SchemaRetriever()
retriever.sync_index()

# Retrieve relevant table metadata for a query
tables = retriever.retrieve_relevant_tables("Show daily usage trends by service type", top_k=5)
```

### 4. Query Validation & Self-Correction (Query Auditor)
Validate generated SQL queries against the live database catalog using dry-run `EXPLAIN` planning:
```python
from embrix.agents.query_auditor import execute_and_validate_with_retry

# Validates and retries if EXPLAIN encounters syntax/schema errors
result = execute_and_validate_with_retry(
    question="Total volume by account",
    engine=engine,
    generate_sql_fn=my_sql_generator_function
)
```

### 5. Schema Drift Detection & Auto-Sync
Detect schema changes (added/removed tables, column type alterations) and automatically resync the metadata store:
```bash
# Run drift check manually
python -m embrix.schema_store.drift_sync
```

---

## Technical Documentation Reference

- **[architecture.md](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/architecture.md)**: Multi-agent flow diagram, module descriptions, and system integration details.
- **[nl2sql_validation_plan.md](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/nl2sql_validation_plan.md)**: Architectural phase specifications for Schema Store, Retrieval RAG, Query Auditor, and Drift handling.
- **[schema_drift_workflow.md](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/schema_drift_workflow.md)**: Detailed configuration for Startup, Scheduled, and Reactive drift triggers.
- **[sample_questions.md](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/sample_questions.md)**: Reference NL questions and benchmark SQL queries across analytics domain dashboards.
