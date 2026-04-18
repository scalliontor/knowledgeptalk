"""
Post-process crawled JSONL → PostgreSQL + Qdrant
Version 2: index ALL content types, no truncation, re-classify unknown
"""
import os
import sys
import json
import re
import uuid
import psycopg2
from qdrant_client.models import PointStruct

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.database import PG_HOST, PG_PORT, PG_USER, PG_PASS, PG_DB
from src.qdrant_client_mgr import get_qdrant_client
from src.embeddings import embed_text, get_embedding_model


def reclassify_content_type(title: str, url: str, current_type: str) -> str:
    """Re-classify content based on title + URL patterns.
    
    Priority order matters! van_ban (full text) checked before soan_van (analysis).
    """
    # Keep explicit non-unknown types, but also re-check for van_ban pattern
    title_lower = title.lower()
    url_lower = url.lower()
    combined = f"{title_lower} {url_lower}"

    # === VĂN BẢN GỐC (full literary text - highest priority) ===
    # URL pattern: /van-ban-...-a{ID}.html  
    # Title pattern: "Văn bản ..." 
    if "van-ban-" in url_lower or title_lower.startswith("văn bản "):
        return "van_ban"
    
    # If already classified as non-unknown, keep it
    if current_type != "unknown":
        return current_type

    # === SOẠN VĂN (THCS: trả lời câu hỏi SGK Ngữ Văn) ===
    if any(kw in combined for kw in ["soạn bài", "soan-bai", "soạn văn", "soan-van"]):
        return "soan_van"
    # === PHÂN TÍCH / NGHỊ LUẬN ===
    if any(kw in combined for kw in ["phân tích", "phan-tich", "nghị luận", "nghi-luan", "cảm nhận", "bình giảng"]):
        return "phan_tich"
    # === TÓM TẮT ===
    if any(kw in combined for kw in ["tóm tắt", "tom-tat", "bố cục", "bo-cuc"]):
        return "tom_tat"
    # === TẬP LÀM VĂN ===
    if any(kw in combined for kw in ["tập làm văn", "tap-lam-van", "viết đoạn", "viết bài", "dàn ý", "văn mẫu", "van-mau"]):
        return "tap_lam_van"
    # === LUYỆN TỪ VÀ CÂU ===
    if any(kw in combined for kw in ["luyện từ và câu", "luyen-tu-va-cau", "luyen-tu-cau", "từ ghép", "từ láy", "danh từ", "động từ", "tính từ", "thực hành tiếng việt", "thuc-hanh-tieng-viet"]):
        return "luyen_tu_va_cau"
    if any(kw in combined for kw in ["chính tả", "chinh-ta"]):
        return "chinh_ta"
    if any(kw in combined for kw in ["kể chuyện", "ke-chuyen"]):
        return "ke_chuyen"
    if any(kw in combined for kw in ["tập đọc", "tap-doc", "bài đọc", "bai-doc", "đọc hiểu"]):
        return "bai_doc"
    if any(kw in combined for kw in ["ôn tập", "on-tap"]):
        return "on_tap"
    if any(kw in combined for kw in ["đề kiểm tra", "đề thi", "de-kiem-tra", "de-thi"]):
        return "de_kiem_tra"
    # If title contains SGK patterns → likely bai_doc
    if any(kw in combined for kw in ["sgk", "sách giáo khoa", "trang"]) and ("lớp" in combined or "lop" in combined):
        return "bai_doc"
    
    return "unknown"


