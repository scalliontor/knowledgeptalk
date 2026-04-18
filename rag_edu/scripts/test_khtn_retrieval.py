import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.retrieval.classifier import QueryClassifier
from src.retrieval.orchestrator import RAGOrchestrator
import psycopg2
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# 1. Connect resources
conn = psycopg2.connect("dbname=rag_edu user=postgres password=postgres host=127.0.0.1 port=5433")
qdrant = QdrantClient(host="127.0.0.1", port=6333)
model = SentenceTransformer('intfloat/multilingual-e5-large', device='cpu')

def embed_fn(text: str):
    return model.encode(f"query: {text}").tolist()

classifier = QueryClassifier()
orchestrator = RAGOrchestrator(conn, qdrant, embed_fn, classifier)

test_cases = [
    # 1. Confusing boundaries between KHTN and Math
    ("tính công thức vận tốc quãng đường thời gian thế nào", {"lop": 8, "bo_sach": "KNTT"}),
    ("áp suất bằng lực chia diện tích phải ko", {"lop": 8}),
    ("1 mol nước nặng bao nhiêu gam", {"lop": 8, "bo_sach": "CD"}),
    ("thể tích hình xilanh đo bằng công thức vật lý nào", {"lop": 9}),
    
    # 2. Confusing boundaries between KHTN, Literature, and History
    ("thuyết tiến hóa của đác un", {"lop": 9}),
    ("ngôi sao nào sáng nhất bầu trời đêm", {"lop": 6}),
    ("phát minh ra điện là ông nào", {"lop": 8}),
    ("kể chuyện về nhà bác học niu tơn", {"lop": 8}),
    
    # 3. Very informal/teen-code KHTN queries
    ("cđg m chả hỉu j về cái pứ hóa học cả giúp vs", {"lop": 8}),
    ("oxi chiếm bn % ko khí zị", {"lop": 6}),
    ("tại sao lá cây lại có màu xanh màu đỏ v", {"lop": 7}),
    ("vi rút viêm gan b có rADN pk k", {"lop": 9}),
    
    # 4. Tricky vague queries
    ("khối lượng riêng là gì", {"lop": 8}),
    ("sao hỏa gọi là sao hỏa", {"lop": 6}),
    ("tác dụng của điện", {"lop": 9}),
    ("phân tử dna", {"lop": 9}),
    
    # 5. Queries with typo
    ("phan ung ho hop te bao", {"lop": 7}),
    ("te bao nahn so va nhan thuwc khacnhau cho nao", {"lop": 6}),
    
    # 6. Social Sciences (History, Geography, Civics) Note: testing cross domain semantic matching!
    ("ai là người đánh đuổi quân nam hán trên sông bạch đằng", {"lop": 6}),
    ("khí hậu việt nam có điểm gì nổi bật", {"lop": 8}),
    ("Quyền trẻ em là gì, nếu tao đánh bạn thì có vi phạm quyền không", {"lop": 6}),
    ("trận điện biên phủ trên không năm nào", {"lop": 9}),
]

print("=== RAG EDU: STRESS TEST KHTN & SOCIAL SCIENCES RETRIEVAL ===")
fail_count = 0
for query, profile in test_cases:
    print(f"\n[QUERY]: {query}")
    print(f"Profile: {profile}")
    ctx, items = orchestrator.retrieve(query, profile)
    print(f"Subject Detected: {profile.get('subject_detected')}")
    print(f"Intent: {ctx.intent.value}")
    
    # Simple fail metrics: subject isn't KHTN (for pure KHTN queries) or 0 items
    is_fail = False
    if profile.get('subject_detected') not in ['khtn', 'toan', 'tieng_viet', 'ngu_van', 'soc']:
         print("  => WARNING: Suspicious subject detected!")
         
    if not items and ctx.intent.value in ["lookup_specific", "explain_concept"]:
        print("  => FAIL: No items found for this query!")
        is_fail = True
        fail_count += 1
    elif items:
        print(f"  => SUCCESS: Found {len(items)} items. Top result: {items[0].title} (Score: {items[0].score:.3f})")
    
print(f"\n=== FINISHED: {fail_count}/{len(test_cases)} failed queries ===")
