# KG Schema v3 — Tổ chức dữ liệu Toán & Văn cho RAG đồng hành

> **Ngày**: 2026-06-03 · **Trạng thái**: DECIDED (Claude quyết theo yêu cầu anh) · chưa migrate
> **Căn cứ**: [research 2026-06-03](../research/2026-06-03_graph-rag-companion.md) (17 patterns confirmed) + audit data thực Neo4j edu (`data_audit_toan_van_2026_06_03` trong memory)
> **Ràng buộc bất biến**: chunk **document-level** (không split nhỏ) · structured-first (Cypher exact) · KHÔNG model mới · companion mode (không phải Q&A mở)

---

## 0. Nguyên tắc nền (áp cho mọi môn)

| # | Nguyên tắc | Nguồn |
|---|---|---|
| P1 | **Concept là node TYPE riêng**, không phải property của chunk | research F1 |
| P2 | Nối chunk↔concept bằng **explicit edge** `(:KnowledgeChunk)-[:COVERS]->(:Concept)` | research F2 |
| P3 | **Retrieval-size ≠ extraction-size**: giữ chunk doc-level để retrieve; nếu auto-extract concept thì chạy trên span nhỏ | research F7 |
| P4 | **Prereq seed từ curriculum** (GDPT 2018), KHÔNG từ telemetry | research F5 + refuted |
| P5 | Giữ **doc-level chunk nguyên vẹn** — granularity điều hướng qua metadata + edge, không chia nhỏ | feedback_product_vision |
| P6 | 1 concept → **nhiều typed variant** (chunk khác nhau cùng COVERS 1 concept) | research F6 |

**3 lớp tách biệt** (chung mọi môn):

```
Lớp 1 — DOCUMENT   :KnowledgeChunk (doc-level, ~3-15K chars) + embedding BGE-m3   ← retrieval unit
Lớp 2 — CONCEPT    :Concept (skill/khái niệm)                                      ← backbone
Lớp 3 — STRUCTURE  (:Concept)-[:PREREQ]->(:Concept)  +  hierarchy lesson/work      ← companion traversal

Nối:  (:KnowledgeChunk)-[:COVERS]->(:Concept)
```

---

## 1. TOÁN — lesson + exercise + concept + prereq DAG

### 1.1 Vấn đề as-is (audit data thực)

- 1 chunk ≈ 1 Bài, ~3-4K chars, bài tập inline. **98% orphan** (32/2090 link hierarchy).
- `problem_type` = **math strand** (6 strand: số học, đại số, hình học, phân số, thống kê, xác suất) + **72% `general`/`practice` residue**.
- **⭐ F1 collision = 2 bug trộn** (vd G9 CTST `lesson_no=2` có 20 title):
  - **Bug A**: "Bài 2 **trang 103**..." = *bài tập số 2 trang 103* → parser nhầm thành `lesson_no=2`. Phải là `exercise_no=2` + `trang_no=103`.
  - **Bug B**: "Bài 2: Hình nón" vs "Bài 2: Căn bậc ba" = lesson thật nhưng **mỗi chương restart số** → `chuong` RỖNG nên không phân biệt.

### 1.2 Schema v3 Toán

```cypher
// ── Lớp DOCUMENT (giữ nguyên doc-level, fix metadata) ──
(:KnowledgeChunk {
   uid, text, embedding,                       // giữ nguyên
   subject_code: 'toan', grade, bo_sach, production_ready,
   document_id, sequence_number,               // Parent-Doc pattern (giữ)
   title,
   // ── FIX F1 ──
   content_class,   // 'vietjack_lesson' | 'vietjack_exercise' | 'lgh_solution'
   chuong,          // NEW: số chương — disambiguate cross-chapter lesson_no (Bug B)
   lesson_no,       // FIX: CHỈ set cho lesson thật; NULL cho trang bài tập
   exercise_no,     // FIX: set cho trang "Bài N trang M" (Bug A)
   trang_no, tap_no,
   concept_id       // denormalize để Cypher filter nhanh (đồng bộ với edge COVERS)
})

// ── Lớp CONCEPT (NEW) ──
(:Concept {
   concept_id: 'toan.so_hoc.tap_hop',          // {môn}.{strand}.{slug}
   name: 'Tập hợp', name_norm: 'tap hop',       // norm = unidecode fold (khớp I4)
   subject: 'toan',
   strand: 'so_hoc',                            // 6 strand từ problem_type
   grade_introduced: 6,
   source: 'gdpt2018'                           // 'gdpt2018' | 'llm_openie' | 'manual'
})

// ── Edges ──
(:KnowledgeChunk)-[:COVERS]->(:Concept)                  // P2
(:Concept)-[:PREREQ {seed:'gdpt2018'}]->(:Concept)       // P4 — DAG, math only
(:KnowledgeChunk)-[:SOLVES]->(:KnowledgeChunk)           // exercise-page → lesson-page (cùng lesson_key)
```

