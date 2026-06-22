# Operations — Release Checklist (promote lên prod :8888)

> Nguồn: [project_state/2026-06-22-canonical.md](../project_state/2026-06-22-canonical.md) §Release gate. **Backtest là gate** — không merge nếu không có report mới + diff.
> 🔒 Không secret trong doc (tham chiếu `server.txt` / `.env`). ⚠️ Restart prod = ESP32 downtime → low-traffic + ask trước.

## Khi nào dùng

Trước **mỗi lần** promote một bản (vd `rag_server_merged.py` @ 8890) lên prod `rag_server.py` @ 8888. Bỏ qua bất kỳ ô nào = **không promote**.

## Gate (sao y canonical — tất cả phải PASS)

```
[ ] Full sweep mới PASS (report trong reports/backtest/<run>/)
[ ] Anchor ≥ 97.0 · Guard ≥ 98.1 · real cruft = 0 · error = 0 · P95 trong ngưỡng (193–368 ms)
[ ] Toán 4–6 tăng hoặc không tụt · Lịch sử tăng hoặc không tụt
[ ] Volume collision = 0 critical (không trùng tập 1/2)
[ ] Canary 8889/8890 smoke pass
[ ] Client context contract confirmed (không còn {})
[ ] Backup Neo4j verified · Git SHA ghi trong release note
[ ] Rollback command documented
[ ] Restart prod 8888 → post-release smoke pass
```

## Trình tự thực thi (theo thứ tự, dừng nếu bất kỳ bước fail)

### A. Trước khi đụng prod
1. **Backtest diff.** Chạy full sweep trên bản ứng viên (8890), lưu vào `reports/backtest/<run-id>/` (81 JSON + log). So với baseline 2026-06-17. *(Đây là gate — không có report mới = stop.)*
2. **Đối chiếu invariant.** Mở [goals-and-anti-goals.md](../product/goals-and-anti-goals.md) §invariant — xác nhận PR không phá structured-first / scope-tập / Gemma-free / sạch nguồn / refuse.
3. **Real cruft = 0.** Verify nguồn sạch trên data, KHÔNG dựa keyword test cũ (`"giáo viên"` là false-positive). Tách `cruft_real` vs `cruft_test_false_positive`.
4. **Weak slices.** Toán tiểu học 4–6 và Lịch sử **tăng hoặc không tụt** so baseline.
5. **Smoke canary/merged.** `curl :8889/health`, `:8890/health` ok; chạy vài câu acceptance đại diện (giảng/đọc/luyện/từ chối).
6. **Endpoint parity.** Bản promote PHẢI có `/v2/moderation/expand-topic` (KHÔNG copy canary thẳng — dùng merged).
7. **Backup Neo4j.** Theo [backup-restore.md](backup-restore.md); xác nhận dump tồn tại + đẩy Drive.
8. **Ghi release note.** Git SHA của bản promote + run-id backtest + rollback command.

### B. Promote (low-traffic + đã hỏi)
9. **Lưu `.bak`.** `cp rag_server.py rag_server.py.bak_<ngày>` trên server (đường lui — xem [rollback.md](rollback.md)).
10. **Đặt file mới.** Đưa bản merged thành `rag_server.py` (giữ tên/port 8888).
11. **Restart bằng SCRIPT FILE + nohup** (KHÔNG inline ssh — xem [canary-prod-ports.md](canary-prod-ports.md) §launch). Đợi ~25–40s (BGE load).

### C. Sau promote
12. **Post-release smoke.** `curl :8888/health` = ok; chạy lại bộ smoke (4 hành trình: giảng/đọc/luyện/từ chối) — xem [user-journeys.md](../product/user-journeys.md).
13. **Theo dõi latency + log** vài phút (`logs/rag_server.log`). Lỗi/tụt metric → [rollback.md](rollback.md) ngay.
14. **Cập nhật canonical.** Nếu baseline đổi, cập nhật [2026-06-22-canonical.md](../project_state/2026-06-22-canonical.md) kèm run-id (không sửa số liệu mà không có report tương ứng).

## Thứ tự thực thi tổng (anh chốt — bối cảnh)

> Backtest Engineer → Repo Cartographer → Architecture Refactor → Fix weak slices → Client integration → **Promote.**
> Lý do: metric đang tốt; rủi ro lớn nhất là refactor làm tụt anchor/guard mà không có backtest diff để bắt. Promote là bước CUỐI.

---
Liên quan: [canary-prod-ports.md](canary-prod-ports.md) · [rollback.md](rollback.md) · [backup-restore.md](backup-restore.md) · [canonical](../project_state/2026-06-22-canonical.md)
