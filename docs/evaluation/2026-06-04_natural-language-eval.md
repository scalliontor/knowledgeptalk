# Natural-language eval — Gemma4 sinh query giọng nói thật

> **Ngày**: 2026-06-04 · Harness `/tmp/eval_natural.py` — Gemma4 (`gemma-4`, temp 1.0) sinh query giọng học sinh THẬT (khẩu ngữ, vòng vo, voice-style, có "ơi/ạ/cái vụ..."), grounded trên anchor thật. Chạy qua retrieval đã fix (T-C/C2 + đ→d). 75 cases Toán+Văn.
> **Lý do**: các eval lớn trước (Toán 4500, Văn 1703...) dùng query TEMPLATE → đặt sẵn token concept/bài sạch → nghi đánh giá cao quá. Đây là phép thử ngôn ngữ tự nhiên thật.

## Kết quả: OVERALL 81.3% (61/75)

| Loại | Template | **Tự nhiên** | Δ |
|---|---|---|---|
| Toán theo bài | 100% | **100%** (15/15) | giữ |
| Toán theo trang | 98.8% | **93.3%** (14/15) | -5 |
| **Toán concept** | 80.7% | **33.3%** (5/15) | **-47** ⚠️ |
| Văn work | 100% | **93.3%** (14/15) | -7 |
| Văn nội dung | 100% | **80.0%** (8/10) | -20 |
| Văn đọc thuộc | — | **100%** (5/5) | — |

## Ví dụ query Gemma4 sinh (thật, lộn xộn)
- "Dạ thầy ơi, cái bài 35 về định lí Pythagore á, thầy giảng lại giúp em được..." → ✓ struct
- "Thầy ơi, thầy giảng giúp em cái Bài 2 phần Hình nón với ạ, tự dưng nãy giờ..." → ✓ struct
- "Cô ơi... cái phần 'tần số tương đối' với cái biểu đồ của nó ấy... ở trang 56 ấy ạ" → ✗ (route sang trang, không match concept)
- "Dạ thầy/cô ơi... cái mấy cái hằng đẳng thức đáng nhớ ấy ạ, sao nó nhìn lằng nhằng" → ✗ concept miss

## Phát hiện cốt lõi
1. **Structured-first ROBUST với voice** (bài/trang/tác phẩm 93-100%). "bài 35", "trang 56", tên tác phẩm sống sót qua câu nói lộn xộn → validate luận điểm structured-first cho voice tutor. Đây là tin tốt nhất.
2. **Concept-only SỤP 80.7%→33% dưới ngôn ngữ tự nhiên** — 2 nguyên nhân:
   - **Mix tín hiệu**: học sinh nói kèm trang ("cái phần X *ở trang N* ấy") → route sang structured (trả theo trang, scorer không credit concept name). Một phần là scoring-artifact (trang trả về có thể ĐÚNG nội dung), một phần là routing chưa tối ưu.
   - **Phrasing mơ hồ** ("cái vụ X", "mấy cái Y") → word-overlap concept miss thật.
3. **Template ĐÃ overestimate concept** — đúng như nghi ngờ. Structured thì không (vì token bài/trang rõ ràng dù phrasing lộn xộn).

## Hành động
- Core companion (bài/trang/tác phẩm) — **đủ tốt cho voice**, ship được.
- **Concept retrieval = ưu tiên cải thiện**:
  - (a) **Vector-rerank** BGE-m3 trong grade+book scope khi concept-exact yếu (cần canary/model).
  - (b) **Routing thông minh**: query có cả concept-word + trang → thử concept path TRƯỚC hoặc song song, không để trang hijack.
  - (c) Concept alias/synonym + lemmatize để bắt phrasing mơ hồ.
- **Phải dùng natural-language eval (Gemma4) làm gate chuẩn**, không chỉ template.

Liên quan: [verify Toán](2026-06-03_verify-arch-toan.md) · [verify Văn](2026-06-04_verify-arch-van.md)
