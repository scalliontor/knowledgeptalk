# Migration Xã hội (Lịch sử / Địa lí / LS&ĐL / GDCD) → schema v3

> **Ngày**: 2026-06-04 · **Actor**: `XAHOI_AGENT_2026_06_04` (mọi mutation reversible theo tag) · **Neo4j edu** `bolt://localhost:7688`
> **Phạm vi**: `subject_code IN ['lich_su','dia_li','lich_su_dia_li','gdcd']`, `production_ready=true` · KHÔNG đụng môn khác, KHÔNG flip production_ready, KHÔNG DELETE, KHÔNG sửa rag_server.
> **Theo**: [kg-schema-v3.md](../design/kg-schema-v3.md) (P1/P2 concept node + COVERS) · pattern Toán/Văn. Xã hội = concept-as-lesson-topic, **KHÔNG PREREQ DAG** (research: lattice math-only).

---

## 1. AUDIT (read-only, trước mọi write)

### Prod chunks per subject × grade × bộ sách

| subject_code | prod total | phân bố |
|---|---:|---|
| **lich_su** | 353 | G6: KNTT 67, CTST 42, CD 35, none 15 · G7: 60 · G8: KNTT 20, CTST 22, CD 18, none 4 · G9: 70 |
| **dia_li** | 315 | G6: KNTT 61, CTST 48, CD 39 · G7: 63 · G8: 39 · G9: 65 |
| **gdcd** | 132 | G6-9 đều ~10-13/bộ × 3 bộ |
| **lich_su_dia_li** | 24 | G6: KNTT 6, CTST 6, CD 7 · G7: none 5 |

Data tập trung **G6-9** (không có tiểu học). `lich_su_dia_li` rất thưa (24) và phần lớn không gắn bộ sách.

### 3 họ data_source (quyết định content_class)

| data_source | n | bản chất | → content_class |
|---|---:|---|---|
| `vietjack_legacy` | 659 | bài giảng "… **Bài N: ‹chủ đề›**" sạch, có lesson_no | `vietjack_lesson` |
| `lesson_guide_multi_label` | 141 | giải SBT/bài tập ("Giải SBT … bài N … trang M") | `lgh_solution` |
| `lgh_leaf` | 24 | mảnh Q&A đứng lẻ (`bo_sach='none'`, lesson_no=NULL) | `lgh_qa` |

### Fill-rate property (trước backfill)

| field | lich_su | dia_li | gdcd | lich_su_dia_li |
|---|---|---|---|---|
| `lesson_no` | 317/353 | 312/315 | 130/132 | 15/24 |
| `trang_no` | 0 | 0 | 0 | 15/24 |
| `content_class` | 0 | 0 | 0 | 0 |
| `concept_id` | 0 | 0 | 0 | 0 |

- **lesson_no đã tốt sẵn** (parse từ "Bài N:" của crawler trước) — Xã hội KHÔNG bị bug F1 kiểu Toán.
- **`exercise_no` = chuỗi rỗng `''`** trên toàn bộ vietjack/gdcd (659 chunk) — field rác, KHÔNG phải số bài tập thật. Bỏ qua.
- **trang_no gần như trống**: chỉ `lich_su_dia_li` có "trang N" trong title (SBT). vietjack lesson **không mang số trang** → `theo_trang` không route được (data gap, không phải lỗi logic).

### Title regex
- vietjack lesson: `Bài\s+(\d+)\s*:\s*(.+)$` → lesson_no + **concept = chủ đề bài**. Coverage: lich_su 295/353, dia_li 247/315, gdcd 130/132.
- SBT trang: `trang\s*(\d+)` (chỉ lich_su_dia_li, 15 chunk).

