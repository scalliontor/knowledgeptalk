# Client → Knowledge PTalk: Required Context Contract

> **Status:** SPEC (new file, 2026-06-22). Đặc tả phía client. KHÔNG sửa runtime, KHÔNG sửa client thật (repo khác).
> **Source-of-truth:** [`docs/project_state/2026-06-22-canonical.md`](../project_state/2026-06-22-canonical.md).
> **Vì sao file này tồn tại:** baseline **anchor 97.0%** (full sweep 2026-06-17) **chỉ đạt khi app gửi context bài** (`current_lesson` / `trang` + `tap`). `rag_client` hiện gửi `{}` → rơi về [degraded mode](degraded-mode-behavior.md). Đây là gap #4 trong canonical.

---

## 1. Endpoint + shape (đã verify trong repo)

- **Endpoint:** `POST /retrieve` (alias `/v2/rag/retrieve`). Server: prod `:8888`, canary `:8889`.
- **Request body:**

```json
{
  "query": "<câu hỏi giọng học sinh, nguyên văn từ STT>",
  "user_profile": {
    "lop": 9,
    "bo_sach": "CTST",
    "subject": "ngu_van",
    "tap": 2,
    "current_lesson": "Sông Đáy",
    "trang": 130
  }
}
```

- **Response (các trường client phải đọc):**

| field | ý nghĩa |
|---|---|
| `intent.tier` | `lesson_card` / `lesson_practice` / `lesson_recite` (đã neo vào bài) · `noncard` / `none` (không neo) |
| `intent.work_name` | tên bài đã neo (rỗng khi không neo) |
| `intent.trang` | trang đã suy ra |
| `context` | bắt đầu bằng `[ĐỒNG HÀNH BÀI HỌC]` khi neo thành công |
| `choices[0].message.content` | câu trả lời (OpenAI-style) đưa xuống TTS |

> Nguồn verify: `rag_edu/scripts/schema_v3_2026_06/backtest_book.py` (body `{"query","user_profile"}`, đọc `resp["intent"]["tier"]`/`["work_name"]`), `megatest.py`, `docs/pilot/TEST_GUIDE.md` §2.

---

## 2. Payload tối thiểu phía client (tên field theo ngôn ngữ client app)

Đây là cấu trúc **khuyến nghị cho client app** (đặt tên dễ đọc); §4 là bảng ánh xạ sang field mà server thực sự đọc.

```jsonc
{
  "student": { "grade": 9 },                 // -> lop
  "book": {
    "subject": "ngu_van",                    // -> subject
    "book_set": "CTST",                      // -> bo_sach
    "volume": 2                              // -> tap   (RẤT QUAN TRỌNG: chống trùng tập 1/2)
  },
  "current_lesson": {
    "lesson_id": "van9_ctst_t2_song_day",    // optional, future-proof
    "lesson_title": "Sông Đáy",              // -> current_lesson  (chốt companion)
    "page": 130                              // -> trang
  },
  "utterance": "giảng cho em bài này với"    // -> query
}
```

---

## 3. Bảng field: bắt buộc / khuyến nghị / ảnh hưởng anchor nếu thiếu

