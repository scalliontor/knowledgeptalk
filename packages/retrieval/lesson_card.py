"""Companion "Lesson Card" retrieval — the anchored serve path.

EXTRACTED VERBATIM from /tmp/refsrc_canary.py (`query_lesson_card`). The Cypher
strings, the content-vector similarity loop, the gate
`bs>=0.50 AND ((bs-bs2)>=0.04 OR bs>=0.60)`, the recite/practice/companion branch
logic, and every emitted intent dict are byte-for-byte copies of the source.

Refactor deviations (documented, behavior-preserving):

  - `GraphDatabase.driver(...)` -> INJECTED `driver_factory()` (zero-arg callable
    returning a fresh driver; preserves per-call create/`.close()` lifecycle).
    `neo4j_uri`/`neo4j_auth` are ALSO accepted for callers that want the package
    to build the driver itself (a default factory is derived from them when
    `driver_factory` is None) — see `_make_driver_factory`.
  - BGE model INJECTED as `model` (was global `bge_m3_model`). The original guard
    `bge_m3_model is not None` becomes `model is not None`.
  - `fold` (=_fold), `is_recite` (=_is_recite), `sanitize` (=sanitize_chunk_text),
    and `classify_intent` are INJECTED callables. `classify_intent` MUST be a
    1-arg callable `classify_intent(query)` — the server binds the BGE model and
    precomputed intent embeddings, reproducing the monolith's global
    `_classify_intent(query)` exactly. `_PRACTICE_RE` is imported from
    knowledge_core (it was a module global next to `sanitize_chunk_text`).

  - The content-vector top1/top2 selection loop is factored into the PURE helper
    `_pick_content_vec(cands, qv)` so the gate can be unit-tested WITHOUT a DB or
    model. It returns `(best, bs, bs2)`; the caller applies the identical gate and
    the identical `print(...)` side-effects, so behavior is unchanged.

No import-time IO.
"""
from __future__ import annotations

import json
import unicodedata

from neo4j import GraphDatabase

from knowledge_core import _PRACTICE_RE


def _make_driver_factory(driver_factory, neo4j_uri, neo4j_auth):
    """Resolve a zero-arg driver factory.

    If `driver_factory` is provided, use it as-is. Otherwise build one from
    `neo4j_uri`/`neo4j_auth` that mirrors the monolith's per-call
    `GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)`.
    """
    if driver_factory is not None:
        return driver_factory
    return lambda: GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)


def _pick_content_vec(cands, qv):
    """PURE: pick best/top1/top2 by dot-product similarity over candidate embeddings.

    Byte-for-byte equivalent to the selection loop in the source content-vector
    block (lines around `best=None; bs=-1.0; bs2=-1.0`). Returns `(best, bs, bs2)`
    where `best` is the candidate dict with the highest similarity (`bs`) and
    `bs2` is the runner-up similarity. `qv` is the query embedding (list of float),
    each candidate's embedding is in `c["emb"]`. Candidates with falsy `emb` are
    skipped, exactly as the source `if not e: continue`.

    No DB, no model — directly unit-testable.
    """
    best = None
    bs = -1.0
    bs2 = -1.0
    for c in cands:
        e = c.get("emb")
        if not e:
            continue
        sim = sum(x * y for x, y in zip(qv, e))
        if sim > bs:
            bs2 = bs
            bs = sim
            best = c
        elif sim > bs2:
            bs2 = sim
    return best, bs, bs2


