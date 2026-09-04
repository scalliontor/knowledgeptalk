from __future__ import annotations

import asyncio
import json
import re
import difflib
import requests
import unicodedata
from typing import Dict, Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from neo4j import GraphDatabase
import time
import urllib.parse
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    _VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:
    _VN_TZ = None

# I4 — Diacritic folding helper (graceful fallback if unidecode not installed)
try:
    from unidecode import unidecode
except ImportError:
    def unidecode(s):
        return s  # graceful fallback


def _fold(s: str) -> str:
    """Lowercase + strip Vietnamese diacritics (self-contained: đ→d + NFD strip; matches name_norm)."""
    s = (s or "").replace("đ", "d").replace("Đ", "D").replace("–", "-")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


# I3 — Book series alias normalizer
BOOK_ALIASES = {
    "kntt": "KNTT", "k.n.t.t": "KNTT", "ket noi": "KNTT",
    "kết nối": "KNTT", "kết nối tri thức": "KNTT",
    "kntt voi cuoc song": "KNTT", "kt": "KNTT",
    "ctst": "CTST", "chan troi": "CTST",
    "chân trời": "CTST", "chân trời sáng tạo": "CTST", "ct st": "CTST",
    "cd": "CD", "canh dieu": "CD",
    "cánh diều": "CD", "cánh-diều": "CD",
}


def _normalize_book_token(tok: str) -> Optional[str]:
    if not tok:
        return None
    low = tok.lower().strip()
    return BOOK_ALIASES.get(low)


app = FastAPI(title="PTalk RAG Server", version="1.0")

# --- CONFIG ---
# Secret/endpoint đọc từ .env (KHÔNG hardcode — .env đã gitignore).
import os as _os
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=True)
except ImportError:
    pass

LLM_API_URL = _os.getenv("RAG_LLM_API_URL", "http://localhost:8080/v1/chat/completions")
LLM_API_KEY = _os.getenv("RAG_LLM_API_KEY", "")
LLM_MODEL = _os.getenv("RAG_LLM_MODEL", "gemma-4")

NEO4J_URI = _os.getenv("NEO4J_URI", "bolt://localhost:7688")
NEO4J_AUTH = (_os.getenv("NEO4J_USER", "neo4j"), _os.getenv("NEO4J_PASSWORD", ""))
if not NEO4J_AUTH[1] or not LLM_API_KEY:
    print("[RAG SERVER] ⚠️ Thiếu NEO4J_PASSWORD / RAG_LLM_API_KEY trong .env")

# --- GLOBAL MODEL ---
import os
os.environ['HF_HOME'] = "/home/namnx/.cache/huggingface"
from sentence_transformers import SentenceTransformer
print("[RAG SERVER] Đang tải mô hình BAAI/bge-m3 lên VRAM...")
bge_m3_model = SentenceTransformer("BAAI/bge-m3")
print("[RAG SERVER] Tải mô hình hoàn tất!")

# ── Intent classifier bằng embedding (robust với paraphrase, không cần Gemma) ──
_INTENT_ANCHORS = {
    "recite": ["đọc thuộc bài thơ này", "đọc cả bài cho mình nghe", "đọc full toàn bộ bài",
               "đọc bài thơ này lên", "ngâm bài thơ", "đọc diễn cảm bài này", "đọc to nguyên bài cho nghe"],
    "practice": ["làm bài tập bài này", "luyện tập trả lời câu hỏi", "giải các câu hỏi trong bài",
                 "cho mình mấy câu để ôn tập", "tự kiểm tra kiến thức", "thực hành làm bài"],
    "explain": ["giảng nội dung bài này", "phân tích ý nghĩa tác phẩm", "tóm tắt nội dung chính",
                "tác giả là ai", "bố cục bài thơ", "giá trị nghệ thuật của bài"],
}
try:
    _INTENT_EMB = {k: [bge_m3_model.encode([p], normalize_embeddings=True)[0].tolist() for p in v]
                   for k, v in _INTENT_ANCHORS.items()}
except Exception as _e:
    _INTENT_EMB = {}
def _classify_intent(query):
    """Trả 'recite'/'practice'/'explain' theo độ gần ngữ nghĩa; None nếu lỗi."""
    if not _INTENT_EMB or not query:
        return None
    try:
        qv = bge_m3_model.encode([query], normalize_embeddings=True)[0].tolist()
        sims = {k: max(sum(a*b for a, b in zip(qv, e)) for e in embs) for k, embs in _INTENT_EMB.items()}
        top = max(sims, key=sims.get)
        # cần margin rõ so với explain mới chuyển khỏi explain
        if top in ("recite", "practice") and (sims[top] - sims["explain"]) < 0.035:
            return "explain"
        return top
    except Exception:
        return None

# --- MODELS ---
class RetrieveRequest(BaseModel):
    query: str
    session_id: Optional[str] = "default"
    user_profile: Optional[Dict[str, Any]] = None

@app.post("/v2/rag/retrieve")
async def api_retrieve(req: RetrieveRequest):
    return await retrieve(req)

