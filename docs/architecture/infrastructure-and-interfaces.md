# Knowledge PTalk — Infrastructure & Interfaces (current, verified 2026-06-22)

> Grounded in live `docker ps` + `ss -tlnp` + `ps` + nginx-gateway config on server `namnx@171.226.10.121` (2026-06-22, sau promote). Đối chiếu lại khi topology đổi. Server-only thật ≠ repo (xem [project_state/canonical](../project_state/2026-06-22-canonical.md)).

## 1. RAG service đặt ở đâu trong hệ sinh thái

**RAG (`rag_server.py` :8888) là MICROSERVICE NỘI BỘ — KHÔNG expose trực tiếp ra ngoài.** Người dùng/thiết bị không gọi thẳng RAG; họ đi qua các app thoại PTalk, các app này mới gọi RAG nội bộ (localhost).

```
Thiết bị (loa ESP32 / app)
   │  (voice pipeline: STT → RAG → LLM → TTS; Redis Streams)
   ▼
nginx-gateway (:8000 / :80)  ──route──▶  ptalk_v1 :8001  (location /)
                              ──route──▶  ptalk_v2 :8002  (location /v2/)
                              ──route──▶  ptalk_eldercare :8003 (location /eldercare/)
                                                │
                                                │ HTTP POST nội bộ (RAG client)
                                                ▼
                                   rag_server.py  :8888  ◀── (canary :8889)
                                                │
                 ┌──────────────┬───────────────┼───────────────┬──────────────┐
                 ▼              ▼               ▼               ▼              ▼
          edu_neo4j        gemma_4_moe       qdrant        rag_postgres    BGE-m3
          :7688 bolt        :8080            :6333          :5433        (in-process)
          (KG companion)   (synth/moderation) (vector fb)  (legacy)      (embeddings)

Dashboard (dashboard-frontend :4321) ──▶ /v2/moderation/expand-topic trên :8888 (kiểm duyệt phụ huynh)
```

## 2. Runtime topology (verified `docker ps` / `ss -tlnp` / `ps`)

### RAG core (đối tượng repo này)
| Thành phần | Cổng | Process / Container | Vai trò |
|---|---|---|---|
| **RAG prod** | **:8888** | `venv/bin/python -u rag_server.py` (pid 2109117) | Production RAG — **đã promote: companion + en-dash fix + moderation** |
| **RAG canary** | **:8889** | `venv/bin/python -u rag_server_canary.py` (pid 1803037) | Staging (cùng base, nơi phát triển companion) |
| RAG thin (ứng viên) | :8891 (tạm) | `apps/companion_api/server.py` + `packages/` | Bản refactored, parity 100%, đủ moderation — cho migrate sau (không chạy thường trực) |
| edu Neo4j | :7688→7687 (bolt), :7475→7474 (http) | container `edu_neo4j` | KG companion (:Lesson/theory/practice/recite). auth neo4j/<EDU_NEO4J_PW> |
| Gemma-4 MoE | :8080→8000 | container `gemma_4_moe` | LLM — CHỈ build/ingest/moderation, **KHÔNG ở serve path** (Gemma-free) |
| Qdrant | :6333-6334 | container `qdrant` | Vector fallback (legacy; prod Neo4j-first) |
| rag_postgres | :5433→5432 | container `rag_postgres` (db `rag_edu`) | Legacy SQL (fallback path) |
| BGE-m3 | in-process | (trong rag_server) | Embedding (anchor content-vec + intent) |

### Voice apps (CloudPTalk — server-only, KHÔNG ở repo này) — client của RAG
| App | Cổng | Process | nginx |
|---|---|---|---|
| ptalk_v1 | :8001 | `uvicorn ptalk_v1.main:app` (SCREEN ptalk_v1) | `location /` |
| ptalk_v2 | :8002 | `uvicorn ptalk_v2.main:app` (SCREEN ptalk_v2) | `location /v2/` |
| ptalk_dify_eldercare | :8003 | `uvicorn` (SCREEN ptalk_dify_eldercare) | `location /eldercare/` |
| ptalk_omni (TTS) | — | SCREEN ptalk_omni (OmniVoice) | UNIX socket |

> ⚠️ Local repo đặt tên `kid_physic`/`kids`/`eldercare`; server thật = `ptalk_v1`/`ptalk_v2`/`ptalk_dify_eldercare`. ĐỪNG đụng các app thoại này (màn hình training).

