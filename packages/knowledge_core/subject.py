"""Subject canonicalization, keyword override, learning-mode + context trim.

EXTRACTED VERBATIM from /tmp/refsrc_canary.py. All function bodies and the
constant tables (SUBJECT_ALIASES, MATH/KHTN/LICHSU/VANHOC_FORCE_KEYWORDS,
CONTEXT_LIMITS) are byte-for-byte copies. Pure: no IO, no model, no DB.

NOTE: `SUBJECT_TO_QDRANT` lives in the source next to these helpers but is only
used by the Qdrant retrieval path (IO). It is NOT extracted here — it belongs to
the retrieval layer, not knowledge_core.
"""
from __future__ import annotations


SUBJECT_ALIASES = {
    "toan": ["toán", "toan", "hình học", "đại số", "phương trình", "bất phương trình", "phân số"],
    "ngu_van": ["ngữ văn", "ngu van", "văn", "soạn bài", "phân tích nhân vật", "bài thơ"],
    "khtn": ["khtn", "khoa học tự nhiên", "nguyên tử", "phân tử", "vật lý", "lý", "hóa học", "hóa", "sinh học", "sinh"],
    "lich_su": ["lịch sử", "lich su", "sử", "khởi nghĩa", "hai bà trưng"],
    "dia_ly": ["địa lý", "địa lí", "dia ly", "bản đồ", "khí hậu", "dân cư"],
    "tieng_anh": ["tiếng anh", "tieng anh", "english", "grammar", "vocabulary"],
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
