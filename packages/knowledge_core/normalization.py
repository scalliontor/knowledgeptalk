"""Pure text-normalization helpers for the PTalk RAG core.

EXTRACTED VERBATIM from /tmp/refsrc_canary.py (canary rag_server). No behavior
changes: function bodies are byte-for-byte copies; only the imports needed to
make this a standalone, side-effect-free module were added. No model load, no
Neo4j/Qdrant/HTTP connections at import time.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# I4 — Diacritic folding helper (graceful fallback if unidecode not installed)
try:
    from unidecode import unidecode
except ImportError:
    def unidecode(s):
        return s  # graceful fallback


def _fold(s: str) -> str:
    """Lowercase + strip Vietnamese diacritics (self-contained: đ→d + NFD strip; matches name_norm)."""
    s = (s or "").replace("đ", "d").replace("Đ", "D").replace("–", "-")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


# I3 — Book series alias normalizer
BOOK_ALIASES = {
    "kntt": "KNTT", "k.n.t.t": "KNTT", "ket noi": "KNTT",
    "kết nối": "KNTT", "kết nối tri thức": "KNTT",
    "kntt voi cuoc song": "KNTT", "kt": "KNTT",
    "ctst": "CTST", "chan troi": "CTST",
    "chân trời": "CTST", "chân trời sáng tạo": "CTST", "ct st": "CTST",
    "cd": "CD", "canh dieu": "CD",
    "cánh diều": "CD", "cánh-diều": "CD",
}


def _normalize_book_token(tok: str) -> Optional[str]:
    if not tok:
        return None
    low = tok.lower().strip()
    return BOOK_ALIASES.get(low)


def normalize_text(value: str) -> str:
    """Normalize Vietnamese text for accent-insensitive lookup."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_recite_title(title):
    """Extract poem/work title from a query-like string."""
    t = title.strip()
    t = re.sub(r"(?i)^(đọc|hay đọc|hãy đọc|đọc cho|kể|ngâm|recite)\s+", "", t, count=1).strip()
    t = re.sub(r"(?i)^(bài thơ|văn bản|bài|tác phẩm|đoạn trích)\s+", "", t, count=1).strip()
    t = re.sub(r"(?i)\s+của\s+(tác giả\s+)?[^,]+$", "", t).strip()
    t = t.strip(" .!?\"'")
    return t if t else title
