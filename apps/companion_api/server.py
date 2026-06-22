"""THIN companion API server — SKELETON for the THIN-SERVER + CORE-IN-REPO refactor.

This is the proposed replacement for the monolith `rag_server_canary.py`. It owns
ONLY: (a) FastAPI app + endpoints, (b) process init (load BGE, build Neo4j/Qdrant
deps, precompute intent embeddings), (c) the response type `RetrieveResponse` +
`lines_payload`, and (d) wiring that calls into `knowledge_core` + `retrieval`.
All RAG logic (parsing/routing/anchoring/Cypher/scoring) lives in the packages and
is byte-for-byte the monolith's behavior.

⚠️ STATUS: SKELETON. It py_compiles clean and the wiring mirrors the monolith's
`retrieve()` orchestration, but it is NOT yet verified end-to-end against a live
server. TODO markers flag the spots that must be reconciled on the server before
this can replace the monolith. The `rag_router.retrieve()` orchestrator referenced
in the canonical plan is NOT yet extracted — until it is, `api_retrieve` below
inlines the same orchestration the monolith's `retrieve()` does (see TODO ORCH).

Run (server, temporary port — see docs/refactor/migration-plan.md):
    PYTHONPATH=/path/to/repo/packages uvicorn apps.companion_api.server:app \
        --host 0.0.0.0 --port 8891
"""
from __future__ import annotations

import json
import os
import unicodedata
from typing import Dict, Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel
from neo4j import GraphDatabase

# ── core (pure) + retrieval (IO, deps injected) ────────────────────
import knowledge_core as kc
from knowledge_core import (
    parse_structured_query,
    route_query_rule_based,
    detect_learning_mode,
    canonicalize_subject,
    override_subject_by_keywords,
    trim_context,
    sanitize_chunk_text,
    _fold,
    _is_recite,
    build_intent_emb,
    classify_intent as _classify_intent_core,
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


# ── CONFIG (from env; server .env supplies values — per CLAUDE.md no literal secrets) ────
LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:8080/v1/chat/completions")
LLM_API_KEY = os.environ.get("GEMMA_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma-4")

NEO4J_URI = os.environ.get("EDU_NEO4J_URI", "bolt://localhost:7688")
NEO4J_AUTH = ("neo4j", os.environ.get("EDU_NEO4J_PW", ""))


# ── GLOBAL MODEL + DEPS (init at process start, NOT at import of packages) ──
os.environ['HF_HOME'] = "/home/namnx/.cache/huggingface"
from sentence_transformers import SentenceTransformer  # noqa: E402

print("[RAG SERVER] Đang tải mô hình BAAI/bge-m3 lên VRAM...")
bge_m3_model = SentenceTransformer("BAAI/bge-m3")
print("[RAG SERVER] Tải mô hình hoàn tất!")

# Precompute intent anchor embeddings (was module-global _INTENT_EMB in monolith).
_INTENT_EMB = build_intent_emb(bge_m3_model)


def _driver_factory():
    """Zero-arg factory mirroring monolith's per-call GraphDatabase.driver(...)."""
    return GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)


def _classify_intent(query):
    """1-arg drop-in for the monolith's global `_classify_intent(query)`.

    Binds the BGE model + precomputed embeddings so `query_lesson_card` can be
    handed a callable with the exact original signature.
    """
    return _classify_intent_core(query, bge_m3_model, _INTENT_EMB)


app = FastAPI(title="PTalk RAG Server (thin)", version="2.0")


# ── MODELS (serving-layer; stay out of packages) ───────────────────
class RetrieveRequest(BaseModel):
    query: str
    session_id: Optional[str] = "default"
    user_profile: Optional[Dict[str, Any]] = None


class RetrieveResponse(BaseModel):
    context: str
    intent: Dict[str, Any]
    sources: list


def lines_payload(title: str, lines: list, intent: dict, source: str) -> RetrieveResponse:
    """Verbatim from monolith; injected into `recite_from_*`."""
    return RetrieveResponse(
        context=json.dumps(
            {"type": "full_recitation_lines", "title": title, "lines": lines},
            ensure_ascii=False,
        ),
        intent={**intent, "query_type": "recite_full_text", "title": title},
        sources=[source],
    )


