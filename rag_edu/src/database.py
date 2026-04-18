import os
import contextlib
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL credentials
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASS = os.getenv("PG_PASS", "postgres")
PG_DB = os.getenv("PG_DB", "rag_edu")

connection_pool = None

def init_db_pool():
    global connection_pool
    if connection_pool is None:
        try:
            connection_pool = SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                host=PG_HOST,
                port=PG_PORT,
                user=PG_USER,
                password=PG_PASS,
                database=PG_DB
            )
            print("PostgreSQL connection pool initialized.")
        except Exception as e:
            # We don't want to crash if db isn't immediately available, but we log
            print(f"Failed to initialize PostreSQL pool: {e}")

@contextlib.contextmanager
def get_db_connection():
    global connection_pool
    if connection_pool is None:
        init_db_pool()
        
    conn = None
    try:
        conn = connection_pool.getconn()
        yield conn
    finally:
        if conn is not None:
            connection_pool.putconn(conn)
