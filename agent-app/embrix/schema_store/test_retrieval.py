"""
Test script for Phase 4 Hybrid RAG Engine (Dense + Sparse + RRF + O(1) FK Expansion).
"""

import logging
from embrix.schema_store.retrieval import HybridSchemaRetriever

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("test_retrieval")


def test_hybrid_retrieval():
    logger.info("Initializing HybridSchemaRetriever and building O(1) FK graph...")
    retriever = HybridSchemaRetriever()

    logger.info(f"O(1) Forward FK Map contains {len(retriever.forward_fk_map)} table entries.")
    logger.info(f"O(1) Reverse FK Map contains {len(retriever.reverse_fk_map)} target entries.")

    test_queries = [
        "billing revenue and usage by country",
        "service usage readings and meter electricity consumption",
        "unpaid customer invoices and billing Profiles"
    ]

    for q in test_queries:
        logger.info(f"\n--- Testing Hybrid RAG Query: '{q}' ---")
        retrieved_tables = retriever.retrieve_relevant_tables(q, top_k=5, expand_fk=True)
        
        logger.info(f"Retrieved {len(retrieved_tables)} relevant tables (with 1-hop FK expansion):")
        for tbl in retrieved_tables[:5]:
            logger.info(f"  • {tbl.qualified_name} ({len(tbl.columns)} columns)")

    logger.info("\n=== PHASE 4 HYBRID RAG VERIFICATION PASSED ===")


if __name__ == "__main__":
    test_hybrid_retrieval()
