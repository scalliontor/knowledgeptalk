# Tiếng Việt G1-5 migration — schema v3 (môn cuối K-9)

> **Ngày**: 2026-06-04 · Harness `/tmp/tv_migrate.py` + `/tmp/eval_tv.py`. Actor `TV_MIGRATE_2026_06_04`, reversible.

## Đặc thù: hybrid Toán + Văn
TV tiểu học vừa có `Bài N` + `trang M` (structured như Toán G1-5) vừa có **bài đọc/tác phẩm** ("Sinh nhật của voi con", "Nhà rông", "Hai Bà Trưng") + section (tập đọc / nghe-viết / luyện từ và câu / viết) như Văn.

## Migration (3842 prod chunks G1-5)
- `content_class` trên **3842**: tv_lesson / tv_vbt / tv_assessment.
- `lesson_no` trên **2421** (extract "Bài N:"), `trang_no` trên **2193** ("trang M").
- **1988 `:Concept`** (reading-text/topic, name_norm đ→d) + **2345 COVERS**. Lọc generic-exact ("Luyện tập", "Ôn tập", "Đọc mở rộng", "Tiết N") — giữ topic cụ thể ("Dấu gạch ngang", "Hai Bà Trưng", "Luyện tập về tính từ").

## Eval
| Loại | Template | Natural (Gemma4) |
|---|---|---|
| theo_bài | 100% (400/400) | 75% (9/12) |
| theo_trang | 97% (388/400) | — |
| kiến thức/concept | 100% (400/400) | 33% (4/12) |
| **OVERALL** | **99%** | — |

**Cross-grade leak = 0.**

## Kết luận (xác nhận pattern toàn hệ)
- **Structured (bài/trang) robust** kể cả natural (75-97%). Template 99% → core companion vững.
- **Concept natural 33%** — học sinh **mô tả nội dung/paraphrase thay vì gọi tên bài** ("đoạn nói về việc ước có phép lạ", "chữ t với th", "câu đơn với câu ghép"). Đây là điểm yếu concept đồng nhất mọi môn (Toán 33%, TV 33%) → cần **vector-rerank BGE** (semantic) cho query mô tả/paraphrase. Template (đặt sẵn tên) che mất.
- TV phonics (G1 "chữ t/th") khó match bằng concept-name — cần facet riêng (phonics_pattern) hoặc vector.

Liên quan: [natural-language eval](2026-06-04_natural-language-eval.md) · [kg-schema-v3](../design/kg-schema-v3.md)
