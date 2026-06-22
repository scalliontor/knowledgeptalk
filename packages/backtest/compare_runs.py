"""Diff two backtest runs (before/after) and apply the regression gate.

Pure stdlib. Consumes two report directories (the aggregate JSON form), joins
per-book on the `book` label, and renders a before/after table plus a global
PASS/FAIL verdict. This is the "regression gate" of the 4-tier methodology:
a refactor must not drop anchor/guard or raise real cruft.

Usage (local, no server)::

    python3 -m packages.backtest.compare_runs <before_dir> <after_dir>
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .reporters import gate_status, load_run

# Regression tolerances. A per-book anchor drop beyond this fails the gate even
# if the global average still clears the absolute floor.
REGRESSION = {
    "anchor_drop_max": 0.5,      # pp a single book may drop
    "guard_drop_max": 0.5,
    "global_anchor_floor": 97.0,
    "global_guard_floor": 98.1,
    "cruft_real_max": 0,
    "errors_max": 0,
    "p95_increase_max_ms": 50.0,  # worst-book p95 may rise this much
}


def _index(run: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {r["book"]: r for r in run["rows"]}


def compare(before_dir: str, after_dir: str) -> Dict[str, Any]:
    before = load_run(before_dir)
    after = load_run(after_dir)
    bi, ai = _index(before), _index(after)

    books = sorted(set(bi) | set(ai))
    rows: List[Dict[str, Any]] = []
    regressions: List[str] = []
    for book in books:
        b = bi.get(book)
        a = ai.get(book)
        row: Dict[str, Any] = {"book": book}
        for m in ("anchor_at_1", "guard_accuracy", "mode_accuracy", "p95"):
            bv = b[m] if b else None
            av = a[m] if a else None
            row[m + "_before"] = bv
            row[m + "_after"] = av
            row[m + "_delta"] = (round(av - bv, 1) if (bv is not None and av is not None) else None)
        row["cruft_real_before"] = b.get("source_cruft_real", 0) if b else None
        row["cruft_real_after"] = a.get("source_cruft_real", 0) if a else None
        # regression detection (only when both present)
        if b and a:
            if (a["anchor_at_1"] - b["anchor_at_1"]) < -REGRESSION["anchor_drop_max"]:
                regressions.append("%s anchor %.1f->%.1f" % (book, b["anchor_at_1"], a["anchor_at_1"]))
            if (a["guard_accuracy"] - b["guard_accuracy"]) < -REGRESSION["guard_drop_max"]:
                regressions.append("%s guard %.1f->%.1f" % (book, b["guard_accuracy"], a["guard_accuracy"]))
            if (a["p95"] - b["p95"]) > REGRESSION["p95_increase_max_ms"]:
                regressions.append("%s p95 %.0f->%.0fms" % (book, b["p95"], a["p95"]))
        elif a and not b:
            row["_note"] = "new book"
        elif b and not a:
            regressions.append("%s MISSING in after-run" % book)
            row["_note"] = "dropped book"
        rows.append(row)

    after_gate = gate_status(after["aggregate"])
    abs_floor_ok = (
        after["aggregate"].get("anchor_at_1", 0) >= REGRESSION["global_anchor_floor"]
        and after["aggregate"].get("guard_accuracy", 0) >= REGRESSION["global_guard_floor"]
        and after["aggregate"].get("source_cruft_real", 0) <= REGRESSION["cruft_real_max"]
        and after["aggregate"].get("errors", 0) <= REGRESSION["errors_max"]
    )
    verdict = (not regressions) and abs_floor_ok and after_gate["pass"]

    return {
        "before": before["aggregate"],
        "after": after["aggregate"],
        "rows": rows,
        "regressions": regressions,
        "after_gate": after_gate,
        "abs_floor_ok": abs_floor_ok,
        "pass": verdict,
    }


def _fmt(v: Optional[float]) -> str:
    return "-" if v is None else ("%.1f" % v)


def _fmt_delta(v: Optional[float]) -> str:
    if v is None:
        return "-"
    sign = "+" if v >= 0 else ""
    return "%s%.1f" % (sign, v)


def render_diff(cmp: Dict[str, Any]) -> str:
    out: List[str] = []
    out.append("# Backtest run comparison (before -> after)")
    out.append("")
    b, a = cmp["before"], cmp["after"]
    out.append("| metric | before | after | delta |")
    out.append("|--------|-------:|------:|------:|")
    for m in ("anchor_at_1", "guard_accuracy", "mode_accuracy"):
        bv, av = b.get(m, 0), a.get(m, 0)
        out.append("| %s | %.1f | %.1f | %s |" % (m, bv, av, _fmt_delta(round(av - bv, 1))))
    out.append(
        "| source_cruft_real | %d | %d | %d |"
        % (b.get("source_cruft_real", 0), a.get("source_cruft_real", 0), a.get("source_cruft_real", 0) - b.get("source_cruft_real", 0))
    )
    out.append("| errors | %d | %d | %d |" % (b.get("errors", 0), a.get("errors", 0), a.get("errors", 0) - b.get("errors", 0)))
    out.append("| p95_max(ms) | %.0f | %.0f | %s |" % (b.get("p95_max", 0), a.get("p95_max", 0), _fmt_delta(round(a.get("p95_max", 0) - b.get("p95_max", 0), 1))))
    out.append("")
    out.append("## Per-book anchor delta")
    out.append("")
    out.append("| book | before | after | delta | note |")
    out.append("|------|-------:|------:|------:|------|")
    for r in sorted(cmp["rows"], key=lambda x: (x.get("anchor_at_1_delta") if x.get("anchor_at_1_delta") is not None else 0)):
        out.append(
            "| %s | %s | %s | %s | %s |"
            % (
                r["book"],
                _fmt(r.get("anchor_at_1_before")),
                _fmt(r.get("anchor_at_1_after")),
                _fmt_delta(r.get("anchor_at_1_delta")),
                r.get("_note", ""),
            )
        )
    out.append("")
    if cmp["regressions"]:
        out.append("## REGRESSIONS")
        for reg in cmp["regressions"]:
            out.append("- %s" % reg)
        out.append("")
    out.append("**VERDICT: %s**" % ("PASS" if cmp["pass"] else "FAIL"))
    if not cmp["abs_floor_ok"]:
        out.append("  - FAIL absolute floor (anchor>=%.1f, guard>=%.1f, real cruft==0, errors==0)" % (REGRESSION["global_anchor_floor"], REGRESSION["global_guard_floor"]))
    if not cmp["after_gate"]["pass"]:
        out.append("  - FAIL release gate on after-run")
    if cmp["regressions"]:
        out.append("  - FAIL %d per-book regression(s)" % len(cmp["regressions"]))
    return "\n".join(out)


def _main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m packages.backtest.compare_runs <before_dir> <after_dir> [out.md]")
        return 2
    cmp = compare(argv[0], argv[1])
    text = render_diff(cmp)
    if len(argv) > 2:
        with open(argv[2], "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("wrote %s" % argv[2])
    else:
        print(text)
    return 0 if cmp["pass"] else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
