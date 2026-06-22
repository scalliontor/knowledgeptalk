"""Read a backtest report directory and render a summary + slice table.

Pure stdlib. Works on the aggregate JSON reports emitted by
rag_edu/scripts/schema_v3_2026_06/backtest_book.py (one file per
subject/grade/book/tap), e.g. reports/backtest/2026-06-17_full-sweep/.

Usage (local, no server)::

    python3 -m packages.backtest.reporters reports/backtest/2026-06-17_full-sweep
    # or
    from packages.backtest.reporters import load_run, render_summary
    run = load_run("reports/backtest/2026-06-17_full-sweep")
    print(render_summary(run))
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional

from .metrics import report_metric_row

# Gate thresholds from docs/project_state/2026-06-22-canonical.md release gate.
GATE = {
    "anchor_at_1_min": 97.0,
    "guard_accuracy_min": 98.1,
    "source_cruft_real_max": 0,
    "errors_max": 0,
    "p95_max_ms": 400.0,
}


def load_run(report_dir: str) -> Dict[str, Any]:
    """Load every *.json report in a directory into a run dict."""
    paths = sorted(glob.glob(os.path.join(report_dir, "*.json")))
    rows: List[Dict[str, Any]] = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as fh:
                rep = json.load(fh)
        except (ValueError, OSError):
            continue
        if not isinstance(rep, dict) or "anchor_acc" not in rep:
            continue
        row = report_metric_row(rep)
        row["_file"] = os.path.basename(p)
        rows.append(row)
    return {
        "dir": report_dir,
        "n_books": len(rows),
        "rows": rows,
        "aggregate": _aggregate(rows),
    }


def _weighted(rows: List[Dict[str, Any]], metric: str, weight: str) -> float:
    num = sum(r[metric] * r[weight] for r in rows if r.get(weight))
    den = sum(r[weight] for r in rows if r.get(weight))
    return round(num / den, 1) if den else 0.0


def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    return {
        "anchor_at_1": _weighted(rows, "anchor_at_1", "lesson_cases"),
        "anchor_all": _weighted(rows, "anchor_all", "lesson_cases"),
        "mode_accuracy": _weighted(rows, "mode_accuracy", "lesson_cases"),
        "guard_accuracy": _weighted(rows, "guard_accuracy", "guard_cases"),
        "errors": sum(r["errors"] for r in rows),
        "lesson_cases": sum(r["lesson_cases"] for r in rows),
        "guard_cases": sum(r["guard_cases"] for r in rows),
        "source_cruft_real": sum(r.get("source_cruft_real", 0) for r in rows),
        "source_cruft_test_false_positive": sum(
            r.get("source_cruft_test_false_positive", 0) for r in rows
        ),
        "source_cruft_legacy_aggregate": sum(
            r.get("source_cruft_legacy_aggregate", 0) for r in rows
        ),
        "p95_max": max((r["p95"] for r in rows), default=0.0),
        "p95_median": _median([r["p95"] for r in rows]),
        "p95_worst_book": _worst_book(rows, "p95"),
    }


def _worst_book(rows: List[Dict[str, Any]], metric: str) -> Optional[str]:
    if not rows:
        return None
    r = max(rows, key=lambda x: x.get(metric, 0))
    return "%s (%.0fms)" % (r["book"], r[metric])


def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return round((s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0), 1)


def gate_status(agg: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate run aggregate against the release gate."""
    checks = {
        "anchor_at_1": (agg.get("anchor_at_1", 0) >= GATE["anchor_at_1_min"], agg.get("anchor_at_1", 0)),
        "guard_accuracy": (agg.get("guard_accuracy", 0) >= GATE["guard_accuracy_min"], agg.get("guard_accuracy", 0)),
        "source_cruft_real": (agg.get("source_cruft_real", 0) <= GATE["source_cruft_real_max"], agg.get("source_cruft_real", 0)),
        "errors": (agg.get("errors", 0) <= GATE["errors_max"], agg.get("errors", 0)),
        # Gate on the representative (median-book) p95, not a single outlier book.
        # The worst-book p95 is surfaced separately as a watch item.
        "p95_median": (agg.get("p95_median", 1e9) <= GATE["p95_max_ms"], agg.get("p95_median", 0)),
    }
    passed = all(ok for ok, _ in checks.values())
    return {"pass": passed, "checks": checks}


