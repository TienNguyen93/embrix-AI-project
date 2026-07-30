"""
embrix.schema_store.init_db
───────────────────────────
Phase 1: Database Setup for pgvector metadata store (embrix_meta).

Builds schema_tables & schema_columns metadata storage 
(pgvector HNSW vector index + tsvector text search GIN index) 
with SQLite fallback

Stands up an isolated database `embrix_meta` with:
- pgvector extension (vector) & pg_trgm extension
- schema_tables (parent chunk store) with HNSW & GIN indexes
    - HNSW: Hierarchical Navigable Small World
    - GIN indexes:
- schema_columns (child chunk store for wide tables) with HNSW & GIN indexes
"""

import os
import sys
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("embrix.schema_store.init_db")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
META_DB_NAME = os.getenv("META_DB_NAME", "embrix_meta")

# Connection string for admin (default postgres db) to create embrix_meta
ADMIN_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/postgres"
# Connection string for embrix_meta
META_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{META_DB_NAME}"


"""
Run standard Data Definition Language (DDL) CREATE EXTENSION commands
to enable:
    - pg_trgm extension (for fuzzy text/lexical matching) 
        - calculates similarity of text based on trigram matching
        - Useful for keyword typo tolerance, autocomplete, and wildcards
    - pgvector extension (for high-dimensional vector/semantic search)
        - vector data type for machine learning embeddings
        - Useful for nearest-neighbor similarity searches (cosine, L2, or inner product distance).
in PostgreSQL databases
"""
DDL_EXTENSIONS = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
"""

"""
Create a catalog table to track high-level database tables and their structural metadata
- table_name TEXT PRIMARY KEY: Defines the name of the database table as a unique identifier; acts as the primary key
- schema_name TEXT NOT NULL: Tracks which database schema (e.g., public, sales, staging) the table belongs to
- description TEXT: Stores documentation, natural language comments, or AI-generated summaries about what data the table holds
- column_count INT: Keeps a count of total columns in that table for quick analytical filtering
- last_synced_at TIMESTAMPTZ DEFAULT now(): Automatically records the timestamp when this catalog entry was created or last updated, using timezone-aware formatting
- version_hash TEXT: Stores a hash of the table's structural state to easily detect if the table structure has changed since the last sync
- search_vector tsvector: Special PostgreSQL type for Full-Text Search; stores tokenized, lexically normalized words from the table name and description to handle quick keyword queries
- embedding vector(768): pgvector column storing a 768-dimensional ML embedding from selected embedding mode; allows for semantic searching (e.g., finding the table even if the user types a synonym instead of the exact name)
"""
DDL_SCHEMA_TABLES = """
CREATE TABLE IF NOT EXISTS schema_tables (
    table_name TEXT PRIMARY KEY,
    schema_name TEXT NOT NULL,
    description TEXT,
    column_count INT,
    last_synced_at TIMESTAMPTZ DEFAULT now(),
    version_hash TEXT,
    search_vector tsvector,
    embedding vector(768)
);
"""

"""
Create a granular tracking table for individual columns within the tables defined above
- id SERIAL PRIMARY KEY: auto-incrementing integer identifier unique to every single column metadata record
- table_name TEXT REFERENCES schema_tables(table_name) ON DELETE CASCADE: Foreign Key linking this column to its parent table. 
    ON DELETE CASCADE ensures that if a table is removed from schema_tables, all its associated columns are automatically deleted
- column_name TEXT NOT NULL: exact name of the column in the target database
- data_type TEXT: structural type of the column (e.g., VARCHAR, INTEGER, TIMESTAMP)
- is_nullable BOOLEAN: Tracks whether the column allows NULL values
- is_primary_key BOOLEAN DEFAULT FALSE: A flag identifying if this specific column serves as the primary identifier for its host table
- fk_target_table & fk_target_column: Optional fields that explicitly track foreign key relationships, documenting how tables map to each other for easy relational graphing
- sample_values TEXT[]: An array of text strings storing example data points to help an LLM or data analyst understand what real entries look like
- contextual_description TEXT: AI-generated or developer-written notes describing the exact business context of the column's data
- search_vector tsvector & embedding vector(768): Work identically to the ones in schema_tables, enabling both keyword-based and semantic/AI-based searching at the individual column level
"""
DDL_SCHEMA_COLUMNS = """
CREATE TABLE IF NOT EXISTS schema_columns (
    id SERIAL PRIMARY KEY,
    table_name TEXT REFERENCES schema_tables(table_name) ON DELETE CASCADE,
    column_name TEXT NOT NULL,
    data_type TEXT,
    is_nullable BOOLEAN,
    is_primary_key BOOLEAN DEFAULT FALSE,
    fk_target_table TEXT,
    fk_target_column TEXT,
    sample_values TEXT[],
    contextual_description TEXT,
    search_vector tsvector,
    embedding vector(768)
);
"""

"""
- hnsw (... vector_cosine_ops) (Tables & Columns): 
    - Builds an Hierarchical Navigable Small World (HNSW) index on the AI vector fields; 
    - Provides lightning-fast, approximate nearest-neighbor (ANN) searches using Cosine Distance. 
    - Ensures semantic AI queries scale efficiently even with millions of rows.