def load_jsonl_to_postgres_and_qdrant(jsonl_path):
    print(f"Loading crawled data from {jsonl_path}...")
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, database=PG_DB)
    q_client = get_qdrant_client()
    get_embedding_model()

    stats = {"raw": 0, "bai_doc": 0, "van_ban": 0, "soan_van": 0, "luyen_tu": 0, "tap_lam_van": 0, "other": 0, "skipped_dup": 0}
    batch_vectors = {"sgk_readings": [], "language_concepts": [], "writing_samples": []}

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            item = json.loads(line)
            meta = item.get("metadata", {})
            
            # Re-classify unknown types
            content_type = reclassify_content_type(item["title"], item["url"], meta.get("content_type", "unknown"))
            grade = meta.get("lop")
            book = meta.get("bo_sach")
            content = item["content"]  # FULL content, no truncation

            with conn.cursor() as cur:
                # 1. Raw Pages
                try:
                    cur.execute("""
                        INSERT INTO raw_pages (url, source_domain, html_content, content_hash, crawled_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (url) DO UPDATE 
                          SET content_hash = EXCLUDED.content_hash, crawled_at = EXCLUDED.crawled_at,
                              crawl_version = raw_pages.crawl_version + 1
                        RETURNING id
                    """, (item["url"], item["source_domain"], content, item["content_hash"], item["crawled_at"]))
                    raw_id = cur.fetchone()[0]
                except Exception as e:
                    print(f"Error inserting raw_pages: {e} - URL: {item.get('url')}")
                    conn.rollback()
                    continue

                # 2. Extracted Content
                try:
                    trang_val = meta.get("trang")
                    # ensure trang is int or None
                    if isinstance(trang_val, str):
                        try: trang_val = int("".join(filter(str.isdigit, trang_val)))
                        except: trang_val = None
                    
                    cur.execute("""
                        INSERT INTO extracted_content (raw_page_id, title, clean_text, content_type, grade, book_series, page_number, word_count, extra_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """, (raw_id, item["title"], content, content_type, grade, book, trang_val, item["word_count"], json.dumps(meta)))
                    ex_id = cur.fetchone()[0]
                except Exception as e:
                    print(f"Error inserting extracted_content: {e} - URL: {item.get('url')}")
                    conn.rollback()
                    continue

                stats["raw"] += 1

                # 3. Route to curated KB tables based on content_type
                # THCS fallback: unknown articles from lớp 6-9 → index as soan_van
                SKIP_TYPES = ("de_kiem_tra", "chinh_ta")
                KB_TYPES = ("van_ban", "bai_doc", "soan_van", "phan_tich", "tom_tat", "on_tap", "ke_chuyen")
                if content_type == "unknown" and grade and grade >= 6:
                    content_type = "soan_van"  # treat unknown THCS as soạn văn
                if content_type in KB_TYPES and grade and content_type not in SKIP_TYPES:
                    vid = str(uuid.uuid4())
                    _book = book or "KNTT"  # default if missing
                    try:
                        cur.execute("""
                            INSERT INTO kb_sgk_reading (extracted_content_id, ten_bai, lop, bo_sach, trang, noi_dung_goc, vector_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                        """, (ex_id, item["title"], grade, _book, trang_val, content, vid))
                        pg_id = cur.fetchone()[0]
                        conn.commit()
                    except psycopg2.IntegrityError:
                        conn.rollback()
                        stats["skipped_dup"] += 1
                        continue
                    except Exception as e:
                        print(f"Error inserting kb_sgk_reading: {e} - URL: {item.get('url')}")
                        conn.rollback()
                        continue

                    vector = embed_text(content[:1500])
                    batch_vectors["sgk_readings"].append(PointStruct(
                        id=str(uuid.uuid4()), vector=vector,
                        payload={"pg_id": pg_id, "lop": grade, "bo_sach": _book, "content_type": content_type}
                    ))
                    if content_type == "van_ban":
                        stats["van_ban"] += 1
                    elif content_type == "soan_van":
                        stats["soan_van"] += 1
                    else:
                        stats["bai_doc"] += 1

                elif content_type == "luyen_tu_va_cau" and grade:
                    vid = str(uuid.uuid4())
                    try:
                        cur.execute("""
                            INSERT INTO kb_language_concepts (extracted_content_id, ten_khai_niem, dinh_nghia, lop_xuat_hien_dau, vector_id)
                            VALUES (%s, %s, %s, %s, %s) RETURNING id
                        """, (ex_id, item["title"], content, grade, vid))
                        pg_id = cur.fetchone()[0]
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        continue

                    vector = embed_text(content[:1500])
                    batch_vectors["language_concepts"].append(PointStruct(
                        id=str(uuid.uuid4()), vector=vector,
                        payload={"pg_id": pg_id, "lop_xuat_hien_dau": grade}
                    ))
                    stats["luyen_tu"] += 1

                elif content_type == "tap_lam_van" and grade:
                    vid = str(uuid.uuid4())
                    try:
                        cur.execute("""
                            INSERT INTO kb_writing_samples (extracted_content_id, dang_bai, lop, noi_dung, word_count, vector_id)
                            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                        """, (ex_id, "tap_lam_van", grade, content, item["word_count"], vid))
                        pg_id = cur.fetchone()[0]
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        continue

                    vector = embed_text(content[:1500])
                    batch_vectors["writing_samples"].append(PointStruct(
                        id=str(uuid.uuid4()), vector=vector,
                        payload={"pg_id": pg_id, "dang_bai": "tap_lam_van", "lop": grade}
                    ))
                    stats["tap_lam_van"] += 1
                else:
                    conn.commit()
                    stats["other"] += 1

                # Batch upsert vectors every 50 items
                for coll, points in batch_vectors.items():
                    if len(points) >= 50:
                        q_client.upsert(coll, points=points)
                        print(f"  Flushed {len(points)} vectors → {coll}")
                        batch_vectors[coll] = []

                if (idx + 1) % 100 == 0:
                    print(f"[{idx+1}] Processed. Stats: {stats}")

    # Final flush
    for coll, points in batch_vectors.items():
        if points:
            q_client.upsert(coll, points=points)
            print(f"  Final flush {len(points)} vectors → {coll}")

    conn.close()
    print(f"\n{'='*50}")
    print(f"Post processing complete!")
    print(f"  Raw pages:        {stats['raw']}")
    print(f"  Văn bản gốc:      {stats['van_ban']}")
    print(f"  Soạn văn:         {stats['soan_van']}")
    print(f"  Bài đọc indexed:  {stats['bai_doc']}")
    print(f"  Ngữ pháp indexed: {stats['luyen_tu']}")
    print(f"  Tập làm văn:      {stats['tap_lam_van']}")
    print(f"  Other (not KB):   {stats['other']}")
    print(f"  Skipped (dup):    {stats['skipped_dup']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        load_jsonl_to_postgres_and_qdrant(sys.argv[1])
    else:
        print("Usage: python3 post_process_crawl.py <path_to_jsonl>")