### 1.3 F1 fix — quy tắc phân loại (Python pass, regex title)

```
content_class:
  title ~ "Toán {lớp} {bộ} Bài {K}: {tên}"          → vietjack_lesson   ; lesson_no=K, exercise_no=NULL
  title ~ "Bài {K} trang {M} Toán {lớp} Tập {T}"     → vietjack_exercise ; exercise_no=K, trang_no=M, lesson_no=NULL
  uid STARTS WITH 'lgh' / có 'Giải ... trang'         → lgh_solution     ; trang_no=M
chuong: regex "Chương {C}" trong title HOẶC suy từ thứ tự document_id; lấp Bug B
concept_id: map strand (problem_type) + tên bài → concept slug
```

### 1.4 Concept backbone Toán — HYBRID (research F4)

- **Strand free**: 6 strand từ `problem_type` → 6 `:Concept` cấp strand ngay.
- **Hand-seed prereq DAG nhỏ** từ GDPT 2018 strand structure (~30-50 concept/lớp đầu), vd:
  ```
  (phan_so@G4-5) -[:PREREQ]-> (ti_so@G6) -[:PREREQ]-> (ti_le_thuc@G7)
  (tap_hop@G6) -[:PREREQ]-> (so_tu_nhien@G6)
  ```
- **Auto-extract concept mịn SAU** bằng LLM router trên span per-section (F7), nếu cần — không bắt buộc Phase 1.

### 1.5 Retrieval Toán (Cypher exact, fix collision)

```cypher
// "Bài 5 Toán 6" + user_profile{grade:6, bo_sach:'KNTT'}
MATCH (k:KnowledgeChunk)
WHERE k.subject_code='toan' AND k.grade=$g AND k.bo_sach=$bo
  AND k.production_ready=true
  AND k.content_class='vietjack_lesson'      // ⭐ ưu tiên lesson, không lẫn exercise page
  AND k.lesson_no=$ln
  AND ($chuong IS NULL OR k.chuong=$chuong)  // disambiguate Bug B nếu query có chương
RETURN k ORDER BY coalesce(k.chunk_index,999) LIMIT 3;
// Nếu hỏi "trang 103": thêm path content_class='vietjack_exercise' AND trang_no=103
```

---

## 2. VĂN — work + section + variant + recitation (KHÔNG prereq DAG)

### 2.1 Vấn đề as-is (audit data thực)

- 1 chunk ≈ 1 (section × variant), ~7-15K chars. **Well-linked** vào Unit hierarchy (4080 link).
- `section_type` (9 bucket) + `variant` (4 bucket) **đã phân loại tốt**.
- `lesson_no` chỉ 13% — Văn tổ chức theo **chủ đề + tác phẩm**, không đánh số bài.
- **`work_name` chưa có** — nằm ở title-slot `Soạn bài ⟨X⟩ SGK Ngữ văn...` nhưng **trộn work thật + skill-section** ("Bếp lửa" vs "Thực hành tiếng Việt trang 86"). V2 fail vì Cypher regex.
- **RecitationSegment (151) + LiteratureText (110) đã tách sẵn** ✅ (research F6 đúng).

### 2.2 Quyết định khác Toán

> **Văn KHÔNG có PREREQ DAG.** Evidence lattice/mastery chỉ validate cho domain cấu trúc cao (toán/lý). Văn concept structure lỏng (research F8 + open Q1). Văn dùng **Work/Theme/Section/Variant** thuần, không prereq.

### 2.3 Schema v3 Văn