# ── ORCHESTRATION ──────────────────────────────────────────────────
# TODO(ORCH): extract this into `packages/rag_router/retrieve()` (canonical plan).
# Until then it mirrors the monolith's async `retrieve()` exactly — every branch
# below is the same order/condition as /tmp/refsrc_canary.py.
async def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    print(f"\n[RAG] Nhận request: {req.query}")

    # ── TIER A: Structured exact lookup ────────────────────
    parsed = parse_structured_query(req.query, req.user_profile)
    print(f"[RAG] Parsed: {parsed}")

    # ── COMPANION: lesson-anchored ──
    lc = query_lesson_card(
        req.user_profile, parsed, req.query,
        driver_factory=_driver_factory, model=bge_m3_model,
        fold=_fold, classify_intent=_classify_intent,
        is_recite=_is_recite, sanitize=sanitize_chunk_text,
        neo4j_uri=NEO4J_URI, neo4j_auth=NEO4J_AUTH,
    )
    if lc:
        print(f"[RAG] Lesson Card hit: {lc['intent'].get('work_name')}")
        return RetrieveResponse(context=lc["context"], intent=lc["intent"], sources=["lesson_card"])

    if parsed.get("bai_no") or parsed.get("trang"):
        tier_a_ctx = query_structured_exact(parsed, driver_factory=_driver_factory)
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
            return RetrieveResponse(context=ctx, intent=intent_a, sources=["tier_a_structured"])

    # ── TIER A-concept ──
    if not (parsed.get("bai_no") or parsed.get("trang")) and parsed.get("lop") and parsed.get("bo_sach"):
        concept_ctx = query_concept_exact(parsed, req.query, driver_factory=_driver_factory)
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
            return RetrieveResponse(context=ctx, intent=intent_c, sources=["tier_a_concept"])

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
        return RetrieveResponse(context="", intent=intent, sources=[])

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
                                        driver_factory=_driver_factory, lines_payload=lines_payload)
            or recite_from_reading_text(title, grade=grade, bo_sach=bo_sach,
                                        driver_factory=_driver_factory, lines_payload=lines_payload)
            or recite_from_full_document(title, intent, grade=grade, bo_sach=bo_sach,
                                         driver_factory=_driver_factory, lines_payload=lines_payload)
        )
        if recitation:
            recitation.context = unicodedata.normalize('NFC', recitation.context)
            return recitation
        intent["delivery_mode"] = "explanation"

    neo4j_chunk_data = query_neo4j_knowledge_chunk(intent, driver_factory=_driver_factory, model=bge_m3_model)
    if neo4j_chunk_data:
        print("[RAG] Found data in Neo4j KnowledgeChunk")
        context_parts.append("[DỮ LIỆU CẤU TRÚC - NEO4J KNOWLEDGE CHUNK]\nNguồn chính:\n" + neo4j_chunk_data)
        sources.append("neo4j_knowledge_chunk")

    lg_data = query_neo4j_lesson_guide(intent, driver_factory=_driver_factory, model=bge_m3_model)
    if lg_data:
        print("[RAG] Found data in Neo4j LessonGuide")
        context_parts.append("[DỮ LIỆU HƯỚNG DẪN - NEO4J LESSON GUIDE]\nNguồn bổ sung:\n" + lg_data)
        sources.append("neo4j_lesson_guide")

    if not context_parts:
        if subject_str in SUBJECT_TO_QDRANT:
            print(f"[RAG] Routing to Qdrant fallback based on subject: {subject_str}")
            qdrant_data = query_qdrant(intent, model=bge_m3_model)
            if qdrant_data:
                context_parts.append("[DỮ LIỆU VECTOR - QDRANT FALLBACK]\nNguồn chính:\n" + qdrant_data)
                sources.append("qdrant_vector_fallback")
        else:
            print(f"[RAG] Routing to Neo4j FullDocument vector fallback based on subject: {subject_str}")
            neo4j_data = query_neo4j_vector(intent, driver_factory=_driver_factory, model=bge_m3_model)
            if neo4j_data:
                context_parts.append("[DỮ LIỆU CẤU TRÚC - NEO4J VECTOR FALLBACK]\nNguồn chính:\n" + neo4j_data)
                sources.append("neo4j_vector_fallback")

    final_context = "\n\n".join(context_parts)
    if not final_context:
        final_context = "Hệ thống RAG chưa tìm thấy dữ liệu nội bộ phù hợp cho câu hỏi này."

    final_context = trim_context(final_context, intent.get("learning_mode", "explain"))
    final_context = unicodedata.normalize('NFC', final_context)

    return RetrieveResponse(context=final_context, intent=intent, sources=sources)


# ── ENDPOINTS ──────────────────────────────────────────────────────
@app.post("/v2/rag/retrieve")
async def api_retrieve_v2(req: RetrieveRequest):
    return await retrieve(req)


@app.post("/retrieve")
async def api_retrieve(req: RetrieveRequest):
    """Backward compatibility with the old RAG system (legacy response shape)."""
    res = await retrieve(req)
    return {
        "context": res.context,
        "retrieved_sources": len(res.sources) if res.sources else 1,
        "intent": res.intent,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


class ExpandTopicRequest(BaseModel):
    topic: Optional[str] = None
    query: Optional[str] = None
    user_profile: Optional[Dict[str, Any]] = None


@app.post("/v2/moderation/expand-topic")
async def expand_topic(req: ExpandTopicRequest):
    """Moderation / topic-expansion endpoint.

    TODO(moderation): NOT present in rag_server_canary.py — it lives only in the
    SERVER `/tmp/rag_server_merged.py`. The exact request/response contract and
    body must be ported VERBATIM from the merged server before promote (it is the
    "sạch nguồn" invariant + the merged baseline measured in canonical). This stub
    exists only so the thin server exposes the same route surface; do NOT ship it
    as-is. See docs/refactor/migration-plan.md step "Port moderation".
    """
    return {"status": "not_implemented", "detail": "port from rag_server_merged.py"}


if __name__ == "__main__":
    import uvicorn
    import asyncio
    # Temporary port 8891 for side-by-side compare vs monolith on 8890.
    config = uvicorn.Config(app, host="0.0.0.0", port=8891)
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
