# SCALE ĐA MÔN + STRESS-TEST 973 CASE — companion Lesson Card (2026-06-14)

> Mở rộng companion từ 2 quyển pilot (Văn 9, Toán 6 CTST) ra **đa môn/đa lớp** bằng generic driver, rồi stress-test 973 case đa dạng. Canary :8889 (prod :8888 chưa đụng).

## Đã scale (Neo4j edu, actor `<SUBJECT>_PILOT_2026_06`)
- **23 quyển / 721 :Lesson / 6 môn** (đang tăng — campaign chạy nền): Toán (6 quyển), KHTN (4), Lịch sử (4), Địa lí (4), GDCD (4), Ngữ văn (1 pilot). Bộ CTST + đang thêm KNTT/CD.
- **Generic driver** `build_book_generic.py` / `run_campaign.py`: tự suy manifest từ DB (Bài N + work_name + tap-signal "Tập 1/2" + trang trích từ text), Gemma synth theory theo **5 loại-môn** (literature/math/science/social/civic), ingest :Lesson + theory(BGE) + practice_json + trang range. Idempotent (skip quyển đã build).

## Stress-test 973 case (megatest.py — deterministic, Gemma-free, no subagent)
Template đa persona × dimension × guard cho mọi quyển: current_lesson, trang(+tap), name-in-query, **typo/teen (gõ sai/không dấu)**, practice, recite(Văn), + adversarial (chitchat, off-topic, **bài ngoài sách**, trang ngoài sách, bẫy từ "trang phục"/năm).

| Dimension | Pass | | Dimension | Pass |
|---|---|---|---|---|
| current_lesson | 97.8% | | guard_offtopic | 100% |
| **typo/teen** | ~98% | | guard_oob_trang | 100% |
| name_query | 99.2% | | guard_trap | 100% |
| practice | 97.8% | | guard_chitchat | 97.1% |
| trang_query | ~96% | | **guard_out_of_book** | **63.8%** ⚠️ |
| recite | 100% | | | |
| **TỔNG: anchor 98.2% · mode 95.3% · guard 91.0% · cruft 0** | | | | |

→ **Đường anchored (production: thiết bị gửi current_lesson/trang+tap) ≈ 98% + typo-robust + 0 cruft + P95<300ms = KHẢ DỤNG PRODUCTION.**

## Bug phát hiện & ĐÃ fix (nhờ test kỹ + cảnh báo "trùng tập 1/2")
1. **Văn generic-driver tạo bài TRÙNG + rác** (titles chủ-đề + biến-thể "Siêu ngắn"/"Ngắn nhất"/"Thực hành Tiếng Việt") → **xoá 3 quyển Văn rác (6/7/8), loại Văn khỏi campaign**. Văn/Tiếng Việt cần builder CURATE TAY (như pilot Văn 9). Concept-subjects titles sạch → driver chạy tốt.
2. **Rác "trang N"** (toán 7/8/9: parser bắt nhầm title → lesson tên "trang 34") → gây khớp nhầm ("trang 999" ⊃ "trang 99"). **Fix: xoá + patch parser skip `^trang \d+$`.**
3. **"(trang X,Y)" trong tên** (toán tiểu học 4/5) → current_lesson "Phân số" không khớp "Phân số (trang 42)". **Fix: strip "(trang…)" + recompute work_name_norm chuẩn (NFD fold); patch parser.**
4. **tập 1/tập 2 trùng trang** (sách reset số trang) → "trang 30" mơ hồ giữa 2 tập. **Companion scope `tap_no`; thiết bị PHẢI gửi tap** → test gửi tap thì trang 100%.
5. **guard_out_of_book leak** (hỏi "tích phân"/"số phức"/"Nhớ rừng" ngoài sách → content-vec ép card) → **fix nâng floor `bs>=0.52→0.60` + margin 0.03→0.04**: out-of-book 34.8%→63.8%, chitchat 87.9%→97.1%, cruft vẫn 0. Backup canary `.bak_pre_oobfix_2026_06_14`.

## Còn lại (honest)
- **guard_out_of_book 63.8%**: hỏi bài ngoài sách vẫn leak ~36% (content-vec bắt bài gần nhất). Production che bằng current_lesson (thiết bị gửi bài đang học). Cải thiện thêm: chặn theo danh mục bài hợp lệ / phân loại intent off-book.
- **Văn/Tiếng Việt**: cần builder curate tay (chưa làm) — generic driver không bóc sạch titles literature.
- Campaign đang build nốt KNTT/CD (parser đã sạch); quyển lớn (toán 4/5/7/8/9) ~25-30'/quyển.

## Hạ tầng tái dùng
- `rag_edu/scripts/schema_v3_2026_06/`: build_book_generic.py (1 quyển), backtest_book.py (500-case/quyển). Server /tmp: run_campaign.py (campaign loop), run_cases.py (chấm), megatest.py (stress-test deterministic), validate_all.py (per-book test).
- Launch campaign: `bash /tmp/start_campaign.sh` (nohup, skip built). Canary: `bash /tmp/start_canary.sh`.
- ⚠️ Server tải nặng (campaign BGE + Gemma + omnivoice + vllm + canary) → test concurrent chậm + đôi lúc OOM/255 blip; megatest deterministic chịu tải tốt hơn workflow đa-agent (workflow bị session-limit).
