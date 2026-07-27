# Implementation Plan: Schema-Aware SQL Generation, Self-Validation & Drift Handling

**Target agent:** Gemini 3.6 Flash / Gemini 3.1 Pro, running inside Antigravity IDE
**Target project:** Embrix (LangGraph + FastAPI + WebSocket, multi-agent NL-to-SQL system)

---

## How to use this document

This file is written as a task list for the coding agent (you, Gemini, operating in Antigravity) to execute directly against the Embrix repo. Each phase is self-contained, has a clear "done when" condition, and lists the exact files to create or modify. Work phases in order — each one depends on the previous. Do not skip the "done when" checks; they are how you confirm the phase actually works before moving to the next.

If the repo structure doesn't match the assumed paths below, first inspect the actual repo layout and adapt the paths, but keep the module boundaries (schema_store, query_auditor, drift_sync) as separate concerns — do not merge them into one file.

---

## Problem being solved

Three failure modes, three separate mechanisms — do not try to solve all three with one component:

| Failure mode | Mechanism |
|---|---|
| Agent doesn't know the schema well enough to write correct SQL | Schema metadata store + targeted retrieval (lightweight RAG, not full GraphRAG) |
| Agent hallucinates tables/columns that don't exist | Execution-based validation (EXPLAIN / dry-run) with a self-correction loop |
| Schema changes underneath the agent (drift) | Scheduled introspection job that diffs and re-syncs the metadata store |

---

## Phase 1 — Schema Metadata Store

**Goal:** Replace ad-hoc prompt-stuffed schema context with a structured, queryable store of table/column metadata.

### Steps

1. Create `embrix/schema_store/models.py` defining:
   - `TableMetadata`: table name, description, columns (name, type, nullable, description, sample values), primary key, foreign keys (target table/column).
   - `SchemaSnapshot`: dict of `TableMetadata` keyed by table name, plus a `version_hash` (hash of the full schema DDL) and `last_synced_at` timestamp.

2. Create `embrix/schema_store/introspect.py`:
   - Function `introspect_schema(db_connection) -> SchemaSnapshot` that queries `information_schema.tables`, `information_schema.columns`, and `information_schema.key_column_usage` (adjust for the actual DB engine — Postgres syntax assumed unless repo shows otherwise).
   - Do NOT hand-write descriptions here — leave `description` fields empty; those get filled once by an LLM pass (Phase 1, step 4) and cached, not regenerated on every sync.

3. Create `embrix/schema_store/store.py`:
   - Persist `SchemaSnapshot` to a local JSON file (`schema_snapshot.json`) AND load it into a vector index (see Phase 2) at startup.
   - Expose `get_table(name)`, `get_all_tables()`, `get_version_hash()`.

4. One-time enrichment step: write a small script `scripts/enrich_schema_descriptions.py` that sends each table's raw column list to the LLM once, asking it to generate a one-sentence description per table/column based on naming conventions and sample rows. Cache results into the JSON file. Only re-run this for tables flagged as changed by the Phase 4 drift job — never regenerate descriptions for unchanged tables (wastes tokens, and description quality doesn't need refreshing if the schema itself hasn't changed).

**Done when:** `schema_snapshot.json` exists, contains every table in the target DB with descriptions filled in, and `get_all_tables()` returns it without hitting the DB.

---

## Phase 2 — Targeted Schema Retrieval (lightweight RAG, not GraphRAG)

**Goal:** Given a natural language query, retrieve only the relevant subset of tables/columns instead of stuffing the entire schema into the prompt.

Do not implement full GraphRAG (community detection, graph summarization). The schema already has explicit structure via foreign keys — that structure IS the graph. Use it directly rather than rediscovering it through clustering.

### Steps

1. Create `embrix/schema_store/retrieval.py`:
   - Embed each table's `description + column names + column descriptions` as one chunk per table (use whatever embedding provider Embrix already has configured; if none, use a small local model — do not add a new paid dependency without checking existing stack first).
   - Store embeddings in a simple vector store already used elsewhere in Embrix, or `chromadb`/`faiss` if none exists yet.
   - Function `retrieve_relevant_tables(nl_query: str, top_k=5) -> list[TableMetadata]`.

2. After retrieving top-k tables by similarity, expand the set by one hop using foreign keys: for each retrieved table, pull in directly-connected tables (via FK) even if they didn't score high on similarity. This is the "graph" part — a single-hop FK expansion, not a learned graph model. This catches join tables that wouldn't otherwise match the NL query semantically.

3. Wire this into the existing SQL-generation agent node in the LangGraph graph: replace whatever full-schema context injection exists today with a call to `retrieve_relevant_tables()`, and pass only that subset into the prompt.

**Done when:** For a test query like "show me total orders by customer last month," the retrieved table set includes `orders` and `customers` (and any join table) but excludes unrelated tables like `audit_logs` or `feature_flags`.

---

## Phase 3 — Query Auditor: Execution-Based Self-Validation

