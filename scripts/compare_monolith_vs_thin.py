#!/usr/bin/env python3
"""Side-by-side parity harness: monolith (:8890) vs thin server (:8891).

⚠️ RUN ON THE SERVER ONLY, AFTER both servers are up. This script is documented
here but is NOT executed as part of the extraction PR (no server access this round
— canonical §"Thực tế hạ tầng"). It is the Step-5 gate in
docs/refactor/migration-plan.md.

What it does
------------
Replays the SAME N cases against both `/v2/rag/retrieve` endpoints and diffs the
fields that define anchored behavior:
  - intent.tier         (lesson_card / lesson_recite / lesson_practice /
                         A_structured / A_concept / None)
  - intent.work_name
  - context             (NFC-normalized; byte-equal expected on anchored paths)
It reports per-field match % and prints every mismatch with both payloads so a
wiring drift (injected dep wrong) is immediately visible.

Acceptance (migration-plan Step 5)
----------------------------------
  - tier match        == 100%
  - work_name match   == 100%
  - context match     == 100% on lesson-card / tier-A cases
Any mismatch ⇒ STOP, fix the thin-server wiring, re-run.

Usage
-----
    python3 scripts/compare_monolith_vs_thin.py \
        --monolith http://127.0.0.1:8890 \
        --thin     http://127.0.0.1:8891 \
        --cases    reports/backtest/<run>/cases.jsonl   # optional

`cases.jsonl`: one JSON object per line, each a RetrieveRequest body:
    {"query": "...", "user_profile": {"lop": 8, "bo_sach": "CTST",
                                      "subject": "toan", "current_lesson": "...",
                                      "tap": 1, "trang": 7}}
If --cases is omitted, a tiny built-in smoke set is used (anchored + guard cases).

Dependencies: only `requests`. Read-only against both servers.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata

try:
    import requests
except ImportError:
    print("requires `requests` (pip install requests)", file=sys.stderr)
    raise


# Minimal smoke set used when --cases is not supplied. Mirrors the kinds of
# requests the full sweep sends: current_lesson anchor, name-in-query anchor,
# trang+tap anchor, practice intent, recite intent, and an out-of-book guard.
DEFAULT_CASES = [
    {"query": "giảng bài này cho mình",
     "user_profile": {"lop": 8, "bo_sach": "CTST", "subject": "toan",
                      "current_lesson": "Phân thức đại số", "tap": 1}},
    {"query": "đọc thuộc bài thơ này cho mình nghe",
     "user_profile": {"lop": 9, "bo_sach": "CTST", "subject": "ngu_van",
                      "current_lesson": "Sang thu", "tap": 2}},
    {"query": "cho mình mấy câu luyện tập bài này",
     "user_profile": {"lop": 6, "bo_sach": "CTST", "subject": "toan",
                      "current_lesson": "Số nguyên tố", "tap": 1}},
    {"query": "bài 1 trang 7 nói gì",
     "user_profile": {"lop": 6, "bo_sach": "CTST", "subject": "toan", "tap": 1}},
    {"query": "tập hợp số tự nhiên là gì",
     "user_profile": {"lop": 6, "bo_sach": "CTST", "subject": "toan"}},
    # guard: out-of-book / off-topic — both servers should refuse identically
    {"query": "thời tiết hôm nay thế nào",
     "user_profile": {"lop": 8, "bo_sach": "CTST", "subject": "toan", "tap": 1}},
]


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _post(base, body, timeout):
    r = requests.post(base.rstrip("/") + "/v2/rag/retrieve", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _field(resp, path):
    """resp is {context, intent, sources}; path like 'intent.tier'."""
    cur = resp
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def load_cases(path):
    if not path:
        return DEFAULT_CASES
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monolith", default="http://127.0.0.1:8890")
    ap.add_argument("--thin", default="http://127.0.0.1:8891")
    ap.add_argument("--cases", default=None, help="jsonl of RetrieveRequest bodies")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--out", default=None, help="optional path to write a JSON diff report")
    args = ap.parse_args()

    cases = load_cases(args.cases)
    fields = ["intent.tier", "intent.work_name"]
    tallies = {f: {"match": 0, "total": 0} for f in fields}
    ctx_match = ctx_total = 0
    mismatches = []

    for i, body in enumerate(cases):
        try:
            a = _post(args.monolith, body, args.timeout)
            b = _post(args.thin, body, args.timeout)
        except Exception as e:
            mismatches.append({"i": i, "query": body.get("query"), "error": str(e)})
            print(f"[{i}] ERROR {e}")
            continue

        case_bad = False
        for f in fields:
            av, bv = _field(a, f), _field(b, f)
            tallies[f]["total"] += 1
            if av == bv:
                tallies[f]["match"] += 1
            else:
                case_bad = True
                mismatches.append({"i": i, "query": body.get("query"),
                                   "field": f, "monolith": av, "thin": bv})

        # context: compare only when an anchored tier was returned by either side
        tier = _field(a, "intent.tier") or _field(b, "intent.tier")
        if tier in ("lesson_card", "lesson_recite", "lesson_practice",
                    "A_structured", "A_concept"):
            ctx_total += 1
            if _nfc(a.get("context")) == _nfc(b.get("context")):
                ctx_match += 1
            else:
                case_bad = True
                mismatches.append({"i": i, "query": body.get("query"),
                                   "field": "context", "tier": tier,
                                   "monolith": (a.get("context") or "")[:200],
                                   "thin": (b.get("context") or "")[:200]})

        print(f"[{i}] {'MISMATCH' if case_bad else 'ok'}  tier={_field(a,'intent.tier')}"
              f" work={_field(a,'intent.work_name')!r}")

    print("\n=== SUMMARY ===")
    for f in fields:
        t = tallies[f]
        pct = (100.0 * t["match"] / t["total"]) if t["total"] else 0.0
        print(f"{f:20s} {t['match']}/{t['total']}  {pct:.1f}%")
    cpct = (100.0 * ctx_match / ctx_total) if ctx_total else 0.0
    print(f"{'context(anchored)':20s} {ctx_match}/{ctx_total}  {cpct:.1f}%")
    print(f"mismatches: {len(mismatches)}")

    report = {"summary": {f: tallies[f] for f in fields},
              "context_anchored": {"match": ctx_match, "total": ctx_total},
              "mismatches": mismatches}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"wrote {args.out}")

    # exit non-zero if anything diverged (so it can gate a CI/launch script)
    diverged = any(tallies[f]["match"] != tallies[f]["total"] for f in fields) \
        or (ctx_total and ctx_match != ctx_total) \
        or any("error" in m for m in mismatches)
    sys.exit(1 if diverged else 0)


if __name__ == "__main__":
    main()
