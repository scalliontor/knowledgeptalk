# Operations — Rollback (quay về bản trước khi promote)

> Nguồn: [project_state/2026-06-22-canonical.md](../project_state/2026-06-22-canonical.md) + [RUNBOOK.md](../RUNBOOK.md). Đường lui phải SẴN trước khi promote (gate yêu cầu "Rollback command documented").
> 🔒 Creds tham chiếu `server.txt` / `.env`. ⚠️ Restart prod = ESP32 downtime ngắn.

## Nguyên tắc

- Mỗi lần sửa `rag_server.py` trên server tạo `rag_server.py.bak_<ngày>` (backup từng lần). Rollback = **đưa `.bak` về lại + restart**.
- Mọi thay đổi DATA (Neo4j) đều **actor-tagged, reversible** (`MATCH (n) WHERE n.<actor>='...'`) → có thể xoá đúng phần mình thêm mà không đụng dữ liệu khác.

## Khi nào rollback

- Post-release smoke fail (`/health` không ok, hoặc 4 hành trình giảng/đọc/luyện/từ chối sai).
- Latency tăng bất thường / lỗi trong `logs/rag_server.log`.
- Bất kỳ invariant nào bị phá lộ ra production (leak nguồn, trộn tập, hết refuse).

## A. Rollback code (file `rag_server.py`)

```bash
# Trên server /home/namnx/Ptalk_project/CloudPTalk:
# 1) Chọn bản .bak gần nhất tốt (liệt kê):
ls -t rag_server.py.bak_*
# 2) Đưa về lại:
cp rag_server.py.bak_<ngày-tốt> rag_server.py
# 3) Restart bằng SCRIPT FILE + nohup (KHÔNG inline ssh — xem canary-prod-ports.md §launch)
bash /tmp/start_rag.sh        # script: pkill -9 -f rag_server.py; sleep 8; nohup venv/bin/python -u rag_server.py ...
# 4) Đợi ~25-40s (BGE load) → verify:
curl localhost:8888/health   # {"status":"ok"}
```

Smoke lại sau rollback: chạy 4 hành trình đại diện ([user-journeys.md](../product/user-journeys.md)) — giảng / đọc thuộc / luyện / từ chối.

## B. Rollback data (Neo4j edu) — nếu lần release có ingest

Hai lựa chọn, ưu tiên theo phạm vi:

1. **Xoá theo actor-tag** (nhẹ, đúng phần mình thêm):
   ```cypher
   // ví dụ: gỡ các :Lesson do release này tạo
   MATCH (n) WHERE n.<actor_field>='<RELEASE_ACTOR>' DETACH DELETE n;
   ```
2. **Restore từ dump** (nặng, khi hỏng diện rộng): theo [backup-restore.md](backup-restore.md).

## Sau rollback

- Ghi lại nguyên nhân + bản `.bak` đã dùng vào release note.
- KHÔNG promote lại cho tới khi backtest diff mới PASS ([release-checklist.md](release-checklist.md)).
- Cập nhật [canonical](../project_state/2026-06-22-canonical.md) nếu trạng thái prod đổi.

## Lưu ý quan trọng

- **KHÔNG copy canary → prod** để "sửa nhanh" (canary thiếu `/v2/moderation/expand-topic`). Rollback luôn về một `.bak` đã từng chạy đủ endpoint.
- Restart = downtime ESP32 → làm nhanh, gọn, đã chuẩn bị script trước.

---
Liên quan: [release-checklist.md](release-checklist.md) · [canary-prod-ports.md](canary-prod-ports.md) · [backup-restore.md](backup-restore.md) · [RUNBOOK.md](../RUNBOOK.md)
