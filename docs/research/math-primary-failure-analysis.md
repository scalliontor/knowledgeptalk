# Toán tiểu học 4–6 — phân tích gốc rễ anchoring (data-driven)

> **Nguồn**: `reports/backtest/2026-06-17_full-sweep/` (full sweep, port 8890 merged). Phân tích từ `by_dimension` + `sample_fails` (30 fail/quyển). KHÔNG chạy lại test, KHÔNG sửa router. Đề xuất vá ở cuối — **chưa implement**.

## 1. Số liệu thật theo dimension (anchor%)

| Quyển | anchor tổng | current_lesson | name_query | trang_query | trang_profile | content_only | practice |
|---|---|---|---|---|---|---|---|
| toan 4 CTST | **75.1** | **100.0** | 95.1 | 52.6 | 67.4 | 31.8 | 100.0 |
| toan 5 CTST | **76.5** | **100.0** | 93.8 | 55.6 | 64.3 | 31.8 | 100.0 |
| toan 6 KNTT (gộp) | **79.1** | **100.0** | 93.8 | 55.6 | 74.1 | 38.7 | 100.0 |
| toan 6 KNTT t1 | 84.9 | 100.0 | 94.6 | 85.7 | 83.3 | 43.0 | 100.0 |
| toan 8 CD t1 | 79.1 | 100.0 | 75.0 | 96.3 | 95.5 | 23.2 | 100.0 |
| toan 8 CTST t1 | 78.6 | 76.8 | 89.8 | 100.0 | 100.0 | 42.9 | 79.3 |

> Lưu ý: con số "82–86%" trong canonical là anchor đo trên run sweep trước/biên khác; full-sweep file cho thấy mẫu hình GIỐNG NHAU — **đường `current_lesson` = 100%**, tụt nằm ở `content_only` và `trang_*`.

## 2. Phân loại định lượng (sample_fails, 30/quyển)

Loại "got" của fail (server trả về cái gì khi sai):

| Quyển | got_none (từ chối) | got_A_concept | got_wrong_card | got_wrong_practice |
|---|---|---|---|---|
| toan 4 CTST | 2 | 0 | 9 | 19 |
| toan 5 CTST | 2 | 3 | 12 | 13 |
| toan 6 KNTT | 11 | 5 | 6 | 8 |
| toan 6 KNTT t1 | 7 | 7 | 9 | 7 |
| toan 8 CD t1 | 9 | 7 | 10 | 4 |
| toan 8 CTST t1 | 13 | 14 | 1 | 2 |

Dimension của fail:

| Quyển | content_only | trang_query | trang_profile | name_query | current_lesson | practice |
|---|---|---|---|---|---|---|
| toan 4 CTST | 17 | 5 | 6 | 2 | 0 | 0 |
| toan 5 CTST | 16 | 7 | 5 | 2 | 0 | 0 |
| toan 6 KNTT | 22 | 6 | 0 | 2 | 0 | 0 |
| toan 6 KNTT t1 | 21 | 5 | 2 | 2 | 0 | 0 |
| toan 8 CD t1 | 19 | 0 | 1 | 10 | 0 | 0 |
| toan 8 CTST t1 | 18 | 0 | 0 | 3 | 4 | 5 |

## 3. Trả lời 4 câu hỏi gốc rễ

**(a) Sai do title dài?** — **Không phải nguyên nhân chính.** Đường `name_query` (nêu tên bài) đạt 93–95% ở toan 4/5/6. Khi học sinh nói tên bài, match work_name OK kể cả tên dài. Ngoại lệ: **toan 8 CD t1 name_query = 75%** vì tên bài chứa **công thức/biến** (`Đồ thị của hàm số bậc nhất y = ax + b`, `Hàm số bậc nhất y = ax + b`, `Đơn thức nhiều biến. Đa thức...`) — học sinh đọc gọn ("bài hàm số bậc nhất") không trùng chuỗi đầy đủ ⇒ **scorer exact-match fail** dù neo đúng họ bài. Đây là **long/formula-title norm**, đặc thù Toán 8+, không phải Toán tiểu học.

