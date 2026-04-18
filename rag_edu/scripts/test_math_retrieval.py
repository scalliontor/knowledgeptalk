import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from src.retrieval.orchestrator import RAGOrchestrator
from src.retrieval.classifier import QueryClassifier

PG_DSN = 'postgresql://postgres:postgres@localhost:5433/rag_edu'
QDRANT_URL = 'http://localhost:6333'
MODEL_NAME = 'intfloat/multilingual-e5-large'

print('Loading models and DB...')
model = SentenceTransformer(MODEL_NAME, device='cuda')
def embed_fn(text: str):
    return model.encode('query: ' + text, normalize_embeddings=True).tolist()

pg_conn = psycopg2.connect(PG_DSN)
qdrant = QdrantClient(url=QDRANT_URL)
classifier = QueryClassifier()

orchestrator = RAGOrchestrator(pg_conn, qdrant, embed_fn, classifier)

queries = [
    'Chị ơi tính diện tích hình tròn có bán kính 5cm tính sao zợ, mệt qá',
    'đổi 8 mét vuông 15 đề xi mét vuông ra đề xi mét kiểu gì, em hong hiểu :(',
    'bà ơi bài 2 trang 113 toán lớp 5 sách cánh diều em giải mãi hong ra cứu bé',
    '3 + 4 nhân 5 bằng mấy hả chị, em chia nhầm nãy giờ'
]

user_profile = {'lop': 5, 'tuan_hien_tai': 20, 'bo_sach': 'CD'}

for q in queries:
    print(f'\n📝 Query: {q}')
    ctx, items = orchestrator.retrieve(q, user_profile)
    print(f'Subject Detected: {user_profile.get("subject_detected")}')
    print(f'Intent: {ctx.intent.value}')
    print(f'Retrieved {len(items)} items:')
    for idx, item in enumerate(items, 1):
        print(f'   [{idx}] Score: {item.score:.4f} | Title: {item.title}')
        print(f'       Content preview: {item.content[:200]}...')
    
    print('--------------------------------------------------')

print('Test completed!')