def render_summary(run: Dict[str, Any]) -> str:
    agg = run["aggregate"]
    gate = gate_status(agg)
    out: List[str] = []
    out.append("# Backtest run summary")
    out.append("")
    out.append("- dir: `%s`" % run["dir"])
    out.append("- books: %d  (lesson=%d, guard=%d)" % (run["n_books"], agg.get("lesson_cases", 0), agg.get("guard_cases", 0)))
    out.append("- anchor@1 (production/anchored path, excl content_only): **%.1f%%**  (gate >= %.1f)" % (agg.get("anchor_at_1", 0), GATE["anchor_at_1_min"]))
    out.append("- anchor (all lesson dims, incl content_only refuse-by-design): %.1f%%  (informational, not the gate metric)" % agg.get("anchor_all", 0))
    out.append("- guard_accuracy: **%.1f%%**  (gate >= %.1f)" % (agg.get("guard_accuracy", 0), GATE["guard_accuracy_min"]))
    out.append("- mode_accuracy: %.1f%%" % agg.get("mode_accuracy", 0))
    out.append("- source_cruft_real: **%d**  (gate == 0)" % agg.get("source_cruft_real", 0))
    out.append(
        "- source_cruft_test_false_positive: %d  (legacy aggregate 'cruft_on_cards' = %d, RE-CLASSIFIED as false positive per canonical)"
        % (agg.get("source_cruft_test_false_positive", 0), agg.get("source_cruft_legacy_aggregate", 0))
    )
    out.append("- errors: %d  (gate == 0)" % agg.get("errors", 0))
    out.append("- latency p95: median-book %.1fms (gate <= %.0f) / worst-book %s" % (agg.get("p95_median", 0), GATE["p95_max_ms"], agg.get("p95_worst_book", "?")))
    out.append("")
    out.append("**GATE: %s**" % ("PASS" if gate["pass"] else "FAIL"))
    for name, (ok, val) in gate["checks"].items():
        out.append("  - %s %s = %s" % ("PASS" if ok else "FAIL", name, val))
    out.append("")
    out.append(render_slice_table(run))
    return "\n".join(out)


def render_slice_table(run: Dict[str, Any], sort_by: str = "anchor_at_1") -> str:
    """Per-book table sorted by anchor (weakest first)."""
    rows = sorted(run["rows"], key=lambda r: r.get(sort_by, 0))
    out: List[str] = []
    out.append("## Per-book slice (weakest anchor first)")
    out.append("")
    out.append("| book | anchor% | guard% | mode% | cruft_real | cruft_fp(legacy) | p95ms | errors |")
    out.append("|------|--------:|-------:|------:|-----------:|-----------------:|------:|-------:|")
    for r in rows:
        out.append(
            "| %s | %.1f | %.1f | %.1f | %d | %d | %.0f | %d |"
            % (
                r["book"],
                r["anchor_at_1"],
                r["guard_accuracy"],
                r["mode_accuracy"],
                r.get("source_cruft_real", 0),
                r.get("source_cruft_legacy_aggregate", 0),
                r["p95"],
                r["errors"],
            )
        )
    return "\n".join(out)


def write_summary(run: Dict[str, Any], out_path: str) -> str:
    text = render_summary(run)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return out_path


def _main(argv: List[str]) -> int:
    if not argv:
        print("usage: python3 -m packages.backtest.reporters <report_dir> [out.md]")
        return 2
    run = load_run(argv[0])
    if run["n_books"] == 0:
        print("no report JSONs found in %s" % argv[0])
        return 1
    text = render_summary(run)
    if len(argv) > 1:
        write_summary(run, argv[1])
        print("wrote %s" % argv[1])
    else:
        print(text)
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
