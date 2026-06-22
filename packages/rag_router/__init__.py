"""rag_router — orchestrator for the thin companion RAG server.

Exports the behavior-preserving `retrieve()` orchestrator (Phase 3a). The serving
layer (`apps/companion_api/server.py`) injects runtime instances (BGE model,
Neo4j driver factory, bound `classify_intent`, the Pydantic response class, and
`lines_payload`). Importing this package loads NO model and opens NO connection.
"""
from __future__ import annotations

from .orchestrator import retrieve

__all__ = ["retrieve"]
