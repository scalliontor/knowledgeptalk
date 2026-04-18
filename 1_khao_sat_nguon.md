# Khảo sát nguồn Knowledge Base - Chatbot tiểu học lớp 1-5

## Tổng quan 3 bộ SGK mới (Chương trình GDPT 2018)

Cả 3 bộ đều được Bộ GD phê duyệt, trường tự chọn. Bạn **phải cover cả 3** vì không biết khách hàng dùng bộ nào.

1. **Kết nối tri thức với cuộc sống (KNTT)** - NXB Giáo dục VN, phổ biến nhất ở thành thị
2. **Chân trời sáng tạo (CTST)** - NXB Giáo dục VN, phổ biến miền Nam
3. **Cánh diều (CD)** - NXB ĐH Sư phạm TP.HCM + ĐH Sư phạm Hà Nội

## Ma trận nguồn dữ liệu - đánh giá chi tiết

| Nguồn | Độ tin cậy | Cấu trúc HTML | Coverage | Bản quyền | Khuyến nghị |
|-------|-----------|---------------|----------|-----------|-------------|
| **loigiaihay.com** | Cao | Nhiễu nhưng có pattern | Đầy đủ 3 bộ × 1-5 | Tư nhân, có rủi ro | **Primary** - crawl chính |
| **vndoc.com** | Trung bình | Nhiều popup/ads | Đầy đủ nhưng lặp nhiều | Tư nhân, có rủi ro | **Secondary** - bổ sung văn mẫu |
| **vietjack.com** | Trung bình | Tương tự loigiaihay | Đầy đủ | Tư nhân | Backup khi loigiaihay thiếu |
| **hoc247.net** | Trung bình | OK | Đầy đủ | Tư nhân | Bổ sung cho lớp 4-5 |
| **hanhtrangso.nxbgd.vn** | **Rất cao** | SPA, cần JS | SGK KNTT chính thức | **Chính thức NXB** | **Gold standard** - ưu tiên |
| **taphuan.nxbgd.vn** | **Rất cao** | SPA | Tài liệu giáo viên | **Chính thức NXB** | Cho dàn ý chuẩn |
| **sachmem.vn** | Cao | OK | SGK điện tử các bộ | **Chính thức** | Alternative hanhtrangso |
| **olm.vn** | Cao | SPA | Bài tập tương tác | Thương mại | Chỉ dùng làm tham khảo |
| **monkeyjunior.com.vn** | - | - | Đối thủ trực tiếp | - | **Nghiên cứu UX, không crawl** |

## Chiến lược 3 tầng nguồn

### Tầng GOLD - Nội dung chính thức NXB (ưu tiên cao nhất)
**Mục tiêu:** bài đọc SGK gốc, văn bản chuẩn, không được sai một chữ

- `hanhtrangso.nxbgd.vn` - đăng ký tài khoản miễn phí, SGK KNTT đầy đủ
- `sachmem.vn` - SGK cả 3 bộ
- File PDF SGK lưu hành nội bộ (nếu có quan hệ với giáo viên)

**Kỹ thuật:** vì đây là SPA (JavaScript), Scrapy thường không đủ. Cần dùng:
- Playwright/Selenium để render JS
- Hoặc tìm API endpoint mà frontend gọi (DevTools Network tab)

### Tầng SILVER - Trang giáo dục tổng hợp
**Mục tiêu:** hướng dẫn giải, dàn ý, bài mẫu, bài tập

- `loigiaihay.com` - cấu trúc URL tốt nhất để crawl
- `vietjack.com` - backup
- `hoc247.net` - bổ sung

**Kỹ thuật:** Scrapy + trafilatura là đủ

### Tầng BRONZE - Tham khảo chất lượng thấp
**Mục tiêu:** tăng đa dạng văn mẫu, nhưng phải filter mạnh

- `vndoc.com` - có nhiều duplicates
- Các blog giáo viên cá nhân

**Kỹ thuật:** crawl + dedup aggressive + LLM quality filter

## Thứ tự thực hiện (đề xuất)

```
Tuần 1-2: Crawl loigiaihay.com lớp 1-5 (Tầng Silver, dễ nhất)
         → Có baseline data để test pipeline
Tuần 3:  Crawl hanhtrangso.nxbgd.vn (Tầng Gold, khó hơn)
         → Có ground truth cho bài đọc SGK
Tuần 4:  Bổ sung vndoc.com + vietjack (Tầng Silver/Bronze)
         → Tăng diversity văn mẫu
Tuần 5:  Clean, dedup, quality filter
Tuần 6:  Index vào vector DB + eval
```

## Các loại content cần phân biệt rõ khi crawl

Với tiểu học lớp 1-5, content trên loigiaihay chia thành các nhóm:

| Nhóm | Đặc điểm | Ví dụ URL pattern | Metadata cần extract |
|------|----------|-------------------|----------------------|
| **Bài đọc SGK** | Có text bài gốc | `bai-X-ten-bai-trang-Y-...` | tên bài, trang, tuần, bộ sách |
| **Tập làm văn** | Dàn ý + văn mẫu | `tap-lam-van-...` | dạng bài (tả cây/người/...), lớp |
| **Luyện từ và câu** | Khái niệm ngữ pháp | `luyen-tu-va-cau-...` | khái niệm, ví dụ |
| **Chính tả** | Quy tắc chính tả | `chinh-ta-...` | quy tắc, ví dụ |
| **Kể chuyện** | Truyện + gợi ý kể | `ke-chuyen-...` | truyện gốc, kỹ năng kể |
| **Ôn tập** | Tổng hợp | `on-tap-trang-X-...` | chương, tuần |
| **Đề kiểm tra** | Đề thi + đáp án | `de-kiem-tra-...` | học kỳ, lớp, độ khó |

**Quan trọng:** KHÔNG được trộn các nhóm này vào cùng một vector collection. Mỗi nhóm có cách retrieve và generate khác nhau.

## Cảnh báo pháp lý (lặp lại từ cuộc trò chuyện)

Commercial use của nội dung scraped là **rủi ro**. Trước khi launch:

1. Đọc Terms of Use của mỗi trang
2. Tư vấn luật sư về sử dụng có biến đổi (transformative use)
3. Chuẩn bị plan B: dần thay thế bằng nội dung tự tạo/mua bản quyền
4. Nhớ: dùng làm **context cho LLM generate** (không hiển thị nguyên văn) an toàn hơn là **reproduce**

## Data bạn nên tự tạo SONG SONG với crawl

Kể cả crawl được nhiều, vẫn cần:

1. **Bảng chương trình theo tuần × lớp × bộ sách** (~ 35 tuần × 5 lớp × 3 bộ = 525 rows)
   - Nguồn: kế hoạch dạy học của Bộ GD (công khai, không bản quyền)
   - Nhập thủ công: 2-3 ngày công

2. **Bộ eval 200 câu hỏi từ trẻ thật**
   - Ghi âm trẻ em thực tế (con của bạn, của team)
   - Transcribe và phân loại
   - Quan trọng hơn bất kỳ data crawl nào

3. **Golden set: 50 câu trả lời mẫu** cho các câu hỏi phổ biến
   - Thuê 1 giáo viên tiểu học viết
   - Dùng làm benchmark cho output của chatbot
