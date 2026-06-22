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
# Phase 3a: orchestration extracted VERBATIM into `packages/rag_router`. The thin
# server now just wires runtime instances into it; the branch order/labels/logs
# live (byte-faithful, incl. the U+1EEC "DỬ" concept-label typo) in
# `rag_router.orchestrator.retrieve`.
from rag_router import retrieve as _orchestrate  # noqa: E402


async def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    return await _orchestrate(
        req,
        model=bge_m3_model,
        driver_factory=_driver_factory,
        classify_intent=_classify_intent,
        response_cls=RetrieveResponse,
        lines_payload=lines_payload,
    )


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
