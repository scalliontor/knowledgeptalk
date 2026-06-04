# Dashboard KG Viewer — Guide cập nhật cho Schema v3

> **Mục đích**: hướng dẫn tự sửa Dashboard (`/kg-browse` + `/kg-analytics`) để hiển thị lớp tri thức MỚI (Concept / Tác phẩm / Section / Variant) sau migration schema v3 (2026-06-03/04). Bản gốc `Dashboard/dashboard/docs/KG_FEATURE_SPEC.md` viết khi chỉ Toán W1 xong — code hiện dừng ở Bài→Chunks. Guide này bổ sung phần còn thiếu.
> **Audience**: dev tự implement. Cypher copy-paste ready (đã test trên data thật).
> **Kết nối**: `bolt://host.docker.internal:7688`, user `dashboard_ro`, password trong `Dashboard/dashboard/.env` (KHÔNG chép vào đây).

---

## 0. Cái gì đã thay đổi (old viewer → schema v3)

| | Viewer cũ (đang chạy) | Cần thêm (schema v3) |
|---|---|---|
| Hierarchy | Bộ→Môn→Lớp→Bài→Chunks | + tầng **Concept** / **Tác phẩm→Section→Variant** |
| Nodes | chỉ `:KnowledgeChunk` | + `:Concept` (3.405), `:LiteraryWork` (418) |
| Edges | `(Unit)-[:HAS_LESSON]->` (cũ) | + `:COVERS`, `:ABOUT_WORK`, `:VERBATIM_OF`, `:PREREQ` |
| Props | grade, bo_sach, lesson_no | + `content_class`, `concept_name`, `work_name`, `section_type`, `variant`, `trang_no` |
| Môn | Toán W1 | **5 môn K-9** đầy đủ |

---

## 1. Data model schema v3 (nguồn sự thật cho query)

### Nodes
```
(:KnowledgeChunk {
   uid, subject_code, grade, bo_sach, production_ready,   // filter cơ bản
   title, text, document_id,                               // hiển thị
   lesson_no, trang_no, tap_no,                            // structured (Toán/TV/KHTN/Sử-Địa)
   content_class,                                          // phân loại nguồn (xem §2)
   concept_name, concept_id_fine,                          // Toán/KHTN/Sử-Địa/GDCD/TV
   work_name, work_name_norm, section_type, variant        // Văn (+ TV section)
})
(:Concept {concept_id, name, name_norm, subject, strand, grade_introduced, level})  // level='fine' | strand
(:LiteraryWork {name, name_norm, author, grade_introduced})   // Văn
(:LiteratureText {grade, series, title, full_text, allow_full_recitation})  // recitation Văn
```

### Edges (mới)
```
(:KnowledgeChunk)-[:COVERS]->(:Concept)          // ~5.224 — mọi môn trừ Văn-recitation
(:KnowledgeChunk)-[:ABOUT_WORK]->(:LiteraryWork) // Văn — chunk phân tích về tác phẩm
(:LiteratureText)-[:VERBATIM_OF]->(:LiteraryWork)// Văn — bản nguyên văn để đọc thuộc
(:Concept)-[:PREREQ]->(:Concept)                 // CHỈ Toán — chuỗi tiên quyết (phân số→tỉ số→tỉ lệ thức)
```

### ⚠️ Lưu ý chuẩn hóa (quan trọng)
- `name_norm` / `work_name_norm` = **fold(đ→d rồi bỏ dấu)**. Khi search/filter text từ UI, fold y hệt phía client trước khi so. (Bug kinh điển: unicodedata KHÔNG tách đ→d.)

---

## 2. content_class theo môn (cho filter "loại nội dung")

