import os
from sqlalchemy import text, create_engine
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "embrix_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

def init_memory_schema():
    connection_string = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    # Explicitly set read_only=off for this DDL session
    engine = create_engine(connection_string, connect_args={'options': '-c default_transaction_read_only=off'})
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS app_meta;"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app_meta.sessions (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                title VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app_meta.messages (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR REFERENCES app_meta.sessions(id) ON DELETE CASCADE,
                role VARCHAR,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app_meta.turn_context (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR REFERENCES app_meta.sessions(id) ON DELETE CASCADE,
                message_id VARCHAR REFERENCES app_meta.messages(id) ON DELETE CASCADE,
                sql_used TEXT,
                result_schema TEXT,
                result_summary TEXT,
                chart_spec TEXT
            );
        """))
        print("Memory schema app_meta initialized successfully.")

if __name__ == "__main__":
    init_memory_schema()
