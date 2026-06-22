# Lịch sử — chuẩn hoá work_name (gốc rễ gap 95.5%)

> **Nguồn**: `reports/backtest/2026-06-17_full-sweep/backtest_lich_su_*.json` (`by_dimension` + `sample_fails`). KHÔNG chạy lại test, KHÔNG sửa router. Đề xuất ở cuối — **chưa implement**.

## 1. Số liệu thật

| Quyển | anchor | current_lesson | name_query | trang_query | trang_profile | content_only | practice |
|---|---|---|---|---|---|---|---|
| lich_su 9 CTST | 73.2 | 79.0 | 93.8 | 100.0 | 100.0 | 28.6 | 70.1 |
| lich_su 6 KNTT | 80.0 | 100.0 | 87.8 | 91.9 | 91.4 | 21.8 | 100.0 |
| lich_su 6 CTST | 79.8 | — | — | — | — | — | — |

(Anchored toàn môn lich_su = 95.5% theo canonical; số trên là per-book trộn cả content_only nên thấp hơn.)

## 2. Phát hiện gốc rễ: suffix bộ-sách dính vào work_name (KNTT)

Bằng chứng trực tiếp từ `sample_fails` lich_su 6 KNTT — các fail `name_query` neo **đúng bài** nhưng FAIL vì **chuỗi không trùng**:

```
[name_query] got lesson_card:Vương quốc Phù Nam   exp "Vương quốc Phù Nam- Kết nối tri thức"
[name_query] got lesson_practice:Ấn Độ cổ đại      exp "Ấn Độ cổ đại- Kết nối tri thức"
[trang_query] got lesson_card:Sự biến chuyển...    exp "Ấn Độ cổ đại- Kết nối tri thức"
```

- **Ground-truth `expected_work` trong DB có suffix `- Kết nối tri thức`** (tên bộ sách KNTT dính vào cuối work_name khi crawl/ingest).
- Server trả về `work_name` **sạch** (`Vương quốc Phù Nam`).
- Scorer `norm(work)==norm(ew)` (exact sau fold) ⇒ **FAIL dù neo ĐÚNG bài**.

→ Đây là **lỗi DATA NORM ở `work_name` (ground-truth)**, KHÔNG phải retrieval chọn sai. Một phần điểm anchor "mất" của Lịch sử KNTT là **false-negative của scorer/data**, không phải lỗi runtime production (production không so exact-string với DB; nó trả card cho học sinh).

## 3. Phát hiện phụ: variant naming (gạch ngang / giới từ / biên trang) — CTST

Từ `sample_fails` lich_su 6 CTST:
```
[name_query]   got "Các vương quốc ở Đông Nam Á"  exp "Các vương quốc Đông Nam Á"   (thừa/thiếu giới từ "ở")
[trang_query]  got "Hy Lạp cổ đại"                exp "Ai Cập cổ đại"                (2 bài chung/kề trang)
[trang_profile]got "Vương quốc Chăm-pa từ..."    exp "Các vương quốc ở Đông Nam Á"   (biên trang)
```
- **Giới từ/dấu**: `Các vương quốc Đông Nam Á` vs `Các vương quốc ở Đông Nam Á` — khác 1 từ "ở" ⇒ exact-match fail. Cùng họ với gạch ngang `–`/`-`, năm trong ngoặc, số La Mã (`Bài II` vs `Bài 2`).
- **Biên trang Lịch sử**: bài Lịch sử dài, nhiều bài chung khoảng trang ⇒ `trang_query`/`trang_profile` đôi khi rơi vào bài kề (Ai Cập vs Hy Lạp cùng cụm "cổ đại").

## 4. lich_su 9 CTST: phần lớn là content_only (không phải work-name)

lich_su 9 CTST anchor thấp nhất (73.2) nhưng `sample_fails`: **18/30 = got_none, 10/30 = got_A_concept**, và **19/30 fail là dimension `content_only`** (mô tả mơ hồ kiểu "giai đoạn này có thắng lợi nào", "xu thế chung hiện nay là gì"). Đây là:
- **Từ chối-đúng** (got none khi không đủ neo) — đúng "không bịa".
- Câu nói về giai đoạn lịch sử rất gần nhau (1945–1954 / 1954–1965 / 1965...) → content-vector mờ.

