"""Classify a single backtest failure into one of 15 taxonomy classes A..O.

See docs/backtest/failure-taxonomy.md for the human description of each class.
This module is a pure, deterministic classifier: given one failing
case-result dict (same shape as metrics.py consumes, plus optional context
fields), it returns the taxonomy code and a short reason.

A "failure" here is any case that did NOT pass its own criterion:
  * lesson case: anchor wrong, or anchor ok but mode wrong
  * guard case : emitted a card when it should have refused

The classifier is heuristic and ordered: the FIRST matching rule wins. Rules
are arranged from most-specific to most-general so a long-math-title miss is
labelled L (Long math title) rather than the catch-all C/H.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from .metrics import (
    CARD_TIERS,
    _norm,
    case_anchor_ok,
    case_emitted_card,
    case_guard_ok,
    case_mode_ok,
    context_has_real_cruft,
    context_is_cruft_false_positive,
    is_guard_case,
)

# Code -> short label. Mirrors docs/backtest/failure-taxonomy.md.
TAXONOMY = {
    "A": "Missing client context",
    "B": "Wrong scope",
    "C": "Volume collision",
    "D": "Title normalization",
    "E": "Long math title",
    "F": "Page ambiguity",
    "G": "Vector overrode structured",
    "H": "Work-name normalization",
    "I": "Intent route",
    "J": "False refusal",
    "K": "Missed refusal",
    "L": "Real cruft",
    "M": "Cruft false-positive",
    "N": "Runtime error",
    "O": "Latency regression",
}

_ROMAN_RE = re.compile(r"\b[IVXLCDM]+\b")
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_MATH_TITLE_RE = re.compile(r"[=+\-×÷*/^√≤≥<>%]|phương trình|biểu thức|đa thức|phân số|số thập phân")
_LATENCY_BUDGET_MS = 400.0  # P95 budget; a single case over this is flagged O


def _is_long_or_mathy(title: Optional[str]) -> bool:
    t = title or ""
    return len(t) >= 45 or bool(_MATH_TITLE_RE.search(t.lower()))


def _norm_differs_only_by_punct(a: Optional[str], b: Optional[str]) -> bool:
    """True if a and b normalise close but raw differs by punctuation/roman/dash."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    # strip non-alnum/space then compare -> if equal, raw diff was punctuation
    sa = re.sub(r"[^a-z0-9 ]", " ", na)
    sb = re.sub(r"[^a-z0-9 ]", " ", nb)
    sa = re.sub(r"\s+", " ", sa).strip()
    sb = re.sub(r"\s+", " ", sb).strip()
    return sa == sb and na != nb


def classify_failure(case: Dict[str, Any]) -> Tuple[str, str]:
    """Return (code, reason) for one failing case. (code in A..O).

    If the case actually passed, returns ("", "pass") so callers can filter.
    """
    # ---- N: runtime error (highest priority: nothing else is meaningful) ----
    if case.get("error"):
        return "N", "runtime error / exception on /retrieve"

    got_tier = case.get("got_tier", "none")
    got_work = case.get("got_work", "")
    exp_work = case.get("expected_work")
    context = case.get("context", "")
    emitted = case_emitted_card(case)

    # ---- L / M: source cruft on an emitted card (independent of anchor) ------
    if emitted and context_has_real_cruft(context):
        return "L", "real source leak in served card context"
    if emitted and context_is_cruft_false_positive(context):
        # Not a behavioral failure -- flagged so the test harness stops counting
        # it as real cruft. Only surfaces when context is available.
        return "M", "loose 'giáo viên' keyword matched but no real leak (false positive)"

    # ---- guard cases ---------------------------------------------------------
    if is_guard_case(case):
        if case_guard_ok(case):
            return "", "pass"
        return "K", "missed refusal: emitted a card for an out-of-scope/chitchat query"

    # ---- lesson cases --------------------------------------------------------
    if case_anchor_ok(case):
        # anchor right; if we are here as a failure, it's a mode/intent miss
        if not case_mode_ok(case):
            return "I", "intent route: anchored right lesson but wrong tier/mode (%s vs %s)" % (
                got_tier,
                case.get("expected_tier"),
            )
        return "", "pass"

    # anchor wrong from here on
    if not emitted:
        # system refused / returned nothing for an in-scope answerable query
        if not case.get("has_client_context", True):
            return "A", "missing client context (no current_lesson/trang) -> no anchor -> refused"
        return "J", "false refusal: in-scope answerable query got no card"

    # emitted a card but wrong work
    # C: volume collision -- landed in the WRONG tap of the same book. Defining
    # signal is got_volume != expected_volume (page numbers reset between tap1/
    # tap2, so a page-anchored query resolves to the other volume's lesson).
    # Title may match (same-titled lesson in both taps) or differ.
    if (
        case.get("expected_volume") is not None
        and case.get("got_volume") is not None
        and case["got_volume"] != case["expected_volume"]
    ):
        same = " (same title)" if _norm(got_work) == _norm(exp_work) else ""
        return "C", "volume collision: wrong tap %s vs %s%s" % (
            case.get("got_volume"),
            case.get("expected_volume"),
            same,
        )

    # F: page ambiguity -- page-driven case where two lessons share/overlap pages
    if case.get("dim") in ("trang_query", "trang_profile") or case.get("page") is not None:
        if not _norm_differs_only_by_punct(got_work, exp_work):
            return "F", "page ambiguity: page-anchored query resolved to neighbour lesson"

    # E: long / math title miss
    if _is_long_or_mathy(exp_work):
        return "E", "long/math title: expected title is long or formula-like, anchor drifted"

    # D / H: title vs work-name normalisation (punctuation/roman/dash/year)
    if _norm_differs_only_by_punct(got_work, exp_work):
        if _ROMAN_RE.search(exp_work or "") or _YEAR_RE.search(exp_work or "") or "-" in (exp_work or ""):
            return "H", "work-name normalization: roman numeral/dash/year in title not folded"
        return "D", "title normalization: punctuation/whitespace difference broke match"

    # G: vector overrode structured -- a content/trang case answered by content-vec
    if got_tier in CARD_TIERS and case.get("dim") in ("current_lesson", "name_query", "trang_query", "trang_profile"):
        return "G", "vector overrode structured anchor: structured cue ignored, vector picked wrong lesson"

    # B: wrong scope -- emitted a card from a different subject/grade/book
    if case.get("got_subject") and case.get("expected_subject") and case["got_subject"] != case["expected_subject"]:
        return "B", "wrong scope: card from different subject/grade/book"

    # default residue -> B (wrong scope / wrong lesson, unattributed)
    return "B", "wrong lesson anchored (unattributed scope miss)"


def latency_outlier_code(latency_ms: Optional[float], budget_ms: float = _LATENCY_BUDGET_MS) -> Optional[str]:
    """Return 'O' if a single case exceeds the latency budget, else None.

    Latency regressions are a run-level concern (see compare_runs), but a single
    grossly-slow case can be tagged O for the per-case taxonomy histogram.
    """
    if latency_ms is not None and latency_ms > budget_ms:
        return "O"
    return None


def classify_run(cases) -> Dict[str, int]:
    """Histogram of taxonomy codes over a list of case-results (failures only)."""
    hist: Dict[str, int] = {}
    for c in cases:
        code, _ = classify_failure(c)
        if code:
            hist[code] = hist.get(code, 0) + 1
        lo = latency_outlier_code(c.get("latency_ms"))
        if lo:
            hist[lo] = hist.get(lo, 0) + 1
    return hist
