"""Qdrant vector retrieval (math / KHTN / social fallback).

EXTRACTED VERBATIM from /tmp/refsrc_canary.py. The body of `query_qdrant` is a
byte-for-byte copy of the source. The only deviations (documented):

  - the BGE model is INJECTED as `model` (was module global `bge_m3_model`);
  - `canonicalize_subject` is imported from `knowledge_core` (was a module-level
    function in the monolith);
  - `SUBJECT_TO_QDRANT` is kept here (it is the Qdrant-collection mapping, a
    retrieval concern) — byte-for-byte from the source.

`QdrantClient`/`psycopg2` are imported lazily INSIDE the function body exactly as
in the source, so importing this module opens NO network connection and loads no
client. The `host=...` constants (localhost + 171.226.10.121 fallback) are kept
verbatim. The postgres password is read from env (`PG_PW`) instead of a literal
(redacted for repo per CLAUDE.md; server `.env` supplies it). See migration-plan.md
for moving the remaining host literals to `.env` in a follow-up.
"""
from __future__ import annotations

from typing import Dict, Any

from knowledge_core import canonicalize_subject


# byte-for-byte from /tmp/refsrc_canary.py
SUBJECT_TO_QDRANT = {
    "toan": "kb_math_exercises",
    "khtn": "kb_khtn_exercises",
    "lich_su": "kb_social_exercises",
    "dia_ly": "kb_social_exercises"
}


def query_qdrant(intent: Dict[str, Any], *, model) -> str:
    """Truy vấn Qdrant cho các môn Toán, KHTN, Sử, Địa..."""
    keyword = intent.get("keyword", "")
    subject = canonicalize_subject(intent.get("subject"), intent.get("search_query", keyword))
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")

    if not keyword:
        return ""

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        try:
            client = QdrantClient(host="localhost", port=6333, timeout=3)
            client.get_collections()
        except:
            client = QdrantClient(host="171.226.10.121", port=6333, timeout=5)

        query_vector = model.encode([keyword], normalize_embeddings=True)[0].tolist()

        must_conditions = []
        if grade:
            must_conditions.append(FieldCondition(key="lop", match=MatchValue(value=int(grade))))
        if bo_sach:
            must_conditions.append(FieldCondition(key="bo_sach", match=MatchValue(value=bo_sach)))

        query_filter = Filter(must=must_conditions) if must_conditions else None

        all_results = []
        target_collections = [SUBJECT_TO_QDRANT.get(subject)] if SUBJECT_TO_QDRANT.get(subject) else ["kb_math_exercises", "kb_khtn_exercises", "kb_social_exercises"]
        target_collections = [c for c in target_collections if c]

        for coll in target_collections:
            try:
                if hasattr(client, 'query_points'):
                    res = client.query_points(
                        collection_name=coll,
                        query=query_vector,
                        query_filter=query_filter,
                        limit=3
                    ).points
                else:
                    res = client.search(
                        collection_name=coll,
                        query_vector=query_vector,
                        query_filter=query_filter,
                        limit=3
                    )
                for r in res:
                    r.payload["_collection_name"] = coll
                all_results.extend(res)
            except Exception as e:
                print(f"[Qdrant Search Error in {coll}] {e}")

        all_results.sort(key=lambda x: x.score, reverse=True)
        results = all_results[:4]

        import psycopg2
        pg_conn = None
        try:
            pg_conn = psycopg2.connect(host="localhost", port=5433, dbname="rag_edu", user="postgres", password=__import__("os").environ.get("PG_PW", ""), connect_timeout=3)
        except:
            try:
                pg_conn = psycopg2.connect(host="171.226.10.121", port=5433, dbname="rag_edu", user="postgres", password=__import__("os").environ.get("PG_PW", ""), connect_timeout=3)
            except Exception as e:
                print(f"[PG Connect Error] {e}")

        contexts = []
        for r in results:
            payload = r.payload or {}
            lop = payload.get("lop", "N/A")
            sach = payload.get("bo_sach", "N/A")
            meta = f"Lớp {lop} | Bộ sách: {sach}"

            content_text = ""
            coll_name = payload.get("_collection_name", "")
            title = payload.get("title", payload.get("ten_bai", f"Bài tập ({coll_name})"))

            kb_id = payload.get("kb_id")
            if kb_id and pg_conn:
                try:
                    with pg_conn.cursor() as cur:
                        table_name = coll_name
                        cur.execute(f"SELECT * FROM {table_name} WHERE id = %s", (kb_id,))
                        row = cur.fetchone()
                        if row:
                            colnames = [desc[0] for desc in cur.description]
                            row_dict = dict(zip(colnames, row))

                            if "ten_khai_niem" in row_dict and row_dict["ten_khai_niem"]:
                                title = row_dict["ten_khai_niem"]
                            elif "bai_so" in row_dict and row_dict["bai_so"]:
                                title = f"Bài {row_dict['bai_so']} (Trang {row_dict.get('trang', '?')})"

                            if "de_bai" in row_dict and "loi_giai" in row_dict:
                                content_text = f"Đề bài: {row_dict['de_bai']}\nLời giải: {row_dict['loi_giai']}"
                            elif "dinh_nghia" in row_dict:
                                content_text = f"Định nghĩa: {row_dict['dinh_nghia']}\nCông thức: {row_dict.get('cong_thuc_text', '')}"
                            else:
                                texts = [str(v) for k, v in row_dict.items() if isinstance(v, str) and len(v) > 20]
                                content_text = "\n".join(texts)
                except Exception as e:
                    print(f"[PG Query Error] {e}")
                    pg_conn.rollback()

            if not content_text:
                # Fallback to payload text if postgres fails
                content_text = payload.get("content", payload.get("text", ""))

            contexts.append(f"📚 {title} ({meta})\n{content_text}")

        if pg_conn:
            pg_conn.close()

        return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Qdrant Error] {e}")
        return ""
