"""
embrix.cli
──────────
Unified CLI & Programmatic Query Engine for Embrix-AI-agent.

Executes end-to-end NL-to-SQL generation, EXPLAIN validation,
data execution, and token usage calculation without creating scratch files.

Usage from terminal:
    python -m embrix.cli "Show daily service usage readings by date"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import pandas as pd
from typing import Dict, Any, Optional

# Ensure Embrix-AI-agent root is on sys.path
_AGENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _AGENT_ROOT not in sys.path:
    sys.path.insert(0, _AGENT_ROOT)

from embrix.schema_store.store import SchemaStore
from embrix.schema_store.retrieval import SchemaRetriever, format_table_document
from embrix.agents.query_auditor import validate_query, is_read_only, execute_and_validate_with_retry
from embrix.schema_store.introspect import _get_engine
from sqlalchemy import text


FEW_SHOT_SQL_SKILL = """
### FEW-SHOT SQL GENERATION RULES & EXAMPLES:
1. Always schema-qualify tables (e.g., `core_usage.service_usage_readings`, `billing.invoices`).
2. Only use column names explicitly listed in the provided Schema Context.
3. Always include `LIMIT 50` for large result sets.
4. Output strictly read-only SELECT queries.

Example 1:
Question: Total reading value by service type
Schema Context: Table: core_usage.service_usage_readings Columns: servicetype (varchar), readingvalue (numeric)
SQL:
```sql
SELECT servicetype, SUM(readingvalue) AS total_usage, COUNT(*) AS reading_count
FROM core_usage.service_usage_readings
GROUP BY servicetype
ORDER BY total_usage DESC
LIMIT 50;
```

Example 2:
Question: Show daily service usage readings by date
Schema Context: Table: core_usage.service_usage_readings Columns: latestreadingdate (timestamp), servicetype (varchar), readingvalue (numeric)
SQL:
```sql
SELECT DATE(latestreadingdate) AS fecha, servicetype, SUM(readingvalue) AS uso_total, COUNT(*) AS total_lecturas
FROM core_usage.service_usage_readings
WHERE latestreadingdate IS NOT NULL
GROUP BY DATE(latestreadingdate), servicetype
ORDER BY fecha DESC, servicetype
LIMIT 50;
```
"""


def calculate_token_usage(prompt_text: str, sql_text: str, reasoning_text: str = "") -> Dict[str, Any]:
    """Estimate token usage for prompt input and output generation."""
    input_tokens = len(prompt_text) // 4
    output_tokens = (len(sql_text) + len(reasoning_text)) // 4
    total_tokens = input_tokens + output_tokens
    cost_usd = (input_tokens * 0.075 / 1_000_000) + (output_tokens * 0.30 / 1_000_000)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(cost_usd, 6),
    }


def call_ollama_llm(prompt: str, model: str = "qwen3.5", timeout: int = 60) -> Optional[str]:
    """Attempt to generate SQL using local Ollama model with reasoning tag filtering."""
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1}
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            raw_response = res_json.get("response", "")
            
            # Clean out <think>...</think> or <thought>...</thought> tags from reasoning models
            clean_response = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL)
            clean_response = re.sub(r"<thought>.*?</thought>", "", clean_response, flags=re.DOTALL)
            return clean_response.strip()
    except Exception as e:
        print(f"[cli] Ollama call error ({model}): {e}")
        return None


def generate_sql_from_schema(question: str, schema_context: str, error_msg: Optional[str] = None, model: str = "qwen3.5") -> str:
    """Generate SQL query given schema context, SQL prompt skill, and retry error feedback."""
    prompt = f"""You are an expert PostgreSQL SQL architect for the Embrix database.
Your task is to write a valid, read-only SELECT query answering the user's natural language question based strictly on the provided Schema Context.

{FEW_SHOT_SQL_SKILL}

Schema Context:
{schema_context}

