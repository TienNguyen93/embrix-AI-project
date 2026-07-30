"""
embrix.schema_store.retrieval
──────────────────────────────
Phase 4: Hybrid RAG Engine.

Features:
1. Dense Vector Search (pgvector / HNSW embeddings with `search_query:` prefix)
2. Sparse Lexical Search (tsvector GIN / keyword matching)
3. Reciprocal Rank Fusion (RRF) to combine dense + sparse scores
4. Parent (Table) / Child (Column) Resolution
5. O(1) Prebuilt Foreign-Key Graph for 1-hop expansion
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Optional, List, Dict, Set, Tuple
from sqlalchemy import text

from embrix.schema_store.models import TableMetadata, SchemaSnapshot
from embrix.schema_store.store import SchemaStore
from embrix.schema_store.enrichment import SchemaEnricher
from embrix.schema_store.chunker import SchemaChunker, ParentChunk, ChildChunk
from embrix.schema_store.init_db import get_meta_engine

logger = logging.getLogger("embrix.schema_store.retrieval")


def get_ollama_query_embedding(text_input: str, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434") -> List[float]:
    """Fetch query vector embedding with required 'search_query:' prefix."""
    prefixed_query = f"search_query: {text_input}"
    payload = json.dumps({"model": model, "prompt": prefixed_query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["embedding"]
    except Exception as e:
        logger.warning(f"Ollama embedding call failed ({e}). Returning zero vector...")
        return [0.0] * 768


class HybridSchemaRetriever:
    """
    Production Hybrid RAG Engine:
    Combines Dense Vector Search + Sparse Lexical Search via Reciprocal Rank Fusion (RRF)
    
    RRF: 
        - combine multiple independent search result rankings into a single, unified list

    """

    def __init__(self, store: Optional[SchemaStore] = None, embedding_model: str = "nomic-embed-text"):
        self.store = store or SchemaStore()
        self.store.load()
        self.embedding_model = embedding_model
        self.engine, self.db_type = get_meta_engine()
        
        # Prebuild Reverse Foreign-Key Index
        self.reverse_fk_map: Dict[str, List[str]] = {}
        self.forward_fk_map: Dict[str, List[str]] = {}
        self._prebuild_fk_graph()

    def _prebuild_fk_graph(self):
        """Prebuild forward and reverse FK maps"""
        all_tables = self.store.get_all_tables()
        for qname, table in all_tables.items():
            self.forward_fk_map[qname] = []
            for fk in table.foreign_keys:
                target_qname = f"{fk.target_schema}.{fk.target_table}"
                self.forward_fk_map[qname].append(target_qname)
                
                if target_qname not in self.reverse_fk_map:
                    self.reverse_fk_map[target_qname] = []
                self.reverse_fk_map[target_qname].append(qname)

    def reciprocal_rank_fusion(
        self, dense_ranks: List[str], sparse_ranks: List[str], k: int = 60
    ) -> List[Tuple[str, float]]:
        """Combine dense and sparse rankings using Reciprocal Rank Fusion (RRF)."""
        rrf_scores: Dict[str, float] = {}

        for rank, table_name in enumerate(dense_ranks):
            rrf_scores[table_name] = rrf_scores.get(table_name, 0.0) + (1.0 / (k + rank + 1))

        for rank, table_name in enumerate(sparse_ranks):
            rrf_scores[table_name] = rrf_scores.get(table_name, 0.0) + (1.0 / (k + rank + 1))

        sorted_results = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
        return sorted_results

    def retrieve_dense(self, query_vector: List[float], top_k: int = 30) -> List[str]:
        """Perform dense vector retrieval against metadata store."""
        results = []
        try:
            with self.engine.connect() as conn:
                if self.db_type == "postgresql":
                    res = conn.execute(
                        text("""
                            SELECT table_name, 1 - (embedding <=> :vec::vector) AS score
                            FROM schema_tables
                            WHERE embedding IS NOT NULL
                            ORDER BY embedding <=> :vec::vector
                            LIMIT :top_k
                        """),
                        {"vec": str(query_vector), "top_k": top_k}
                    ).fetchall()
                    results = [row[0] for row in res]
                else:
                    res = conn.execute(
                        text("SELECT table_name FROM schema_tables LIMIT :top_k"),
                        {"top_k": top_k}
                    ).fetchall()
                    results = [row[0] for row in res]
        except Exception as e:
            logger.warning(f"Dense retrieval query failed ({e}). Returning fallback tables...")
            results = list(self.store.snapshot.tables.keys())[:top_k]

        return results

    def retrieve_sparse(self, nl_query: str, top_k: int = 30) -> List[str]:
        """Perform sparse lexical search against table & column descriptions."""
        results = []
        keywords = [w.lower() for w in nl_query.split() if len(w) > 2 and w.lower() not in {"what", "is", "the", "for", "and", "show", "list", "get", "find"}]
        if not keywords:
            return results

        try:
            with self.engine.connect() as conn:
                if self.db_type == "postgresql":
                    res = conn.execute(
                        text("""
                            SELECT table_name, ts_rank(search_vector, plainto_tsquery(:query)) AS score
                            FROM schema_tables
                            WHERE search_vector IS NOT NULL
                            ORDER BY score DESC
                            LIMIT :top_k
                        """),
                        {"query": nl_query, "top_k": top_k}
                    ).fetchall()
                    results = [row[0] for row in res if row[1] > 0]
                else:
                    # In SQLite mode, rank tables by keyword match count across tables and columns
                    table_scores: Dict[str, float] = {}
                    all_tables = self.store.get_all_tables()
                    for qname, tbl in all_tables.items():
                        score = 0.0
                        table_str = (qname + " " + (tbl.description or "")).lower()
                        cols_str = " ".join([c.name + " " + (c.description or "") for c in tbl.columns]).lower()

                        for kw in keywords:
                            if kw in table_str:
                                score += 2.0
                            if kw in cols_str:
                                score += 1.0

                        if score > 0:
                            table_scores[qname] = score

                    sorted_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)
                    results = [t[0] for t in sorted_tables[:top_k]]
        except Exception as e:
            logger.warning(f"Sparse retrieval failed ({e}). Returning empty list...")
            results = []

        return results




    def retrieve_relevant_tables(
        self, nl_query: str, top_k: int = 5, expand_fk: bool = True
    ) -> List[TableMetadata]:
        """
        Full Hybrid RAG Retrieval Pipeline:
        Dense Vector + Sparse Lexical -> RRF Fusion -> O(1) FK Expansion -> Top-K Tables.
        """
        # 1. Fetch Query Vector
        query_vector = get_ollama_query_embedding(nl_query, model=self.embedding_model)

        # 2. Execute Dense & Sparse Retrieval
        dense_hits = self.retrieve_dense(query_vector, top_k=30)
        sparse_hits = self.retrieve_sparse(nl_query, top_k=30)

        # 3. Apply Reciprocal Rank Fusion (RRF)
        fused_rankings = self.reciprocal_rank_fusion(dense_hits, sparse_hits)
        candidate_qnames = [t[0] for t in fused_rankings[:top_k]]

        # Fallback if no hits returned
        if not candidate_qnames:
            candidate_qnames = list(self.store.snapshot.tables.keys())[:top_k]

        final_qnames = set(candidate_qnames)

        # 4. O(1) Single-Hop Foreign Key Expansion
        if expand_fk:
            for qname in candidate_qnames:
                # Forward FKs (Tables this table points to)
                for target_qname in self.forward_fk_map.get(qname, []):
                    if target_qname in self.store.snapshot.tables:
                        final_qnames.add(target_qname)
                # Reverse FKs (Tables that point to this table)
                for source_qname in self.reverse_fk_map.get(qname, []):
                    if source_qname in self.store.snapshot.tables:
                        final_qnames.add(source_qname)

        # 5. Hydrate TableMetadata Objects
        retrieved_tables = []
        for qname in final_qnames:
            tbl = self.store.get_table(qname)
            if tbl:
                retrieved_tables.append(tbl)

        return retrieved_tables


# Backwards compatibility helpers
SchemaRetriever = HybridSchemaRetriever


def format_table_document(table: TableMetadata) -> str:
    """Format table metadata into a descriptive text chunk for embedding."""
    col_str = ", ".join([f"{c.name} ({c.description or c.data_type})" for c in table.columns])
    fk_str = ", ".join([f"{fk.source_column}->{fk.target_schema}.{fk.target_table}" for fk in table.foreign_keys])
    
    doc = (
        f"Table: {table.qualified_name}\n"
        f"Schema: {table.schema_name}\n"
        f"Name: {table.table_name}\n"
        f"Description: {table.description}\n"
        f"Columns: {col_str}\n"
    )
    if fk_str:
        doc += f"Foreign Keys: {fk_str}\n"
    return doc


