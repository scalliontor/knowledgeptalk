import json
from typing import Optional
from psycopg2.extras import RealDictCursor
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
from src.retrieval.taxonomy import RetrievedItem


def _qdrant_search(client: QdrantClient, collection: str, vector: list, qfilter, top_k: int):
    """Wrapper that handles both old .search() and new .query_points() Qdrant APIs."""
    try:
        # New Qdrant client API (>=1.7)
        result = client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=qfilter,
            limit=top_k,
            with_payload=True,
        )
        return result.points
    except AttributeError:
        # Fallback to legacy .search()
        return client.search(
            collection_name=collection,
            query_vector=vector,
            query_filter=qfilter,
            limit=top_k,
            with_payload=True,
        )


class CurriculumRetriever:
    def __init__(self, pg_conn):
        self.conn = pg_conn

    def get_current_week_lessons(self, grade: int, book_series: str, week: int) -> list[RetrievedItem]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT cs.*, kr.noi_dung_goc, kr.tom_tat, kr.tac_gia
                FROM curriculum_schedule cs
                LEFT JOIN kb_sgk_reading kr ON kr.id = cs.bai_doc_id
                WHERE cs.lop = %s AND cs.bo_sach = %s AND cs.tuan = %s
            """, (grade, book_series, week))
            rows = cur.fetchall()

        return [RetrievedItem(
            source="curriculum_schedule",
            id=str(row["id"]),
            title=f"Tuần {row['tuan']}: {row['chu_diem']}",
            content=f"Chủ điểm: {row['chu_diem']}\nBài đọc: {row['bai_doc_chinh']}\n{row.get('tom_tat') or ''}",
            score=1.0,
            metadata=dict(row)
        ) for row in rows]


class SGKReadingRetriever:
    def __init__(self, pg_conn, qdrant_client: QdrantClient, embed_fn):
        self.conn = pg_conn
        self.qdrant = qdrant_client
        self.embed = embed_fn
        self.collection = "sgk_readings"

    def exact_lookup(self, lesson_name: str, grade: Optional[int] = None,
                     book_series: Optional[str] = None) -> list[RetrievedItem]:
        def _query(g, b):
            conditions = ["ten_bai ILIKE %s"]
            params = [f"%{lesson_name}%"]

            if g:
                conditions.append("lop = %s")
                params.append(g)
            if b:
                conditions.append("bo_sach = %s")
                params.append(b)

            sql = f"""
                SELECT * FROM kb_sgk_reading
                WHERE {' AND '.join(conditions)}
                ORDER BY CASE WHEN ten_bai ILIKE %s THEN 0 ELSE 1 END, lop
                LIMIT 5
            """
            params.append(lesson_name)

            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

            return [RetrievedItem(
                source="kb_sgk_reading",
                id=str(row["id"]),
                title=row["ten_bai"],
                content=row["noi_dung_goc"],
                score=1.0 if row["ten_bai"].lower() == lesson_name.lower() else 0.8,
                metadata={
                    "tac_gia": row["tac_gia"],
                    "the_loai": row["the_loai"],
                    "lop": row["lop"],
                    "bo_sach": row["bo_sach"],
                    "trang": row["trang"],
                    "tuan": row["tuan"],
                }
            ) for row in rows]
            
        items = _query(grade, book_series)
        # If strict search fails, retry just by name
        if not items and (grade is not None or book_series is not None):
            items = _query(None, None)
            
        return items

    def semantic_search(self, query: str, grade: Optional[int] = None,
                        book_series: Optional[str] = None, top_k: int = 5) -> list[RetrievedItem]:
        query_vector = self.embed(query)
        must_conditions = []

        # Apply grade filter — but use a ±1 grade range to handle payload mismatches
        if grade is not None:
            must_conditions.append(FieldCondition(
                key="lop",
                range=Range(gte=max(1, grade - 1), lte=grade + 1)
            ))
        if book_series is not None:
            must_conditions.append(FieldCondition(key="bo_sach", match=MatchValue(value=book_series)))

        qfilter = Filter(must=must_conditions) if must_conditions else None
        results = _qdrant_search(self.qdrant, self.collection, query_vector, qfilter, top_k)

        if not results:
            # Retry without filter if no results
            results = _qdrant_search(self.qdrant, self.collection, query_vector, None, top_k)

        if not results:
            return []

        pg_ids = [int(r.payload["pg_id"]) for r in results if r.payload.get("pg_id")]
        if not pg_ids:
            return []

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM kb_sgk_reading WHERE id = ANY(%s)", (pg_ids,))
            rows_by_id = {row["id"]: row for row in cur.fetchall()}

        items = []
        for r in results:
            pg_id = r.payload.get("pg_id")
            if not pg_id:
                continue
            pg_row = rows_by_id.get(int(pg_id))
            if pg_row:
                items.append(RetrievedItem(
                    source="kb_sgk_reading",
                    id=str(pg_row["id"]),
                    title=pg_row["ten_bai"],
                    content=pg_row["noi_dung_goc"],
                    score=r.score,
                    metadata={"lop": pg_row["lop"], "bo_sach": pg_row["bo_sach"]}
                ))
        return items


class LanguageConceptRetriever:
    def __init__(self, pg_conn, qdrant_client, embed_fn):
        self.conn = pg_conn
        self.qdrant = qdrant_client
        self.embed = embed_fn
        self.collection = "language_concepts"

    def retrieve(self, query: str, user_grade: Optional[int] = None, top_k: int = 3) -> list[RetrievedItem]:
        query_vector = self.embed(query)
        must_conditions = []
        if user_grade is not None:
            must_conditions.append(FieldCondition(
                key="lop_xuat_hien_dau", range=Range(lte=user_grade)
            ))

        qfilter = Filter(must=must_conditions) if must_conditions else None
        results = _qdrant_search(self.qdrant, self.collection, query_vector, qfilter, top_k)

        # Fallback: no filter if filtered returns nothing
        if not results:
            results = _qdrant_search(self.qdrant, self.collection, query_vector, None, top_k)

        if not results:
            return []

        pg_ids = [int(r.payload["pg_id"]) for r in results if r.payload.get("pg_id")]
        if not pg_ids:
            return []

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM kb_language_concepts WHERE id = ANY(%s)", (pg_ids,))
            rows_by_id = {row["id"]: row for row in cur.fetchall()}

        items = []
        for r in results:
            pg_id = r.payload.get("pg_id")
            if not pg_id:
                continue
            row = rows_by_id.get(int(pg_id))
            if row:
                content = f"Khái niệm: {row['ten_khai_niem']}\nĐịnh nghĩa: {row['dinh_nghia']}\n"
                if row.get("vi_du"):
                    content += f"Ví dụ: {json.dumps(row['vi_du'], ensure_ascii=False)}"
                items.append(RetrievedItem(
                    source="kb_language_concepts",
                    id=str(row["id"]),
                    title=row["ten_khai_niem"],
                    content=content,
                    score=r.score
                ))
        return items


class WritingOutlineRetriever:
    def __init__(self, pg_conn, qdrant_client=None, embed_fn=None):
        self.conn = pg_conn
        self.qdrant = qdrant_client
        self.embed = embed_fn

    def retrieve(self, writing_type: str, grade: int) -> list[RetrievedItem]:
        # 1. Try kb_writing_outlines (structured dàn ý)
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM kb_writing_outlines WHERE dang_bai = %s AND lop = %s LIMIT 1",
                (writing_type, grade)
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "SELECT *, ABS(lop - %s) as distance FROM kb_writing_outlines "
                    "WHERE dang_bai = %s ORDER BY distance ASC LIMIT 1",
                    (grade, writing_type)
                )
                row = cur.fetchone()

        if row:
            cau_truc = row["cau_truc"] if isinstance(row["cau_truc"], dict) else json.loads(row["cau_truc"])
            c_parts = [f"Dàn ý: {row['dang_bai']} (lớp {row['lop']})\n"]
            if "mo_bai" in cau_truc:
                c_parts.append(f"MỞ BÀI:\n  Gợi ý: {cau_truc['mo_bai'].get('goi_y', '')}")
            if "than_bai" in cau_truc:
                c_parts.append("\nTHÂN BÀI:")
                for q in cau_truc["than_bai"].get("ta_bao_quat", []):
                    c_parts.append(f"    - {q}")
                for q in cau_truc["than_bai"].get("ta_chi_tiet", []):
                    c_parts.append(f"    - {q}")
            if "ket_bai" in cau_truc:
                c_parts.append(f"\nKẾT BÀI:\n  Gợi ý: {cau_truc['ket_bai'].get('goi_y', '')}")
            return [RetrievedItem(
                source="kb_writing_outlines",
                id=str(row["id"]),
                title=f"Dàn ý {row['dang_bai']}",
                content="\n".join(c_parts),
                score=1.0
            )]

        # 2. Fallback: kb_writing_samples (văn mẫu)
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Try by writing type first
            cur.execute("""
                SELECT * FROM kb_writing_samples
                WHERE dang_bai = %s
                ORDER BY ABS(lop - %s)
                LIMIT 2
            """, (writing_type, grade))
            samples = cur.fetchall()
            # Broader fallback: any sample near this grade
            if not samples:
                cur.execute("""
                    SELECT * FROM kb_writing_samples
                    ORDER BY ABS(lop - %s)
                    LIMIT 2
                """, (grade,))
                samples = cur.fetchall()

        if samples:
            items = []
            for s in samples:
                items.append(RetrievedItem(
                    source="kb_writing_samples",
                    id=str(s["id"]),
                    title=s.get("tieu_de") or s.get("chu_de") or f"Văn mẫu {s.get('dang_bai','')}",
                    content=s.get("noi_dung", ""),
                    score=0.7,
                    metadata={"lop": s.get("lop"), "loai": s.get("dang_bai")}
                ))
            return items

        return []

class MathExerciseRetriever:
    def __init__(self, pg_conn, qdrant_client, embed_fn):
        self.conn = pg_conn
        self.qdrant = qdrant_client
        self.embed = embed_fn
        self.collection = "kb_math_exercises"

    def semantic_search(self, query: str, grade: Optional[int] = None, top_k: int = 3) -> list[RetrievedItem]:
        query_vector = self.embed(query)
        must_conditions = []
        if grade is not None:
            must_conditions.append(FieldCondition(
                key="lop", range=Range(gte=max(1, grade - 1), lte=grade + 1)
            ))

        qfilter = Filter(must=must_conditions) if must_conditions else None
        results = _qdrant_search(self.qdrant, self.collection, query_vector, qfilter, top_k)

        if not results:
            results = _qdrant_search(self.qdrant, self.collection, query_vector, None, top_k)

        if not results:
            return []

        pg_ids = [int(r.payload["kb_id"]) for r in results if r.payload.get("kb_id")]
        if not pg_ids:
            return []

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM kb_math_exercises WHERE id = ANY(%s)", (pg_ids,))
            rows_by_id = {row["id"]: row for row in cur.fetchall()}

        items = []
        for r in results:
            pg_id = r.payload.get("kb_id")
            if not pg_id:
                continue
            row = rows_by_id.get(int(pg_id))
            if row:
                content = f"Đề bài: {row['de_bai']}\nLời giải: {row['loi_giai']}"
                items.append(RetrievedItem(
                    source="kb_math_exercises",
                    id=str(row["id"]),
                    title=f"Toán {row['lop']} ({row['bo_sach']})",
                    content=content,
                    score=r.score
                ))
        return items

class KHTNRetriever:
    def __init__(self, pg_conn, qdrant_client, embed_fn):
        self.conn = pg_conn
        self.qdrant = qdrant_client
        self.embed = embed_fn
        self.collection = "kb_khtn_exercises"

    def semantic_search(self, query: str, grade: Optional[int] = None, top_k: int = 3) -> list[RetrievedItem]:
        query_vector = self.embed(query)
        must_conditions = []
        if grade is not None:
            must_conditions.append(FieldCondition(
                key="lop", range=Range(gte=max(6, grade - 1), lte=grade + 1)
            ))

        qfilter = Filter(must=must_conditions) if must_conditions else None
        results = _qdrant_search(self.qdrant, self.collection, query_vector, qfilter, top_k)

        if not results:
            results = _qdrant_search(self.qdrant, self.collection, query_vector, None, top_k)

        if not results:
            return []

        pg_ids = [int(r.payload["kb_id"]) for r in results if r.payload.get("kb_id")]
        if not pg_ids:
            return []

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM kb_khtn_exercises WHERE id = ANY(%s)", (pg_ids,))
            rows_by_id = {row["id"]: row for row in cur.fetchall()}

        items = []
        for r in results:
            pg_id = r.payload.get("kb_id")
            if not pg_id:
                continue
            row = rows_by_id.get(int(pg_id))
            if row:
                content = f"Đề bài/Câu hỏi: {row['de_bai']}\nLời giải/Đáp án: {row['loi_giai']}"
                items.append(RetrievedItem(
                    source="kb_khtn_exercises",
                    id=str(row["id"]),
                    title=f"KHTN {row['lop']} ({row['bo_sach']})",
                    content=content,
                    score=r.score
                ))
        return items

class SocialScienceRetriever:
    def __init__(self, pg_conn, qdrant_client, embed_fn):
        self.conn = pg_conn
        self.qdrant = qdrant_client
        self.embed = embed_fn
        self.collection = "kb_social_exercises"

    def semantic_search(self, query: str, grade: Optional[int] = None, top_k: int = 3) -> list[RetrievedItem]:
        query_vector = self.embed(query)
        must_conditions = []
        if grade is not None:
            must_conditions.append(FieldCondition(
                key="lop", range=Range(gte=max(4, grade - 1), lte=grade + 1)
            ))

        qfilter = Filter(must=must_conditions) if must_conditions else None
        results = _qdrant_search(self.qdrant, self.collection, query_vector, qfilter, top_k)

        if not results:
            results = _qdrant_search(self.qdrant, self.collection, query_vector, None, top_k)

        if not results:
            return []

        pg_ids = [int(r.payload["kb_id"]) for r in results if r.payload.get("kb_id")]
        if not pg_ids:
            return []

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM kb_social_exercises WHERE id = ANY(%s)", (pg_ids,))
            rows_by_id = {row["id"]: row for row in cur.fetchall()}

        items = []
        for r in results:
            pg_id = r.payload.get("kb_id")
            if not pg_id:
                continue
            row = rows_by_id.get(int(pg_id))
            if row:
                content = f"Vấn đề/Câu hỏi: {row['de_bai']}\nKiến thức/Lời giải: {row['loi_giai']}"
                items.append(RetrievedItem(
                    source="kb_social_exercises",
                    id=str(row["id"]),
                    title=f"Khoa học Xã hội {row['lop']} ({row['bo_sach']})",
                    content=content,
                    score=r.score
                ))
        return items



class GraphRetriever:
    """Retrieves structured Q&A and text passages from the Neo4j Graph Database.

    Uses the original flat schema (Passage_Span, Question, Solution nodes)
    with fulltext indexes: qa_ft, passage_ft.

    Schema v2 (hierarchical) methods are preserved as stubs for future re-ingestion.
    """

    def __init__(self):
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                "bolt://localhost:7688",
                auth=("neo4j", "edu_graph_2026")
            )
            self._available = True
        except Exception as e:
            print(f"[GraphRetriever] Neo4j unavailable: {e}")
            self._driver = None
            self._available = False

    def search_by_keyword(self, query: str, top_k: int = 3) -> list[RetrievedItem]:
        """Full-text keyword search across Passage_Span, Question, Solution nodes."""
        if not self._available:
            return []
        import re
        safe_query = re.sub(r'[^\w\s]', ' ', query).strip()
        if not safe_query:
            return []
        items = []
        try:
            with self._driver.session() as session:
                try:
                    result = session.run("""
                        CALL db.index.fulltext.queryNodes("qa_ft", $search_term) YIELD node, score
                        MATCH (s:Solution)-[:SOLVES]->(q:Question)
                        WHERE elementId(node) = elementId(q) OR elementId(node) = elementId(s)
                        RETURN q.raw_text AS question, s.raw_text AS solution,
                               q.node_id AS node_id, score
                        ORDER BY score DESC LIMIT $top_k
                    """, search_term=safe_query, top_k=top_k)
                    for rec in result:
                        items.append(RetrievedItem(
                            source="graph_neo4j",
                            id=rec["node_id"] or "",
                            title=f"[Graph] {(rec['question'] or '')[:60]}...",
                            content=f"Câu hỏi: {rec['question']}\nLời giải: {rec['solution']}",
                            score=min(1.0, rec["score"] / 10.0 + 0.5)
                        ))
                except Exception:
                    pass
                try:
                    result2 = session.run("""
                        CALL db.index.fulltext.queryNodes("passage_ft", $search_term) YIELD node, score
                        RETURN node.title AS p_title, node.raw_text AS raw_text,
                               node.node_id AS node_id, score
                        ORDER BY score DESC LIMIT 2
                    """, search_term=safe_query)
                    for rec in result2:
                        if rec["raw_text"]:
                            items.append(RetrievedItem(
                                source="graph_neo4j",
                                id=rec["node_id"] or "",
                                title=f"[Graph Passage] {rec['p_title'] or ''}",
                                content=rec["raw_text"],
                                score=min(1.0, rec["score"] / 20.0 + 0.5)
                            ))
                except Exception:
                    pass
        except Exception as e:
            print(f"[GraphRetriever] Query error: {e}")
        return items

    def search_by_lesson(self, lesson_name: str, top_k: int = 5) -> list[RetrievedItem]:
        """Search nodes associated with a specific lesson."""
        if not self._available:
            return []
        import re
        safe = re.sub(r'[^\w\s]', ' ', lesson_name).strip()
        if not safe:
            return []
        items = []
        try:
            with self._driver.session() as session:
                try:
                    result = session.run("""
                        CALL db.index.fulltext.queryNodes("qa_ft", $keyword) YIELD node, score
                        MATCH (s:Solution)-[:SOLVES]->(q:Question)
                        WHERE elementId(node) = elementId(q) OR elementId(node) = elementId(s)
                        RETURN q.raw_text AS question, s.raw_text AS solution, q.node_id AS node_id
                        LIMIT $top_k
                    """, keyword=safe, top_k=top_k)
                    for rec in result:
                        items.append(RetrievedItem(
                            source="graph_neo4j",
                            id=rec["node_id"] or "",
                            title=f"[Graph] {(rec['question'] or '')[:60]}...",
                            content=f"Câu hỏi: {rec['question']}\nLời giải: {rec['solution']}",
                            score=0.95
                        ))
                except Exception:
                    pass
                try:
                    result2 = session.run("""
                        CALL db.index.fulltext.queryNodes("passage_ft", $keyword) YIELD node, score
                        WITH node, score ORDER BY score DESC LIMIT $top_k
                        RETURN node.raw_text AS raw_text, node.node_id AS node_id, node.title AS title, score
                    """, keyword=safe, top_k=max(2, top_k // 2))
                    for rec in result2:
                        if rec["raw_text"]:
                            items.append(RetrievedItem(
                                source="graph_neo4j",
                                id=rec["node_id"] or "",
                                title=f"[Graph Passage] {rec['title'] or ''}",
                                content=rec["raw_text"],
                                score=1.0
                            ))
                except Exception:
                    pass
        except Exception as e:
            print(f"[GraphRetriever] Lesson search error: {e}")
        return items

    # ── Schema v2 (Grade → Subject → BookSeries → Unit → Lit/Lesson/Summary) ──

    def lookup_literature(self, title_query: str, series=None, grade: int = 9) -> list[RetrievedItem]:
        """V2: Tìm toàn văn tác phẩm theo tên bài (bi-directional CONTAINS match)."""
        items = []
        if not self._available or not self._driver:
            return items
        try:
            # Match both: unit name within query, or query within unit name
            base_cypher = """
                MATCH (u:Unit)-[:HAS_LITERATURE]->(lit:LiteratureText){series_filter}
                WHERE toLower($q) CONTAINS toLower(u.work_name)
                   OR toLower(u.work_name) CONTAINS toLower($q)
                   OR toLower(lit.title) CONTAINS toLower($q)
                   OR toLower($q) CONTAINS toLower(lit.title)
                RETURN lit.title AS title, lit.full_text AS content,
                       lit.author AS author, lit.series AS series,
                       lit.grade AS grade
                ORDER BY
                    CASE WHEN toLower($q) CONTAINS toLower(u.work_name) THEN 0 ELSE 1 END,
                    size(u.work_name) DESC
                LIMIT 2
            """
            if series:
                cypher = base_cypher.replace("{series_filter}", " {series: $series}")
                result = self._driver.session().run(cypher, q=title_query, series=series)
            else:
                cypher = base_cypher.replace("{series_filter}", "")
                result = self._driver.session().run(cypher, q=title_query)

            for r in result:
                content = r["content"] or ""
                if content:
                    items.append(RetrievedItem(
                        source=f"LiteratureText/{r['series']}",
                        id=f"lit_{title_query[:20]}",
                        title=r["title"],
                        content=content,
                        score=1.0
                    ))
        except Exception as e:
            print(f"[GraphRetriever v2] lookup_literature error: {e}")
        return items


    def lookup_lesson_guide(self, title_query: str, series=None, grade: int = 9) -> list[RetrievedItem]:
        """V2: Tìm soạn bài / hướng dẫn học theo tên tác phẩm (bi-directional CONTAINS)."""
        items = []
        if not self._available or not self._driver:
            return items
        try:
            base_cypher = """
                MATCH (u:Unit)-[:HAS_LESSON]->(lg:LessonGuide){series_filter}
                WHERE toLower($q) CONTAINS toLower(u.work_name)
                   OR toLower(u.work_name) CONTAINS toLower($q)
                   OR toLower(lg.title) CONTAINS toLower($q)
                   OR toLower($q) CONTAINS toLower(lg.title)
                RETURN lg.title AS title, lg.content AS content, lg.series AS series
                ORDER BY
                    CASE WHEN toLower($q) CONTAINS toLower(u.work_name) THEN 0 ELSE 1 END,
                    size(u.work_name) DESC
                LIMIT 2
            """
            if series:
                cypher = base_cypher.replace("{series_filter}", " {series: $series}")
                result = self._driver.session().run(cypher, q=title_query, series=series)
            else:
                cypher = base_cypher.replace("{series_filter}", "")
                result = self._driver.session().run(cypher, q=title_query)
            for r in result:
                content = r["content"] or ""
                if content:
                    items.append(RetrievedItem(
                        source=f"LessonGuide/{r['series']}",
                        id=f"lg_{title_query[:20]}",
                        title=r["title"],
                        content=content[:3000],
                        score=0.9
                    ))
        except Exception as e:
            print(f"[GraphRetriever v2] lookup_lesson_guide error: {e}")
        return items

    def lookup_summary(self, title_query: str, series=None, grade: int = 9) -> list[RetrievedItem]:
        """V2: Tìm tóm tắt tác phẩm theo tên bài (bi-directional CONTAINS)."""
        items = []
        if not self._available or not self._driver:
            return items
        try:
            base_cypher = """
                MATCH (u:Unit)-[:HAS_SUMMARY]->(sm:Summary){series_filter}
                WHERE toLower($q) CONTAINS toLower(u.work_name)
                   OR toLower(u.work_name) CONTAINS toLower($q)
                   OR toLower(sm.title) CONTAINS toLower($q)
                   OR toLower($q) CONTAINS toLower(sm.title)
                RETURN sm.title AS title, sm.content AS content, sm.series AS series
                ORDER BY
                    CASE WHEN toLower($q) CONTAINS toLower(u.work_name) THEN 0 ELSE 1 END,
                    size(u.work_name) DESC
                LIMIT 2
            """
            if series:
                cypher = base_cypher.replace("{series_filter}", " {series: $series}")
                result = self._driver.session().run(cypher, q=title_query, series=series)
            else:
                cypher = base_cypher.replace("{series_filter}", "")
                result = self._driver.session().run(cypher, q=title_query)
            for r in result:
                content = r["content"] or ""
                if content:
                    items.append(RetrievedItem(
                        source=f"Summary/{r['series']}",
                        id=f"sm_{title_query[:20]}",
                        title=r["title"],
                        content=content,
                        score=0.85
                    ))
        except Exception as e:
            print(f"[GraphRetriever v2] lookup_summary error: {e}")
        return items

    def fulltext_search(self, query: str, grade: int = 9, series=None, top_k: int = 3) -> list[RetrievedItem]:
        """V2: Fulltext search trên lesson_fulltext index (LessonGuide)."""
        items = []
        try:
            cypher = """
                CALL db.index.fulltext.queryNodes("lesson_fulltext", $q) YIELD node, score
                RETURN node.title AS title, node.content AS content,
                       node.series AS series, score
                LIMIT $k
            """
            result = self._driver.session().run(cypher, q=query, k=top_k)
            for r in result:
                content = r["content"] or ""
                items.append(RetrievedItem(
                    source=f"LessonGuide_FT/{r['series']}",
                    id=f"ft_{query[:20]}",
                    title=r["title"],
                    content=content[:2000],
                    score=float(r["score"])
                ))
        except Exception as e:
            print(f"[GraphRetriever v2] fulltext_search error: {e}, falling back to keyword search")
            items = self.search_by_keyword(query, top_k=top_k)
        return items


