# Embrix Conversational Analytics (Multi-Agent BI)

Welcome to the **Embrix Conversational BI Platform** repository. 

---

## Workspace Structure

```
.
├── Embrix-AI-agent/          # SQL Agent Core, RAG & Schema Infrastructure
│   ├── embrix/                # Schema Store, Vector Retrieval, Query Auditor & Drift Sync
│   ├── scripts/               # Schema metadata enrichment scripts
│   ├── chroma_db/             # ChromaDB vector index directory
│   ├── schema_snapshot.json   # Persisted schema metadata snapshot
│   ├── nl2sql_validation_plan.md # Validation & self-correction blueprint
│   ├── schema_drift_workflow.md  # Schema drift synchronization specification
│   └── README.md              # Instructions for setup and agent administration
```

---

## Prerequisites & Execution Modes

- **🤖 AI Chat Mode (VS Code / Antigravity / Codex)**:
  - **No setup required!** The AI assistant uses its built-in cloud LLM (Gemini 3.6 Flash / Pro) in-memory to generate and audit SQL queries directly.

- **💻 Local Terminal CLI Mode (`python -m embrix.cli`)**:
  - Requires [Ollama](https://ollama.com/) running locally with **`qwen3.5`** and **`nomic-embed-text`**:
    ```bash
    ollama pull qwen3.5
    ollama pull nomic-embed-text
    ```

---

## Quick Start (Post-Clone Setup)

1. **Create & Activate Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/Scripts/activate  # Git Bash
   # or .\venv\Scripts\Activate.ps1 (PowerShell)
   ```

2. **Install Dependencies**:
   ```bash
   pip install sqlalchemy psycopg2-binary chromadb pydantic python-dotenv pandas tabulate
   ```

3. **Run Initialization**:
   ```bash
   python -m embrix.cli --init
   ```

4. **Schema Drift Resync (`schema_drift_workflow.md`)**:
   - If PostgreSQL database tables change, run manual resync:
     `python -m embrix.schema_store.drift_sync`
   - Refer to **[`Embrix-AI-agent/schema_drift_workflow.md`](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/schema_drift_workflow.md)** for Startup, Scheduled, and Reactive background triggers.

👉 **Full Documentation**: Refer to **[Embrix-AI-agent/README.md](file:///C:/Users/nguye/Documents/antigravity/keen-einstein/Embrix-AI-agent/README.md)** for detailed module references, vector RAG options, and CLI parameters.