```cypher
// ── Lớp DOCUMENT (giữ nguyên, thêm work_name) ──
(:KnowledgeChunk {
   subject_code:'ngu_van', grade, bo_sach, production_ready,
   section_type,    // soan_bai | thuc_hanh_tieng_viet | viet | noi_nghe |
                    // tri_thuc_ngu_van | cung_co | on_tap | trac_nghiem | lgh_qa_solution
   variant,         // standard | chi_tiet | sieu_ngan | ngan_nhat
   work_name,       // NEW: CHỈ khi section_type='soan_bai' VÀ slot là tác phẩm thật
   tap_no, trang_no,
   allow_full_recitation, allow_snippet, rights_status   // rights (giữ)
})

// ── Lớp WORK/THEME (NEW) — "concept" của Văn ──
(:LiteraryWork {
   work_id, name: 'Bếp lửa', name_norm: 'bep lua',
   author: 'Bằng Việt', the_loai: 'tho',
   grade, source: 'extracted'
})

// ── Recitation tách riêng (đã có, thêm rights) ──
(:LiteratureText {grade, series, title, full_text, allow_full_recitation, license})
(:RecitationSegment {segment_text, order})

// ── Edges ──
(:KnowledgeChunk)-[:ABOUT_WORK]->(:LiteraryWork)     // analytical content về 1 tác phẩm
(:LiteratureText)-[:VERBATIM_OF]->(:LiteraryWork)    // bản nguyên văn để đọc
(:LiteratureText)-[:HAS_SEGMENT]->(:RecitationSegment)
// nhiều variant (chi_tiet/sieu_ngan) cùng ABOUT_WORK 1 LiteraryWork → P6, không nhân bản
```

### 2.4 work_name extraction — fix V2 (Python, gated)

```python
# Regex slot giữa "Soạn bài" và "SGK"
m = re.search(r'Soạn bài\s+(.+?)\s+SGK', title)
slot = m.group(1) if m else None
# GATE: chỉ là work khi section_type='soan_bai' VÀ slot KHÔNG phải skill-phrase
SKILL_PHRASES = ['thực hành tiếng việt','viết','nói và nghe','nói nghe',
                 'ôn tập','củng cố','tri thức ngữ văn','thảo luận']
is_work = (section_type=='soan_bai'
           and slot and not any(p in slot.lower() for p in SKILL_PHRASES))
work_name = slot if is_work else None
```
→ Lý do V1.E fail: Cypher `BETWEEN`/regex extraction khó; **phải Python pass**, gate bằng `section_type` (field này đã tách skill type sẵn — đó là giá trị của nó).

### 2.5 Variant — companion chọn độ sâu (research F6)

Học sinh có thể xin "giải thích kỹ" (chi_tiet) hoặc "tóm tắt nhanh" (sieu_ngan). Cùng 1 `work_name` + `section_type`, retrieval lọc thêm `variant` theo intent — **không nhân bản concept**, chỉ chọn chunk khác.

### 2.6 Retrieval Văn

```cypher
// "Soạn bài Bếp lửa phần đọc hiểu" + profile{grade:9,bo_sach:'KNTT'}
MATCH (k:KnowledgeChunk)
WHERE k.subject_code='ngu_van' AND k.grade=$g AND k.bo_sach=$bo
  AND k.production_ready=true
  AND k.work_name = $work        // hoặc (:KnowledgeChunk)-[:ABOUT_WORK]->(:LiteraryWork{name:$work})
  AND ($section IS NULL OR k.section_type=$section)
  AND ($variant IS NULL OR k.variant=$variant)
RETURN k LIMIT 3;
// "Đọc thuộc bài thơ Bếp lửa" → recitation path: LiteratureText{allow_full_recitation:true}
```

---

## 3. COMPANION layer (Phase sau — thiết kế sẵn)

> **Phase 1 chỉ cần `CURRENT_LESSON` position** (research open Q4). Mastery vector = Phase 3, cần telemetry chưa có.

```cypher
(:Student {student_id, grade, bo_sach})              // từ device provisioning
(:Session {session_id, started_at})
(:Student)-[:HAS_SESSION]->(:Session)
(:Student)-[:CURRENT_LESSON]->(:KnowledgeChunk)      // Phase 1: vị trí hiện tại
(:Session)-[:STUDIED {at}]->(:KnowledgeChunk)        // lịch sử

// Phase 3 (khi có telemetry) — research F8/F9, MATH-first:
(:Student)-[:MASTERY {score, updated_at, source:'llm_dialogue_judge'}]->(:Concept)
```

