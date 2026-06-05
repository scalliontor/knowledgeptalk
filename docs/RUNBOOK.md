# RUNBOOK — PTalk RAG (vận hành, debug, hiểu data)

> Tài liệu vận hành thực chiến. Đọc kèm [00_STATE.md](00_STATE.md) (trạng thái) + [design/kg-schema-v3.md](design/kg-schema-v3.md) (schema).
> **Quy ước**: secret tham chiếu `server.txt` / `.env`, KHÔNG chép giá trị vào doc.

## 1. Vị trí code (server là sự thật, KHÔNG phải repo này)
RAG live ở **server** `namnx@171.226.10.121`, thư mục `/home/namnx/Ptalk_project/CloudPTalk/`:
| File | Vai trò |
|---|---|
| `rag_server.py` | **PROD** (:8888) — ESP32 + CloudPTalk gọi. Có endpoint `/retrieve`, `/v2/rag/retrieve`, `/health`, **`/v2/moderation/expand-topic`** (kiểm duyệt phụ huynh). |
| `rag_server_canary.py` | **Bản nháp/test** (:8889) — nơi phát triển code mới trước khi merge sang prod. |
| `rag_server.py.bak_*` | Backup từng lần sửa (restore khi hỏng). |
| `venv/` | Python env (có sentence-transformers, neo4j, qdrant, fastapi, uvicorn). |
| `logs/rag_server.log`, `logs/rag_canary.log` | Log. |
| `ingestion/` | Script crawl + embed + upsert Neo4j. |

> Repo `Knowledgeforptalk` này = **tri thức/dữ liệu + tài liệu**, KHÔNG phải code đang chạy.

## 2. ⛔ Cách START/RESTART rag_server (quan trọng — đã tốn rất nhiều công)
**Lệnh inline qua ssh để start rag_server BỊ LỖI** (output bị nuốt, ssh drop ~72s đúng lúc uvicorn startup; screen/tmux/nohup inline đều chết). **CÁCH CHẠY ĐƯỢC = viết SCRIPT FILE rồi chạy:**
```bash
# 1) Tạo script trên server, ví dụ /tmp/start_rag.sh:
cat > /tmp/start_rag.sh <<'SH'
#!/bin/bash
cd /home/namnx/Ptalk_project/CloudPTalk
pkill -9 -f rag_server.py; sleep 8
nohup venv/bin/python -u rag_server.py > logs/rag_server.log 2>&1 &
SH
# 2) Chạy: ssh '... bash /tmp/start_rag.sh'
# 3) Đợi ~25-40s (BGE load), verify:
curl localhost:8888/health      # {"status":"ok"}
```
- Dùng `venv/bin/python` (KHÔNG `source venv/bin/activate` — hang trong shell non-tty).
- BGE-m3 load ~25s (2.1GB VRAM). Sau đó uvicorn bind 0.0.0.0:8888.
- Canary: y hệt với `rag_server_canary.py` (port 8889 trong file).
- **Trong terminal interactive của anh** (tty thật): `screen -dmS ptalk_rag bash -c "source venv/bin/activate; python3 -u rag_server.py > logs/rag_server.log 2>&1"` chạy ổn (khác sshpass non-tty).

## 3. Truy cập + verify nhanh
```bash
# SSH (creds trong server.txt)
sshpass -p '<pass>' ssh -o StrictHostKeyChecking=no namnx@171.226.10.121 '<cmd>'   # nhớ | tr -d '\r'
# Neo4j (read)
docker exec edu_neo4j cypher-shell -u neo4j -p '<neo4j_pass>' --format plain "<cypher>"
#   hoặc python: bolt://localhost:7688 auth ("neo4j","<neo4j_pass>")
# Gemma
curl -s localhost:8080/v1/models -H "Authorization: Bearer <gemma_key>"
# Health
curl -s localhost:8888/health ; curl -s localhost:8889/health
```

## 4. Kiến trúc retrieve (code MỚI — structured-first, Gemma-free)
```
/retrieve(query, user_profile{lop,bo_sach,subject})
  parse_structured_query  (regex bài/trang + profile)         ~1ms
  ├─ Tier A structured (có bài/trang)  → Cypher exact          ~40ms → return
  ├─ Tier A concept (chủ đề)           → COVERS word-overlap   ~10ms → return
  └─ rule router (route_query_rule_based — KHÔNG Gemma)
        ├─ recite (_is_recite)         → LiteratureText verbatim
        └─ vector fallback (BGE embed raw query, grade+book filter)  ~300ms
```
- **KHÔNG gọi Gemma trong retrieve** (router regex 93% vs Gemma 53% subject, nhanh 20.000×). Gemma chỉ cho compose câu trả lời (service CloudPTalk khác).
- Prod HIỆN TẠI vẫn code CŨ: `route_query` (Gemma) chạy mọi query → **2-3s** (chờ merge code mới → ~50ms).

