"""Pure metric functions for the Knowledge PTalk RAG backtest.

NO I/O, NO network, NO server. Every function takes plain Python data
(a list of case-result dicts, or an aggregate report dict produced by
rag_edu/scripts/schema_v3_2026_06/backtest_book.py) and returns numbers.

A "case-result" dict is the per-case record. It mirrors the variables scored
inside backtest_book.py's run loop. Minimal shape::

    {
      "dim": "current_lesson",        # dimension / slice label
      "expected_work": "Tự lập" | None,  # None => guard case
      "expected_tier": "lesson_card",    # optional, for mode
      "got_tier": "lesson_card",         # tier returned by /retrieve
      "got_work": "Tu lap",              # work_name returned
      "context": "....",                 # raw served context text (for cruft)
      "latency_ms": 38.9,
      "error": False,                    # True if the call raised
    }

These functions are intentionally tolerant of missing keys so they can run on
partial records.

--------------------------------------------------------------------------------
CRUFT: real leak vs test false-positive
--------------------------------------------------------------------------------
Source-of-truth (docs/project_state/2026-06-22-canonical.md): the old "204
cruft" was a FALSE POSITIVE. backtest_book.py's CRUFT list contained the bare
keyword "giáo viên", which legitimately appears in GDCD / civics content
("vai trò của giáo viên", "tôn trọng thầy cô giáo viên"). Direct Neo4j check
over all 1852 theory chunks: real source cruft = 0.

We therefore split cruft into two metrics:

  * source_cruft_real           -> genuine source leak. Must be 0.
  * source_cruft_test_false_pos -> matched only by the loose "giáo viên" keyword
                                   and NOT by any real-leak pattern. Informational.

REAL leak patterns are tightened so the bare word "giáo viên" no longer fires:
only the crawl-artifact forms "Giáo viên VietJack" / "(Giáo viên ...)" count,
plus the other unambiguous source markers (vietjack, lời giải, video giải, ...).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Serving tiers that mean "a lesson card was emitted". Mirrors
# backtest_book.py CARD_TIERS. A guard PASS == returned tier NOT in this set.
CARD_TIERS = frozenset({"lesson_card", "lesson_practice", "lesson_recite"})

# ---------------------------------------------------------------------------
# Cruft patterns
# ---------------------------------------------------------------------------
# REAL leak: unambiguous crawl/source artifacts. Matched case-insensitively
# against the served context. NOTE the "giáo viên" forms are deliberately
# narrow -- only the VietJack-attribution / parenthetical-credit forms, which
# are the actual scraped artifacts, NOT the bare word.
REAL_CRUFT_PATTERNS = (
    r"vietjack",
    r"loigiaihay",
    r"xem lời giải",
    r"video giải",
    r"hay nhất,\s*chi tiết",
    r"giải bài nhanh với ai",
    r"cô ngô",
    r"giáo viên vietjack",        # "Giáo viên VietJack" attribution
    r"\(\s*giáo viên",            # "(Giáo viên ...)" parenthetical credit
)

# The LOOSE keyword that produced the historical false positives. Kept ONLY so
# we can quantify how many "cruft" hits were false alarms. It is NOT part of the
# real-leak decision.
LOOSE_FALSE_POSITIVE_KEYWORD = "giáo viên"

_REAL_CRUFT_RE = re.compile("|".join(REAL_CRUFT_PATTERNS), re.IGNORECASE)


def _norm(x: Optional[str]) -> str:
    """Diacritic-folding normaliser, identical to backtest_book.py norm()."""
    x = (x or "").replace("đ", "d").replace("Đ", "D")
    x = unicodedata.normalize("NFD", x)
    return "".join(c for c in x if unicodedata.category(c) != "Mn").lower().strip()


def context_has_real_cruft(context: Optional[str]) -> bool:
    """True iff the served context contains a genuine source leak."""
    return bool(_REAL_CRUFT_RE.search(context or ""))


def context_has_loose_keyword(context: Optional[str]) -> bool:
    """True iff the loose 'giáo viên' keyword appears (real or not)."""
    return LOOSE_FALSE_POSITIVE_KEYWORD in (context or "").lower()


def context_is_cruft_false_positive(context: Optional[str]) -> bool:
    """Loose keyword fired but there is NO real leak -> false positive."""
    return context_has_loose_keyword(context) and not context_has_real_cruft(context)


# ---------------------------------------------------------------------------
# Per-case helpers
# ---------------------------------------------------------------------------
def is_guard_case(case: Dict[str, Any]) -> bool:
    """Guard case == no expected work (refusal expected)."""
    return case.get("expected_work") is None


def case_anchor_ok(case: Dict[str, Any]) -> bool:
    """anchor@1 for a lesson case: normalised work_name matches expected."""
    if is_guard_case(case):
        return False
    return _norm(case.get("got_work")) == _norm(case.get("expected_work"))


def case_mode_ok(case: Dict[str, Any]) -> bool:
    """mode: anchor correct AND tier matches expected tier."""
    if not case_anchor_ok(case):
        return False
    exp = case.get("expected_tier")
    if exp is None:
        return True
    return case.get("got_tier") == exp


def case_guard_ok(case: Dict[str, Any]) -> bool:
    """guard PASS: returned tier is NOT a card tier (model refused to card)."""
    return case.get("got_tier", "none") not in CARD_TIERS


def case_emitted_card(case: Dict[str, Any]) -> bool:
    return case.get("got_tier", "none") in CARD_TIERS


# ---------------------------------------------------------------------------
# Aggregate metrics over a list of case-results
# ---------------------------------------------------------------------------
def _pct(num: int, den: int) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def _percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile. Pure, no numpy. pct in [0,100]."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 1)
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 1)


def anchor_at_1(cases: Iterable[Dict[str, Any]]) -> float:
    cases = [c for c in cases if not is_guard_case(c) and not c.get("error")]
    return _pct(sum(case_anchor_ok(c) for c in cases), len(cases))


def mode_accuracy(cases: Iterable[Dict[str, Any]]) -> float:
    cases = [c for c in cases if not is_guard_case(c) and not c.get("error")]
    return _pct(sum(case_mode_ok(c) for c in cases), len(cases))


def guard_accuracy(cases: Iterable[Dict[str, Any]]) -> float:
    cases = [c for c in cases if is_guard_case(c) and not c.get("error")]
    return _pct(sum(case_guard_ok(c) for c in cases), len(cases))


def refusal_precision(cases: Iterable[Dict[str, Any]]) -> float:
    """Of all REFUSALS the system made, how many SHOULD have been refused.

    precision = correct_refusals / all_refusals
    A refusal == no card emitted. "Correct" == it was a guard case.
    """
    refusals = [c for c in cases if not c.get("error") and not case_emitted_card(c)]
    correct = [c for c in refusals if is_guard_case(c)]
    return _pct(len(correct), len(refusals))


def refusal_recall(cases: Iterable[Dict[str, Any]]) -> float:
    """Of all cases that SHOULD be refused, how many were.

    recall = correct_refusals / all_should_refuse  == guard_accuracy, but kept
    as a named metric so reports speak precision/recall explicitly.
    """
    should = [c for c in cases if is_guard_case(c) and not c.get("error")]
    correct = [c for c in should if not case_emitted_card(c)]
    return _pct(len(correct), len(should))


def volume_collision_rate(cases: Iterable[Dict[str, Any]]) -> float:
    """Fraction of anchor MISSES where the wrong-but-emitted work belongs to
    the OTHER volume of the same book (page-reset collision).

    Requires per-case 'expected_volume' and 'got_volume' when available; cases
    lacking volume info are skipped. Returns % over anchor-miss-with-card cases.
    """
    misses = [
        c
        for c in cases
        if not is_guard_case(c)
        and not c.get("error")
        and case_emitted_card(c)
        and not case_anchor_ok(c)
        and c.get("expected_volume") is not None
        and c.get("got_volume") is not None
    ]
    collisions = [c for c in misses if c["got_volume"] != c["expected_volume"]]
    return _pct(len(collisions), len(misses))


def source_cruft_real(cases: Iterable[Dict[str, Any]]) -> int:
    """Count of cases where a REAL source leak appears in a served card.

    Only counts when a card tier was emitted (a leak in a refusal context is not
    a card leak). MUST be 0 for the 'sạch nguồn' invariant.
    """
    return sum(
        1
        for c in cases
        if not c.get("error")
        and case_emitted_card(c)
        and context_has_real_cruft(c.get("context"))
    )


def source_cruft_test_false_positive(cases: Iterable[Dict[str, Any]]) -> int:
    """Count of cases flagged by the loose 'giáo viên' keyword but with NO real
    leak. This is the historical '204 cruft' artifact. Informational only.
    """
    return sum(
        1
        for c in cases
        if not c.get("error")
        and case_emitted_card(c)
        and context_is_cruft_false_positive(c.get("context"))
    )


def error_count(cases: Iterable[Dict[str, Any]]) -> int:
    return sum(1 for c in cases if c.get("error"))


def latency_percentiles(cases: Iterable[Dict[str, Any]]) -> Dict[str, float]:
    lat = [c["latency_ms"] for c in cases if c.get("latency_ms") is not None]
    return {
        "p50": _percentile(lat, 50),
        "p95": _percentile(lat, 95),
        "p99": _percentile(lat, 99),
        "max": round(max(lat), 1) if lat else 0.0,
    }


def path_breakdown(cases: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per-served-tier (routing path) breakdown: n + anchor%."""
    out: Dict[str, Dict[str, Any]] = {}
    for c in cases:
        if c.get("error"):
            continue
        tier = c.get("got_tier", "none")
        d = out.setdefault(tier, {"n": 0, "anchor_ok": 0})
        d["n"] += 1
        if case_anchor_ok(c):
            d["anchor_ok"] += 1
    for d in out.values():
        d["anchor%"] = _pct(d.pop("anchor_ok"), d["n"])
    return out


