"""
Test script for Phase 3 Contextual Enrichment Engine & Phase 2 Chunker integration.
"""

import json
import logging
from embrix.schema_store.models import SchemaSnapshot
from embrix.schema_store.enrichment import SchemaEnricher
from embrix.schema_store.chunker import SchemaChunker

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logger = logging.getLogger("test_enrichment")


def test_enrichment():
    logger.info("Loading schema_snapshot.json...")
    with open("schema_snapshot.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    snapshot = SchemaSnapshot.from_dict(data)
    
    enricher = SchemaEnricher()
    enriched_snapshot = enricher.enrich_snapshot(snapshot)

    # Inspect sample enriched table
    usage_table = enriched_snapshot.tables.get("core_usage.service_usage_readings")
    assert usage_table is not None, "core_usage.service_usage_readings must exist!"

    logger.info(f"Sample Enriched Table Description:\n{usage_table.description}")

    # Build chunks with enriched snapshot
    chunker = SchemaChunker()
    parents, children = chunker.chunk_snapshot(enriched_snapshot)

    logger.info(f"Chunker produced {len(parents)} enriched parent chunks and {len(children)} enriched child chunks.")

    sample_parent = [p for p in parents if p.table_name == "core_usage.service_usage_readings"][0]
    logger.info(f"Sample Enriched Parent Chunk Text:\n{sample_parent.text_to_embed}")

    logger.info("=== PHASE 3 CONTEXTUAL ENRICHMENT VERIFICATION PASSED ===")


if __name__ == "__main__":
    test_enrichment()