**(b) Title gần nhau (cluster)?** — **CÓ, là nguyên nhân #1 của `content_only`/`trang_*`.** Khi không có anchor cứng, content-vector phải chọn giữa các bài cùng chương embed gần nhau (đã ghi nhận pilot: top1=0.655 vs top2=0.645). Bằng chứng trong `got_wrong_*`: hầu hết là **đúng-chương sai-bài**:
- `cách nhân một số với một tổng` → got `Nhân với số có một chữ số` exp `Tính chất giao hoán...` (đều chương phép nhân).
- `làm sao đưa 2 phân số về cùng mẫu` → got `Phân số` exp `Trừ hai phân số khác mẫu` (đều chương phân số).
- `có dấu ngoặc thì làm cái nào đầu tiên` → got `Quy tắc dấu ngoặc` exp `Thứ tự thực hiện các phép tính`.

→ Các fail này **sạch nguồn, đúng chương**, sai bài chính xác. Production che bằng `current_lesson`.

**(c) Thiếu current_lesson?** — **ĐÚNG, đây là cấu trúc của gap.** 100% fail nằm ở dimension **không có** `current_lesson` (content_only / trang_query / trang_profile / name_query). Dimension `current_lesson` = 0 fail (trừ toan 8 CTST t1, xem dưới). Tức **gap = ca thiếu anchor**, không phải đường anchored hỏng. Đây trùng với gap #4 canonical (client gửi `{}`): nếu client luôn gửi `current_lesson`, gap Toán tiểu học gần như biến mất.