- gin (search_vector) (Tables & Columns): 
    - Builds a Generalized Inverted Index (GIN) optimized for PostgreSQL Full-Text Search
    - Enables instantaneous, index-backed keyword queries using matches like @@ to_tsquery()
- idx_schema_columns_table_name: 
    - Standard B-Tree index on the foreign key column
    - Ensures that lookups joining tables to columns or filtering for all columns belonging to a specific table happen instantly
"""
DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_schema_tables_embedding ON schema_tables USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_schema_columns_embedding ON schema_columns USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_schema_tables_search_vector ON schema_tables USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_schema_columns_search_vector ON schema_columns USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_schema_columns_table_name ON schema_columns (table_name);
"""


def get_meta_engine():
    """Returns an engine for embrix_meta database, or fallback SQLite engine if embrix_meta database cannot be created."""
    try:
        engine = create_engine(META_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine, "postgresql"
    except Exception:
        # Fallback to local SQLite metadata database
        sqlite_url = "sqlite:///embrix_meta.db"
        logger.info("Using local SQLite metadata store (embrix_meta.db)...")
        return create_engine(sqlite_url), "sqlite"


def ensure_meta_database():
    """Ensure the embrix_meta database exists on PostgreSQL or use fallback."""
    logger.info(f"Connecting to admin DB at {DB_HOST}:{DB_PORT} to verify '{META_DB_NAME}'...")
    try:
        admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": META_DB_NAME}
            ).fetchone()
            
            if not result:
                logger.info(f"Database '{META_DB_NAME}' does not exist. Attempting creation...")
                try:
                    conn.execute(text(f'CREATE DATABASE "{META_DB_NAME}"'))
                    logger.info(f"Database '{META_DB_NAME}' created successfully.")
                except Exception as ddl_err:
                    logger.warning(f"Could not create database '{META_DB_NAME}' (likely read-only user): {ddl_err}")
            else:
                logger.info(f"Database '{META_DB_NAME}' exists.")
    except Exception as e:
        logger.warning(f"Could not connect to PostgreSQL admin database: {e}")


