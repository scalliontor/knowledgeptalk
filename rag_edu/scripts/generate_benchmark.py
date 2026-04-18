import sys
import os
import json
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from litellm import completion
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from litellm import completion

PG_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/rag_edu"
conn = psycopg2.connect(PG_DSN)

def generate_query(content, context_type, grade):
    """Giả lập học sinh hỏi dựa trên context_type (VD: KHTN, Sử, Toán)"""
    prompt = f"""Bạn đóng vai một học sinh lớp {grade}. Bạn đang có một nội dung kiến thức trong SGK như sau:
-------------------
{content[:800]}
-------------------
Hãy ĐẶT 1 CÂU HỎI vô cùng tự nhiên, ngắn gọn bằng tiếng Việt (có thể viết tắt, không dấu, hoặc hơi teen-code đôi chút) mang tính chất THẮC MẮC về phần Đề bài / Nội dung / Khái niệm trên.
YÊU CẦU:
- NGẮN GỌN dưới 20 từ.
- KHÔNG lộ các từ khóa quá hàn lâm, dùng cách hỏi của trẻ em/học sinh.
- TRẢ VỀ DUY NHẤT câu hỏi, không có phần giải thích, không bọc trong ngoặc kép.
"""
    try:
        response = completion(
            model="openai/gemma-4",
            api_key="gemma4-openclaw-2026",
            api_base="http://171.226.10.121:8000/llm/v1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip().strip('"')
    except Exception as e:
        print("LLM Error:", e)
        return None

benchmarks = []

# ========================
# 1. KHTN
# ========================
print("Sampling 30 KHTN queries...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("SELECT * FROM kb_khtn_exercises ORDER BY RANDOM() LIMIT 30")
    for row in cur.fetchall():
        q = generate_query(row['de_bai'], 'KHTN', row['lop'])
        if q:
            benchmarks.append({
                "id": str(row['id']),
                "query": q,
                "target_table": "kb_khtn_exercises",
                "subject": "khtn",
                "grade": row['lop'],
                "book_series": row['bo_sach']
            })

# ========================
# 2. Xã Hội (Sử, Địa, GDCD)
# ========================
print("Sampling 30 Social Science queries...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("SELECT * FROM kb_social_exercises ORDER BY RANDOM() LIMIT 30")
    for row in cur.fetchall():
        q = generate_query(row['de_bai'], 'Khoa học Xã hội', row['lop'])
        if q:
            benchmarks.append({
                "id": str(row['id']),
                "query": q,
                "target_table": "kb_social_exercises",
                "subject": "soc", # could be lich_su, dia_li, gdcd
                "grade": row['lop'],
                "book_series": row['bo_sach']
            })

# ========================
# 3. Toán
# ========================
print("Sampling 30 Math queries...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("SELECT * FROM kb_math_exercises ORDER BY RANDOM() LIMIT 30")
    for row in cur.fetchall():
        q = generate_query(row['de_bai'], 'Toán', row['lop'])
        if q:
            benchmarks.append({
                "id": str(row['id']),
                "query": q,
                "target_table": "kb_math_exercises",
                "subject": "toan",
                "grade": row['lop'],
                "book_series": row['bo_sach']
            })

# ========================
# 4. Ngữ Văn (Đọc)
# ========================
print("Sampling 30 Literature queries...")
with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute("SELECT * FROM kb_sgk_reading ORDER BY RANDOM() LIMIT 30")
    for row in cur.fetchall():
        q = generate_query(row.get('noi_dung_goc', row['ten_bai']), 'Ngữ văn', row['lop'])
        if q:
            benchmarks.append({
                "id": str(row['id']),
                "query": q,
                "target_table": "kb_sgk_reading",
                "subject": "ngu_van",
                "grade": row['lop'],
                "book_series": row['bo_sach']
            })

# ========================
# 5. Adversarial / Cross-Subject
# ========================
adversarial = [
    {"query": "tao muốn viết dàn ý văn dựa trên công thức tính vận tốc của lý", "subject": "cross", "grade": 8},
    {"query": "nam hán trên sông bạch đằng thì pứ hoá học là j", "subject": "cross", "grade": 9},
    {"query": "tác giả thuý kiều mượn bn tiền mua đt", "subject": "cross", "grade": 9},
    {"query": "sao hỏa gọi là sao hỏa z mài", "subject": "khtn", "grade": 6},
    {"query": "dkiet li là tg nao the ??", "subject": "ngu_van", "grade": 7},
    {"query": "cm ho tao 2 tam dac dong dang ma k dug hinh vo", "subject": "toan", "grade": 8},
    {"query": "tao đấm mày thì quyền trẻ e vi pham chổ nao z", "subject": "soc", "grade": 6},
    {"query": "phan ung oxi hoa cua the ki 19 lsu la gi", "subject": "cross", "grade": 8},
    {"query": "viet bai van ta lai nha nguc thuy chung dia li", "subject": "cross", "grade": 6},
    {"query": "ai thuc hien pp chiet tinh bot trong bai viet", "subject": "khtn", "grade": 7}
]

for ad in adversarial:
     benchmarks.append({
        "id": "NONE",
        "query": ad["query"],
        "target_table": "ANY",
        "subject": ad["subject"],
        "grade": ad["grade"],
        "book_series": "ANY"
     })

with open("scripts/benchmark_set.json", "w", encoding="utf-8") as f:
    json.dump(benchmarks, f, ensure_ascii=False, indent=2)

print(f"Generated {len(benchmarks)} queries into scripts/benchmark_set.json")