→ lich_su 9 KHÔNG phải vấn đề work_name_norm; là **content_only đặc thù môn Sử** (timeline cluster). Không nên dùng để biện minh nới gate.

## 5. Đề xuất: tách `lesson_title_norm` vs `work_name_norm` + alias curated (chưa implement)

Hiện `backfill_worknorm.py` chỉ làm 1 trường: `work_name_norm = fold(work_name)`. `fold()` bỏ dấu + lowercase nhưng **KHÔNG** xử lý suffix bộ-sách, gạch ngang `–`, giới từ, số La Mã.

### Đề xuất A — chuẩn hoá data (rủi ro thấp, ưu tiên 1)
- **Strip suffix bộ-sách** khỏi `work_name`/`work_name_norm`: regex bỏ đuôi `-\s*(Kết nối tri thức|Chân trời sáng tạo|Cánh diều)` (và biến thể). Đây là rác ingest — nên dọn ở DATA, không ở runtime.
- **Mở rộng `fold()`**: `–`(U+2013)/`—`→`-`, collapse multi-space, optional strip giới từ rìa ("ở","của","từ" khi ở đầu/giữa cụm chuẩn). Áp đối xứng cho cả ground-truth lẫn server resolve.

### Đề xuất B — tách 2 trường norm (rủi ro thấp, cho match linh hoạt)
- `work_name_norm` (full, đã strip suffix) — dùng cho exact anchor.
- `lesson_title_norm` (canonical, đã strip giới từ/gạch ngang/năm) — dùng cho fuzzy fallback khi exact miss.
- Match: exact `work_name_norm` trước; nếu miss, thử `lesson_title_norm` (vẫn deterministic, không phải vector).

### Đề xuất C — alias curated cho Lịch sử (rủi ro thấp-trung bình)
- Bảng alias tay cho các cặp variant đã biết: `Các vương quốc Đông Nam Á` ⇄ `Các vương quốc ở Đông Nam Á`; số La Mã ⇄ Ả Rập; năm trong ngoặc bỏ/giữ. Curate từ chính `sample_fails`.

### Rủi ro & cách backtest
- **Rủi ro**: strip giới từ/gạch ngang quá tay có thể làm 2 bài khác nhau collide (vd "Ai Cập cổ đại" vs "Hy Lạp cổ đại" KHÔNG được merge — chúng khác token chính). Quy tắc: chỉ chuẩn hoá **ký tự/khoảng trắng/suffix bộ-sách**, alias chỉ thêm cho cặp đã verify; không bao giờ collapse 2 work_name có token định danh khác nhau.
- **Backtest đo**: chạy `backtest_book.py lich_su 6 KNTT None 500 <port>` + `lich_su 6 CTST` trước/sau; kỳ vọng `name_query` KNTT 87.8→≥95, anchor tổng tăng; **guard không tụt, cruft=0**. Verify riêng trên Neo4j: `MATCH (l:Lesson{subject_code:'lich_su'}) WHERE l.work_name CONTAINS 'Kết nối tri thức' RETURN count(*)` để đo số bài dính suffix.

## 6. Lưu ý quan trọng cho metric
Một phần "mất điểm" Lịch sử là **artefact của scorer exact-match + data bẩn**, không phải runtime sai. Trước khi tối ưu retrieval, **dọn data + chuẩn hoá norm** sẽ nâng anchor đo được mà KHÔNG đụng logic. Đây là vá rẻ và an toàn nhất cho gap #2.

## Tham chiếu mã
- `rag_edu/scripts/schema_v3_2026_06/backfill_worknorm.py` (L6-9 `fold()`, L11-13 set `work_name_norm`).
- `rag_edu/scripts/schema_v3_2026_06/v_a_work_name.py` (`fold()` + `extract_work` + SKILL_PAT blocklist).
- `rag_edu/scripts/schema_v3_2026_06/backtest_book.py` (L117-119 `norm()`, L139 exact-match).
