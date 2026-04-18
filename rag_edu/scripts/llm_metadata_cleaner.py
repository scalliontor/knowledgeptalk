import os
import json
import psycopg2
from litellm import completion
from dotenv import load_dotenv

# Load môi trường
load_dotenv("/home/namnx/knowledgeforptalk/rag_edu/.env")
LLM_MODEL = "openai/gemma-4"

def llm_fix_metadata(title: str, content: str) -> dict:
    prompt = f"""Bạn là một chuyên gia về chương trình sách giáo khoa mới (CTST, KNTT, CD) và chương trình cũ 2006.
Dựa vào tiêu đề và nội dung bài học dưới đây, hãy xác định nó thuộc Lớp mấy và Bộ sách nào (CTST, KNTT, CD, 2006).

Tiêu đề: {title}
Nội dung trích đoạn: {content[:300]}...

Trả về JSON nghiêm ngặt:
{{
    "lop": <số 1-12>,
    "bo_sach": "<CTST, KNTT, CD, hoặc 2006>"
}}
"""
    try:
        response = completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=15
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return None

def main():
    conn = psycopg2.connect(host='localhost', port=5433, dbname='rag_edu', user='postgres', password='postgres')
    cur = conn.cursor()
    
    # Lọc 1000 bài chưa được gắn chuẩn CTST / CD (vẫn dính KNTT do tool crawl lỗi)
    cur.execute("SELECT id, ten_bai, noi_dung_goc FROM kb_sgk_reading WHERE lop = 9 AND bo_sach = 'KNTT' AND ten_bai NOT ILIKE '%Kết nối tri thức%' LIMIT 5;")
    rows = cur.fetchall()
    
    print(f"Bắt đầu quy trình dùng LLM quét tự động {len(rows)} bản ghi lỗi...")
    for r in rows:
        r_id, title, content = r
        print(f"\\nĐang phân tích ID {r_id}: {title}")
        res = llm_fix_metadata(title, content)
        if res:
            print(f"--> LLM phán đoán: Lớp {res.get('lop')} - Bộ {res.get('bo_sach')}")
            # cur.execute("UPDATE kb_sgk_reading SET lop=%s, bo_sach=%s WHERE id=%s", (res.get('lop'), res.get('bo_sach'), r_id))
            # conn.commit()

if __name__ == "__main__":
    main()
