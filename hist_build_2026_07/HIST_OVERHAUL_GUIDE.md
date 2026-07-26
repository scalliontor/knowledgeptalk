# Đại tu môn Lịch sử — chẩn đoán + kế hoạch T1/T2/T3 (2026-07-26)

> User ghi nhận "Sử sai rất nhiều" → verify có số liệu → kết luận: **phần lớn là vấn đề DATA**, phần còn lại là retrieval mù môn. Xử lý toàn tuyến lớp 4-12.

## 1. Chẩn đoán (đã verify trên prod :8888 + Neo4j :7688)

### Ba lớp bệnh
1. **Retrieval mù môn**: router trả `subject=None` cho 11/12 câu sự kiện → gate `$subject IS NULL OR k.subject_code=$subject` thành pass-through → câu Sử kéo chunk Ngữ văn/Hóa. VD "ĐBP **trên không** (1972)" → chunk Văn 6 về ĐBP 1954 → LLM tóm tắt trung thực chunk sai → bịa "1973"; "kế hoạch Nava" → *Giải Hóa 10*.
2. **Coverage**: `lich_su` ≈1003 node nhưng **chỉ THCS L6-9**; **THPT L10-12 = 0, tiểu học L4-5 = 0** — đúng chỗ user ghi lỗi dày nhất (L11/L12 mỗi bài 4-7 lỗi dữ kiện).
3. **Độ sâu**: node L6-9 là "Lý thuyết" tóm tắt nông — thiếu chi tiết SGK hỏi (ngày ký Giơnevơ 21/7, nơi ký Tạm ước = Paris, TBT Đại hội II = Trường Chinh…).

### Đối chiếu data-vs-retrieval trên 15 lỗi tiêu biểu user ghi
| Phân loại | Số ca | Nghĩa |
|---|---|---|
| DATA GAP (kho không có fact → LLM bịa) | 8 | Tạm ước Paris, Đại hội III, Trần Phú, Nhật đảo chính, Đờ Lát, Giơnevơ 21/7… |
| DATA SAI MÔN (fact chỉ nằm trong chunk Văn) | 3 | ĐBP trên không, Nguyễn Hiền, Nguyễn Trung Trực |
| RETRIEVAL (data có, prod không lôi ra — **T1 đã chữa**) | 4 | 1925, 1930-31, 1929, 1871 đều có trong chunk lich_su và canary-T1 lôi ra đúng |

### Taxonomy lỗi từ checklist user (27 note + 2 sheet)
1. Sai **năm/mốc** (~15) — nhiều nhất. 2. Sai **tên/thực thể** (~8). 3. Sai **quan hệ nhân-quả/trạng thái** (~10, tinh vi: "Nhật đầu hàng→kháng Nhật" thay vì "Nhật đảo chính Pháp→kháng Nhật") — chứng minh chunk văn xuôi + LLM tóm tắt KHÔNG đủ, cần fact-statement chốt sẵn. 4. **Bịa khi miss** (Nguyễn Minh Sát không có thật) — riêng câu **đố-ngược** (mô tả→tên) không trích được wiki_query → cần fact-node thuộc-tính hoặc abstain. 5. **Thiếu ý** (L4 "không sâu").

## 2. T1 — subject-gate (DONE trên canary :8893, chờ restart prod)
- Patch `rag_server_canary8892.py` (backup `.bak_pre_hist_t1_20260714`):
  (a) mở `LICHSU_FORCE_KEYWORDS` + cụm nhiều-từ (chiến dịch/cách mạng tháng/xô viết/tạm ước/hiệp định/tên triều-vua/trận…);
  (b) `_NORM_SYS` thêm luật + few-shot ép câu sự kiện → `subject="lich_su"` (kể cả khi source=wiki).
- Kết quả 40 câu: gán đúng môn **3/30 → 24/30**, nhiễm chéo môn **1 → 0**; regression recite 4/4 OK.
- Giới hạn: KHÔNG trị va chạm trong-môn (1954 vs 1972) → cần T2.

## 3. T2 — lớp fact-card (:HistLesson + :HistEvent) — ĐANG BUILD
### Khung chương trình (data-only, ĐÃ ingest)
- Sheet "Lịch sử" xlsx = khung SGK hoàn chỉnh: **813 bài** L4-12 (8 khối: sách mới 3 bộ + sách cũ). Dedup đa-bộ (difflib ≥0.72 trong cùng lớp) → **411 chủ đề** (`hist_topics.json`).
- Đã nạp **808 `:HistLesson`** {grade, bo_sach(KNTT|CTST|CD|CU), bai_no, title, title_norm, subject_code='lich_su', ingest_batch='hist_v1_2026_07_26'} — script `ingest_hist_lessons.py` (creds qua env). Rollback: `MATCH (l:HistLesson {ingest_batch:'hist_v1_2026_07_26'}) DETACH DELETE l`.

### Fact-card :HistEvent (workflow 34 chunk đang chạy)
Schema thẻ: `{name, aliases[], kind(event|campaign|battle|treaty|movement|person|dynasty|period|org|artifact|place|concept), year, date_start, date_end, place, actors[], summary, facts[3-8 câu tự-đứng-được có mốc thời gian], traps[bẫy sai phổ biến + đáp án đúng], lessons[{book,bai}], sources[URL]}`.
Dây chuyền mỗi chunk: **gen** (web-grounded: vi.wikipedia/nguoikesu/.gov.vn, KHÔNG chép SGK — dữ kiện không được bảo hộ bản quyền, diễn đạt tự viết) → **cổng tất định** trong script (year sanity, 3-12 facts, có URL, chống cruft soạn-bài) → **verifier đối kháng** kiểm độc lập từng thẻ, sửa-có-bằng-chứng/loại, tự đắp thẻ cho bẫy còn thiếu → ghi `verified_g{lớp}_c{chunk}.json`.
34 ghi chú lỗi của user (`ls_error_notes.json`) được nhồi vào prompt như **bẫy ưu tiên bắt buộc phủ**.

### Retrieval T2 (sẽ code trên canary, cần 1 restart khi lên prod)
Thứ tự tầng cho câu Sử: **(1) HistEvent exact/alias/year match** (rẻ, ms; câu chứa năm/định-ngữ ưu tiên event khớp year/alias — trị 1954-vs-1972) → **(2) KG chunk cùng subject** (gate T1) → **(3) wiki** (lưới đỡ, giữ nguyên budget/breaker) → **(4) abstain trung thực** (không bịa; đặc biệt câu đố-ngược không match).

## 4. T3 — coverage: fact-card lấp luôn L10-12 + L4-5 trong cùng đợt build (411 chủ đề đủ 9 lớp).

## 5. Đo lường
- `hist_battery.json`: ~40 câu regression đúc từ chính lỗi user ghi (expect/forbid marker) — chạy trước/sau trên :8888 vs :8893.
- Test cũ: `probe/cmp_hist_t1` 40 câu (3/30→24/30).

## 6. Trạng thái & việc còn
- [x] T1 canary + test; [x] :HistLesson 808; [x] battery; [ ] workflow fact-card xong → gate cuối + dedup liên-lớp → ingest :HistEvent (reversible); [ ] T2 hook canary + battery so sánh; [ ] **xin user restart prod** (gộp: T1 + few-shot recite 16/19 + T2).
- Nguyên tắc giữ nguyên: restart prod PHẢI XIN; data-only tự do nhưng backup per-eid; phán đoán agent phải có cổng tất định gác.
