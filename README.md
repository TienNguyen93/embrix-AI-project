# Embrix Conversational Analytics (Multi-Agent BI)

Welcome to the **Embrix Conversational BI Platform** repository. The project is organized into two primary sub-modules:

---

## Workspace Structure

```
.
├── SQL-agentic-web-app/      # Web Application (FastAPI Backend + React/Vite Frontend)
│   ├── backend/               # FastAPI orchestration server & LangGraph pipeline
│   ├── frontend/              # Glassmorphic React UI canvas with Recharts & SQL editor
│   ├── .env                   # Web app environment configuration
│   └── README.md              # Instructions for running the web application
│
├── Embrix-AI-agent/          # SQL Agent Core, RAG & Schema Infrastructure
│   ├── embrix/                # Schema Store, Vector Retrieval, Query Auditor & Drift Sync
│   ├── scripts/               # Schema metadata enrichment scripts
│   ├── chroma_db/             # ChromaDB vector index directory
│   ├── schema_snapshot.json   # Persisted schema metadata snapshot
│   ├── architecture.md        # Technical architecture documentation
│   ├── nl2sql_validation_plan.md # Validation & self-correction blueprint
│   ├── schema_drift_workflow.md  # Schema drift synchronization specification
│   ├── sample_questions.md    # Sample business queries and benchmark SQL
│   └── README.md              # Instructions for setup and agent administration
```

---

## 1. Web Application (`SQL-agentic-web-app`)

The **[SQL-agentic-web-app](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/SQL-agentic-web-app/README.md)** directory contains everything needed to build and run the full conversational BI web interface.

- **FastAPI Backend**: Orchestrates LangGraph multi-agent nodes (`sql_agent.py`), connects to PostgreSQL, and maintains conversational memory in SQLite.
- **React Frontend**: Modern glassmorphic interface with streaming execution steps, Recharts visualizations, interactive SQL editing, and follow-up recommendations.

👉 **Quick Start**: Refer to **[SQL-agentic-web-app/README.md](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/SQL-agentic-web-app/README.md)** for detailed backend and frontend setup instructions.

---

## 2. SQL Agent Core & RAG (`Embrix-AI-agent`)

The **[Embrix-AI-agent](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/README.md)** directory contains the core engine for schema store persistence, vector retrieval (RAG with 1-hop FK expansion), dry-run `EXPLAIN` query auditing, and automatic schema drift synchronization.

- **Schema Metadata Store**: `schema_snapshot.json` stores table and column descriptions without hitting the live DB per request.
- **ChromaDB Vector RAG**: Retrieves relevant schema subsets for natural language queries.
- **Query Auditor**: Dry-runs SQL queries using `EXPLAIN` to catch syntax/schema hallucinations before execution.
- **Schema Drift Sync**: Monitors DB schema changes and automatically updates the metadata store and vector index.

👉 **Quick Start**: Refer to **[Embrix-AI-agent/README.md](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/README.md)** for instructions on running introspection, enrichment scripts, vector indexing, and drift sync tasks.
