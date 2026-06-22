#!/usr/bin/env python3
"""scenario_backtest.py — KNOWLEDGE scenario backtest RUNNER (server-side).

⚠️ THIS RUNS ON THE BUILD/SERVER HOST ONLY. It is NOT executed in this repo's
CI / local dev loop (no Neo4j, no Gemma, no /retrieve here). The PURE logic it
drives lives in packages/backtest/scenario_knowledge.py and is unit-tested with
fakes (packages/backtest/tests/test_scenario.py). This file is the thin I/O shell:
read Neo4j -> generate scenarios (Gemma) -> POST /retrieve -> judge (Gemma) ->
aggregate -> write reports/backtest/scenarios/<book>_<ts>.json.

WHAT IT MEASURES (vs backtest_book.py)
--------------------------------------
backtest_book.py scores ROUTING (did the right card anchor, right tier, no cruft,
guards refuse). THIS scores KNOWLEDGE: for each :Lesson, Gemma invents realistic
study scenarios grounded in that lesson's THEORY, we fire them at the companion,
and Gemma judges whether the SERVED context actually contains the correct &
sufficient knowledge (ground truth = the lesson's own theory). See the judge
rubric in scenario_knowledge.py.

USAGE (on the server, with services up):
    EDU_NEO4J_PW=... GEMMA_KEY=... \
    python3 scripts/scenario_backtest.py <subject> <grade> <book> <tap> <n_lessons> <port>
  e.g.
    python3 scripts/scenario_backtest.py gdcd 6 CTST none 12 8889

  <tap> = volume number or 'none'/'None' for single-volume books.
  <n_lessons> = how many lessons to sample (each yields ~6 scenarios).
  <port> = canary port (8889/8890). NEVER 8888 (production).

ENV:
  EDU_NEO4J_PW   (required)  Neo4j edu password.
  EDU_NEO4J_URI  (optional)  default bolt://localhost:7688.
  GEMMA_KEY      (required)  Bearer key for the local Gemma OpenAI-compatible API.
  GEMMA_URL      (optional)  default http://localhost:8080/v1/chat/completions.

OUTPUT:
  reports/backtest/scenarios/<subject>_<grade>_<book>_t<tap>_<UTC-ts>.json
  + a printed summary (score_run aggregate).
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

# Make `packages` importable when run from the repo root on the server.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from packages.backtest.scenario_knowledge import build_scenarios, judge, score_run  # noqa: E402

# --------------------------------------------------------------------------- #
# args
# --------------------------------------------------------------------------- #
SUBJECT = sys.argv[1] if len(sys.argv) > 1 else "gdcd"
GRADE = int(sys.argv[2]) if len(sys.argv) > 2 else 6
BOOK = sys.argv[3] if len(sys.argv) > 3 else "CTST"
_TAP_ARG = sys.argv[4] if len(sys.argv) > 4 else "none"
TAP = None if _TAP_ARG.lower() in ("none", "null", "") else int(_TAP_ARG)
N_LESSONS = int(sys.argv[5]) if len(sys.argv) > 5 else 12
PORT = sys.argv[6] if len(sys.argv) > 6 else "8889"

if PORT == "8888":
    sys.exit("REFUSING: PORT=8888 is production. Use canary 8889/8890.")

# --------------------------------------------------------------------------- #
# env / endpoints (NO hardcoded secrets)
# --------------------------------------------------------------------------- #
NEO4J_URI = os.environ.get("EDU_NEO4J_URI", "bolt://localhost:7688")
NEO4J_PW = os.environ.get("EDU_NEO4J_PW", "")
RETRIEVE_URL = f"http://localhost:{PORT}/retrieve"
GEMMA_URL = os.environ.get("GEMMA_URL", "http://localhost:8080/v1/chat/completions")
GEMMA_KEY = os.environ.get("GEMMA_KEY", "")


def gemma(system_prompt, user_prompt, max_tokens=1400):
    """Injected LLM callable (generator + judge). OpenAI-compatible Gemma API.
    Mirrors backtest_book.py gemma(): POST /v1/chat/completions, Bearer GEMMA_KEY,
    model gemma-4. Raises on HTTP/JSON error (callers in scenario_knowledge swallow)."""
    body = json.dumps(
        {
            "model": "gemma-4",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        GEMMA_URL,
        data=body,
        headers={"Authorization": f"Bearer {GEMMA_KEY}", "Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["choices"][0]["message"]["content"]


def post_retrieve(query, user_profile):
    """POST one query to the companion /retrieve and normalise the response into the
    `response_context` shape consumed by scenario_knowledge.judge()."""
    body = json.dumps({"query": query, "user_profile": user_profile}).encode()
    req = urllib.request.Request(RETRIEVE_URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        ms = (time.time() - t0) * 1000.0
        intent = resp.get("intent", {}) or {}
        return {
            "tier": intent.get("tier", "none"),
            "work_name": intent.get("work_name", ""),
            "context": resp.get("context", "") or "",
            "error": False,
            "latency_ms": round(ms, 1),
        }
    except Exception as e:  # network / timeout / decode
        return {"tier": "none", "work_name": "", "context": "", "error": True,
                "latency_ms": None, "exc": str(e)[:120]}


# --------------------------------------------------------------------------- #
# 1. pull ground-truth lessons from Neo4j edu
# --------------------------------------------------------------------------- #
def pull_lessons():
    from neo4j import GraphDatabase  # imported here so the module imports without driver

    drv = GraphDatabase.driver(NEO4J_URI, auth=("neo4j", NEO4J_PW))
    cypher = """
        MATCH (l:Lesson {subject_code:$s, grade:$g, bo_sach:$b})
        WHERE ($tap IS NULL OR l.tap_no=$tap)
        OPTIONAL MATCH (l)-[:HAS_THEORY]->(t)
        OPTIONAL MATCH (l)-[:HAS_RECITE]->(r)
        RETURN l.work_name AS work_name, l.subject_code AS subject_code,
               l.grade AS grade, l.bo_sach AS bo_sach, l.tap_no AS tap_no,
               l.trang_from AS trang_from, l.trang_to AS trang_to,
               l.practice_json AS practice,
               collect(DISTINCT t.text)[0] AS theory,
               count(DISTINCT r) AS recite_n
    """
    try:
        with drv.session() as s:
            rows = s.run(cypher, s=SUBJECT, g=GRADE, b=BOOK, tap=TAP).data()
    finally:
        drv.close()
    lessons = []
    for r in rows:
        if not r.get("work_name") or not (r.get("theory") or "").strip():
            continue  # need a name + theory ground truth
        lessons.append(
            {
                "work_name": r["work_name"],
                "subject_code": r.get("subject_code") or SUBJECT,
                "grade": r.get("grade") or GRADE,
                "bo_sach": r.get("bo_sach") or BOOK,
                "tap_no": r.get("tap_no"),
                "trang_from": r.get("trang_from"),
                "trang_to": r.get("trang_to"),
                "theory": r["theory"],
                "practice": r.get("practice"),
                "has_recite": (r.get("recite_n") or 0) > 0,
            }
        )
    return lessons[:N_LESSONS]


# --------------------------------------------------------------------------- #
# 2. drive: scenarios -> /retrieve -> judge
# --------------------------------------------------------------------------- #
def run():
    lessons = pull_lessons()
    print(f"[scenario] {len(lessons)} lessons w/ theory for {SUBJECT} {GRADE} {BOOK} tap={TAP}", flush=True)

    results = []
    for li, lesson in enumerate(lessons):
        scenarios = build_scenarios(lesson, gemma)
        if not scenarios:
            print(f"  [{li+1}/{len(lessons)}] {lesson['work_name'][:30]}: 0 scenarios (gen skip)", flush=True)
            continue
        for sc in scenarios:
            # Production-realistic profile: client always supplies current_lesson.
            profile = {
                "current_lesson": lesson["work_name"],
                "lop": GRADE,
                "subject": SUBJECT,
                "bo_sach": BOOK,
            }
            if lesson.get("tap_no") is not None:
                profile["tap"] = lesson["tap_no"]
            rc = post_retrieve(sc["question"], profile)
            j = judge(sc, rc, lesson["theory"], gemma)
            results.append(
                {
                    "subject": SUBJECT,
                    "intent": sc["intent"],
                    "work_name": lesson["work_name"],
                    "scenario": sc["scenario"],
                    "question": sc["question"],
                    "expected_points": sc["expected_points"],
                    "served_tier": rc.get("tier"),
                    "served_work": rc.get("work_name"),
                    "latency_ms": rc.get("latency_ms"),
                    "error": rc.get("error", False),
                    # judgement fields (consumed by score_run)
                    "anchored_ok": j["anchored_ok"],
                    "knowledge_correct": j["knowledge_correct"],
                    "intent_ok": j["intent_ok"],
                    "hallucination": j["hallucination"],
                    "cruft_real": j["cruft_real"],
                    "score": j["score"],
                }
            )
        print(f"  [{li+1}/{len(lessons)}] {lesson['work_name'][:30]}: {len(scenarios)} scenarios judged", flush=True)

    summary = score_run(results)

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = os.path.join(_REPO_ROOT, "reports", "backtest", "scenarios")
    os.makedirs(out_dir, exist_ok=True)
    tap_lbl = "none" if TAP is None else str(TAP)
    out_path = os.path.join(out_dir, f"{SUBJECT}_{GRADE}_{BOOK}_t{tap_lbl}_{ts}.json")
    report = {
        "meta": {
            "subject": SUBJECT, "grade": GRADE, "book": BOOK, "tap": TAP,
            "n_lessons_requested": N_LESSONS, "n_lessons_used": len(lessons),
            "port": PORT, "neo4j_uri": NEO4J_URI, "generated_utc": ts,
        },
        "summary": summary,
        "results": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print("\n" + "=" * 70 + "\nSCENARIO KNOWLEDGE BACKTEST — SUMMARY\n" + "=" * 70)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\nSAVED {out_path}")


if __name__ == "__main__":
    run()
