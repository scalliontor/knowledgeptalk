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
    'Ai là tác giả của bài thơ Đồng chí và bài thơ được sáng tác trong hoàn cảnh nào?',
    'Đọc cho em nghe bài thơ Đoàn thuyền đánh cá của Huy Cận lớp 9 với ạ',
    'Phong cách nghệ thuật của Nguyễn Du thể hiện qua Truyện Kiều lớp 9 như thế nào?',
    'Cho em xin thông tin về nhân vật Vũ Nương trong Chuyện người con gái Nam Xương lớp 9',
    'Tóm tắt bài Làng của Kim Lân lớp 9'
]

# Lack of context test: no specific grade in the prompt, let user_profile decide or ambiguous
profiles = [
    {'lop': 9}, 
    {'lop': 9}, 
    {'lop': 9}, 
    {'lop': 9}, 
    {'lop': 9}  
]

for idx, q in enumerate(queries):
    up = profiles[idx]
    print(f'\n📝 Query: {q}  |  Profile: Lớp {up.get("lop", "None")}')
    ctx, items = orchestrator.retrieve(q, up)
    
    print(f'Subject Detected: {up.get("subject_detected")}')
    print(f'Intent: {ctx.intent.value}')
    print(f'Retrieved {len(items)} items:')
    for item_idx, item in enumerate(items, 1):
        print(f'   [{item_idx}] Source: {item.source} | Score: {item.score:.4f} | Title: {item.title}')
        # Just print first 150 chars, replace newlines with space to make it compact
        content = item.content[:150].replace('\n', ' ')
        print(f'       Content preview: {content}...')
    
    print('--------------------------------------------------')

print('Test completed!')