### Hạ tầng dùng chung (server đa-tenant)
nginx-gateway (:8000/:80), authentik (SSO :9090/:9444, unified identity), dashboard-frontend (:4321), mosquitto (MQTT :8443→1883), cloudiot_api/db, cloudptalk-db (:5432), redis. Ngoài ra server còn các project KHÁC (legal_neo4j :7474/:7687, deeptutor, LightRAG, ollama :11435, vie-api…) — KHÔNG liên quan, cẩn thận không nhầm (vd `legal_neo4j` :7687 vs `edu_neo4j` :7688).

## 3. Giao diện (interface / API surface)

### 3.1 nginx-gateway routing (cổng vào ngoài cùng)
```
location /llm/        → gemma_4_moe:8000
location /bolt        → :7688 (neo4j bolt)
location /browser/ /db/ → :7475 (neo4j browser/db)
location /dashboard/ + / (qdrant block) → :6333
location /sso/        → :9090 (authentik)
location /api/v1/     → cloudiot_api:8000
location /v2/         → :8002 (ptalk_v2)        ← app thoại, KHÔNG phải RAG
location /eldercare/  → :8003 (ptalk_eldercare)
location /            → :8001 (ptalk_v1)
```
→ **RAG :8888 không có route nginx** ⇒ chỉ gọi được nội bộ (localhost) từ ptalk_v*/Dashboard. Đây là ranh giới bảo mật: thiết bị → ptalk → RAG.

### 3.2 RAG HTTP API (cái mà ptalk_v*/Dashboard gọi)
| Endpoint | Method | Body | Trả về | Ai gọi |
|---|---|---|---|---|
| `/v2/rag/retrieve` | POST | `{query, session_id?, user_profile{...}}` | `{context, intent, sources}` | ptalk voice apps |
| `/retrieve` (legacy) | POST | như trên | `{context, retrieved_sources, intent}` | client cũ |
| `/v2/moderation/expand-topic` | POST | `{topic, max_words?}` | `{topic, description, words[]}` | Dashboard (kiểm duyệt) |
| `/health` | GET | — | `{status:"ok"}` | health check |

### 3.3 Client context contract (điều kiện đạt anchor ~97%)
`user_profile` thiết bị PHẢI gửi (xem [client/required-context-contract](../client/required-context-contract.md)):
```json
{ "lop": 8, "bo_sach": "CTST", "subject": "toan", "tap": 1,
  "current_lesson": "Hình thang - Hình thang cân", "trang": 35 }
```
Ánh xạ client→server: `volume→tap`, `page→trang`, `book_set→bo_sach`, `grade→lop`, `lesson_title→current_lesson`. Thiếu `current_lesson`/`trang`+`tap` ⇒ degraded mode (rơi về content-vector/route thường, KHÔNG đạt 97%). `rag_client` hiện gửi `{}` → cần tích hợp.

### 3.4 RAG retrieve pipeline (bên trong /v2/rag/retrieve)
`parse_structured_query` → **companion `query_lesson_card`** (current_lesson→tên bài→trang+tap→content-vector; gate `bs≥0.50 AND (margin≥0.04 OR bs≥0.60)`) → Tier-A structured (`bai_no`/`trang`) → Tier-A concept → router rule-based (Gemma-free) → Neo4j KnowledgeChunk/LessonGuide → Qdrant/Neo4j vector fallback. Chi tiết: [research/anchoring-current-method](../research/anchoring-current-method.md).

## 4. Trạng thái code (prod vs repo)
- **Prod :8888 = monolith** `rag_server.py` (1317 dòng, đã promote): prod-base + companion inline + moderation. Backup `rag_server.py.bak_pre_promote_20260622`.
- **Refactored = repo** `packages/{knowledge_core,retrieval,rag_router}` + `apps/companion_api/server.py` (thin) — **parity 100% vs monolith**, đủ moderation → ứng viên thay prod lần migrate sau (sync packages + thin → :8888, xem [refactor/migration-plan](../refactor/migration-plan.md)).
- edu Neo4j: data live (en-dash fix 29 bài + enrich STEM actor `<SUBJ>_ENRICH_2026_06`).

## 5. Deploy / ops
- Launch = script file + `nohup` (inline ssh hay fail). prod: `pkill -9 -f 'rag_server\.py'` (literal dot — KHÔNG match canary) `; sleep 6; nohup venv/bin/python -u rag_server.py > logs/rag.log 2>&1 &`. canary: `bash /tmp/start_canary.sh`.
- Restart prod = ESP32 downtime ngắn (~16s) → low-traffic. Rollback: `cp rag_server.py.bak_pre_promote_20260622 rag_server.py` + restart.
- ⚠️ SSH server fail2ban khi nhiều kết nối nhanh → lệnh đơn, giãn cách.
- Backup KG: `neo4j-admin database dump` qua container tạm → rclone Drive (xem [operations/backup-restore](../operations/backup-restore.md)).
