"""rag_router — orchestrator extracted from the thin companion server.

Behavior-preserving extraction (Phase 3a): `retrieve()` below is a byte-for-byte
copy of the orchestration that previously lived INLINE in
`apps/companion_api/server.py` (which itself mirrored the monolith
`rag_server_canary.py`). Every branch, condition, ordering, label string, and
log line is preserved verbatim — any behavioral difference is a bug.

Deviations are purely dependency-injection so this module imports clean (NO model
load, NO Neo4j/Qdrant/HTTP at import):
  - the serving layer injects runtime instances via keyword-only params:
    `model` (BGE), `driver_factory` (zero-arg Neo4j driver factory),
    `classify_intent` (1-arg bound callable), `response_cls` (the Pydantic
    `RetrieveResponse`), and `lines_payload` (RetrieveResponse-returning helper);
  - the global `bge_m3_model` -> `model`, `_driver_factory` -> `driver_factory`,
    `_classify_intent` -> `classify_intent`, `RetrieveResponse(...)` ->
    `response_cls(...)`. Nothing else changed.

⚠️ The concept-tier label uses U+1EEC ("DỬ") — a source typo in the monolith —
while the exact-tier label uses U+1EEE ("DỮ"). Both are preserved BYTE-FAITHFULLY
for parity. Do NOT "fix" the typo.
"""
from __future__ import annotations

import os
import unicodedata

from knowledge_core import (
    parse_structured_query,
    route_query_rule_based,
    detect_learning_mode,
    canonicalize_subject,
    override_subject_by_keywords,
    trim_context,
    _fold,
    _is_recite,
    sanitize_chunk_text,
)
from retrieval import (
    query_lesson_card,
    query_structured_exact,
    query_concept_exact,
    query_neo4j_knowledge_chunk,
    query_neo4j_lesson_guide,
    query_neo4j_vector,
    query_qdrant,
    recite_from_literature_text,
    recite_from_reading_text,
    recite_from_full_document,
    SUBJECT_TO_QDRANT,
)


# Neo4j config — same env-derived constants the serving layer uses (server.py).
# `query_lesson_card` is always called with an explicit `driver_factory`, so these
# are NOT used to build a driver (see retrieval.lesson_card._make_driver_factory);
# they are passed through ONLY to keep the call-site byte-identical to the monolith.
NEO4J_URI = os.environ.get("EDU_NEO4J_URI", "bolt://localhost:7688")
NEO4J_AUTH = ("neo4j", os.environ.get("EDU_NEO4J_PW", ""))


