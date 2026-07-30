# Embrix AI Codebase Documentation

This document provides extremely detailed documentation of every single file within the `keen-einstein` project workspace, including the CLI agent, the web application, config files, modules, and the newly established `agent-app/` active development directory.

## Root Directory (`/`)

* **`README.md`**
  * **Purpose & Architecture:** The main entry point documentation for the overall project.
  * **Role in System:** Explains high-level goals of the Embrix Conversational Analytics system.
* **`AGENTS.md`**
  * **Purpose & Architecture:** Embrix AI Agent Directives containing zero-scratch-file protocols, required output formats (SQL + Markdown table + Token Cost), and read-only (SELECT) enforcement rules.
  * **Role in System:** Essential instruction manual used by LLM agents acting within the workspace.
* **`architecture_tradeoff_breakdown.txt`**
  * **Purpose & Architecture:** Text file documenting technical choices, why certain database and agentic frameworks were chosen, and their performance tradeoffs.
* **`miscel.md`**
  * **Purpose & Architecture:** Miscellaneous developer notes and scratchpad ideas for system expansions.
* **`.gitignore`**
  * **Purpose & Architecture:** Standard Git ignore file protecting `.env`, `venv`, `__pycache__`, and SQLite artifacts from being committed.

---

## agent-app (`/agent-app/`)
*Clean active application folder hosting REST API, multi-model Gemini rate limiting, and pgvector RAG development.*

### Configs & Core Package
* **`.env`**: Active environment variables for DB connections, LLM APIs, and embedding settings.
* **`.env.example`**: Environment variable template for team onboarding (PostgreSQL creds, Gemini API Key, Ollama base URL, ports).
* **`WALKTHROUGH.md`**: Complete end-to-end beginner guide explaining system goals, file-by-file functions, simple examples, system diagrams, and setup instructions.
* **`RATE_LIMITER_EXPLANATION.md`**: Deep-dive technical explanation of the multi-dimensional Sliding Window Log Rate Limiter algorithm.
* **`RAG_EVALUATION_EXPLANATION.md`**: Detailed architectural guide explaining the RAG benchmark evaluation suite, formulas, and frontend connection.
* **`AGENTS.md`**: Directives and output protocols for the active application workspace.




* **`README.md`**: Setup and execution instructions for `agent-app`.
* **`nl2sql_validation_plan.md`**: Plan for Natural Language to SQL validation pipelines.
* **`schema_drift_workflow.md`**: Design doc explaining schema drift detection and synchronization.
* **`schema_snapshot.json`**: A static, in-memory representation of the full schema metadata.
* **`embrix_meta.db`**: Local SQLite metadata store fallback.

### `embrix/` (Main Python Package)
* **`__init__.py`**: Exposes the package modules.
* **`cli.py`**
  * **Purpose:** Command Line Interface handling query parsing, schema context, and inference pipeline.
  * **Key Functions:** `calculate_token_usage()`, `call_ollama_llm()`, `generate_sql_from_schema()`, `run_pipeline()`.

#### `embrix/agents/` (Agentic Tools)
* **`__init__.py`**: Exposes agent functionalities.
* **`query_auditor.py`**
  * **Purpose:** Ensures database safety (read-only enforcement) and valid SQL syntax.
  * **Role in System:** Intercepts generated SQL. If it contains DML/DDL, provides feedback for auto-retry.

#### `embrix/eval/` (RAG Evaluation Framework & Benchmark Suite)
* **`__init__.py`**: Exposes evaluation suite modules.
* **`benchmark_dataset.jsonl`**
  * **Purpose:** Gold-standard benchmark dataset containing 20 curated natural language questions across `core_usage`, `core_revenue`, `core_engine`, `core_oms`, `core_pricing`, `core_mediation`, and `core_config` with target table ground truths.
* **`evaluator.py`**
  * **Purpose:** `RAGEvaluator` engine calculating **Recall@K**, **Precision@K**, **Mean Reciprocal Rank (MRR)**, **EXPLAIN Pass Rate**, and latency metrics.
* **`run_eval.py`**
  * **Purpose:** CLI benchmark runner executing automated RAG evaluation sweeps and formatting terminal output tables.

### Phase 7 RAG Evaluation Framework Flow Diagram