**"Bài 5 build trên Bài 3 em đã học"** — traverse (Toán only, vì có PREREQ DAG):
```cypher
MATCH (cur:KnowledgeChunk {lesson_no:5})-[:COVERS]->(c:Concept)
MATCH (pre:Concept)-[:PREREQ]->(c)
MATCH (preLesson:KnowledgeChunk)-[:COVERS]->(pre)
OPTIONAL MATCH (s:Student)-[:STUDIED|CURRENT_LESSON]->(preLesson)
RETURN pre.name, preLesson.lesson_no, (s IS NOT NULL) AS da_hoc;
```

> ⚠️ Mastery infer ngầm (LLM judge dialogue correctness) **chỉ validate cho Toán** (research F9). Văn để sau / bỏ.

---

## 4. So sánh Toán vs Văn (quyết định cuối)

| Chiều | **TOÁN** | **VĂN** |
|---|---|---|
| Đơn vị doc | 1 Bài (lesson) + exercise pages | 1 (work × section × variant) |
| Concept node | Math strand + khái niệm (Q-matrix) | LiteraryWork / Theme (mỏng hơn) |
| Key edge | `COVERS` + `SOLVES` + `PREREQ` | `ABOUT_WORK` + `VERBATIM_OF` |
| **PREREQ DAG** | ✅ CÓ (seed GDPT 2018) | ❌ KHÔNG (lattice math-only) |
| Recitation | — | ✅ RecitationSegment/LiteratureText (rights-gated) |
| Variant | (ít) | ✅ chi_tiet/sieu_ngan/ngan_nhat |
| Retrieval key | grade+bo_sach+**chuong**+lesson_no | grade+bo_sach+**work_name**+section_type+variant |
| Mastery (Phase 3) | ✅ defensible (KT validate) | ⚠️ speculative |
| Fix nóng nhất | **F1**: tách lesson/exercise + thêm chuong | **work_name** extract gated |

---

## 5. Migration plan (theo thứ tự rủi ro thấp → cao)

### Toán (làm trước — research migration order)
1. **T-A** Python pass: phân `content_class` (lesson/exercise/lgh) + fix `lesson_no`/`exercise_no` + extract `chuong`. *(fix Bug A+B)*
2. **T-B** Tạo 6 `:Concept` strand + `COVERS` edge từ `problem_type`.
3. **T-C** Patch `rag_server` retrieval: ưu tiên `content_class='vietjack_lesson'` + dùng `chuong`. *(fix F1 collision live)*
4. **T-D** Hand-seed PREREQ DAG ~30 concept G6 KNTT (GDPT 2018).
5. **T-E** Test lại G6-9 (kỳ vọng F1 collision 25-50% → 80%+).

### Văn (sau Toán)
6. **V-A** Python pass: extract `work_name` gated by `section_type` (fix V2).
7. **V-B** Tạo `:LiteraryWork` + `ABOUT_WORK` edge; nối `LiteratureText -[:VERBATIM_OF]-> :LiteraryWork`.
8. **V-C** Patch retrieval: filter `work_name` + `section_type` + `variant`.

### Companion (Phase sau)
9. `:Student`/`:Session`/`CURRENT_LESSON` khi wire device profile.
10. Mastery (Toán only) khi có telemetry dialogue.

---

## 6. Cái KHÔNG làm (refuted — research)

- ❌ Học prereq từ telemetry adjacency matrix → **seed từ curriculum**.
- ❌ LLM auto-tag KC mỗi dialogue turn → đừng giả định free.
- ❌ Coi CCSS/GDPT đã encode validated builds-on → chỉ **candidate seed**, người duyệt.
- ❌ Nhúng concept làm property thay node → **node riêng + edge**.
- ❌ Split chunk nhỏ hơn doc-level → giữ doc-level, điều hướng qua metadata+edge.
- ❌ Văn PREREQ/mastery vội → evidence math-only.

---

Liên quan: [research evidence base](../research/2026-06-03_graph-rag-companion.md) · memory `data_audit_toan_van_2026_06_03` · `deep_research_per_subject_2026_05_31` · [[feedback-product-vision]]
