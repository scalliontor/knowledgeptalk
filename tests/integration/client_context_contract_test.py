"""Integration stub: Client Context Contract for Knowledge PTalk /retrieve.

Đặc tả (executable) cho hợp đồng client → server. Mặc định **SKIP** trừ khi có
server thật ở RAG_URL. KHÔNG gọi prod, KHÔNG đụng server trong vòng refactor;
đây chỉ là test stub để CI/người verify chạy khi đã có canary an toàn.

Chạy có chủ đích:
    RAG_URL=http://localhost:8889 pytest tests/integration/client_context_contract_test.py -v

Không set RAG_URL  -> toàn bộ test SKIP (không có side-effect).

Ground truth (verify trong repo, không phải bịa):
  - body: {"query": <str>, "user_profile": {...}}   (backtest_book.py, megatest.py)
  - server đọc profile keys: lop, bo_sach, subject, tap, current_lesson, trang
  - response: intent.tier / intent.work_name / intent.trang, context, choices[0].message.content
  - CARD_TIERS = {lesson_card, lesson_practice, lesson_recite}
  Tham chiếu: docs/client/required-context-contract.md
"""
import json
import os
import urllib.error
import urllib.request

import pytest

RAG_URL = os.environ.get("RAG_URL", "").rstrip("/")
TIMEOUT = float(os.environ.get("RAG_TIMEOUT", "30"))

CARD_TIERS = {"lesson_card", "lesson_practice", "lesson_recite"}

# Bài có thật trong pilot Văn 9 CTST tập 2 (docs/pilot/TEST_GUIDE.md). Override
# qua ENV nếu chạy trên corpus/môn khác.
LESSON_TITLE = os.environ.get("RAG_TEST_LESSON", "Sông Đáy")
PROFILE_BASE = {
    "lop": int(os.environ.get("RAG_TEST_LOP", "9")),
    "bo_sach": os.environ.get("RAG_TEST_BO_SACH", "CTST"),
    "subject": os.environ.get("RAG_TEST_SUBJECT", "ngu_van"),
    "tap": int(os.environ.get("RAG_TEST_TAP", "2")),
}
# Trang đã biết map về một bài (TEST_GUIDE: trang 130 = Sông Đáy, CTST t2).
KNOWN_PAGE = int(os.environ.get("RAG_TEST_TRANG", "130"))


