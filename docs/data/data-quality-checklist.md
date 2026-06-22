# Data-Quality Checklist — Knowledge PTalk (Cypher để CHẠY SAU)

> **Vai trò**: Corpus / Data-Quality. **Ràng buộc vòng này**: KHÔNG SSH, KHÔNG đụng Neo4j. Mọi Cypher dưới đây là **để chạy SAU** (read-only) khi có quyền — KHÔNG chạy bây giờ.
> **Cách chạy sau** (read-only, đúng quy ước repo): trên server `bolt://localhost:7688` (Neo4j edu), `cypher-shell` hoặc driver chỉ với câu `MATCH`/`RETURN`. **Không** `SET`/`DELETE`/`MERGE` trừ khi được cho phép rõ ràng.
> **Tham chiếu chuẩn hóa**: mọi so khớp tên bài/khái niệm phải dùng `fold()` (xem `vietnamese-normalization.md`). Cypher thuần KHÔNG có `fold()` → các check dưới dùng property `*_norm` đã backfill, hoặc `apoc.text.clean`/`toLower` xấp xỉ + verify tay.

## Checklist tổng (tick khi đã chạy + ghi run-id)

- [ ] **C1** Không có :Lesson trùng theo (subject, grade, book_set, volume, page, title_norm) — Q-DUP
- [ ] **C2** Mọi :Lesson có `work_name_norm` + `trang_from` + `theory` không rỗng — Q-MISS
- [ ] **C3** Không theory chứa **real cruft** (`Giáo viên VietJack` / `Xem lời giải` / `loigiaihay` / `Video Giải`) — Q-CRUFT. ⚠️ KHÔNG tính `"giáo viên"` trần (từ vựng hợp lệ).
- [ ] **C4** Văn: mỗi (work_name, variant) hợp lệ + có ≥1 recite path cho bài có thơ — Q-VAN
- [ ] **C5** Toán: mọi :Lesson/:KnowledgeChunk(lesson) có Concept qua COVERS; không COVERS orphan — Q-TOAN
- [ ] **C6** Volume: không trang collision giữa tap 1 và tap 2 cùng quyển — Q-DUP-VOL
- [ ] **C7** Coverage: toan 6 KNTT tập 2 thực sự chỉ 4 bài? (anomaly từ inventory) — Q-COV

---

## Q-DUP — duplicate lesson (C1)

```cypher
// :Lesson trùng theo (subject, grade, book_set, volume, page, title_norm)
MATCH (l:Lesson)
WITH l.subject_code AS s, l.grade AS g, l.bo_sach AS bo,
     coalesce(l.tap_no, 0) AS vol, l.trang_from AS page,
     coalesce(l.work_name_norm, toLower(l.work_name)) AS tnorm,
     collect(l) AS ls
WHERE size(ls) > 1
RETURN s, g, bo, vol, page, tnorm, size(ls) AS n,
       [x IN ls | x.work_name] AS titles
ORDER BY n DESC;
```

```cypher
// Biến thể trên :KnowledgeChunk nền (Văn/Toán)
MATCH (k:KnowledgeChunk)
WHERE k.production_ready = true
WITH k.subject_code AS s, k.grade AS g, k.bo_sach AS bo,
     coalesce(k.tap_no,0) AS vol, k.trang_no AS page,
     coalesce(k.work_name_norm, k.title) AS tnorm, collect(k.uid) AS uids
WHERE size(uids) > 1
RETURN s, g, bo, vol, page, tnorm, size(uids) AS n LIMIT 100;
```

## Q-MISS — lesson thiếu field anchor (C2)

```cypher
// :Lesson thiếu work_name_norm / trang / theory
MATCH (l:Lesson)
WITH l,
     (l.work_name_norm IS NULL OR l.work_name_norm = '') AS miss_norm,
     (l.trang_from IS NULL)                              AS miss_trang,
     (l.theory IS NULL OR size(toString(l.theory)) < 20) AS miss_theory
WHERE miss_norm OR miss_trang OR miss_theory
RETURN l.subject_code AS s, l.grade AS g, l.bo_sach AS bo, l.work_name AS bai,
       miss_norm, miss_trang, miss_theory
ORDER BY s, g LIMIT 200;
```

```cypher
// :Lesson không có HAS_THEORY (đứt link sang KnowledgeChunk theory)
MATCH (l:Lesson) WHERE NOT (l)-[:HAS_THEORY]->()
RETURN l.subject_code AS s, l.grade AS g, l.bo_sach AS bo, l.work_name AS bai
ORDER BY s, g LIMIT 200;
```

## Q-CRUFT — real cruft trong theory (C3) ⚠️ chỉ real, không tính "giáo viên" trần

```cypher
// CHỈ các chuỗi rác nguồn THẬT. KHÔNG dùng "giáo viên" trần (false-positive).
WITH ['Giáo viên VietJack', '(Giáo viên', 'Xem lời giải', 'Xem chi tiết',
      'loigiaihay', 'Video Giải', 'Bài giảng:', 'Giải bài nhanh với AI Hay'] AS cruft
MATCH (n)
WHERE (n:Lesson OR n:KnowledgeChunk)
  AND any(c IN cruft WHERE coalesce(n.theory, n.text, '') CONTAINS c)
RETURN labels(n) AS lbl, n.subject_code AS s, n.grade AS g,
       coalesce(n.work_name, n.title) AS bai,
       [c IN cruft WHERE coalesce(n.theory, n.text,'') CONTAINS c] AS hit
LIMIT 200;
// Kỳ vọng: 0 hàng (verify Neo4j 2026-06-22: vietjack=0, xem-lời-giải=0, loigiaihay=0).
```

