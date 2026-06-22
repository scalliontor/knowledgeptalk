"""Neo4j vector / knowledge-chunk / lesson-guide retrieval + recitation lookups.

EXTRACTED VERBATIM from /tmp/refsrc_canary.py. Every function body, every Cypher
string, and every scoring/sort expression is a byte-for-byte copy of the source.

Refactor deviations (documented, behavior-preserving):

  - `GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)` is replaced by an INJECTED
    `driver_factory()` — a zero-arg callable that returns a fresh driver (the
    monolith created and `.close()`d a driver per call; the factory preserves
    that exact lifecycle). NEO4J_URI/NEO4J_AUTH are no longer module globals.
  - The BGE model is INJECTED as `model` (was module global `bge_m3_model`).
  - `normalize_text` / `clean_recite_title` are imported from `knowledge_core`.
  - The `recite_from_*` functions return a response object built by an INJECTED
    `lines_payload(title, lines, intent, source)` callable (the monolith's
    `lines_payload` builds a Pydantic `RetrieveResponse`, which is a serving-layer
    type — kept out of this pure-retrieval module). Scoring/segment ordering is
    unchanged.

No import-time IO: importing this module opens no driver and loads no model.
"""
from __future__ import annotations

import re
from typing import Dict, Any, Optional

from knowledge_core import normalize_text, clean_recite_title


def query_neo4j_vector(intent: Dict[str, Any], *, driver_factory, model) -> str:
    """Truy vấn Hybrid (Vector + Structural) qua Neo4j Native Vector"""
    keyword = intent.get("keyword", "")
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")

    if not keyword:
        return ""

    try:
        query_vector = model.encode([keyword], normalize_embeddings=True)[0].tolist()

        driver = driver_factory()

        # Return focused sections, not the entire FullDocument, to keep LLM context tight.
        cypher_query = """
        CALL db.index.vector.queryNodes('section_embedding', 15, $query_vector)
        YIELD node AS sec, score
        WHERE ($grade IS NULL OR sec.grade = $grade)
          AND ($bo_sach IS NULL OR sec.bo_sach = $bo_sach)
        WITH sec, score
        MATCH (fd:FullDocument)-[:HAS_SECTION]->(sec)
        RETURN fd.title AS lesson_title, fd.grade AS grade, fd.bo_sach AS bo_sach,
               sec.title AS section_title, sec.text AS section_text, score
        ORDER BY score DESC
        LIMIT 5
        """

        params = {
            "query_vector": query_vector,
            "grade": grade,
            "bo_sach": bo_sach
        }

        with driver.session() as session:
            results = session.run(cypher_query, **params)
            contexts = []
            for r in results:
                meta = f"Lớp {r['grade']} | Bộ sách: {r['bo_sach']}"
                contexts.append(
                    f"📚 {r['lesson_title']} ({meta})\n"
                    f"Mục: {r['section_title']}\n{r['section_text']}"
                )

            return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Neo4j Vector Error] {e}")
        return ""


def query_neo4j_knowledge_chunk(intent: Dict[str, Any], *, driver_factory, model) -> str:
    """Truy vấn Neo4j KnowledgeChunk (Production & Staging sạch)"""
    keyword = intent.get("keyword", "")
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")
    subject = intent.get("subject")

    if not keyword:
        return ""

    ALLOW_STAGING = False

    try:
        query_vector = model.encode([keyword], normalize_embeddings=True)[0].tolist()

        driver = driver_factory()

        cypher_query = """
        CALL db.index.vector.queryNodes('knowledge_chunk_embedding', 5, $query_vector)
        YIELD node AS k, score
        WHERE (k:KnowledgeChunk)
          AND ($grade IS NULL OR k.grade = $grade OR toString(k.grade) = toString($grade))
          AND ($bo_sach IS NULL OR k.bo_sach = $bo_sach)
          AND ($subject IS NULL OR k.subject_code = $subject)
          AND (
            coalesce(k.production_ready, false) = true
            OR ($allow_staging = true AND k:StagingClean)
          )
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, score
        ORDER BY score DESC
        """

        params = {
            "query_vector": query_vector,
            "grade": grade,
            "bo_sach": bo_sach,
            "subject": subject,
            "allow_staging": ALLOW_STAGING
        }

        with driver.session() as session:
            results = session.run(cypher_query, **params)
            contexts = []
            for r in results:
                meta = f"Lớp {r['grade']} | Bộ sách: {r['bo_sach']}"
                contexts.append(
                    f"📚 {r['title']} ({meta})\n{r['text']}"
                )

            return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Neo4j KnowledgeChunk Vector Error] {e}")
        return ""


