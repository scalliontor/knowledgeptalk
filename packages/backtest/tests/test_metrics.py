"""Unit tests for packages.backtest.metrics (+ a slice of failure_taxonomy).

Run from repo root:
    python3 -m pytest packages/backtest/tests/ -q

The CRITICAL tests are the cruft-split ones: the bare word "giáo viên" must
NOT count as a real source leak (it is legitimate civics/GDCD vocabulary).
Only the crawl artifacts "Giáo viên VietJack" / "(Giáo viên ...)" are leaks.
"""

import pytest

from packages.backtest import failure_taxonomy as ftx
from packages.backtest import metrics as m


# --------------------------------------------------------------------------- #
# fixtures (inline, tiny)
# --------------------------------------------------------------------------- #
def lesson_case(**kw):
    base = dict(
        dim="current_lesson",
        expected_work="Tự lập",
        expected_tier="lesson_card",
        got_work="Tự lập",
        got_tier="lesson_card",
        context="Tự lập là tự làm lấy công việc của mình.",
        latency_ms=40.0,
        error=False,
    )
    base.update(kw)
    return base


def guard_case(**kw):
    base = dict(
        dim="guard_chitchat",
        expected_work=None,
        expected_tier="none",
        got_work="",
        got_tier="none",
        context="",
        latency_ms=12.0,
        error=False,
    )
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# anchor / mode / guard
# --------------------------------------------------------------------------- #
def test_anchor_at_1_diacritic_fold():
    # got_work without diacritics still matches expected via norm()
    cases = [lesson_case(got_work="Tu lap"), lesson_case(got_work="Tự lập")]
    assert m.anchor_at_1(cases) == 100.0


def test_anchor_miss_counts():
    cases = [lesson_case(), lesson_case(got_work="Tiết kiệm")]
    assert m.anchor_at_1(cases) == 50.0


def test_mode_requires_anchor_and_tier():
    # anchored right but wrong tier -> mode miss
    cases = [lesson_case(got_tier="lesson_practice", expected_tier="lesson_card")]
    assert m.anchor_at_1(cases) == 100.0
    assert m.mode_accuracy(cases) == 0.0


def test_guard_accuracy_pass_and_fail():
    cases = [guard_case(got_tier="none"), guard_case(got_tier="lesson_card")]
    # one correctly refused, one wrongly emitted a card
    assert m.guard_accuracy(cases) == 50.0


def test_errors_excluded_from_anchor():
    cases = [lesson_case(), lesson_case(error=True, got_work="")]
    assert m.error_count(cases) == 1
    assert m.anchor_at_1(cases) == 100.0  # the errored case is excluded


# --------------------------------------------------------------------------- #
# refusal precision / recall
# --------------------------------------------------------------------------- #
def test_refusal_recall_equals_guard_accuracy():
    cases = [guard_case(got_tier="none"), guard_case(got_tier="lesson_card")]
    assert m.refusal_recall(cases) == m.guard_accuracy(cases) == 50.0


def test_refusal_precision_penalizes_false_refusal():
    # one correct refusal (guard), one false refusal (lesson case got no card)
    cases = [
        guard_case(got_tier="none"),
        lesson_case(got_tier="none", got_work=""),  # in-scope but refused
    ]
    # 2 refusals total, only 1 correct
    assert m.refusal_precision(cases) == 50.0


# --------------------------------------------------------------------------- #
# CRUFT split -- the load-bearing tests
# --------------------------------------------------------------------------- #
def test_bare_giao_vien_is_NOT_real_cruft():
    ctx = "Học sinh cần tôn trọng thầy cô giáo viên và bạn bè trong lớp."
    assert m.context_has_real_cruft(ctx) is False
    assert m.context_has_loose_keyword(ctx) is True
    assert m.context_is_cruft_false_positive(ctx) is True


def test_giao_vien_vietjack_IS_real_cruft():
    ctx = "Soạn bài này hay nhất - Giáo viên VietJack biên soạn."
    assert m.context_has_real_cruft(ctx) is True
    assert m.context_is_cruft_false_positive(ctx) is False


def test_paren_giao_vien_IS_real_cruft():
    ctx = "Lời giải chi tiết (Giáo viên: Cô Ngô) trang 12."
    assert m.context_has_real_cruft(ctx) is True


def test_vietjack_keyword_is_real_cruft():
    assert m.context_has_real_cruft("nguồn: vietjack.me") is True


def test_clean_context_no_cruft():
    ctx = "Tự lập là tự làm lấy công việc của mình."
    assert m.context_has_real_cruft(ctx) is False
    assert m.context_is_cruft_false_positive(ctx) is False


def test_source_cruft_real_vs_false_positive_counts():
    cases = [
        lesson_case(context="tôn trọng giáo viên của mình"),         # false positive
        lesson_case(context="biên soạn bởi Giáo viên VietJack"),     # real leak
        lesson_case(context="nội dung sạch, không nguồn"),           # clean
    ]
    assert m.source_cruft_real(cases) == 1
    assert m.source_cruft_test_false_positive(cases) == 1


