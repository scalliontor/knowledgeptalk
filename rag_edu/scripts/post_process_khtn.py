import json
import glob
import os
import psycopg2
import uuid
import re
from dotenv import load_dotenv

load_dotenv()

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5433"),
        database=os.getenv("PG_DB", "rag_edu"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASS", "postgres"),
    )

def setup_db(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kb_khtn_exercises (
            id SERIAL PRIMARY KEY,
            extracted_content_id INTEGER REFERENCES extracted_content(id) ON DELETE CASCADE,
            lop INTEGER,
            bo_sach VARCHAR(50),
            de_bai TEXT,
            loi_giai TEXT,
            co_hinh BOOLEAN DEFAULT false,
            vector_id VARCHAR(50) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

def extract_exercises(content):
    """
    Split KHTN content into exercises using CH/Câu and Lời giải.
    """
    parsed = []
    
    # KHTN uses ** CH1**, ** Câu 1**, **Phương pháp giải:**, **Lời giải chi tiết:**
    # Split blocks if there are multiple CH/Câu
    blocks = re.split(r'\n\s*\*\*\s*(?:CH|Câu|Bài)\s*\d+\s*\*\*', content)
    if len(blocks) == 1:
        blocks = [content]
        
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        # Determine split keyword
        split_kw = ""
        if '**Lời giải chi tiết:**' in block:
            split_kw = '**Lời giải chi tiết:**'
        elif '**Lời giải:**' in block:
            split_kw = '**Lời giải:**'
        elif '**Trả lời:**' in block:
            split_kw = '**Trả lời:**'
        elif 'Lời giải chi tiết:' in block:
            split_kw = 'Lời giải chi tiết:'
        elif 'Lời giải:' in block:
            split_kw = 'Lời giải:'
            
        if not split_kw:
            # Fallback if no explicit solution keyword is found
            continue
            
        de_bai, loi_giai = block.split(split_kw, 1)
        
        # Clean up de_bai (remove Phương pháp giải)
        for ppg in ['**Phương pháp giải:**', 'Phương pháp giải:']:
            if ppg in de_bai:
                de_bai, _ = de_bai.split(ppg, 1)
                
        # Clean up markdown asterisks
        de_bai = de_bai.replace('**', '').strip()
        loi_giai = loi_giai.replace('**', '').strip()
        
        # Ignore junk solutions
        if len(loi_giai) < 10:
            continue
            
        parsed.append({
            "de_bai": de_bai,
            "loi_giai": loi_giai,
            "co_hinh": 'hình ' in de_bai.lower() or 'sơ đồ' in de_bai.lower() or 'quan sát' in de_bai.lower()
        })
            
    return parsed

def process_all():
    conn = get_db_conn()
    cur = conn.cursor()
    setup_db(cur)
    conn.commit()
    
    files = glob.glob('/home/namnx/knowledgeforptalk/rag_edu/data/jsonl/khtn_loigiaihay_*.jsonl')
    
    print(f"Found {len(files)} JSONL files to process")
    total_parsed = 0
    total_exercises = 0
    
    for f in files:
        with open(f, 'r') as fp:
            for line in fp:
                try:
                    item = json.loads(line)
                    meta = item.get("metadata", {})
                    lop = meta.get("lop")
                    bo_sach = meta.get("bo_sach")
                    if not lop or not bo_sach: continue
                    
                    # Insert extracted_content
                    cur.execute("""
                        INSERT INTO extracted_content (title, clean_text, content_type, grade, subject, book_series, word_count, extra_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        item["title"], item["content"], "khtn_lesson",
                        lop, "khtn", bo_sach, item["word_count"], json.dumps(meta)
                    ))
                    ext_id = cur.fetchone()[0]
                    total_parsed += 1
                    
                    # Extract exercises
                    content = item["content"]
                    exs = extract_exercises(content)
                    
                    for ex in exs:
                        cur.execute("""
                            INSERT INTO kb_khtn_exercises (extracted_content_id, lop, bo_sach, de_bai, loi_giai, co_hinh, vector_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            ext_id, lop, bo_sach, ex["de_bai"], ex["loi_giai"], ex["co_hinh"], str(uuid.uuid4())
                        ))
                        total_exercises += 1
                except Exception as e:
                    pass
                    #print(f"Error processing line: {e}")
                    
    conn.commit()
    print(f"Done! Inserted {total_parsed} KHTN articles and extracted {total_exercises} KHTN exercises.")

if __name__ == '__main__':
    process_all()