## 5. Hiểu DATA (Neo4j edu)
5 môn K-9 đã lên **schema v3** (3 lớp tách: Document/Concept/Structure). Chi tiết: [design/kg-schema-v3.md](design/kg-schema-v3.md).
```cypher
// Tổng quan
MATCH (k:KnowledgeChunk) WHERE k.production_ready=true RETURN count(k);          // ~15.2K
MATCH (c:Concept) RETURN c.subject, count(*) ORDER BY count(*) DESC;             // ~3.9K total
MATCH ()-[r:COVERS]->() RETURN count(r);                                          // ~5.2K
MATCH (w:LiteraryWork) WHERE EXISTS{(:LiteratureText)-[:VERBATIM_OF]->(w)} RETURN count(w); // 68 (recite)
// 1 chunk
MATCH (k:KnowledgeChunk {subject_code:'toan',production_ready:true})-[:COVERS]->(c:Concept)
RETURN k.title,k.lesson_no,k.trang_no,k.content_class,c.name LIMIT 5;
```
**Fields chunk**: `subject_code, grade, bo_sach, production_ready, lesson_no, trang_no, content_class, concept_name, work_name, work_name_norm, section_type, variant`. **Concept**: `name, name_norm(folded đ→d), subject, strand, grade_introduced, level`. **Edges**: COVERS, ABOUT_WORK, VERBATIM_OF, PREREQ(Toán).
- ⛔ **fold = đ→d RỒI strip dấu** (unicodedata KHÔNG tách đ). Mọi `name_norm`/`work_name_norm` theo quy tắc này; query phải fold y hệt khi so.
- content_class: Toán `vietjack_lesson/vietjack_exercise/lgh_qa`; Văn dùng `section_type`+`variant`; KHTN `lesson/exercise/quiz/...`; TV `tv_lesson/tv_vbt/tv_assessment`. **UI map nhãn TV, đừng hiện "vietjack"** (xem dashboard-kg-viewer-v2.md §2).
- Mọi thay đổi **actor-tagged, reversible** (`MATCH (n) WHERE n.<actor>='...' ...`).

## 6. DEBUG playbook
| Triệu chứng | Cách |
|---|---|
| Concept query trả rỗng | Test `_fold("phân số")` phải = `"phan so"`. Nếu ra `"phân số"` → unidecode no-op, name_norm lệch. Fix: `_fold` self-contained (đ→d+NFD). |
| rag_server không lên | §2 script method. `head -8 logs/rag_server.log` tìm "Uvicorn running". BGE load test: `venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"`. |
| Sai môn (misroute) | `rag_edu/scripts/schema_v3_2026_06/exp_regex_v2.py` (router A/B regex vs Gemma). |
| Latency cao | `bench_fullflow.py` (prod cũ 2.7s vì Gemma router; code mới ~50ms). |
| Eval 1 môn | `eval_{toan,van,tv}_full.py` (template, scale) + `eval_natural.py` (**Gemma4 voice — gate THẬT**; template đánh giá CAO hơn thực tế). |
| Recite sai/thiếu | LiteratureText coverage (68 works). Detection 100%; thiếu thì crawl thêm thơ (Thi Viện/loigiaihay). |

## 7. Quy tắc an toàn (CLAUDE.md + bài học session)
- ⛔ Server production dùng chung — chỉ read-only trừ khi được phép. **Restart prod = downtime ESP32** → cẩn thận, backup + script method + rollback sẵn.
- ⛔ KHÔNG copy canary→prod thẳng (canary thiếu `/v2/moderation/expand-topic`). Merge giữ đủ endpoint.
- ⛔ KHÔNG commit secret. KHÔNG đụng training screens.
- ⛔ Verify kiến thức trước promote (đã bắt bug SGK cũ, concept dead, misroute nhờ verify).

Liên quan: [00_STATE.md](00_STATE.md) · [design/kg-schema-v3.md](design/kg-schema-v3.md) · [evaluation/](evaluation/) · scripts `rag_edu/scripts/schema_v3_2026_06/`
