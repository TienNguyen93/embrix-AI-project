"""
embrix.schema_store.store
─────────────────────────
Persistence layer for the SchemaSnapshot.

Saves to / loads from a local JSON file (``schema_snapshot.json``).
Exposes simple accessors: ``get_table()``, ``get_all_tables()``,
``get_tables_in_schema()``, and ``get_version_hash()``.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from embrix.schema_store.models import SchemaSnapshot, TableMetadata

# Default location — project root
_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "schema_snapshot.json",
)


class SchemaStore:
    """In-memory + file-backed schema metadata store."""

    def __init__(self, snapshot_path: str = _DEFAULT_PATH):
        self._path = snapshot_path
        self._snapshot: Optional[SchemaSnapshot] = None

    # ── Load / Save ───────────────────────────────────────────

    def load(self) -> SchemaSnapshot:
        """Load the snapshot from the JSON file into memory."""
        if not os.path.exists(self._path):
            raise FileNotFoundError(
                f"Schema snapshot not found at {self._path}. "
                "Run introspection first."
            )
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._snapshot = SchemaSnapshot.from_dict(data)
        print(
            f"[store] Loaded snapshot: {len(self._snapshot.tables)} tables, "
            f"hash={self._snapshot.version_hash[:12]}…"
        )
        return self._snapshot

    def save(self, snapshot: SchemaSnapshot) -> None:
        """Persist the snapshot to the JSON file and update in-memory copy."""
        self._snapshot = snapshot
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, indent=2, default=str)
        print(
            f"[store] Saved snapshot: {len(snapshot.tables)} tables -> {self._path}"
        )

    def save_if_loaded(self) -> None:
        """Save the current in-memory snapshot (no-op if nothing loaded)."""
        if self._snapshot:
            self.save(self._snapshot)

    # ── Accessors (all from memory — no DB hit) ───────────────

    @property
    def snapshot(self) -> SchemaSnapshot:
        if self._snapshot is None:
            self.load()
        return self._snapshot  # type: ignore[return-value]

    def get_table(self, qualified_name: str) -> Optional[TableMetadata]:
        """Get a single table by qualified name (e.g. 'core_usage.service_usage_readings')."""
        return self.snapshot.tables.get(qualified_name)

    def get_all_tables(self) -> dict[str, TableMetadata]:
        """Return every table across all schemas."""
        return self.snapshot.tables

    def get_tables_in_schema(self, schema_name: str) -> list[TableMetadata]:
        """Return all tables belonging to a specific schema."""
        return [
            t for t in self.snapshot.tables.values()
            if t.schema_name == schema_name
        ]

    def get_version_hash(self) -> str:
        """Return the version hash of the current snapshot."""
        return self.snapshot.version_hash

    def get_all_schema_names(self) -> list[str]:
        """Return a sorted list of all unique schema names in the snapshot."""
        return sorted({t.schema_name for t in self.snapshot.tables.values()})

    def get_table_names(self, schema_name: Optional[str] = None) -> list[str]:
        """Return all qualified table names, optionally filtered by schema."""
        if schema_name:
            return sorted(
                k for k, v in self.snapshot.tables.items()
                if v.schema_name == schema_name
            )
        return sorted(self.snapshot.tables.keys())

    # ── Update helpers (used by drift_sync) ───────────────────

    def update_table(self, table: TableMetadata) -> None:
        """Insert or replace a single table in the snapshot (in-memory only — call save() after)."""
        self.snapshot.tables[table.qualified_name] = table

    def remove_table(self, qualified_name: str) -> bool:
        """Remove a table from the snapshot. Returns True if it existed."""
        return self.snapshot.tables.pop(qualified_name, None) is not None
