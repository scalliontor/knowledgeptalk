"""
Subject detector — Layer 1 of multi-subject RAG classifier.
Detects which school subject a query relates to using rule-based keyword matching.
"""
import re
from typing import Optional

# ======================================================
# Keyword banks per subject
# ======================================================

SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "toan": [
        r"cộng", r"trừ", r"phép\s+nhân", r"tích\b", r"chia", r"phân số", r"hỗn số", r"phần trăm",
        r"tam giác", r"hình thang", r"hình thoi", r"hình tròn", r"diện tích",
        r"chu vi", r"thể tích", r"phương trình", r"bất phương trình",
        r"số thập phân", r"số tự nhiên", r"ước số", r"bội số", r"tỉ số",
        r"căn bậc", r"lũy thừa", r"hàm số", r"hệ tọa độ", r"đồ thị",
        r"toán\b", r"bài\s+toán", r"lời\s+giải\s+toán",
    ],
    "khtn": [
        r"nguyên tử", r"phân tử", r"hóa trị", r"liên kết hóa", r"axit", r"bazơ",
        r"muối\b", r"phản ứng hóa", r"oxygen", r"hydrogen", r"quang hợp",
        r"hô hấp", r"tế bào", r"gene", r"di truyền", r"vận tốc", r"lực\b",
        r"năng lượng", r"điện trở", r"từ trường", r"âm thanh", r"ánh sáng",
        r"nhiệt độ", r"dung dịch", r"khtn", r"khoa học tự nhiên", r"phản ứng",
        r"mol\b", r"electron", r"proton", r"thí nghiệm", r"động năng", r"thế năng",
        r"hệ mặt trời", r"ngân hà", r"vũ trụ", r"thực vật", r"động vật", r"sinh vật",
        r"đa dạng sinh học", r"hô hấp", r"khoáng chất"
    ],
    "tieng_anh": [
        r"english", r"grammar", r"vocabulary", r"pronunciation", r"tense",
        r"present simple", r"past simple", r"future", r"unit\s+\d",
        r"từ vựng tiếng anh", r"ngữ pháp tiếng anh", r"tiếng anh lớp",
        r"\bverb\b", r"\bnoun\b", r"\badjective\b", r"writing skill",
        # Common standalone English words in Vietnamese queries
        r"\bschool\b", r"\bbook\b", r"\bfriend\b", r"\bhome\b", r"\bfamily\b",
        r"\bteacher\b", r"\bstudent\b", r"\bplay\b", r"\bsport\b",
        r"nghĩa\s+(là\s+gì|tiếng\s+việt|của\s+\w+)\s*\?",
        r"(tiếng anh|anh văn)\s+(là gì|nghĩa|nói)",
    ],
    "lich_su": [
        r"triều đại", r"cách mạng", r"kháng chiến", r"khởi nghĩa",
        r"chiến tranh\b", r"\bvua\b", r"hoàng đế", r"nhà\s+(nguyễn|lý|trần|lê|đinh|tiền lê|hồ)",
        r"thế kỉ\s+\d", r"năm\s+\d{3,4}", r"giải phóng\s+dân tộc",
        r"lịch sử", r"trận\s+\w+", r"cuộc\s+khởi nghĩa",
    ],
    "dia_li": [
        r"khí hậu", r"địa hình", r"dân số", r"châu\s+\w+", r"đại dương",
        r"khoáng sản", r"đồng bằng", r"cao nguyên", r"kinh tế vùng",
        r"công nghiệp hóa", r"nông nghiệp\b", r"địa lí", r"địa lý",
        r"vùng kinh tế", r"bản đồ",
    ],
    "gdcd": [
        r"đạo đức", r"trung thực", r"tôn trọng", r"pháp luật",
        r"quyền và nghĩa vụ", r"nhân quyền", r"công dân", r"tiết kiệm",
        r"gdcd", r"giáo dục công dân", r"nhặt được", r"quyền trẻ em",
    ],
}

