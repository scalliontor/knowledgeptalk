# Lesson Card Model — node `:Lesson` + 4 thành phần + companion flow

> Mô hình dữ liệu **sản phẩm** của companion. Nguồn: [pilot/RESULTS.md](../pilot/RESULTS.md), [pilot/MULTISUBJECT_SCALE_2026_06_14.md](../pilot/MULTISUBJECT_SCALE_2026_06_14.md), [design/kg-schema-v3.md](../design/kg-schema-v3.md), [canonical](../project_state/2026-06-22-canonical.md).
> Mô hình **schema/retrieval** đầy đủ (KnowledgeChunk/Concept/Work) ở [kg-schema-v3.md](../design/kg-schema-v3.md) — file này tập trung tầng companion mà người dùng cảm nhận.

## Ý tưởng cốt lõi: 1 bài = 1 thẻ học (`:Lesson`)

Một **Lesson Card** là một node `:Lesson` đại diện cho **một bài học trong SGK** (vd "Sang thu", "Phân số", "Bài 5 — Phép cộng"). Một thẻ phục vụ **nhiều ý định trên cùng một bài**, không phải nhiều câu hỏi rời rạc. Companion **tự nhận diện ý định theo nghĩa** (embedding classifier, không phụ thuộc từ khoá cứng) rồi trả đúng thành phần.

Quy mô hiện tại (Neo4j edu, canary): companion đã scale ra nhiều quyển/môn; pilot gốc = Ngữ văn 9 CTST tập 2 (13 bài), Toán 6 CTST tập 2 (24 bài), mở rộng đa môn (Toán/KHTN/Sử/Địa/GDCD CTST+).

## 4 thành phần của một Lesson Card

| Thành phần | Tier (nội bộ) | Nội dung | Ghi chú |
|---|---|---|---|
| 📖 **Giảng** | `lesson_card` | Tác giả / hoàn cảnh / thể loại / bố cục / nội dung / giá trị + **câu hỏi gợi mở**. | Grounded từ nguồn (VietJack TGTP làm ground-fact + Gemma synth lúc build, KHÔNG ở serve path). |
| 🎤 **Đọc thuộc** | `lesson_recite` | **Nguyên văn** bài thơ/đoạn để đọc thuộc. | Verbatim từ `LiteratureText` đã validate (vd nguồn Thi Viện), **rights-gated**. Văn-only. |
| ✍️ **Luyện tập có dẫn dắt** | `lesson_practice` | Bộ câu hỏi `{câu hỏi SGK + gợi ý sư phạm + đáp án ẩn}`, `delivery_mode=guided_practice`. | KHÔNG đưa đáp án trần — dẫn dắt từng bước. |
| 💡 **Gợi mở** | (nằm trong `lesson_card`) | Câu hỏi mở rộng tư duy kèm phần giảng. | Đẩy bé suy nghĩ thay vì kết thúc bằng đáp án. |

> Lưu ý môn: **đọc thuộc** đặc thù Văn (thơ/văn bản). **Luyện tập** có ở Toán & môn concept. **Văn/Tiếng Việt cần builder CURATE TAY** (generic driver bóc title literature không sạch — xem MULTISUBJECT_SCALE §bug). Môn concept (Toán/KHTN/Sử/Địa/GDCD) title sạch → driver tự động chạy tốt.

## Cách NEO một thẻ (thứ tự ưu tiên = structured-first)

Companion chọn đúng `:Lesson` theo độ ưu tiên giảm dần (khớp invariant structured-first của canonical):

```
1. current_lesson   (thiết bị/hồ sơ gửi)            ← mạnh nhất, đường production
2. tên bài trong câu (named — kể cả nói vòng)
3. số trang          (trong câu hỏi HOẶC trong profile)
4. mô tả nội dung    (content-vector: BGE cosine trên theory embeddings,
                      gate margin top1−top2 ≥ ~0.04 + floor → chống chitchat khớp-mờ)
```