### F1-style issues
- **KHÔNG có collision kiểu Toán.** "Collision" lesson_no chỉ là **bài giảng + bản giải SBT cùng lesson_no** (distinct_titles tối đa = 3) → đó là khác `content_class`, không phải parse sai. content_class tách 2 lớp này.
- **1 mislabel crawler** (flag, không sửa): `lich_su G6 CTST lesson_no=1` có chunk SBT title *"Giải Sách bài tập Lịch sử 6 bài 1- **Bài 6: Ai Cập cổ đại**"* — crawler gán `bài 1` nhưng nội dung là Bài 6. Lẻ tẻ, để lại + báo.
- **lgh_leaf 24 chunk** (`bo_sach='none'`, no lesson) — Q&A trắc nghiệm lẻ, không route được theo cấu trúc; là nguồn 0% của lich_su_dia_li G7-9.

---

## 2. BACKFILL (actor `XAHOI_AGENT_2026_06_04`, reversible)

Python pass, ONLY 4 subject_code, additive. Backup field bị ghi đè vào `_xahoi_backup_<field>`. KHÔNG đụng production_ready, KHÔNG delete.

| Mutation | n | ghi chú |
|---|---:|---|
| `content_class` set | **824** | vietjack_lesson 659 · lgh_solution 141 · lgh_qa 24 |
| `concept_name_xh` (từ "Bài N: ‹X›") | **621** | lich_su 255, dia_li 236, gdcd 130; lich_su_dia_li 0 (toàn SBT/Q&A) |
| `trang_no` (từ title "trang N") | **15** | chỉ lich_su_dia_li |
| `xahoi_actor` tag | **824** | toàn bộ prod chunk |

Verify sau write: content_class phủ 100% (824/824); concept phủ đúng các bộ vietjack.

---

## 3. CONCEPT NODES + COVERS (P1/P2)

`:Concept {concept_id:'‹subj›.‹slug›', name, name_norm, subject, grade_introduced, level:'fine', source:'lesson_title', created_actor}`. Dedup theo (subject, name_norm) — concept là **node TYPE riêng**, nối `(:KnowledgeChunk)-[:COVERS]->(:Concept)`. **KHÔNG PREREQ** (theo schema v3 Xã hội).

> ⚠️ `name_norm` map **đ→d TRƯỚC** rồi mới strip dấu (critical). Verified: "Đông"→"dong", "độc lập"→"doc lap", "Ấn Độ"→"an do".

| | lich_su | dia_li | gdcd | lich_su_dia_li | tổng |
|---|---:|---:|---:|---:|---:|
| Concept nodes | 176 | 177 | 53 | 0 | **421** |
| COVERS edges | | | | | **621** |

(gdcd ít concept hơn vì mỗi lớp ~10 bài, tên bài lặp giữa các bộ → dedup; lich_su_dia_li=0 vì không có vietjack lesson.)

---

## 4. EVAL (4625 case, Cypher-emulated retrieval, per subject)

Harness `/tmp/eval_xahoi.py` (adapt từ `/tmp/eval_toan_full.py`). ~500 query/lớp G6-9, 4 loại: **theo_bài** (lesson_no/title), **theo_trang** (title CONTAINS "trang N"), **kiến thức** ("X là gì"), **giải thích/nội dung**. Emulate structured-exact (grade+bo+lesson_no) + concept-exact (word-overlap name_norm ≥2 từ ≥4 ký tự HOẶC full-contains). Kết quả `/tmp/eval_xahoi_results.json`.

### Hit-rate grade × type (hit% (n))

**lich_su**
| Lớp | theo_bài | theo_trang | kiến thức | giải thích | OVERALL |
|---|---|---|---|---|---|
| G6 | 100.0 | — | 96.8 | 96.0 | 97.6% |
| G7 | 100.0 | — | 100.0 | 100.0 | 100.0% |
| G8 | 100.0 | — | 100.0 | 100.0 | 100.0% |
| G9 | 100.0 | — | 96.0 | 98.4 | 98.1% |

