import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "embrix_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
SCHEMA_NAME = os.getenv("SCHEMA_NAME", "core_revenue")

def get_engine(schema_name=SCHEMA_NAME):
    """Returns a SQLAlchemy engine connected to the PostgreSQL database."""
    # Using psycopg2 driver
    connection_string = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string, connect_args={'options': f'-csearch_path={schema_name},public'})
    return engine

_empty_table_cache = {}

def check_empty_tables(engine, schema_name=SCHEMA_NAME):
    """
    Executes a quick COUNT(*) on all tables in the schema.
    Logs a warning message if a table is empty, and logs if it has data.
    Returns a dictionary of table -> row count.
    """
    global _empty_table_cache
    if schema_name in _empty_table_cache:
        return _empty_table_cache[schema_name]

    from sqlalchemy import text
    tables = get_schema_tables(engine, schema=schema_name)
    row_counts = {}
    with engine.connect() as conn:
        for table in tables:
            try:
                result = conn.execute(text(f"SELECT COUNT(1) FROM {schema_name}.{table}")).scalar()
                row_counts[table] = result
                if result == 0:
                    print(f"[!] [Empty] Table {schema_name}.{table} is completely empty.")
                else:
                    print(f"[i] [Has Data: {result} rows] Table {schema_name}.{table}")
            except Exception as e:
                row_counts[table] = -1
    
    _empty_table_cache[schema_name] = row_counts
    return row_counts

def get_all_schemas_and_tables(engine):
    """Returns a dict mapping schema -> list of tables."""
    from sqlalchemy import text
    query = """
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog') 
        ORDER BY table_schema, table_name
    """
    schema_dict = {}
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query)).fetchall()
            for row in result:
                schema = row[0]
                table = row[1]
                if schema not in schema_dict:
                    schema_dict[schema] = []
                schema_dict[schema].append(table)
    except Exception as e:
        print(f"Error fetching schemas: {e}")
    return schema_dict


def get_schema_tables(engine, schema=SCHEMA_NAME):
    """
    Programmatically extracts all table names from the given schema.
    This works independently of IDE GUI limitations by querying metadata directly.
    """
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names(schema=schema)
        return tables
    except Exception as e:
        print(f"Error fetching tables for schema '{schema}': {e}")
        return []

def get_table_columns(engine, table_name, schema=SCHEMA_NAME):
    """
    Extracts column details (name, type) for a specific table in the schema.
    """
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name, schema=schema)
        # return a list of dicts: [{'name': 'id', 'type': INTEGER()}, ...]
        return columns
    except Exception as e:
        print(f"Error fetching columns for table '{table_name}': {e}")
        return []

if __name__ == "__main__":
    # Test the connection and extraction
    print(f"Testing connection to {DB_NAME} on {DB_HOST}...")
    engine = get_engine()
    
    tables = get_schema_tables(engine)
    print(f"\nFound {len(tables)} tables in schema '{SCHEMA_NAME}':")
    for table in tables:
        print(f"- {table}")
        
        # Optionally, print first 3 columns of each table to verify column extraction
        columns = get_table_columns(engine, table)
        col_names = [col['name'] for col in columns[:3]]
        if len(columns) > 3:
            col_names.append("...")
        print(f"  Columns: {', '.join(col_names)}")
