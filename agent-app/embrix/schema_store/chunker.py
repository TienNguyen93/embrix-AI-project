"""
embrix.schema_store.chunker
───────────────────────────
Phase 2: Parent (Table) + Child (Column) Chunking Strategy.

Generates structured parent chunks for all tables and child chunks for wide
tables (>30 columns) to ensure high precision in RAG retrieval.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from embrix.schema_store.models import TableMetadata, ColumnMetadata, SchemaSnapshot


@dataclass
class ParentChunk:
    """Parent chunk representing a full database table."""
    table_name: str
    schema_name: str
    description: str
    column_count: int
    text_to_embed: str
    version_hash: str = ""


@dataclass
class ChildChunk:
    """Child chunk representing a single column within a wide table (>30 columns)."""
    table_name: str
    column_name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    fk_target_table: Optional[str]
    fk_target_column: Optional[str]
    sample_values: List[str]
    text_to_embed: str


class SchemaChunker:
    """
    Chunking engine that processes SchemaSnapshot metadata into:
    1. Parent Chunks: One parent chunk per table (all 1,013 tables).
    2. Child Chunks: One child chunk per column for wide tables (> wide_threshold columns aka 30).
    """

    def __init__(self, wide_threshold: int = 30):
        self.wide_threshold = wide_threshold

    def build_parent_chunk(self, table: TableMetadata) -> ParentChunk:
        """Construct parent chunk text representation for vector & lexical search."""
        pk_str = ", ".join(table.primary_key) if table.primary_key else "None"
        fk_list = [
            f"{fk.source_column} -> {fk.target_schema}.{fk.target_table}({fk.target_column})"
            for fk in table.foreign_keys
        ]
        fk_str = "; ".join(fk_list) if fk_list else "None"

        cols_summary = ", ".join([f"{c.name} ({c.data_type})" for c in table.columns[:15]])
        if len(table.columns) > 15:
            cols_summary += f" ... (+{len(table.columns) - 15} more columns)"

        text_to_embed = (
            f"search_document: Table: {table.qualified_name}\n"
            f"Schema: {table.schema_name}\n"
            f"Description: {table.description}\n"
            f"Primary Key: {pk_str}\n"
            f"Foreign Keys: {fk_str}\n"
            f"Columns: {cols_summary}"
        )

        return ParentChunk(
            table_name=table.qualified_name,
            schema_name=table.schema_name,
            description=table.description,
            column_count=len(table.columns),
            text_to_embed=text_to_embed
        )

    def build_child_chunks(self, table: TableMetadata) -> List[ChildChunk]:
        """Construct column child chunks if table width > wide_threshold."""
        if len(table.columns) <= self.wide_threshold:
            return []

        child_chunks = []
        pk_set = set(table.primary_key)
        fk_map = {fk.source_column: fk for fk in table.foreign_keys}

        for col in table.columns:
            is_pk = col.name in pk_set
            fk_info = fk_map.get(col.name)
            fk_target_table = f"{fk_info.target_schema}.{fk_info.target_table}" if fk_info else None
            fk_target_column = fk_info.target_column if fk_info else None

            fk_str = f"Foreign Key -> {fk_target_table}.{fk_target_column}" if fk_info else ""
            samples_str = ", ".join([str(v) for v in col.sample_values[:3]]) if col.sample_values else "N/A"

            text_to_embed = (
                f"search_document: Column: {col.name} ({col.data_type})\n"
                f"Table: {table.qualified_name}\n"
                f"Context: {col.description}\n"
                f"PK: {is_pk} | {fk_str}\n"
                f"Sample Values: {samples_str}"
            )

            child_chunks.append(
                ChildChunk(
                    table_name=table.qualified_name,
                    column_name=col.name,
                    data_type=col.data_type,
                    is_nullable=col.nullable,
                    is_primary_key=is_pk,
                    fk_target_table=fk_target_table,
                    fk_target_column=fk_target_column,
                    sample_values=col.sample_values,
                    text_to_embed=text_to_embed
                )
            )

        return child_chunks

    def chunk_snapshot(self, snapshot: SchemaSnapshot) -> Tuple[List[ParentChunk], List[ChildChunk]]:
        """Process an entire SchemaSnapshot into Parent and Child chunks."""
        parents = []
        children = []

        for qualified_name, table_meta in snapshot.tables.items():
            parent = self.build_parent_chunk(table_meta)
            parents.append(parent)

            if len(table_meta.columns) > self.wide_threshold:
                table_children = self.build_child_chunks(table_meta)
                children.extend(table_children)

        return parents, children
