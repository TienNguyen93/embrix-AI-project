"""
embrix.agents.query_auditor
───────────────────────────
Execution-based self-validation for generated SQL queries using EXPLAIN (dry-run)
against the live database. Includes a self-correction retry loop and failure logger.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


_LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "validation_failures.log",
)


@dataclass
class ValidationResult:
    is_valid: bool
    error_message: Optional[str] = None
    explain_plan: Optional[str] = None


@dataclass
class AuditLogEntry:
    timestamp: str
    question: str
    attempted_sql: str
    error_msg: str
    referenced_tables: list[str] = field(default_factory=list)


def log_validation_failure(question: str, sql: str, error_msg: str) -> None:
    """Log validation failure to JSON lines file for Phase 4 reactive drift detection."""
    tables = list(set(re.findall(r'\b([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\b', sql)))

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "attempted_sql": sql,
        "error_msg": error_msg,
        "referenced_tables": tables,
    }

    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[auditor] Warning: Failed to write validation failure log: {e}")


def is_read_only(sql: str) -> bool:
    """Check if query is strictly read-only (SELECT / WITH)."""
    clean_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL).strip()
    
    forbidden = r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b'
    if re.search(forbidden, clean_sql, re.IGNORECASE):
        return False
    return bool(re.match(r'^(WITH|SELECT)\b', clean_sql, re.IGNORECASE))


def validate_query(sql: str, engine: Engine) -> ValidationResult:
    """
    Validate query using EXPLAIN against the live database without executing data mutations.
    """
    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, error_message="Empty SQL query provided.")

    if not is_read_only(sql):
        return ValidationResult(
            is_valid=False,
            error_message="Security Violation: Query contains prohibited DML/DDL statements or non-SELECT keywords."
        )

    clean_sql = sql.strip().rstrip(';')

    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"EXPLAIN {clean_sql}"))
            plan_lines = [str(row[0]) for row in result.fetchall()]
            return ValidationResult(is_valid=True, explain_plan="\n".join(plan_lines))
    except Exception as e:
        error_msg = str(e)
        return ValidationResult(is_valid=False, error_message=error_msg)


def execute_and_validate_with_retry(
    question: str,
    engine: Engine,
    generate_sql_fn: Callable[[str, Optional[str]], str],
    max_retries: int = 2,
) -> dict:
    """
    Run self-correction loop:
    Generates SQL -> EXPLAIN validation -> if failed, feeds exact DB error back to generator.
    """
    last_error = None
    attempted_sqls = []

    for attempt in range(max_retries + 1):
        sql = generate_sql_fn(question, last_error)
        attempted_sqls.append(sql)

        val_result = validate_query(sql, engine)

        if val_result.is_valid:
            return {
                "success": True,
                "sql": sql,
                "attempts": attempt + 1,
                "explain_plan": val_result.explain_plan,
                "error": None,
            }

        last_error = val_result.error_message
        log_validation_failure(question, sql, last_error or "")

    return {
        "success": False,
        "sql": attempted_sqls[-1] if attempted_sqls else "",
        "attempts": max_retries + 1,
        "explain_plan": None,
        "error": f"Failed after {max_retries + 1} attempts. Last database error: {last_error}",
    }


class QueryAuditor:
    """Query Auditor class wrapper."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def validate(self, sql: str) -> ValidationResult:
        return validate_query(sql, self.engine)

    def execute_and_validate_with_retry(
        self,
        initial_sql: str,
        question: str,
        schema_context: str,
        llm_callback: Callable[[str, str], str],
        max_retries: int = 2
    ) -> tuple[ValidationResult, str]:
        current_sql = initial_sql
        for attempt in range(max_retries + 1):
            val_res = self.validate(current_sql)
            if val_res.is_valid:
                return val_res, current_sql

            log_validation_failure(question, current_sql, val_res.error_message or "")
            retry_prompt = f"{question}\n\nPrevious attempted SQL generated an error: {val_res.error_message}. Fix the query."
            current_sql = llm_callback(retry_prompt, schema_context)

        return self.validate(current_sql), current_sql

