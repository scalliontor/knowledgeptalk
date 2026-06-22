# Neo4j Schema v3 — tổng hợp cho Corpus / Data-Quality

> **Nguồn**: tổng hợp từ `docs/design/kg-schema-v3.md` (DECIDED 2026-06-03) + code thực `rag_edu/scripts/schema_v3_2026_06/build_book_generic.py`, `backfill_worknorm.py`, `diag_weak.py` (companion Lesson Card đang dùng).
> **Mục đích**: tham chiếu nhanh node/edge/property + **các field anchor** cho data-quality. **Không** mô tả runtime serve (runtime ở server `rag_server.py`/`rag_server_canary.py`, không ở repo này).
> **Lưu ý**: phần `:Lesson` (companion card) là lớp MỚI do builder dựng, nằm CHỒNG lên lớp `:KnowledgeChunk` gốc của schema-v3 design. Hai lớp cùng tồn tại trong Neo4j edu.

## 0. Hai lớp song song trong Neo4j edu

```
LỚP COMPANION (mới, builder Lesson Card)         LỚP NỀN (schema-v3 design, KnowledgeChunk)
  (:Lesson) ──HAS_THEORY──> (:KnowledgeChunk      ← retrieval unit doc-level + embedding BGE-m3
                              {theory, embedding})   (:Concept), (:LiteraryWork), (:LiteratureText)
            ──HAS_RECITE──> (:LiteratureText)        edges: COVERS / PREREQ / ABOUT_WORK / VERBATIM_OF
            ──HAS_PRACTICE-> (practice_json)
            ──COVERS──────> (:Concept)
```

- Companion path = anchor theo `:Lesson` (current_lesson / tên bài / trang+tập) → đọc `theory`/`recite`/`practice`.
- Khi không có :Lesson cho môn đó → rơi xuống lớp nền (Tier A concept + vector trên `:KnowledgeChunk`).

## 1. Node: `:Lesson` (companion card — lớp anchor chính)

Props (suy từ `build_book_generic.py` ingest + diag):

| Prop | Ý nghĩa | Dùng cho anchor? |
|---|---|---|
| `subject_code` | `'toan'`,`'ngu_van'`,`'khtn'`,`'lich_su'`,`'dia_li'`,`'gdcd'` | ✅ scope |
| `grade` | lớp 4–9 (lưu int; query coi cả int và string) | ✅ scope |
| `bo_sach` | `'CTST'` / `'KNTT'` / `'CD'` (book_set) | ✅ scope |
| `tap_no` | tập 1/2 hoặc NULL (1-tập). Suy từ tap-signal `text CONTAINS 'Tập 2'` | ✅ **chống trùng tập** |
| `work_name` | tên bài (vd "Tia X", "Khởi nghĩa Lam Sơn"). NFD (có dấu) | ✅ anchor tên bài |
| `work_name_norm` | **fold(work_name)** — đ→d + NFD strip dấu + lower | ✅ **match-key chính** |
| `lesson_no` | số "Bài N" parse từ title | ✅ anchor (Toán: cần `chuong` disambiguate) |
| `trang_from` / `trang_to` | range trang (trang_from từ regex `trang (\d+)` trong src; trang_to = trang_from của bài kế − 1, trong cùng tập) | ✅ anchor theo trang |
| `theory` | thẻ kiến thức synth (Gemma) — định nghĩa/nội dung chính | nội dung giảng |
| `practice_json` | 3 câu luyện {cau, cau_hoi, goi_y, dap_an} | mode luyện |

> **Anchor key thật** = `work_name_norm` (fold). Query KHÔNG được match `work_name` (NFD, có dấu) bằng `(?i)`/`startswith` → fail câm. Xem `vietnamese-normalization.md`.

## 2. Edges companion

```cypher
(:Lesson)-[:HAS_THEORY]->(:KnowledgeChunk {theory, embedding})   // thẻ kiến thức + vector BGE-m3
(:Lesson)-[:HAS_RECITE]->(:LiteratureText)                        // bản nguyên văn để đọc thuộc (Văn)
(:Lesson)-[:HAS_PRACTICE]->(practice payload)                     // 3 câu luyện (lưu cùng node/json)
(:Lesson)-[:COVERS]->(:Concept)                                   // map khái niệm (Toán/KHTN)
```

## 3. Lớp nền — `:KnowledgeChunk` (schema-v3 design)

Doc-level (~3–15K chars), **retrieval unit**, có `embedding` BGE-m3. Props chung + per-subject:

```cypher
(:KnowledgeChunk {
   uid, text, embedding, title,
   subject_code, grade, bo_sach, production_ready,   // scope + gate serve
   document_id, sequence_number,                     // Parent-Doc pattern
   trang_no, tap_no
})
```

### 3.1 Toán (lesson + exercise + concept)

