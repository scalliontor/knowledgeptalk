# PILOT TEST GUIDE — Bạn-đồng-hành Ngữ văn 9 CTST tập 2

> Companion (Lesson Card) chạy trên **canary :8889** (prod :8888 KHÔNG đụng). 13 bài tập 2 đã dựng `:Lesson`.
> Cập nhật creds trong [server.txt](../../server.txt) — KHÔNG chép mật khẩu vào file này.

## 1. Mở Swagger UI (qua SSH tunnel — vì :8889 không mở ra ngoài)
Trên máy anh:
```bash
ssh -L 8889:localhost:8889 namnx@171.226.10.121   # giữ phiên này mở
```
Rồi mở trình duyệt: **http://localhost:8889/docs** (Swagger UI) — bấm `POST /retrieve` → "Try it out".
OpenAPI JSON: http://localhost:8889/openapi.json

## 2. Endpoint + body
`POST /retrieve` (hoặc `/v2/rag/retrieve`). Body:
```json
{
  "query": "<câu hỏi giọng học sinh>",
  "user_profile": {
    "lop": 9,
    "bo_sach": "CTST",
    "subject": "ngu_van",
    "current_lesson": "<TÊN BÀI ĐANG HỌC, vd: Sông Đáy>"
  }
}
```
**Các trường `user_profile`** (free dict, Swagger không liệt kê chi tiết):
| field | ý nghĩa | giá trị |
|---|---|---|
| `lop` | lớp | 9 |
| `bo_sach` | bộ sách (mã ngắn) | `CTST` / `KNTT` / `CD` |
| `subject` | môn | `ngu_van` |
| `current_lesson` | **bài đang học** (chốt companion) | tên tác phẩm (vd "Tì bà hành") |

→ Companion fire khi: **`current_lesson` khớp bài** · **tên bài trong `query`** · HOẶC **số trang trong `query`** (vd "trang 69").

**3 chế độ theo ý định câu hỏi (cùng 1 bài):**
| Hỏi kiểu | tier | Trả về |
|---|---|---|
| "giảng / X là gì / bố cục / nội dung" | `lesson_card` | Thẻ giảng (tác giả/bố cục/nội dung/giá trị + câu hỏi gợi mở) |
| "làm bài tập / luyện tập / giải câu" | `lesson_practice` | Câu hỏi SGK + **gợi ý**, đáp án tag "[chỉ hé khi cần]"; `delivery_mode=guided_practice` (LLM ra câu hỏi+gợi ý trước, giữ đáp án) |
| "đọc thuộc / đọc diễn cảm" | `lesson_recite` | Nguyên văn tác phẩm |

13 bài đều có `practice_json` (tổng 55 câu luyện tập, gợi ý do Gemma sinh — không lộ đáp án).

### Tra theo TRANG (đã wire)
13 bài có `trang_from/trang_to` (phủ liền mạch tập 2). Gõ số trang là ra đúng bài:
```json
{ "query": "giảng bài trang 69 cho tớ", "user_profile": { "lop": 9, "bo_sach": "CTST", "subject": "ngu_van" } }
```
→ trang 69 = **Hai chữ nước nhà** · 130 = Sông Đáy · 124 = Mùa xuân chín · 40 = Ngôi mộ cổ. (Dải trang ước lượng từ mục lục + page-ref; trang kỹ-năng/ôn-tập sẽ map về bài đọc liền trước.)

## 3. Ví dụ curl (chạy trên máy đã tunnel, hoặc đổi sang localhost trên server)
```bash
# A. Đồng hành: học sinh đang học Sông Đáy, hỏi chung chung
curl -s -X POST http://localhost:8889/retrieve -H 'Content-Type: application/json' -d '{
  "query":"giảng cho em bài này với","user_profile":{"lop":9,"bo_sach":"CTST","current_lesson":"Sông Đáy"}}'

# B. Hỏi nêu tên bài
curl -s -X POST http://localhost:8889/retrieve -H 'Content-Type: application/json' -d '{
  "query":"tác giả bài Tì bà hành là ai","user_profile":{"lop":9,"bo_sach":"CTST"}}'
```
Kết quả: `context` bắt đầu `[ĐỒNG HÀNH BÀI HỌC]` gồm Tác giả/Hoàn cảnh/Thể loại/Bố cục/Nội dung chính/Giá trị + Câu hỏi gợi mở; `intent.tier="lesson_card"`, `intent.work_name`, `intent.trang`.

## 4. 13 bài đã có Lesson Card (tập 2)
Sông Đáy · Tì bà hành · Mùa xuân chín · Hai chữ nước nhà · Cái bóng trên tường · Kí ức tuổi thơ · Cái roi tre · Ngôi mộ cổ · Kẻ sát nhân lộ diện · Cách suy luận · Đấu tranh cho một thế giới hoà bình · Bài phát biểu của TTK LHQ về biến đổi khí hậu · Bức thư tưởng tượng

## 5. Test cases Gemma sinh sẵn (52 case)
File: [van9_ctst_t2_testcases.json](van9_ctst_t2_testcases.json) — 4 câu/bài, giọng học sinh thật.
Chạy hàng loạt (trên server): `venv/bin/python /tmp/run_tests.py` → baseline hiện tại **52/52 = 100%** vào đúng `lesson_card`.

## 6. Trạng thái sau test mạnh (35 query Gemma + adversarial)
**Đã chạy đúng:** by_name 8/8 · by_page (bài đọc) đúng · current_lesson 5/5 · typo không dấu OK · trang ngoài sách/chitchat không bịa.
**Đã sửa (2026-06-11):**
- ✅ **"Đọc thuộc"** → trả **nguyên văn** (`tier=lesson_recite`), vd "đọc thuộc Mùa xuân chín" ra cả bài thơ Hàn Mặc Tử.
- ✅ **Dải trang theo mốc cấu trúc** (THTV 15/46/74/104/128, ôn tập, tri thức) → trang luyện-tập (74, 104...) **KHÔNG map nhầm** vào bài đọc liền trước nữa.

**Còn lại (honest):**
- Trang kỹ-năng/ôn-tập (vd 74) trả `tier=A_structured`/None (chưa có câu "đây là phần Thực hành tiếng Việt") — chấp nhận được, không sai bài.
- Dải `trang_from/to` vẫn là **ước lượng từ page-ref** (chưa phải span chính xác từng trang SGK) — anh test sách thật thấy lệch bài nào báo tôi chỉnh.
- Câu trần "X là gì" / khái niệm tiếng Việt không kèm bài → chưa có theory dạng thẻ.
- Mới **canary :8889**; prod :8888 nguyên vẹn.
