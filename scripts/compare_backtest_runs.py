#!/usr/bin/env python3
"""Thin CLI wrapper around packages.backtest.compare_runs.

Diffs two backtest run directories (the aggregate JSON form) and prints a
before/after table with a PASS/FAIL regression-gate verdict. Pure-local; does
NOT touch the server.

Usage:
    python3 scripts/compare_backtest_runs.py <before_dir> <after_dir> [out.md]

Exit code: 0 if the gate PASSES, 1 if it FAILS (CI-friendly).

Example:
    python3 scripts/compare_backtest_runs.py \
        reports/backtest/2026-06-17_full-sweep \
        reports/backtest/2026-06-30_candidate \
        reports/backtest/2026-06-30_candidate/diff.md
"""
import os
import sys

# Make the repo root importable so `packages.backtest` resolves regardless of cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from packages.backtest.compare_runs import _main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
