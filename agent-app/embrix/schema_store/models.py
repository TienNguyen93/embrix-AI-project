"""
embrix.schema_store.models
──────────────────────────
Data classes for schema metadata used by the Schema Metadata Store.

TableMetadata  — one table's full column + key inventory.
SchemaSnapshot — the full DB snapshot keyed by schema.table, with versioning.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ColumnMetadata:
    """Metadata for a single database column."""
    name: str
    data_type: str
    nullable: bool = True
    description: str = ""
    sample_values: list[str] = field(default_factory=list)


@dataclass
class ForeignKey:
    """A single foreign-key relationship."""
    source_column: str
    target_schema: str
    target_table: str
    target_column: str


@dataclass
class TableMetadata:
    """Complete metadata for a single database table."""
    schema_name: str
    table_name: str
    description: str = ""
    columns: list[ColumnMetadata] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    row_count: int = 0

    @property
    def qualified_name(self) -> str:
        """Return schema.table qualified name."""
        return f"{self.schema_name}.{self.table_name}"

    # ── Serialization helpers ──────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "description": self.description,
            "columns": [
                {
                    "name": c.name,
                    "data_type": c.data_type,
                    "nullable": c.nullable,
                    "description": c.description,
                    "sample_values": c.sample_values,
                }
                for c in self.columns
            ],
            "primary_key": self.primary_key,
            "foreign_keys": [
                {
                    "source_column": fk.source_column,
                    "target_schema": fk.target_schema,
                    "target_table": fk.target_table,
                    "target_column": fk.target_column,
                }
                for fk in self.foreign_keys
            ],
            "row_count": self.row_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TableMetadata":
        return cls(
            schema_name=d["schema_name"],
            table_name=d["table_name"],
            description=d.get("description", ""),
            columns=[
                ColumnMetadata(
                    name=c["name"],
                    data_type=c["data_type"],
                    nullable=c.get("nullable", True),
                    description=c.get("description", ""),
                    sample_values=c.get("sample_values", []),
                )
                for c in d.get("columns", [])
            ],
            primary_key=d.get("primary_key", []),
            foreign_keys=[
                ForeignKey(
                    source_column=fk["source_column"],
                    target_schema=fk["target_schema"],
                    target_table=fk["target_table"],
                    target_column=fk["target_column"],
                )
                for fk in d.get("foreign_keys", [])
            ],
            row_count=d.get("row_count", 0),
        )


@dataclass
class SchemaSnapshot:
    """
    Complete snapshot of all tables across all target schemas.
    Keyed by qualified name  (e.g. ``core_usage.service_usage_readings``).
    """
    tables: dict[str, TableMetadata] = field(default_factory=dict)
    version_hash: str = ""
    last_synced_at: Optional[str] = None  # ISO-8601 timestamp string

    # ── Serialization helpers ──────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "version_hash": self.version_hash,
            "last_synced_at": self.last_synced_at,
            "tables": {k: v.to_dict() for k, v in self.tables.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SchemaSnapshot":
        tables = {
            k: TableMetadata.from_dict(v)
            for k, v in d.get("tables", {}).items()
        }
        return cls(
            tables=tables,
            version_hash=d.get("version_hash", ""),
            last_synced_at=d.get("last_synced_at"),
        )
