"""Tier A structured-first exact lookups (bài/trang + concept-name).

EXTRACTED VERBATIM from /tmp/refsrc_canary.py. `query_structured_exact` and
`query_concept_exact` bodies — including every Cypher string, the `conds`/`params`
construction, the `_fold`-folded title variants, and the ORDER BY scoring — are
byte-for-byte copies of the source.

Refactor deviations (documented, behavior-preserving):
  - `GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)` -> INJECTED
    `driver_factory()` (zero-arg callable returning a fresh driver; preserves the
    per-call create/`.close()` lifecycle of the monolith).
  - `_fold` is imported from `knowledge_core` (was a module global).

No import-time IO.
"""
from __future__ import annotations

from typing import Dict, Any

from knowledge_core import _fold


def query_concept_exact(parsed: Dict[str, Any], query: str, *, driver_factory) -> str:
    """Tier A-concept: topic-only query (no bai/trang) -> exact lookup by Concept name within grade+book."""
    grade = parsed.get("lop")
    bo_sach = parsed.get("bo_sach")
    subject = parsed.get("subject")
    if not (grade and bo_sach):
        return ""
    q_folded = _fold(query)
    cypher = """
        MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept)
        WHERE coalesce(k.production_ready,false) = true
          AND (k.grade = $grade OR toString(k.grade) = toString($grade))
          AND k.bo_sach = $bo_sach
          AND ($subject IS NULL OR k.subject_code = $subject)
          AND c.name_norm IS NOT NULL AND size(c.name_norm) >= 3
        WITH k, c, $q_folded AS q
        WITH k, c, q, [w IN split(c.name_norm,' ') WHERE size(w) >= 4] AS cw
        WITH k, c, q, cw, [w IN cw WHERE q CONTAINS w] AS hits
        WHERE q CONTAINS c.name_norm
           OR (size(cw) >= 2 AND size(hits) >= 2)
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, k.subject_code AS subj, c.name AS concept,
               size(c.name_norm) AS clen,
               (CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(hits) END) AS mscore
        ORDER BY
            mscore DESC,
            CASE WHEN k.content_class = 'vietjack_lesson' THEN 0 ELSE 1 END,
            clen DESC, size(k.text) DESC
        LIMIT 3
    """
    try:
        driver = driver_factory()
        with driver.session() as s:
            results = s.run(cypher, grade=grade, bo_sach=bo_sach,
                            subject=subject, q_folded=q_folded).data()
        driver.close()
    except Exception as e:
        print(f"[Concept Exact Error] {e}")
        return ""
    if not results:
        return ""
    contexts = []
    for r in results:
        meta = f"Lớp {r['grade']} | {r['bo_sach']} | {r['subj']}"
        contexts.append(f"\U0001f4d0 {r['title']} ({meta}) [concept: {r['concept']}]\n{(r['text'] or '')[:4000]}")
    return "\n\n".join(contexts)


def query_structured_exact(parsed: Dict[str, Any], *, driver_factory) -> str:
    """Tier A: exact Cypher lookup if structured ref present."""
    if not (parsed.get("bai_no") or parsed.get("trang")):
        return ""

    conds = ["k:KnowledgeChunk", "k.production_ready = true"]
    params = {}

    if parsed.get("lop"):
        conds.append("k.grade = $grade")
        params["grade"] = parsed["lop"]
    if parsed.get("bo_sach") and parsed["bo_sach"] != "LEGACY":
        conds.append("k.bo_sach = $bo_sach")
        params["bo_sach"] = parsed["bo_sach"]
    if parsed.get("subject"):
        conds.append("k.subject_code = $subject")
        params["subject"] = parsed["subject"]

    # Bai_no match — strict (KHÔNG match "bài 14" cho query "bài 1")
    # Sử dụng CONTAINS với 4 delimiters: "Bài N:", "Bài N ", "Bài N.", "Bài N,"
    # I4 — also match diacritic-folded variants of the title (e.g. "bai 1:")
    if parsed.get("bai_no"):
        n = parsed["bai_no"]
        conds.append(
            "(k.lesson_no = $bai_no OR "
            "toLower(k.title) CONTAINS $bai_colon OR "
            "toLower(k.title) CONTAINS $bai_space OR "
            "toLower(k.title) CONTAINS $bai_dot OR "
            "toLower(k.title) ENDS WITH $bai_end OR "
            "toLower(k.title) CONTAINS $bai_colon_folded OR "
            "toLower(k.title) CONTAINS $bai_space_folded OR "
            "toLower(k.title) CONTAINS $bai_dot_folded OR "
            "toLower(k.title) ENDS WITH $bai_end_folded)"
        )
        params["bai_no"] = n
        params["bai_colon"] = f"bài {n}:"
        params["bai_space"] = f"bài {n} "
        params["bai_dot"] = f"bài {n}."
        params["bai_end"] = f"bài {n}"
        # Folded (no diacritic) variants
        params["bai_colon_folded"] = _fold(f"bài {n}:")
        params["bai_space_folded"] = _fold(f"bài {n} ")
        params["bai_dot_folded"] = _fold(f"bài {n}.")
        params["bai_end_folded"] = _fold(f"bài {n}")

    # Trang match — title contains "trang N" (raw or folded)
    if parsed.get("trang"):
        trang_text = f"trang {parsed['trang']}"
        conds.append(
            "(toLower(k.title) CONTAINS $trang_text OR "
            "toLower(k.title) CONTAINS $trang_text_folded)"
        )
        params["trang_text"] = trang_text
        params["trang_text_folded"] = _fold(trang_text)

    # I1 — Prefer vietjack source + earliest chunk_index for stable Tier A ordering.
    cypher = f"""
        MATCH (k)
        WHERE {' AND '.join(conds)}
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, k.lesson_no AS lesson_no, k.subject_code AS subj
        ORDER BY
            CASE WHEN k.lesson_no = $bai_no_strict THEN 0 ELSE 1 END,
            CASE WHEN coalesce(k.source,'') CONTAINS 'vietjack' THEN 0 ELSE 1 END,
            coalesce(k.chunk_index, 999) ASC,
            size(k.text) DESC
        LIMIT 3
    """
    params["bai_no_strict"] = parsed.get("bai_no")

    try:
        driver = driver_factory()
        with driver.session() as s:
            results = s.run(cypher, **params).data()
        driver.close()
    except Exception as e:
        print(f"[Tier A Cypher Error] {e}")
        return ""

    if not results:
        return ""

    contexts = []
    for r in results:
        meta = f"Lớp {r['grade']} | {r['bo_sach']} | {r['subj']}"
        text_trim = (r["text"] or "")[:4000]
        contexts.append(f"📌 {r['title']} ({meta})\n{text_trim}")

    return "\n\n".join(contexts)
