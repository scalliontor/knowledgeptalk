"""retrieval — IO-bound RAG retrieval layer extracted from rag_server_canary.py.

Behavior-preserving extraction: every function body, Cypher string, and scoring
expression is a byte-for-byte copy from /tmp/refsrc_canary.py. The deviations
(documented per-module) are purely about dependency injection so the modules
import clean (NO model load, NO Neo4j/Qdrant/Postgres/HTTP connection at import):

  - Neo4j driver: each function takes a `driver_factory()` (zero-arg callable
    returning a fresh driver). `lesson_card` also accepts `neo4j_uri`/`neo4j_auth`
    and builds a default factory from them. This mirrors the monolith's per-call
    `GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)` + `.close()` lifecycle.
  - BGE model: injected as `model` (was global `bge_m3_model`).
  - `lesson_card.query_lesson_card` takes injected callables `fold`,
    `classify_intent` (1-arg), `is_recite`, `sanitize` — all sourced from
    `knowledge_core` and bound by the serving layer.
  - `recite_from_*` build their response via an injected `lines_payload` callable
    (the Pydantic `RetrieveResponse` stays in the serving layer).

Qdrant/psycopg2 clients are imported lazily inside `query_qdrant` (as in source).
"""
from __future__ import annotations

from .lesson_card import query_lesson_card, _pick_content_vec, _make_driver_factory
from .structured import query_structured_exact, query_concept_exact
from .neo4j_queries import (
    query_neo4j_vector,
    query_neo4j_knowledge_chunk,
    query_neo4j_lesson_guide,
    recite_from_literature_text,
    recite_from_reading_text,
    recite_from_full_document,
)
from .vector import query_qdrant, SUBJECT_TO_QDRANT

__all__ = [
    # lesson_card
    "query_lesson_card", "_pick_content_vec", "_make_driver_factory",
    # structured
    "query_structured_exact", "query_concept_exact",
    # neo4j_queries
    "query_neo4j_vector", "query_neo4j_knowledge_chunk", "query_neo4j_lesson_guide",
    "recite_from_literature_text", "recite_from_reading_text", "recite_from_full_document",
    # vector
    "query_qdrant", "SUBJECT_TO_QDRANT",
]