**dia_li**
| Lớp | theo_bài | theo_trang | kiến thức | giải thích | OVERALL |
|---|---|---|---|---|---|
| G6 | 100.0 | — | 96.0 | 98.4 | 98.1% |
| G7 | 100.0 | — | 100.0 | 100.0 | 100.0% |
| G8 | 100.0 | — | 93.6 | 96.8 | 96.8% |
| G9 | 100.0 | — | 96.8 | 96.0 | 97.6% |

**gdcd**
| Lớp | theo_bài | theo_trang | kiến thức | giải thích | OVERALL |
|---|---|---|---|---|---|
| G6 | 100.0 | — | 100.0 | 100.0 | 100.0% |
| G7 | 100.0 | — | 92.8 | 94.4 | 95.7% |
| G8 | 100.0 | — | 100.0 | 100.0 | 100.0% |
| G9 | 100.0 | — | 100.0 | 100.0 | 100.0% |

**lich_su_dia_li** (data rất thưa)
| Lớp | theo_bài | theo_trang | kiến thức | giải thích | OVERALL |
|---|---|---|---|---|---|
| G6 | — | 100.0 | — | — | 100.0% |
| G7 | — | — | — | — | 0.0% |
| G8 | — | — | — | — | 0.0% |
| G9 | — | — | — | — | 0.0% |

**CROSS-GRADE LEAK = 0 / 4625** ✅ (filter `toInteger(grade)=$g` + `bo_sach` cứng).

### Kết luận
- ✅ **theo_bài 100%** mọi lớp/môn có vietjack lesson — lesson_no sạch sẵn, structured-exact hoạt động.
- ✅ **kiến thức / giải thích 93-100%** — concept-exact (word-overlap name_norm) cực tốt cho Xã hội vì tên bài = câu mô tả dài, nhiều từ ≥4 ký tự, ít trùng sibling (khác Toán: tên ngắn/ký hiệu).
- ✅ **Zero cross-grade leak** — grade+bo filter cứng.
- ⚠️ ô `—` (theo_trang, lich_su_dia_li) = **không có anchor data**, không phải fail logic.

---

## 5. Gaps (top 3)

1. **`trang_no` trống cho vietjack lesson (659 chunk)** → query "trang N …" của Sử/Địa/GDCD không route được. Cần crawl/backfill số trang (title vietjack không mang). Hiện chỉ `lich_su_dia_li` SBT có trang.
2. **`lich_su_dia_li` G7-9 = 0%** (data sparsity): chỉ 24 prod chunk, đa số `lgh_leaf` Q&A lẻ `bo_sach='none'`, không lesson/concept → không có anchor structured. Cần crawl bài giảng vietjack cho môn tích hợp này; hoặc gán bộ sách + lesson cho lgh_leaf.
3. **Mislabel crawler lẻ tẻ** (vd lich_su G6 CTST ln=1 "Bài 6: Ai Cập cổ đại" gán nhầm bài 1) ở lớp SBT `lesson_guide_multi_label` — không sai về nội dung (vẫn retrieve được qua concept), nhưng `lesson_no` SBT không tin cậy 100%. Đã flag, KHÔNG sửa/demote (nội dung đúng, không phải SGK cũ).

### Knowledge-correctness
- Không phát hiện SGK cũ hay subject-mislabel nghiêm trọng → **không demote/quarantine chunk nào**. (Chỉ 1 lesson_no SBT lệch như trên, để lại.)

---

## 6. Reversibility
- Mọi chunk mutation: `xahoi_actor='XAHOI_AGENT_2026_06_04'`, field ghi đè backup ở `_xahoi_backup_*` (thực tế gần như không có ghi đè vì content_class/concept/trang trước đó NULL).
- Concept node + COVERS edge: `created_actor='XAHOI_AGENT_2026_06_04'`. Rollback = MATCH theo actor → remove property / DELETE node+edge (additive, an toàn).

Liên quan: [kg-schema-v3.md](../design/kg-schema-v3.md) · [graph-rag-companion research](../research/2026-06-03_graph-rag-companion.md) · [verify-arch-toan](2026-06-03_verify-arch-toan.md)