@app.post("/retrieve")
async def api_retrieve_legacy(req: RetrieveRequest):
    """Backward compatibility with the old RAG system"""
    res = await retrieve(req)
    # Map to the old response format: {"context": "...", "retrieved_sources": N, "intent": "..."}
    return {
        "context": res.context,
        "retrieved_sources": len(res.sources) if res.sources else 1,
        "intent": res.intent
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

class RetrieveResponse(BaseModel):
    context: str
    intent: Dict[str, Any]
    sources: list

# --- CORE FUNCTIONS ---
def normalize_text(value: str) -> str:
    """Normalize Vietnamese text for accent-insensitive lookup."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_recite_title(title):
    """Extract poem/work title from a query-like string."""
    t = title.strip()
    t = re.sub(r"(?i)^(đọc|hay đọc|hãy đọc|đọc cho|kể|ngâm|recite)\s+", "", t, count=1).strip()
    t = re.sub(r"(?i)^(bài thơ|văn bản|bài|tác phẩm|đoạn trích)\s+", "", t, count=1).strip()
    t = re.sub(r"(?i)\s+của\s+(tác giả\s+)?[^,]+$", "", t).strip()
    t = t.strip(" .!?\"'")
    return t if t else title

def lines_payload(title: str, lines: list[dict], intent: dict, source: str) -> RetrieveResponse:
    return RetrieveResponse(
        context=json.dumps(
            {"type": "full_recitation_lines", "title": title, "lines": lines},
            ensure_ascii=False,
        ),
        intent={**intent, "query_type": "recite_full_text", "title": title},
        sources=[source],
    )

def call_gemma(system_prompt: str, user_prompt: str, max_tokens: int = 150, timeout: int = 30) -> str:
    """Gọi LLM (Gemma-4) qua VLLM API"""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.01,
        "max_tokens": max_tokens
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    try:
        response = requests.post(LLM_API_URL, json=payload, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"[LLM Error] HTTP {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[LLM Exception] {e}")
    return ""

# --- BANNED-TOPIC EXPANSION (parental moderation helper) ---
class TopicExpandRequest(BaseModel):
    topic: str
    max_words: int = 5

class TopicExpandResponse(BaseModel):
    topic: str
    description: str
    words: list

def expand_banned_topic(topic: str, max_words: int = 5) -> "TopicExpandResponse":
    """Expand a banned topic into ~max_words Vietnamese words/phrases via Gemma.
    Returns a TopicExpandResponse; on any failure returns empty words (fail-open)."""
    topic = (topic or "").strip()
    if not topic:
        return TopicExpandResponse(topic=topic, description="", words=[])
    system_prompt = (
        "Bạn là bộ lọc an toàn nội dung cho trẻ em (tiếng Việt). "
        "Cho một CHỦ ĐỀ cần cấm, hãy liệt kê các TỪ/CỤM TỪ tiếng Việt thường gặp "
        "thuộc chủ đề đó mà trẻ có thể nói hoặc hỏi. "
        "Chỉ trả về JSON đúng định dạng, KHÔNG giải thích:\n"
        '{"desc":"<mô tả ngắn 1 câu>","words":["...","..."]}\n'
        f"Tối đa {max_words} từ. Mỗi từ ngắn gọn, viết thường, không trùng lặp."
    )
    raw = call_gemma(system_prompt, topic, max_tokens=256)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(raw)
        seen, words = set(), []
        for w in (data.get("words") or []):
            w = (w or "").strip().lower()
            if w and w not in seen:
                seen.add(w)
                words.append(w)
            if len(words) >= max_words:
                break
        return TopicExpandResponse(topic=topic, description=data.get("desc", ""), words=words)
    except Exception as e:
        print(f"[expand_banned_topic] parse fail (fail-open): {e} | raw={raw[:120]!r}")
        return TopicExpandResponse(topic=topic, description="", words=[])

@app.post("/v2/moderation/expand-topic")
async def api_expand_topic(req: TopicExpandRequest) -> TopicExpandResponse:
    """Given a banned TOPIC, ask Gemma for ~N Vietnamese words/phrases to block.
    Stateless: persistence + RBAC are the Dashboard's job. Fail-open → words: []."""
    return expand_banned_topic(req.topic, req.max_words)


def route_query(query: str) -> Dict[str, Any]:
    """Phân tích ý định câu hỏi bằng Gemma-4"""
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

_RECITE_STRONG = re.compile(r"(đọc thuộc|đọc diễn cảm|đọc nguyên văn|đọc cả bài|đọc hết bài|đọc nguyên bài|"
    r"học thuộc|thuộc lòng|ngâm thơ|ngâm bài|đọc to bài|đọc lại bài|"
    r"đọc.{0,15}cho.{0,12}nghe|cho.{0,12}nghe.{0,8}(bài thơ|bài|tác phẩm|truyện)|"
    r"ngâm.{0,12}(bài thơ|thơ|tác phẩm))")
_RECITE_VERB = re.compile(r"\b(đọc|kể|ngâm|thuộc)\b")
_RECITE_NOUN = re.compile(r"(bài thơ|bài|văn bản|tác phẩm|truyện|chuyện|câu chuyện|đoạn thơ|khổ thơ|bài ca dao|bài vè)")
_NOT_RECITE = re.compile(r"(đọc hiểu|đọc kỹ|đọc kĩ|đọc đề|đọc thêm|đọc mở rộng|đọc trước|"
    r"soạn|phân tích|giải thích|giải bài|tóm tắt|cảm nghĩ|cảm nhận|nội dung|ý nghĩa|"
    r"viết|tập đọc|luyện đọc|cách đọc)")

# Mốc tác giả + danh từ chỉ TÁC PHẨM (cố ý KHÔNG gồm 'bài' trơ vì quá phổ biến:
# 'bài tập'...). Dùng để bắt yêu cầu đọc KỂ CẢ KHI STT làm rớt/đổi động từ 'đọc'
# (vd nghe 'đọc' thành 'tôi'/'đục') — miễn là câu vẫn nêu RÕ một tác phẩm.
_AUTHOR_MARK = re.compile(r"\b(nhà thơ|nhà văn|tác giả|thi sĩ)\b")
_RECITE_WORK_NOUN = re.compile(r"(bài thơ|bài ca dao|bài vè|văn bản|tác phẩm|đoạn thơ|khổ thơ|truyện|câu chuyện)")
# Câu HỎI (hỏi-về, không phải yêu-cầu-đọc): "có biết X không", "X là ai/gì", "của ai"...
# Dùng để CHẶN heuristic 'bare work-noun' (dòng dưới) hiểu nhầm câu hỏi thành lệnh đọc.
# KHÔNG áp cho recite có động từ rõ (đọc/ngâm/kể) vì các nhánh đó đã return True phía trên.
# Câu hỏi META về chương trình (ĐẾM / LIỆT KÊ), KHÔNG phải lệnh đọc một bài.
# Phải chặn TRƯỚC _RECITE_VERB+_RECITE_NOUN vì 'kể tên các bài thơ' có cả động từ
# 'kể' lẫn danh từ 'bài thơ' -> nếu không chặn sẽ thành lệnh đọc thơ ngẫu nhiên.
_META_QUERY_RE = re.compile(r"(bao nhiêu|có mấy|mấy bài|kể tên|liệt kê|danh sách|"
    r"gồm những|có những|những bài nào|bài nào|tất cả các bài|toàn bộ các bài)")
_QUESTION_RE = re.compile(r"(có biết|bạn biết|em biết|biết .{0,20}không|"
    r"là ai\b|là gì\b|của ai\b|ai là\b|có phải|"
    r"(nói|kể|viết) về .{0,10}gì|thế nào\b|ra sao\b|như thế nào)")

def _is_recite(q_lower: str) -> bool:
    """Hardened recite detection: exclude reading-comprehension/analysis uses of 'đọc'."""
    if _META_QUERY_RE.search(q_lower):
        return False
    if _NOT_RECITE.search(q_lower):
        return False
    if _RECITE_STRONG.search(q_lower):
        return True
    if _RECITE_VERB.search(q_lower) and _RECITE_NOUN.search(q_lower):
        return True
    # STT-tolerant: động từ 'đọc' hay bị nghe nhầm ('tôi'/'đục') hoặc rớt hẳn. Nếu câu
    # nêu RÕ một tác phẩm (danh từ tác phẩm hoặc mốc tác giả 'nhà thơ...') mà KHÔNG có
    # tín hiệu phân tích/giải thích (_NOT_RECITE đã loại ở trên) → coi là muốn đọc nguyên
    # văn. Khớp sai vô hại: recite_from_* fuzzy theo tên bài, không khớp thì trả None →
    # handler tự rơi về RAG thường (xem 'Fallback to normal retrieval').
    # Câu hỏi "có biết X không / X là ai/gì" → hỏi-về, KHÔNG phải đọc nguyên văn.
    # (Recite có động từ rõ đã return True ở trên; chỉ chặn heuristic bare-work-noun.)
    if _QUESTION_RE.search(q_lower):
        return False
    if _RECITE_WORK_NOUN.search(q_lower) or _AUTHOR_MARK.search(q_lower):
        return True
    return False

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

def _recite_core(title: str) -> str:
    """Trích lõi tên tác phẩm: bỏ '(tác giả)' và tiền tố 'văn bản/bài thơ...'."""
    t = re.sub(r"\([^)]*\)", "", title or "")
    return normalize_text(clean_recite_title(t))


def _best_window_ratio(core: str, wanted: str) -> float:
    """Độ giống lớn nhất giữa core và một cửa sổ token của wanted (và ngược lại)."""
    if not core or not wanted:
        return 0.0
    ct, wt = core.split(), wanted.split()
    if not ct or not wt:
        return 0.0
    needle, hay = (ct, wt) if len(ct) <= len(wt) else (wt, ct)
    ns = " ".join(needle)
    best = difflib.SequenceMatcher(None, core, wanted).ratio()
    n = len(needle)
    for i in range(0, len(hay) - n + 1):
        w = " ".join(hay[i:i + n])
        r = difflib.SequenceMatcher(None, ns, w).ratio()
        if r > best:
            best = r
    return best


# Stopwords/prefix tokens (đã normalize, bỏ dấu) không mang nghĩa tên tác phẩm.
_RECITE_STOPWORDS = {
    "cua", "bai", "tho", "van", "ban", "tac", "gia", "doc", "ngam", "ke",
    "cho", "nghe", "pham", "doan", "trich", "loi", "the", "hay",
}

# Ngưỡng chấp nhận khớp fuzzy. Phải đủ cao để KHÔNG ép khớp bài không có trong data.
_RECITE_SCORE_MIN = 0.8      # điểm tổng hợp (Gemma-JSON đã làm sạch tên -> siết chặt để KHÔNG ép rác)
_RECITE_OVERLAP_MIN = 0.62   # phần token lõi (tên bài) phải trùng đáng kể
_RECITE_TOKEN_FUZZ = 0.75    # 2 token coi như "cùng từ" nếu ratio >= mức này


def _content_tokens(norm: str) -> list[str]:
    """Tách token nội dung (bỏ stopword: 'của','bài','thơ','tác','giả'...)."""
    return [w for w in (norm or "").split() if w not in _RECITE_STOPWORDS]


def _same_word(a: str, b: str) -> bool:
    """2 token coi như cùng từ. Fuzzy CHỈ áp cho token >= 4 ký tự.

    Token ngắn mà fuzzy thì rác: 'nao'~'dao' (câu hỏi 'bài nào' khớp 'hoa đào'),
    'gi'~'gai' ('là gì' khớp 'Con gái của mẹ'). Token ngắn phải khớp CHÍNH XÁC.
    """
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= _RECITE_TOKEN_FUZZ


def _token_overlap(core_toks: list[str], wanted_toks: list[str]) -> float:
    """Tỉ lệ token trùng, CHUẨN HOÁ THEO TẬP DÀI HƠN (coverage đối xứng).

    Trước đây chia theo tập NGẮN → core tí hon (vd 'bo') khớp mọi query dài
    ('tuc nuoc vo bo') ra 1.0 => ép khớp SAI bài. Chia theo tập dài chặn hẳn:
    core phải phủ ĐỦ tên muốn đọc thì mới đạt ngưỡng.
    """
    if not core_toks or not wanted_toks:
        return 0.0
    short, long_ = (core_toks, wanted_toks) if len(core_toks) <= len(wanted_toks) else (wanted_toks, core_toks)
    matched = 0
    for st in short:
        if any(_same_word(st, lt) for lt in long_):
            matched += 1
    return matched / len(long_)


# Ngưỡng phủ token tối thiểu để tầng khớp-chuỗi (score 2/1) được phép chọn bài.
_RECITE_COVERAGE_MIN = 0.34


def _recite_specific_enough(title_norm: str, core_norm: str, wanted: str) -> bool:
    """Câu hỏi có nêu ĐỦ tên bài để được phép đọc nguyên văn?

    Tầng khớp-chuỗi trong recite_from_* (wanted nằm trong title) KHÔNG có hàng rào
    nên một 'tên bài' rỗng nghĩa sẽ ép khớp bừa: wanted='tho' khớp 148/1098 node và
    bầu ra 'Chiều xuân (Anh Thơ)' để đọc cho học sinh (bug 03/09/2026 — câu hỏi
    'lớp 7 có bao nhiêu bài thơ' bị đọc thành một bài thơ ngẫu nhiên).

    Đo trên 3784 tên bài thật (LiteratureText + ReadingText + Lesson.work_name):
    0 tên bài bị từ chối oan; 'tho'/'bai'/'nao'/'gi' bị chặn sạch.
    """
    wt = _content_tokens(wanted)
    if not wt:
        # Tên bài toàn stopword ('Bận', 'Văn hay', 'Lời của cây'->'loi'): chỉ tha khi
        # khớp ĐÚNG NGUYÊN CHUỖI -> câu hỏi chung chung không thể lọt.
        return core_norm == wanted or title_norm == wanted
    for cand in (core_norm, title_norm):
        ct = _content_tokens(cand)
        if not ct:
            if cand == wanted:
                return True
            continue
        if _token_overlap(ct, wt) >= _RECITE_COVERAGE_MIN:
            return True
    return False


def _recite_match_score(core_norm: str, wanted_norm: str) -> tuple[float, float]:
    """Điểm khớp fuzzy giữa tên node (core_norm) và tên muốn đọc (wanted_norm).

    Kết hợp:
      - window-ratio (difflib trên chuỗi đã bỏ dấu) → chịu được nhầm phụ âm
        đơn (dừng↔rừng) và cắt cụt;
      - token-overlap trên token lõi (đã bỏ stopword/tên tác giả) → chặn
        false-positive khi từ lõi khác hẳn nhau.
    Trả về (combined_score, core_token_overlap).
    """
    win = _best_window_ratio(core_norm, wanted_norm)
    overlap = _token_overlap(_content_tokens(core_norm), _content_tokens(wanted_norm))
    combined = 0.5 * win + 0.5 * overlap
    return combined, overlap


def best_recite_match(wanted: str, candidates: list[dict], title_key: str = "title"):
    """Chọn node khớp fuzzy nhất với tên muốn đọc; None nếu không đủ tin cậy.

    `wanted` đã được normalize_text + clean_recite_title trước khi gọi.
    Trả về dict row tốt nhất (kèm log), hoặc None để TRÁNH ép khớp bài
    không có thật trong dữ liệu (LLM sẽ không bịa bài giả).
    """
    if not wanted:
        return None
    best_row = None
    best_combined = 0.0
    best_overlap = 0.0
    best_core = ""
    for row in candidates:
        core = _recite_core(row.get(title_key, ""))
        if not core:
            continue
        combined, overlap = _recite_match_score(core, wanted)
        # ưu tiên điểm cao; hoà thì chọn core ngắn hơn (sát tên bài hơn)
        if combined > best_combined or (combined == best_combined and best_row is not None and len(core) < len(best_core)):
            best_combined, best_overlap, best_core, best_row = combined, overlap, core, row
    if best_row is not None and best_combined >= _RECITE_SCORE_MIN and best_overlap >= _RECITE_OVERLAP_MIN:
        print(f"[Recite Fuzzy] '{wanted}' ~ '{best_core}' "
              f"combined={best_combined:.2f} overlap={best_overlap:.2f}")
        return best_row
    return None


def _literature_payload(row: Optional[dict], intent: dict) -> Optional[RetrieveResponse]:
    """Dựng payload đọc-nguyên-văn từ 1 node LiteratureText (None nếu không có full_text)."""
    if not row or not row.get("full_text"):
        return None
    lines = [
        {"text": line.strip(), "pause_ms": 700}
        for line in row["full_text"].splitlines()
        if line.strip()
    ]
    if not lines:
        return None
    return lines_payload(row["title"], lines, intent, "neo4j_literature_text")


def recite_from_literature_text(title: str, intent: dict, grade=None, bo_sach=None, strict_grade=False,
                                author=None, require_homonym_default=False) -> Optional[RetrieveResponse]:
    """author: tên tác giả học sinh nêu -> CHỈ nhận bản của đúng tác giả đó (None nếu
    không có bản nào -> nhường cho các nhánh sau). Cần cho tác phẩm TRÙNG TÊN, vd
    'Mẹ' có bản Đỗ Trung Lai (Ngữ văn 7) và bản Trần Quốc Minh (lớp 2).

    require_homonym_default: chỉ trả kết quả khi tên bài TRÙNG (>=2 bản) và graph đã
    đánh dấu đúng 1 bản recite_default=TRUE -> tôn trọng đánh dấu của người ingest.
    """
    clean_title = clean_recite_title(title)
    wanted = normalize_text(clean_title)
    if not wanted:
        wanted = normalize_text(title)
    if not wanted:
        return None

    cypher = """
    MATCH (lt:LiteratureText)
    WHERE ($grade IS NULL OR lt.grade = $grade OR toString(lt.grade) = toString($grade))
      AND ($bo_sach IS NULL OR lt.series IS NULL OR lt.series = $bo_sach)
      AND NOT (toLower(lt.title) CONTAINS 'đọc hiểu' OR toLower(lt.title) CONTAINS 'trắc nghiệm' OR toLower(lt.title) CONTAINS 'luyện đề' OR toLower(lt.title) CONTAINS 'phân tích' OR toLower(lt.title) CONTAINS 'soạn bài' OR toLower(lt.title) CONTAINS 'sơ đồ tư duy' OR toLower(lt.title) CONTAINS 'dàn ý')
    RETURN lt.title AS title, lt.full_text AS full_text, lt.grade AS grade,
           lt.series AS series, lt.author AS author, lt.url AS url,
           coalesce(lt.recite_default,false) AS recite_default, lt.recite_dup_of AS recite_dup_of
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        with driver.session() as session:
            candidates = [dict(r) for r in session.run(cypher, grade=None, bo_sach=None)]   # SOFT: lấy MỌI bản; grade/bo chỉ để rank
            if not candidates:
                # Văn bản canonical (grade='canon', series='poetry_canon') không gắn lớp/bộ -> bỏ filter thử lại
                candidates = [dict(r) for r in session.run(cypher, grade=None, bo_sach=None)]
    except Exception as e:
        print(f"[Neo4j LiteratureText Recitation Error] {e}")
        return None
    finally:
        driver.close()

    if author:
        _a = _fold(author)
        _by_author = [c for c in candidates
                      if _a in _fold(c.get("title") or "")
                      or _a in _fold(c.get("author") or "")
                      or _a in _fold((c.get("full_text") or "")[:200])]
        if not _by_author:
            return None                    # nêu tác giả mà KB không có bản nào -> nhường nhánh khác
        candidates = _by_author

    if strict_grade and grade is not None:
        candidates = [c for c in candidates if str(c.get("grade")) == str(grade)]
        if not candidates:
            return None                    # khong co ban GRADE-EXACT -> nhuong lesson_card/soft
    scored = []
    for row in candidates:
        normalized_title = normalize_text(row.get("title", ""))
        normalized_url = normalize_text(row.get("url", ""))
        score = 0
        if wanted == normalized_title:
            score = 3
        elif not _recite_specific_enough(normalized_title, _recite_core(row.get("title", "")), wanted):
            score = 0          # câu hỏi không nêu đủ tên bài -> KHÔNG ép khớp (xem _recite_specific_enough)
        elif re.search(r"(?:^|\s)" + re.escape(wanted) + r"(?:\s|$)", normalized_title):
            score = 2
        elif wanted in normalized_title or normalized_title in wanted or wanted in normalized_url:
            score = 1
        if score > 0:
            _gm = 1 if (grade is not None and str(row.get("grade")) == str(grade)) else 0
            _bm = 1 if (bo_sach and row.get("series") == bo_sach) else 0
            _isdef = 1 if row.get("recite_default") else 0
            _isdup = 1 if row.get("recite_dup_of") else 0
            scored.append((score, _gm, _bm, _isdef, _isdup, len(normalized_title), row))
    scored.sort(key=lambda x: (-x[0], -x[1], -x[2], -x[3], x[4], x[5]))  # score>grade>bo>default>khong-dup>title

    if require_homonym_default:
        # Chỉ can thiệp khi THẬT trùng tên: >=2 tác phẩm khác nhau khớp mạnh (score>=2)
        # và graph đánh dấu đúng 1 bản recite_default -> trả bản đó. Ngoài ra nhường
        # nguyên luồng cũ (return None) để không đổi hành vi các bài không trùng tên.
        strong = [s for s in scored if s[0] >= 2]
        works = {_recite_core(s[6].get("title", "")) for s in strong}
        defaults = [s for s in strong if s[3] == 1]
        if len(works) < 2 or len(defaults) != 1:
            return None
        print(f"[Recite Homonym] {title!r} trùng {len(works)} bản -> chọn recite_default "
              f"{defaults[0][6].get('title')!r}")
        return _literature_payload(defaults[0][6], intent)

    best = scored[0][6] if scored else None

    # Fuzzy fallback: STT nghe sai tên bài (rừng->dừng/rương/giường...),
    # cắt cụt tên tác giả, hoặc sai tên tác giả. Có gate token-overlap để
    # KHÔNG ép khớp bài không có trong dữ liệu.
    if best is None:
        best = best_recite_match(wanted, candidates, title_key="title")

    return _literature_payload(best, intent)

def recite_from_reading_text(title: str, grade=None, bo_sach=None) -> Optional[RetrieveResponse]:
    clean_title = clean_recite_title(title)
    wanted = normalize_text(clean_title) or normalize_text(title)
    if not wanted:
        return None
    cypher = """
    MATCH (rt:ReadingText)
    WHERE ($grade IS NULL OR rt.grade = $grade OR toString(rt.grade) = toString($grade))
      AND ($bo_sach IS NULL OR rt.bo_sach IS NULL OR rt.bo_sach = $bo_sach)
      AND NOT (toLower(rt.title) CONTAINS 'đọc hiểu' OR toLower(rt.title) CONTAINS 'trắc nghiệm' OR toLower(rt.title) CONTAINS 'luyện đề' OR toLower(rt.title) CONTAINS 'phân tích' OR toLower(rt.title) CONTAINS 'soạn bài' OR toLower(rt.title) CONTAINS 'sơ đồ tư duy' OR toLower(rt.title) CONTAINS 'dàn ý')
    OPTIONAL MATCH (rt)-[:HAS_SEGMENT]->(seg:RecitationSegment)
    RETURN rt.title AS title, rt.original_text AS original_text,
           collect({idx: seg.segment_index, text: seg.text, pause: seg.pause_after_ms}) AS segments
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        with driver.session() as session:
            records = [dict(r) for r in session.run(cypher, grade=grade, bo_sach=bo_sach)]
            record = next(
                (
                    r for r in records
                    if (wanted in normalize_text(r.get("title", "")) or normalize_text(r.get("title", "")) in wanted)
                    and _recite_specific_enough(normalize_text(r.get("title", "")),
                                                _recite_core(r.get("title", "")), wanted)
                ),
                None,
            )
            # Fuzzy fallback: STT nghe sai tên / cắt cụt / sai tác giả.
            if not record:
                record = best_recite_match(wanted, records, title_key="title")
            if not record:
                return None

            segments = [s for s in record["segments"] if s.get("text")]
            if segments:
                segments.sort(key=lambda s: s.get("idx") if s.get("idx") is not None else 0)
                lines = [{"text": s["text"], "pause_ms": s.get("pause") or 600} for s in segments]
            else:
                text = record["original_text"] or ""
                lines = [{"text": line.strip(), "pause_ms": 600} for line in text.splitlines() if line.strip()]

            if not lines:
                return None

            return lines_payload(record["title"], lines, {"source": "ReadingText"}, "neo4j_reading_text")
    except Exception as e:
        print(f"[Neo4j ReadingText Recitation Error] {e}")
        return None
    finally:
        driver.close()

def recite_from_full_document(title: str, intent: dict, grade=None, bo_sach=None) -> Optional[RetrieveResponse]:
    """Fallback for canonical reading_original FullDocument. Avoid soan_bai_full for recitation."""
    clean_title = clean_recite_title(title)
    wanted = normalize_text(clean_title) or normalize_text(title)
    if not wanted:
        return None
    cypher = """
    MATCH (fd:FullDocument)
    WHERE fd.document_type = 'reading_original'
      AND ($grade IS NULL OR fd.grade = $grade OR toString(fd.grade) = toString($grade))
      AND ($bo_sach IS NULL OR fd.bo_sach IS NULL OR fd.bo_sach = $bo_sach)
      AND NOT (toLower(fd.title) CONTAINS 'đọc hiểu' OR toLower(fd.title) CONTAINS 'trắc nghiệm' OR toLower(fd.title) CONTAINS 'luyện đề' OR toLower(fd.title) CONTAINS 'phân tích' OR toLower(fd.title) CONTAINS 'soạn bài' OR toLower(fd.title) CONTAINS 'sơ đồ tư duy' OR toLower(fd.title) CONTAINS 'dàn ý')
    OPTIONAL MATCH (fd)-[:HAS_SECTION]->(s:Section)-[:HAS_BLOCK]->(b:ContentBlock)
    RETURN fd.title AS title, fd.full_text AS full_text,
           collect({sidx: s.section_index, bidx: b.block_index, text: b.text}) AS blocks
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        with driver.session() as session:
            records = [dict(r) for r in session.run(cypher, grade=grade, bo_sach=bo_sach)]
    except Exception as e:
        print(f"[Neo4j FullDocument Recitation Error] {e}")
        return None
    finally:
        driver.close()

    record = next(
        (
            r for r in records
            if (wanted in normalize_text(r.get("title", "")) or normalize_text(r.get("title", "")) in wanted)
            and _recite_specific_enough(normalize_text(r.get("title", "")),
                                        _recite_core(r.get("title", "")), wanted)
        ),
        None,
    )
    # Fuzzy fallback: STT nghe sai tên / cắt cụt / sai tác giả.
    if not record:
        record = best_recite_match(wanted, records, title_key="title")
    if not record:
        return None

    blocks = [b for b in record["blocks"] if b.get("text")]
    if blocks:
        blocks.sort(key=lambda b: (
            b.get("sidx") if b.get("sidx") is not None else 0,
            b.get("bidx") if b.get("bidx") is not None else 0,
        ))
        lines = [{"text": b["text"], "pause_ms": 600} for b in blocks]
    else:
        lines = [{"text": line.strip(), "pause_ms": 600} for line in (record.get("full_text") or "").splitlines() if line.strip()]
    if not lines:
        return None
    return lines_payload(record["title"], lines, intent, "neo4j_full_document")

SUBJECT_ALIASES = {
    "toan": ["toán", "toan", "hình học", "đại số", "phương trình", "bất phương trình", "phân số"],
    "ngu_van": ["ngữ văn", "ngu van", "văn", "soạn bài", "phân tích nhân vật", "bài thơ"],
    "khtn": ["khtn", "khoa học tự nhiên", "nguyên tử", "phân tử", "vật lý", "lý", "hóa học", "hóa", "sinh học", "sinh"],
    "lich_su": ["lịch sử", "lich su", "sử", "khởi nghĩa", "hai bà trưng"],
    "dia_ly": ["địa lý", "địa lí", "dia ly", "bản đồ", "khí hậu", "dân cư"],
    "tieng_anh": ["tiếng anh", "tieng anh", "english", "grammar", "vocabulary"],
}

SUBJECT_TO_QDRANT = {
    "toan": "kb_math_exercises",
    "khtn": "kb_khtn_exercises",
    "lich_su": "kb_social_exercises",
    "dia_ly": "kb_social_exercises"
}

def canonicalize_subject(raw_subject: str | None, query: str = "") -> str | None:
    text = f"{raw_subject or ''} {query or ''}".lower()
    
    for code, keys in SUBJECT_ALIASES.items():
        if any(k in text for k in keys):
            return code
            
    # Default fallback if direct match fails but original subject is set
    s = (raw_subject or "").lower().strip()
    return s if s else None

MATH_FORCE_KEYWORDS = [
    "tập hợp", "lũy thừa", "số tự nhiên", "số nguyên tố",
    "số nguyên", "số nguyên âm", "hợp số", "ước chung", "bội chung", "chia hết",
    "dấu hiệu chia hết", "phân số", "tử số", "mẫu số",
    "góc", "đường thẳng", "đoạn thẳng", "tia",
    "tam giác", "hình vuông", "hình chữ nhật",
    "phương trình", "tìm x", "biểu thức",
    "quy tắc dấu ngoặc", "thứ tự thực hiện phép tính",
    "tỉ lệ thuận", "tỉ lệ nghịch", "đại lượng tỉ lệ", "tỉ lệ thức", "dãy tỉ số"
]

KHTN_FORCE_KEYWORDS = [
    "nguyên tử", "phân tử", "tế bào", "cơ thể sống",
    "vật sống", "chất", "hỗn hợp", "oxygen", "không khí",
    "nhiệt độ", "lực", "năng lượng", "âm thanh",
    "ánh sáng", "thực vật", "động vật", "vi khuẩn"
]

LICHSU_FORCE_KEYWORDS = [
    "lịch sử", "khởi nghĩa", "triều đại", "văn minh",
    "nhà nước", "thời nguyên thủy", "cổ đại",
    "ai cập", "lưỡng hà", "hy lạp", "la mã",
    "đông nam á", "việt nam thời cổ đại",
    "trước công nguyên", "sau công nguyên",
    "phong kiến", "đế quốc", "thuộc địa",
]

VANHOC_FORCE_KEYWORDS = [
    "cảm nghĩ", "cảm hứng", "cảm nhận", "tác phẩm", "bài thơ", "nhân vật",
    "tâm trạng", "giá trị nội dung", "nghệ thuật", "tóm tắt truyện", "phân tích nhân vật",
    "biện pháp tu từ", "ý nghĩa nhan đề",
]

def override_subject_by_keywords(query: str, subject: str | None) -> str | None:
    q = query.lower()

    if any(k in q for k in MATH_FORCE_KEYWORDS):
        return "toan"

    if any(k in q for k in KHTN_FORCE_KEYWORDS):
        return "khtn"

    if any(k in q for k in LICHSU_FORCE_KEYWORDS):
        return "lich_su"

    # NEW: literary-analysis keywords -> ngu_van (only if subject not already determined)
    if subject is None and any(k in q for k in VANHOC_FORCE_KEYWORDS):
        return "ngu_van"

    return subject

def detect_learning_mode(query: str) -> str:
    q = query.lower()
    tutor_keys = ["em chưa hiểu", "giải thích", "hướng dẫn", "gợi ý", "làm sao", "vì sao", "tại sao"]
    review_keys = ["ôn tập", "tóm tắt", "kiến thức trọng tâm", "lý thuyết", "chuẩn bị kiểm tra"]
    solution_keys = ["giải bài", "lời giải", "đáp án", "bài tập", "tính", "chứng minh"]

    if any(k in q for k in review_keys):
        return "review"
    if any(k in q for k in tutor_keys):
        return "tutor"
    if any(k in q for k in solution_keys):
        return "solution"

    return "tutor"  # Default cho học sinh

CONTEXT_LIMITS = {
    "tutor": 6000,
    "solution": 9000,
    "review": 7000,
    "recite_full_text": 20000,
    "explain": 8000,
}

def trim_context(context: str, mode: str) -> str:
    limit = CONTEXT_LIMITS.get(mode, 8000)
    if len(context) <= limit:
        return context
    return context[:limit] + "\n\n[Context truncated for relevance]"

def query_qdrant(intent: Dict[str, Any]) -> str:
    """Truy vấn Qdrant cho các môn Toán, KHTN, Sử, Địa..."""
    keyword = intent.get("keyword", "")
    subject = canonicalize_subject(intent.get("subject"), intent.get("search_query", keyword))
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")

    if not keyword:
        return ""

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        try:
            client = QdrantClient(host="localhost", port=6333, timeout=3)
            client.get_collections()
        except:
            client = QdrantClient(host=os.getenv("QDRANT_HOST_FALLBACK", "localhost"), port=6333, timeout=5)

        query_vector = bge_m3_model.encode([keyword], normalize_embeddings=True)[0].tolist()

        must_conditions = []
        if grade:
            must_conditions.append(FieldCondition(key="lop", match=MatchValue(value=int(grade))))
        if bo_sach:
            must_conditions.append(FieldCondition(key="bo_sach", match=MatchValue(value=bo_sach)))

        query_filter = Filter(must=must_conditions) if must_conditions else None

        all_results = []
        target_collections = [SUBJECT_TO_QDRANT.get(subject)] if SUBJECT_TO_QDRANT.get(subject) else ["kb_math_exercises", "kb_khtn_exercises", "kb_social_exercises"]
        target_collections = [c for c in target_collections if c]
        
        for coll in target_collections:
            try:
                if hasattr(client, 'query_points'):
                    res = client.query_points(
                        collection_name=coll,
                        query=query_vector,
                        query_filter=query_filter,
                        limit=3
                    ).points
                else:
                    res = client.search(
                        collection_name=coll,
                        query_vector=query_vector,
                        query_filter=query_filter,
                        limit=3
                    )
                for r in res:
                    r.payload["_collection_name"] = coll
                all_results.extend(res)
            except Exception as e:
                print(f"[Qdrant Search Error in {coll}] {e}")
                
        all_results.sort(key=lambda x: x.score, reverse=True)
        results = all_results[:4]

        import psycopg2
        pg_conn = None
        try:
            pg_conn = psycopg2.connect(host="localhost", port=5433, dbname="rag_edu", user=os.getenv("PG_USER", "postgres"), password=os.environ.get("PG_PASS", ""), connect_timeout=3)
        except:
            try:
                pg_conn = psycopg2.connect(host=os.getenv("PG_HOST_FALLBACK", "localhost"), port=5433, dbname="rag_edu", user=os.getenv("PG_USER", "postgres"), password=os.environ.get("PG_PASS", ""), connect_timeout=3)
            except Exception as e:
                print(f"[PG Connect Error] {e}")

        contexts = []
        for r in results:
            payload = r.payload or {}
            lop = payload.get("lop", "N/A")
            sach = payload.get("bo_sach", "N/A")
            meta = f"Lớp {lop} | Bộ sách: {sach}"
            
            content_text = ""
            coll_name = payload.get("_collection_name", "")
            title = payload.get("title", payload.get("ten_bai", f"Bài tập ({coll_name})"))
            
            kb_id = payload.get("kb_id")
            if kb_id and pg_conn:
                try:
                    with pg_conn.cursor() as cur:
                        table_name = coll_name
                        cur.execute(f"SELECT * FROM {table_name} WHERE id = %s", (kb_id,))
                        row = cur.fetchone()
                        if row:
                            colnames = [desc[0] for desc in cur.description]
                            row_dict = dict(zip(colnames, row))
                            
                            if "ten_khai_niem" in row_dict and row_dict["ten_khai_niem"]:
                                title = row_dict["ten_khai_niem"]
                            elif "bai_so" in row_dict and row_dict["bai_so"]:
                                title = f"Bài {row_dict['bai_so']} (Trang {row_dict.get('trang', '?')})"
                                
                            if "de_bai" in row_dict and "loi_giai" in row_dict:
                                content_text = f"Đề bài: {row_dict['de_bai']}\nLời giải: {row_dict['loi_giai']}"
                            elif "dinh_nghia" in row_dict:
                                content_text = f"Định nghĩa: {row_dict['dinh_nghia']}\nCông thức: {row_dict.get('cong_thuc_text', '')}"
                            else:
                                texts = [str(v) for k, v in row_dict.items() if isinstance(v, str) and len(v) > 20]
                                content_text = "\n".join(texts)
                except Exception as e:
                    print(f"[PG Query Error] {e}")
                    pg_conn.rollback()

            if not content_text:
                # Fallback to payload text if postgres fails
                content_text = payload.get("content", payload.get("text", ""))

            contexts.append(f"📚 {title} ({meta})\n{content_text}")

        if pg_conn:
            pg_conn.close()

        return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Qdrant Error] {e}")
        return ""

def query_neo4j_vector(intent: Dict[str, Any]) -> str:
    """Truy vấn Hybrid (Vector + Structural) qua Neo4j Native Vector"""
    keyword = intent.get("keyword", "")
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")
    
    if not keyword:
        return ""
        
    try:
        query_vector = bge_m3_model.encode([keyword], normalize_embeddings=True)[0].tolist()
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        
        # Return focused sections, not the entire FullDocument, to keep LLM context tight.
        cypher_query = """
        CALL db.index.vector.queryNodes('section_embedding', 15, $query_vector)
        YIELD node AS sec, score
        WHERE ($grade IS NULL OR sec.grade = $grade)
          AND ($bo_sach IS NULL OR sec.bo_sach = $bo_sach)
        WITH sec, score
        MATCH (fd:FullDocument)-[:HAS_SECTION]->(sec)
        RETURN fd.title AS lesson_title, fd.grade AS grade, fd.bo_sach AS bo_sach,
               sec.title AS section_title, sec.text AS section_text, score
        ORDER BY score DESC
        LIMIT 5
        """
        
        params = {
            "query_vector": query_vector,
            "grade": grade,
            "bo_sach": bo_sach
        }
        
        with driver.session() as session:
            results = session.run(cypher_query, **params)
            contexts = []
            for r in results:
                meta = f"Lớp {r['grade']} | Bộ sách: {r['bo_sach']}"
                contexts.append(
                    f"📚 {r['lesson_title']} ({meta})\n"
                    f"Mục: {r['section_title']}\n{r['section_text']}"
                )
                
            return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Neo4j Vector Error] {e}")
        return ""

def query_neo4j_knowledge_chunk(intent: Dict[str, Any]) -> str:
    """Truy vấn Neo4j KnowledgeChunk (Production & Staging sạch)"""
    keyword = intent.get("keyword", "")
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")
    subject = intent.get("subject")
    
    if not keyword:
        return ""
        
    ALLOW_STAGING = False
        
    try:
        query_vector = bge_m3_model.encode([keyword], normalize_embeddings=True)[0].tolist()
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        
        cypher_query = """
        CALL db.index.vector.queryNodes('knowledge_chunk_embedding', 5, $query_vector)
        YIELD node AS k, score
        WHERE (k:KnowledgeChunk)
          AND ($grade IS NULL OR k.grade = $grade OR toString(k.grade) = toString($grade))
          AND ($bo_sach IS NULL OR k.bo_sach = $bo_sach)
          AND ($subject IS NULL OR k.subject_code = $subject)
          AND (
            coalesce(k.production_ready, false) = true
            OR ($allow_staging = true AND k:StagingClean)
          )
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, score
        ORDER BY score DESC
        """
        
        params = {
            "query_vector": query_vector,
            "grade": grade,
            "bo_sach": bo_sach,
            "subject": subject,
            "allow_staging": ALLOW_STAGING
        }
        
        with driver.session() as session:
            results = session.run(cypher_query, **params)
            contexts = []
            for r in results:
                meta = f"Lớp {r['grade']} | Bộ sách: {r['bo_sach']}"
                contexts.append(
                    f"📚 {r['title']} ({meta})\n{r['text']}"
                )
                
            return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Neo4j KnowledgeChunk Vector Error] {e}")
        return ""


# ── Phase 1: LessonGuide whole-doc retrieval ───────────────────────
# Activates 11K LessonGuide content via lesson_guide_embedding index.
# NOTE: LessonGuide.subject is currently NULL for all nodes (Phase 1.5 will backfill).
# So we rely on vector similarity + optional grade/bo_sach filter only.
def query_neo4j_lesson_guide(intent: Dict[str, Any]) -> str:
    """Truy vấn whole-document LessonGuide via lesson_guide_embedding (1024d cosine)."""
    keyword = intent.get("keyword", "")
    grade = intent.get("grade")
    bo_sach = intent.get("bo_sach")

    if not keyword:
        return ""

    try:
        query_vector = bge_m3_model.encode([keyword], normalize_embeddings=True)[0].tolist()
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

        # Top-3 whole-doc matches with optional grade/bo_sach filter
        cypher_query = """
        CALL db.index.vector.queryNodes('lesson_guide_embedding', 5, $query_vector)
        YIELD node AS lg, score
        WHERE (lg:LessonGuide)
          AND lg.embedding IS NOT NULL
          AND ($grade IS NULL OR lg.grade = $grade OR toString(lg.grade) = toString($grade))
          AND ($bo_sach IS NULL OR lg.bo_sach = $bo_sach)
        RETURN lg.title AS title, lg.grade AS grade, lg.bo_sach AS bo_sach,
               lg.content AS content, lg.url AS url, score
        ORDER BY score DESC
        LIMIT 3
        """

        params = {
            "query_vector": query_vector,
            "grade": grade,
            "bo_sach": bo_sach,
        }

        with driver.session() as session:
            results = session.run(cypher_query, **params)
            contexts = []
            for r in results:
                meta_parts = []
                if r["grade"]:
                    meta_parts.append(f"Lớp {r['grade']}")
                if r["bo_sach"] and r["bo_sach"] != "LEGACY":
                    meta_parts.append(f"Bộ sách: {r['bo_sach']}")
                meta = " | ".join(meta_parts) if meta_parts else "Hướng dẫn học"
                # Truncate content per match — let trim_context handle final size
                content = (r["content"] or "")[:4000]
                contexts.append(
                    f"📖 {r['title']} ({meta})\n{content}"
                )

            return "\n\n".join(contexts)
    except Exception as e:
        print(f"[Neo4j LessonGuide Vector Error] {e}")
        return ""


# ── Tier A: Structured-first parsing & exact lookup ────────────────
# Use case: PTalk voice tutor, query có signal mạnh (lop, bo_sach từ device + bài_no, trang từ query)

_SUBJECT_KW = {
    "ngu_van": ["ngữ văn", "soạn văn", "soạn bài", "văn lớp"],
    "khtn": ["khoa học tự nhiên", "khtn"],
    "toan": ["toán", "đại số", "hình học"],
    "tieng_viet": ["tiếng việt"],
    "lich_su": ["lịch sử"],
    "dia_li": ["địa lí", "địa lý"],
    "lich_su_dia_li": ["lịch sử và địa lí", "lịch sử và địa lý"],
    "gdcd": ["giáo dục công dân", "gdcd", "công dân"],
    "tieng_anh": ["tiếng anh", "english"],
    "vat_li": ["vật lí", "vật lý"],
    "hoa_hoc": ["hóa học", "hóa lớp"],
    "sinh_hoc": ["sinh học"],
}

def parse_structured_query(query: str, user_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Extract structured signals từ query + user_profile."""
    user_profile = user_profile or {}
    q_lower = query.lower()

    # User profile (device-known)
    parsed = {
        "lop": user_profile.get("lop") or user_profile.get("grade"),
        "bo_sach": user_profile.get("bo_sach") or user_profile.get("bo_sach_chinh"),
        "subject": user_profile.get("subject") or user_profile.get("mon"),
    }

    # Bài_no from query
    m_bai = re.search(r"\bb[àa]i\s*(\d+)", q_lower)
    parsed["bai_no"] = int(m_bai.group(1)) if m_bai else None

    # Trang from query
    m_trang = re.search(r"\btrang\s*(\d+)", q_lower)
    parsed["trang"] = int(m_trang.group(1)) if m_trang else None
    if parsed["trang"] is None and user_profile and user_profile.get("trang") is not None:
        try: parsed["trang"] = int(user_profile.get("trang"))
        except Exception: pass

    # Câu_no (sometimes used in SBT context)
    m_cau = re.search(r"\bc[âa]u\s*(\d+)", q_lower)
    parsed["cau_no"] = int(m_cau.group(1)) if m_cau else None

    # Subject from query keyword (override profile if found)
    for code, kws in _SUBJECT_KW.items():
        for kw in kws:
            if kw in q_lower:
                parsed["subject"] = code
                break
        if parsed.get("subject"):
            break

    # Grade from query if explicit (override profile)
    m_lop = re.search(r"\bl[ớo]p\s*(\d+)", q_lower)
    if m_lop:
        parsed["lop"] = int(m_lop.group(1))

    # Series detection from query
    if "kntt" in q_lower or "kết nối tri thức" in q_lower:
        parsed["bo_sach"] = "KNTT"
    elif "ctst" in q_lower or "chân trời sáng tạo" in q_lower:
        parsed["bo_sach"] = "CTST"
    elif "cánh diều" in q_lower or " cd " in q_lower or q_lower.endswith(" cd"):
        parsed["bo_sach"] = "CD"

    # I3 — Scan full BOOK_ALIASES map (handles "ket noi", "chan troi",
    # "canh dieu", "k.n.t.t", etc.). Explicit query token overrides profile.
    q_folded = _fold(query)
    for alias, canon in BOOK_ALIASES.items():
        alias_folded = _fold(alias)
        # Match either raw (with diacritics) or folded form
        if alias in q_lower or (alias_folded and alias_folded in q_folded):
            parsed["bo_sach"] = canon
            break

    return parsed


def query_concept_exact(parsed: Dict[str, Any], query: str) -> str:
    """Tier A-concept: topic-only query (no bai/trang) -> exact lookup by Concept name within grade+book."""
    grade = parsed.get("lop")
    bo_sach = parsed.get("bo_sach")
    subject = parsed.get("subject")
    if not (grade and bo_sach):
        return ""
    q_folded = _fold(query)
    cypher = """
        MATCH (k:KnowledgeChunk)-[:COVERS]->(c:Concept)
        WHERE coalesce(k.production_ready,false) = true
          AND (k.grade = $grade OR toString(k.grade) = toString($grade))
          AND k.bo_sach = $bo_sach
          AND ($subject IS NULL OR k.subject_code = $subject)
          AND c.name_norm IS NOT NULL AND size(c.name_norm) >= 3
        WITH k, c, $q_folded AS q
        WITH k, c, q, [w IN split(c.name_norm,' ') WHERE size(w) >= 4] AS cw
        WITH k, c, q, cw, [w IN cw WHERE q CONTAINS w] AS hits
        WHERE q CONTAINS c.name_norm
           OR (size(cw) >= 2 AND size(hits) >= 2)
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, k.subject_code AS subj, c.name AS concept,
               size(c.name_norm) AS clen,
               (CASE WHEN q CONTAINS c.name_norm THEN 1000 ELSE size(hits) END) AS mscore
        ORDER BY
            mscore DESC,
            CASE WHEN k.content_class = 'vietjack_lesson' THEN 0 ELSE 1 END,
            clen DESC, size(k.text) DESC
        LIMIT 3
    """
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session() as s:
            results = s.run(cypher, grade=grade, bo_sach=bo_sach,
                            subject=subject, q_folded=q_folded).data()
        driver.close()
    except Exception as e:
        print(f"[Concept Exact Error] {e}")
        return ""
    if not results:
        return ""
    contexts = []
    for r in results:
        meta = f"L\u1edbp {r['grade']} | {r['bo_sach']} | {r['subj']}"
        contexts.append(f"\U0001f4d0 {r['title']} ({meta}) [concept: {r['concept']}]\n{(r['text'] or '')[:4000]}")
    return "\n\n".join(contexts)


def query_structured_exact(parsed: Dict[str, Any]) -> str:
    """Tier A: exact Cypher lookup if structured ref present."""
    if not (parsed.get("bai_no") or parsed.get("trang")):
        return ""

    conds = ["k:KnowledgeChunk", "k.production_ready = true"]
    params = {}

    if parsed.get("lop"):
        conds.append("k.grade = $grade")
        params["grade"] = parsed["lop"]
    if parsed.get("bo_sach") and parsed["bo_sach"] != "LEGACY":
        conds.append("k.bo_sach = $bo_sach")
        params["bo_sach"] = parsed["bo_sach"]
    if parsed.get("subject"):
        conds.append("k.subject_code = $subject")
        params["subject"] = parsed["subject"]

    # Bai_no match — strict (KHÔNG match "bài 14" cho query "bài 1")
    # Sử dụng CONTAINS với 4 delimiters: "Bài N:", "Bài N ", "Bài N.", "Bài N,"
    # I4 — also match diacritic-folded variants of the title (e.g. "bai 1:")
    if parsed.get("bai_no"):
        n = parsed["bai_no"]
        conds.append(
            "(k.lesson_no = $bai_no OR "
            "toLower(k.title) CONTAINS $bai_colon OR "
            "toLower(k.title) CONTAINS $bai_space OR "
            "toLower(k.title) CONTAINS $bai_dot OR "
            "toLower(k.title) ENDS WITH $bai_end OR "
            "toLower(k.title) CONTAINS $bai_colon_folded OR "
            "toLower(k.title) CONTAINS $bai_space_folded OR "
            "toLower(k.title) CONTAINS $bai_dot_folded OR "
            "toLower(k.title) ENDS WITH $bai_end_folded)"
        )
        params["bai_no"] = n
        params["bai_colon"] = f"bài {n}:"
        params["bai_space"] = f"bài {n} "
        params["bai_dot"] = f"bài {n}."
        params["bai_end"] = f"bài {n}"
        # Folded (no diacritic) variants
        params["bai_colon_folded"] = _fold(f"bài {n}:")
        params["bai_space_folded"] = _fold(f"bài {n} ")
        params["bai_dot_folded"] = _fold(f"bài {n}.")
        params["bai_end_folded"] = _fold(f"bài {n}")

    # Trang match — title contains "trang N" (raw or folded)
    if parsed.get("trang"):
        trang_text = f"trang {parsed['trang']}"
        conds.append(
            "(toLower(k.title) CONTAINS $trang_text OR "
            "toLower(k.title) CONTAINS $trang_text_folded)"
        )
        params["trang_text"] = trang_text
        params["trang_text_folded"] = _fold(trang_text)

    # I1 — Prefer vietjack source + earliest chunk_index for stable Tier A ordering.
    cypher = f"""
        MATCH (k)
        WHERE {' AND '.join(conds)}
        RETURN k.title AS title, k.grade AS grade, k.bo_sach AS bo_sach,
               k.text AS text, k.lesson_no AS lesson_no, k.subject_code AS subj
        ORDER BY
            CASE WHEN k.lesson_no = $bai_no_strict THEN 0 ELSE 1 END,
            CASE WHEN coalesce(k.source,'') CONTAINS 'vietjack' THEN 0 ELSE 1 END,
            coalesce(k.chunk_index, 999) ASC,
            size(k.text) DESC
        LIMIT 3
    """
    params["bai_no_strict"] = parsed.get("bai_no")

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session() as s:
            results = s.run(cypher, **params).data()
        driver.close()
    except Exception as e:
        print(f"[Tier A Cypher Error] {e}")
        return ""

    if not results:
        return ""

    contexts = []
    for r in results:
        meta = f"Lớp {r['grade']} | {r['bo_sach']} | {r['subj']}"
        text_trim = (r["text"] or "")[:4000]
        contexts.append(f"📌 {r['title']} ({meta})\n{text_trim}")

    return "\n\n".join(contexts)


# ── COMPANION (Lesson Card) + sanitize ─────────────────────────────
_LESSON_NOISE = [
    r"\(Giáo viên VietJack\)", r"Cô [A-ZÀ-Ỹ][^\n]*\(Giáo viên[^\n]*\)",
    r"Xem lời giải", r"Xem chi tiết", r"Bài giảng:[^\n]*",
    r"Toán - Văn - Anh[^\n]*", r"Giải sgk[^\n]*", r"Quảng cáo",
    r"Giải bài nhanh với AI Hay", r"20\+ Mẫu[^\n]*",
]
def sanitize_chunk_text(t: str) -> str:
    t = t or ""
    for p in _LESSON_NOISE:
        t = re.sub(p, "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()

_PRACTICE_RE = re.compile(r"(làm bài tập|luyện tập|giải câu|giải bài|làm câu|bài tập|chữa bài|trả lời câu|soạn câu|tự kiểm tra|câu hỏi để|câu hỏi ôn|ôn lại|thực hành|kiểm tra lại|luyện)")

def query_lesson_card(user_profile, parsed, query, allow_vec=True, force_recite=None, force_practice=None):
    """Companion: nếu profile.current_lesson hoặc query nêu tên 1 bài có :Lesson -> trả Lesson Card.
    allow_vec=False: CHỈ neo exact (tên/trang), bỏ qua content-vector (semantic, độ chính xác thấp)
    -> dùng cho pass đầu (trước rewrite) để rewrite được ưu tiên hơn semantic-guess."""
    up = user_profile or {}
    cur = up.get("current_lesson") or up.get("bai_dang_hoc") or ""
    grade = parsed.get("lop"); book = parsed.get("bo_sach")
    subj_f = parsed.get("subject")
    cur_norm = _fold(cur) if cur else ""
    qf = _fold(query)
    cy = """
        MATCH (l:Lesson)
        WHERE ($tap IS NULL OR l.tap_no=$tap)
          AND ($subject IS NULL OR l.subject_code=$subject)
          AND ( ($cur_norm <> '' AND l.work_name_norm=$cur_norm)
                OR ($cur_norm = '' AND size(l.work_name_norm)>=5 AND $qf CONTAINS l.work_name_norm)
                OR ($trang IS NOT NULL AND l.trang_from IS NOT NULL AND l.trang_from<=$trang AND $trang<=l.trang_to) )
        MATCH (l)-[:HAS_THEORY]->(t:KnowledgeChunk)
        OPTIONAL MATCH (l)-[:HAS_RECITE]->(lt:LiteratureText)
        WITH l, t, count(lt) AS recite, collect(coalesce(lt.full_text, lt.text))[0] AS recite_text, size(l.work_name_norm) AS wlen,
             max(CASE WHEN lt.recite_default THEN 1 ELSE 0 END) AS rdef,
             (CASE WHEN ($cur_norm<>'' AND l.work_name_norm=$cur_norm) THEN 2
                   WHEN ($cur_norm='' AND size(l.work_name_norm)>=5 AND $qf CONTAINS l.work_name_norm) THEN 2
                   ELSE 1 END) AS prio,
             (CASE WHEN $grade IS NOT NULL AND l.grade=$grade THEN 1 ELSE 0 END) AS gmatch,
             (CASE WHEN $book IS NOT NULL AND l.bo_sach=$book THEN 1 ELSE 0 END) AS bmatch
        RETURN l.work_name AS work, l.trang_no AS trang, l.subject_code AS subj,
               t.text AS theory, t.guiding_questions AS gq, recite, recite_text, l.practice_json AS practice_json
        ORDER BY prio DESC, gmatch DESC, bmatch DESC, rdef DESC, wlen DESC LIMIT 1
    """
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session() as s:
            rec = s.run(cy, grade=grade, book=book, cur_norm=cur_norm, qf=qf, trang=parsed.get('trang'), tap=(user_profile or {}).get('tap') or (user_profile or {}).get('tap_no'), subject=subj_f).single()
        driver.close()
    except Exception as e:
        print(f"[Lesson Card Error] {e}")
        return None
    if not rec:
        if not allow_vec:
            return None  # pass đầu (trước rewrite): chỉ neo exact, nhường content-vec cho pass cuối
        # CONTENT-VECTOR: không có neo tên/trang -> match ngữ nghĩa trên theory embeddings (mô tả nội dung -> ra bài)
        if grade and book and bge_m3_model is not None and len((query or '').split())>=3:
            try:
                tap = (user_profile or {}).get('tap') or (user_profile or {}).get('tap_no')
                qv = bge_m3_model.encode([query], normalize_embeddings=True)[0].tolist()
                drv = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
                with drv.session() as _s:
                    cand = _s.run("""MATCH (l:Lesson)-[:HAS_THEORY]->(t:KnowledgeChunk)
                        WHERE l.grade=$g AND l.bo_sach=$b AND ($tap IS NULL OR l.tap_no=$tap) AND ($subject IS NULL OR l.subject_code=$subject) AND t.embedding IS NOT NULL
                        RETURN l.work_name AS work, l.trang_no AS trang, l.subject_code AS subj,
                               t.text AS theory, t.guiding_questions AS gq, t.embedding AS emb,
                               l.practice_json AS practice_json,
                               [(l)-[:HAS_RECITE]->(lt) | lt.full_text][0] AS recite_text""",
                        g=grade,b=book,tap=tap,subject=subj_f).data()
                drv.close()
                best=None; bs=-1.0; bs2=-1.0
                for c in cand:
                    e=c.get("emb")
                    if not e: continue
                    sim=sum(x*y for x,y in zip(qv,e))
                    if sim>bs: bs2=bs; bs=sim; best=c
                    elif sim>bs2: bs2=sim
                if best is not None: print(f"[content-vec] top1={bs:.3f} top2={bs2:.3f} -> {best.get('work')}")
                if best is not None and bs>=0.50 and ((bs-bs2)>=0.04 or bs>=0.60):
                    best['recite']=1 if best.get('recite_text') else 0
                    print(f"[RAG] content-vec hit {best.get('work')} sim={bs:.3f}")
                    rec=best
            except Exception as _e:
                print(f"[content-vec] {_e}")
        if not rec:
            return None
    _qlow = (query or "").lower()
    # Intent do GEMMA quyết (force_recite/force_practice); chỉ khi None mới fallback regex.
    if force_recite is not None or force_practice is not None:
        _want_recite = bool(force_recite); _want_practice = bool(force_practice)
    else:
        _im = _classify_intent(query)
        _want_recite = bool(_is_recite(_qlow) or _im == "recite")
        _want_practice = bool(_PRACTICE_RE.search(_qlow) or _im == "practice")
    if _want_recite and rec.get("recite_text"):
        rctx = unicodedata.normalize('NFC', "[ĐỌC THUỘC - NGUYÊN VĂN]\nNguồn chính:\n" + (rec["work"] or "") + "\n\n" + rec["recite_text"])
        return {"context": rctx, "intent": {"need_rag": True, "subject": rec["subj"], "grade": grade, "bo_sach": book, "query_type": "recite_full_text", "tier": "lesson_recite", "work_name": rec["work"]}}
    if _want_practice and rec.get("practice_json"):
        try:
            _ex = json.loads(rec["practice_json"])
        except Exception:
            _ex = []
        if _ex:
            _L = ["[LUYỆN TẬP - ĐỒNG HÀNH] " + (rec["work"] or ""),
                  "(Đưa từng câu hỏi kèm gợi ý cho học sinh thử; CHỈ hé đáp án khi học sinh đã thử hoặc yêu cầu.)"]
            for _e in _ex:
                _L.append("\n" + str(_e.get("cau","")) + ": " + str(_e.get("cau_hoi","")))
                _L.append("  Gợi ý: " + str(_e.get("goi_y","")))
                _L.append("  [Đáp án — chỉ hé khi cần]: " + str(_e.get("dap_an","")))
            pctx = unicodedata.normalize('NFC', "\n".join(_L))
            return {"context": pctx, "intent": {"need_rag": True, "subject": rec["subj"], "grade": grade, "bo_sach": book, "query_type": "practice", "delivery_mode": "guided_practice", "tier": "lesson_practice", "work_name": rec["work"]}}
    parts = [sanitize_chunk_text(rec["theory"])]
    try:
        gq = json.loads(rec["gq"]) if rec["gq"] else []
    except Exception:
        gq = []
    if gq:
        parts.append("Câu hỏi gợi mở:\n- " + "\n- ".join(gq))
    if rec["recite"]:
        parts.append("(Có bản nguyên văn để đọc thuộc.)")
    ctx = unicodedata.normalize('NFC', "[ĐỒNG HÀNH BÀI HỌC]\nNguồn chính:\n" + "\n\n".join(parts))
    intent = {"need_rag": True, "subject": rec["subj"], "grade": grade, "bo_sach": book,
              "query_type": "companion", "learning_mode": "tutor", "tier": "lesson_card",
              "work_name": rec["work"], "trang": rec["trang"]}
    return {"context": ctx, "intent": intent}


REWRITE_ENABLED = os.getenv("RAG_QUERY_REWRITE", "1") == "1"
_GREETING_RE = re.compile(r"^(chào|xin chào|hi|hello|alo|a lô|cậu ơi|bạn ơi)(\s+\w+){0,3}[\s,.!?ạ]*$")

def rewrite_query_fast(query: str) -> str:
    """Gemma-4 sửa nhanh câu STT sai (bỏ qua chào hỏi). Trả '' nếu không đổi/lỗi."""
    q = (query or "").strip()
    if not q or _GREETING_RE.match(q.lower()):
        return ""
    sys_p = (
        "Bạn sửa câu hỏi của học sinh nói qua giọng nói (STT thường sai chính tả, sai tên bài/tác giả). "
        "Câu thường là yêu cầu ĐỌC/HỌC một bài thơ hoặc tác phẩm trong sách giáo khoa Việt Nam. "
        "Nếu câu có tên TÁC GIẢ (Thế Lữ, Tố Hữu, Nguyễn Du, Xuân Diệu, Hồ Chí Minh...), hãy suy ra TÁC PHẨM "
        "nổi tiếng của họ trong chương trình và sửa thành dạng 'Đọc bài thơ <Tên tác phẩm> của <Tác giả>'. "
        "Sửa cả lỗi chính tả tên bài (vd 'nhờ dừng/nhớ giường' -> 'Nhớ rừng'). "
        "CHỈ trả về MỘT câu đã sửa, không giải thích.\n"
        "Ví dụ:\n"
        "- 'tôi bài nhờ dừng của nhà thơ thế lữ' => Đọc bài thơ Nhớ rừng của Thế Lữ\n"
        "- 'đọc bài lượm tố hữu' => Đọc bài thơ Lượm của Tố Hữu"
    )
    try:
        out = call_gemma(sys_p, q, max_tokens=64, timeout=4)
    except Exception as e:
        print("[RAG] rewrite err:", e)
        return ""
    if not out:
        return ""
    out = out.strip().strip('"' + "“”").splitlines()[0].strip()
    return out


# ── GEMMA-JSON query normalizer: hiểu câu STT bẩn -> JSON có cấu trúc (<1s) ──
# Nguyên tắc: Gemma CHỈ chuẩn hoá (intent + tên bài + môn); KHO (Neo4j) quyết định
# 'có/không ra'. KHÔNG để Gemma tự quyết tồn tại (nó 'biết' Lão Hạc/Vợ nhặt là thật -> ép rác).
NORMALIZE_ENABLED = os.getenv("RAG_QUERY_NORMALIZE", "1") == "1"
_SESSION_WORK = {}   # session_id -> bài Gemma neo gần nhất (đưa vào ngữ cảnh làm anchor follow-up)
_SUBJECT_CODES = {"ngu_van", "toan", "khtn", "lich_su", "dia_li", "gdcd", "tieng_anh"}
_SUBJECT_ALIAS = {
    "van": "ngu_van", "ngu van": "ngu_van", "ngữ văn": "ngu_van", "ngu_văn": "ngu_van",
    "toán": "toan", "lịch sử": "lich_su", "lich su": "lich_su", "sử": "lich_su",
    "địa lí": "dia_li", "địa lý": "dia_li", "dia ly": "dia_li", "dia_ly": "dia_li", "địa": "dia_li",
    "khoa học tự nhiên": "khtn", "gdcd": "gdcd", "tiếng anh": "tieng_anh",
}
def _subject_code(s):
    if not s:
        return None
    s = str(s).strip().lower()
    if s in _SUBJECT_CODES:
        return s
    return _SUBJECT_ALIAS.get(s)

_NORM_SYS = (
    "Bạn phân tích câu nói của học sinh Việt Nam (qua nhận dạng giọng nói, có thể sai chính tả/tên bài). "
    "Trả về DUY NHẤT một dòng JSON, KHÔNG giải thích, KHÔNG markdown:\n"
    '{"intent":"recite|explain|practice|chat","source":"sgk|wiki|realtime|chat","work":"tên tác phẩm/bài học đã sửa lỗi (KHÔNG kèm tác giả) hoặc null",'
    '"author":"tác giả nếu học sinh nêu hoặc null","subject":"ngu_van|toan|khtn|lich_su|dia_li|gdcd hoặc null",'
    '"grade":"số lớp 1-12 nếu câu nêu, hoặc null","bo_sach":"CTST|KNTT|CD nếu câu nêu, hoặc null",'
    '"bai_no":"số bài nếu câu nêu (vd bài 5 -> 5), hoặc null","trang":"số trang nếu câu nêu, hoặc null",'
    '"wiki_query":"tên thực thể gọn để tra Wikipedia khi source=wiki, hoặc null"}\n'
    "Quy tắc:\n"
    "- grade/bo_sach/bai_no/trang: CHỈ điền khi câu NÊU RÕ (vd 'giải bài 5 lớp 8 trang 20 chân trời'); KHÔNG suy đoán -> null.\n"
    "- intent=recite: muốn ĐỌC/NGÂM/HỌC THUỘC nguyên văn cả bài.\n"
    "- intent=explain: HỎI VỀ bài (là gì, là ai, có biết…không, nội dung, ý nghĩa, giảng, phân tích).\n"
    "- intent=practice: muốn làm bài tập/luyện tập.\n"
    "- intent=chat: chào hỏi/tán gẫu -> work=null.\n"
    "- source: 'sgk' nếu hỏi/đọc/giảng/làm BÀI hoặc TÁC PHẨM có trong sách giáo khoa (MẶC ĐỊNH). "
    "'wiki' nếu hỏi kiến thức ĐỜI SỐNG/lịch sử/nhân vật/tổ chức/trường học/khoa học phổ thông KHÔNG gắn 1 bài SGK cụ thể. "
    "'realtime' nếu hỏi NGÀY/GIỜ hiện tại. 'chat' nếu chào hỏi/tán gẫu.\n"
    "- wiki_query: CHỈ điền khi source=wiki — TÊN THỰC THỂ gọn để tra Wikipedia "
    "(vd 'Nguyễn Hiền','Học viện Công nghệ Bưu chính Viễn thông','Liên minh châu Âu'), KHÔNG phải cả câu; source khác -> null.\n"
    "- work: CHỈ tên tác phẩm, sửa lỗi STT (vd 'nhớ dừng'->'Nhớ rừng'; 'thế nữ'->author 'Thế Lữ').\n"
    "- FOLLOW-UP: nếu có dòng '[BÀI CŨ]: X' và câu hiện tại HỎI TIẾP về bài đó (không nêu bài mới rõ ràng, "
    "vd 'nội dung chính là gì','tác giả là ai','đọc lại đi','giảng thêm') -> work=X (giữ chủ đề). "
    "Nếu câu NÊU tác phẩm/bài KHÁC -> work=bài mới (ĐỔI chủ đề). Câu không nêu bài & không có bài cũ -> work=null.\n"
    "- TUYỆT ĐỐI không đổi sang tên tác phẩm khác cái học sinh muốn nói.\n"
    "Ví dụ: 'đọc cho tôi bài nhớ dừng của thế nữ' => {\"intent\":\"recite\",\"work\":\"Nhớ rừng\",\"author\":\"Thế Lữ\",\"subject\":\"ngu_van\"}\n"
    "'bạn có biết tác phẩm lão hạc không' => {\"intent\":\"explain\",\"source\":\"sgk\",\"work\":\"Lão Hạc\",\"author\":null,\"subject\":\"ngu_van\"}\n"
    "'nguyễn hiền là ai' => {\"intent\":\"explain\",\"source\":\"wiki\",\"work\":null,\"wiki_query\":\"Nguyễn Hiền\",\"subject\":null}\n"
    "'mấy giờ rồi' => {\"intent\":\"chat\",\"source\":\"realtime\",\"work\":null,\"wiki_query\":null}"
)
def _normalize_query_gemma(query, prev_work=None):
    """Gemma-4 -> {intent, work, author, subject, grade, bo_sach, bai_no, trang}. None nếu lỗi.
    prev_work = bài Gemma đã neo ở lượt TRƯỚC (cùng session) -> đưa vào ngữ cảnh để Gemma
    tự quyết follow-up (giữ bài cũ) hay đổi chủ đề (bài mới)."""
    q = (query or "").strip()
    if not q:
        return None
    usr = q if not prev_work else f"[BÀI CŨ]: {prev_work}\nCâu hiện tại: {q}"
    try:
        raw = call_gemma(_NORM_SYS, usr, max_tokens=120, timeout=3)
    except Exception as e:
        print("[normalize] err:", e)
        return None
    if not raw:
        return None
    raw = raw.replace("```json", "").replace("```", "").strip()
    d = None
    try:
        d = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
            except Exception:
                d = None
    if not isinstance(d, dict):
        return None
    intent = str(d.get("intent") or "").strip().lower()
    if intent not in ("recite", "explain", "practice", "chat"):
        intent = "explain"
    work = d.get("work")
    work = work.strip() if isinstance(work, str) else None
    if work and work.lower() in ("null", "none", ""):
        work = None
    author = d.get("author")
    if isinstance(author, str) and author.strip().lower() in ("null", "none", ""):
        author = None
    def _int(v):
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return None
    _bo = d.get("bo_sach")
    _bo = _bo.strip().upper() if isinstance(_bo, str) else None
    if _bo not in ("CTST", "KNTT", "CD"):
        _bo = None
    _src = str(d.get("source") or "").strip().lower()
    if _src not in ("sgk", "wiki", "realtime", "chat"):
        _src = "sgk"                      # mặc định an toàn: đi kho SGK trước
    _wq = d.get("wiki_query")
    _wq = _wq.strip() if isinstance(_wq, str) and _wq.strip().lower() not in ("null", "none", "") else None
    if _src != "wiki":
        _wq = None                        # wiki_query chỉ có nghĩa khi source=wiki
    return {"intent": intent, "source": _src, "wiki_query": _wq,
            "work": work or None, "author": (author or None),
            "subject": _subject_code(d.get("subject")),
            "grade": _int(d.get("grade")), "bo_sach": _bo,
            "bai_no": _int(d.get("bai_no")), "trang": _int(d.get("trang"))}

def _not_found_response(work, grade):
    """RAG trung thực: KHÔNG có trong kho -> nói 'chưa có', không bịa/ép rác."""
    _w = work or "này"
    msg = f'[KHÔNG TÌM THẤY] Kho tri thức hiện CHƯA có tác phẩm/bài học "{_w}"'
    if grade:
        msg += f" trong chương trình lớp {grade}"
    msg += (". Hãy nói thật với học sinh rằng bài này chưa có trong kho, "
            "gợi ý em kiểm tra lại tên bài hoặc chọn bài khác. TUYỆT ĐỐI không bịa nội dung.")
    intent = {"need_rag": True, "query_type": "not_found", "learning_mode": "tutor",
              "tier": "not_found", "work_name": work, "grade": grade}
    return RetrieveResponse(context=unicodedata.normalize('NFC', msg), intent=intent, sources=["not_found"])


def _infer_subject_into(parsed, query):
    """Suy MÔN sớm từ query khi profile không ghi môn → để các tầng exact (lesson_card/
    concept/structured) lọc đúng môn, CHỐNG leak chéo (hỏi Văn ra Toán/KHTN). Chỉ set khi trống."""
    if parsed.get("subject"):
        return
    s = override_subject_by_keywords(query, canonicalize_subject(None, query))
    if s:
        parsed["subject"] = s
        print(f"[RAG] Suy môn sớm: {s}")


# ══════════════════════════════════════════════════════════════════════════
# WIKI ORCHESTRATOR (canary :8892) — lưới đỡ NGOÀI-SGK. Xem WIKI_ORCHESTRATOR_CANARY_GUIDE.md
#   Bất biến: wiki KHÔNG BAO GIỜ chạm recite (context text-block, không phải JSON) ;
#   chỉ chạy khi gwork=None HOẶC B2b/B4-miss + intent=explain + có wiki_query ; async + budget + breaker.
# ══════════════════════════════════════════════════════════════════════════
WIKI_ENABLED = os.getenv("WIKI_ENABLED", "1") == "1"          # van tắt-nhanh (ops)
WIKI_LANG = os.getenv("WIKI_LANG", "vi")
WIKI_BUDGET_S = float(os.getenv("WIKI_BUDGET_S", "2.5"))      # ngân sách TỔNG wall-clock 1 lượt wiki
WIKI_CHARS = int(os.getenv("WIKI_CHARS", "2200"))
_WIKI_UA = "PTalkEdu/1.0 (lien he: namnx@ptalk.vn)"

# cache TÁCH: hit / stable-negative (không có trang) / transient-fail (timeout) — TTL khác nhau
_WIKI_CACHE = {}                 # term_norm -> (expire_ts, (title, extract))
_WIKI_TTL_HIT = 86400            # 24h cho kết quả CÓ nội dung
_WIKI_TTL_NEG = 6 * 3600         # 6h cho "không có trang" ổn định
_WIKI_TTL_FAIL = 45              # 45s cho lỗi tạm thời (KHÔNG đầu độc entity thật 24h)
# circuit-breaker: N lỗi liên tiếp -> tắt wiki 1 cooldown, trả rỗng tức thì
_WIKI_CB = {"fails": 0, "open_until": 0.0}
_WIKI_CB_THRESHOLD = 3
_WIKI_CB_COOLDOWN = 60.0


def _wiki_norm_term(t):
    return _fold((t or "").strip())[:120]


def _wiki_title_ok(title, term):
    """Chống trúng trang LẠC NGHĨA / trang định hướng: title phải liên quan term."""
    if not title:
        return False
    tl = title.lower()
    if "(định hướng)" in tl or "disambig" in tl:
        return False
    a, b = _fold(title), _fold(term)
    if not b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if ta & tb or a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def _wiki_fetch_sync(term):
    """1 REQUEST gộp: generator=search + prop=extracts -> (title, extract). BLOCKING (chạy trong to_thread)."""
    base = "https://%s.wikipedia.org/w/api.php" % WIKI_LANG
    params = {
        "action": "query", "format": "json", "utf8": 1, "redirects": 1,
        "generator": "search", "gsrsearch": term, "gsrlimit": 3, "gsrnamespace": 0,
        "prop": "extracts", "exintro": 1, "explaintext": 1, "exchars": WIKI_CHARS,
    }
    url = base + "?" + urllib.parse.urlencode(params)
    r = requests.get(url, headers={"User-Agent": _WIKI_UA}, timeout=WIKI_BUDGET_S)
    if r.status_code != 200:
        raise RuntimeError("wiki http %s" % r.status_code)
    pages = (r.json().get("query", {}) or {}).get("pages", {}) or {}
    for p in sorted(pages.values(), key=lambda x: x.get("index", 999)):   # theo thứ hạng search
        title = p.get("title", "")
        ext = (p.get("extract", "") or "").strip()
        if ext and _wiki_title_ok(title, term):
            return (title, ext)
    return ("", "")   # không có trang khớp -> stable-negative


async def _try_wiki(term):
    """Lưới đỡ: ASYNC (to_thread, KHÔNG block event loop) + budget + circuit-breaker + cache tách.
    Trả (title, extract) hoặc ('','')."""
    if not WIKI_ENABLED:
        return ("", "")
    term = (term or "").strip()
    if not term:
        return ("", "")
    now = time.time()
    if now < _WIKI_CB["open_until"]:            # breaker MỞ -> rỗng tức thì
        print("[wiki] circuit-open -> skip")
        return ("", "")
    key = _wiki_norm_term(term)
    c = _WIKI_CACHE.get(key)
    if c and c[0] > now:
        return c[1]
    try:
        out = await asyncio.wait_for(asyncio.to_thread(_wiki_fetch_sync, term), timeout=WIKI_BUDGET_S)
        _WIKI_CB["fails"] = 0                    # thành công -> reset breaker
        _WIKI_CACHE[key] = (now + (_WIKI_TTL_HIT if out[1] else _WIKI_TTL_NEG), out)
        return out
    except Exception as e:
        print("[wiki] fail: %r" % (e,))
        _WIKI_CB["fails"] += 1
        if _WIKI_CB["fails"] >= _WIKI_CB_THRESHOLD:
            _WIKI_CB["open_until"] = now + _WIKI_CB_COOLDOWN
            print("[wiki] circuit OPEN %ss" % _WIKI_CB_COOLDOWN)
        _WIKI_CACHE[key] = (now + _WIKI_TTL_FAIL, ("", ""))   # transient -> TTL NGẮN
        return ("", "")


def _wiki_response(title, ext, qtype):
    ctx = unicodedata.normalize("NFC", "[NGUỒN NGOÀI SGK - Wikipedia: %s]\n%s" % (title, ext))
    return RetrieveResponse(
        context=ctx,
        intent={"need_rag": True, "query_type": qtype, "learning_mode": "explain",
                "source": "wikipedia", "source_title": title, "tier": "wiki"},
        sources=["wikipedia"])


async def retrieve(req: RetrieveRequest):
    print(f"\n[RAG] Nhận request: {req.query}")
    q = req.query
    sid = req.session_id or "default"
    prev_work = _SESSION_WORK.get(sid)

    # ══ B0+B1. GEMMA NORMALIZER LÀ TRUNG TÂM (mọi câu; bài cũ = work lượt TRƯỚC làm anchor follow-up) ══
    norm = _normalize_query_gemma(q, prev_work) if NORMALIZE_ENABLED else None
    if norm:
        print(f"[RAG] Normalize(prev={prev_work!r}): {norm}")
        kind = norm.get("intent"); gwork = norm.get("work"); gsubj = norm.get("subject")
        gauthor = norm.get("author")
        recite_intent = (kind == "recite"); practice_intent = (kind == "practice")
        bai_no = norm.get("bai_no"); trang = norm.get("trang")
        gsource = norm.get("source"); gwikiq = norm.get("wiki_query")
        ggrade = norm.get("grade"); gbo = norm.get("bo_sach")
        if ggrade is None:                       # option B: grade cua be tu profile (SOFT tie-break), query text sach
            _up = req.user_profile or {}
            try: ggrade = int(_up.get("grade") or _up.get("lop"))
            except (TypeError, ValueError): ggrade = None
        if gbo is None:
            gbo = (req.user_profile or {}).get("bo_sach") or (req.user_profile or {}).get("bo") or None
    else:
        # Gemma lỗi/timeout -> KHÔNG đoán bằng regex (Gemma là bộ não DUY NHẤT). Rơi xuống retrieval thường.
        kind = None; gwork = None; gsubj = None; gauthor = None
        recite_intent = False; practice_intent = False
        bai_no = None; trang = None
        gsource = None; gwikiq = None
        ggrade = None; gbo = None

    subj = gsubj
    parsed = {"lop": None, "bo_sach": None, "subject": subj, "bai_no": bai_no, "trang": trang}
    if gwork and gsource == "sgk":
        _SESSION_WORK[sid] = gwork      # HIGH#6: chỉ anchor khi domain SGK (không nhiễm wiki/realtime/chat)
    print(f"[RAG] intent={kind} work={gwork!r} subj={subj} bai_no={bai_no} trang={trang} prev={prev_work!r} (grade-free)")

    # ══ REALTIME: CHỈ khi câu THUẦN hỏi giờ/ngày (không kèm học/bài/đọc...) — HIGH#11 ══
    if gsource == "realtime" and not gwork:
        _ql = q.lower()
        if not any(k in _ql for k in ("học", "bài", "đọc", "giảng", "thơ", "văn", "toán")):
            _now = (datetime.now(_VN_TZ) if _VN_TZ else datetime.now()).strftime("Bây giờ là %H giờ %M, ngày %d/%m/%Y")
            return RetrieveResponse(context="[THỜI GIAN THỰC]\n" + _now,
                                    intent={"need_rag": True, "query_type": "realtime"}, sources=["clock"])

    if kind == "chat" and not gwork:
        return RetrieveResponse(context="", intent={"need_rag": False, "query_type": "chat"}, sources=[])

    # ══ B2. ANCHOR THEO WORK CỦA GEMMA (work=biến; câu nêu bài khác -> thay biến; KHÔNG dùng current_lesson) ══
    if gwork:
        # TÁC GIẢ nêu rõ -> bản của ĐÚNG tác giả thắng lesson_card. Không có bước này thì
        # tác phẩm trùng tên luôn ra bản có :Lesson: 'Mẹ của Đỗ Trung Lai' (Ngữ văn 7, chỉ
        # là :LiteratureText) bị trả thành 'Mẹ' của Trần Quốc Minh (lớp 2, có :Lesson).
        if recite_intent and gauthor:
            _rs = {"subject": subj, "grade": None, "bo_sach": None, "query_type": "recite_full_text"}
            _rauth = recite_from_literature_text(gwork, _rs, grade=ggrade, bo_sach=gbo, author=gauthor)
            if _rauth:
                print(f"[RAG] ✅ Author-exact recite work={gwork!r} author={gauthor!r}")
                _rauth.context = unicodedata.normalize('NFC', _rauth.context)
                return _rauth
        if recite_intent and ggrade is not None:     # recite + grade cu the: uu tien ban GRADE-EXACT truoc lesson_card
            _rs = {"subject": subj, "grade": None, "bo_sach": None, "query_type": "recite_full_text"}
            _rstrict = recite_from_literature_text(gwork, _rs, grade=ggrade, bo_sach=gbo, strict_grade=True)
            if _rstrict:
                _rstrict.context = unicodedata.normalize('NFC', _rstrict.context)
                return _rstrict
        # Không nêu tác giả/lớp mà tên bài TRÙNG nhiều tác phẩm -> theo recite_default
        # của graph. Chỉ fire khi thật trùng tên (xem require_homonym_default), nên các
        # bài không trùng tên vẫn đi nguyên luồng lesson_card như trước.
        if recite_intent and not gauthor and ggrade is None:
            _rs = {"subject": subj, "grade": None, "bo_sach": None, "query_type": "recite_full_text"}
            _rhom = recite_from_literature_text(gwork, _rs, require_homonym_default=True)
            if _rhom:
                _rhom.context = unicodedata.normalize('NFC', _rhom.context)
                return _rhom
        anchor_prof = {"current_lesson": gwork}      # ép anchor EXACT theo work Gemma (bỏ size-guard)
        pa = {"lop": ggrade, "bo_sach": gbo, "subject": subj}   # grade-anchor: câu NÊU lớp/bộ -> lọc đúng bản
        lc = query_lesson_card(anchor_prof, pa, gwork, allow_vec=False,
                               force_recite=recite_intent, force_practice=practice_intent)
        if lc:
            print(f"[RAG] ✅ Lesson anchor tier={lc['intent'].get('tier')} work={lc['intent'].get('work_name')!r}")
            return RetrieveResponse(context=lc["context"], intent=lc["intent"], sources=["lesson_card"])
        # B2a. recite ĐỘC LẬP (work không có :Lesson nhưng có nguyên văn)
        if recite_intent:
            _ri = {"subject": subj, "grade": None, "bo_sach": None, "query_type": "recite_full_text"}
            rec = (recite_from_literature_text(gwork, _ri, grade=ggrade, bo_sach=gbo)
                   or recite_from_reading_text(gwork, grade=ggrade, bo_sach=gbo)
                   or recite_from_full_document(gwork, _ri, grade=ggrade, bo_sach=gbo))
            if rec:
                rec.context = unicodedata.normalize('NFC', rec.context)
                return rec
        # B2b. Khong co :Lesson & khong co nguyen van.
        # recite/practice-miss -> not_found TỨC THÌ (HIGH#5). explain-miss + có wiki_query -> lưới wiki (bỏ #2).
        if kind == "explain" and gwikiq:
            _wt, _we = await _try_wiki(gwikiq)
            if _we:
                print(f"[RAG] WIKI fallback (B2b) title={_wt!r}")
                return _wiki_response(_wt, _we, "wiki_fallback")
        print(f"[RAG] KHONG RA: work={gwork!r}")
        return _not_found_response(gwork, None)

    # ══ EAGER WIKI: chỉ khi KHÔNG có work SGK — câu kiến-thức-đời ngoài SGK (#3) ══
    if gsource == "wiki" and kind == "explain" and gwikiq:
        _wt, _we = await _try_wiki(gwikiq)
        if _we:
            print(f"[RAG] WIKI eager title={_wt!r}")
            return _wiki_response(_wt, _we, "wiki")
        # wiki rỗng -> rơi xuống retrieval thường / not_found

    # ══ B3. TIER A: câu nêu BÀI SỐ / TRANG (không có work cụ thể) ══
    if parsed.get("bai_no") or parsed.get("trang"):
        tier_a_ctx = query_structured_exact(parsed)
        if tier_a_ctx:
            intent_a = {"need_rag": True, "subject": subj, "grade": None, "bo_sach": None,
                        "query_type": "explain", "learning_mode": "tutor", "tier": "A_structured",
                        "bai_no": parsed.get("bai_no"), "trang": parsed.get("trang")}
            ctx = unicodedata.normalize('NFC', f"[DU LIEU EXACT - TIER A]\nNguon chinh:\n{tier_a_ctx}")
            return RetrieveResponse(context=ctx, intent=intent_a, sources=["tier_a_structured"])

    # ══ B4. RETRIEVAL THƯỜNG (không có work; câu hỏi kiến thức/chủ đề) ══
    intent = route_query_rule_based(q)
    if subj and not intent.get("subject"):
        intent["subject"] = subj
    intent["grade"] = None; intent["bo_sach"] = None       # bỏ giới hạn lớp
    intent["learning_mode"] = detect_learning_mode(q)
    intent["subject"] = canonicalize_subject(intent.get("subject"), q)
    intent["subject"] = override_subject_by_keywords(q, intent.get("subject"))
    print(f"[RAG] Ý định (B4): {intent}")
    if intent.get("need_rag") is False:
        return RetrieveResponse(context="", intent=intent, sources=[])

    context_parts = []; sources = []
    subject_str = (intent.get("subject") or "").lower()
    if recite_intent or intent.get("query_type") == "recite_full_text":
        title = intent.get("title") or intent.get("keyword", "")
        recitation = (recite_from_literature_text(title, intent, grade=None, bo_sach=None)
                      or recite_from_reading_text(title, grade=None, bo_sach=None)
                      or recite_from_full_document(title, intent, grade=None, bo_sach=None))
        if recitation:
            recitation.context = unicodedata.normalize('NFC', recitation.context)
            return recitation
    neo4j_chunk_data = query_neo4j_knowledge_chunk(intent)
    if neo4j_chunk_data:
        context_parts.append("[DỮ LIỆU CẤU TRÚC - NEO4J KNOWLEDGE CHUNK]\nNguồn chính:\n" + neo4j_chunk_data)
        sources.append("neo4j_knowledge_chunk")
    lg_data = query_neo4j_lesson_guide(intent)
    if lg_data:
        context_parts.append("[DỮ LIỆU HƯỚNG DẪN - NEO4J LESSON GUIDE]\nNguồn bổ sung:\n" + lg_data)
        sources.append("neo4j_lesson_guide")
    if not context_parts:
        if subject_str in SUBJECT_TO_QDRANT:
            qdrant_data = query_qdrant(intent)
            if qdrant_data:
                context_parts.append("[DỮ LIỆU VECTOR - QDRANT FALLBACK]\nNguồn chính:\n" + qdrant_data)
                sources.append("qdrant_vector_fallback")
        else:
            neo4j_data = query_neo4j_vector(intent)
            if neo4j_data:
                context_parts.append("[DỮ LIỆU CẤU TRÚC - NEO4J VECTOR FALLBACK]\nNguồn chính:\n" + neo4j_data)
                sources.append("neo4j_vector_fallback")
    final_context = "\n\n".join(context_parts)
    if not final_context:
        # B4-miss: lưới wiki cho câu explain có thực thể (gate HIGH#5) trước khi trả miss trung thực
        if kind == "explain" and gwikiq:
            _wt, _we = await _try_wiki(gwikiq)
            if _we:
                print(f"[RAG] WIKI fallback (B4) title={_wt!r}")
                return _wiki_response(_wt, _we, "wiki_fallback")
        final_context = "Hệ thống RAG chưa tìm thấy dữ liệu nội bộ phù hợp cho câu hỏi này."
    final_context = trim_context(final_context, intent.get("learning_mode", "explain"))
    final_context = unicodedata.normalize('NFC', final_context)
    return RetrieveResponse(context=final_context, intent=intent, sources=sources)

if __name__ == "__main__":
    import uvicorn
    import asyncio
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("RAG_PORT", "8888")))
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
