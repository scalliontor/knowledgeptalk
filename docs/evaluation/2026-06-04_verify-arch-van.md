# Verify kiến trúc RAG Văn — eval G6-9 (work + section + variant)

> **Ngày**: 2026-06-04 · Harness `/tmp/eval_van_full.py` — emulate work-exact retrieval (schema v3 V-C) qua Neo4j bolt, KHÔNG cần canary. 4 loại query/lớp. Kết quả `/tmp/eval_van_results.json`.

## Bối cảnh
Văn tổ chức theo **tác phẩm × section × variant** (khác Toán = lesson+exercise). Test trên 593 chunk soạn bài có `work_name` (G6-9: 72-98 tác phẩm/lớp). 4 loại học sinh hỏi:
- **tác phẩm**: "soạn bài Bếp lửa", "giảng {tác phẩm}"
- **section**: "{work} phần đọc hiểu / viết / nói nghe / thực hành tiếng Việt"
- **variant**: "{work} siêu ngắn / chi tiết / ngắn nhất"
- **nội dung**: "{work} nói về gì", "phân tích {work}"

## Hit-rate grade × type

| Lớp | tác phẩm | section | variant | nội dung | OVERALL |
|---|---|---|---|---|---|
| G6 | 100% | 100% | 72.8% | 100% | 93.2% |
| G7 | 100% | 100% | 64.1% | 100% | 93.8% |
| G8 | 100% | 100% | — | 100% | 100% |
| G9 | 100% | 100% | — | 100% | 100% |

**Theo loại**: tác phẩm **100%** (500/500) · section **100%** (500/500) · nội dung **100%** (500/500) · variant **69.5%** (141/203). **Cross-grade leak = 0/1703** ✅. **OVERALL 96.4%** (1641/1703).

## Kết luận
- ✅ **work-exact retrieval xuất sắc** — tác phẩm/section/nội dung đều 100%. Companion "soạn bài X phần đọc hiểu" trả đúng.
- ✅ schema v3 Văn validate: work_name + section_type + variant filter chính xác.
- ⚠️ **variant 69.5%** — khi học sinh xin bản "siêu ngắn/chi tiết" cụ thể nhưng tác phẩm đó không có đúng variant trong bộ sách đó → miss. **Diagnostic xác nhận: khi variant TỒN TẠI thì retrieval đúng 0/80 miss** — 30% miss là request variant không có. **Fix (cho V-C code): variant-fallback** — nếu lọc `variant=$var` rỗng thì bỏ filter, trả bản có sẵn của tác phẩm (companion vẫn đưa được nội dung, chỉ khác độ sâu). Là hành vi sản phẩm đúng.
- G8/G9 variant=0 cases: các tác phẩm soạn bài đó chỉ có bản `standard` (chi_tiet/sieu_ngan tập trung ở G6-7) — data reality, không phải lỗi.

## Yêu cầu kỹ thuật rút ra (cho V-C code thật)
- **`work_name_norm`** (folded, đ→d) bắt buộc trên chunk để match (như concept `name_norm`). Đã backfill 593 chunks + 418 LiteraryWork. Bug ban đầu: match work cố định của anchor → 3.2%; sửa thành match `k.work_name_norm` per-chunk → 96.4%.
- Section keyword detect: đọc hiểu→soan_bai, viết→viet, nói và nghe→noi_nghe, thực hành tiếng Việt→thuc_hanh_tieng_viet.
- Variant: siêu ngắn→sieu_ngan, chi tiết→chi_tiet, ngắn nhất→ngan_nhat. Nên fallback nếu variant yêu cầu không có.

## BỔ SUNG — Văn theo trang / theo bài (structured-exact)

Câu hỏi: Văn có theo bài/trang được như Toán không? → **CÓ**, dùng chung path structured-exact (title CONTAINS "trang N"/"bài N"). Harness `/tmp/eval_van_struct.py`, grounded trên chunk có trang_no/lesson_no.

| Loại | Hit | Anchor coverage |
|---|---|---|
| theo_trang | **96.0%** (480/500) | 983 chunks (21%) |
| theo_bài | **100%** (500/500) | 534 chunks (12%) |

**Leak = 0.**

### Khác biệt Văn vs Toán (quan trọng)
- Coverage thấp hơn nhiều: Văn tổ chức theo **tác phẩm/skill**, không đánh số bài/trang đều như Toán. trang chỉ ở Thực hành tiếng Việt + vài soạn bài (21%); "Bài N" chỉ 7% title / lesson_no 12%.
- **"Bài N" trong Văn = CHỦ ĐỀ chứa 2-3 tác phẩm** (1:nhiều), không phải 1 bài cụ thể như Toán (1:1). → theo_bài Văn là **entry point thô**; companion nên narrow tiếp bằng work_name + section.
- → Văn hỗ trợ **2 cách vào**: (1) structured trang/bài khi học sinh nhắc số (96-100%), (2) work/section — cách tự nhiên (100%). Cách (2) là chính cho Văn.

### Tổng kết Văn đầy đủ (6 loại)
theo_trang 96% · theo_bài 100% · tác phẩm 100% · section 100% · nội dung 100% · variant 69.5% · **leak 0**.

## PROBE — query tự nhiên đa dạng (đọc cả bài / phân tích cảm nghĩ / giải thích / tóm tắt)

Harness `/tmp/probe_van_v2.py` — auto-resolve grade+book của tác phẩm rồi sinh query tự nhiên (test robust phrasing, không phải template cứng). **12/12 hit.**

| Query tự nhiên | Tier | OK |
|---|---|---|
| "đọc cả bài thơ Bếp lửa cho em nghe" | RECITATION (verbatim) | ✓ |
| "đọc thuộc Nam quốc sơn hà" / "ngâm Phò giá về kinh" | RECITATION | ✓ |
| "phân tích cảm nghĩ về Bếp lửa" | work-exact → soạn bài | ✓ |
| "giải thích ý nghĩa nhan đề Bếp lửa" | work-exact | ✓ |
| "hình ảnh người bà trong Bếp lửa" | work-exact | ✓ |
| "cảm nhận nhân vật Dế Mèn trong Bài học đường đời đầu tiên" | work-exact | ✓ |
| "Lão Hạc của ai và nói về gì" | work-exact | ✓ |
| "viết đoạn văn nêu cảm nghĩ về Quê hương" | work-exact+section | ✓ |
| "cảm hứng chủ đạo của Tây Tiến" | work-exact | ✓ |
| "tóm tắt truyện Lặng lẽ Sa Pa" | work-exact | ✓ |

### Kết luận probe
1. **Recitation intent** ("đọc cả bài/đọc thuộc/ngâm/đọc diễn cảm") → route đúng sang LiteratureText verbatim, tách khỏi analytical.
2. **Work-match phrasing-agnostic**: phân tích / giải thích / cảm nghĩ / tóm tắt / hình ảnh nhân vật / nhan đề... đều resolve đúng tác phẩm trong câu → trả soạn bài (doc-level chunk chứa đủ mọi khía cạnh phân tích).
3. **Không leak chéo bộ sách**: query với grade/book sai → retrieval TỪ CHỐI đúng (Bếp lửa không ở G8 CD → miss đúng, vì nó ở G8 KNTT). Đây là hành vi mong muốn.
4. Validate sức mạnh **chunk doc-level**: 1 soạn-bài chunk = toàn bộ phân tích tác phẩm → mọi câu hỏi về tác phẩm đó đều trúng cùng 1 chunk.

Liên quan: [kg-schema-v3.md](../design/kg-schema-v3.md) · [verify Toán](2026-06-03_verify-arch-toan.md)
