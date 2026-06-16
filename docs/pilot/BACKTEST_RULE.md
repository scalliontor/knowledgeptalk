# QUY TẮC BACKTEST 500-CÂU / QUYỂN SÁCH — companion Lesson Card

> Cách đánh giá **khả dụng production** của companion cho MỘT quyển sách bất kỳ. Script: [`../../rag_edu/scripts/schema_v3_2026_06/backtest_book.py`](../../rag_edu/scripts/schema_v3_2026_06/backtest_book.py). Chạy: `python backtest_book.py <subject> <grade> <book> <tap> <N> <port>`.

## Nguyên lý
1. **Ground truth từ DB**: pull mọi `:Lesson` của quyển (work_name, trang_from/to, có recite?, practice_json, theory text).
2. **Sinh ~500 câu giọng học sinh (Gemma, temp 0.7)** — paraphrase đa dạng, grounded theo nội dung thật, gán nhãn `(expected_work, expected_mode, dimension)`. Phân bổ theo **chiều neo × intent × adversarial**:
   - Chiều neo (cách thiết bị/HS cấp ngữ cảnh): `current_lesson` (profile) · `trang_query` (số trang trong câu) · `trang_profile` (thiết bị gửi trang) · `name_query` (nêu tên bài) · `content_only` (mô tả nội dung, KHÔNG neo — ca khó nhất).
   - Intent/mode: giảng (`lesson_card`) · luyện tập (`lesson_practice`) · đọc thuộc (`lesson_recite`).
   - ~15% adversarial guard: chitchat, off-topic môn, trang ngoài sách (999), bẫy từ ("trang phục"), bẫy năm (1945), **bài ngoài sách** (tên tác phẩm không thuộc quyển).
3. **Chạy /retrieve thật** trên canary, đo mỗi request. Chấm:
   - **Anchor accuracy** = intent.work_name == expected_work (neo đúng bài).
   - **Mode accuracy** = anchor đúng VÀ tier đúng intent.
   - **Guard accuracy** = câu adversarial KHÔNG bị ép ra card.
   - **Cruft** = rác VietJack lọt vào card (phải = 0).
   - **Latency** P50/P95/P99 (gate voice: P95 < 1.5s).
4. Output JSON + bảng theo từng chiều + sample fails → `/tmp/backtest_<subject>_<grade>_<book>_t<tap>.json`.

## Tiêu chí PASS production (đề xuất)
| Metric | Ngưỡng | Lý do |
|---|---|---|
| Anchor (current_lesson/trang/name) | ≥ 95% | đây là cách thiết bị thực tế gửi ngữ cảnh |
| Cruft trên card | = 0 | tuyệt đối không lộ nguồn/rác |
| Guard (chitchat/off-topic/trap/oob-trang) | ≥ 95% | không bịa khi không nên |
| Guard out-of-book | ≥ 90% | không ép card cho bài ngoài sách |
| Latency P95 | < 1500ms | đồng hành thoại |
| content_only | (không gate) | fallback khi KHÔNG có neo; prod luôn gửi anchor |

## Kết quả 2 quyển pilot (canary :8889, 2026-06-14)
| | Văn 9 CTST t2 (495 ca) | Toán 6 CTST t2 (500 ca) |
|---|---|---|
| Latency P50 / P95 / P99 | 20 / 171 / 189 ms | 20 / 275 / 296 ms |
| Cruft trên card | **0** | **0** |
| Anchor — current_lesson | 100% | 100% |
| Anchor — trang_query / trang_profile | 98.1% / 100% | 96.7% / 100% |
| Anchor — name_query | 100% | 98.6% |
| Anchor — content_only (không neo) | 29.5% | 62.7% |
| Guard (chitchat/offtopic/trap/oob-trang) | 100% | 100% |
| Guard out-of-book | 66.7% ⚠️ | 100% |
| **PASS production?** | ✅ đường anchored | ✅ đường anchored |

## Đọc kết quả
- **Đường thiết-bị-gửi-anchor (current_lesson/trang/tên) = 96-100% + 0 cruft + P95<300ms → KHẢ DỤNG PRODUCTION.** Đây là cách dùng thật (Kid-mentor gửi current_lesson/trang).
- **`content_only` thấp** = câu mô tả mơ hồ KHÔNG neo (vd "bài này nói về gì") — bản chất không xác định được bài nếu thiếu anchor; trả none thường là ĐÚNG. Không phải lỗi production vì thiết bị luôn gửi anchor.
- **Văn `guard_out_of_book` 66.7%**: hỏi bài KHÔNG thuộc quyển (Nhớ rừng…) thi thoảng bị content-vec ép ra card (do clause `bs>=0.52` thêm cho cluster bài na ná). Toán 100% (tên văn xa nội dung toán). → cần siết: nâng floor content-vec không-margin (0.52→~0.58) HOẶC chặn khi câu nêu tên-bài-không-khớp-sách. (chưa làm)

## Điều kiện tiên quyết khi promote prod
1. Client (Kid-mentor) PHẢI gửi `current_lesson` và/hoặc `trang` trong `user_profile`.
2. Giữ endpoint `/v2/moderation/expand-topic` khi merge code companion vào prod.
3. Deploy theo script+nohup (RUNBOOK §2), backup + rollback.
4. (nên) siết guard out-of-book trước khi mở cho môn Văn.
