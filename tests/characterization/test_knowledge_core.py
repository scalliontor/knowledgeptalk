"""Characterization tests for packages/knowledge_core.

Purpose: LOCK the behavior of the verbatim-extracted RAG core so any future
refactor that changes output is caught. These tests run fully LOCAL — no server,
no BGE model, no Neo4j/Qdrant. Python 3.8 compatible.

Two layers:
  1. Targeted assertions on the contract of each pure function (readable intent).
  2. A whole-corpus snapshot lock against `golden_knowledge_core.json`
     (regression net for refactors).

Functions needing the BGE model (`classify_intent`, `build_intent_emb`) are NOT
exercised here with a real model; a tiny fake-model unit test pins their
injected-dependency contract instead.
"""
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_PKGS = os.path.join(_REPO, "packages")
for _p in (_PKGS, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import knowledge_core as kc  # noqa: E402
from corpus import build_corpus  # noqa: E402
from runner import compute_record  # noqa: E402

_GOLDEN = os.path.join(_HERE, "golden_knowledge_core.json")


# ─────────────────────────── import hygiene ────────────────────────────

def test_package_imports_with_no_model_or_db():
    """Importing knowledge_core must not load BGE or connect to Neo4j/Qdrant.
    (If it did, this collection itself would have failed; we assert the public
    surface is present and callable.)"""
    for name in (
        "_fold", "normalize_text", "clean_recite_title",
        "parse_structured_query", "route_query_rule_based", "_is_recite",
        "canonicalize_subject", "override_subject_by_keywords",
        "detect_learning_mode", "sanitize_chunk_text", "_PRACTICE_RE",
        "classify_intent", "build_intent_emb", "build_lines_payload_dict",
    ):
        assert hasattr(kc, name), "missing public symbol: %s" % name


# ──────────────────────────────── _fold ────────────────────────────────

def test_fold_strips_diacritics_and_lowercases():
    assert kc._fold("Ngữ Văn") == "ngu van"
    assert kc._fold("LỊCH SỬ") == "lich su"


def test_fold_d_special_case():
    assert kc._fold("đ") == "d"
    assert kc._fold("Đường") == "duong"
    assert kc._fold("ĐỌC") == "doc"


def test_fold_en_dash_becomes_hyphen():
    # The exact regression the canonical state calls out: en-dash "–" in
    # work_name_norm vs runtime hyphen.
    assert kc._fold("Hình thang – Hình thang cân") == "hinh thang - hinh thang can"
    # And a plain hyphen folds to the same string -> they MATCH after folding.
    assert kc._fold("Hình thang - Hình thang cân") == kc._fold("Hình thang – Hình thang cân")


def test_fold_idempotent():
    samples = [
        "Hình thang – Hình thang cân", "Đường tròn", "Ngữ Văn 9 — CTST",
        "", "đđ Đ", "Cách mạng tháng Tám 1945",
    ]
    for s in samples:
        once = kc._fold(s)
        assert kc._fold(once) == once, "fold not idempotent on %r" % s


def test_fold_handles_none_and_empty():
    assert kc._fold("") == ""
    assert kc._fold(None) == ""


# ────────────────────────── parse_structured_query ─────────────────────

def test_parse_extracts_all_fields_from_query():
    p = kc.parse_structured_query("bài 12 trang 37 toán lớp 8 KNTT", {})
    assert p["bai_no"] == 12
    assert p["trang"] == 37
    assert p["lop"] == 8
    assert p["subject"] == "toan"
    assert p["bo_sach"] == "KNTT"


def test_parse_trang_falls_back_to_profile_when_absent_in_query():
    prof = {"lop": 8, "bo_sach": "KNTT", "subject": "toan", "trang": 55}
    p = kc.parse_structured_query("giảng bài này cho em", prof)
    assert p["trang"] == 55  # taken from profile
    assert p["lop"] == 8
    assert p["bo_sach"] == "KNTT"
    assert p["subject"] == "toan"
    assert p["bai_no"] is None


def test_parse_query_trang_overrides_profile_trang():
    prof = {"trang": 99}
    p = kc.parse_structured_query("trang 37 nói gì", prof)
    assert p["trang"] == 37


def test_parse_profile_alias_keys():
    # grade / bo_sach_chinh / mon are accepted aliases.
    prof = {"grade": 6, "bo_sach_chinh": "CTST", "mon": "khtn"}
    p = kc.parse_structured_query("hỏi linh tinh", prof)
    assert p["lop"] == 6
    assert p["bo_sach"] == "CTST"
    assert p["subject"] == "khtn"


def test_parse_trang_profile_non_int_does_not_crash():
    p = kc.parse_structured_query("câu hỏi", {"trang": "not-a-number"})
    assert p["trang"] is None


def test_parse_none_profile():
    p = kc.parse_structured_query("bài 3", None)
    assert p["bai_no"] == 3
    assert p["lop"] is None


# ─────────────────────────── route / _is_recite ────────────────────────

def test_route_chitchat():
    r = kc.route_query_rule_based("chào cậu ơi")
    assert r["need_rag"] is False
    assert r["query_type"] == "chat"


def test_route_recite():
    r = kc.route_query_rule_based("hãy đọc bài thơ Sang thu cho em nghe")
    assert r["need_rag"] is True
    assert r["query_type"] == "recite_full_text"
    assert r["subject"] == "ngu_van"


def test_route_explain_default():
    r = kc.route_query_rule_based("giải thích vì sao nước biển mặn")
    assert r["query_type"] == "explain"
    assert r["subject"] is None


def test_is_recite_true_cases():
    assert kc._is_recite("đọc thuộc bài thơ này") is True
    assert kc._is_recite("ngâm bài thơ việt bắc") is True


def test_is_recite_excludes_reading_comprehension():
    # "đọc hiểu" / "phân tích" must NOT be treated as recite.
    assert kc._is_recite("đọc hiểu văn bản này") is False
    assert kc._is_recite("phân tích bài thơ này") is False
    assert kc._is_recite("soạn bài thơ này") is False


# ───────────────────────── canonicalize_subject ────────────────────────

def test_canonicalize_subject_from_query():
    assert kc.canonicalize_subject(None, "giải phương trình bậc hai") == "toan"
    assert kc.canonicalize_subject(None, "phân tích bài thơ") == "ngu_van"
    assert kc.canonicalize_subject(None, "khởi nghĩa hai bà trưng") == "lich_su"


def test_canonicalize_subject_fallback_to_raw():
    assert kc.canonicalize_subject("gdcd", "câu hỏi không khớp alias") == "gdcd"
    assert kc.canonicalize_subject(None, "câu hỏi trung tính") is None


# ──────────────────── override_subject_by_keywords ─────────────────────

def test_override_math_force():
    assert kc.override_subject_by_keywords("tính diện tích hình tam giác", None) == "toan"


def test_override_khtn_force():
    assert kc.override_subject_by_keywords("nguyên tử và phân tử", None) == "khtn"


def test_override_lichsu_force():
    assert kc.override_subject_by_keywords("cuộc khởi nghĩa lớn", None) == "lich_su"


def test_override_vanhoc_only_when_subject_none():
    # Literary keyword -> ngu_van only if subject not already set.
    assert kc.override_subject_by_keywords("cảm nhận của em", None) == "ngu_van"
    # Already set to something non-matching -> unchanged.
    assert kc.override_subject_by_keywords("cảm nhận của em", "toan") == "toan"


# ──────────────────────── detect_learning_mode ─────────────────────────

def test_detect_learning_mode():
    assert kc.detect_learning_mode("ôn tập kiến thức trọng tâm") == "review"
    assert kc.detect_learning_mode("em chưa hiểu, giải thích giúp em") == "tutor"
    assert kc.detect_learning_mode("giải bài tập trang 40") == "solution"
    assert kc.detect_learning_mode("kể cho em nghe câu chuyện") == "tutor"  # default


# ──────────────────────── sanitize_chunk_text ──────────────────────────

def test_sanitize_removes_real_cruft():
    raw = "Định lí Pytago. (Giáo viên VietJack) Xem lời giải để biết thêm."
    out = kc.sanitize_chunk_text(raw)
    assert "Giáo viên VietJack" not in out
    assert "(Giáo viên VietJack)" not in out
    assert "Xem lời giải" not in out
    assert "Định lí Pytago" in out


def test_sanitize_keeps_plain_giao_vien():
    # The canonical-state false-positive guard: a BARE "giáo viên" (valid
    # GDCD/other-subject vocabulary) must be PRESERVED, NOT stripped.
    raw = "Học sinh cần tôn trọng giáo viên và bạn bè trong lớp."
    out = kc.sanitize_chunk_text(raw)
    assert "giáo viên" in out
    assert out == raw  # nothing was removed


def test_sanitize_removes_more_cruft_patterns():
    raw = "Bài học. Quảng cáo Giải sgk Toán 8 Toán - Văn - Anh khoá học."
    out = kc.sanitize_chunk_text(raw)
    assert "Quảng cáo" not in out
    assert "Giải sgk" not in out
    assert "Bài học" in out


def test_sanitize_none_and_empty():
    assert kc.sanitize_chunk_text(None) == ""
    assert kc.sanitize_chunk_text("") == ""


# ─────────────────── classify_intent / build_intent_emb ────────────────

class _Vec(list):
    """List that mimics the numpy `.tolist()` the source calls on each encoded
    vector (`model.encode(...)[0].tolist()`)."""

    def tolist(self):
        return list(self)


class _FakeModel:
    """Deterministic stand-in for the BGE model. encode() returns a fixed
    1-d vector per text so we can pin the injected-dependency contract of
    classify_intent / build_intent_emb without loading any real model. Each
    returned vector exposes `.tolist()` exactly like a numpy row."""

    def __init__(self, table):
        # table: text -> list[float]
        self._table = table

    def encode(self, texts, normalize_embeddings=True):
        out = []
        for t in texts:
            out.append(_Vec(self._table.get(t, [0.0])))
        return out


def test_classify_intent_returns_none_without_emb():
    fake = _FakeModel({})
    assert kc.classify_intent("đọc bài thơ", fake, {}) is None
    assert kc.classify_intent("", fake, {"recite": [[1.0]]}) is None


def test_build_intent_emb_uses_injected_model():
    # Map every anchor phrase to vector [1.0]; query also [1.0] -> recite wins
    # but margin vs explain is 0 (< 0.035) so it collapses to "explain".
    table = {}
    for phrases in kc._INTENT_ANCHORS.values():
        for p in phrases:
            table[p] = [1.0]
    fake = _FakeModel(table)
    emb = kc.build_intent_emb(fake)
    assert set(emb.keys()) == set(kc._INTENT_ANCHORS.keys())
    # query identical to anchors -> all sims equal -> margin 0 -> explain
    fake2 = _FakeModel(dict(table, **{"q": [1.0]}))
    assert kc.classify_intent("q", fake2, emb) == "explain"


def test_build_intent_emb_returns_empty_on_model_error():
    class _Boom:
        def encode(self, *a, **k):
            raise RuntimeError("no model")
    assert kc.build_intent_emb(_Boom()) == {}


def test_classify_intent_recite_with_margin():
    # recite anchors map to [1.0]; explain anchors to [0.0]; query [1.0] ->
    # sim(recite)=1, sim(explain)=0, margin 1 >= 0.035 -> "recite".
    table = {}
    for k, phrases in kc._INTENT_ANCHORS.items():
        v = [1.0] if k == "recite" else [0.0]
        for p in phrases:
            table[p] = v
    table["doc bai tho"] = [1.0]
    fake = _FakeModel(table)
    emb = kc.build_intent_emb(fake)
    assert kc.classify_intent("doc bai tho", fake, emb) == "recite"


# ───────────────────── build_lines_payload_dict ────────────────────────

def test_build_lines_payload_dict():
    out = kc.build_lines_payload_dict(
        "Sang thu", ["Bỗng nhận ra hương ổi", "Phả vào trong gió se"],
        {"subject": "ngu_van"}, {"url": "x"},
    )
    ctx = json.loads(out["context"])
    assert ctx["type"] == "full_recitation_lines"
    assert ctx["title"] == "Sang thu"
    assert ctx["lines"] == ["Bỗng nhận ra hương ổi", "Phả vào trong gió se"]
    assert out["intent"]["query_type"] == "recite_full_text"
    assert out["intent"]["title"] == "Sang thu"
    assert out["intent"]["subject"] == "ngu_van"
    assert out["sources"] == [{"url": "x"}]


# ─────────────────────── corpus + snapshot lock ────────────────────────

def test_corpus_is_large_enough():
    corpus = build_corpus()
    assert len(corpus) >= 60, "corpus too small: %d" % len(corpus)


def _load_golden():
    assert os.path.exists(_GOLDEN), (
        "golden snapshot missing — run `python3 tests/characterization/gen_golden.py`"
    )
    with open(_GOLDEN, encoding="utf-8") as fh:
        return json.load(fh)


def test_snapshot_count_matches_corpus():
    golden = _load_golden()
    assert golden["n"] == len(build_corpus())


def test_snapshot_lock_full_corpus():
    """The behavior-locking net: recompute every record and assert it equals
    the committed golden snapshot exactly. Any drift in the pure core trips
    this test."""
    golden = _load_golden()
    expected = golden["records"]
    corpus = build_corpus()
    assert len(expected) == len(corpus)

    mismatches = []
    for idx, (c, exp) in enumerate(zip(corpus, expected)):
        got = compute_record(c["query"], c["profile"])
        if got != exp:
            # find the first differing field for a readable failure
            diff_fields = sorted(
                k for k in set(got) | set(exp) if got.get(k) != exp.get(k)
            )
            mismatches.append((idx, c["query"], diff_fields))

    assert not mismatches, "snapshot drift in %d record(s): %s" % (
        len(mismatches), mismatches[:5],
    )