# ── Phase 1: LessonGuide whole-doc retrieval ───────────────────────
# Activates 11K LessonGuide content via lesson_guide_embedding index.
# NOTE: LessonGuide.subject is currently NULL for all nodes (Phase 1.5 will backfill).
# So we rely on vector similarity + optional grade/bo_sach filter only.
def query_neo4j_lesson_guide(intent: Dict[str, Any], *, driver_factory, model) -> str:
    """Truy vấn whole-document LessonGuide via lesson_guide_embedding (1024d cosine)."""
    keyword = intent.get("keyword", "")
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")

    if not keyword:
        return ""

    try:
        query_vector = model.encode([keyword], normalize_embeddings=True)[0].tolist()
        driver = driver_factory()

        # Top-3 whole-doc matches with optional grade/bo_sach filter
        cypher_query = """
        CALL db.index.vector.queryNodes('lesson_guide_embedding', 5, $query_vector)
        YIELD node AS lg, score
        WHERE (lg:LessonGuide)
          AND lg.embedding IS NOT NULL
          AND ($grade IS NULL OR lg.grade = $grade OR toString(lg.grade) = toString($grade))
          AND ($bo_sach IS NULL OR lg.bo_sach = $bo_sach)
        RETURN lg.title AS title, lg.grade AS grade, lg.bo_sach AS bo_sach,
               lg.content AS content, lg.url AS url, score
        ORDER BY score DESC
        LIMIT 3
        """

        params = {
            "query_vector": query_vector,
            "grade": grade,
            "bo_sach": bo_sach,
        }

        with driver.session() as session:
            results = session.run(cypher_query, **params)
            contexts = []
            for r in results:
                meta_parts = []
                if r["grade"]:
                    meta_parts.append(f"Lớp {r['grade']}")
                if r["bo_sach"] and r["bo_sach"] != "LEGACY":
                    meta_parts.append(f"Bộ sách: {r['bo_sach']}")
                meta = " | ".join(meta_parts) if meta_parts else "Hướng dẫn học"
                # Truncate content per match — let trim_context handle final size
                content = (r["content"] or "")[:4000]
                contexts.append(
                    f"📖 {r['title']} ({meta})\n{content}"
                )

            return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Neo4j LessonGuide Vector Error] {e}")
        return ""


def recite_from_literature_text(title: str, intent: dict, grade=None, bo_sach=None,
                                *, driver_factory, lines_payload):
    clean_title = clean_recite_title(title)
    wanted = normalize_text(clean_title)
    if not wanted:
        wanted = normalize_text(title)
    if not wanted:
        return None

    cypher = """
    MATCH (lt:LiteratureText)
    WHERE ($grade IS NULL OR lt.grade = $grade OR toString(lt.grade) = toString($grade))
      AND ($bo_sach IS NULL OR lt.series = $bo_sach)
    RETURN lt.title AS title, lt.full_text AS full_text, lt.grade AS grade,
           lt.series AS series, lt.author AS author, lt.url AS url
    """
    driver = driver_factory()
    try:
        with driver.session() as session:
            candidates = [dict(r) for r in session.run(cypher, grade=grade, bo_sach=bo_sach)]
    except Exception as e:
        print(f"[Neo4j LiteratureText Recitation Error] {e}")
        return None
    finally:
        driver.close()

    scored = []
    for row in candidates:
        normalized_title = normalize_text(row.get("title", ""))
        normalized_url = normalize_text(row.get("url", ""))
        score = 0
        if wanted == normalized_title:
            score = 3
        elif re.search(r"(?:^|\s)" + re.escape(wanted) + r"(?:\s|$)", normalized_title):
            score = 2
        elif wanted in normalized_title or normalized_title in wanted or wanted in normalized_url:
            score = 1
        if score > 0:
            scored.append((score, len(normalized_title), row))
    scored.sort(key=lambda x: (-x[0], x[1]))
    best = scored[0][2] if scored else None

    if not best or not best.get("full_text"):
        return None

    lines = [
        {"text": line.strip(), "pause_ms": 700}
        for line in best["full_text"].splitlines()
        if line.strip()
    ]
    if not lines:
        return None
    return lines_payload(best["title"], lines, intent, "neo4j_literature_text")