```cypher
(:KnowledgeChunk {
   content_class,   // 'vietjack_lesson' | 'vietjack_exercise' | 'lgh_solution'
   chuong,          // số chương — disambiguate cross-chapter lesson_no (F1 Bug B)
   lesson_no,       // CHỈ set cho lesson thật; NULL cho trang bài tập
   exercise_no,     // set cho trang "Bài N trang M" (F1 Bug A)
   concept_id       // denormalize, đồng bộ edge COVERS
})
(:Concept {
   concept_id: 'toan.so_hoc.tap_hop',   // {môn}.{strand}.{slug}
   name, name_norm,                     // name_norm = fold(name) — match-key concept
   subject:'toan', strand,              // 6 strand (số học/đại số/hình học/phân số/thống kê/xác suất)
   grade_introduced, source:'gdpt2018', level    // level:'fine' cho concept mịn
})
(:KnowledgeChunk)-[:COVERS]->(:Concept)
(:Concept)-[:PREREQ {seed:'gdpt2018'}]->(:Concept)      // DAG, MATH-ONLY
(:KnowledgeChunk)-[:SOLVES]->(:KnowledgeChunk)          // exercise-page → lesson-page
```

> **F1 collision** (audit cũ): `lesson_no` bị parse nhầm từ "Bài 2 trang 103" (= exercise_no=2 + trang=103) và mỗi chương restart số → cần `content_class='vietjack_lesson'` + `chuong` để khử. `concept_retrieve` (diag_weak.py) match qua `c.name_norm` (`q CONTAINS c.name_norm` hoặc ≥2 từ ≥4 ký tự).

### 3.2 Văn (work + section + variant + recitation; KHÔNG prereq)

```cypher
(:KnowledgeChunk {
   section_type,   // soan_bai | thuc_hanh_tieng_viet | viet | noi_nghe | tri_thuc_ngu_van
                   //  | cung_co | on_tap | trac_nghiem | lgh_qa_solution
   variant,        // standard | chi_tiet | sieu_ngan | ngan_nhat
   work_name,      // CHỈ khi section_type='soan_bai' VÀ slot là tác phẩm thật (gated)
   work_name_norm, // fold(work_name) — backfill bởi backfill_worknorm.py
   allow_full_recitation, allow_snippet, rights_status
})
(:LiteraryWork { work_id, name, name_norm, author, the_loai, grade, source })
(:LiteratureText { grade, series, title, full_text, allow_full_recitation, license })
(:RecitationSegment { segment_text, order })
(:KnowledgeChunk)-[:ABOUT_WORK]->(:LiteraryWork)
(:LiteratureText)-[:VERBATIM_OF]->(:LiteraryWork)
(:LiteratureText)-[:HAS_SEGMENT]->(:RecitationSegment)
```

> **Văn KHÔNG có PREREQ DAG** (lattice/mastery chỉ defensible cho Toán). Variant cho phép companion chọn độ sâu (chi_tiet / sieu_ngan) cùng 1 work_name.

## 4. ⭐ Field dùng cho ANCHOR (tóm tắt — quan trọng nhất)

| Field | Trên node | Vai trò anchor | Lưu ý chuẩn hóa |
|---|---|---|---|
| `work_name` | :Lesson, :KnowledgeChunk(văn) | tên bài (hiển thị) | **NFD, có dấu** — KHÔNG match trực tiếp |
| `work_name_norm` | :Lesson, :KnowledgeChunk(văn), (=name_norm trên :Concept/:LiteraryWork) | **match-key chính** | = `fold()` = đ→d + NFD strip Mn + lower |
| `trang_from` / `trang_to` | :Lesson | anchor theo trang đang mở | phải đi cùng `tap_no` |
| `tap_no` | :Lesson, :KnowledgeChunk | chống trùng tập 1/2 | NULL = sách 1 tập |
| `subject_code` | mọi node | scope môn | enum cố định |
| `grade` | mọi node | scope lớp | query so cả int và `toString(grade)` |
| `bo_sach` | mọi node | scope bộ sách | `'CTST'`/`'KNTT'`/`'CD'` |
| `lesson_no` (+`chuong`) | :Lesson, :KnowledgeChunk(toán) | anchor "Bài N" | Toán cần `chuong` khử cross-chapter collision |
| `production_ready` | :KnowledgeChunk | gate serve | `coalesce(...,false)=true` |

**Thứ tự routing structured-first** (invariant canonical): `current_lesson` → `work_name_norm` (tên bài) → `trang_from/to`+`tap_no` → content-vector (`embedding`).

---
Liên quan: `docs/design/kg-schema-v3.md` (design gốc) · `docs/data/vietnamese-normalization.md` · `docs/data/data-quality-checklist.md` · `rag_edu/scripts/schema_v3_2026_06/`
