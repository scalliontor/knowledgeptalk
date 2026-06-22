"""Unit tests for packages.backtest.scenario_knowledge.

NO Gemma, NO server, NO Neo4j -- every external call is a fake injected callable
and every /retrieve response is a hand-built dict. Run from repo root::

    python3 -m pytest packages/backtest/tests/test_scenario.py -q

Coverage:
  * robust_json  -- fences, prose-wrapped, arrays, trailing commas, garbage.
  * build_scenarios -- parses {"scenarios":[...]} and bare-array replies,
    coerces bad intent, caps expected_points, skips junk, [] on gen failure.
  * judge -- deterministic anchored/intent/cruft + Gemma-judged knowledge/halluc;
    scoring penalties (no anchor, hallucination, real cruft).
  * score_run -- overall + by_subject + by_intent aggregation, error handling.
"""

import json

from packages.backtest import scenario_knowledge as sk


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def lesson(**kw):
    base = dict(
        work_name="Tự lập",
        subject_code="gdcd",
        grade=6,
        bo_sach="CTST",
        tap_no=None,
        trang_from=12,
        trang_to=14,
        theory="Tự lập là tự làm lấy công việc của mình. Biểu hiện: tự giác học tập. "
        "Ý nghĩa: giúp ta trưởng thành, được tôn trọng.",
        practice=None,
        has_recite=False,
    )
    base.update(kw)
    return base


def scenario(**kw):
    base = dict(
        scenario="Em chưa hiểu tự lập là gì.",
        question="Tự lập là gì và có ý nghĩa thế nào?",
        intent="explain",
        expected_points=["định nghĩa tự lập", "ý nghĩa"],
        lesson=lesson(),
    )
    base.update(kw)
    return base


def served(**kw):
    base = dict(
        tier="lesson_card",
        work_name="Tự lập",
        context="Tự lập là tự làm lấy công việc của mình, giúp ta trưởng thành.",
        error=False,
        latency_ms=40.0,
    )
    base.update(kw)
    return base


def fake_gemma(reply):
    """Return a gemma(system, user) callable that always yields `reply`."""

    def _g(system_prompt, user_prompt):
        return reply

    return _g


def raising_gemma(system_prompt, user_prompt):
    raise RuntimeError("gemma down")


# --------------------------------------------------------------------------- #
# robust_json
# --------------------------------------------------------------------------- #
def test_robust_json_plain_object():
    assert sk.robust_json('{"a": 1}') == {"a": 1}


def test_robust_json_code_fence():
    assert sk.robust_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_robust_json_prose_wrapped():
    raw = 'Đây là kết quả: {"knowledge_correct": 2, "hallucination": false} . Hết.'
    assert sk.robust_json(raw) == {"knowledge_correct": 2, "hallucination": False}


def test_robust_json_array():
    assert sk.robust_json("[1, 2, 3]") == [1, 2, 3]


