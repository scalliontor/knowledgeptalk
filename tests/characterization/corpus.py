"""Deterministic characterization corpus for packages/knowledge_core.

This module is shared by the test (`test_knowledge_core.py`) and the snapshot
generator (`gen_golden.py`) so that the EXACT same inputs produce the golden
file and are asserted against it. Behavior-locking only — no model, no DB.

Sources of inputs:
  - real student utterances mined from the 2026-06-17 full-sweep backtest
    (`reports/backtest/2026-06-17_full-sweep/*.json`, field `sample_fails`,
    where each entry is [case_type, utterance, detail]);
  - synthetic user_profile variants (lop / bo_sach / subject / tap / trang /
    current_lesson);
  - hand-written edge cases (empty, teen/no-diacritics, en-dash "–" vs hyphen
    "-", "đ", Roman numerals, years).

Everything here is pure Python 3.8 and import-clean.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_BACKTEST_DIR = os.path.join(
    _REPO, "reports", "backtest", "2026-06-17_full-sweep"
)

# How many mined real utterances to fold into the corpus. Deterministic slice
# of the sorted-by-first-appearance distinct list (NOT random).
_N_REAL_UTTERANCES = 80


def load_real_utterances(limit: int = _N_REAL_UTTERANCES) -> List[str]:
    """Distinct student utterances from backtest sample_fails, in first-seen
    order across sorted filenames. Deterministic. Returns [] if the backtest
    artifacts are absent (the snapshot still locks the synthetic+edge corpus).
    """
    out: List[str] = []
    seen = set()
    files = sorted(glob.glob(os.path.join(_BACKTEST_DIR, "*.json")))
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                j = json.load(fh)
        except Exception:
            continue
        for sf in (j.get("sample_fails") or []):
            if (
                isinstance(sf, list)
                and len(sf) >= 2
                and isinstance(sf[1], str)
            ):
                u = sf[1].strip()
                if u and u not in seen:
                    seen.add(u)
                    out.append(u)
                    if len(out) >= limit:
                        return out
    return out


# Synthetic user_profile variants covering the structured-first scope axes
# (lop / bo_sach / subject / tap / trang / current_lesson). The empty {} profile
# is the real-world "client sends {}" case called out in the canonical state.
PROFILES: List[Optional[Dict[str, Any]]] = [
    None,
    {},
    {"lop": 8, "bo_sach": "KNTT", "subject": "toan", "tap": 1,
     "trang": 37, "current_lesson": "Hình thang – Hình thang cân"},
    {"grade": 6, "bo_sach_chinh": "CTST", "mon": "khtn",
     "trang": "55", "current_lesson": "Tế bào"},
    {"lop": 9, "bo_sach": "CD", "subject": "ngu_van", "tap": 2,
     "current_lesson": "Truyện Kiều"},
    {"lop": 7, "subject": "lich_su", "trang": 12},
    {"lop": 4, "bo_sach": "CTST", "subject": "toan", "tap": 2,
     "current_lesson": "Phép cộng trong phạm vi 1000"},
    {"trang": None},
    {"lop": "8", "trang": "not-a-number"},
]

# Hand-written edge utterances. These specifically exercise: empty, teen /
# no-diacritics, en-dash vs hyphen, "đ", Roman numerals, years, code-block-ish
# cruft, recite vs not-recite, chitchat, math/khtn/lichsu/vanhoc force keywords.
EDGE_UTTERANCES: List[str] = [
    "",
    "   ",
    "bài 12 trang 37 toán lớp 8 KNTT",
    "soan bai 5 ngu van lop 9 ket noi tri thuc",
    "doc thuoc bai tho nay cho minh nghe",
    "đọc hiểu văn bản này giúp em",
    "Hình thang – Hình thang cân",
    "Hình thang - Hình thang cân",
    "đường tròn nội tiếp đa giác đều",
    "Cách mạng tháng Tám năm 1945",
    "Chiến tranh thế giới thứ II",
    "Chương III bài Lũy thừa với số mũ tự nhiên",
    "chào cậu ơi",
    "cậu đang làm gì đấy",
    "hãy đọc bài thơ Sang thu cho em nghe",
    "ngâm bài thơ Việt Bắc đi nhé",
    "giải bài tập trang 40",
    "phân tích nhân vật trong tác phẩm này",
    "ôn tập kiến thức trọng tâm chương 2",
    "em chưa hiểu vì sao nước biển lại mặn",
    "tính diện tích hình tam giác",
    "nguyên tử và phân tử khác nhau thế nào",
    "khởi nghĩa Hai Bà Trưng diễn ra khi nào",
    "cảm nhận của em về bài thơ",
    "Toán - Văn - Anh 2K7 (Chương trình mới)",
    "soạn câu hỏi 3 trang 88",
]


def _build_raw() -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    """The full ordered list of (query, profile) input pairs. Deterministic."""
    pairs: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    # 1) edge utterances against the empty profile (cheap, isolates query logic)
    for u in EDGE_UTTERANCES:
        pairs.append((u, {}))

    # 2) the structured anchor query against EVERY profile (parse interactions)
    anchor = "bài 12 trang 37 toán lớp 8 KNTT"
    for p in PROFILES:
        pairs.append((anchor, p))

    # 3) a no-signal query against every profile (profile-only field flow)
    bare = "giúp em hiểu bài này với"
    for p in PROFILES:
        pairs.append((bare, p))

    # 4) real mined utterances against the empty profile + one rich profile
    rich = {"lop": 6, "bo_sach": "CTST", "subject": "dia_li",
            "trang": 20, "current_lesson": "Lớp vỏ khí"}
    for u in load_real_utterances():
        pairs.append((u, {}))
        pairs.append((u, rich))

    return pairs


def build_corpus() -> List[Dict[str, Any]]:
    """Return the corpus as a list of {"query","profile"} dicts (JSON-safe)."""
    return [
        {"query": q, "profile": p}
        for (q, p) in _build_raw()
    ]