Mọi neo đều **scope chặt**: `lớp + bộ sách + TẬP + (trang)`. Tập (`tap_no`) bắt buộc để chống nhập nhằng trang giữa Tập 1/Tập 2 (sách reset số trang) — thiết bị PHẢI gửi `tap`.

## Companion flow (hồ sơ → Lesson Card)

```
Hồ sơ + ngữ cảnh thiết bị
  profile { lop, bo_sach, subject,  current_lesson | (trang + tap) }
        │
        ▼
  parse_structured_query   (regex bài/trang + đọc profile)   ~1ms
        │
        ▼
  CHỌN :Lesson   theo thứ tự neo ở trên, scope lop+bo_sach+tap
        │ (không neo được → từ chối an toàn, KHÔNG đoán)
        ▼
  PHÂN LOẠI Ý ĐỊNH  (embedding classifier BGE: recite / practice / explain;
                     margin ~0.035; regex giữ fast-path)
        │
        ├─ explain  → trả thành phần 📖 Giảng (+ 💡 gợi mở)
        ├─ practice → trả thành phần ✍️ Luyện tập có dẫn dắt
        └─ recite   → trả thành phần 🎤 Đọc thuộc (verbatim, rights-gated)
```

Đặc tính quan trọng:
- **Gemma-free serve path** — phân loại ý định bằng **embedding**, không gọi LLM (giữ độ trễ thấp). LLM (Gemma) chỉ dùng lúc **build/synth** nội dung, không ở đường nóng.
- **Robust paraphrase** — vì so nghĩa, "đọc full / ngâm / nghe trọn bài" đều → recite; "ôn / tự kiểm tra / luyện" → practice; chịu được gõ sai/không dấu (typo/teen).
- **Đường anchored (thiết bị gửi `current_lesson`/`trang`+`tap`) ≈ 97–98%**, typo-robust, cruft 0, P95 < 300 ms → khả dụng production.

## Vì sao thiết kế thế này (ánh xạ north star)

| Quyết định mô hình | Phục vụ cam kết |
|---|---|
| 1 `:Lesson` phục vụ nhiều ý định | "bạn đồng hành một bài", không phải nhiều câu hỏi rời |
| Neo theo `current_lesson`/trang trước | "bám đúng bài/trang đang mở" + structured-first |
| 4 thành phần giảng/đọc/luyện/gợi mở | "giảng · đọc · luyện" (3 việc của gia sư) |
| Recite verbatim rights-gated | đọc thuộc đúng nguyên văn, hợp pháp |
| Intent = embedding, build = Gemma | "độ trễ thấp" (Gemma-free serve) |
| Không neo → từ chối | "từ chối khi ngoài bài thay vì đoán" |

## Giới hạn đã biết (honest)

- **Trang-range chưa tuyệt đối**: suy từ start-pages (sitemap) → cap CHẶT để không trả sai bài, đổi lại vài trang-giữa của bài nhiều trang → None. Production neo chính bằng `current_lesson`; trang là phụ.
- **Content-only (mô tả nội dung, không neo) ~70%**: mô tả quá mơ hồ/ngắn vẫn trượt — nhưng đây phần lớn là từ chối an toàn, không phải gap production.
- **guard_out_of_book ~64%**: hỏi bài ngoài sách vẫn leak ~36% (content-vec bắt bài gần nhất); production che bằng `current_lesson` (thiết bị gửi bài đang học).
- **Coverage Lesson Card** mở rộng dần; văn bản phụ (Đọc mở rộng/Viết/Nói nghe) chưa dựng thẻ đầy đủ.

---
Liên quan: [north-star.md](north-star.md) · [user-journeys.md](user-journeys.md) · [design/kg-schema-v3.md](../design/kg-schema-v3.md) · [pilot/RESULTS.md](../pilot/RESULTS.md) · [canonical](../project_state/2026-06-22-canonical.md)