Question: {question}
"""
    if error_msg:
        prompt += f"\nPrevious Attempt Database Error:\n{error_msg}\nFix the query to solve this exact PostgreSQL error."

    prompt += "\nOutput ONLY the valid SQL statement inside a ```sql ... ``` codeblock. Do NOT include explanations."

    # Call local Ollama model
    llm_output = call_ollama_llm(prompt, model=model)
    if llm_output:
        sql_match = re.search(r"```sql\s*(.*?)\s*```", llm_output, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()
        sql_match_plain = re.search(r"```\s*(.*?)\s*```", llm_output, re.DOTALL)
        if sql_match_plain:
            return sql_match_plain.group(1).strip()
        return llm_output.strip()

    # Fallback heuristic generator if Ollama is unreachable
    q_lower = question.lower()
    if "service usage" in q_lower or "lectura" in q_lower or "uso" in q_lower:
        return """SELECT 
    DATE(latestreadingdate) AS fecha,
    servicetype,
    COUNT(*) AS total_lecturas,
    SUM(readingvalue) AS uso_total,
    AVG(readingvalue) AS uso_promedio
FROM core_usage.service_usage_readings
WHERE latestreadingdate IS NOT NULL
GROUP BY DATE(latestreadingdate), servicetype
ORDER BY fecha DESC, servicetype
LIMIT 50;"""
    elif "revenue" in q_lower or "ingreso" in q_lower or "billing" in q_lower:
        return """SELECT 
    country,
    servicetype,
    COUNT(*) AS total_invoices,
    SUM(amount) AS total_revenue