```mermaid
flowchart TD
    A["Benchmark Dataset (20 Cases) - embrix/eval/benchmark_dataset.jsonl"] --> B["CLI Benchmark Runner - embrix/eval/run_eval.py"]
    
    B --> C["RAG Evaluator Engine - embrix/eval/evaluator.py"]
    
    %% Retrieval Evaluation
    C --> D["1. Hybrid RAG Retrieval Sweep - embrix/schema_store/retrieval.py"]
    D --> D1["Dense HNSW + Sparse tsvector GIN + RRF + O(1) FK Expansion"]
    
    %% Metric Calculation
    D1 --> E["2. Precision & Recall Metric Engine - embrix/eval/evaluator.py"]
    E --> E1["Recall@5 Calculation"]
    E --> E2["Precision@5 Calculation"]
    E --> E3["Mean Reciprocal Rank (MRR) Calculation"]
    
    %% Audit Pass Rate
    C --> F["3. Security & Syntax Auditor - embrix/agents/query_auditor.py"]
    F --> F1["EXPLAIN Pass Rate & Read-Only Verification"]
    
    %% Output Report
    E1 & E2 & E3 & F1 --> G["Markdown Benchmark Performance Report - embrix/eval/run_eval.py"]
```

#### `app.py` & `embrix/api/` (Production REST API & UI Integration)
* **`app.py`**
  * **Purpose:** FastAPI REST API Application server.
  * **Role in System:** Serves endpoints for `SQL-agentic-web-app/frontend` (`/query`, `/query/rerun`, `/sessions`, `/schema/empty_tables`, `/suggested_questions`, `/health`).
* **`embrix/api/schemas.py`**
  * **Purpose:** Pydantic DTO data models (`QueryRequest`, `QueryResponse`, `SessionRequest`, `HealthResponse`).
* **`embrix/api/pipeline.py`**
  * **Purpose:** Production NL-to-SQL Execution Pipeline connecting Hybrid RAG Retrieval, Resilient LLM Pool, QueryAuditor, and PostgreSQL data fetching.

### Phase 6 System Architecture & REST API Flow Diagram

```mermaid
flowchart TD
    A["React Web UI - SQL-agentic-web-app/frontend"] -->|HTTP POST /query| B["FastAPI Server - agent-app/app.py"]
    
    B --> C["API Execution Pipeline - embrix/api/pipeline.py"]
    
    %% RAG Step
    C --> D["1. Hybrid Schema Retriever - embrix/schema_store/retrieval.py"]
    D --> D1["Dense HNSW + Sparse tsvector GIN + RRF + O(1) FK Expansion"]
    
    %% LLM Step
    C --> E["2. Resilient LLM Provider - embrix/llm/factory.py"]
    E --> E1["Multi-Model Gemini Pool (gemini-2.0-flash-exp) -> Local Ollama Fallback"]
    
    %% Audit Step
    C --> F["3. Query Auditor - embrix/agents/query_auditor.py"]
    F --> F1["Read-Only Check & PostgreSQL EXPLAIN Syntax Validation"]
    
    %% DB Execution Step
    C --> G["4. Live Database Execution - embrix/cli.py"]
    G --> H["PostgreSQL Database - 10.22.16.238"]
    
    H -->|Query Results JSON| B
    B -->|QueryResponse JSON Payload| A
```

#### `embrix/llm/` (Decoupled LLM Provider Abstraction & Multi-Dimensional Rate Limiter Pool)
* **`__init__.py`**: Exposes LLM provider modules.
* **`base.py`**
  * **Purpose:** Abstract Base Class (`BaseLLMProvider`) and standardized response wrapper (`LLMResponse`).
* **`rate_limiter.py`**
  * **Purpose:** Thread-safe `SlidingWindowRateLimiter` enforcing **RPM (Requests/Min)**, **TPM (Tokens/Min)**, and **RPD (Requests/Day)** sliding-window quota limits.
* **`gemini_pool.py`**
  * **Purpose:** `GeminiPoolProvider` managing round-robin rotation across free Gemini models:
    - **`gemini-3.1-flash-lite`** (Primary): RPM=15, TPM=250k, RPD=500
    - **`gemini-3-flash`** (Secondary): RPM=5, TPM=250k, RPD=20
    - **`gemini-2.5-flash-lite`** (Tertiary): RPM=10, TPM=250k, RPD=20
  * **Role in System:** Multi-model pool with automatic failover on HTTP 429 or quota exhaustion.
* **`ollama_provider.py`**
  * **Purpose:** Local `OllamaProvider` (`qwen3.5` / `llama.cpp` local endpoints).
  * **qwen3.5** model architecture:        
    * Parameters:          9.7B
    * Context length:      262144
    * Embedding length:    4096
    * Quantization:        Q4_K_M
    * Requires:            0.17.1

  * **qwen3.5** Parameters
    * Presence_penalty:    1.5
    * Temperature:         1
    * Top_k:               20
    * Top_p:               0.95 
