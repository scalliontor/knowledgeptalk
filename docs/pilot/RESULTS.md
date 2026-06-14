# PILOT RESULTS — Bạn-đồng-hành Ngữ văn 9 CTST tập 2 (2026-06-14)

> Companion "Lesson Card" — pilot 13 bài đọc trên **canary :8889** (prod :8888 chưa đụng). Vận hành/launch: [../RUNBOOK.md](../RUNBOOK.md). Dùng thử: [TEST_GUIDE.md](TEST_GUIDE.md).

## Companion làm được gì — 3 chế độ/bài, neo nhiều cách
1 bài học (`:Lesson`, 13 bài) phục vụ 3 ý định, **tự nhận diện theo nghĩa** (không phụ thuộc từ khoá cứng):
- 📖 **Giảng** (`tier=lesson_card`) — tác giả/hoàn cảnh/thể loại/bố cục/nội dung/giá trị + câu hỏi gợi mở (grounded VietJack TGTP).
- ✍️ **Luyện tập** (`tier=lesson_practice`) — 55 câu {câu hỏi SGK + gợi ý sư phạm + đáp án ẩn}, `delivery_mode=guided_practice`.
- 🎤 **Đọc thuộc** (`tier=lesson_recite`) — nguyên văn 5 thơ (Sông Đáy, Tì bà hành, Hai chữ nước nhà, Cái roi tre, Mùa xuân chín; nguồn Thi Viện, validated).

**Cách NEO bài** (theo độ ưu tiên): `current_lesson` (thiết bị gửi) · tên bài trong câu · số `trang` (trong câu hoặc profile) · mô tả nội dung (content-vector). Scoped `lớp+bộ sách+TẬP+trang`.

## Kết quả acceptance test (53 ca, canary)
| Chiều | Kết quả | Ghi chú |
|---|---|---|
| Intent recite paraphrase | 6/6 | "đọc full/đọc bài/ngâm/đọc lên/nghe trọn bài" → recite |
| Intent practice paraphrase | 5/5 | "mấy câu ôn/luyện tập/tự kiểm tra" → practice |
| Intent explain paraphrase | 4/4 | "giảng/phân tích/bố cục" → giảng |
| Named (nói vòng có tên bài) | 4/4 | |
| Trang trong câu (+bẫy "trang phục"/năm/out-range) | 6/6 | |
| Trang trong profile | 3/3 | thiết bị gửi trang |
| Content-only (mô tả nội dung, KHÔNG neo) | 14/20 (70%) | content-vector + margin guard |
| Guard chitchat/off-topic | 4/4 | 0 false-positive |
| Tap-scope (tap1 không trả bài tập2) | 1/1 | |
| **Tổng** | **47/53 = 88%** | điểm trừ duy nhất = content-only (ca khó) |

**Kịch bản thực tế (thiết bị gửi `current_lesson`/`trang`): ~100%** mọi cách hỏi.

## Cơ chế chính (rag_server_canary.py — `query_lesson_card`)
- **Intent = EMBEDDING classifier** (BGE, so nghĩa query với anchor phrases {recite/practice/explain}, margin 0.035; regex giữ fast-path). → robust paraphrase, không cần Gemma (+~40ms).
- **Content-vector tier**: không neo tên/trang → BGE cosine trên 13 theory embeddings, gate **margin top1−top2 ≥ 0.03** (chống chitchat khớp-mờ).
- **Tap-scope**: `parse_structured_query` đọc `profile.trang`; companion match `($tap IS NULL OR l.tap_no=$tap)`. Đã backfill `tap_no` g9 CTST ngu_van.
- **Recite verbatim**: `_is_recite`/classifier + `[(l)-[:HAS_RECITE]->(lt)|lt.full_text]`.

## Giới hạn còn lại (honest)
- **Trang-range chưa chuẩn tuyệt đối**: suy từ start-pages (vietjack.me sitemap) → đã cap CHẶT để KHÔNG trả sai bài, đổi lại vài trang-giữa của bài nhiều trang → None. Fix triệt để cần **mục lục tập-2 sạch** (web lẫn lớp 11-12; PPCT chỉ có thứ tự theo tiết). → production neo chính bằng `current_lesson`; trang là phụ.
- **Content-only 70%**: mô tả quá mơ hồ/ngắn vẫn trượt; tăng được bằng embed thêm nguyên-văn.
- **Coverage**: mới 13 bài đọc chính; văn bản phụ (Đọc mở rộng/Viết/Nói nghe) chưa dựng Lesson.

## Hạ tầng tái dùng (để scale)
- Page-method: `../../rag_edu/scripts/schema_v3_2026_06/build_pagemap_vietjackme.py` (vietjack.me sitemap → trang).
- Pipeline pilot: crawl TGTP→theory · Gemma synth practice (gợi ý) · agent crawl recite (Thi Viện) · backfill tap.
- Test: [van9_ctst_t2_testcases.json](van9_ctst_t2_testcases.json), /tmp acceptance.py + para_retest.py (trên server).
