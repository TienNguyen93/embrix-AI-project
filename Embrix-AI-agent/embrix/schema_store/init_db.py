"""
embrix.schema_store.init_db
───────────────────────────
Phase 1: Database Setup for pgvector metadata store (embrix_meta).

Stands up an isolated database `embrix_meta` with:
- pgvector extension (vector) & pg_trgm extension
- schema_tables (parent chunk store) with HNSW & GIN indexes
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


DDL_EXTENSIONS = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
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


def run_phase_1_setup():
    """Main runner for Phase 1 Database Setup."""
    logger.info("=== STARTING PHASE 1: DATABASE SETUP (pgvector) ===")
    ensure_meta_database()
    init_pgvector_tables()
    verify_pgvector_setup()
    logger.info("=== PHASE 1 DATABASE SETUP COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    run_phase_1_setup()