* **`factory.py`**
  * **Purpose:** `ResilientLLMProvider` and `get_llm_provider()` factory implementing automatic failover from free Gemini Pool to local Ollama to offline heuristic fallback.

### Phase 5 Multi-Model Gemini Rate-Limiter Pool Flow Diagram

```mermaid
flowchart TD
    A["User NL Question & Schema Context"] --> B["ResilientLLMProvider - embrix/llm/factory.py"]
    
    %% Gemini Pool Path
    B --> C["GeminiPoolProvider - embrix/llm/gemini_pool.py"]
    C --> D["SlidingWindowRateLimiter (RPM, TPM, RPD) - embrix/llm/rate_limiter.py"]
    D -->|Check RPM, TPM, RPD Limits| E{"Quota OK? - embrix/llm/rate_limiter.py"}
    
    E -- YES --> F["Primary: gemini-3.1-flash-lite (RPM:15, TPM:250k, RPD:500) - embrix/llm/gemini_pool.py"]
    E -- NO / 429 Error --> G["Secondary: gemini-3-flash (RPM:5, TPM:250k, RPD:20) - embrix/llm/gemini_pool.py"]
    G -- 429 Error --> H["Tertiary: gemini-2.5-flash-lite (RPM:10, TPM:250k, RPD:20) - embrix/llm/gemini_pool.py"]
    
    %% Local Ollama Fallback Path
    H -- All Gemini Rate Limited --> I["Local Fallback: OllamaProvider (qwen3.5) - embrix/llm/ollama_provider.py"]
    F & G & H & I --> J["LLMResponse (Content, Tokens, Cost USD) - embrix/llm/base.py"]
```

### Phase 4 Hybrid RAG Engine Flow Diagram

```mermaid
flowchart TD
    A["Natural Language Question"] --> B["1. Vector Query Embedder: nomic-embed-text - embrix/schema_store/retrieval.py"]
    A --> C["2. Keyword & Lexical Extractor - embrix/schema_store/retrieval.py"]
    
    B -->|search_query: prefix| D["Dense Vector Search: HNSW Cosine Distance - embrix/schema_store/init_db.py"]
    C --> E["Sparse Lexical Search: tsvector GIN / Keyword Match - embrix/schema_store/init_db.py"]
    
    D -->|Top 30 Dense Hits| F["Reciprocal Rank Fusion Engine: RRF Score = 1 / 60 + DenseRank + 1 / 60 + SparseRank - embrix/schema_store/retrieval.py"]
    E -->|Top 30 Sparse Hits| F
    
    F --> G["Fused Top Candidate Tables - embrix/schema_store/retrieval.py"]
    G --> H["3. O(1) Prebuilt Foreign-Key Graph Expansion - embrix/schema_store/retrieval.py"]
    H -->|Forward & Reverse FK Expansion| I["Final Relational Schema Context to LLM - embrix/schema_store/retrieval.py"]
```

### Phase 3 Pre-Embedding Contextual Enrichment Flow Diagram

```mermaid
flowchart TD
    A["Raw Database Metadata - agent-app/schema_snapshot.json"] --> B["SchemaEnricher Engine - embrix/schema_store/enrichment.py"]
    
    %% Table Domain Mapping
    B --> C["1. Domain Category Taxonomy Mapping - embrix/schema_store/enrichment.py"]
    C -->|core_usage| C1["Domain: Usage & Telemetry Rating Engine - embrix/schema_store/enrichment.py"]
    C -->|core_revenue| C2["Domain: Revenue Accounting & Ledger - embrix/schema_store/enrichment.py"]
    C -->|core_engine| C3["Domain: Billing & Account Management - embrix/schema_store/enrichment.py"]
    
    %% Synonym Injection
    B --> D["2. Column Business Synonym Injection - embrix/schema_store/enrichment.py"]
    D --> D1["readingvalue -> Usage Consumption Volume / kWh - embrix/schema_store/enrichment.py"]
    D --> D2["latestreadingdate -> Usage Timestamp / Reading Date - embrix/schema_store/enrichment.py"]
    D --> D3["accountid -> Customer Account Number - embrix/schema_store/enrichment.py"]
    
    %% Factual vs Search Synonym Pre-Embedding Text
    C1 & C2 & C3 & D1 & D2 & D3 --> E["3. Construct Enriched Pre-Embedding Text Document - embrix/schema_store/enrichment.py"]
    E --> E1["Factual Description + Related Business Synonym Tags - embrix/schema_store/enrichment.py"]
    E1 --> F["Feed Enriched Snapshot to Phase 2 SchemaChunker & HNSW Vector Store - embrix/schema_store/chunker.py"]
```

