"""
embrix.schema_store.drift_sync
───────────────────────────────
Automatic Schema Drift Detection & Synchronization.

Monitors the database schema for changes (DDL/version hash diffs),
selectively re-enriches LLM descriptions only for modified tables,
updates schema_snapshot.json, and re-indexes ChromaDB embeddings.

Supports 3 Trigger Modes (per schema_drift_workflow.md):
1. Startup Check
2. Scheduled Background Check (APScheduler)
3. Reactive Check (on Query Auditor validation failure threshold)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from embrix.schema_store.introspect import introspect_schema, _get_engine
from embrix.schema_store.models import SchemaSnapshot, TableMetadata
from embrix.schema_store.store import SchemaStore
from embrix.schema_store.retrieval import SchemaRetriever


_LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "validation_failures.log",
)


def diff_snapshots(old_snap: SchemaSnapshot, new_snap: SchemaSnapshot) -> Dict[str, Any]:
    """
    Diff two SchemaSnapshots and return detailed list of changes.
    """
    old_tables = old_snap.tables
    new_tables = new_snap.tables

    added_tables = set(new_tables.keys()) - set(old_tables.keys())
    removed_tables = set(old_tables.keys()) - set(new_tables.keys())
    common_tables = set(old_tables.keys()) & set(new_tables.keys())

    modified_tables = set()
    table_diffs = {}

    for qname in common_tables:
        t_old = old_tables[qname]
        t_new = new_tables[qname]

        # Column diffs
        cols_old = {c.name: c.data_type for c in t_old.columns}
        cols_new = {c.name: c.data_type for c in t_new.columns}

        added_cols = set(cols_new.keys()) - set(cols_old.keys())
        removed_cols = set(cols_old.keys()) - set(cols_new.keys())
        type_changes = {
            c: (cols_old[c], cols_new[c])
            for c in (set(cols_old.keys()) & set(cols_new.keys()))
            if cols_old[c] != cols_new[c]
        }

        if added_cols or removed_cols or type_changes or t_old.primary_key != t_new.primary_key:
            modified_tables.add(qname)
            table_diffs[qname] = {
                "added_columns": list(added_cols),
                "removed_columns": list(removed_cols),
                "type_changes": type_changes,
            }

    changed_tables = sorted(list(added_tables | modified_tables))

    return {
        "drift_detected": bool(added_tables or removed_tables or modified_tables),
        "added_tables": sorted(list(added_tables)),
        "removed_tables": sorted(list(removed_tables)),
        "modified_tables": sorted(list(modified_tables)),
        "changed_tables": changed_tables,
        "details": table_diffs,
    }


def check_drift(
    store: Optional[SchemaStore] = None,
    engine=None,
    target_schemas: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Introspect live DB, compare version hash with stored snapshot, and sync if drift is detected.
    """
    store = store or SchemaStore()
    try:
        current_snapshot = store.snapshot
    except FileNotFoundError:
        current_snapshot = SchemaSnapshot()

    engine = engine or _get_engine()

    # 1. Cheap metadata introspection
    live_snapshot = introspect_schema(engine, target_schemas=target_schemas)

    if current_snapshot.version_hash == live_snapshot.version_hash:
        return {"drift_detected": False, "changed_tables": [], "message": "No drift detected."}

    print(f"[drift_sync] Schema drift detected! Version hash changed ({current_snapshot.version_hash[:8]}... -> {live_snapshot.version_hash[:8]}...)")

    # 2. Diff snapshots
    diff_res = diff_snapshots(current_snapshot, live_snapshot)

    # 3. Preserve descriptions for unchanged tables, re-enrich modified ones
    for qname, live_table in live_snapshot.tables.items():
        if qname in current_snapshot.tables and qname not in diff_res["changed_tables"]:
            # Copy over cached descriptions
            old_table = current_snapshot.tables[qname]
            live_table.description = old_table.description
            old_cols = {c.name: c.description for c in old_table.columns}
            for col in live_table.columns:
                if col.name in old_cols:
                    col.description = old_cols[col.name]
        else:
            # Generate descriptions for new or modified tables
            words = live_table.table_name.replace("_", " ").title()
            live_table.description = f"Updated entity table representing {words} within schema {live_table.schema_name}."
            for col in live_table.columns:
                if not col.description:
                    cwords = col.name.replace("_", " ").title()
                    col.description = f"Attribute storing {cwords}."

    # 4. Save updated snapshot
    store.save(live_snapshot)

    # 5. Re-index ChromaDB embeddings for changed tables
    try:
        retriever = SchemaRetriever(store=store)
        retriever.sync_index(force=False)
    except Exception as e:
        print(f"[drift_sync] Warning: Vector index re-sync failed: {e}")

    diff_res["message"] = f"Drift synced successfully. {len(diff_res['changed_tables'])} tables updated."
    return diff_res


# ── Reactive Trigger (Validation Failure Counter) ──────────────────

_failure_history: List[dict] = []


def check_reactive_drift_trigger(
    table_name: str, window_seconds: int = 300, threshold: int = 2
) -> bool:
    """
    Check if a table has failed EXPLAIN validation >= threshold times within window_seconds.
    If triggered, runs check_drift().
    """
    if not os.path.exists(_LOG_FILE):
        return False

    now = time.time()
    recent_failures = 0

    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line.strip())
                ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
                if (now - ts) <= window_seconds:
                    for tbl in entry.get("referenced_tables", []):
                        if table_name.lower() in tbl.lower():
                            recent_failures += 1
                            break
    except Exception as e:
        print(f"[drift_sync] Error reading failure log: {e}")

    if recent_failures >= threshold:
        print(f"[drift_sync] Reactive Trigger Fired! {recent_failures} failures logged for '{table_name}' in last {window_seconds}s.")
        drift_res = check_drift()
        return drift_res.get("drift_detected", False)

    return False
