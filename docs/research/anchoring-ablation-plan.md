# Anchoring — kế hoạch ablation (chạy SAU bằng framework backtest)

> **Mục tiêu**: thiết kế thí nghiệm tách contribution của từng bậc anchor, để định lượng "structured đóng góp bao nhiêu / vector đóng góp bao nhiêu / threshold mới có an toàn không / client-context tác động ra sao". KHÔNG implement ở vòng này. Chạy bằng `rag_edu/scripts/schema_v3_2026_06/backtest_book.py` (đã có `by_dimension` + `sample_fails` + latency).
>
> **Ràng buộc**: không đụng prod `:8888`; ablation chạy trên canary `:8889`/candidate riêng; mỗi variant = 1 bản server tách (toggle qua env/flag), backtest cùng seed 42.

## 0. Đại lượng đo (mọi variant đều xuất)
- `anchor_acc`, `mode_acc`, `guard_acc` (tổng + per `by_dimension`).
- `guard_out_of_book`, `guard_chitchat`, `guard_oob_trang` (riêng — chống regression "sạch nguồn"/"từ chối").
- `cruft_on_cards` (phải = 0 mọi variant).
- `latency` P50/P95/P99.
- Per-dimension delta vs baseline (current hybrid).

## 1. Ma trận variant

| # | Variant | Bậc bật | Mục đích đo |
|---|---|---|---|
| V0 | **structured-only** | 1 current_lesson + 2 name + 3 trang. Tắt content-vector (bậc 4) hoàn toàn. | Trần trên của đường deterministic; bao nhiêu % đạt được KHÔNG cần vector. Kỳ vọng: anchor giữ ~90%+ ở current_lesson/name/trang, content_only → gần 0 (toàn none). Guard out-of-book → ~100% (không vector ép card). |
| V1 | **vector-only** | Chỉ bậc 4 (content-vector + gate hiện tại). Tắt 1–3. | Đo riêng năng lực vector. Kỳ vọng anchor tụt mạnh ở current_lesson; cho thấy structured là xương sống. |
| V2 | **hybrid hiện tại (baseline)** | 1+2+3+4, gate `bs>=0.50 AND (margin>=0.04 OR bs>=0.60)`. | Mốc so sánh = full-sweep 2026-06-17 (anchor 97.0). |
| V3 | **hybrid + threshold mới** | Như V2 nhưng quét gate: {`margin>=0.03`}, {`bs>=0.55`}, {`bs>=0.46 AND (margin>=0.03 OR bs>=0.52)`}(pilot Toán cũ). | Tìm điểm Pareto anchor↑ (content_only) vs guard_out_of_book↓. Xác nhận gate hiện tại có phải tối ưu. |
| V4 | **hybrid + client-context** | V2 nhưng FORCE mọi case có `current_lesson` (mô phỏng client luôn gửi đúng bài). | Đo trần production thật khi gap #4 (client gửi `{}`) được vá. Kỳ vọng anchor→~99%+, Toán tiểu học gap gần biến mất. **Đây là biện minh ROI cho client-context contract.** |
| V5 | **hybrid − context (no current_lesson)** | V2 nhưng STRIP `current_lesson` khỏi mọi profile (chỉ giữ trang/name khi có). | Đo sàn xấu nhất (client không gửi bài). Khoảng cách V5↔V4 = giá trị của client-context. |
| V6 (tuỳ chọn) | **hybrid + work_name norm fix** | V2 + áp chuẩn hoá suffix/gạch ngang/alias (xem `history-work-name-normalization.md` + `math-primary-failure-analysis.md` V1). | Tách phần gap là **artefact scorer/data** khỏi phần gap **retrieval thật**. |

## 2. Cohort (quyển) chạy ablation
Tối thiểu, chọn quyển đại diện từng failure mode:
- **Toán tiểu học cluster**: toan 4 CTST, toan 5 CTST, toan 6 KNTT t1.
- **Toán formula-title**: toan 8 CD t1.
- **Toán anomaly current_lesson**: toan 8 CTST t1 (kiểm V4/V6 có cứu 76.8%→).
- **Lịch sử suffix/variant**: lich_su 6 KNTT, lich_su 6 CTST, lich_su 9 CTST.
- **Control (đang tốt)**: gdcd 6 CTST + ngu_van 9 CTST t2 (đảm bảo không variant nào làm tụt môn đang tốt).

## 3. Giả thuyết cần xác nhận (gắn với phân tích gap)
- **H1**: V0 (structured-only) giữ anchor ≥95% trên current_lesson/name/trang, chứng minh gap nằm ở content_only (thiếu anchor), không ở đường anchored. → nếu đúng, ưu tiên client-context hơn là vá vector.
- **H2**: V4 (force current_lesson) đưa Toán tiểu học 75–85% → ~99%, định lượng ROI của client-context contract (gap #4).
- **H3**: V6 (norm fix) nâng anchor đo được của Lịch sử KNTT mà KHÔNG đụng retrieval ⇒ phần lớn gap Sử là artefact data/scorer.
- **H4**: V3 (threshold quét) cho thấy gate hiện `bs>=0.50/margin>=0.04` đã ở vùng tối ưu — nới xuống thì content_only↑ nhỏ nhưng guard_out_of_book↓ lớn (regression "từ chối ngoài bài").

## 4. Quy trình chạy (đề xuất, không chạy bây giờ)
1. Backup canary; tạo các bản server-variant qua flag/env (V0–V6), KHÔNG đụng `:8888`.
2. Với mỗi (variant × quyển): `python backtest_book.py <subject> <grade> <book> <tap> 500 <port_variant>` (seed 42 cố định → cùng tập câu).
3. Gom JSON vào `reports/backtest/<run-id>-ablation/`; viết script tổng hợp bảng `variant × dimension × metric`.
4. Đọc theo gate canonical: variant nào **anchor↑ và guard không tụt và cruft=0 và P95 trong ngưỡng** mới là ứng viên.
5. Quyết định: deterministic-weight + client-context (V4/V0) vs gate-tuning (V3) vs norm-fix (V6).

## 5. Gate so sánh (PASS để xét promote)
```
anchor ≥ 97.0 (tổng) · guard ≥ 98.1 · guard_out_of_book không tụt dưới baseline
cruft_real = 0 · errors = 0 · P95 trong 193–368ms (Gemma-free)
Toán 4–6 và Lịch sử: tăng hoặc không tụt per-book
ngu_van/gdcd control: không tụt
```

## 6. Đầu ra mong đợi
Một bảng quyết định: với mỗi gap (Toán tiểu học, Lịch sử), chỉ ra **can thiệp rẻ nhất + an toàn nhất** đạt mục tiêu, có số đo trước/sau. Kỳ vọng kết luận: **client-context (V4) + data/norm fix (V6)** thắng gate-tuning (V3) về cả anchor lẫn guard.

## Tham chiếu
- Framework: `rag_edu/scripts/schema_v3_2026_06/backtest_book.py`, `megatest.py`.
- Phương pháp chấm: `docs/pilot/BACKTEST_RULE.md`.
- Routing as-built: `docs/research/anchoring-current-method.md`.
- Gap analysis: `docs/research/math-primary-failure-analysis.md`, `docs/research/history-work-name-normalization.md`.
- Baseline artifact: `reports/backtest/2026-06-17_full-sweep/`.
