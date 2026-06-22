# User Journeys — 4 hành trình thật

> Minh hoạ companion flow trên các tình huống thực. Nguồn: [pilot/RESULTS.md](../pilot/RESULTS.md) (acceptance 47/53), [pilot/MULTISUBJECT_SCALE_2026_06_14.md](../pilot/MULTISUBJECT_SCALE_2026_06_14.md) (stress-test 973 case), [lesson-card-model.md](lesson-card-model.md).
> Ký hiệu: **profile** = ngữ cảnh thiết bị gửi kèm. Đường "anchored" (có `current_lesson`/`trang`+`tap`) ≈ 97–98% trong đo thực.

---

## Hành trình 1 — Bé học Văn xin GIẢNG "Sang thu"

**Bối cảnh.** Bé mở SGK Ngữ văn, thiết bị biết bài đang học.

```
profile = { lop: 9, bo_sach: "CTST", subject: "ngu_van",
            current_lesson: "Sang thu", tap: 2 }
Bé: "Giảng cho con bài này với" / "Phân tích bài Sang thu" / "Bố cục bài này thế nào?"
```

**Hệ thống làm gì.**
1. `parse_structured_query` đọc `current_lesson="Sang thu"` từ profile → neo `:Lesson` ngay (ưu tiên cao nhất), scope lớp 9 + CTST + **tập 2**.
2. Intent classifier (embedding) → **explain**.
3. Trả thành phần 📖 **Giảng**: tác giả / hoàn cảnh / thể loại / bố cục / nội dung / giá trị + 💡 câu hỏi gợi mở.

**Kết quả mong đợi.** Bài giảng đúng "Sang thu", **sạch nguồn** (không nhắc vietjack), độ trễ thấp (Gemma-free). Dù bé nói vòng ("giảng bài này", không nêu tên) vẫn đúng vì neo bằng `current_lesson`.

---

## Hành trình 2 — Bé xin ĐỌC THUỘC bài thơ

**Bối cảnh.** Cùng bài, bé muốn nghe/đọc thuộc nguyên văn.

```
profile = { lop: 9, bo_sach: "CTST", subject: "ngu_van",
            current_lesson: "Sông Đáy", tap: 2 }
Bé: "Đọc full bài thơ đi" / "Ngâm bài này cho con nghe" / "Nghe trọn bài"
```

**Hệ thống làm gì.**
1. Neo `:Lesson` qua `current_lesson`.
2. Intent classifier → **recite** (mọi paraphrase "đọc full / ngâm / đọc lên / nghe trọn bài" đều về recite — pilot 6/6).
3. Trả thành phần 🎤 **Đọc thuộc**: **nguyên văn** từ `LiteratureText` đã validate (nguồn Thi Viện), **rights-gated** (chỉ đọc full khi `allow_full_recitation`).

**Kết quả mong đợi.** Đọc đúng từng chữ (verbatim — không paraphrase). Nếu bài chưa có bản nguyên văn validated → từ chối/đề nghị bài khác thay vì chế lại.

---

## Hành trình 3 — Bé Toán xin LUYỆN TẬP

**Bối cảnh.** Bé học Toán, muốn ôn/tự kiểm tra.

```
profile = { lop: 6, bo_sach: "CTST", subject: "toan",
            current_lesson: "Phân số", tap: 2 }
Bé: "Cho con mấy câu ôn" / "Luyện tập bài này" / "Tự kiểm tra phần này"
```

**Hệ thống làm gì.**
1. Neo `:Lesson` "Phân số" qua `current_lesson`, scope lớp 6 + CTST + tập 2.
   - *Lưu ý chống bẫy*: tên bài tiểu học hay có đuôi "(trang 42)"; parser **strip `(trang…)`** + recompute `work_name_norm` (fold đ→d + NFD) nên `current_lesson="Phân số"` vẫn khớp đúng.
2. Intent classifier → **practice**.
3. Trả thành phần ✍️ **Luyện tập có dẫn dắt**: `{câu hỏi SGK + gợi ý sư phạm + đáp án ẩn}`, `delivery_mode=guided_practice` — dẫn từng bước, **không xổ đáp án** ngay.

**Kết quả mong đợi.** Bé được luyện đúng "Phân số" của đúng tập, với gợi ý sư phạm. *(Gap đã biết: Toán tiểu học 4–6 anchoring 82–86% nếu thiếu `current_lesson` — đường anchored vẫn cao.)*

---

## Hành trình 4 — Bé hỏi LẠC ĐỀ → companion TỪ CHỐI

**Bối cảnh.** Bé hỏi ngoài bài đang học, hoặc chitchat, hoặc bài không có trong sách.

```
profile = { lop: 6, bo_sach: "CTST", subject: "toan",
            current_lesson: "Phân số", tap: 2 }
Bé: "Hôm nay trời đẹp nhỉ?"  (chitchat)
Bé: "Giải giúp con bài tích phân"  (ngoài sách / ngoài bài)
Bé: "Trang 999 nói gì?"  (trang ngoài sách)
```

**Hệ thống làm gì.**
1. Không neo được `:Lesson` hợp lệ trong scope (chitchat/off-topic), hoặc content-vector dưới ngưỡng (floor `bs≥0.60` + margin ≥ 0.04).
2. **Guard** chặn → **từ chối an toàn**: "Cái này không nằm trong bài hôm nay" — KHÔNG đoán, KHÔNG hallucinate.

**Kết quả mong đợi.** Guard chitchat/off-topic/trang-ngoài-sách ≈ 97–100% trong stress-test, 0 false-positive trên chitchat thường.
*(Honest: `guard_out_of_book` ≈ 64% — hỏi một bài có thật nhưng ngoài quyển vẫn leak ~36% do content-vec bắt bài gần nhất. Production che bằng `current_lesson` (thiết bị luôn gửi bài đang học) → ranh giới rõ hơn.)*

---

## Tóm tắt: cùng một bài, ý định khác → thành phần khác

| Bé nói (ví dụ paraphrase) | Intent | Thành phần trả |
|---|---|---|
| "giảng / phân tích / bố cục bài này" | explain | 📖 Giảng + 💡 gợi mở |
| "đọc full / ngâm / nghe trọn bài" | recite | 🎤 Đọc thuộc (verbatim) |
| "mấy câu ôn / luyện tập / tự kiểm tra" | practice | ✍️ Luyện tập có dẫn dắt |
| chitchat / ngoài bài / trang ngoài sách | (guard) | ❌ Từ chối an toàn |

> Điểm chung 4 hành trình: **thiết bị gửi `current_lesson`/`trang`+`tap`** là yếu tố làm hệ thống đáng tin. Đây cũng là gap #4 trong canonical — `rag_client` hiện gửi `{}`, cần contract + integration để đạt anchor 97% thực địa.

---
Liên quan: [lesson-card-model.md](lesson-card-model.md) · [north-star.md](north-star.md) · [goals-and-anti-goals.md](goals-and-anti-goals.md) · [pilot/RESULTS.md](../pilot/RESULTS.md)
