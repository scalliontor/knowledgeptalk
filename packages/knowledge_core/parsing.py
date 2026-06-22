"""Structured-query parser (Tier A signal extraction).

EXTRACTED VERBATIM from /tmp/refsrc_canary.py. `parse_structured_query` and its
constant `_SUBJECT_KW` are byte-for-byte copies; `_fold` / `BOOK_ALIASES` are
imported from .normalization instead of being defined inline. Pure: no IO, no
model, no DB.
"""
from __future__ import annotations

import re
from typing import Dict, Any

from .normalization import _fold, BOOK_ALIASES


# ── Tier A: Structured-first parsing & exact lookup ────────────────
# Use case: PTalk voice tutor, query có signal mạnh (lop, bo_sach từ device + bài_no, trang từ query)

_SUBJECT_KW = {
    "ngu_van": ["ngữ văn", "soạn văn", "soạn bài", "văn lớp"],
    "khtn": ["khoa học tự nhiên", "khtn"],
    "toan": ["toán", "đại số", "hình học"],
    "tieng_viet": ["tiếng việt"],
    "lich_su": ["lịch sử"],
    "dia_li": ["địa lí", "địa lý"],
    "lich_su_dia_li": ["lịch sử và địa lí", "lịch sử và địa lý"],
    "gdcd": ["giáo dục công dân", "gdcd", "công dân"],
    "tieng_anh": ["tiếng anh", "english"],
    "vat_li": ["vật lí", "vật lý"],
    "hoa_hoc": ["hóa học", "hóa lớp"],
    "sinh_hoc": ["sinh học"],
}


def parse_structured_query(query: str, user_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Extract structured signals từ query + user_profile."""
    user_profile = user_profile or {}
    q_lower = query.lower()

    # User profile (device-known)
    parsed = {
        "lop": user_profile.get("lop") or user_profile.get("grade"),
        "bo_sach": user_profile.get("bo_sach") or user_profile.get("bo_sach_chinh"),
        "subject": user_profile.get("subject") or user_profile.get("mon"),
    }

    # Bài_no from query
    m_bai = re.search(r"\bb[àa]i\s*(\d+)", q_lower)
    parsed["bai_no"] = int(m_bai.group(1)) if m_bai else None

    # Trang from query
    m_trang = re.search(r"\btrang\s*(\d+)", q_lower)
    parsed["trang"] = int(m_trang.group(1)) if m_trang else None
    if parsed["trang"] is None and user_profile and user_profile.get("trang") is not None:
        try: parsed["trang"] = int(user_profile.get("trang"))
        except Exception: pass

    # Câu_no (sometimes used in SBT context)
    m_cau = re.search(r"\bc[âa]u\s*(\d+)", q_lower)
    parsed["cau_no"] = int(m_cau.group(1)) if m_cau else None

    # Subject from query keyword (override profile if found)
    for code, kws in _SUBJECT_KW.items():
        for kw in kws:
            if kw in q_lower:
                parsed["subject"] = code
                break
        if parsed.get("subject"):
            break

    # Grade from query if explicit (override profile)
    m_lop = re.search(r"\bl[ớo]p\s*(\d+)", q_lower)
    if m_lop:
        parsed["lop"] = int(m_lop.group(1))

    # Series detection from query
    if "kntt" in q_lower or "kết nối tri thức" in q_lower:
        parsed["bo_sach"] = "KNTT"
    elif "ctst" in q_lower or "chân trời sáng tạo" in q_lower:
        parsed["bo_sach"] = "CTST"
    elif "cánh diều" in q_lower or " cd " in q_lower or q_lower.endswith(" cd"):
        parsed["bo_sach"] = "CD"

    # I3 — Scan full BOOK_ALIASES map (handles "ket noi", "chan troi",
    # "canh dieu", "k.n.t.t", etc.). Explicit query token overrides profile.
    q_folded = _fold(query)
    for alias, canon in BOOK_ALIASES.items():
        alias_folded = _fold(alias)
        # Match either raw (with diacritics) or folded form
        if alias in q_lower or (alias_folded and alias_folded in q_folded):
            parsed["bo_sach"] = canon
            break

    return parsed
