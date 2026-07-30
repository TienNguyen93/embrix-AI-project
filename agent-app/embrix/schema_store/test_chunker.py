"""
Test script for Phase 2 SchemaChunker module.
"""

import json
import logging
from embrix.schema_store.models import SchemaSnapshot
from embrix.schema_store.chunker import SchemaChunker

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("test_chunker")


def test_chunking():
    logger.info("Loading schema_snapshot.json...")
    with open("schema_snapshot.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    snapshot = SchemaSnapshot.from_dict(data)
    logger.info(f"Loaded snapshot with {len(snapshot.tables)} tables.")

    chunker = SchemaChunker(wide_threshold=30)
    parents, children = chunker.chunk_snapshot(snapshot)

    logger.info(f"Generated {len(parents)} Parent Chunks (Tables).")
    logger.info(f"Generated {len(children)} Child Chunks (Columns from wide tables >30 cols).")

    assert len(parents) == len(snapshot.tables), "Parent chunk count must match table count!"
    
    # Inspect sample parent chunk
    sample_parent = parents[0]
    logger.info(f"Sample Parent Chunk ({sample_parent.table_name}):\n{sample_parent.text_to_embed[:200]}...")

    if children:
        sample_child = children[0]
        logger.info(f"Sample Child Chunk ({sample_child.table_name}.{sample_child.column_name}):\n{sample_child.text_to_embed[:200]}...")

    logger.info("=== PHASE 2 CHUNKER VERIFICATION PASSED ===")


if __name__ == "__main__":
    test_chunking()