```cypher
// Đối chứng false-positive: đếm "giáo viên" trần (HỢP LỆ, kỳ vọng ~11, KHÔNG phải lỗi)
MATCH (n) WHERE (n:Lesson OR n:KnowledgeChunk)
  AND toLower(coalesce(n.theory, n.text,'')) CONTAINS 'giáo viên'
  AND NOT coalesce(n.theory, n.text,'') CONTAINS 'Giáo viên VietJack'
RETURN count(n) AS hop_le;
```

## Q-VAN — Văn variant/recite consistency (C4)

```cypher
// Variant không hợp lệ (ngoài tập 4 giá trị)
MATCH (k:KnowledgeChunk {subject_code:'ngu_van'})
WHERE k.variant IS NOT NULL
  AND NOT k.variant IN ['standard','chi_tiet','sieu_ngan','ngan_nhat']
RETURN DISTINCT k.variant AS bad_variant, count(*) AS n;
```

```cypher
// Work có work_name_norm nhưng KHÔNG có variant 'standard' (companion mặc định sẽ hụt)
MATCH (k:KnowledgeChunk {subject_code:'ngu_van', production_ready:true})
WHERE k.work_name IS NOT NULL
WITH k.work_name AS work, k.grade AS g, k.bo_sach AS bo,
     collect(DISTINCT k.variant) AS variants
WHERE NOT 'standard' IN variants
RETURN g, bo, work, variants ORDER BY g LIMIT 100;
```

```cypher
// Bài có thơ nhưng thiếu recite path (LiteratureText allow_full_recitation)
MATCH (w:LiteraryWork {the_loai:'tho'})
WHERE NOT (:LiteratureText {allow_full_recitation:true})-[:VERBATIM_OF]->(w)
RETURN w.grade AS g, w.name AS bai_tho LIMIT 100;
```

## Q-TOAN — Concept↔Chunk qua COVERS (C5)

```cypher
// Lesson/chunk Toán (lesson thật) KHÔNG có COVERS sang Concept
MATCH (k:KnowledgeChunk {subject_code:'toan', production_ready:true})
WHERE coalesce(k.content_class,'') = 'vietjack_lesson'
  AND NOT (k)-[:COVERS]->(:Concept)
RETURN k.grade AS g, k.bo_sach AS bo, count(k) AS chunk_thieu_concept
ORDER BY chunk_thieu_concept DESC;
```

```cypher
// Concept orphan (không chunk nào COVERS) — backbone treo
MATCH (c:Concept {subject:'toan'})
WHERE NOT (:KnowledgeChunk)-[:COVERS]->(c)
RETURN c.grade_introduced AS g, c.name AS concept_orphan LIMIT 100;
```

```cypher
// Concept thiếu name_norm (sẽ fail concept_retrieve trong diag_weak.py)
MATCH (c:Concept) WHERE c.name_norm IS NULL OR size(c.name_norm) < 3
RETURN c.subject AS s, c.name AS concept LIMIT 100;
```

## Q-DUP-VOL — trang collision giữa tập 1/2 (C6)

```cypher
// Cùng (subject,grade,book_set), 1 số trang xuất hiện ở CẢ tap 1 và tap 2,
// và 2 :Lesson khác bài → rủi ro anchor-theo-trang chọn nhầm tập.
MATCH (a:Lesson), (b:Lesson)
WHERE a.subject_code = b.subject_code AND a.grade = b.grade
  AND a.bo_sach = b.bo_sach
  AND a.tap_no = 1 AND b.tap_no = 2
  AND a.trang_from IS NOT NULL AND b.trang_from IS NOT NULL
  AND a.trang_from <= b.trang_to AND b.trang_from <= a.trang_to   // overlap range
RETURN a.subject_code AS s, a.grade AS g, a.bo_sach AS bo,
       a.work_name AS bai_t1, a.trang_from AS t1_from, a.trang_to AS t1_to,
       b.work_name AS bai_t2, b.trang_from AS t2_from, b.trang_to AS t2_to
LIMIT 100;
// Backtest đã chứng tap separation OK (toan 8 KNTT t1=96.4/t2=98.8) → kỳ vọng ít/không.
```

## Q-COV — anomaly coverage (C7)

```cypher
// toan 6 KNTT tap 2 — inventory thấy CHỈ 4 bài; verify có phải thiếu coverage không
MATCH (l:Lesson {subject_code:'toan', grade:6, bo_sach:'KNTT', tap_no:2})
RETURN count(l) AS so_bai_t2, collect(l.work_name) AS ten_bai;
// Nếu <10 → coverage gap thật, không phải lỗi count.
```

```cypher
// ngu_van 9 CTST — sweep chỉ có tap 2; verify tap 1 có :Lesson không
MATCH (l:Lesson {subject_code:'ngu_van', grade:9, bo_sach:'CTST'})
RETURN l.tap_no AS tap, count(l) AS n ORDER BY tap;
```

---
Liên quan: `docs/data/corpus-inventory.md` (anomaly nguồn) · `docs/data/neo4j-schema-v3.md` (field) · `docs/data/vietnamese-normalization.md` (fold) · `docs/project_state/2026-06-22-canonical.md` (real cruft=0)
