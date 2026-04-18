import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from dotenv import load_dotenv

load_dotenv()

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# Embeddings dimension (e.g., 1024 for bge-m3 or e5-large)
EMBEDDING_DIM = 1024

def get_qdrant_client():
    # Provide local memory/file option for testing if QDRANT_HOST is "memory"
    if QDRANT_HOST == "memory":
        return QdrantClient(":memory:")
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def init_collections(client: QdrantClient):
    """
    Initialize required collections if they don't exist.
    """
    collections = [
        "sgk_readings",
        "language_concepts",
        "writing_outlines",
        "writing_samples"
    ]
    
    existing = [c.name for c in client.get_collections().collections]
    
    for coll in collections:
        if coll not in existing:
            client.create_collection(
                collection_name=coll,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
            )
            print(f"Created Qdrant collection: {coll}")
        else:
            print(f"Qdrant collection {coll} already exists.")