| Field (client) | -> server | Mức | Ảnh hưởng nếu THIẾU |
|---|---|---|---|
| `utterance` | `query` | **BẮT BUỘC** | Không có gì để truy hồi. Vô nghĩa. |
| `student.grade` | `lop` | **BẮT BUỘC** | Mất scope lớp → có thể neo nhầm bài cùng tên khác lớp; tụt anchor mạnh. |
| `book.subject` | `subject` | **BẮT BUỘC** | Mất scope môn → routing môn sai, dễ neo nhầm. |
| `book.book_set` | `bo_sach` | **BẮT BUỘC** | Mất scope bộ sách (CTST/KNTT/CD) → neo nhầm bài trùng tên giữa các bộ. |
| `book.volume` | `tap` | **KHUYẾN NGHỊ MẠNH** | Page reset giữa tập 1/2 → tra theo `trang` có thể trúng nhầm tập. Invariant "không trùng tập 1/2" yêu cầu trường này khi dùng `trang`. (toan8 KNTT: t1 96.4% / t2 98.8% **chỉ tách được nhờ `tap`**.) |
| `current_lesson.lesson_title` | `current_lesson` | **KHUYẾN NGHỊ MẠNH** | Mất "neo bài đang mở" → mất đường anchored (97%). Câu mơ hồ ("giảng bài này đi") rơi về content-vector hoặc **từ chối** (degraded). Đây là yếu tố #1 tạo nên 97%. |
| `current_lesson.page` | `trang` | KHUYẾN NGHỊ | Mất tra theo trang. Nếu `query` có sẵn "trang N" thì bù được phần nào; nếu không, mất 1 đường neo. **Phải đi kèm `tap`** để không trúng nhầm tập. |
| `current_lesson.lesson_id` | (chưa wire) | OPTIONAL | Future-proof. Server hiện neo theo `current_lesson` (tên) + `trang`+`tap`; `lesson_id` để dành cho neo theo ID khi runtime hỗ trợ. KHÔNG dựa vào hôm nay. |

**Quy tắc vàng:** client PHẢI gửi đủ 4 trường scope (`grade`, `subject`, `book_set`, `volume`) **và** ít nhất một neo bài (`lesson_title` ưu tiên, hoặc `page`+`volume`). Thiếu cả neo bài = degraded.

---

## 4. Ánh xạ field client → field profile server đọc (canonical)

Server đọc `user_profile` như free dict; **đúng tên key dưới đây mới có tác dụng**:

| Client field | Server profile key | Ghi chú |
|---|---|---|
| `student.grade` | `lop` | int (4–9) |
| `book.subject` | `subject` | mã môn: `ngu_van` `toan` `khtn` `lich_su` `dia_li` `gdcd` |
| `book.book_set` | `bo_sach` | `CTST` / `KNTT` / `CD` |
| `book.volume` | **`tap`** | int 1 hoặc 2. **volume → tap** (đừng gửi "volume" cho server). |
| `current_lesson.lesson_title` | **`current_lesson`** | string = tên bài đang mở (vd "Sông Đáy"). |
| `current_lesson.page` | **`trang`** | int. **page → trang**. |
| `utterance` | `query` | top-level, KHÔNG trong `user_profile`. |

> Tham chiếu cách parse: `parse_structured_query` đọc profile `{lop/grade, bo_sach, subject/mon, trang, tap}`; `query_lesson_card` đọc `current_lesson`/`bai_dang_hoc` + `tap` (server-only, [canonical](../project_state/2026-06-22-canonical.md)). Client gửi đúng tên server-side ở cột giữa.

---

## 5. Ví dụ payload đúng (3 tier)

```jsonc
// A. Companion: đang mở bài, hỏi chung chung -> lesson_card
{ "query": "giảng cho em bài này với",
  "user_profile": {"lop":9,"bo_sach":"CTST","subject":"ngu_van","tap":2,"current_lesson":"Sông Đáy"} }

// B. Luyện tập -> lesson_practice
{ "query": "cho em làm bài tập bài này",
  "user_profile": {"lop":9,"bo_sach":"CTST","subject":"ngu_van","tap":2,"current_lesson":"Mùa xuân chín"} }

// C. Tra theo trang (cần tap để không trùng tập) -> lesson_card
{ "query": "giảng bài trang 130 cho tớ",
  "user_profile": {"lop":9,"bo_sach":"CTST","subject":"ngu_van","tap":2} }
```

---

## 6. Liên quan
- Hành vi khi client gửi `{}` / thiếu neo bài: [degraded-mode-behavior.md](degraded-mode-behavior.md).
- Test đặc tả (skip nếu không có server): [`tests/integration/client_context_contract_test.py`](../../tests/integration/client_context_contract_test.py).
- Release gate yêu cầu "Client context contract confirmed (không còn `{}`)": [canonical §Release gate](../project_state/2026-06-22-canonical.md).
