# Báo cáo kiểm định NỘI DUNG RAG vs bản gốc SGK
> 76 bài anh feedback "có nhưng đọc thiếu/sai/thừa" — 4 agent đối chiếu nguyên văn RAG thực đọc với bản gốc. 2026-07-08.

## 🔑 Kết luận nhanh
1. **Tuyến định tuyến ổn** — chỉ 2 ca đọc-nhầm-bài thật (WRONG_WORK). RAG khai NOT_FOUND trung thực (không bịa) → nhiều feedback cũ "đọc bài khác" nay đã hết (do bản-honest hôm nay).
2. **Vấn đề #1 = SAI TỪ (lỗi OCR trong text nguồn đã lưu)** — phổ biến ~30 bài, nhất là **văn xuôi THCS/THPT**. Chữ hỏng kiểu `phải→pahri`, `khỉ→khi`, `đáy→đầy`, `Bà mơ→Ba mơ`. Đây là lỗi dữ liệu nguồn crawl, KHÔNG phải đọc sai bài.
3. **Nhiều feedback "đọc thiếu câu" là do TTS runtime, KHÔNG phải data** — text lưu ĐỦ (vd Vội vàng, Con đường mùa đông, Cảm hoài, Muối của rừng, Trong lòng mẹ đều đủ). Đừng đuổi theo "ghost".

## 🔴 A. ĐỌC NHẦM BÀI (WRONG_WORK) — sửa node
- **Cậu bé thông minh (L3)** → đọc truyện Lương Thế Vinh (lấy bóng/bưởi dưới hố). Đúng phải là truyện cổ tích vua bắt nộp gà trống biết đẻ.
- **Bàn tay cô giáo (L3)** → đọc bản "Tết tóc/Vá áo". SGK TV3 là bản GẤP GIẤY "Một tờ giấy trắng / Cô gấp cong cong". (Cùng text này phục vụ cả L1 — cần tách bản đúng theo lớp.)

## 🟠 B. ĐỌC THỪA / SAI CẤP (THUA) — lọc/siết
- **Cross-grade over-read**: hỏi **lớp 4** nhưng đọc **bản đầy đủ lớp 9**: "Khúc hát ru…", "Đoàn thuyền đánh cá", "Bài thơ về tiểu đội xe không kính" (SGK L4 chỉ TRÍCH vài khổ). → grade-free đọc bản dài nhất.
- **Lặp/thừa khổ**: "truyện cổ nước mình" (12 dòng in trùng 2 lần), "Mặt trời xanh của tôi" (thêm 1 khổ ngoài SGK).
- **Đuôi rác crawl đọc thành tiếng**: "Em vẽ Bác Hồ" (dính "Đồng Dao Thả Đỉa Ba Ba/Giáo Án/emoji"), "những con sếu bằng giấy" (đuôi "Lòng Dân Lớp 5"), "việt nam" (đuôi `<img src`), "vua tàu thủy" (đuôi câu hỏi đọc hiểu + header "trang 56").

## 🟡 C. SAI THỨ TỰ (SAI_THUTU)
- **Mưa (L3, Trần Tâm)** — 5 khổ bị ĐẢO: chèn "Bà xỏ kim" lên khổ 2, "Gió reo gió hát" xuống cuối, chèn "(Trần Tâm)" vào giữa.
- **Thời gian (L11, Văn Cao)** — bỏ 2 chữ "còn xanh" sau "câu thơ"/"bài hát", đặt sai 1 "còn xanh" vào "đôi mắt em".

## 🟣 D. SAI BẢN / DỊCH SAI (BAN_KHAC) — thay bản
- **Nam Quốc Sơn Hà (L8)** — dịch thơ SAI bản: đọc "Đất nước Đại Nam, Nam đế ngự…". SGK KNTT dùng bản Lê Thước–Nam Trân "Sông núi nước Nam vua Nam ở / Vằng vặc sách trời chia xứ sở…". → thay.
- **Ngưỡng cửa (L1)** — đọc 4 khổ, SGK TV1 chỉ 3 (khổ 4 "Nơi ấy ngôi sao khuya…" thừa) + "Nơi này→Nơi ấy".

