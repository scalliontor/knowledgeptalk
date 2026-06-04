# Verify kiến trúc RAG Toán — test sinh bởi Gemma4

> **Ngày**: 2026-06-03 · **Harness**: `verify_arch_toan.py` (Gemma4 sinh query giọng học sinh, chạy live qua canary :8889 `/retrieve`)
> **Mục tiêu**: verify kiến trúc với 4 loại học sinh hỏi: **theo trang / theo bài / hỏi kiến thức / cách giải**
> **Phương pháp**: 13 anchor THẬT từ Neo4j (lesson + page) → Gemma4 sinh 29 query tự nhiên → chấm có trả đúng nội dung không.

## Kết quả tổng (29 case)

| Loại hỏi | n | nonempty | Tier A | concept/trang đúng | Verdict |
|---|---:|---:|---:|---:|---|
| **theo_trang** (trang N) | 5 | 5 | **5/5** | trang 5/5 | ✅ XUẤT SẮC |
| **theo_bai** có số "bài N" | 2 | 2 | **2/2** | concept 2/2 | ✅ TỐT |
| **theo_bai** chỉ nói chủ đề (không số) | 6 | 6 | 0/6 | concept 0/6 | ❌ HỎNG |
| **hỏi kiến thức** ("X là gì") | 8 | 8 | 0/8 | concept 2/8 | ❌ YẾU |
| **cách giải** ("cách làm X") | 8 | 8 | 0/8 | concept 1/8 | ❌ YẾU |

## Phát hiện cốt lõi

### ✅ Tier A structured = xuất sắc KHI query có anchor rõ
- **"Giải trang 42 Toán 9 KNTT"** → Tier A, đúng trang. 5/5 perfect.
- **"giảng bài 22 đại lượng tỉ lệ thuận"** → Tier A, đúng bài (ctx 7444 chars, concept match).
- Anchor `trang N` hoặc `bài N` (số explicit) trong query → `parse_structured_query` bắt được → Cypher exact → đúng.

### ❌ GAP nghiêm trọng: học sinh nói theo CHỦ ĐỀ (không số) → rơi vector → SAI
Đây là cách học sinh nói tự nhiên nhất khi đang học companion mode:

> Q (G6 KNTT): *"Cô ơi, phần 'Tập hợp' này em chưa hiểu, giảng lại giúp em"*
> → Tier A KHÔNG fire (không có "bài N") → **Qdrant vector fallback**
> → trả về: **"Lớp 5 | KNTT — bài tập thống kê (chiều cao, cân nặng)"**
> → **SAI lớp (5≠6) + SAI chủ đề (thống kê≠tập hợp) + leak cross-grade**

Cùng pattern cho mọi query topic-only (Hàm số y=ax+b, tâm đối xứng, góc-cạnh-góc...). Vector fuzz trả nội dung lệch hoàn toàn.

### ❌ Bug phụ: Qdrant fallback KHÔNG hard-filter grade+bo_sach
Query G6 trả content G5. user_profile `{lop:6}` bị bỏ qua ở path Qdrant.

## Kết luận → validate schema v3

Test này **chứng minh empirically** đúng hướng schema v3:

1. **Concept layer (T-B/T-B2) + retrieval patch (T-C) là CẦN THIẾT** — chính xác cho case "nói theo chủ đề không số". Khi học sinh nói "giảng Tập hợp", hệ thống phải làm **concept-name exact lookup** (grade+book+concept) → trả đúng G6 KNTT Tập hợp, KHÔNG vector-fuzz sang G5.
2. **Tier A trang/bài-số đã solid** — không cần đụng path đó.
3. **Qdrant fallback cần hard grade+bo_sach filter** — bug độc lập, fix trong T-C.

## Before-measurement (baseline trước T-C)

Đây là baseline trước khi patch retrieval. Sau T-B2 (concept mịn) + T-C (retrieval concept lookup + hard grade filter), re-run harness này, kỳ vọng:
- theo_bai topic-only: 0/6 → 5/6+
- kien_thuc/cach_giai: 2-3/16 → 12/16+
- Hết cross-grade leak.

## Lưu ý phương pháp
- `concept_match` = fold-substring khái niệm trong context (strict — có thể undercount nhẹ khi tên dài/nhiều ký hiệu như "y = ax + b"). Nhưng các case fail đã verify trả NỘI DUNG KHÁC (vd G5 thống kê), không phải scorer miss.
- Gemma4 (`gemma-4`, max_len 16384) sinh query rất tự nhiên giọng học sinh ("Cô ơi...", "em chưa hiểu lắm ạ").
- Harness: `/tmp/verify_arch_toan.py` trên server; kết quả `/tmp/verify_arch_results.json`.

---

## UPDATE — sau T-A/T-B/T-B2/T-C (cùng ngày)

