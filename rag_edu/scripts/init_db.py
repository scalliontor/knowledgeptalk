import os
import sys
import psycopg2

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.database import PG_HOST, PG_PORT, PG_USER, PG_PASS, PG_DB
from src.qdrant_client_mgr import get_qdrant_client, init_collections

def init_postgres():
    print(f"Connecting to database {PG_DB} at {PG_HOST}:{PG_PORT}...")
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, database=PG_DB
        )
        conn.autocommit = True
        
        schema_path = os.path.join(os.path.dirname(__file__), '..', '..', '2_schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
            
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            
        print("PostgreSQL schema applied successfully.")
        conn.close()
    except psycopg2.OperationalError as e:
        print(f"Warning: Ensure PostgreSQL is running and DB exists. Details: {e}")
    except Exception as e:
        print(f"Error applying postgres schema: {e}")

def init_qdrant():
    print("Connecting to Qdrant...")
    try:
        client = get_qdrant_client()
        init_collections(client)
    except Exception as e:
        print(f"Warning: Ensure Qdrant is running. Details: {e}")

if __name__ == "__main__":
    init_postgres()
    init_qdrant()
