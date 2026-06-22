# Degraded Mode — khi client thiếu context bài

> **Status:** SPEC (new file, 2026-06-22). KHÔNG sửa runtime.
> **Đi kèm:** [required-context-contract.md](required-context-contract.md). **Source-of-truth:** [canonical 2026-06-22](../project_state/2026-06-22-canonical.md).

## 1. Định nghĩa "degraded"

Hệ ở **degraded mode** khi `user_profile` **không có neo bài** — tức:
- client gửi `user_profile: {}` (tình trạng `rag_client` HIỆN TẠI), hoặc
- thiếu **cả** `current_lesson` **và** (`trang`+`tap`), hoặc
- thiếu trường scope (`lop` / `subject` / `bo_sach`) làm routing môn/lớp không khoá được.

Khi đó **đường anchored (structured-first) không kích hoạt đủ**. Hệ rơi xuống các nấc thấp hơn của thứ tự routing (invariant):

```
current_lesson  →  tên bài trong query  →  trang+tập  →  content-vector  →  (refuse)
   [neo]              [neo]                  [neo]          [đoán theo nghĩa]   [từ chối]
```

Thiếu 3 nấc neo đầu, query mơ hồ ("giảng bài này đi") **không còn bài để bám** → chỉ còn content-vector hoặc từ chối.

## 2. Hành vi MONG ĐỢI ở degraded mode (đặc tả, không đổi runtime)

| Tình huống | Hành vi đúng |
|---|---|
| Query có **tên bài rõ** ("giảng bài Sông Đáy") | Vẫn neo được qua nấc "tên bài trong query" → `lesson_card`. Degraded KHÔNG chặn đường này. |
| Query có **"trang N"** nhưng thiếu `tap` | Tra theo trang **rủi ro trùng tập 1/2** → có thể neo nhầm. Ưu tiên: nếu mơ hồ tập → **từ chối/hỏi lại** thay vì đoán. |
| Query **mơ hồ** ("giảng bài này", "phân tích giúp em") + không neo | KHÔNG có `current_lesson` để biết "bài này" là bài nào → **từ chối an toàn** (không bịa). `tier` = `noncard`/`none`. |
| Query **ngoài bài / chitchat / offtopic** | Giữ guard: `tier` không thuộc CARD_TIERS, không tạo thẻ giảng. |

> `CARD_TIERS = {lesson_card, lesson_practice, lesson_recite}`. Degraded đúng = **giảm tỉ lệ vào CARD_TIERS cho câu mơ hồ**, KHÔNG phải tạo thẻ sai.

## 3. ⛔ Quy tắc tuyên bố số liệu (quan trọng — chống lặp lỗi cũ)

- **KHÔNG được dùng 97% anchor để claim "production đạt 97%" khi client còn gửi `{}`.** Con số 97.0% (full sweep 2026-06-17) đo trên backtest **có cấp `current_lesson`/`trang`+`tap`** (xem dimension `current_lesson`, `trang_profile` trong `reports/backtest/2026-06-17_full-sweep/*.json`). Đó là **trần trên có context**, KHÔNG phải số production hiện tại.
- Khi client gửi `{}`: kỳ vọng thực tế là **đường content-vector** — trong backtest dimension `content_only` chỉ 25–47%, và **phần lớn phần còn lại là từ chối an toàn** (không có neo → không đoán). Production với `{}` sẽ **thấp hơn 97% rõ rệt** cho câu mơ hồ.
- Báo cáo phải **tách**: "anchor có context" vs "hành vi degraded khi không context". Đừng gộp.

## 4. Ưu tiên: TỪ CHỐI hơn ĐOÁN

Bám north star ("**từ chối khi ngoài bài thay vì đoán**") và invariant "Refuse ngoài bài":

1. Không có neo + query mơ hồ → **hỏi lại / từ chối**, KHÔNG chọn đại một bài.
2. Có "trang N" nhưng không có `tap` và sách có 2 tập → **không tự ý chọn tập**; hỏi lại hoặc từ chối.
3. Content-vector chỉ được trả khi **đủ tự tin** (đúng môn+lớp+bộ sách); nếu không, từ chối.

> Hệ quả: ở degraded, **guard/refuse cao là ĐÚNG**, không phải lỗi. Lỗi = tạo thẻ giảng sai bài (cruft/false-card).

## 5. Việc client PHẢI làm để thoát degraded

- Wire `rag_client` gửi đủ payload theo [required-context-contract.md §3–4](required-context-contract.md): scope (`lop`/`subject`/`bo_sach`/`tap`) **luôn luôn**, neo bài (`current_lesson`, `trang`) **khi app biết bài/trang đang mở**.
- Release gate (canonical) chỉ tick **"Client context contract confirmed (không còn `{}`)"** khi `rag_client` thực sự gửi context — không phải khi spec này tồn tại.

## 6. Liên quan
- [required-context-contract.md](required-context-contract.md) · [canonical 2026-06-22](../project_state/2026-06-22-canonical.md) · test: [`tests/integration/client_context_contract_test.py`](../../tests/integration/client_context_contract_test.py).
