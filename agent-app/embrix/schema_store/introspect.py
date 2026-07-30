"""
embrix.schema_store.introspect
──────────────────────────────
Live database introspection → SchemaSnapshot.

Queries ``information_schema`` to build a complete SchemaSnapshot
containing every table, column, PK, and FK across the requested schemas.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from embrix.schema_store.models import (
    ColumnMetadata,
    ForeignKey,
    SchemaSnapshot,
    TableMetadata,
)

# Schemas to exclude from introspection
EXCLUDED_SCHEMAS = frozenset({"public", "information_schema", "pg_catalog", "pg_toast"})


def _get_engine(
    host: str | None = None,
    port: str | None = None,
    dbname: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> Engine:
    """Create a plain SQLAlchemy engine, reading defaults from .env."""
    from dotenv import load_dotenv
    load_dotenv()

    host = host or os.environ.get("DB_HOST", "localhost")
    port = port or os.environ.get("DB_PORT", "5432")
    dbname = dbname or os.environ.get("DB_NAME", "embrix_db")
    user = user or os.environ.get("DB_USER", "postgres")
    password = password or os.environ.get("DB_PASSWORD", "password")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(url)


def introspect_schema(
    engine: Engine,
    target_schemas: Optional[list[str]] = None,
    sample_row_limit: int = 3,
) -> SchemaSnapshot:
    """
    Introspect the database and return a complete SchemaSnapshot.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy engine connected to the target Postgres database.
    target_schemas : list[str] | None
        If provided, only introspect these schemas.
        If None, introspect all schemas except EXCLUDED_SCHEMAS.
    sample_row_limit : int
        Number of sample values to fetch per column (for enrichment context).
    """
    tables: dict[str, TableMetadata] = {}
    ddl_parts: list[str] = []  # used to compute version_hash

    with engine.connect() as conn:
        # ── 1. Discover schemas ───────────────────────────────
        if target_schemas:
            schemas = [s for s in target_schemas if s not in EXCLUDED_SCHEMAS]
        else:
            rows = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "ORDER BY schema_name"
                )
            ).fetchall()
            schemas = [r[0] for r in rows if r[0] not in EXCLUDED_SCHEMAS]

        print(f"[introspect] Targeting {len(schemas)} schemas: {schemas}")

        for schema in schemas:
            # ── 2. Tables in this schema ──────────────────────
            tbl_rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name"
                ),
                {"schema": schema},
            ).fetchall()

            for (tbl_name,) in tbl_rows:
                qualified = f"{schema}.{tbl_name}"

                # ── 3. Columns ────────────────────────────────
                col_rows = conn.execute(
                    text(
                        "SELECT column_name, data_type, is_nullable "
                        "FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = :table "
                        "ORDER BY ordinal_position"
                    ),
                    {"schema": schema, "table": tbl_name},
                ).fetchall()

                columns: list[ColumnMetadata] = []
                for col_name, data_type, is_nullable in col_rows:
                    columns.append(
                        ColumnMetadata(
                            name=col_name,
                            data_type=data_type,
                            nullable=(is_nullable == "YES"),
                        )
                    )
                    ddl_parts.append(f"{qualified}.{col_name}:{data_type}")

                # ── 4. Primary key ────────────────────────────
                pk_rows = conn.execute(
                    text(
                        """
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                          ON tc.constraint_name = kcu.constraint_name
                         AND tc.table_schema = kcu.table_schema
                        WHERE tc.table_schema = :schema
                          AND tc.table_name = :table
                          AND tc.constraint_type = 'PRIMARY KEY'
                        ORDER BY kcu.ordinal_position
                        """
                    ),
                    {"schema": schema, "table": tbl_name},
                ).fetchall()
                primary_key = [r[0] for r in pk_rows]

                # ── 5. Foreign keys ───────────────────────────
                fk_rows = conn.execute(
                    text(
                        """
                        SELECT
                            kcu.column_name        AS source_column,
                            ccu.table_schema       AS target_schema,
                            ccu.table_name         AS target_table,
                            ccu.column_name        AS target_column
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                          ON tc.constraint_name = kcu.constraint_name
                         AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage ccu
                          ON tc.constraint_name = ccu.constraint_name
                         AND tc.table_schema = ccu.table_schema
                        WHERE tc.table_schema = :schema
                          AND tc.table_name = :table
                          AND tc.constraint_type = 'FOREIGN KEY'
                        """
                    ),
                    {"schema": schema, "table": tbl_name},
                ).fetchall()

                foreign_keys = [
                    ForeignKey(
                        source_column=r[0],
                        target_schema=r[1],
                        target_table=r[2],
                        target_column=r[3],
                    )
                    for r in fk_rows
                ]

                # ── 6. Row count (cheap estimate) ─────────────
                try:
                    row_count = conn.execute(
                        text(f"SELECT COUNT(1) FROM {schema}.{tbl_name}")
                    ).scalar()
                except Exception:
                    row_count = 0

                # ── 7. Sample values ──────────────────────────
                if row_count > 0 and sample_row_limit > 0:
                    try:
                        sample_rows = conn.execute(
                            text(
                                f"SELECT * FROM {schema}.{tbl_name} "
                                f"LIMIT :lim"
                            ),
                            {"lim": sample_row_limit},
                        ).fetchall()
                        # Get column names from the result set
                        col_names = [c.name for c in columns]
                        for i, col in enumerate(columns):
                            vals = []
                            for row in sample_rows:
                                val = row[i] if i < len(row) else None
                                if val is not None:
                                    vals.append(str(val)[:100])  # truncate long values
                            col.sample_values = vals
                    except Exception:
                        pass  # sample values are best-effort

                tables[qualified] = TableMetadata(
                    schema_name=schema,
                    table_name=tbl_name,
                    columns=columns,
                    primary_key=primary_key,
                    foreign_keys=foreign_keys,
                    row_count=row_count,
                )

        print(f"[introspect] Found {len(tables)} tables across {len(schemas)} schemas")

    # ── Version hash ──────────────────────────────────────────
    ddl_str = "\n".join(sorted(ddl_parts))
    version_hash = hashlib.sha256(ddl_str.encode()).hexdigest()

    return SchemaSnapshot(
        tables=tables,
        version_hash=version_hash,
        last_synced_at=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    engine = _get_engine()
    snapshot = introspect_schema(engine)
    print(f"\nSnapshot version hash: {snapshot.version_hash}")
    print(f"Synced at: {snapshot.last_synced_at}")
    print(f"Total tables: {len(snapshot.tables)}")
    for qname, tbl in sorted(snapshot.tables.items()):
        print(f"  {qname}: {len(tbl.columns)} cols, {tbl.row_count} rows, {len(tbl.foreign_keys)} FKs")