**Goal:** Catch hallucinated SQL before it reaches the user, using the database as ground truth rather than asking the LLM to grade its own output.

This is the most important phase — it's what actually prevents hallucination, not the schema context alone.

### Steps

1. In the existing Query Auditor agent node (per the Embrix multi-agent design), implement:
   ```python
   def validate_query(sql: str, db_connection) -> ValidationResult:
       try:
           # Use EXPLAIN (or EXPLAIN QUERY PLAN for SQLite) — this parses and
           # plans the query against the live schema WITHOUT executing it or
           # returning/mutating data.
           db_connection.execute(f"EXPLAIN {sql}")
           return ValidationResult(valid=True)
       except DatabaseError as e:
           return ValidationResult(valid=False, error=str(e))
   ```
   Use `EXPLAIN` (read-only plan) rather than actually running the query — this validates correctness against live schema without cost or side effects. For write-capable queries, additionally confirm the query is read-only via an AST check before even reaching this step (Embrix should not execute non-SELECT statements generated by the agent without separate explicit confirmation logic).

2. Wire a self-correction loop in the LangGraph graph: if `validate_query` fails, feed the exact DB error message back to the SQL-generation node as additional context and regenerate. Cap retries at 2 attempts. On a 3rd failure, return a clear failure to the user with the last error rather than looping indefinitely.

3. Log every validation failure (query, error, retrieved tables used) to a `validation_failures` table or log file. This log is the input to Phase 4's drift detection — repeated failures referencing the same table/column are the strongest signal that the schema changed.

**Done when:** Deliberately ask the agent a question referencing a nonexistent column; confirm it fails EXPLAIN, retries once with corrected SQL, and either succeeds or returns a clear error — never silently returns a hallucinated result.

---

## Phase 4 — Drift Detection & Auto-Resync

**Goal:** Keep the schema metadata store (Phase 1) in sync automatically when the underlying database changes, without a full re-index every time.

### Steps

1. Create `embrix/schema_store/drift_sync.py`:
   - Function `check_drift() -> bool` that re-runs `introspect_schema()` (cheap — metadata-only, no data scan) and compares the new `version_hash` against the stored one.
   - If hashes differ, diff table-by-table and column-by-column to find exactly what changed (added/removed/renamed table or column, type change).

2. Only re-run the LLM description-enrichment step (Phase 1, step 4) for the tables that actually changed — not the whole schema. Update `schema_snapshot.json` and re-embed only those changed table chunks in the vector store (Phase 2).

3. Trigger `check_drift()` in two ways:
   - **Scheduled:** a lightweight background task (APScheduler, or whatever job runner Embrix already uses) every N hours — pick an interval based on how often the DB actually changes in this environment; hourly is a reasonable default for active development.
   - **Reactive:** if the Query Auditor (Phase 3) logs 2+ validation failures referencing the same table within a short window, trigger an immediate `check_drift()` rather than waiting for the schedule. This handles the case where a schema change just happened and users are actively hitting it.

4. If drift is detected mid-conversation (reactive trigger fires), surface a clear one-line message to the user ("Note: the `orders` table schema was updated — retrying with the new structure") before retrying — don't fail silently or retry without explanation.

**Done when:** Manually add a column to a test table in the DB, confirm `check_drift()` detects it within one cycle, updates the snapshot, and the next NL query referencing that column succeeds without a code change or restart.

---

## File structure summary

```
embrix/
  schema_store/
    models.py          # TableMetadata, SchemaSnapshot
    introspect.py       # DB → SchemaSnapshot
    store.py            # persistence + accessors
    retrieval.py         # embedding + FK-expansion retrieval
    drift_sync.py         # diffing + resync triggers
  agents/
    query_auditor.py     # EXPLAIN-based validation + retry loop (existing agent, modified)
    sql_generator.py     # existing agent, modified to use retrieval.py
scripts/
  enrich_schema_descriptions.py   # one-time / per-drift LLM enrichment
schema_snapshot.json     # persisted metadata store
```

---

## Order of implementation (recap)

1. Schema metadata store (Phase 1) — do this first, everything else depends on it.
2. Retrieval (Phase 2) — needs Phase 1's data to embed.
3. Query Auditor validation loop (Phase 3) — can be built in parallel with Phase 2, but needs Phase 1's live DB connection pattern.
4. Drift sync (Phase 4) — needs Phases 1–3 all working, since it re-triggers pieces of each.

## Explicitly out of scope for this plan

- Full GraphRAG (community summarization, graph embeddings) — not justified for a relational schema with explicit FK structure.
- Automatic execution of write queries (INSERT/UPDATE/DELETE) generated by the agent — validation here only covers read-path correctness; write-path safety needs a separate confirmation-gated design if Embrix ever supports it.
- Multi-database / cross-schema federation — this plan assumes a single target database; extend `introspect.py` per-engine if Embrix needs to support more than one DB type.
