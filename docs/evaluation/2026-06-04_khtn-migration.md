# Migration KHTN sang schema v3 — audit + backfill + eval

> **Ngày**: 2026-06-04 · **Actor mutation**: `KHTN_AGENT_2026_06_04` (reversible) · **Neo4j edu** bolt:7688
> **Phạm vi**: `subject_code IN [khtn, vat_li, hoa_hoc, sinh_hoc]`, `production_ready=true` (2306 chunk)
> **Theo pattern**: [kg-schema-v3.md](../design/kg-schema-v3.md) (đã chứng minh cho Toán + Văn) · mirror [verify Toán](2026-06-03_verify-arch-toan.md)
> **Bất biến**: chunk doc-level · structured-first (Cypher exact) · KHÔNG model mới · companion mode

## 1. AUDIT (read-only)

### Prod chunk per subject × grade × bộ sách
| subject_code | tổng prod | phân bố lớp (chính) |
|---|---:|---|
| **khtn** | 1225 | G6 (322), G7 (221), G8 (429), G9 (249), G5 (4) — đủ KNTT/CTST/CD |
| **sinh_hoc** | 638 | G6 (122), G7 (182), G10 (226), G11 (108) — gần như toàn `bo_sach=none` |
| **hoa_hoc** | 258 | G11 (207), G3 (19), G8 (16), G9 (13), G10 (3) |
| **vat_li** | 185 | G10 (86), G5 (35), G11 (28), G4 (17), G6 (14), G8 (5) |

### Fill rate property (trước backfill)
| field | khtn | vat_li | hoa_hoc | sinh_hoc |
|---|---|---|---|---|
| lesson_no | 60% | 14% | 7% | 1% |
| trang_no | ~0% (1 chunk) | 14% | 7% | ~0% |
| chunk_type | 38% | 100% | 100% | 100% |
| content_class | 0 | 0 | 0 | 0 |
| concept (node) | 0 | 0 | 0 | 0 |

Existing `lesson_no` của khtn (731 chunk) đối chiếu với title `Bài N` → **0 mismatch** (đáng tin, không cần ghi đè).

### Title pattern (regex thiết kế từ 20+ sample/môn)
- **khtn lesson**: `(Khoa học tự nhiên|KHTN) {g} {bộ} Bài {N}: {tên}` → 599 (48%). lesson_no=N, concept=tên.
- **khtn quiz**: `Trắc nghiệm khoa học tự nhiên {g} bài {N} {bộ}` → 79.
- **khtn SBT**: `Giải sách bài tập KHTN lớp {g} Bài {N}: {tên}` → ~179 (workbook, giữ lesson_no link).
- **vat_li/hoa_hoc exercise**: `Giải {môn} {g} bài {N} trang {M}... {bộ}` → trang_no=M (đây là **bài tập số N trang M**, KHÔNG phải lesson — F1 Bug A).
- **vat_li lesson**: `Lý thuyết {tên} - Vật lí {g} {bộ}` → concept=tên (5 chunk).
- **vat_li exam**: `Đề thi {kì} Vật lí {g} {bộ}` → 17.
- **qa_fragment**: title ngắn kết thúc `-` / có "là/nào/?" / `chunk_type=solution` → fragment hỏi-đáp lẻ (loigiaihay), thường `bo_sach=none`.