Đã thực thi schema-v3 Toán + patch retrieval canary, rồi verify lại.

### Data layer (verified Cypher)
- **T-A**: 565 exercise pages tách khỏi lesson (`content_class=vietjack_exercise`, lesson_no→exercise_no, backup `_f1_backup_lesson_no`). Collision G9 CTST `lesson_no=2`: **20→10 titles**.
- **T-B**: 6 strand `:Concept` + 609 COVERS.
- **T-B2**: 677 fine `:Concept` từ lesson title; **987/1003 (98%) lesson có concept** + 987 COVERS.

### Code layer (rag_server_canary.py, py_compile OK)
- **T-C** patch: (1) **grade propagation fix** — `parsed["lop"]→intent["grade"]` (retrieval fns đọc `grade`, parsed dùng `lop` → đây là root cross-grade leak); (2) **NEW `query_concept_exact()` Tier-A path** — query topic-only (không bài/trang) → exact lookup theo Concept name trong (grade+book).
- **T-C2**: cải tiến concept match partial (word-overlap ≥2 từ ≥4 ký tự) thay full-name CONTAINS — bắt "định lí Thalès" cho concept "Định lí Thalès trong tam giác".

### Verified live (khi canary ổn định)
| Query topic-only | Trước (baseline) | Sau T-C |
|---|---|---|
| "phần Tập hợp này em chưa hiểu" (G6 KNTT) | Qdrant → **G5 thống kê** (leak) | ✅ `A_concept` → **Toán 6 KNTT Bài 1: Tập hợp** |
| "cách giải phương trình bậc hai" (G9 CTST) | fallback sai | ✅ `A_concept` → **Bài 2: Phương trình bậc hai một ẩn** |
| grade leak G6→G5 | có | ✅ hết (giờ filter đúng grade) |

→ **Cơ chế concept-exact ĐÚNG như thiết kế** — fix gap topic-only.

### ⚠️ Blocker ops (không phải lỗi code)
Canary :8889 **không stay up ổn định** qua remote launch (shared GPU L40S + ssh drop session dài + screen flaky trên box). Instance ổn định từng phục vụ đủ test; các restart sau race nhau. → Full T-E regression (29-case re-run) + verify T-C2 partial-match cần canary chạy ổn định 1 lần (tốt nhất user start trong session trực tiếp). Prod :8888 (ESP32) KHÔNG đụng — vẫn healthy.

Backups: `rag_server_canary.py.bak_pre_TC_2026_06_03`, `.bak_pre_TC2_2026_06_03`.

---

## COMPREHENSIVE EVAL — G1-9 × ~500 câu (3250 cases, Cypher-emulated)

> Harness `/tmp/eval_toan_full.py` — emulate retrieval (structured-exact + concept-exact T-C/C2) trực tiếp qua Neo4j bolt, KHÔNG cần canary. 4 loại query/lớp, templated từ anchor thật. Kết quả `/tmp/eval_toan_full_results.json`.

### Hit-rate grade × type

| Lớp | theo_bài | theo_trang | kiến thức | cách giải | OVERALL |
|---|---|---|---|---|---|
| G1 | — | — | 44.0% | 48.0% | 46.0% |
| G2 | — | — | 77.6% | 76.0% | 76.8% |
| G3 | — | — | 81.6% | 85.6% | 83.6% |
| G4 | — | — | 75.2% | 73.6% | 74.4% |
| G5 | — | — | 60.0% | 65.6% | 62.8% |
| G6 | 100% | 100% | 70.4% | 70.4% | 85.2% |
| G7 | 100% | 100% | 88.8% | 85.6% | 93.6% |
| G8 | 100% | 100% | 72.8% | 77.6% | 87.6% |
| G9 | 100% | 73.6% | 86.4% | 88.0% | 87.0% |

**Theo loại**: theo_bài **100%** (500/500) · theo_trang **93.4%** (467/500) · kiến thức **73.0%** (821/1125) · cách giải **74.5%** (838/1125). **Cross-grade leak = 0/3250** ✅. **OVERALL 80.8%** (2626/3250).

### Kết luận
- ✅ **theo_bài 100%** — F1 fix + structured-exact. **Cross-grade leak triệt tiêu** (grade-propagation fix) — bug nặng nhất baseline.
- ✅ G6-9 (data đủ): 85-94%.
- ⚠️ **G1-5 thiếu lesson_no/trang_no** (chỉ 250 câu/lớp, chỉ test concept) — DATA GAP: G1-5 crawl chưa backfill số bài/trang. Cần backfill để (a) đủ 500/lớp, (b) bật theo_bài/trang tiểu học.
- ⚠️ **kiến thức/cách giải 73-74%** — concept-exact miss ~26% (tên concept dài/sibling). Cải thiện: vector-rerank trong grade+book scope, hoặc concept alias.
- ⚠️ theo_trang G9 73.6% — nhiều chunk share trang; cần tie-break.