def init_pgvector_tables():
    """Enable extensions, create schema_tables and schema_columns, and build HNSW/GIN indexes."""
    logger.info(f"Initializing schema tables...")
    engine, db_type = get_meta_engine()
    
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            if db_type == "postgresql":
                logger.info("Enabling pgvector and pg_trgm extensions if permitted...")
                try:
                    conn.execute(text(DDL_EXTENSIONS))
                except Exception as ext_err:
                    logger.warning(f"Extension creation skipped: {ext_err}")
                
                conn.execute(text(DDL_SCHEMA_TABLES))
                conn.execute(text(DDL_SCHEMA_COLUMNS))
                
                try:
                    conn.execute(text(DDL_INDEXES))
                except Exception as idx_err:
                    logger.warning(f"Vector index creation skipped: {idx_err}")
            else:
                # SQLite Fallback Schema
                logger.info("Creating SQLite fallback metadata schema...")
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS schema_tables (
                        table_name TEXT PRIMARY KEY,
                        schema_name TEXT NOT NULL,
                        description TEXT,
                        column_count INT,
                        last_synced_at TEXT,
                        version_hash TEXT,
                        search_vector TEXT,
                        embedding TEXT
                    );
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS schema_columns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        table_name TEXT,
                        column_name TEXT NOT NULL,
                        data_type TEXT,
                        is_nullable BOOLEAN,
                        is_primary_key BOOLEAN DEFAULT 0,
                        fk_target_table TEXT,
                        fk_target_column TEXT,
                        sample_values TEXT,
                        contextual_description TEXT,
                        search_vector TEXT,
                        embedding TEXT
                    );
                """))
            
            trans.commit()
            logger.info(f"Database schema initialized successfully ({db_type}).")
            return engine, db_type
        except Exception as e:
            trans.rollback()
            logger.error(f"Failed to initialize metadata schema: {e}")
            raise e


def verify_pgvector_setup():
    """Run a test INSERT and distance calculation round-trip."""
    logger.info("Verifying metadata store round-trip query...")
    meta_engine, db_type = get_meta_engine()
    dummy_vector = [0.1] * 768
    
    with meta_engine.connect() as conn:
        trans = conn.begin()
        try:
            # Upsert dummy test row
            conn.execute(
                text("""
                    INSERT INTO schema_tables (table_name, schema_name, description, column_count, embedding)
                    VALUES (:table_name, :schema_name, :description, :column_count, :embedding)
                    ON CONFLICT (table_name) DO UPDATE SET description = EXCLUDED.description
                """),
                {
                    "table_name": "test_schema.test_table",
                    "schema_name": "test_schema",
                    "description": "Test table verification row for metadata setup",
                    "column_count": 1,
                    "embedding": str(dummy_vector)
                }
            )
            
            # Query verification row
            res = conn.execute(
                text("SELECT table_name FROM schema_tables WHERE table_name = 'test_schema.test_table'")
            ).fetchone()
            
            # Clean up dummy row
            conn.execute(text("DELETE FROM schema_tables WHERE table_name = 'test_schema.test_table'"))
            trans.commit()
            
            if res and res[0] == "test_schema.test_table":
                logger.info(f"Metadata store verification SUCCESS! ({db_type})")
                return True
            else:
                logger.error("Verification query returned unexpected result.")
                return False
        except Exception as e:
            trans.rollback()
            logger.error(f"Verification failed: {e}")
            raise e


def seed_metadata_from_snapshot():
    """Seed schema_tables with enriched descriptions from schema_snapshot.json."""
    engine, db_type = get_meta_engine()
    try:
        import json
        from embrix.schema_store.enrichment import SchemaEnricher
        from embrix.schema_store.models import SchemaSnapshot

        with open("schema_snapshot.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        snapshot = SchemaSnapshot.from_dict(data)
        enricher = SchemaEnricher()
        enriched_snapshot = enricher.enrich_snapshot(snapshot)

        with engine.connect() as conn:
            # Clear old backup/dummy rows if present
            conn.execute(text("DELETE FROM schema_tables WHERE table_name LIKE 'core_backup.%' OR table_name = 'test_schema.test_table'"))
            conn.commit()

            # Check existing production count
            res = conn.execute(text("SELECT COUNT(*) FROM schema_tables")).scalar() or 0
            if res > 100:
                logger.info(f"Metadata store already contains {res} production table entries.")
                return

            logger.info(f"Seeding {len(enriched_snapshot.tables)} enriched tables into metadata store...")
            for qname, tbl in enriched_snapshot.tables.items():
                if db_type == "postgresql":
                    conn.execute(
                        text("""
                            INSERT INTO schema_tables (table_name, schema_name, description, column_count)
                            VALUES (:name, :schema, :desc, :cnt)
                            ON CONFLICT (table_name) DO NOTHING
                        """),
                        {"name": qname, "schema": tbl.schema_name, "desc": tbl.description, "cnt": len(tbl.columns)}
                    )
                else:
                    conn.execute(
                        text("""
                            INSERT OR REPLACE INTO schema_tables (table_name, schema_name, description, column_count)
                            VALUES (:name, :schema, :desc, :cnt)
                        """),
                        {"name": qname, "schema": tbl.schema_name, "desc": tbl.description, "cnt": len(tbl.columns)}
                    )
            conn.commit()
            logger.info("Metadata store seeding completed.")

    except Exception as e:
        logger.warning(f"Metadata store seeding notice: {e}")


def run_phase_1_setup():
    """Main runner for Phase 1 Database Setup."""
    logger.info("=== STARTING PHASE 1: DATABASE SETUP (pgvector) ===")
    ensure_meta_database()
    init_pgvector_tables()
    verify_pgvector_setup()
    seed_metadata_from_snapshot()
    logger.info("=== PHASE 1 DATABASE SETUP COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    run_phase_1_setup()

