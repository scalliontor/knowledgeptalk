"""Knowledge PTalk backtest toolkit (pure, local, server-free).

Turns the ad-hoc Gemma-generated backtest into a versioned, repeatable system
with standard metrics. NONE of this code talks to the server or changes runtime
behavior -- it operates on case-result lists (live) and on the aggregate JSON
reports emitted by rag_edu/scripts/schema_v3_2026_06/backtest_book.py.

Modules:
  metrics            -- pure metric functions (anchor@1, guard, cruft split, ...)
  failure_taxonomy   -- classify one failure into class A..O
  reporters          -- read a report dir -> summary.md + slice table
  compare_runs       -- diff two runs -> before/after + PASS/FAIL gate
  scenario_knowledge -- LLM-judge KNOWLEDGE backtest (build_scenarios/judge/score_run)

See docs/backtest/ for methodology, metric definitions and the failure taxonomy.
"""

from . import compare_runs, failure_taxonomy, metrics, reporters, scenario_knowledge  # noqa: F401

__all__ = ["metrics", "failure_taxonomy", "reporters", "compare_runs", "scenario_knowledge"]
__version__ = "1.0.0"
