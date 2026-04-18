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

def extract_exercises(content):
    """
    Very basic heuristic to split loigiaihay exercises based on ' Câu ' or 'Bài '
    and 'Phương pháp giải:' and 'Lời giải chi tiết:'.
    """
    exercises = []
    # Using regex to split by sections like "Luyện tập 1 Câu 3" or just "Câu 1"
    parts = re.split(r'\n(?=([A-Za-z\s]+ )?(Câu|Bài) \d+)', content)
    
    current_chunk = []
    for part in parts:
        if part is None: continue
        if re.match(r'^([A-Za-z\s]+ )?(Câu|Bài) \d+', part.strip()):
            if current_chunk:
                exercises.append('\n'.join(current_chunk))
            current_chunk = [part]
        else:
            current_chunk.append(part)
    if current_chunk:
        exercises.append('\n'.join(current_chunk))
    
    parsed = []
    for exText in exercises:
        if 'Phương pháp giải' not in exText and 'Lời giải chi tiết' not in exText:
            continue
            
        de_bai = ""
        loi_giai = ""
        
        # Split into De Bai and Loi giai
        try:
            if 'Phương pháp giải:' in exText:
                de_bai, rest = exText.split('Phương pháp giải:', 1)
            elif 'Lời giải chi tiết:' in exText:
                de_bai, rest = exText.split('Lời giải chi tiết:', 1)
            else:
                rest = ""
                
            if 'Lời giải chi tiết:' in exText and 'Phương pháp giải:' in exText:
                _, loi_giai = exText.split('Lời giải chi tiết:', 1)
            else:
                loi_giai = rest
                
            parsed.append({
                "de_bai": de_bai.strip(),
                "loi_giai": loi_giai.strip(),
                "co_hinh": 'Hình ' in de_bai or 'hình vẽ' in de_bai.lower()
            })
        except Exception:
            pass
            
    return parsed

def process_all():
    conn = get_db_conn()
    cur = conn.cursor()
    
    # Process jsonl files
    files = glob.glob('/home/namnx/knowledgeforptalk/rag_edu/data/jsonl/math_loigiaihay_*.jsonl')
    if not files:
        # Check local path for testing
        files = glob.glob('../data/jsonl/math_loigiaihay_*.jsonl')
        
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
                    
                    # 1. Insert extracted_content
                    cur.execute("""
                        INSERT INTO extracted_content (title, clean_text, content_type, grade, subject, book_series, word_count, extra_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        item["title"], item["content"], meta.get("content_type", "math_exercise"),
                        lop, "toan", bo_sach, item["word_count"], json.dumps(meta)
                    ))
                    ext_id = cur.fetchone()[0]
                    total_parsed += 1
                    
                    # 2. Extract exercises
                    content = item["content"]
                    exs = extract_exercises(content)
                    
                    for ex in exs:
                        cur.execute("""
                            INSERT INTO kb_math_exercises (extracted_content_id, lop, bo_sach, de_bai, loi_giai, co_hinh, vector_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            ext_id, lop, bo_sach, ex["de_bai"], ex["loi_giai"], ex["co_hinh"], str(uuid.uuid4())
                        ))
                        total_exercises += 1
                except Exception as e:
                    print(f"Error processing line: {e}")
                    import traceback
                    traceback.print_exc()
                    
    conn.commit()
    print(f"Done! Inserted {total_parsed} articles and extracted {total_exercises} math exercises.")

if __name__ == '__main__':
    process_all()
