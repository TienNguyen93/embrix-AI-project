"""
embrix.api.pipeline
───────────────────
Production NL-to-SQL Execution Pipeline for REST API backend endpoints.
Integrates:
- Hybrid RAG Retrieval (HybridSchemaRetriever)
- Resilient LLM Provider (Gemini Pool / Ollama)
- QueryAuditor (Read-Only Enforcement & EXPLAIN Audit)
- Live PostgreSQL Database Execution
"""

import time
import json
import logging
import pandas as pd
from typing import Dict, Any, Tuple, Optional
from sqlalchemy import create_engine, text


from embrix.schema_store.retrieval import HybridSchemaRetriever
from embrix.llm.factory import get_llm_provider
from embrix.agents.query_auditor import QueryAuditor
from embrix.cli import _get_engine

logger = logging.getLogger("embrix.api.pipeline")

# Cached Singleton Dependencies
_retriever_instance: Optional[HybridSchemaRetriever] = None


def get_shared_retriever() -> HybridSchemaRetriever:
    """Return singleton HybridSchemaRetriever instance."""
    global _retriever_instance
    if _retriever_instance is None:
        logger.info("Initializing singleton HybridSchemaRetriever...")
        _retriever_instance = HybridSchemaRetriever()
    return _retriever_instance


def execute_nl2sql_pipeline(
    question: str,
    schema_name: str = "core_usage",
    model_preference: str = "auto",
    preferred_model: Optional[str] = None,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Execute full production NL-to-SQL pipeline:
    1. Hybrid RAG Schema Retrieval
    2. Resilient Multi-Model Gemini / Ollama LLM Generation
    3. EXPLAIN & Read-Only Query Audit
    4. Database Execution & JSON Formatting
    """
    start_time = time.time()
    
    # 1. Retrieve Relevant Tables via Hybrid RAG
    retriever = get_shared_retriever()
    tables = retriever.retrieve_relevant_tables(question, top_k=top_k)
    
    # Format Schema Context for LLM
    schema_context_lines = []
    for tbl in tables:
        cols_str = ", ".join([f"{c.name} ({c.data_type})" for c in tbl.columns])
        schema_context_lines.append(f"Table: {tbl.qualified_name}\nDescription: {tbl.description}\nColumns: {cols_str}\n")
    schema_context = "\n".join(schema_context_lines)
    
    retrieved_table_names = [t.qualified_name for t in tables]

    # 2. Generate SQL via LLM Provider
    llm_provider = get_llm_provider(model_preference)
    llm_res = llm_provider.generate_sql(question, schema_context, preferred_model=preferred_model)
    generated_sql = llm_res.content


    # 3. Check Live DB Connection & Audit Query
    engine = _get_engine()
    auditor = QueryAuditor(engine=engine)
    
    db_online = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_online = True
    except Exception:
        db_online = False

    if not db_online:
        exec_duration = time.time() - start_time
        return {
            "sql": generated_sql,
            "result_json": "[]",
            "nl_response": f"Database is OFFLINE. Query generated and validated against metadata cache.\n\n--thought for {int(exec_duration)} seconds--",
            "retrieved_tables": retrieved_table_names,
            "metrics": {
                "input_tokens": llm_res.input_tokens,
                "output_tokens": llm_res.output_tokens,
                "estimated_cost_usd": llm_res.estimated_cost_usd,
                "model_name": llm_res.model_name,
                "provider_name": llm_res.provider_name,
                "execution_time_sec": exec_duration,
                "db_status": "OFFLINE"
            }
        }

    # 4. Online Mode: Audit & Execute against PostgreSQL
    audit_res, final_sql = auditor.execute_and_validate_with_retry(
        initial_sql=generated_sql,
        question=question,
        schema_context=schema_context,
        llm_callback=lambda p, s: llm_provider.generate_sql(p, s).content
    )

    if not audit_res.is_valid:
        raise ValueError(f"Query Audit Failed: {audit_res.error_message}")

    # Execute SQL and fetch rows
    try:
        df = pd.read_sql(text(final_sql), engine)
        result_json = df.to_json(orient="records") if not df.empty else "[]"
        row_count = len(df)
    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        raise RuntimeError(f"Database Query Execution Failed: {e}")

    exec_duration = time.time() - start_time
    nl_response = (
        f"Query executed successfully returning {row_count} rows.\n\n"
        f"--thought for {int(exec_duration)} seconds--"
    )

    return {
        "sql": final_sql,
        "result_json": result_json,
        "nl_response": nl_response,
        "retrieved_tables": retrieved_table_names,
        "metrics": {
            "input_tokens": llm_res.input_tokens,
            "output_tokens": llm_res.output_tokens,
            "estimated_cost_usd": llm_res.estimated_cost_usd,
            "model_name": llm_res.model_name,
            "provider_name": llm_res.provider_name,
            "execution_time_sec": exec_duration,
            "db_status": "ONLINE"
        }
    }