def query_lesson_card(user_profile, parsed, query, *,
                      driver_factory=None, model,
                      fold, classify_intent, is_recite, sanitize,
                      neo4j_uri=None, neo4j_auth=None):
    """Companion: nếu profile.current_lesson hoặc query nêu tên 1 bài có :Lesson -> trả Lesson Card.

    Refactor: `_fold`->fold, `_classify_intent`->classify_intent (1-arg),
    `_is_recite`->is_recite, `sanitize_chunk_text`->sanitize, `bge_m3_model`->model,
    driver from `driver_factory` (or built from neo4j_uri/neo4j_auth). Body verbatim.
    """
    _df = _make_driver_factory(driver_factory, neo4j_uri, neo4j_auth)
    up = user_profile or {}
    cur = up.get("current_lesson") or up.get("bai_dang_hoc") or ""
    grade = parsed.get("lop"); book = parsed.get("bo_sach")
    subj_f = parsed.get("subject")
    cur_norm = fold(cur) if cur else ""
    qf = fold(query)
    cy = """
        MATCH (l:Lesson)
        WHERE ($grade IS NULL OR l.grade=$grade)
          AND ($book IS NULL OR l.bo_sach=$book)
          AND ($tap IS NULL OR l.tap_no=$tap)
          AND ($subject IS NULL OR l.subject_code=$subject)
          AND ( ($cur_norm <> '' AND l.work_name_norm=$cur_norm)
                OR ($cur_norm = '' AND size(l.work_name_norm)>=5 AND $qf CONTAINS l.work_name_norm)
                OR ($trang IS NOT NULL AND l.trang_from IS NOT NULL AND l.trang_from<=$trang AND $trang<=l.trang_to) )
        MATCH (l)-[:HAS_THEORY]->(t:KnowledgeChunk)
        OPTIONAL MATCH (l)-[:HAS_RECITE]->(lt:LiteratureText)
        WITH l, t, count(lt) AS recite, collect(coalesce(lt.full_text, lt.text))[0] AS recite_text, size(l.work_name_norm) AS wlen,
             (CASE WHEN ($cur_norm<>'' AND l.work_name_norm=$cur_norm) THEN 2
                   WHEN ($cur_norm='' AND size(l.work_name_norm)>=5 AND $qf CONTAINS l.work_name_norm) THEN 2
                   ELSE 1 END) AS prio
        RETURN l.work_name AS work, l.trang_no AS trang, l.subject_code AS subj,
               t.text AS theory, t.guiding_questions AS gq, recite, recite_text, l.practice_json AS practice_json
        ORDER BY prio DESC, wlen DESC LIMIT 1
    """
    try:
        driver = _df()
        with driver.session() as s:
            rec = s.run(cy, grade=grade, book=book, cur_norm=cur_norm, qf=qf, trang=parsed.get('trang'), tap=(user_profile or {}).get('tap') or (user_profile or {}).get('tap_no'), subject=subj_f).single()
        driver.close()
    except Exception as e:
        print(f"[Lesson Card Error] {e}")
        return None
    if not rec:
        # CONTENT-VECTOR: không có neo tên/trang -> match ngữ nghĩa trên theory embeddings (mô tả nội dung -> ra bài)
        if grade and book and model is not None and len((query or '').split())>=3:
            try:
                tap = (user_profile or {}).get('tap') or (user_profile or {}).get('tap_no')
                qv = model.encode([query], normalize_embeddings=True)[0].tolist()
                drv = _df()
                with drv.session() as _s:
                    cand = _s.run("""MATCH (l:Lesson)-[:HAS_THEORY]->(t:KnowledgeChunk)
                        WHERE l.grade=$g AND l.bo_sach=$b AND ($tap IS NULL OR l.tap_no=$tap) AND ($subject IS NULL OR l.subject_code=$subject) AND t.embedding IS NOT NULL
                        RETURN l.work_name AS work, l.trang_no AS trang, l.subject_code AS subj,
                               t.text AS theory, t.guiding_questions AS gq, t.embedding AS emb,
                               l.practice_json AS practice_json,
                               [(l)-[:HAS_RECITE]->(lt) | lt.full_text][0] AS recite_text""",
                        g=grade,b=book,tap=tap,subject=subj_f).data()
                drv.close()
                best, bs, bs2 = _pick_content_vec(cand, qv)
                if best is not None: print(f"[content-vec] top1={bs:.3f} top2={bs2:.3f} -> {best.get('work')}")
                if best is not None and bs>=0.50 and ((bs-bs2)>=0.04 or bs>=0.60):
                    best['recite']=1 if best.get('recite_text') else 0
                    print(f"[RAG] content-vec hit {best.get('work')} sim={bs:.3f}")
                    rec=best
            except Exception as _e:
                print(f"[content-vec] {_e}")
        if not rec:
            return None
    _qlow = (query or "").lower()
    _im = classify_intent(query)
    if (is_recite(_qlow) or _im == "recite") and rec.get("recite_text"):
        rctx = unicodedata.normalize('NFC', "[ĐỌC THUỘC - NGUYÊN VĂN]\nNguồn chính:\n" + (rec["work"] or "") + "\n\n" + rec["recite_text"])
        return {"context": rctx, "intent": {"need_rag": True, "subject": rec["subj"], "grade": grade, "bo_sach": book, "query_type": "recite_full_text", "tier": "lesson_recite", "work_name": rec["work"]}}
    if (_PRACTICE_RE.search(_qlow) or _im == "practice") and rec.get("practice_json"):
        try:
            _ex = json.loads(rec["practice_json"])
        except Exception:
            _ex = []
        if _ex:
            _L = ["[LUYỆN TẬP - ĐỒNG HÀNH] " + (rec["work"] or ""),
                  "(Đưa từng câu hỏi kèm gợi ý cho học sinh thử; CHỈ hé đáp án khi học sinh đã thử hoặc yêu cầu.)"]
            for _e in _ex:
                _L.append("\n" + str(_e.get("cau","")) + ": " + str(_e.get("cau_hoi","")))
                _L.append("  Gợi ý: " + str(_e.get("goi_y","")))
                _L.append("  [Đáp án — chỉ hé khi cần]: " + str(_e.get("dap_an","")))
            pctx = unicodedata.normalize('NFC', "\n".join(_L))
            return {"context": pctx, "intent": {"need_rag": True, "subject": rec["subj"], "grade": grade, "bo_sach": book, "query_type": "practice", "delivery_mode": "guided_practice", "tier": "lesson_practice", "work_name": rec["work"]}}
    parts = [sanitize(rec["theory"])]
    try:
        gq = json.loads(rec["gq"]) if rec["gq"] else []
    except Exception:
        gq = []
    if gq:
        parts.append("Câu hỏi gợi mở:\n- " + "\n- ".join(gq))
    if rec["recite"]:
        parts.append("(Có bản nguyên văn để đọc thuộc.)")
    ctx = unicodedata.normalize('NFC', "[ĐỒNG HÀNH BÀI HỌC]\nNguồn chính:\n" + "\n\n".join(parts))
    intent = {"need_rag": True, "subject": rec["subj"], "grade": grade, "bo_sach": book,
              "query_type": "companion", "learning_mode": "tutor", "tier": "lesson_card",
              "work_name": rec["work"], "trang": rec["trang"]}
    return {"context": ctx, "intent": intent}
