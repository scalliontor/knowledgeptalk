"""Scenario-level KNOWLEDGE backtest for the Knowledge PTalk companion.

WHY THIS EXISTS (vs backtest_book.py)
-------------------------------------
The existing per-book backtest (rag_edu/scripts/schema_v3_2026_06/backtest_book.py)
scores only ROUTING quality: did the right :Lesson card anchor, with the right
tier, without source cruft, and did guards refuse. That answers "did we point at
the right page?" -- not "did the student actually get the right KNOWLEDGE?".

This module scores the second question with an LLM-as-judge. For each :Lesson we
ask Gemma to invent ~6 realistic STUDY SCENARIOS grounded in that lesson's own
theory, fire them at the companion's /retrieve, then have Gemma JUDGE whether the
served context contains the correct, sufficient knowledge for that scenario.

PURITY / DEPENDENCY INJECTION
-----------------------------
This module is pure-ish: it performs NO network I/O and reads NO secrets itself.
Everything that touches the outside world is INJECTED as a callable:

    gemma(system_prompt, user_prompt) -> str      # the LLM (judge + generator)

The Neo4j read and the /retrieve POST live in the RUNNER (scripts/scenario_backtest.py),
which reads EDU_NEO4J_PW / EDU_NEO4J_URI / GEMMA_KEY from the environment. This
file only transforms data + builds/parses prompts, so it is unit-testable with a
fake gemma() and fake responses (see packages/backtest/tests/test_scenario.py).

Python 3.8 compatible (no PEP 604 unions; `from __future__ import annotations`).

DATA SHAPES
-----------
A `lesson` dict (produced by the runner from Neo4j) -- minimal shape::

    {
      "work_name": "Tự lập",
      "subject_code": "gdcd",
      "grade": 6,
      "bo_sach": "CTST",
      "tap_no": None,            # or 1 / 2
      "trang_from": 12, "trang_to": 14,
      "theory": "....",          # HAS_THEORY text (ground truth knowledge)
      "practice": "...." | None, # practice_json / practice text (optional)
      "has_recite": False,       # whether a HAS_RECITE node exists
    }

A `scenario` dict (one study situation), produced by build_scenarios()::

    {
      "scenario": "Em đang ôn bài và chưa rõ vì sao cần tự lập.",
      "question": "Tự lập là gì và vì sao học sinh cần tự lập?",
      "intent": "explain",                 # explain | practice | recite
      "expected_points": ["định nghĩa tự lập", "ý nghĩa/ vai trò", "biểu hiện"],
      "lesson": <the lesson dict>,         # carried for judging / anchoring
    }

A `response_context` dict (what the runner records from /retrieve)::

    {
      "tier": "lesson_card",     # resp["intent"]["tier"]
      "work_name": "Tự lập",     # resp["intent"]["work_name"]
      "context": "....",         # resp["context"]  -- the served text
      "error": False,
      "latency_ms": 41.0,
    }

A `judgement` dict (output of judge())::

    {
      "anchored_ok": True,        # did the right lesson card anchor?
      "knowledge_correct": 2,     # 0 = wrong/missing, 1 = partial, 2 = full
      "intent_ok": True,          # did the served tier match the scenario intent?
      "hallucination": False,     # did the answer invent facts outside theory?
      "cruft_real": False,        # genuine source leak (vietjack / lời giải / ...)
      "score": 1.0,               # composite 0..1, see _composite_score()
      "judge_raw": "...",         # raw judge text (debug)
    }
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Sequence

# Reuse the SAME real-cruft definition as metrics.py so "sạch nguồn" is judged
# identically across both backtests. The bare word "giáo viên" is NOT a leak.
from .metrics import context_has_real_cruft

# Serving tiers that mean a lesson card was emitted (mirror metrics.CARD_TIERS).
CARD_TIERS = frozenset({"lesson_card", "lesson_practice", "lesson_recite"})

# Map a scenario intent -> the tier(s) we expect /retrieve to serve.
# explain  -> lesson_card (the companion's teach/explain card)
# practice -> lesson_practice (guided practice)
# recite   -> lesson_recite (verbatim recitation)
INTENT_EXPECTED_TIERS = {
    "explain": frozenset({"lesson_card"}),
    "practice": frozenset({"lesson_practice"}),
    "recite": frozenset({"lesson_recite"}),
}

VALID_INTENTS = frozenset(INTENT_EXPECTED_TIERS.keys())


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _norm(x: Optional[str]) -> str:
    """Diacritic-folding normaliser, identical to backtest_book.py / metrics."""
    x = (x or "").replace("đ", "d").replace("Đ", "D")
    x = unicodedata.normalize("NFD", x)
    return "".join(c for c in x if unicodedata.category(c) != "Mn").lower().strip()


def robust_json(raw: Optional[str]) -> Optional[Any]:
    """Best-effort extract a JSON value from an LLM reply.

    Tolerant of: ```json fences, leading/trailing prose, single trailing commas.
    Tries the whole string first, then the widest {...} or [...] span. Returns the
    decoded object, or None if nothing parses. NEVER raises.
    """
    if not raw:
        return None
    s = raw.strip()
    # strip code fences
    s = s.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates: List[str] = [s]
    # widest object span and widest array span
    for opener, closer in (("{", "}"), ("[", "]")):
        i = s.find(opener)
        j = s.rfind(closer)
        if i != -1 and j != -1 and j > i:
            candidates.append(s[i : j + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception:
            # tolerate a single trailing comma before } or ]
            try:
                fixed = re.sub(r",\s*([}\]])", r"\1", cand)
                return json.loads(fixed)
            except Exception:
                continue
    return None


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except Exception:
        return default
    return max(lo, min(hi, n))


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "có", "co", "đúng", "dung")
    return False


# --------------------------------------------------------------------------- #
# 1. scenario generation (grounded on the lesson's own theory)
# --------------------------------------------------------------------------- #
_GEN_SYS = (
    "Bạn là người thiết kế bài test cho trợ lý học tập (gia sư) bám SGK. "
    "Bạn tạo các TÌNH HUỐNG HỌC TẬP THẬT giọng học sinh, kèm câu hỏi KIẾN THỨC "
    "mà CHỈ DỰA VÀO nội dung bài học bên dưới là trả lời được. "
    "TUYỆT ĐỐI không bịa kiến thức ngoài nội dung được cho. Chỉ trả JSON, không giải thích."
)


def _gen_user_prompt(lesson: Dict[str, Any]) -> str:
    theory = (lesson.get("theory") or "")[:1600]
    has_prac = bool(lesson.get("practice"))
    has_rec = bool(lesson.get("has_recite"))
    extra = []
    if has_prac:
        extra.append('1 kịch bản intent="practice" (xin làm/luyện bài tập của bài này)')
    if has_rec:
        extra.append('1 kịch bản intent="recite" (xin ĐỌC THUỘC/đọc nguyên văn)')
    extra_line = (" Bắt buộc thêm: " + "; ".join(extra) + ".") if extra else ""
    return (
        "BÀI: {work}\n"
        "MÔN: {subj} lớp {grade} (bộ {book})\n"
        "NỘI DUNG BÀI (ground truth, dùng để ra câu hỏi & chấm điểm):\n"
        "<<<\n{theory}\n>>>\n\n"
        "Tạo ĐÚNG 6 kịch bản học tập đa dạng, bám nội dung trên. Đa dạng kiểu: "
        "hỏi KHÁI NIỆM, hỏi VÍ DỤ/biểu hiện, 'em chưa hiểu phần ...', hỏi VẬN DỤNG/liên hệ."
        "{extra}\n"
        "Mỗi kịch bản là object:\n"
        '{{"scenario": "tình huống giọng học sinh (1 câu)",'
        ' "question": "câu hỏi kiến thức trả lời được TỪ nội dung bài",'
        ' "intent": "explain|practice|recite",'
        ' "expected_points": ["2-3 ý KIẾN THỨC CỐT LÕI trích từ nội dung bài để trả lời câu hỏi"]}}\n'
        'Trả về JSON: {{"scenarios": [ ...6 object... ]}}'
    ).format(
        work=lesson.get("work_name", ""),
        subj=lesson.get("subject_code", ""),
        grade=lesson.get("grade", ""),
        book=lesson.get("bo_sach", ""),
        theory=theory,
        extra=extra_line,
    )


def _coerce_scenario(raw: Any, lesson: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate/normalise one scenario object from the LLM. Returns None if junk."""
    if not isinstance(raw, dict):
        return None
    question = (raw.get("question") or "").strip()
    if not question:
        return None
    intent = (raw.get("intent") or "explain").strip().lower()
    if intent not in VALID_INTENTS:
        intent = "explain"
    pts_raw = raw.get("expected_points") or []
    if isinstance(pts_raw, str):
        pts_raw = [pts_raw]
    points = [str(p).strip() for p in pts_raw if str(p).strip()]
    return {
        "scenario": (raw.get("scenario") or "").strip() or question,
        "question": question,
        "intent": intent,
        "expected_points": points[:3],
        "lesson": lesson,
    }


def build_scenarios(lesson: Dict[str, Any], gemma: Callable[[str, str], str]) -> List[Dict[str, Any]]:
    """Generate ~6 grounded study scenarios for one :Lesson.

    `gemma(system_prompt, user_prompt) -> str` is INJECTED (the runner builds it
    from GEMMA_KEY/host). Returns [] on any generation failure -- the caller
    decides whether to skip the lesson. NEVER raises.
    """
    try:
        raw = gemma(_GEN_SYS, _gen_user_prompt(lesson))
    except Exception:
        return []
    parsed = robust_json(raw)
    items: Sequence[Any]
    if isinstance(parsed, dict):
        items = parsed.get("scenarios") or []
    elif isinstance(parsed, list):
        items = parsed
    else:
        return []
    out: List[Dict[str, Any]] = []
    for it in items:
        sc = _coerce_scenario(it, lesson)
        if sc is not None:
            out.append(sc)
    return out


# --------------------------------------------------------------------------- #
# 2. judge (LLM-as-judge over the SERVED context vs the lesson's theory)
# --------------------------------------------------------------------------- #
_JUDGE_SYS = (
    "Bạn là giám khảo nghiêm khắc chấm câu trả lời của một trợ lý học tập (gia sư) bám SGK. "
    "Bạn so NỘI DUNG GỐC của bài (ground truth) với NGỮ CẢNH trợ lý đã phục vụ học sinh. "
    "Chỉ chấm dựa trên NỘI DUNG GỐC; bất kỳ điều gì NGOÀI nội dung gốc đều là BỊA (hallucination). "
    "Chỉ trả JSON đúng schema, không thêm chữ nào khác."
)

# Rubric is embedded in the user prompt so it travels with each call (the judge
# model is stateless). See module docstring + judge() for the field meanings.
_JUDGE_RUBRIC = (
    "RUBRIC (chấm CHẶT, chỉ dựa NỘI DUNG GỐC):\n"
    "- knowledge_correct: 0 = sai hoặc không có kiến thức cho câu hỏi; "
    "1 = đúng nhưng THIẾU (không đủ expected_points); "
    "2 = ĐÚNG và ĐỦ các expected_points (diễn đạt khác cũng được, miễn đúng ý).\n"
    "- hallucination: true nếu NGỮ CẢNH chứa khẳng định kiến thức KHÔNG có trong NỘI DUNG GỐC.\n"
    "- expected_points: chỉ tính điểm khi ý đó THỰC SỰ xuất hiện (đồng nghĩa được) trong NGỮ CẢNH.\n"
    "Diễn đạt lại / tóm tắt đúng ý KHÔNG phải hallucination."
)


def _judge_user_prompt(scenario: Dict[str, Any], response_context: Dict[str, Any], theory: str) -> str:
    pts = scenario.get("expected_points") or []
    pts_str = "\n".join("  - " + p for p in pts) if pts else "  (không nêu rõ)"
    served = (response_context.get("context") or "")[:2000]
    return (
        "NỘI DUNG GỐC CỦA BÀI (ground truth):\n<<<\n{theory}\n>>>\n\n"
        "TÌNH HUỐNG HỌC SINH: {scenario}\n"
        "CÂU HỎI: {question}\n"
        "Ý KIẾN THỨC CẦN CÓ (expected_points):\n{pts}\n\n"
        "NGỮ CẢNH TRỢ LÝ ĐÃ PHỤC VỤ:\n<<<\n{served}\n>>>\n\n"
        "{rubric}\n\n"
        'Trả JSON: {{"knowledge_correct": 0|1|2, "hallucination": true|false, '
        '"reason": "ngắn gọn vì sao"}}'
    ).format(
        theory=(theory or "")[:1800],
        scenario=scenario.get("scenario", ""),
        question=scenario.get("question", ""),
        pts=pts_str,
        served=served,
        rubric=_JUDGE_RUBRIC,
    )


def _anchored_ok(scenario: Dict[str, Any], response_context: Dict[str, Any]) -> bool:
    """Did the right lesson card anchor? Deterministic (no LLM): normalised
    work_name match + a card tier was emitted. Mirrors backtest_book anchor."""
    if response_context.get("error"):
        return False
    if response_context.get("tier", "none") not in CARD_TIERS:
        return False
    expected_work = (scenario.get("lesson") or {}).get("work_name")
    return _norm(response_context.get("work_name")) == _norm(expected_work)


def _intent_ok(scenario: Dict[str, Any], response_context: Dict[str, Any]) -> bool:
    """Did the served tier match the scenario's pedagogical intent?"""
    expected = INTENT_EXPECTED_TIERS.get(scenario.get("intent", "explain"), CARD_TIERS)
    return response_context.get("tier", "none") in expected


def _composite_score(anchored_ok: bool, knowledge_correct: int, intent_ok: bool,
                     hallucination: bool, cruft_real: bool) -> float:
    """Composite 0..1. KNOWLEDGE dominates; anchoring/intent are gates/bonuses;
    hallucination and real cruft are hard penalties (zero-out).

    - If not anchored: max 0.25 (a wrong/no card cannot teach the right knowledge).
    - hallucination OR real cruft -> 0.0 (a confident wrong/leaky answer is worse
      than a refusal for a learning companion).
    - else base = 0.6*knowledge(0..2 -> 0..1) + 0.25*anchored + 0.15*intent.
    """
    if hallucination or cruft_real:
        return 0.0
    if not anchored_ok:
        # partial credit only if some knowledge leaked through a non-anchored path
        return round(0.25 * (knowledge_correct / 2.0), 3)
    base = 0.6 * (knowledge_correct / 2.0) + 0.25 * 1.0 + 0.15 * (1.0 if intent_ok else 0.0)
    return round(base, 3)


def judge(scenario: Dict[str, Any], response_context: Dict[str, Any], theory: str,
          gemma: Callable[[str, str], str]) -> Dict[str, Any]:
    """LLM-judge one (scenario, served-context) pair against the lesson theory.

    Deterministic fields (anchored_ok, intent_ok, cruft_real) are computed in
    Python; only knowledge_correct + hallucination come from Gemma. `gemma` is
    INJECTED. NEVER raises; on judge failure knowledge_correct defaults to 0 and
    hallucination to False (conservative: missing knowledge, no false leak claim).
    """
    anchored = _anchored_ok(scenario, response_context)
    intent_ok = _intent_ok(scenario, response_context)
    cruft_real = bool(
        response_context.get("tier", "none") in CARD_TIERS
        and context_has_real_cruft(response_context.get("context"))
    )

    knowledge_correct = 0
    hallucination = False
    judge_raw = ""
    # Only consult the judge if a card actually anchored AND no error -- judging a
    # refusal/empty context for knowledge is meaningless (it has none by design).
    if anchored and not response_context.get("error"):
        try:
            judge_raw = gemma(_JUDGE_SYS, _judge_user_prompt(scenario, response_context, theory))
        except Exception:
            judge_raw = ""
        parsed = robust_json(judge_raw)
        if isinstance(parsed, dict):
            knowledge_correct = _clamp_int(parsed.get("knowledge_correct"), 0, 2, 0)
            hallucination = _as_bool(parsed.get("hallucination"))

    score = _composite_score(anchored, knowledge_correct, intent_ok, hallucination, cruft_real)
    return {
        "anchored_ok": anchored,
        "knowledge_correct": knowledge_correct,
        "intent_ok": intent_ok,
        "hallucination": hallucination,
        "cruft_real": cruft_real,
        "score": score,
        "judge_raw": judge_raw,
    }


# --------------------------------------------------------------------------- #
# 3. aggregate scoring
# --------------------------------------------------------------------------- #
def _pct(num: float, den: float) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def _avg(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def score_run(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a list of per-scenario result records into a run summary.

    Each `result` is expected to carry the judgement fields plus optional slice
    labels. Minimal shape (the runner produces this)::

        {
          "anchored_ok": bool, "knowledge_correct": 0|1|2, "intent_ok": bool,
          "hallucination": bool, "cruft_real": bool, "score": float,
          "subject": "gdcd", "intent": "explain", "error": False,
        }

    Returns overall metrics + breakdown by subject and by intent dimension.
    Errored records are counted but excluded from rate denominators (except the
    explicit error count). NEVER raises.
    """
    results = list(results)
    ok = [r for r in results if not r.get("error")]
    n = len(ok)

    def _block(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        m = len(rows)
        return {
            "n": m,
            "anchor%": _pct(sum(1 for r in rows if r.get("anchored_ok")), m),
            "knowledge_correct_avg": _avg([float(r.get("knowledge_correct", 0)) for r in rows]),
            "knowledge_full%": _pct(sum(1 for r in rows if r.get("knowledge_correct", 0) == 2), m),
            "intent%": _pct(sum(1 for r in rows if r.get("intent_ok")), m),
            "hallucination%": _pct(sum(1 for r in rows if r.get("hallucination")), m),
            "real_cruft": sum(1 for r in rows if r.get("cruft_real")),
            "score_avg": _avg([float(r.get("score", 0.0)) for r in rows]),
        }

    by_subject: Dict[str, Dict[str, Any]] = {}
    by_intent: Dict[str, Dict[str, Any]] = {}
    for r in ok:
        by_subject.setdefault(r.get("subject", "unknown"), []).append(r)  # type: ignore[arg-type]
        by_intent.setdefault(r.get("intent", "unknown"), []).append(r)  # type: ignore[arg-type]

    overall = _block(ok)
    overall["total"] = len(results)
    overall["errors"] = sum(1 for r in results if r.get("error"))
    return {
        "overall": overall,
        "by_subject": {k: _block(v) for k, v in sorted(by_subject.items())},  # type: ignore[arg-type]
        "by_intent": {k: _block(v) for k, v in sorted(by_intent.items())},  # type: ignore[arg-type]
    }
