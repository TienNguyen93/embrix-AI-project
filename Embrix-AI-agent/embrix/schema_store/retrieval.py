"""
embrix.schema_store.retrieval
──────────────────────────────
Targeted schema retrieval using vector search (ChromaDB + nomic-embed-text)
and single-hop Foreign Key expansion with concurrent indexing.
"""

from __future__ import annotations

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List

from embrix.schema_store.models import TableMetadata, SchemaSnapshot
from embrix.schema_store.store import SchemaStore


_CHROMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "chroma_db",
)


def get_ollama_embedding(text_input: str, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434") -> List[float]:
    """Fetch vector embedding from Ollama API."""
    payload = json.dumps({"model": model, "prompt": text_input}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res["embedding"]


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


class SchemaRetriever:
    """Vector index and targeted retrieval for schema metadata."""

    def __init__(self, store: Optional[SchemaStore] = None, embedding_model: str = "nomic-embed-text"):
        self.store = store or SchemaStore()
        self.store.load()
        self.embedding_model = embedding_model
        self._collection = None

    def _init_chroma(self):
        import chromadb
        client = chromadb.PersistentClient(path=_CHROMA_DIR)
        self._collection = client.get_or_create_collection(name="schema_metadata")

    def sync_index(self, force: bool = False, max_workers: int = 16):
        """Index or update table embeddings in ChromaDB concurrently."""
        if self._collection is None:
            self._init_chroma()

        snapshot = self.store.snapshot
        existing_ids = set(self._collection.get()["ids"]) if not force else set()

        tables_to_index = []
        for qname, table in snapshot.tables.items():
            if force or qname not in existing_ids:
                tables_to_index.append(table)

        if not tables_to_index:
            print("[retrieval] Vector index is up to date.")
            return

        print(f"[retrieval] Concurrently indexing {len(tables_to_index)} tables into ChromaDB (workers={max_workers})...")
        
        indexed_data = []

        def _embed_single(tbl: TableMetadata):
            doc_text = format_table_document(tbl)
            emb = get_ollama_embedding(doc_text, model=self.embedding_model)
            return (
                tbl.qualified_name,
                doc_text,
                emb,
                {"schema": tbl.schema_name, "table": tbl.table_name}
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_table = {executor.submit(_embed_single, tbl): tbl for tbl in tables_to_index}
            for future in as_completed(future_to_table):
                tbl = future_to_table[future]
                try:
                    res = future.result()
                    indexed_data.append(res)
                except Exception as e:
                    print(f"  [!] Embedding failed for {tbl.qualified_name}: {e}")

        if indexed_data:
            ids = [item[0] for item in indexed_data]
            documents = [item[1] for item in indexed_data]
            embeddings = [item[2] for item in indexed_data]
            metadatas = [item[3] for item in indexed_data]

            # Upsert in batches of 200
            batch_size = 200
            for i in range(0, len(ids), batch_size):
                self._collection.upsert(
                    ids=ids[i:i+batch_size],
                    documents=documents[i:i+batch_size],
                    embeddings=embeddings[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
            print(f"[retrieval] Successfully indexed {len(ids)} tables into ChromaDB.")

    def retrieve_relevant_tables(
        self, nl_query: str, top_k: int = 5, expand_fk: bool = True
    ) -> List[TableMetadata]:
        """
        Retrieve relevant tables for a natural language query using vector search
        plus 1-hop foreign key expansion.
        """
        if self._collection is None:
            self._init_chroma()

        # 1. Embed query
        query_emb = get_ollama_embedding(nl_query, model=self.embedding_model)

        # 2. Vector search
        results = self._collection.query(
            query_embeddings=[query_emb],
            n_results=min(top_k, self._collection.count())
        )

        retrieved_qnames = set()
        if results and results.get("ids") and results["ids"][0]:
            retrieved_qnames.update(results["ids"][0])

        # 3. Single-hop FK expansion
        if expand_fk:
            fk_expanded = set()
            all_tables = self.store.get_all_tables()
            
            for qname in retrieved_qnames:
                tbl = all_tables.get(qname)
                if not tbl:
                    continue
                # Source -> Target FKs
                for fk in tbl.foreign_keys:
                    target_qname = f"{fk.target_schema}.{fk.target_table}"
                    if target_qname in all_tables:
                        fk_expanded.add(target_qname)

            # Target <- Source FKs (reverse lookup)
            for other_qname, other_tbl in all_tables.items():
                for fk in other_tbl.foreign_keys:
                    target_qname = f"{fk.target_schema}.{fk.target_table}"
                    if target_qname in retrieved_qnames:
                        fk_expanded.add(other_qname)

            retrieved_qnames.update(fk_expanded)

        # 4. Fetch TableMetadata objects
        table_list = []
        for qname in retrieved_qnames:
            tbl = self.store.get_table(qname)
            if tbl:
                table_list.append(tbl)

        return table_list
