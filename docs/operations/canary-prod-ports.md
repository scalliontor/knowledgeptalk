# Operations — Ports canary / prod / merged + cách launch

> Nguồn: [project_state/2026-06-22-canonical.md](../project_state/2026-06-22-canonical.md) §thực tế hạ tầng + [RUNBOOK.md](../RUNBOOK.md) §2.
> ⚠️ **Runtime KHÔNG ở repo này.** Production = single-file trên **server** `/home/namnx/Ptalk_project/CloudPTalk`. Repo local = scripts + docs.
> 🔒 **Không secret trong doc.** Creds (SSH, Neo4j, Gemma) tham chiếu `server.txt` / `.env`.

## Bảng port

| Port | File trên server | Vai trò | Có gì đặc biệt |
|---|---|---|---|
| **8888** | `rag_server.py` | **PROD** — ESP32 + CloudPTalk gọi thật. | Có endpoint `/v2/moderation/expand-topic` (kiểm duyệt phụ huynh). Hiện chạy **code cũ** (chưa có companion). |
| **8889** | `rag_server_canary.py` | **CANARY** — nơi phát triển/test code mới. | Companion Lesson Card đã chạy ở đây. **Thiếu** moderation endpoint (đừng copy thẳng sang prod). |
| **8890** | `rag_server_merged.py` (ở `/tmp` trên server) | **MERGED CANDIDATE** — bản gộp companion **+ giữ** moderation. | Đã test full-sweep đạt chuẩn (anchor 97.0). Ứng viên promote lên 8888. |

Endpoints chính (prod): `/retrieve`, `/v2/rag/retrieve`, `/health`, `/v2/moderation/expand-topic`.

Phụ thuộc runtime (server-only):
- **Neo4j edu**: `bolt://localhost:7688` (container `edu_neo4j`).
- **Gemma local**: `:8080` — chỉ dùng lúc **build/ingest**, KHÔNG ở serve path (serve = Gemma-free).
- **venv**: `venv/bin/python` (sentence-transformers / neo4j / qdrant / fastapi / uvicorn).

## ⛔ Cách LAUNCH (đã tốn rất nhiều công — đọc kỹ)

**Lệnh inline qua ssh để start rag_server BỊ LỖI** (output bị nuốt; ssh drop ~72s đúng lúc uvicorn startup; screen/tmux/nohup inline đều chết). **Cách chạy được = viết SCRIPT FILE rồi chạy script đó.**

```bash
# 1) Tạo script trên server (ví dụ /tmp/start_rag.sh):
#    #!/bin/bash
#    cd /home/namnx/Ptalk_project/CloudPTalk
#    pkill -9 -f rag_server.py; sleep 8
#    nohup venv/bin/python -u rag_server.py > logs/rag_server.log 2>&1 &
#
# 2) Chạy script qua ssh:  ssh '... bash /tmp/start_rag.sh'
# 3) Đợi ~25-40s (BGE-m3 load ~2.1GB VRAM), rồi verify:
curl localhost:8888/health      # {"status":"ok"}
```

Lưu ý:
- Dùng `venv/bin/python` trực tiếp — **KHÔNG** `source venv/bin/activate` (hang trong shell non-tty).
- Canary y hệt với `rag_server_canary.py` (port 8889 cấu hình trong file); merged với `rag_server_merged.py` (8890).
- Trong **terminal interactive thật (tty)** của anh thì `screen -dmS ptalk_rag bash -c "source venv/bin/activate; python3 -u rag_server.py > logs/rag_server.log 2>&1"` chạy ổn — khác sshpass non-tty.
- **SSH server flaky** (fail2ban khi nhiều kết nối nhanh) → dùng lệnh đơn, tách transfer khỏi launch.

## ⚠️ Ràng buộc khi restart prod

- **Restart prod :8888 = downtime ngắn cho ESP32.** → chỉ làm lúc low-traffic + **hỏi trước**.
- **KHÔNG copy canary → prod thẳng** (canary thiếu `/v2/moderation/expand-topic`). Phải dùng bản **merged** giữ đủ endpoint.
- Mọi promote phải qua [release-checklist.md](release-checklist.md); có sẵn đường lui [rollback.md](rollback.md).

## Verify nhanh (read-only)

```bash
curl -s localhost:8888/health    # prod
curl -s localhost:8889/health    # canary
curl -s localhost:8890/health    # merged candidate (khi đang chạy)
# Neo4j (read): docker exec edu_neo4j cypher-shell -u neo4j -p '<pass trong .env>' --format plain "<cypher>"
```

---
Liên quan: [release-checklist.md](release-checklist.md) · [rollback.md](rollback.md) · [backup-restore.md](backup-restore.md) · [RUNBOOK.md](../RUNBOOK.md) · [canonical](../project_state/2026-06-22-canonical.md)
