import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.retrieval.classifier import QueryClassifier
from src.retrieval.orchestrator import RAGOrchestrator
import psycopg2
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# 1. Connect resources
conn = psycopg2.connect("dbname=rag_edu user=postgres password=postgres host=127.0.0.1 port=5433")
qdrant = QdrantClient(host="127.0.0.1", port=6333)
model = SentenceTransformer('intfloat/multilingual-e5-large', device='cpu')

def embed_fn(text: str):
    return model.encode(f"query: {text}").tolist()

classifier = QueryClassifier()
orchestrator = RAGOrchestrator(conn, qdrant, embed_fn, classifier)

test_cases = [
    ("tao muốn viết dàn ý văn dựa trên công thức tính vận tốc của lý", {"lop": 8}),
    ("nam hán trên sông bạch đằng thì pứ hoá học là j", {"lop": 9}),
    ("tác giả thuý kiều mượn bn tiền mua đt", {"lop": 9}),
    ("cm ho tao 2 tam dac dong dang ma k dug hinh vo", {"lop": 8}),
    ("tao đấm mày thì quyền trẻ e vi pham chổ nao z", {"lop": 6}),
    ("viet bai van ta lai nha nguc thuy chung dia li", {"lop": 6}),
    ("ai thuc hien pp chiet tinh bot trong bai viet", {"lop": 7}),
]

print("=== ADVERSARIAL RESULTS ===")
for query, profile in test_cases:
    ctx, items = orchestrator.retrieve(query, profile)
    print(f"\n[Q]: {query}")
    print(f"-> Detected Subject: {profile.get('subject_detected', 'None')} | Intent: {ctx.intent.value}")
    if items:
        print(f"-> Top Hit: {items[0].title} (Score: {items[0].score:.3f})")
        print(f"-> Content Prep: {items[0].content[:150]}...")
    else:
        print("-> Top Hit: None")
