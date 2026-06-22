"""Query routing (intent → subject/title/keyword/query_type).

EXTRACTED VERBATIM from /tmp/refsrc_canary.py. The Gemma-free path
(`route_query_rule_based`, `_is_recite`, and the four recite/not-recite regexes)
is byte-for-byte identical to the source and is the production serve path.

`route_query` (the Gemma path) had a module-level dependency on `call_gemma`
(an HTTP call to the LLM). To keep this module IO-free, `call_gemma` is now an
INJECTED callable parameter (`call_gemma(system_prompt, user_prompt) -> str`).
The body is otherwise unchanged. `route_query` is NOT on the latency-critical
serve path in the canary runtime (the orchestrator uses
`route_query_rule_based`).
"""
from __future__ import annotations

import json
import re
from typing import Dict, Any, Callable


_RECITE_STRONG = re.compile(r"(đọc thuộc|đọc diễn cảm|đọc nguyên văn|đọc cả bài|đọc hết bài|đọc nguyên bài|"
    r"học thuộc|thuộc lòng|ngâm thơ|ngâm bài|đọc to bài|đọc lại bài|"
    r"đọc.{0,15}cho.{0,12}nghe|cho.{0,12}nghe.{0,8}(bài thơ|bài|tác phẩm|truyện)|"
    r"ngâm.{0,12}(bài thơ|thơ|tác phẩm)|đọc.{0,15}truyền cảm|truyền cảm|ngâm nga|đọc.{0,12}cho.{0,12}nghe)")
_RECITE_VERB = re.compile(r"\b(đọc|kể|ngâm|thuộc)\b")
_RECITE_NOUN = re.compile(r"(bài thơ|bài|văn bản|tác phẩm|truyện|chuyện|câu chuyện|đoạn thơ|khổ thơ|bài ca dao|bài vè)")
_NOT_RECITE = re.compile(r"(đọc hiểu|đọc kỹ|đọc kĩ|đọc đề|đọc thêm|đọc mở rộng|đọc trước|"
    r"soạn|phân tích|giải thích|giải bài|tóm tắt|cảm nghĩ|cảm nhận|nội dung|ý nghĩa|"
    r"viết|tập đọc|luyện đọc|cách đọc)")


def _is_recite(q_lower: str) -> bool:
    """Hardened recite detection: exclude reading-comprehension/analysis uses of 'đọc'."""
    if _NOT_RECITE.search(q_lower):
        return False
    if _RECITE_STRONG.search(q_lower):
        return True
    return bool(_RECITE_VERB.search(q_lower) and _RECITE_NOUN.search(q_lower))


def route_query_rule_based(query: str) -> Dict[str, Any]:
    """Fast fallback when Gemma router is unavailable or returns invalid JSON."""
    q = query.strip()
    q_lower = q.lower()

    if (
        re.match(r"^(chào|xin chào|hi|hello|alo|a lô|cậu ơi|bạn ơi)(\s+\w+){0,3}[\s,.!?ạ]*$", q_lower)
        or re.search(r"\b(cậu|bạn)\s+(đang\s+)?(làm gì|khỏe không|ở đâu|nghe không)\b", q_lower)
    ):
        return {
            "need_rag": False,
            "subject": None,
            "title": None,
            "keyword": "",
            "query_type": "chat",
            "need_web_search": False,
            "search_query": "",
        }

    if _is_recite(q_lower):
        title = re.sub(
            r"(?i).*(?:bài thơ|văn bản|tác phẩm|bài)\s+",
            "",
            q,
            count=1,
        )
        title = re.sub(r"(?i)\s+(cho|nghe|đi|nhé|nha|ạ|với|tôi|em|con).*$", "", title).strip(" .!?\"'")
        return {
            "need_rag": True,
            "subject": "ngu_van",
            "title": title or q,
            "keyword": title or q,
            "query_type": "recite_full_text",
            "need_web_search": False,
            "search_query": "",
        }

    return {
        "need_rag": True,
        "subject": None,
        "title": None,
        "keyword": q,
        "query_type": "explain",
        "need_web_search": False,
        "search_query": "",
    }


def route_query(query: str, call_gemma: Callable[[str, str], str]) -> Dict[str, Any]:
    """Phân tích ý định câu hỏi bằng Gemma-4.

    NOTE (refactor): `call_gemma` is INJECTED as a callable to keep this module
    IO-free. In the original single-file server it was a module-level function
    making an HTTP request to the local Gemma endpoint. The body below is
    otherwise verbatim.
    """
    system_prompt = """Output strict JSON:
{"s":"<Toán|Ngữ Văn|KHTN|Lịch Sử|Địa Lý|null>","t":"<Title if any>","k":"<Keyword>","q":"<r if read/recite, e if explain>"}"""
    response_text = call_gemma(system_prompt, query)
    # Xử lý xoá code block markdown nếu có
    response_text = response_text.replace('```json', '').replace('```', '').strip()
    try:
        data = json.loads(response_text)
        return {
            "need_rag": True,
            "subject": data.get("s"),
            "title": data.get("t"),
            "keyword": data.get("k") or query,
            "query_type": "recite_full_text" if data.get("q") == "r" else "explain"
        }
    except Exception as e:
        print(f"[Router Error] Không parse được JSON: {response_text}")
        return route_query_rule_based(query)
