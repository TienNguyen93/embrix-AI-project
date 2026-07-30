#!/usr/bin/env python3
"""
scripts/enrich_schema_descriptions.py
──────────────────────────────────────
One-time (or per-drift) LLM enrichment pass.

Reads the raw ``schema_snapshot.json``, sends each table's column list to
an LLM, asks for a one-sentence description per table and per column,
caches results back into the JSON file.

Only processes tables whose ``description`` field is empty — safe to re-run
after drift detection adds new tables without re-enriching unchanged ones.

Usage:
    python scripts/enrich_schema_descriptions.py [--force]
        --force   re-enrich ALL tables, not just empty-description ones.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from embrix.schema_store.store import SchemaStore
from embrix.schema_store.models import TableMetadata


def _build_prompt(table: TableMetadata) -> str:
    """Build a prompt asking the LLM to describe a table and its columns."""
    col_lines = []
    for c in table.columns:
        nullable = "nullable" if c.nullable else "not null"
        samples = ", ".join(c.sample_values[:3]) if c.sample_values else "no samples"
        col_lines.append(f"  - {c.name} ({c.data_type}, {nullable}) — samples: [{samples}]")

    fk_lines = []
    for fk in table.foreign_keys:
        fk_lines.append(f"  - {fk.source_column} → {fk.target_schema}.{fk.target_table}.{fk.target_column}")

    columns_block = "\n".join(col_lines)
    fk_block = "\n".join(fk_lines) if fk_lines else "  (none)"

    return f"""You are a database documentation assistant. Given the following PostgreSQL table metadata, provide:
1. A concise one-sentence description of what this table stores/represents.
2. A concise one-phrase description for each column explaining its business meaning.

Table: {table.schema_name}.{table.table_name}
Row count: {table.row_count}
Primary key: {', '.join(table.primary_key) if table.primary_key else '(none)'}

Columns:
{columns_block}

Foreign keys:
{fk_block}

Respond ONLY in this exact JSON format — no markdown, no explanation:
{{
  "table_description": "...",
  "column_descriptions": {{
    "column_name": "description",
    ...
  }}
}}"""


def _call_llm(prompt: str, model: str = "qwen3:8b", base_url: str = "http://localhost:11434") -> str:
    """Call Ollama's chat completion endpoint."""
    import urllib.request

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())

    return data.get("message", {}).get("content", "")


def _parse_llm_response(raw: str) -> dict:
    """Extract JSON from the LLM response, tolerating markdown wrappers and <think> tags."""
    import re

    # Strip <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

    # Try to find JSON block
    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    raise ValueError(f"Could not extract JSON from LLM response:\n{raw[:500]}")


def enrich_snapshot(store: SchemaStore, force: bool = False, model: str = "qwen3:8b") -> int:
    """
    Enrich table/column descriptions via LLM.

    Returns the number of tables enriched.
    """
    snapshot = store.snapshot
    enriched_count = 0
    total = len(snapshot.tables)

    for idx, (qname, table) in enumerate(sorted(snapshot.tables.items()), 1):
        # Skip tables that already have descriptions (unless --force)
        if table.description and not force:
            continue

        print(f"[enrich] ({idx}/{total}) Enriching {qname}...")

        prompt = _build_prompt(table)

        try:
            raw = _call_llm(prompt, model=model)
            result = _parse_llm_response(raw)

            # Apply table description
            table.description = result.get("table_description", "")

            # Apply column descriptions
            col_descs = result.get("column_descriptions", {})
            for col in table.columns:
                if col.name in col_descs:
                    col.description = col_descs[col.name]

            enriched_count += 1

            # Throttle to avoid overwhelming Ollama
            time.sleep(0.5)

        except Exception as e:
            print(f"  [!] Failed to enrich {qname}: {e}")
            continue

    # Save updated snapshot
    if enriched_count > 0:
        store.save(snapshot)
        print(f"\n[enrich] Done — enriched {enriched_count}/{total} tables.")
    else:
        print(f"\n[enrich] No tables needed enrichment (all already have descriptions).")

    return enriched_count


def main():
    parser = argparse.ArgumentParser(description="Enrich schema descriptions via LLM")
    parser.add_argument("--force", action="store_true", help="Re-enrich all tables")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model name (default: qwen3:8b)")
    args = parser.parse_args()

    store = SchemaStore()
    store.load()
    enrich_snapshot(store, force=args.force, model=args.model)


if __name__ == "__main__":
    main()