**(d) Vector override structured?** — **Hầu như KHÔNG ở Toán tiểu học.** Các fail là vector chọn-trong-vùng-mờ khi **vốn không có structured** (content_only). KHÔNG thấy ca có `trang`/`name` đúng mà bị vector ghi đè. Ngoại lệ cảnh báo: **toan 8 CTST t1 có 4 fail dimension `current_lesson` + practice 79.3%** — đây là quyển DUY NHẤT current_lesson < 100% (76.8%), nghi vấn riêng (xem #4), KHÔNG đại diện Toán tiểu học.

### Kết luận gốc rễ
1. **Gap Toán tiểu học ≈ gap "thiếu anchor + cluster bài cùng chương"**, không phải lỗi retrieval đường anchored.
2. Khi có anchor (`current_lesson`/`name`): 93–100%. Khi không: content-vector rơi vào vùng mờ giữa các bài na ná.
3. `content_only` thấp (22–43%) phần lớn là **từ chối-đúng hoặc đúng-chương-sai-bài-sạch**, không vi phạm "sạch nguồn"/"không bịa".
4. Hai vấn đề norm phụ, đặc thù lớp lớn: **formula-title** (toan 8 CD name_query 75%) và **toan 8 CTST t1 current_lesson 76.8%** (anomaly cần điều tra, có thể tên bài có dấu `–` gạch ngang dài / khoảng trắng — giống lỗi Lịch sử).

## 4. Anomaly toan 8 CTST t1 (cần ưu tiên xác minh)

current_lesson 76.8% (các quyển khác 100%) + practice 79.3% + got_none 13/30 + got_A_concept 14/30. Nhiều fail là `got none`/`got A_concept` ngay cả khi expected là bài cụ thể (`giải thích hộ em cái này với` + current_lesson → none). Giả thuyết: **tên bài chứa gạch ngang dài `–`** (`Hình bình hành – Hình thoi`, `Hình thang – Hình thang cân`, `Hình chữ nhật – Hình vuông`, `Cộng, trừ phân thức`) khiến `current_lesson` client gửi (hoặc work_name DB) lệch chuỗi với tên server resolve ⇒ exact-match fail. **Cùng họ lỗi với Lịch sử** (`history-work-name-normalization.md`). Cần verify bằng truy DB so `work_name` vs ký tự gạch ngang (`–` U+2013 vs `-` U+002D).

## 5. Đề xuất hướng vá AN TOÀN (chưa implement)

> Nguyên tắc: **không đụng gate đang chạy, không hạ ngưỡng "sạch nguồn"**. Mỗi vá có backtest đo trước/sau.

### V1 — Canonical alias cho lesson/concept title Toán (data-only, rủi ro thấp nhất)
- **Làm gì**: thêm trường `work_name_aliases` (mảng) hoặc Concept alias cho bài có **công thức/biến/gạch ngang**: `Đồ thị của hàm số bậc nhất y = ax + b` ⇄ {`đồ thị hàm số bậc nhất`, `hàm số bậc nhất`}; `Hình bình hành – Hình thoi` ⇄ {`hình bình hành`, `hình thoi`}. Match work_name OR bất kỳ alias (sau fold).
- **Vá đâu**: lớp DATA (build_book_generic / backfill), KHÔNG đụng retrieval logic. Chuẩn hoá gạch ngang `–`→`-` và collapse khoảng trắng trong `fold()` (mở rộng `norm()`).
- **Rủi ro**: alias quá rộng có thể làm 1 alias khớp nhiều bài → cần alias **đặc trưng** (≥1 token phân biệt), ưu tiên longest-match. Thấp.
- **Đo**: backtest lại 6 quyển này; kỳ vọng `name_query` toan 8 CD 75→≥90, current_lesson toan 8 CTST 76.8→≥95. Anchor tổng các quyển không tụt; cruft phải vẫn 0; guard không đổi.

### V2 — Tăng trọng số deterministic khi có current_lesson (logic, rủi ro trung bình)
- **Làm gì**: khi `user_profile.current_lesson` có giá trị và resolve được 1 `:Lesson` trong scope, **khoá** kết quả vào bài đó, bỏ qua content-vector hoàn toàn (đã gần như vậy ở bậc 1 — chỉ cần đảm bảo không có nhánh nào để vector ghi đè current_lesson).
- **Rủi ro**: nếu `current_lesson` client gửi là chuỗi rác/không khớp bài nào → cần fallback có kiểm soát (fuzzy match alias trước khi bỏ qua). Trung bình.
- **Đo**: kiểm tra dimension `current_lesson` = 100% mọi quyển (bắt anomaly toan 8 CTST t1); guard không tụt.

### V3 — Chặn vector override khi structured score cao (logic, rủi ro trung bình-cao)
- **Làm gì**: nếu có `trang`/`name` resolve được bài với độ tin cao (trang nằm gọn trong 1 `[trang_from,trang_to]` duy nhất), KHÔNG cho content-vector thay đổi kết quả.
- **Rủi ro**: với Toán tiểu học **không thấy** ca vector override structured trong dữ liệu ⇒ lợi ích nhỏ ở môn này; chủ yếu phòng ngừa. Áp dụng phải cẩn thận với trang chồng nhiều bài (1 trang = nhiều bài). Trung bình-cao vì đụng nhánh quyết định.
- **Đo**: trang_query/trang_profile toan 4/5 (52–67%) — kỳ vọng tăng phần do biên trang, nhưng phần lớn fail trang_* là **đúng-chương-sai-bài cluster** nên cải thiện có giới hạn.

### KHÔNG nên làm
- KHÔNG hạ floor content-vec để "cứu" content_only — sẽ kéo guard out-of-book/chitchat tụt (đã thấy ở MULTISUBJECT_SCALE). content_only thấp ≠ gap production.
- KHÔNG ép card khi không có anchor — vi phạm "từ chối ngoài bài".

## 6. Ưu tiên đề xuất
1. **V1 (alias + chuẩn hoá gạch ngang/space)** — rẻ, an toàn nhất, đánh trúng formula-title (toan 8 CD) + nghi anomaly toan 8 CTST t1.
2. **V2** — củng cố đường production thật (current_lesson), bắt anomaly.
3. **V3** — phòng ngừa, lợi ích đo được thấp ở Toán tiểu học → để sau.

Mọi vá đo bằng `backtest_book.py` (cùng seed 42) trên đúng 6 quyển + so `by_dimension` trước/sau; gate release theo canonical (anchor ≥97, guard ≥98.1, cruft=0, P95 trong ngưỡng).