### F1-style problems phát hiện (mirror audit Toán)
1. **Bug A (exercise vs lesson)**: `Giải ... bài N trang M` = *bài tập số N ở trang M*, nếu parse `N`→lesson_no sẽ sai. → tách `content_class=khtn_exercise`, set `trang_no=M`, KHÔNG set lesson_no=N.
2. **bo_sach='none' = 1287/2306 (56%)** — phần lớn là qa_fragment hỏi-đáp lẻ không gắn bộ sách → **structured-first bất khả** cho nhóm này (chỉ vào được qua vector). Đây là gap data lớn nhất.
3. **⚠️ FLAG curriculum — subject mislabel G6-9**: GDPT 2018 gộp Lý/Hóa/Sinh thành **KHTN** ở THCS (G6-9). Nhưng có content G6-9 mang nhãn môn tách:
   - `sinh_hoc` G6 (122), G7 (182); `hoa_hoc` G8 (16), G9 (13); `vat_li` G6 (14), G8 (5).
   - → Đây là phân-miền của KHTN bị gán nhãn môn riêng (hoặc SGK chương trình cũ). **KHÔNG xoá / KHÔNG demote** (nội dung vẫn đúng tri thức, chỉ sai nhãn subject_code). Đã actor-tag để retrieval gom chung qua filter `subject_code IN [khtn,vat_li,hoa_hoc,sinh_hoc]`. Đề xuất sau: hợp nhất nhãn về `khtn` cho G6-9 (giữ sub-domain ở field phụ).
   - `hoa_hoc` G3 (19) + `vat_li` G4 (17), G5 (35): dưới cấp KHTN (THCS bắt đầu G6) → là "Khoa học/TNXH" tiểu học gán nhầm. **FLAG, để lại** (ít, không hại; retrieval lớp khác không chạm).

## 2. BACKFILL (actor `KHTN_AGENT_2026_06_04`, reversible)

Python pass trên title (script `/tmp/khtn_backfill2.py` + `/tmp/lt_fix3.py`). Backup field ghi đè vào `_khtn_backup_<field>`; KHÔNG đụng `production_ready`, KHÔNG xoá, KHÔNG chạm môn khác.

| Mutation | Count |
|---|---:|
| `content_class` set | **2306** (toàn bộ target) |
| `lesson_no` set (có backup `_khtn_backup_lesson_no` 659) | 783 |
| `trang_no` set | 45 |
| `concept_name` + `concept_name_norm` (fold đ→d) | 658 |
| chunk actor-tagged `_khtn_actor` | 2306 |

### content_class phân bố cuối (per subject)
| subject | lesson | exercise | quiz | exam | qa_fragment | index | other |
|---|---:|---:|---:|---:|---:|---:|---:|
| khtn | 599+5* | 52 | 79 | — | 303 | 13 | 179 |
| vat_li | 5 | 25 | — | 17 | 133 | 5 | — |
| hoa_hoc | — | 18 | — | — | 239 | 1 | — |
| sinh_hoc | 8 | — | — | — | 629 | 1 | — |

(* +5 = vat_li `Lý thuyết` lessons fixed riêng; `khtn_other`=179 = SBT "Giải sách bài tập ... Bài N" còn lại, giữ lesson_no.)

## 3. CONCEPT NODES (lớp Concept tách rời — P1/P2)

`:Concept {concept_id:'khtn.<slug>', name, name_norm (fold đ→d), subject:'khtn', grade_introduced, level:'fine', source:'lesson_title', created_actor}` + edge `(:KnowledgeChunk)-[:COVERS {actor}]->(:Concept)`.

| | Count |
|---|---:|
| `:Concept` (level=fine) tạo | **379** |
| `COVERS` edge | **663** |
| chunk có `concept_name` nguồn | 663 (G6 139 concept, G9 90, G8 83, G7 79) |

Concept = **chủ đề/khái niệm bài học KHTN** (vd "Tế bào", "Lực ma sát", "Hiện tượng phóng xạ", "Quang hợp"). Khớp nguyên tắc: concept là node riêng, nối bằng edge thật, không nhúng property.

## 4. EVAL — G5-10, 2000 case (Cypher-emulated)

Harness `/tmp/eval_khtn_full.py` — emulate retrieval schema-v3 (structured-exact lesson_no/trang + concept-exact word-overlap trên `Concept.name_norm`, ≥2 từ ≥4 ký tự HOẶC full-contains). 4 loại: **theo_bài / theo_trang / kiến thức ("X là gì") / vận dụng (cách làm/ứng dụng)**. Kết quả `/tmp/eval_khtn_results.json`.