> Lưu ý: emulated (Cypher) = logic retrieval thật; còn parse intent của Gemma router (subject misclassify) chưa tính. Live canary T-E sẽ xác nhận thêm phần router.

---

## EVAL v2 — sau backfill G1-5 (4500 cases, đủ 500/lớp G1-9)

Backfill `lesson_no`/`trang_no`/`tap_no` cho G1-5 từ title ("Bài N: ... (trang P Tập T)") — 540 chunks. Tiểu học đánh số bài liên tục → chỉ 1 collision cell. Script `/tmp/backfill_g15.py`. Cũng fix emulation trang path = `title CONTAINS "trang N"` (khớp code thật query_structured_exact).

| Lớp | theo_bài | theo_trang | kiến thức | cách giải | OVERALL |
|---|---|---|---|---|---|
| G1 | 100% | 100% | 58.4% | 49.6% | 77.0% |
| G2 | 100% | 93.6% | 77.6% | 86.4% | 89.4% |
| G3 | 100% | 97.6% | 84.8% | 83.2% | 91.4% |
| G4 | 100% | 98.4% | 72.8% | 68.0% | 84.8% |
| G5 | 100% | 100% | 56.8% | 58.4% | 78.8% |
| G6 | 100% | 100% | 76.8% | 71.2% | 87.0% |
| G7 | 100% | 100% | 88.0% | 91.2% | 94.8% |
| G8 | 100% | 100% | 88.8% | 71.2% | 90.0% |
| G9 | 100% | 100% | 89.6% | 85.6% | 93.8% |

**Theo loại**: theo_bài **100%** (1125/1125) · theo_trang **98.8%** (1112/1125) · kiến thức **77.1%** (867/1125) · cách giải **73.9%** (831/1125). **Cross-grade leak = 0/4500** ✅. **OVERALL 87.4%** (3935/4500). (v1 80.8% → v2 87.4% nhờ backfill G1-5.)

### Còn lại
- **kiến thức/cách giải 74-77%** — concept-exact partial match. Cải thiện: vector-rerank trong grade+book scope (fallback khi concept miss), concept alias/synonym, hoặc dùng BGE-m3 trên lesson chunks của cell.
- G1/G5 concept thấp (49-58%) — data concept tiểu học thưa/đơn giản.
- theo_trang G2 93.6% — vài trang share nhiều bài; tie-break.

---

## EVAL v3 — fix đ→d trên Concept.name_norm

Diagnostic phát hiện: ~26% concept miss vì **`name_norm` của Concept (tạo ở T-B2) KHÔNG map đ→d** (chỉ strip dấu) → concept có đ ("Định lí Viète"→"đinh li", "Đa thức", "Điểm. Đường thẳng", "Biểu đồ") không khớp query đã fold đ→d. Fix: re-normalize 672 Concept `name_norm` với đ→d (`/tmp/fix_concept_norm.py`). **Áp cho cả live retrieval** (canary T-C/C2 đọc name_norm).

| Lớp | theo_bài | theo_trang | kiến thức | cách giải | OVERALL |
|---|---|---|---|---|---|
| G1 | 100% | 100% | 67.2% | 62.4% | 82.4% |
| G2 | 100% | 93.6% | 84.0% | 89.6% | 91.8% |
| G3 | 100% | 97.6% | 90.4% | 85.6% | 93.4% |
| G4 | 100% | 98.4% | 76.0% | 72.8% | 86.8% |
| G5 | 100% | 100% | 65.6% | 67.2% | 83.2% |
| G6 | 100% | 100% | 81.6% | 81.6% | 90.8% |
| G7 | 100% | 100% | 88.0% | 92.8% | 95.2% |
| G8 | 100% | 100% | 78.4% | 78.4% | 89.2% |
| G9 | 100% | 100% | 95.2% | 97.6% | 98.2% |

**Theo loại**: theo_bài 100% · theo_trang 98.8% · kiến thức **80.7%** (↑từ 77.1) · cách giải **80.9%** (↑từ 73.9). leak=0. **OVERALL 90.1%** (↑từ 87.4). 

Còn lại ~19% concept miss = **sibling-confusion** ("Phân thức đại số"→"Đơn thức nhiều biến", "Cung và dây"→"Độ dài cung tròn") — word-overlap chọn concept liên quan. Cần vector-rerank (BGE-m3) trong grade+book scope để phân biệt — chờ canary.

Liên quan: [../design/kg-schema-v3.md](../design/kg-schema-v3.md) · [../research/2026-06-03_graph-rag-companion.md](../research/2026-06-03_graph-rag-companion.md)