### Phase 2 Chunking & Retrieval Flow Diagram

```mermaid
flowchart TD
    A["schema_snapshot.json / SchemaSnapshot - embrix/schema_store/models.py"] --> B["SchemaChunker - embrix/schema_store/chunker.py"]
    
    %% Parent Branch
    B -->|All 1,013 Tables| C["Parent Chunk Generator - embrix/schema_store/chunker.py"]
    C --> C1["ParentChunk: Table Name, Schema, Summary, PKs, FKs - embrix/schema_store/chunker.py"]
    C1 --> C2["Upsert to schema_tables in pgvector - embrix/schema_store/init_db.py"]

    %% Child Branch
    B -->|Check Column Count > 30| D{"Is Wide Table? - embrix/schema_store/chunker.py"}
    D -- NO (<=30 Cols) --> E["Skip Child Chunks - embrix/schema_store/chunker.py"]
    D -- YES (>30 Cols) --> F["Child Chunk Generator - embrix/schema_store/chunker.py"]
    F --> F1["ChildChunk: Column Name, Data Type, Context, FK Target, Sample Values - embrix/schema_store/chunker.py"]
    F1 --> F2["Upsert to schema_columns in pgvector - embrix/schema_store/init_db.py"]

    %% Retrieval Resolution
    C2 --> G["Dense + Sparse Hybrid RAG Query - embrix/schema_store/retrieval.py"]
    F2 --> G
    G --> H["Resolve Child Column Matches Back to Parent Table - embrix/schema_store/retrieval.py"]
    H --> I["Final Reranked Relational Context to LLM - embrix/schema_store/retrieval.py"]
```
* **`store.py`**: Interfaces with ChromaDB for schema artifact storage.

#### `scripts/` (Maintenance Utilities)
* **`enrich_schema_descriptions.py`**: Script using an LLM to automatically generate semantic descriptions for schema columns.
* **`fast_enrich_all.py`**: Heuristics-based fallback for faster table documentation without LLM calls.

---

## Embrix-AI-agent (`/Embrix-AI-agent/`)
*Legacy/Standalone CLI version of the agent system. Structure is largely identical to `agent-app/` but may serve as an earlier version or isolated testbed.*
*(Files in this directory mirror the `agent-app/` structure mentioned above).*

---

## SQL-agentic-web-app (`/SQL-agentic-web-app/`)
This directory contains the full-stack web application offering an interactive chat UI over the database.

### Configs & Documentation
* **`.env` / `.env.template`**: Connection strings and port definitions for FastAPI/Vite.
* **`README.md`** & **`architecture.md`**: Explains the web-app stack (FastAPI + React), LangGraph implementation, and multi-turn conversational patterns.
* **`sample_questions.md`**: Examples to test the app.
* **`flow_diagram.png`**: Visual system map linking Frontend, Backend APIs, Memory, and DB.

### `backend/` (FastAPI Server)
* **`api.py`**
  * **Purpose:** RESTful router acting as the main gateway connecting frontend React to backend agent loops.
  * **Endpoints:** `POST /sessions`, `GET /sessions`, `GET /sessions/{session_id}/messages`, `POST /query`, `POST /query/rerun`, `GET /suggested_questions`.
* **`db_connection.py`**
  * **Purpose:** DB connection utility (`get_engine`, `check_empty_tables`, `get_schema_tables`).
* **`infer_schema.py`**
  * **Purpose:** Synthesizes metadata into LLM-friendly context strings (`build_schema_context()`).
* **`memory.py`**
  * **Purpose:** Handles SQLite-based session storage (`memory.sqlite`) to support conversational memory.
* **`sql_agent.py`**
  * **Purpose:** The core LangGraph/State-machine logic managing generation and validation (`create_sql_agent()`).
* **`export_graph_json.py` / `export_graph_png.py`**: Visualization utilities for schema topology.
* **`init_db.py` / `main.py` / `test_api.py`**: Core FastAPI bootstrapper (`main.py`) and initializations.

### `frontend/` (React + Vite UI)
* **`package.json` / `package-lock.json` / `vite.config.js`**: Node.js build configs configuring Vite.
* **`index.html`**: Root HTML mounting point for the React app.
* **`src/main.jsx`**: Bootstraps the React DOM.
* **`src/App.jsx`**
  * **Purpose:** The core chat UI component handling chat states, suggested questions, rendering the DataGrid/Charts, and LLM thoughts.
* **`src/App.css` / `src/index.css`**: Application styling.
