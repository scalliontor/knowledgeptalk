"""Chunk-text sanitization + practice-intent regex.

EXTRACTED VERBATIM from /tmp/refsrc_canary.py (the COMPANION / Lesson Card
block). `_LESSON_NOISE`, `sanitize_chunk_text`, and `_PRACTICE_RE` are
byte-for-byte copies. Pure: only depends on `re`.
"""
from __future__ import annotations

import re


# ── COMPANION (Lesson Card) + sanitize ─────────────────────────────
_LESSON_NOISE = [
    r"\(Giáo viên VietJack\)", r"Cô [A-ZÀ-Ỹ][^\n]*\(Giáo viên[^\n]*\)",
    r"Xem lời giải", r"Xem chi tiết", r"Bài giảng:[^\n]*",
    r"Toán - Văn - Anh[^\n]*", r"Giải sgk[^\n]*", r"Quảng cáo",
    r"Giải bài nhanh với AI Hay", r"20\+ Mẫu[^\n]*",
]


def sanitize_chunk_text(t: str) -> str:
    t = t or ""
    for p in _LESSON_NOISE:
        t = re.sub(p, "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


_PRACTICE_RE = re.compile(r"(làm bài tập|luyện tập|giải câu|giải bài|làm câu|bài tập|chữa bài|trả lời câu|soạn câu|tự kiểm tra|câu hỏi để|câu hỏi ôn|ôn lại|thực hành|kiểm tra lại|luyện)")