async def retrieve(
    req,
    *,
    model,
    driver_factory,
    classify_intent,
    response_cls,
    lines_payload,
):
    print(f"\n[RAG] Nhận request: {req.query}")

    # ── TIER A: Structured exact lookup ────────────────────
    parsed = parse_structured_query(req.query, req.user_profile)
    print(f"[RAG] Parsed: {parsed}")

    # ── COMPANION: lesson-anchored ──
    lc = query_lesson_card(
        req.user_profile, parsed, req.query,
        driver_factory=driver_factory, model=model,
        fold=_fold, classify_intent=classify_intent,
        is_recite=_is_recite, sanitize=sanitize_chunk_text,
        neo4j_uri=NEO4J_URI, neo4j_auth=NEO4J_AUTH,
    )
    if lc:
        print(f"[RAG] Lesson Card hit: {lc['intent'].get('work_name')}")
        return response_cls(context=lc["context"], intent=lc["intent"], sources=["lesson_card"])

    if parsed.get("bai_no") or parsed.get("trang"):
        tier_a_ctx = query_structured_exact(parsed, driver_factory=driver_factory)
        if tier_a_ctx:
            print(f"[RAG] Tier A hit ({len(tier_a_ctx)} chars)")
            intent_a = {
                "need_rag": True,
                "subject": parsed.get("subject"),
                "grade": parsed.get("lop"),
                "bo_sach": parsed.get("bo_sach"),
                "query_type": "explain",
                "learning_mode": "tutor",
                "tier": "A_structured",
                "bai_no": parsed.get("bai_no"),
                "trang": parsed.get("trang"),
            }
            ctx = unicodedata.normalize('NFC', f"[DỮ LIỆU EXACT - TIER A]\nNguồn chính:\n{tier_a_ctx}")
            return response_cls(context=ctx, intent=intent_a, sources=["tier_a_structured"])

    # ── TIER A-concept ──
    if not (parsed.get("bai_no") or parsed.get("trang")) and parsed.get("lop") and parsed.get("bo_sach"):
        concept_ctx = query_concept_exact(parsed, req.query, driver_factory=driver_factory)
        if concept_ctx:
            print(f"[RAG] Tier A-concept hit ({len(concept_ctx)} chars)")
            intent_c = {
                "need_rag": True, "subject": parsed.get("subject"),
                "grade": parsed.get("lop"), "bo_sach": parsed.get("bo_sach"),
                "query_type": "explain", "learning_mode": "tutor", "tier": "A_concept",
            }
            # NOTE: byte-faithful to monolith — concept label uses U+1EEC ("DỬ", a source
            # typo) + escaped form, unlike the other labels' literal "DỮ". Preserved for parity.
            ctx = unicodedata.normalize('NFC', f"[DỬ LIỆU CONCEPT - TIER A]\nNguồn ch\xednh:\n{concept_ctx}")
            return response_cls(context=ctx, intent=intent_c, sources=["tier_a_concept"])

    # 1. Router (Gemma-FREE rule-based)
    intent = route_query_rule_based(req.query)
    intent.update({k: v for k, v in parsed.items() if v is not None and k in ("lop", "bo_sach")})
    if parsed.get("lop"):
        intent["grade"] = parsed["lop"]
    if parsed.get("subject") and not intent.get("subject"):
        intent["subject"] = parsed["subject"]

    # 1.1 Enrich intent
    intent["learning_mode"] = detect_learning_mode(req.query)
    intent["subject"] = canonicalize_subject(intent.get("subject"), req.query)
    intent["subject"] = override_subject_by_keywords(req.query, intent.get("subject"))
    print(f"[RAG] Ý định: {intent}")

    if intent.get("need_rag") is False:
        return response_cls(context="", intent=intent, sources=[])

    keyword = intent.get("keyword", "")

    # 2. Retrieval
    grade = intent.get("grade")
    subject = intent.get("subject")
    subject_str = (subject or "").lower()

    context_parts = []
    sources = []

    if intent.get("delivery_mode") == "full_recitation" or intent.get("query_type") == "recite_full_text":
        title = intent.get("title") or intent.get("keyword", "")
        grade = intent.get("grade")
        bo_sach = intent.get("bo_sach")
        print(f"[RAG] Full Recitation: Tìm bài '{title}'")
        recitation = (
            recite_from_literature_text(title, intent, grade=grade, bo_sach=bo_sach,
                                        driver_factory=driver_factory, lines_payload=lines_payload)
            or recite_from_reading_text(title, grade=grade, bo_sach=bo_sach,
                                        driver_factory=driver_factory, lines_payload=lines_payload)
            or recite_from_full_document(title, intent, grade=grade, bo_sach=bo_sach,
                                         driver_factory=driver_factory, lines_payload=lines_payload)
        )
        if recitation:
            recitation.context = unicodedata.normalize('NFC', recitation.context)
            return recitation
        intent["delivery_mode"] = "explanation"

    neo4j_chunk_data = query_neo4j_knowledge_chunk(intent, driver_factory=driver_factory, model=model)
    if neo4j_chunk_data:
        print("[RAG] Found data in Neo4j KnowledgeChunk")
        context_parts.append("[DỮ LIỆU CẤU TRÚC - NEO4J KNOWLEDGE CHUNK]\nNguồn chính:\n" + neo4j_chunk_data)
        sources.append("neo4j_knowledge_chunk")

    lg_data = query_neo4j_lesson_guide(intent, driver_factory=driver_factory, model=model)
    if lg_data:
        print("[RAG] Found data in Neo4j LessonGuide")
        context_parts.append("[DỮ LIỆU HƯỚNG DẪN - NEO4J LESSON GUIDE]\nNguồn bổ sung:\n" + lg_data)
        sources.append("neo4j_lesson_guide")

    if not context_parts:
        if subject_str in SUBJECT_TO_QDRANT:
            print(f"[RAG] Routing to Qdrant fallback based on subject: {subject_str}")
            qdrant_data = query_qdrant(intent, model=model)
            if qdrant_data:
                context_parts.append("[DỮ LIỆU VECTOR - QDRANT FALLBACK]\nNguồn chính:\n" + qdrant_data)
                sources.append("qdrant_vector_fallback")
        else:
            print(f"[RAG] Routing to Neo4j FullDocument vector fallback based on subject: {subject_str}")
            neo4j_data = query_neo4j_vector(intent, driver_factory=driver_factory, model=model)
            if neo4j_data:
                context_parts.append("[DỮ LIỆU CẤU TRÚC - NEO4J VECTOR FALLBACK]\nNguồn chính:\n" + neo4j_data)
                sources.append("neo4j_vector_fallback")

    final_context = "\n\n".join(context_parts)
    if not final_context:
        final_context = "Hệ thống RAG chưa tìm thấy dữ liệu nội bộ phù hợp cho câu hỏi này."

    final_context = trim_context(final_context, intent.get("learning_mode", "explain"))
    final_context = unicodedata.normalize('NFC', final_context)

    return response_cls(context=final_context, intent=intent, sources=sources)
