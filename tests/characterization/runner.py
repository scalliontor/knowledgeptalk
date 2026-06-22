"""Pure evaluation of knowledge_core over the characterization corpus.

`compute_record(query, profile)` returns a fully JSON-serializable dict of every
behavior we want to lock. Shared by the snapshot generator and the test so the
golden file and the live computation use the IDENTICAL function. No model, no
DB, no IO (besides the corpus loader, which only reads local backtest JSON).
"""
from __future__ import annotations

import sys
import os
from typing import Any, Dict, Optional

# Make `import knowledge_core` work without installing the package.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_PKGS = os.path.join(_REPO, "packages")
if _PKGS not in sys.path:
    sys.path.insert(0, _PKGS)

import knowledge_core as kc  # noqa: E402


def compute_record(query: str, profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluate the pure surface of knowledge_core for one input pair."""
    q_lower = query.lower()

    rec: Dict[str, Any] = {
        "query": query,
        "profile": profile,
        "fold": kc._fold(query),
        "normalize_text": kc.normalize_text(query),
        "clean_recite_title": kc.clean_recite_title(query) if query.strip() else "",
        "parse_structured_query": kc.parse_structured_query(query, profile),
        "route_query_rule_based": kc.route_query_rule_based(query),
        "is_recite": kc._is_recite(q_lower),
        "canonicalize_subject_none": kc.canonicalize_subject(None, query),
        "canonicalize_subject_toan": kc.canonicalize_subject("toan", query),
        "override_subject_none": kc.override_subject_by_keywords(query, None),
        "override_subject_van": kc.override_subject_by_keywords(query, "ngu_van"),
        "detect_learning_mode": kc.detect_learning_mode(query),
        "sanitize_chunk_text": kc.sanitize_chunk_text(query),
        "practice_re_match": bool(kc._PRACTICE_RE.search(q_lower)),
    }
    return rec