# ── skip guard: chỉ chạy khi có server và /retrieve sống ──────────────────────
def _server_reachable() -> bool:
    if not RAG_URL:
        return False
    try:
        body = json.dumps({"query": "ping", "user_profile": {}}).encode()
        req = urllib.request.Request(
            RAG_URL + "/retrieve", data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_reachable(),
    reason="Set RAG_URL tới một server /retrieve (canary, KHÔNG prod) để chạy. "
           "Mặc định skip — test chỉ là stub đặc tả.",
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _retrieve(query: str, profile: dict) -> dict:
    body = json.dumps({"query": query, "user_profile": profile}).encode()
    req = urllib.request.Request(
        RAG_URL + "/retrieve", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _tier(resp: dict) -> str:
    return ((resp.get("intent") or {}).get("tier")) or "none"


def _work(resp: dict) -> str:
    return ((resp.get("intent") or {}).get("work_name")) or ""


def _norm(x: str) -> str:
    import unicodedata
    x = (x or "").replace("đ", "d").replace("Đ", "D")
    x = unicodedata.normalize("NFD", x)
    return "".join(c for c in x if unicodedata.category(c) != "Mn").lower().strip()


# ── 1. Payload ĐỦ context -> tier lesson_card (đường anchored) ─────────────────
def test_full_context_yields_lesson_card_tier():
    """current_lesson + scope đầy đủ -> phải neo vào bài (CARD_TIERS)."""
    profile = {**PROFILE_BASE, "current_lesson": LESSON_TITLE}
    resp = _retrieve("giảng cho em bài này với", profile)
    assert _tier(resp) in CARD_TIERS, (
        f"đủ context (current_lesson={LESSON_TITLE!r}) phải vào CARD_TIERS, "
        f"got tier={_tier(resp)!r}"
    )
    assert _norm(_work(resp)) == _norm(LESSON_TITLE), (
        f"phải neo đúng bài: got work_name={_work(resp)!r} exp {LESSON_TITLE!r}"
    )


# ── 2. Payload {} (degraded) -> KHÔNG được tạo thẻ giảng cho câu mơ hồ ─────────
def test_empty_profile_ambiguous_query_is_not_lesson_card():
    """user_profile={} + câu mơ hồ "bài này" -> KHÔNG neo (degraded).

    Không có current_lesson/trang/scope -> "bài này" vô định -> phải từ chối
    thay vì đoán đại một bài. Đây là behavior degraded mong đợi
    (docs/client/degraded-mode-behavior.md §2).
    """
    resp = _retrieve("giảng cho em bài này với", {})
    assert _tier(resp) not in CARD_TIERS, (
        f"profile rỗng + câu mơ hồ KHÔNG được tạo thẻ giảng (đoán bừa), "
        f"got tier={_tier(resp)!r} work={_work(resp)!r}"
    )


# ── 3. Ánh xạ volume->tap, page->trang đúng ───────────────────────────────────
def test_page_in_profile_maps_to_trang_and_anchors():
    """trang (= client page) trong profile -> neo theo trang.

    TEST_GUIDE: trang 130 (CTST t2) = Sông Đáy. tap đi kèm để không trùng tập.
    """
    profile = {**PROFILE_BASE, "trang": KNOWN_PAGE}  # 'trang' = ánh xạ của client 'page'
    resp = _retrieve("giảng bài này cho tớ", profile)
    assert _tier(resp) in CARD_TIERS, (
        f"trang={KNOWN_PAGE} trong profile phải neo (CARD_TIERS), "
        f"got tier={_tier(resp)!r}"
    )
    assert _norm(_work(resp)) == _norm(LESSON_TITLE), (
        f"trang {KNOWN_PAGE} phải map đúng bài {LESSON_TITLE!r}, got {_work(resp)!r}"
    )


def test_volume_tap_separates_page_collision():
    """tap (= client volume) phải tách trang trùng giữa tập 1 và tập 2.

    Cùng số trang ở t1 vs t2 KHÔNG được ra cùng một bài. Nếu corpus test chỉ có
    1 tập (KNOWN tap), test này tự xác nhận tap được tôn trọng: đổi tap sang
    tập không tồn tại -> KHÔNG được neo nhầm về bài của tap đúng.
    """
    same_tap = {**PROFILE_BASE, "trang": KNOWN_PAGE}
    other = dict(PROFILE_BASE)
    other["tap"] = 1 if PROFILE_BASE["tap"] != 1 else 2
    other["trang"] = KNOWN_PAGE

    r_same = _retrieve("giảng bài này", same_tap)
    r_other = _retrieve("giảng bài này", other)

    # Nếu cả hai đều neo, KHÔNG được ra cùng một work_name (đó là trùng tập).
    if _tier(r_same) in CARD_TIERS and _tier(r_other) in CARD_TIERS:
        assert _norm(_work(r_same)) != _norm(_work(r_other)), (
            "tap phải tách trang trùng tập: trang giống nhau ở tap khác nhau "
            f"không được ra cùng bài (got {_work(r_same)!r} cả hai tap)"
        )
    # Trường hợp lành mạnh khác: tap sai không tồn tại -> not anchored là OK.


# ── 4. Guard sanity: out-of-book vẫn từ chối ở mọi mode ───────────────────────
def test_out_of_book_named_work_is_refused():
    """Tên bài KHÔNG thuộc sách -> KHÔNG tạo thẻ (guard), kể cả đủ scope."""
    resp = _retrieve("giảng bài Lặng lẽ Sa Pa cho em", dict(PROFILE_BASE))
    assert _tier(resp) not in CARD_TIERS, (
        f"bài ngoài sách phải bị từ chối, got tier={_tier(resp)!r} work={_work(resp)!r}"
    )