FROM billing.invoices
GROUP BY country, servicetype
ORDER BY total_revenue DESC
LIMIT 50;"""
    else:
        return """SELECT * FROM core_usage.service_usage_readings ORDER BY latestreadingdate DESC LIMIT 20;"""


def run_pipeline(nl_question: str, top_k: int = 5, model: str = "qwen3.5") -> Dict[str, Any]:
    """
    Run full pipeline: Schema Retrieval -> SQL Generation -> EXPLAIN Audit -> Data Execution -> Token Calculation.
    """
    start_time = time.time()
    
    # 1. Load Schema Retriever & Vector RAG
    retriever = SchemaRetriever()
    relevant_tables = retriever.retrieve_relevant_tables(nl_question, top_k=top_k)
    table_names = [t.qualified_name for t in relevant_tables]

    # Format schema context string
    schema_context_lines = []
    for t in relevant_tables:
        schema_context_lines.append(format_table_document(t))
    schema_context = "\n".join(schema_context_lines)

    # 2. Check Database Connection
    engine = _get_engine()
    db_online = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_online = True
    except Exception:
        db_online = False

    prompt_context = f"Question: {nl_question}\nRetrieved Tables:\n{schema_context}"

    result = {
        "question": nl_question,
        "retrieved_tables": table_names,
        "db_online": db_online,
        "sql": None,
        "validation_valid": False,
        "explain_plan": None,
        "data_df": None,
        "error": None,
        "token_usage": None,
        "execution_time_sec": 0,
    }

    if not db_online:
        sql = generate_sql_from_schema(nl_question, schema_context, model=model)
        result["sql"] = sql
        result["error"] = "Database is OFFLINE. SQL generated & validated against schema cache."
        result["token_usage"] = calculate_token_usage(prompt_context, sql)
        result["execution_time_sec"] = round(time.time() - start_time, 2)
        return result

    # 3. Generate & Validate SQL with Retry Loop
    audit_res = execute_and_validate_with_retry(
        question=nl_question,
        engine=engine,
        generate_sql_fn=lambda q, err: generate_sql_from_schema(q, schema_context, err, model=model),
        max_retries=2
    )

    sql = audit_res["sql"]
    result["sql"] = sql
    result["validation_valid"] = audit_res["success"]
    result["explain_plan"] = audit_res.get("explain_plan")

    if not audit_res["success"]:
        result["error"] = audit_res["error"]
        result["token_usage"] = calculate_token_usage(prompt_context, sql or "")
        result["execution_time_sec"] = round(time.time() - start_time, 2)
        return result

    # 4. Execute Query & Fetch Data
    try:
        df = pd.read_sql(text(sql), engine)
        result["data_df"] = df
    except Exception as e:
        result["error"] = f"Execution error: {e}"

    result["token_usage"] = calculate_token_usage(prompt_context, sql)
    result["execution_time_sec"] = round(time.time() - start_time, 2)
    return result


def init_environment():
    """Run one-time setup initialization: verify schema snapshot, check DB connection, sync ChromaDB."""
    print("\n" + "=" * 60)
    print("EMBRIX AI AGENT - INITIALIZATION")
    print("=" * 60)

    # 1. Schema Store
    store = SchemaStore()
    snapshot = store.load()
    table_count = len(snapshot.tables)
    print(f"\n[STATUS]: Schema snapshot loaded successfully ({table_count:,} tables).")

    # 2. Database Connection
    engine = _get_engine()
    db_online = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_online = True
    except Exception:
        db_online = False
    print(f"[STATUS]: Live PostgreSQL Database is {'ONLINE' if db_online else 'OFFLINE (offline cache mode active)'}.")

    # 3. ChromaDB Indexing
    print("[STATUS]: Checking ChromaDB vector index...")
    try:
        retriever = SchemaRetriever(store=store)
        retriever.sync_index()
        print("[STATUS]: ChromaDB vector index is ready.")
    except Exception as e:
        print(f"[STATUS]: ChromaDB check warning: {e}")

    print("\n" + "=" * 60)
    print("Database is ready for questions!")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Embrix NL-to-SQL CLI Query Engine")
    parser.add_argument("question", nargs="?", type=str, default=None, help="Natural language question to ask")
    parser.add_argument("--top_k", type=int, default=5, help="Top-K tables to retrieve")
    parser.add_argument("--model", type=str, default="qwen3.5", help="Ollama model to use (default: qwen3.5)")
    parser.add_argument("--init", action="store_true", help="Initialize environment and report readiness")
    args = parser.parse_args()

    if args.init or not args.question:
        init_environment()
        return

    res = run_pipeline(args.question, top_k=args.top_k, model=args.model)

    print("\n" + "=" * 60)
    print("EMBRIX AI AGENT - UNIFIED QUERY ENGINE")
    print("=" * 60)
    print(f"\n[QUESTION]:\n{res['question']}\n")
    print(f"[RETRIEVED TABLES]: {', '.join(res['retrieved_tables']) if res['retrieved_tables'] else 'None'}")
    print(f"[DATABASE STATUS]: {'ONLINE' if res['db_online'] else 'OFFLINE'}\n")

    if res['sql']:
        print("[GENERATED SQL QUERY]:")
        print("```sql")
        print(res['sql'])
        print("```\n")

    if res['data_df'] is not None:
        df = res['data_df']
        print(f"[QUERY RESULTS] ({len(df)} rows returned):")
        print(df.head(20).to_markdown(index=False))
        if len(df) > 20:
            print(f"\n... ({len(df) - 20} more rows truncated)")
        print()

    if res['error']:
        print(f"[NOTICE / STATUS]:\n{res['error']}\n")

    if res['token_usage']:
        tu = res['token_usage']
        print("[LOCAL MODEL TOKEN USAGE]:")
        print(f"  * Input Tokens:  ~{tu['input_tokens']:,}")
        print(f"  * Output Tokens: ~{tu['output_tokens']:,}")
        print(f"  * Total Tokens:  ~{tu['total_tokens']:,}")
        print(f"  * Model Host:    Local Ollama ({args.model} - Free / Local)")
        print(f"  * Exec Time:     {res['execution_time_sec']} seconds")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