# TV/NV keywords (checked separately, depends on grade context)
TVNV_KEYWORDS = [
    r"bài đọc", r"bài thơ", r"tập làm văn", r"văn mẫu",
    r"nhân vật", r"tác giả", r"tác phẩm", r"phân tích\s+bài",
    r"soạn\s+(bài|văn)", r"đọc hiểu", r"văn bản",
    # Reading request patterns — "đọc cho tớ bài X", "đọc bài X"
    r"đọc\s+(cho\s+\w+\s+)?bài\b", r"nghe\s+bài\b",
    r"cảm\s+nhận", r"tóm\s+tắt\s+bài",
    r"nội\s+dung\s+(bài|của)", r"nhớ\s+rừng",  # common literary works as anchors
]


def detect_subject(query: str, user_profile: Optional[dict] = None) -> tuple[str, float]:
    """
    Detect school subject from query.

    Returns:
        (subject, confidence) where subject ∈ {
            toan, khtn, tieng_anh, lich_su, dia_li, gdcd,
            tieng_viet, ngu_van, unknown
        }
    """
    q = query.lower()
    scores: dict[str, int] = {}

    # Score each subject
    for subj, patterns in SUBJECT_KEYWORDS.items():
        score = sum(1 for p in patterns if re.search(p, q))
        scores[subj] = score

    # TV/NV scoring — influenced by grade
    tvnv_score = sum(1 for p in TVNV_KEYWORDS if re.search(p, q))
    grade = user_profile.get("lop") if user_profile else None

    if grade and isinstance(grade, int):
        tvnv_key = "tieng_viet" if grade <= 5 else "ngu_van"
    else:
        tvnv_key = "ngu_van" if tvnv_score else None

    if tvnv_key:
        scores[tvnv_key] = scores.get(tvnv_key, 0) + tvnv_score

    # Find winner
    if not scores or max(scores.values()) == 0:
        # No strong signal — return None, 0.0 so we can fallback to semantic global search
        return None, 0.0

    best_subj = max(scores, key=scores.get)
    best_score = scores[best_subj]

    # Compute confidence
    sorted_vals = sorted(scores.values(), reverse=True)
    runner_up = sorted_vals[1] if len(sorted_vals) > 1 else 0
    if runner_up > 0:
        confidence = best_score / (best_score + runner_up)
    else:
        confidence = 1.0

    return best_subj, round(confidence, 3)


def test_subject_detector():
    """Quick sanity check — run with python -m src.retrieval.subject_detector"""
    cases = [
        # (query, profile, expected_subject)
        ("Đọc bài Lượm",             {"lop": 2}, "tieng_viet"),
        ("Đọc bài Lão Hạc",          {"lop": 8}, "ngu_van"),
        ("Từ ghép là gì lớp 4",       {"lop": 4}, "tieng_viet"),
        ("Công thức diện tích tam giác", {"lop": 5}, "toan"),
        ("Phân số là gì",             {"lop": 3}, "toan"),
        ("Nguyên tử là gì",           {"lop": 7}, "khtn"),
        ("School nghĩa là gì",        {"lop": 6}, "tieng_anh"),
        ("Trận Bạch Đằng năm bao nhiêu", {"lop": 6}, "lich_su"),
        ("Đồng bằng sông Hồng ở đâu", {"lop": 7}, "dia_li"),
        ("Trung thực là đức tính gì",  {"lop": 5}, "gdcd"),
    ]

    print("=== Subject Detector Test ===")
    passed = 0
    for query, profile, expected in cases:
        subj, conf = detect_subject(query, profile)
        ok = "✅" if subj == expected else "❌"
        if subj == expected:
            passed += 1
        print(f"{ok} [{expected:12s}→{subj:12s} {conf:.2f}] {query}")
    print(f"\n{passed}/{len(cases)} passed")


if __name__ == "__main__":
    test_subject_detector()