def test_cruft_only_counts_on_emitted_card():
    # real-leak text but tier is a refusal -> not a card leak
    cases = [lesson_case(got_tier="none", context="Giáo viên VietJack")]
    assert m.source_cruft_real(cases) == 0


# --------------------------------------------------------------------------- #
# volume collision
# --------------------------------------------------------------------------- #
def test_volume_collision_rate():
    # anchor miss, card emitted, same title different tap -> collision
    cases = [
        lesson_case(
            got_work="Phân số",
            expected_work="Số thập phân",
            expected_volume=2,
            got_volume=1,
        )
    ]
    assert m.volume_collision_rate(cases) == 100.0


# --------------------------------------------------------------------------- #
# latency
# --------------------------------------------------------------------------- #
def test_latency_percentiles_monotone():
    cases = [lesson_case(latency_ms=float(x)) for x in range(1, 101)]
    lat = m.latency_percentiles(cases)
    assert lat["p50"] <= lat["p95"] <= lat["p99"] <= lat["max"]
    assert lat["max"] == 100.0


def test_latency_empty():
    assert m.latency_percentiles([])["p95"] == 0.0


# --------------------------------------------------------------------------- #
# slice + summary
# --------------------------------------------------------------------------- #
def test_slice_anchor_separates_cruft():
    cases = [
        lesson_case(dim="content_only", context="giáo viên dạy tốt"),       # fp
        lesson_case(dim="content_only", context="Giáo viên VietJack soạn"), # real
    ]
    sl = m.slice_anchor(cases)["content_only"]
    assert sl["n"] == 2
    assert sl["cruft_real"] == 1
    assert sl["cruft_fp"] == 1


def test_summarize_cases_shape():
    cases = [lesson_case(), guard_case()]
    s = m.summarize_cases(cases)
    for key in (
        "anchor_at_1",
        "guard_accuracy",
        "source_cruft_real",
        "source_cruft_test_false_positive",
        "latency_ms",
        "slice_anchor",
        "path_breakdown",
    ):
        assert key in s
    assert s["source_cruft_real"] == 0


# --------------------------------------------------------------------------- #
# report-level adapter
# --------------------------------------------------------------------------- #
def test_report_metric_row_reclassifies_legacy_cruft():
    report = {
        "book": "gdcd 6 CTST tapNone",
        "anchor_acc": 90.8,
        "mode_acc": 73.9,
        "guard_acc": 100.0,
        "errors": 0,
        "lesson_cases": 360,
        "guard_cases": 75,
        "cruft_on_cards": 17,
        "latency_ms": {"p50": 38.9, "p95": 202.9, "p99": 219.7, "max": 254.2},
    }
    row = m.report_metric_row(report)
    assert row["source_cruft_real"] == 0
    # legacy 17 is re-classified as suspected false positive at report level
    assert row["source_cruft_test_false_positive"] == 17
    assert row["source_cruft_legacy_aggregate"] == 17
    assert row["anchor_at_1"] == 90.8


# --------------------------------------------------------------------------- #
# failure taxonomy slice
# --------------------------------------------------------------------------- #
def test_taxonomy_runtime_error_is_N():
    code, _ = ftx.classify_failure(lesson_case(error=True))
    assert code == "N"


def test_taxonomy_missed_refusal_is_K():
    code, _ = ftx.classify_failure(guard_case(got_tier="lesson_card", got_work="Tự lập"))
    assert code == "K"


def test_taxonomy_real_cruft_is_L():
    code, _ = ftx.classify_failure(lesson_case(context="Giáo viên VietJack soạn"))
    assert code == "L"


def test_taxonomy_false_positive_cruft_is_M_not_L():
    code, _ = ftx.classify_failure(lesson_case(context="tôn trọng giáo viên"))
    assert code == "M"


def test_taxonomy_volume_collision_is_C():
    # page-anchored query landed on the OTHER tap (anchor miss + volume mismatch)
    case = lesson_case(
        dim="trang_query",
        page=12,
        got_work="Phân số",       # a tap-1 lesson on page 12
        expected_work="Số thập phân",  # tap-2 lesson on page 12
        expected_volume=2,
        got_volume=1,
        context="clean",
    )
    code, _ = ftx.classify_failure(case)
    assert code == "C"


def test_taxonomy_intent_route_is_I():
    case = lesson_case(got_tier="lesson_practice", expected_tier="lesson_card", context="clean")
    code, _ = ftx.classify_failure(case)
    assert code == "I"


def test_taxonomy_false_refusal_is_J():
    case = lesson_case(got_tier="none", got_work="", context="")
    code, _ = ftx.classify_failure(case)
    assert code == "J"


def test_taxonomy_passing_case_returns_empty():
    code, reason = ftx.classify_failure(lesson_case())
    assert code == "" and reason == "pass"