## 🔵 E. SAI TỪ / LỖI OCR (SAI_TU) — cần dọn text nguồn (nhóm LỚN NHẤT)
Text đúng bài, đủ, nhưng chữ hỏng. Ví dụ nặng (đổi nghĩa):
- **Quạt cho bà ngủ**: "**Ba** mơ tay cháu" → phải "**Bà** mơ"; "Cốc chén **lặng** im"→"**nằm** im"; "hoa **xoan**"→"hoa **cam**".
- **Anh Đom Đóm**: "long lanh **đầy** nước" → "**đáy** nước".
- **Muối của rừng (L12)**: chữ "**khỉ**" → "**khi**" khắp bài (con khi, đàn khi…).
- **Nhiều bài** dính `pahri`(phải), lỗi dấu/OCR: Cây tre VN, Bức thư thủ lĩnh da đỏ, Sự tích Hồ Gươm, Sọ Dừa, Thạch Sanh, Chân-Tay-Tai-Mắt-Miệng, Lặng lẽ Sa Pa, Những ngôi sao xa xôi, Xe Đêm, Trong Lòng Mẹ, Hịch tướng sĩ, Ta đi tới, Ai đã đặt tên cho dòng sông, Hải khẩu linh từ, Lời tiễn dặn (có chuỗi vô nghĩa "sĩ giới không nung"), Trở về (chuỗi hỏng "những Bảy Bảo…"), Cảm hoài, Mộ, Nguyên tiêu ("giữa **lòng**"→"giữa **dòng**"), Tôi có một ước mơ…

## ⚪ F. NOT_FOUND — thiếu data (feedback cũ đã lỗi thời, KHÔNG phải lỗi đọc)
Bài SGK CÓ THẬT nhưng kho chưa có, RAG từ chối trung thực: Cuộc họp của chữ viết, Ở lại với chiến khu, Chú ở bên Bác Hồ, Trên đường mòn HCM, Rước đèn ông sao, Con rồng cháu tiên, Thầy bói xem voi, Lợn cưới áo mới, Thi nhạc, nụ cười mang tên mùa xuân.

## ✅ G. RAG ĐÚNG — feedback là false-positive (đa phần do TTS)
Khi mẹ vắng nhà, Mùa thu của em, Ngày hội rừng xanh, Một mái nhà chung, Chuyện cổ tích về loài người, Bài ca về trái đất, Trước cổng trời, Hạt gạo làng ta, Chú đi tuần, Cửa sông, Những cánh buồm, Lượm, Sơn Tinh Thủy Tinh, **Vội vàng (KHÔNG thiếu 3-4 câu cuối)**, Trong lòng mẹ (cuối OK), Con đường mùa đông (đủ), Cảm hoài (đủ), Muối của rừng (đọc hết), Lễ xướng danh, Thiên Trường vãn vọng.

## 📋 Hướng xử lý
| Nhóm | Số | Cách | Restart? |
|---|--:|---|---|
| A. Wrong-work | 2 | thay/xoá node sai, nạp bản đúng | data-only |
| B. Thừa/rác/cross-grade | ~9 | strip đuôi rác (data); cross-grade cần grade-anchor (code) | 1 phần cần restart |
| C. Sai thứ tự | 2 | re-crawl 2 bài từ nguồn sạch | data-only |
| D. Sai bản dịch | 2 | thay bản đúng | data-only |
| E. **Sai từ/OCR** | **~30** | **dọn OCR (re-crawl thohay sạch / sửa từ điển lỗi)** | data-only |
| F. Not-found | 10 | cào bù (nhiều bài obscure, khó) | data-only |
| G. False-positive | ~20 | KHÔNG cần làm gì (báo lại tester: lỗi TTS) | — |