| Môn | content_class values | Ý nghĩa |
|---|---|---|
| Toán | `vietjack_lesson` · `vietjack_exercise` · `lgh_qa` | bài giảng vs trang bài tập vs Q&A |
| Văn | (dùng `section_type` thay) `soan_bai`·`lgh_qa_solution`·`trac_nghiem`·`thuc_hanh_tieng_viet`·`viet`·`noi_nghe`·`tri_thuc_ngu_van`·`cung_co`·`on_tap`·`general` | + `variant`: `chi_tiet`·`sieu_ngan`·`ngan_nhat`·`standard` |
| KHTN | `lesson`·`exercise`·`quiz`·`exam`·`qa_fragment`·`index`·`other` | |
| Xã hội (Sử/Địa/GDCD) | `vietjack_lesson`·`lgh_solution`·`lgh_qa` | |
| Tiếng Việt | `tv_lesson`·`tv_vbt`·`tv_assessment` | |

→ UI: khi chọn môn, đổ dropdown content_class tương ứng (ưu tiên `*_lesson` mặc định).

### ⛔ KHÔNG hiện tên nguồn crawl ("vietjack" / "lgh" / "loigiaihay") ra UI
`content_class` chứa tag provenance nội bộ (`vietjack_*`, `lgh_*`) — **chỉ dùng để filter/ordering/audit, KHÔNG show thô cho người dùng**. (Title sạch: 0/15.226 chunk có "vietjack" trong title — chỉ content_class có.) Luôn map qua nhãn tiếng Việt:

```ts
const CONTENT_CLASS_LABEL: Record<string,string> = {
  // Toán / Xã hội
  vietjack_lesson: "Bài giảng",  vietjack_exercise: "Bài tập",
  lgh_qa: "Hỏi đáp",  lgh_solution: "Lời giải",  lgh_qa_solution: "Hỏi đáp & lời giải",
  // KHTN
  lesson: "Bài học",  exercise: "Bài tập",  quiz: "Trắc nghiệm",  exam: "Đề kiểm tra",
  qa_fragment: "Hỏi đáp",  index: "Mục lục",  other: "Khác",
  // Tiếng Việt
  tv_lesson: "Bài học",  tv_vbt: "Vở bài tập",  tv_assessment: "Ôn tập / Kiểm tra",
};
const labelOf = (cc?: string) => CONTENT_CLASS_LABEL[cc ?? ""] ?? "Nội dung";

// Văn dùng section_type:
const SECTION_LABEL: Record<string,string> = {
  soan_bai:"Đọc hiểu / Soạn bài", viet:"Viết", noi_nghe:"Nói và nghe",
  thuc_hanh_tieng_viet:"Thực hành tiếng Việt", tri_thuc_ngu_van:"Tri thức ngữ văn",
  cung_co:"Củng cố", on_tap:"Ôn tập", trac_nghiem:"Trắc nghiệm",
  lgh_qa_solution:"Hỏi đáp & lời giải", general:"Tổng hợp",
};
const VARIANT_LABEL: Record<string,string> = {
  chi_tiet:"Chi tiết", sieu_ngan:"Siêu ngắn", ngan_nhat:"Ngắn nhất", standard:"Tiêu chuẩn",
};
```
→ Áp ở `FilterSidebar` (option label), `BrowseListView` (badge), `ChunkDetailPanel`. **Không nơi nào render `content_class` / `source` thô.** Nếu sau này muốn chặt hơn: ẩn luôn cột "nguồn" hoặc gộp vietjack_lesson+lgh_solution thành "Bài giảng & lời giải".

---

## 3. Browse hierarchy PER-SUBJECT + Cypher từng level

> Mọi query thêm filter chuẩn: `k.production_ready=true AND k.subject_code=$subject AND k.grade=toInteger($grade) AND k.bo_sach=$bo_sach`. Param hóa hết. Index sẵn: composite (grade,subject,bo_sach,content_class) + vector.

