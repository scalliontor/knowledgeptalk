# PILOT 2 — Bạn-đồng-hành Toán 6 CTST tập 2 (trang-style, 2026-06-14)

> Port mô hình companion "Lesson Card" (đã làm cho Ngữ văn 9) sang **Toán 6 Chân trời sáng tạo TẬP 2** — chạy **canary :8889** (prod :8888 KHÔNG đụng). Động lực: [../audit/rag_subject_audit_2026_06_14.md](../audit/rag_subject_audit_2026_06_14.md) chứng minh Tier A nền trả SAI bài 9/10 + rác VietJack cho câu khái niệm Toán.

## Đã build (Neo4j edu, actor `TOAN_PILOT_2026_06`)
- **24 `:Lesson`** = trọn tập 2 (5 chương): Phân số (7) · Số thập phân (5) · Tính đối xứng (3) · Hình học phẳng (7) · Xác suất (2). Mỗi Lesson: `subject_code='toan', grade=6, bo_sach='CTST', tap_no=2, lesson_no, chuong, work_name(+_norm), trang_from, trang_to, practice_json`.
- **24 theory `:KnowledgeChunk`** (`content_type='theory'`, BGE-m3 embedded 1024d) — **Gemma synth** (định nghĩa + kiến thức chính + công thức + ví dụ + lưu ý + câu hỏi gợi mở). Sạch, KHÔNG rác VietJack. Toán K-6 = kiến thức chuẩn → Gemma ít bịa (đã verify tay phân số/so sánh/góc/tỉ số% — đúng hết, kể cả 3 practice So-sánh-phân-số).
- **Practice**: mỗi bài 3 câu {câu hỏi + gợi ý + đáp án ẩn} lưu `l.practice_json` (mode `guided_practice`).
- **TRANG**: trích từ chính text VietJack ("trang N Tập 2") → trang_from; trang_to = boundary bài kế (sort theo trang toàn tập). **Phủ liền mạch trang 7→106, không hở** (sạch hơn cả sitemap dùng cho Văn).
- Tập 2 grounded bằng tín hiệu "Tập 1/Tập 2" trong text (không đoán).

## Code companion (rag_server_canary.py — KHÔNG prod)
- Companion `query_lesson_card` **generic theo môn** (không cần code riêng cho Toán). Đã thêm:
  - **`subject_code` scope** vào match chính + content-vector (chống va trang Toán↔Văn cùng grade+book+tap). Backward-compat: subject NULL → khớp mọi môn (Văn không đổi).
  - **Nới content-vec gate**: `bs>=0.46 AND (margin>=0.03 OR bs>=0.52)` — vì các bài Toán cùng chương na ná nhau (top1≈top2) khiến gate Văn cũ loại nhầm → rớt về Tier A rác.
- Backups: `.bak_pre_toansubj_2026_06_14`, `.bak_pre_cvgate_2026_06_14`.

## Kết quả test (15 ca, canary)
| Chiều | Kết quả |
|---|---|
| Neo theo trang (13→So sánh phân số, 85→Góc, 100→Phép thử nghiệm) | ✅ đúng bài |
| Neo theo trang trong profile (19→Phép nhân/chia phân số) | ✅ |
| Neo theo current_lesson ("So sánh phân số") | ✅ |
| Content-vector (hỗn số/góc/tỉ số%/trung điểm/xác suất là gì) | ✅ card sạch |
| Practice mode ("cho vài bài luyện tập") | ✅ guided_practice |
| Guard chitchat | ✅ không bịa card |
| No-regress Văn (Sông Đáy) | ✅ vẫn chạy |
| **Anchor accuracy (đúng bài / guard đúng)** | **15/15** |
| **Strict (đúng cả mode)** | **12/15** |
| **Cruft VietJack trên card companion** | **0/15** (trước: Tier A 9/10 dính rác) |

## TRƯỚC vs SAU (cùng câu, cùng profile l6/CTST/toan)
| Query | Tier A nền (trước) | Companion (sau) |
|---|---|---|
| phân số là gì | ❌ "Bài 2 Các phép tính **số thập phân**" + rác | ✅ card phân-số sạch (Hỗn số*) |
| tỉ số phần trăm là gì | ❌ rác | ✅ "Tỉ số và tỉ số phần trăm" |
| trang 13 | (không có companion) | ✅ "So sánh phân số" |
| góc là gì | ❌ | ✅ "Góc" |

## Giới hạn còn lại (honest)
- **Bare concept không neo** ("phân số là gì" → "Hỗn số" thay vì bài định nghĩa Bài 1): các bài cùng chương embed na ná (top1=0.655 vs top2=0.645) → content-vec chọn chưa chuẩn bài foundational. **Vẫn là card đúng-chương, sạch** (không còn rác). Production thiết bị gửi `current_lesson`/`trang` → chính xác tuyệt đối. = đúng class giới hạn "content-only" của Văn.
- **Mode lệch**: "...tính sao", "...học bài gì" → ra đúng bài nhưng mode luyện-tập thay vì giảng (intent classifier). 2/15.
- Chưa làm: tập 1 Toán 6; văn bản HĐTH&TN; chương khác lớp.

## Tái dùng để scale
- Synth: `/tmp/toan_synth.py` (Gemma, manifest 24 bài, trích trang từ DB) → `/tmp/toan_cards.json`.
- Ingest: `/tmp/toan_ingest.py` (BGE embed + :Lesson + practice_json + trang range).
- Patch code: `/tmp/patch_toan_subj.py`. Test: `/tmp/toan_companion_test.py`.
- Quy trình lặp được cho mọi (môn, lớp, bộ sách): grounded tập từ text → manifest bài → Gemma synth theory+practice → trích trang từ DB → ingest → (subject scope đã có sẵn).