def recite_from_reading_text(title: str, grade=None, bo_sach=None,
                             *, driver_factory, lines_payload):
    wanted = normalize_text(title)
    cypher = """
    MATCH (rt:ReadingText)
    WHERE ($grade IS NULL OR rt.grade = $grade OR toString(rt.grade) = toString($grade))
      AND ($bo_sach IS NULL OR rt.bo_sach = $bo_sach)
    OPTIONAL MATCH (rt)-[:HAS_SEGMENT]->(seg:RecitationSegment)
    RETURN rt.title AS title, rt.original_text AS original_text,
           collect({idx: seg.segment_index, text: seg.text, pause: seg.pause_after_ms}) AS segments
    """
    driver = driver_factory()
    try:
        with driver.session() as session:
            records = [dict(r) for r in session.run(cypher, grade=grade, bo_sach=bo_sach)]
            record = next(
                (
                    r for r in records
                    if wanted in normalize_text(r.get("title", "")) or normalize_text(r.get("title", "")) in wanted
                ),
                None,
            )
            if not record:
                return None

            segments = [s for s in record["segments"] if s.get("text")]
            if segments:
                segments.sort(key=lambda s: s.get("idx") if s.get("idx") is not None else 0)
                lines = [{"text": s["text"], "pause_ms": s.get("pause") or 600} for s in segments]
            else:
                text = record["original_text"] or ""
                lines = [{"text": line.strip(), "pause_ms": 600} for line in text.splitlines() if line.strip()]

            if not lines:
                return None

            return lines_payload(record["title"], lines, {"source": "ReadingText"}, "neo4j_reading_text")
    except Exception as e:
        print(f"[Neo4j ReadingText Recitation Error] {e}")
        return None
    finally:
        driver.close()


def recite_from_full_document(title: str, intent: dict, grade=None, bo_sach=None,
                              *, driver_factory, lines_payload):
    """Fallback for canonical reading_original FullDocument. Avoid soan_bai_full for recitation."""
    wanted = normalize_text(title)
    cypher = """
    MATCH (fd:FullDocument)
    WHERE fd.document_type = 'reading_original'
      AND ($grade IS NULL OR fd.grade = $grade OR toString(fd.grade) = toString($grade))
      AND ($bo_sach IS NULL OR fd.bo_sach = $bo_sach)
    OPTIONAL MATCH (fd)-[:HAS_SECTION]->(s:Section)-[:HAS_BLOCK]->(b:ContentBlock)
    RETURN fd.title AS title, fd.full_text AS full_text,
           collect({sidx: s.section_index, bidx: b.block_index, text: b.text}) AS blocks
    """
    driver = driver_factory()
    try:
        with driver.session() as session:
            records = [dict(r) for r in session.run(cypher, grade=grade, bo_sach=bo_sach)]
    except Exception as e:
        print(f"[Neo4j FullDocument Recitation Error] {e}")
        return None
    finally:
        driver.close()

    record = next(
        (
            r for r in records
            if wanted in normalize_text(r.get("title", "")) or normalize_text(r.get("title", "")) in wanted
        ),
        None,
    )
    if not record:
        return None

    blocks = [b for b in record["blocks"] if b.get("text")]
    if blocks:
        blocks.sort(key=lambda b: (
            b.get("sidx") if b.get("sidx") is not None else 0,
            b.get("bidx") if b.get("bidx") is not None else 0,
        ))
        lines = [{"text": b["text"], "pause_ms": 600} for b in blocks]
    else:
        lines = [{"text": line.strip(), "pause_ms": 600} for line in (record.get("full_text") or "").splitlines() if line.strip()]
    if not lines:
        return None
    return lines_payload(record["title"], lines, intent, "neo4j_full_document")
