"""knowledge_core — pure (IO-free) RAG core extracted from rag_server_canary.py.

Behavior-preserving extraction: every function body is a byte-for-byte copy from
/tmp/refsrc_canary.py. The only deviations (documented per-module) are:
  - functions that needed the BGE model now take `model` as a parameter
    (`intent.classify_intent`, `intent.build_intent_emb`);
  - `routing.route_query` takes `call_gemma` as an injected callable;
  - `payload`: the `RetrieveResponse`-returning `lines_payload` stays in the
    serving layer; only the pure dict builder is here.

Importing this package loads NO model and opens NO Neo4j/Qdrant/HTTP connection.
Tests run fully local, no server.
"""
from __future__ import annotations

from .normalization import (
    unidecode,
    _fold,
    BOOK_ALIASES,
    _normalize_book_token,
    normalize_text,
    clean_recite_title,
)
from .parsing import (
    _SUBJECT_KW,
    parse_structured_query,
)
from .routing import (
    _RECITE_STRONG,
    _RECITE_VERB,
    _RECITE_NOUN,
    _NOT_RECITE,
    _is_recite,
    route_query_rule_based,
    route_query,
)
from .subject import (
    SUBJECT_ALIASES,
    canonicalize_subject,
    MATH_FORCE_KEYWORDS,
    KHTN_FORCE_KEYWORDS,
    LICHSU_FORCE_KEYWORDS,
    VANHOC_FORCE_KEYWORDS,
    override_subject_by_keywords,
    detect_learning_mode,
    CONTEXT_LIMITS,
    trim_context,
)
from .sanitize import (
    _LESSON_NOISE,
    sanitize_chunk_text,
    _PRACTICE_RE,
)
from .intent import (
    _INTENT_ANCHORS,
    build_intent_emb,
    classify_intent,
)
from .payload import (
    build_lines_payload_dict,
)

__all__ = [
    # normalization
    "unidecode", "_fold", "BOOK_ALIASES", "_normalize_book_token",
    "normalize_text", "clean_recite_title",
    # parsing
    "_SUBJECT_KW", "parse_structured_query",
    # routing
    "_RECITE_STRONG", "_RECITE_VERB", "_RECITE_NOUN", "_NOT_RECITE",
    "_is_recite", "route_query_rule_based", "route_query",
    # subject
    "SUBJECT_ALIASES", "canonicalize_subject",
    "MATH_FORCE_KEYWORDS", "KHTN_FORCE_KEYWORDS", "LICHSU_FORCE_KEYWORDS",
    "VANHOC_FORCE_KEYWORDS", "override_subject_by_keywords",
    "detect_learning_mode", "CONTEXT_LIMITS", "trim_context",
    # sanitize
    "_LESSON_NOISE", "sanitize_chunk_text", "_PRACTICE_RE",
    # intent
    "_INTENT_ANCHORS", "build_intent_emb", "classify_intent",
    # payload
    "build_lines_payload_dict",
]
