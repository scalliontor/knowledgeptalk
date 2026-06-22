# North Star — Knowledge PTalk

> Nguồn: [project_state/2026-06-22-canonical.md](../project_state/2026-06-22-canonical.md) §North star. File này giải thích **vì sao**.

## Tuyên ngôn

> **Knowledge PTalk là lớp tri thức biến loa AI thành _bạn đồng hành học bài_, bám đúng _bài/trang SGK đang mở_ để _giảng · đọc · luyện_, _sạch nguồn_, _độ trễ thấp_, và _từ chối khi ngoài bài_ thay vì đoán.**

## 6 cam kết (mỗi cam kết là một ràng buộc thiết kế)

| Cam kết | Nghĩa cụ thể | Vì sao quan trọng |
|---|---|---|
| **Bạn đồng hành** (không phải search) | Một phiên = học **một bài cụ thể**; PTalk biết bé đang ở đâu trong SGK. | Trẻ học theo tiến trình lớp; trợ lý hữu ích là người ngồi cạnh cùng trang sách, không phải máy tìm kiếm. |
| **Bám đúng bài/trang đang mở** | Neo theo `current_lesson` → tên bài → `trang`+`tập` trước khi nghĩ tới vector. | Cùng một câu hỏi ("giảng bài này") chỉ đúng khi biết "bài này" là bài nào. Structured-first cho độ chính xác cao + rẻ. |
| **Giảng · đọc · luyện** | 3 ý định cốt lõi trên cùng một bài (không phải hỏi-đáp tổng quát). | Đây là 3 việc một gia sư làm với một bài: giảng lại, cho đọc thuộc, ra bài luyện có dẫn dắt. |
| **Sạch nguồn** | Không leak "vietjack", "xem lời giải", "video giải", "cô giáo VietJack". | Phụ huynh/giáo viên tin tưởng; nội dung phải nghe như bài giảng, không như trang web crawl. |
| **Độ trễ thấp** | Serve path **không gọi LLM** (Gemma-free); P95 ~193–368 ms. | Loa thoại cần phản hồi tức thì; LLM trong đường nóng = 2–3 s, hỏng trải nghiệm. |
| **Từ chối khi ngoài bài** | Không có neo / ngoài scope → **từ chối an toàn**, không đoán bừa. | Một gia sư tốt nói "cái này không trong bài hôm nay" chứ không bịa. Tin cậy > coverage. |

## Vì sao companion-theo-bài, KHÔNG phải Q&A mở

**Q&A mở** (hỏi gì đáp nấy, retrieve toàn corpus) nghe linh hoạt hơn nhưng sai với bài toán này:

1. **Ngữ cảnh quyết định đáp án đúng.** "Đọc thuộc bài này", "giảng phần đọc hiểu", "trang 86 nói gì" — đều vô nghĩa nếu không biết bé đang mở **bài nào, tập mấy**. Q&A mở phải đoán; companion thì _được thiết bị/hồ sơ cho biết_ vị trí.

2. **Structured-first thắng khi truy vấn có cấu trúc.** Vì input thật có lớp + bộ sách + bài + trang, một câu Cypher exact (`subject + grade + bo_sach + tap + lesson_no`) chính xác và rẻ hơn nhiều so với vector search toàn corpus. Vector chỉ là **fallback**, không phải đường chính.

3. **Trùng tập / trùng số là cái bẫy của Q&A mở.** "Trang 30" mơ hồ giữa Tập 1 và Tập 2 (sách reset số trang); "Bài 2" lặp ở mỗi chương. Companion scope theo `tap_no` + neo theo bài đang mở nên loại được nhập nhằng — Q&A mở thì không.

4. **Từ chối là tính năng, không phải thiếu sót.** Với trẻ em, đoán sai nguy hiểm hơn im lặng. Companion biết "bài hôm nay" nên có ranh giới rõ để từ chối; Q&A mở luôn cố trả lời nên dễ hallucinate.

5. **Độ trễ.** Đường companion structured-first không cần LLM router/generator → đáp nhanh. Q&A mở thường kéo theo LLM trong đường nóng.

> Hệ quả: thiết kế dữ liệu (node `:Lesson`, schema v3 ba lớp), routing (structured-first), và contract client (`current_lesson`/`trang`+`tap`) đều phục vụ north star này. Xem [lesson-card-model.md](lesson-card-model.md) và [goals-and-anti-goals.md](goals-and-anti-goals.md).

## Đo bằng gì (north star có số)

Baseline đo thực (full sweep 2026-06-17, ~40k case — xem canonical):
- **Anchor 97.0%** (đường production khi thiết bị gửi `current_lesson`/`trang`+`tap`).
- **Guard 98.1%** (từ chối đúng chitchat/ngoài bài).
- **Real source cruft = 0** (sạch nguồn đạt).
- **P95 193–368 ms** (độ trễ thấp đạt).

Mỗi cam kết ở trên ánh xạ tới một metric; một thay đổi làm tụt metric tương ứng = đi ngược north star.

---
Liên quan: [goals-and-anti-goals.md](goals-and-anti-goals.md) · [lesson-card-model.md](lesson-card-model.md) · [user-journeys.md](user-journeys.md) · [canonical](../project_state/2026-06-22-canonical.md)
