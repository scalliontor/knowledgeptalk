import os
import time
import psycopg2
from src.retrieval.orchestrator import RAGOrchestrator
from src.retrieval.classifier import QueryClassifier
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = "http://localhost:6333"
MODEL_NAME = "intfloat/multilingual-e5-large"
PG_DSN = "postgresql://postgres:postgres@localhost:5433/rag_edu"

def embed_fn(text: str) -> list[float]:
    model = SentenceTransformer(MODEL_NAME, device="cuda")
    return model.encode(text, normalize_embeddings=True).tolist()

def main():
    pg_conn = psycopg2.connect(PG_DSN)
    qdrant = QdrantClient(url=QDRANT_URL)
    classifier = QueryClassifier()
    
    orch = RAGOrchestrator(pg_conn, qdrant, embed_fn, classifier)
    
    queries = [
        ("giải bài 1 trang 14 toán lớp 5", {"lop": 5, "bo_sach_chinh": "KNTT"}),
        ("cách làm bài tập nhân số thập phân với 10", {"lop": 5, "bo_sach_chinh": "KNTT"}),
        ("bài 10 tập 1 toán 5", {"lop": 5, "bo_sach_chinh": "KNTT"}),
    ]
    
    for q, prof in queries:
        print(f"\n=======================")
        print(f"QUERY: {q}")
        ctx, items = orch.retrieve(q, prof)
        print(f"INTENT: {ctx.intent} | SUBJECT: {prof.get('subject_detected')}")
        print(f"RETRIEVED: {len(items)} items")
        for i, it in enumerate(items):
            print(f"  [{i+1}] {it.title} (score: {it.score:.3f})\n  Preview: {it.content[:200]}...")
            print(f"  --")

if __name__ == '__main__':
    main()
