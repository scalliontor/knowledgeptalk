import os
import time
import psycopg2
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

# Constants
QDRANT_URL = "http://localhost:6333"
MODEL_NAME = "intfloat/multilingual-e5-large"
PG_DSN = "postgresql://postgres:postgres@localhost:5433/rag_edu"
BATCH_SIZE = 32

def main():
    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME, device='cuda')
    
    qc = QdrantClient(url=QDRANT_URL)
    conn = psycopg2.connect(PG_DSN)
    
    # Define collection
    coll_name = "kb_khtn_exercises"
    if not qc.collection_exists(coll_name):
        qc.create_collection(
            collection_name=coll_name,
            vectors_config=VectorParams(size=model.get_sentence_embedding_dimension(), distance=Distance.COSINE)
        )
        print(f"Created collection {coll_name}")
        
    print("Loading un-embedded KHTN exercises...")
    with conn.cursor() as cur:
        cur.execute("SELECT id, vector_id, lop, bo_sach, de_bai, loi_giai FROM kb_khtn_exercises")
        rows = cur.fetchall()
        print(f"Rows fetched: {len(rows)}")
        
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i+BATCH_SIZE]
            texts_to_embed = []
            valid_ids = []
            points = []
            
            for row in batch:
                row_id, vector_id, lop, bo_sach, de, giai = row
                # We embed the "de_bai" block with instructions
                text = f"query: khoa học tự nhiên lớp {lop} bài tập: {de}"
                texts_to_embed.append(text)
                valid_ids.append((row_id, vector_id, lop, bo_sach))
                
            if not texts_to_embed: continue
            
            embeddings = model.encode(texts_to_embed, normalize_embeddings=True)
            
            for (row_id, vector_id, lop, bo_sach), emb in zip(valid_ids, embeddings):
                points.append(
                    PointStruct(
                        id=str(vector_id),
                        vector=emb.tolist(),
                        payload={
                            "kb_id": row_id,
                            "lop": lop,
                            "bo_sach": bo_sach,
                            "subject": "khtn"
                        }
                    )
                )
            # Upsert
            qc.upsert(collection_name=coll_name, points=points)
            print(f"Inserted {i + len(batch)} / {len(rows)} points")

if __name__ == '__main__':
    main()
