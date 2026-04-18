import os
import sys
import uuid
import psycopg2
from qdrant_client.models import PointStruct

# Add src to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.database import PG_HOST, PG_PORT, PG_USER, PG_PASS, PG_DB
from src.qdrant_client_mgr import get_qdrant_client
from src.embeddings import embed_text, get_embedding_model

def insert_dummy_data():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, database=PG_DB)
    conn.autocommit = True
    q_client = get_qdrant_client()
    get_embedding_model() # Pre-load

    # 1. BÀI ĐỌC SGK
    sgk_data = [
        {
            "ten_bai": "Lượm",
            "tac_gia": "Tố Hữu",
            "lop": 2,
            "bo_sach": "KNTT",
            "tuan": 5,
            "noi_dung_goc": "Chú bé loắt choắt... Lượm là em bé liên lạc dũng cảm.",
        }
    ]
    
    with conn.cursor() as cur:
        for d in sgk_data:
            vid = str(uuid.uuid4())
            try:
                cur.execute("""
                    INSERT INTO extracted_content(title, clean_text, content_type) 
                    VALUES (%s, %s, 'bai_doc') RETURNING id
                """, (d["ten_bai"], d["noi_dung_goc"]))
                ex_id = cur.fetchone()[0]

                cur.execute("""
                    INSERT INTO kb_sgk_reading (extracted_content_id, ten_bai, tac_gia, lop, bo_sach, tuan, noi_dung_goc, vector_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (ex_id, d["ten_bai"], d["tac_gia"], d["lop"], d["bo_sach"], d["tuan"], d["noi_dung_goc"], vid))
                pg_id = cur.fetchone()[0]
                
                # Insert to Qdrant
                vector = embed_text(d["noi_dung_goc"])
                q_client.upsert(
                    collection_name="sgk_readings",
                    points=[PointStruct(
                        id=str(uuid.uuid4()), # Need integer or UUID
                        vector=vector,
                        payload={"pg_id": pg_id, "lop": d["lop"], "bo_sach": d["bo_sach"], "tuan": d["tuan"]}
                    )]
                )
                print("Inserted SGK Reading: Lượm")
            except psycopg2.IntegrityError:
                print("Lượm already exists.")
    
    # 2. NGỮ PHÁP (LANGUAGE CONCEPTS)
    concept_data = [
        {"ten": "Từ ghép", "dinh_nghia": "Từ ghép là từ gồm 2 tiếng trở lên kết hợp với nhau...", "lop_xuat_hien": 4}
    ]
    
    with conn.cursor() as cur:
        for d in concept_data:
            vid = str(uuid.uuid4())
            try:
                cur.execute("""
                    INSERT INTO extracted_content(title, clean_text, content_type) 
                    VALUES (%s, %s, 'luyen_tu_va_cau') RETURNING id
                """, (d["ten"], d["dinh_nghia"]))
                ex_id = cur.fetchone()[0]
                
                cur.execute("""
                    INSERT INTO kb_language_concepts (extracted_content_id, ten_khai_niem, dinh_nghia, lop_xuat_hien_dau, vector_id)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (ex_id, d["ten"], d["dinh_nghia"], d["lop_xuat_hien"], vid))
                pg_id = cur.fetchone()[0]
                
                vector = embed_text(d["dinh_nghia"])
                q_client.upsert(
                    collection_name="language_concepts",
                    points=[PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={"pg_id": pg_id, "lop_xuat_hien_dau": d["lop_xuat_hien"]}
                    )]
                )
                print("Inserted Concept: Từ ghép")
            except psycopg2.IntegrityError:
                print("Từ ghép already exists.")
    
    print("Dummy data population finished.")
    conn.close()

if __name__ == "__main__":
    insert_dummy_data()