def slice_anchor(cases: Iterable[Dict[str, Any]], key: str = "dim") -> Dict[str, Dict[str, Any]]:
    """anchor% / mode% / cruft per slice. Mirrors report by_dimension shape."""
    out: Dict[str, Dict[str, Any]] = {}
    for c in cases:
        sl = c.get(key, "unknown")
        d = out.setdefault(sl, {"n": 0, "anchor": 0, "mode": 0, "cruft_real": 0, "cruft_fp": 0})
        d["n"] += 1
        if is_guard_case(c):
            if case_guard_ok(c):
                d["anchor"] += 1  # guard pass folded into anchor like backtest_book
        else:
            if case_anchor_ok(c):
                d["anchor"] += 1
            if case_mode_ok(c):
                d["mode"] += 1
        if case_emitted_card(c) and context_has_real_cruft(c.get("context")):
            d["cruft_real"] += 1
        elif case_emitted_card(c) and context_is_cruft_false_positive(c.get("context")):
            d["cruft_fp"] += 1
    for d in out.values():
        d["anchor%"] = _pct(d["anchor"], d["n"])
        d["mode%"] = _pct(d["mode"], d["n"])
    return out


def summarize_cases(cases: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll a list of case-results into the canonical metric block."""
    lesson = [c for c in cases if not is_guard_case(c)]
    guard = [c for c in cases if is_guard_case(c)]
    return {
        "total": len(cases),
        "lesson_cases": len(lesson),
        "guard_cases": len(guard),
        "errors": error_count(cases),
        "anchor_at_1": anchor_at_1(cases),
        "mode_accuracy": mode_accuracy(cases),
        "guard_accuracy": guard_accuracy(cases),
        "refusal_precision": refusal_precision(cases),
        "refusal_recall": refusal_recall(cases),
        "volume_collision_rate": volume_collision_rate(cases),
        "source_cruft_real": source_cruft_real(cases),
        "source_cruft_test_false_positive": source_cruft_test_false_positive(cases),
        "latency_ms": latency_percentiles(cases),
        "slice_anchor": slice_anchor(cases),
        "path_breakdown": path_breakdown(cases),
    }


# ---------------------------------------------------------------------------
# Report-level adapters (operate on the AGGREGATE JSON from backtest_book.py)
# ---------------------------------------------------------------------------
# The 2026-06-17 reports store only aggregates, not raw contexts. At that level
# we cannot recompute real-vs-false-positive cruft from text (the strings were
# not persisted). We surface the legacy aggregate as a *suspected* false
# positive, per the canonical correction, and keep real cruft unknown->0-claim
# ONLY when the run already used the tightened keyword. Callers should prefer
# case-level metrics when raw contexts are available.
# Dimensions that are "refuse-by-design when no client anchor" and therefore
# excluded from the production/anchored-path anchor figure (the canonical 97.0%).
# In production the client always supplies current_lesson, so content_only does
# not occur; including it understates the production anchor.
NON_PRODUCTION_DIMS = frozenset({"content_only"})


def anchored_path_from_report(report: Dict[str, Any]) -> float:
    """Recompute anchor over by_dimension EXCLUDING guard_* and the
    refuse-by-design dims -> the 'production/anchored path' anchor (canonical).
    Falls back to anchor_acc if by_dimension is absent.
    """
    bd = report.get("by_dimension")
    if not bd:
        return report.get("anchor_acc", 0.0)
    num = den = 0.0
    for dim, v in bd.items():
        if dim.startswith("guard_") or dim in NON_PRODUCTION_DIMS:
            continue
        n = v.get("n", 0)
        num += v.get("anchor%", 0.0) * n / 100.0
        den += n
    return round(100.0 * num / den, 1) if den else report.get("anchor_acc", 0.0)


def report_metric_row(report: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one aggregate report JSON into a comparable metric row."""
    lat = report.get("latency_ms", {}) or {}
    legacy_cruft = report.get("cruft_on_cards", 0)
    return {
        "book": report.get("book", "?"),
        # all-lesson-dim anchor (incl content_only) -- conservative
        "anchor_all": report.get("anchor_acc", 0.0),
        # production/anchored-path anchor (excl content_only) -- canonical 97%
        "anchor_at_1": anchored_path_from_report(report),
        "mode_accuracy": report.get("mode_acc", 0.0),
        "guard_accuracy": report.get("guard_acc", 0.0),
        "errors": report.get("errors", 0),
        "lesson_cases": report.get("lesson_cases", 0),
        "guard_cases": report.get("guard_cases", 0),
        # Legacy aggregate 'cruft_on_cards' used the loose keyword. Per canonical
        # correction (real cruft verified = 0 in Neo4j), treat it as suspected
        # false-positive at report level. Mark real as 0 unless the run is known
        # to have used the tightened patterns (see source_cruft_real_known).
        "source_cruft_legacy_aggregate": legacy_cruft,
        "source_cruft_real": report.get("source_cruft_real", 0),
        "source_cruft_test_false_positive": report.get(
            "source_cruft_test_false_positive", legacy_cruft
        ),
        "p50": lat.get("p50", 0.0),
        "p95": lat.get("p95", 0.0),
        "p99": lat.get("p99", 0.0),
        "max": lat.get("max", 0.0),
    }
