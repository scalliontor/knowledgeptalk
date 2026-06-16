# RAG AUDIT — Toán & các môn ngoài pilot (2026-06-14)

> **CẬP NHẬT 2026-06-14**: khuyến nghị #2 (build companion cho Toán) ĐÃ THỰC HIỆN cho **Toán 6 CTST tập 2** → xem [../pilot/TOAN_v6_ctst_t2_RESULTS.md](../pilot/TOAN_v6_ctst_t2_RESULTS.md). Trang-style port thành công: 24 :Lesson, anchor 15/15, cruft 0/15 (audit này = "trước"). Các môn/lớp khác vẫn ở trạng thái audit bên dưới.

> Test trực tiếp trên **canary :8889** và **prod :8888** (kết quả GIỐNG nhau — đây là hành vi production thật). Companion "Lesson Card" mới chỉ phủ **Ngữ văn 9 CTST tập 2**; mọi môn khác rơi xuống RAG nền (Tier A concept + vector). Mục tiêu: đo "ngu tới đâu" trước khi quyết mở rộng.

## TL;DR
- **Toán = tệ nhất**: câu hỏi khái niệm trả **SAI bài 9/10**, dính rác VietJack 9/10. "định lí Pytago" → "Bài 2: Lựa chọn dạng biểu đồ" (lệch hoàn toàn). Concept-tag sai lệch ("[concept: Phân số]" nhưng nội dung là *số thập phân*) → đúng audit cũ "98% orphan + F1 collision".
- **Quy luật xuyên môn**: retrieve đúng **CHỈ KHI** tên khái niệm ≈ đúng tên bài (Sử/Địa thắng vì "bài"="chủ đề"; "lực ma sát"=Bài 44 Lực ma sát). Khái niệm trừu tượng / span nhiều bài (Toán, "tế bào", "quang hợp") → trả Trắc nghiệm/Bài tập/sai bài.
- **Bug serve toàn hệ thống**: `sanitize_chunk_text()` (đã có ở canary) **KHÔNG áp trên đường Tier A** → rác "Video Giải… Cô …(Giáo viên VietJack)… Xem lời giải… hay nhất, chi tiết" lọt ra mọi kết quả A_concept.
- **Coverage gap**: "định luật Ôm" (Vật lí 9) → "Hệ thống RAG chưa tìm thấy dữ liệu".

## Data nền (Neo4j edu, KnowledgeChunk theo subject_code)
ngu_van 9690 · tieng_viet 4898 · **toan 2665** · khtn 1529 · tieng_anh 1166 · sinh_hoc 1050 · hoa_hoc 684 · vat_li 579 · lich_su 497 · dia_li 353 · gdcd 152 · …

**Toán 2665**: lớp 1-9 đủ (l9=433…l1=41); bộ sách KNTT 821 / CTST 735 / none 572 / CD 506 / OLD 31. content_class = vietjack_lesson 1422 / vietjack_exercise 565 / NULL 460 / lgh_qa 218. chunk_type phần lớn NULL (1987). **concept_name = 0/2665** (không có concept gắn trên chunk). lesson_no chỉ 43%.
→ "vietjack_lesson" của Toán = **mục lục + Giải bài tập** (không phải định nghĩa/giảng sạch). Y hệt tình trạng Văn TRƯỚC pilot ("tra đáp án" ≠ "giảng bài").

## Kết quả test Toán (10 câu khái niệm, mọi lớp)
| Query | Bài RAG trả | Đúng |
|---|---|---|
| phân số là gì (6 CTST) | Bài 2: Các phép tính với **số thập phân** | ❌ |
| hai phân số bằng nhau (6 KNTT) | Bài 29: **số thập phân** | ❌ |
| số hữu tỉ là gì (7 CTST) | "Bài tập" generic | ❌ |
| hằng đẳng thức đáng nhớ (8 KNTT) | Bài 5: **chia đa thức** | ❌ |
| **định lí Pytago (8 CTST)** | Bài 2: **chọn dạng biểu đồ** (thống kê) | ❌❌ |
| căn bậc hai số học (9 KNTT) | Bài 3.32 (1 bài tập lẻ) | ❌ |
| góc nội tiếp (9 CTST) | đường tròn **ngoại tiếp** | ⚠️ |
| diện tích hình tam giác (5 KNTT) | Bài 50: diện tích xq **hình khối** | ❌ |
| ước chung lớn nhất (6 KNTT) | **Bội** chung nhỏ nhất | ⚠️ |
| đơn thức là gì (8 CTST) | Bài 1: Đơn thức và đa thức | ✅ |
**1/10 đúng bài · 9/10 dính rác.** Prod :8888 xác nhận giống hệt (phân số/Pytago/diện tích tam giác).

## Kết quả test cross-subject (8 câu)
| Query | Môn | Trả | Đúng |
|---|---|---|---|
| lực ma sát là gì | KHTN 6 | Bài 44: Lực ma sát | ✅ |
| khởi nghĩa Lam Sơn | Sử 7 | Bài 16: Khởi nghĩa Lam Sơn | ✅ |
| khí hậu Việt Nam | Địa 8 | Bài 4: Khí hậu Việt Nam | ✅ |
| tế bào là gì | KHTN 6 | Trắc nghiệm Cánh diều | ❌ |
| quang hợp là gì | KHTN 6 | "Bài tập" generic | ❌ |
| hệ tuần hoàn ở người | Sinh 8 | Trắc nghiệm bài 30 | ❌ |
| phản ứng oxi hóa khử | Hóa 8 | Trắc nghiệm bài 7 | ❌ |
| định luật Ôm | Lý 9 | KHÔNG có data | ❌ |

## Nguyên nhân gốc
1. **Không có lớp "theory/định nghĩa" sạch** cho Toán/KHTN — chunk toàn Giải-bài-tập/Trắc-nghiệm. Hỏi "X là gì" không có gì đúng để trả.
2. **Concept→chunk linkage hỏng** (Toán: 0 concept trên chunk; COVERS orphan; F1 collision exercise_no↔lesson_no). Tier A gắn concept đúng nhưng kéo về chunk sai bài.
3. **Vector fallback yếu** cho khái niệm trừu tượng (Pytago→biểu đồ).
4. **sanitize không áp trên Tier A serve path** → rác lọt mọi môn.

## Khuyến nghị (ưu tiên)
- **Quick win toàn hệ thống (rẻ, an toàn)**: áp `sanitize_chunk_text()` trên đường Tier A khi serve → sạch rác VietJack cho MỌI môn ngay, không đụng data. (Vẫn không sửa "sai bài", nhưng hết lộ nguồn/rác.)
- **Companion/Lesson-card cho Toán** = cần nhất nhưng khác Văn: Toán **concept-centric** (neo theo khái niệm: phân số, Pytago, hằng đẳng thức) chứ không work-centric. Cần: crawl/synth theory sạch (định nghĩa + công thức + ví dụ) + content-vector tier (như pilot) + sửa concept linkage. KHTN tương tự (định nghĩa + ví dụ).
- **Sử/Địa**: đã tạm ổn vì "bài"="chủ đề" → ưu tiên thấp, chỉ cần sanitize + bổ recite/tóm tắt.
- **Coverage**: bổ data nơi trống (Vật lí "định luật Ôm").

## Tái lập
Script (server, read-only RAG calls): `/tmp/toan_probe.py`, `/tmp/multi_probe.py`. Profile `{lop, bo_sach, subject}`. Đổi `localhost:8889`↔`8888` để so canary/prod.
