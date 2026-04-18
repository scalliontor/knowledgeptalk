import os
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

print(f"Loading embedding model: {MODEL_NAME}...")
try:
    # Set up lazy loading to avoid memory overhead until needed
    model = None
except Exception as e:
    print(f"Warning: could not initialize embedding model properly. {e}")
    model = None

def get_embedding_model():
    global model
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    return model

def embed_text(text: str) -> list[float]:
    """Generates embedding for a single string."""
    m = get_embedding_model()
    prefix = "query: " if MODEL_NAME.startswith("intfloat/multilingual-e5") else ""
    return m.encode(f"{prefix}{text}").tolist()

def embed_documents(texts: list[str]) -> list[list[float]]:
    """Generates embeddings for multiple documents."""
    m = get_embedding_model()
    prefix = "passage: " if MODEL_NAME.startswith("intfloat/multilingual-e5") else ""
    formatted_texts = [f"{prefix}{t}" for t in texts]
    return m.encode(formatted_texts).tolist()