### 3.1 Toán — `Bộ→Môn→Lớp→Bài→Concept→Chunks` (+ PREREQ)
**L: Bài (lesson_no)** — ưu tiên `content_class='vietjack_lesson'` (tránh trang bài tập):
```cypher
MATCH (k:KnowledgeChunk)
WHERE k.subject_code='toan' AND k.grade=toInteger($grade) AND k.bo_sach=$bo_sach
  AND k.production_ready=true AND k.content_class='vietjack_lesson' AND k.lesson_no IS NOT NULL
RETURN k.lesson_no AS lesson_no, collect(DISTINCT k.title)[0] AS sample_title, count(*) AS chunks
ORDER BY lesson_no;
```
**L+1: Concept của 1 bài** (qua COVERS):
```cypher
MATCH (k:KnowledgeChunk {subject_code:'toan',production_ready:true})-[:COVERS]->(c:Concept)
WHERE k.grade=toInteger($grade) AND k.bo_sach=$bo_sach AND k.lesson_no=toInteger($lesson_no)
RETURN c.concept_id AS id, c.name AS concept, c.strand AS strand, count(k) AS chunks ORDER BY chunks DESC;
```
**Bonus PREREQ** (companion "bài này dựa bài kia"):
```cypher
MATCH (pre:Concept)-[:PREREQ*1..3]->(c:Concept {concept_id:$concept_id})
RETURN [n IN nodes((pre)-[:PREREQ*1..3]->(c)) | n.name+' (G'+n.grade_introduced+')'] AS chain LIMIT 5;
```

### 3.2 Văn — `Bộ→Môn→Lớp→Tác phẩm→Section→Variant→Chunks` (+ recitation)
**L: Tác phẩm (work_name)**:
```cypher
MATCH (k:KnowledgeChunk {subject_code:'ngu_van',production_ready:true})
WHERE k.grade=toInteger($grade) AND k.bo_sach=$bo_sach AND k.work_name IS NOT NULL
RETURN k.work_name AS work, count(*) AS chunks,
       collect(DISTINCT k.section_type) AS sections, collect(DISTINCT k.variant) AS variants
ORDER BY work;
```
**L+1: Section × Variant của 1 tác phẩm**:
```cypher
MATCH (k:KnowledgeChunk {subject_code:'ngu_van',production_ready:true})
WHERE k.grade=toInteger($grade) AND k.bo_sach=$bo_sach AND k.work_name=$work
RETURN k.section_type AS section, k.variant AS variant, k.uid AS uid, k.title AS title
ORDER BY section, variant;
```
**Recitation (đọc nguyên văn)** — node riêng:
```cypher
MATCH (lt:LiteratureText)-[:VERBATIM_OF]->(w:LiteraryWork {name:$work})
RETURN lt.title AS title, lt.allow_full_recitation AS allow, left(lt.full_text,400) AS preview;
```

### 3.3 KHTN / Lịch sử / Địa lý / GDCD — `Bộ→Môn→Lớp→Concept→Chunks`
(không đánh số bài đều → Concept là tầng chính)
```cypher
MATCH (k:KnowledgeChunk {production_ready:true})-[:COVERS]->(c:Concept)
WHERE k.subject_code=$subject AND k.grade=toInteger($grade) AND k.bo_sach=$bo_sach
RETURN c.name AS concept, count(k) AS chunks ORDER BY concept;
// subject ∈ ['khtn','lich_su','dia_li','gdcd'] (Lý/Hóa/Sinh G6-9 cũng có thể gộp khtn)
```

### 3.4 Tiếng Việt — `Bộ→Môn→Lớp→Bài→(reading-text Concept)→Chunks`
(hybrid: có lesson_no/trang_no VÀ concept = bài đọc)
```cypher
MATCH (k:KnowledgeChunk {subject_code:'tieng_viet',production_ready:true})
WHERE k.grade=toInteger($grade) AND k.bo_sach=$bo_sach AND k.lesson_no IS NOT NULL
RETURN k.lesson_no AS bai, collect(DISTINCT k.concept_name)[..3] AS reading_texts,
       collect(DISTINCT k.trang_no) AS pages, count(*) AS chunks ORDER BY bai;
```

### 3.5 Chunk detail (mọi môn) — endpoint `/api/kg/chunk/[uid]`
```cypher
MATCH (k:KnowledgeChunk {uid:$uid})
OPTIONAL MATCH (k)-[:COVERS]->(c:Concept)
OPTIONAL MATCH (k)-[:ABOUT_WORK]->(w:LiteraryWork)
RETURN k.title AS title, k.text AS text, k.grade AS grade, k.bo_sach AS bo_sach,
       k.lesson_no AS lesson_no, k.trang_no AS trang_no, k.content_class AS content_class,
       k.section_type AS section_type, k.variant AS variant,
       collect(DISTINCT c.name) AS concepts, w.name AS work;
```

