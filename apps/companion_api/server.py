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
import requests
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


# ── MODERATION (banned-topic expansion) — ported VERBATIM from merged monolith ──
def call_gemma(system_prompt: str, user_prompt: str, max_tokens: int = 150) -> str:
    """Gọi LLM (Gemma-4) qua VLLM API"""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.01,
        "max_tokens": max_tokens
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    try:
        response = requests.post(LLM_API_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"[LLM Error] HTTP {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[LLM Exception] {e}")
    return ""


class TopicExpandRequest(BaseModel):
    topic: str
    max_words: int = 5

class TopicExpandResponse(BaseModel):
    topic: str
    description: str
    words: list

def expand_banned_topic(topic: str, max_words: int = 5) -> "TopicExpandResponse":
    """Expand a banned topic into ~max_words Vietnamese words/phrases via Gemma.
    Returns a TopicExpandResponse; on any failure returns empty words (fail-open)."""
    topic = (topic or "").strip()
    if not topic:
        return TopicExpandResponse(topic=topic, description="", words=[])
    system_prompt = (
        "Bạn là bộ lọc an toàn nội dung cho trẻ em (tiếng Việt). "
        "Cho một CHỦ ĐỀ cần cấm, hãy liệt kê các TỪ/CỤM TỪ tiếng Việt thường gặp "
        "thuộc chủ đề đó mà trẻ có thể nói hoặc hỏi. "
        "Chỉ trả về JSON đúng định dạng, KHÔNG giải thích:\n"
        '{"desc":"<mô tả ngắn 1 câu>","words":["...","..."]}\n'
        f"Tối đa {max_words} từ. Mỗi từ ngắn gọn, viết thường, không trùng lặp."
    )
    raw = call_gemma(system_prompt, topic, max_tokens=256)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw)
        seen, words = set(), []
        for w in (data.get("words") or []):
            w = (w or "").strip().lower()
            if w and w not in seen:
                seen.add(w)
                words.append(w)
            if len(words) >= max_words:
                break
        return TopicExpandResponse(topic=topic, description=data.get("desc", ""), words=words)
    except Exception as e:
        print(f"[expand_banned_topic] parse fail (fail-open): {e} | raw={raw[:120]!r}")
        return TopicExpandResponse(topic=topic, description="", words=[])

@app.post("/v2/moderation/expand-topic")
async def api_expand_topic(req: TopicExpandRequest) -> TopicExpandResponse:
    """Given a banned TOPIC, ask Gemma for ~N Vietnamese words/phrases to block.
    Stateless: persistence + RBAC are the Dashboard's job. Fail-open → words: []."""
    return expand_banned_topic(req.topic, req.max_words)


if __name__ == "__main__":
    import uvicorn
    import asyncio
    # Temporary port 8891 for side-by-side compare vs monolith on 8890.
    config = uvicorn.Config(app, host="0.0.0.0", port=8891)
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