def test_robust_json_trailing_comma():
    assert sk.robust_json('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_robust_json_garbage_returns_none():
    assert sk.robust_json("no json at all") is None
    assert sk.robust_json("") is None
    assert sk.robust_json(None) is None


# --------------------------------------------------------------------------- #
# build_scenarios
# --------------------------------------------------------------------------- #
def test_build_scenarios_wrapped():
    reply = json.dumps(
        {
            "scenarios": [
                {
                    "scenario": "Em chưa rõ.",
                    "question": "Tự lập là gì?",
                    "intent": "explain",
                    "expected_points": ["a", "b", "c", "d"],  # should cap at 3
                }
            ]
        }
    )
    out = sk.build_scenarios(lesson(), fake_gemma(reply))
    assert len(out) == 1
    assert out[0]["intent"] == "explain"
    assert out[0]["expected_points"] == ["a", "b", "c"]
    assert out[0]["lesson"]["work_name"] == "Tự lập"


def test_build_scenarios_bare_array_and_bad_intent():
    reply = json.dumps(
        [
            {"question": "X?", "intent": "bogus", "expected_points": ["p"]},
            {"question": "", "intent": "explain"},  # no question -> dropped
            {"not": "a question"},  # junk -> dropped
        ]
    )
    out = sk.build_scenarios(lesson(), fake_gemma(reply))
    assert len(out) == 1
    assert out[0]["intent"] == "explain"  # bogus coerced to explain
    assert out[0]["scenario"] == "X?"  # falls back to question when no scenario


def test_build_scenarios_gen_failure_returns_empty():
    assert sk.build_scenarios(lesson(), raising_gemma) == []
    assert sk.build_scenarios(lesson(), fake_gemma("garbage")) == []


# --------------------------------------------------------------------------- #
# judge — deterministic gates
# --------------------------------------------------------------------------- #
def test_judge_full_knowledge_anchored():
    g = fake_gemma('{"knowledge_correct": 2, "hallucination": false}')
    j = sk.judge(scenario(), served(), lesson()["theory"], g)
    assert j["anchored_ok"] is True
    assert j["knowledge_correct"] == 2
    assert j["intent_ok"] is True
    assert j["hallucination"] is False
    assert j["cruft_real"] is False
    # 0.6*1 + 0.25 + 0.15 = 1.0
    assert j["score"] == 1.0


def test_judge_not_anchored_skips_gemma_and_caps_score():
    # Judge must NOT call gemma when nothing anchored; use a gemma that would blow up.
    j = sk.judge(scenario(), served(work_name="Khác bài"), lesson()["theory"], raising_gemma)
    assert j["anchored_ok"] is False
    assert j["knowledge_correct"] == 0
    assert j["score"] == 0.0  # 0.25 * (0/2)


def test_judge_intent_mismatch_lowers_score_but_not_zero():
    # scenario wants practice, served a lesson_card -> intent_ok False
    sc = scenario(intent="practice")
    g = fake_gemma('{"knowledge_correct": 2, "hallucination": false}')
    j = sk.judge(sc, served(tier="lesson_card"), lesson()["theory"], g)
    assert j["anchored_ok"] is True
    assert j["intent_ok"] is False
    # 0.6*1 + 0.25 + 0 = 0.85
    assert j["score"] == 0.85


def test_judge_hallucination_zeros_score():
    g = fake_gemma('{"knowledge_correct": 2, "hallucination": true}')
    j = sk.judge(scenario(), served(), lesson()["theory"], g)
    assert j["hallucination"] is True
    assert j["score"] == 0.0


def test_judge_real_cruft_detected_and_zeros_score():
    g = fake_gemma('{"knowledge_correct": 2, "hallucination": false}')
    rc = served(context="Tự lập là... Giáo viên VietJack biên soạn.")
    j = sk.judge(scenario(), rc, lesson()["theory"], g)
    assert j["cruft_real"] is True
    assert j["score"] == 0.0


def test_judge_bare_giao_vien_is_not_cruft():
    # "giáo viên" alone is legitimate GDCD vocabulary, NOT a leak (canonical).
    g = fake_gemma('{"knowledge_correct": 2, "hallucination": false}')
    rc = served(context="Tự lập giúp em không phụ thuộc giáo viên hay bố mẹ.")
    j = sk.judge(scenario(), rc, lesson()["theory"], g)
    assert j["cruft_real"] is False
    assert j["score"] == 1.0


def test_judge_partial_knowledge_score():
    g = fake_gemma('{"knowledge_correct": 1, "hallucination": false}')
    j = sk.judge(scenario(), served(), lesson()["theory"], g)
    # 0.6*0.5 + 0.25 + 0.15 = 0.7
    assert j["knowledge_correct"] == 1
    assert j["score"] == 0.7


def test_judge_recite_intent_matches_recite_tier():
    sc = scenario(intent="recite")
    g = fake_gemma('{"knowledge_correct": 2, "hallucination": false}')
    j = sk.judge(sc, served(tier="lesson_recite"), lesson()["theory"], g)
    assert j["anchored_ok"] is True  # lesson_recite is a card tier
    assert j["intent_ok"] is True
    assert j["score"] == 1.0


def test_judge_robust_to_bad_judge_json():
    j = sk.judge(scenario(), served(), lesson()["theory"], fake_gemma("the model rambled"))
    assert j["knowledge_correct"] == 0
    assert j["hallucination"] is False  # conservative default


def test_judge_error_response_not_anchored():
    j = sk.judge(scenario(), served(error=True, tier="none"), lesson()["theory"], raising_gemma)
    assert j["anchored_ok"] is False
    assert j["score"] == 0.0


# --------------------------------------------------------------------------- #
# score_run
# --------------------------------------------------------------------------- #
def result(**kw):
    base = dict(
        subject="gdcd",
        intent="explain",
        anchored_ok=True,
        knowledge_correct=2,
        intent_ok=True,
        hallucination=False,
        cruft_real=False,
        score=1.0,
        error=False,
    )
    base.update(kw)
    return base


def test_score_run_overall():
    rows = [
        result(),
        result(knowledge_correct=1, score=0.7),
        result(anchored_ok=False, knowledge_correct=0, intent_ok=False, score=0.0),
    ]
    s = sk.score_run(rows)
    o = s["overall"]
    assert o["n"] == 3
    assert o["total"] == 3
    assert o["errors"] == 0
    assert o["anchor%"] == round(100 * 2 / 3, 1)
    assert o["knowledge_correct_avg"] == round((2 + 1 + 0) / 3, 3)
    assert o["knowledge_full%"] == round(100 * 1 / 3, 1)
    assert o["score_avg"] == round((1.0 + 0.7 + 0.0) / 3, 3)
    assert o["real_cruft"] == 0


def test_score_run_excludes_errors_from_rates():
    rows = [result(), result(error=True, score=0.0, anchored_ok=False)]
    s = sk.score_run(rows)
    o = s["overall"]
    assert o["total"] == 2
    assert o["errors"] == 1
    assert o["n"] == 1  # error excluded from rate denominator
    assert o["anchor%"] == 100.0


def test_score_run_breakdowns():
    rows = [
        result(subject="gdcd", intent="explain"),
        result(subject="toan", intent="practice", knowledge_correct=0, score=0.0, anchored_ok=False),
        result(subject="gdcd", intent="recite"),
    ]
    s = sk.score_run(rows)
    assert set(s["by_subject"].keys()) == {"gdcd", "toan"}
    assert set(s["by_intent"].keys()) == {"explain", "practice", "recite"}
    assert s["by_subject"]["gdcd"]["n"] == 2
    assert s["by_subject"]["toan"]["anchor%"] == 0.0
    assert s["by_intent"]["explain"]["n"] == 1


def test_score_run_hallucination_and_cruft_counts():
    rows = [
        result(hallucination=True, score=0.0),
        result(cruft_real=True, score=0.0),
        result(),
    ]
    s = sk.score_run(rows)["overall"]
    assert s["hallucination%"] == round(100 * 1 / 3, 1)
    assert s["real_cruft"] == 1


def test_score_run_empty():
    s = sk.score_run([])
    assert s["overall"]["n"] == 0
    assert s["overall"]["total"] == 0
    assert s["by_subject"] == {}