### Hit-rate grade × type (hit% | n)
| Lớp | theo_bài | theo_trang | kiến thức | vận dụng | OVERALL |
|---|---|---|---|---|---|
| G5 | — | 100% (125) | — | — | 100% |
| G6 | 100% (125) | — | 92.0% (125) | 92.0% (125) | 94.7% |
| G7 | 100% (125) | — | 88.8% (125) | 90.4% (125) | 93.1% |
| G8 | 100% (125) | 100% (125) | 96.8% (125) | 93.6% (125) | 97.6% |
| G9 | 100% (125) | — | 100% (125) | 96.8% (125) | 98.9% |
| G10 | 100% (125) | 100% (125) | — | — | 100% |

**Theo loại**: theo_bài **100%** (625/625) · theo_trang **100%** (375/375) · kiến thức **94.4%** (472/500) · vận dụng **93.2%** (466/500).
**Cross-grade leak = 0/2000** ✅. **OVERALL 96.9%** (1938/2000).

### Kết luận
- ✅ **theo_bài 100%** — structured-exact trên lesson_no + `content_class=khtn_lesson` (ưu tiên lesson, không lẫn exercise/quiz) hoạt động hoàn hảo.
- ✅ **kiến thức/vận dụng 93-94%** — concept-exact (word-overlap trên name_norm) tốt hơn Toán baseline (73-77%) vì tên concept KHTN ngắn/danh từ rõ ("Tế bào", "Quang hợp").
- ✅ **leak = 0** — hard-filter grade + bo_sach đúng (không lặp bug cross-grade của Toán baseline).
- Concept miss ~6-7% = tên concept dài nhiều mệnh đề (vd "Điện từ trường. Mô hình sóng điện từ") hoặc sibling cùng từ khoá.

## 5. Gap còn lại (top 3)

1. **bo_sach='none' = 56% prod (1287 chunk)** — chủ yếu `khtn_qa_fragment` (loigiaihay hỏi-đáp lẻ) + sinh_hoc/hoa_hoc G10-11. Không có bộ sách → **structured-first không vào được**, chỉ vector. Eval không chấm nhóm này (không đủ anchor). Cần: backfill `bo_sach` từ source_url/nội dung, hoặc chấp nhận vector-only cho nhóm tra cứu.
2. **trang_no gần như trống ở khtn (chỉ 45 chunk toàn target)** — crawl KHTN không bắt số trang như Toán/Văn. theo_trang chỉ chạy được G5/G8/G10. Cần re-crawl/parse trang từ title `Giải ... trang M` cho vat_li/hoa_hoc (đã có 25+18) và bổ sung khtn.
3. **Subject mislabel G6-9 (Lý/Hóa/Sinh tách khỏi KHTN)** — FLAG ở §1.3. GDPT 2018 = KHTN tích hợp ở THCS. Retrieval hiện gom qua filter đa-subject; nhưng companion theo "bộ sách KHTN" sẽ lệch nếu device gửi subject=khtn còn data nằm ở sinh_hoc. Đề xuất: hợp nhất nhãn `subject_code='khtn'` cho G6-9 (giữ sub-domain field), giai đoạn sau.

## 6. Reversibility

Mọi mutation reversible qua actor tag `KHTN_AGENT_2026_06_04`:
- Chunk: `_khtn_actor` (2306), backup `_khtn_backup_lesson_no` (659) / `_khtn_backup_trang_no`.
- Concept: `created_actor='KHTN_AGENT_2026_06_04'` (379); edge `COVERS {actor:...}` (663).
- KHÔNG đụng `production_ready`, KHÔNG xoá node, KHÔNG sửa rag_server, KHÔNG chạm môn khác. prod target vẫn 2306.

Liên quan: [kg-schema-v3.md](../design/kg-schema-v3.md) · [verify Toán](2026-06-03_verify-arch-toan.md) · [verify Văn](2026-06-04_verify-arch-van.md)