---

## 4. Files Dashboard cần sửa (map vào code hiện có)

| File | Sửa gì |
|---|---|
| `src/app/api/kg/browse/route.ts` | Thêm level mới theo §3 — detect deepest param: nếu có `lesson_no`/`work` → trả Concept/Section thay vì nhảy thẳng Chunks. Per-subject switch (`subject==='ngu_van'` → work path; else → concept path). |
| `src/lib/kg-types.ts` | `BrowseLevel` thêm: `L4_concept`, `L4a_work`, `L4b_section`, `L5_chunk`. Thêm field `concept`, `work`, `section_type`, `variant` vào `BrowseItem.meta`. |
| `src/components/kg/FilterSidebar.tsx` | Dropdown động theo môn: Toán→content_class; Văn→section_type+variant; thêm filter "Concept" (autocomplete trên `name_norm`). |
| `src/components/kg/BrowseListView.tsx` | Render thêm tile cấp Concept/Tác phẩm (icon 🧠 cho concept, 📖 cho work, badge variant). |
| `src/components/kg/BrowseGraphView.tsx` | Thêm group color: `concept` (#a78bfa), `work` (#ec4899); vẽ edge COVERS/ABOUT_WORK; nếu Toán, optional vẽ PREREQ (mũi tên). |
| `src/components/kg/ChunkDetailPanel.tsx` | Hiện concepts[], work, section_type, variant, content_class (badges). |
| `src/app/api/kg/analytics/route.ts` | (tùy chọn) thêm card: tổng Concept, tổng Tác phẩm, COVERS coverage %; heatmap "concept/lớp". |

---

## 5. Analytics — thêm metrics schema v3 (cho `/kg-analytics`)
```cypher
// Coverage tri thức
MATCH (c:Concept) RETURN c.subject AS subject, count(*) AS concepts ORDER BY concepts DESC;
MATCH (w:LiteraryWork) RETURN count(*) AS works;
MATCH (:KnowledgeChunk)-[:COVERS]->() RETURN count(*) AS covers_edges;
// % chunk có concept (theo môn)
MATCH (k:KnowledgeChunk {production_ready:true})
RETURN k.subject_code AS subj, count(*) AS total,
  sum(CASE WHEN (k)-[:COVERS]->() THEN 1 ELSE 0 END) AS with_concept;
// content_class breakdown (donut)
MATCH (k:KnowledgeChunk {production_ready:true}) WHERE k.subject_code=$subject
RETURN k.content_class AS cls, count(*) AS n ORDER BY n DESC;
```

---

## 6. Tham khảo thêm
- Bản showcase nhanh (sunburst + heatmap, self-contained, không cần Dashboard): `docs/viz/kg-showcase.html` — có thể nhúng iframe vào `/kg-analytics` nếu muốn.
- Schema decision đầy đủ: [kg-schema-v3.md](kg-schema-v3.md)
- Eval (độ chính xác/latency retrieval): `docs/evaluation/*` — structured-first 93-100%, latency 8-40ms, leak=0.

## 7. Verification checklist (sau khi sửa)
| # | Test | Expect |
|---|---|---|
| 1 | `/kg-browse` Toán G6 KNTT → click Bài → | thấy tile **Concept** (Tập hợp, Số nguyên...) |
| 2 | Văn G8 KNTT → click → | thấy **Tác phẩm** (Bếp lửa...) → Section (đọc hiểu/viết) → Variant |
| 3 | Văn → tác phẩm có recitation | hiện nút "Đọc nguyên văn" (LiteratureText) |
| 4 | KHTN/Sử/Địa G6-9 → | tile **Concept** trực tiếp dưới Lớp |
| 5 | Graph view Toán | thấy edge COVERS + (optional) PREREQ |
| 6 | Chunk detail | badges concept/work/section/variant/content_class |
| 7 | Analytics | card Concept (3.405) + Tác phẩm (418) + COVERS (5.224) |
