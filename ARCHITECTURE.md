# Knowledgeforptalk — Tri thức giáo dục & pipeline RAG

> Kho tri thức + pipeline nạp dữ liệu giáo dục Việt Nam cho RAG của hệ PTalk.
> Toàn cảnh: [../ARCHITECTURE.md](../ARCHITECTURE.md). Bộ não gọi RAG: [../CloudPTalk/ARCHITECTURE.md](../CloudPTalk/ARCHITECTURE.md).

## 1. Vai trò
Cung cấp ngữ cảnh tri thức (sách giáo khoa, văn học, KHTN, lịch sử…) để LLM trả lời "có căn cứ". Gồm 2 phần dễ nhầm:

1. **Pipeline ingest** (chính ở repo này): crawl → parse → validate → embed → nạp vào **Neo4j** (+ Qdrant).
2. **Microservice serving** `rag_edu` (FastAPI) — bản dùng `multilingual-e5-large` + Postgres `rag_edu` + Qdrant. Đây là bản thay thế/đang phát triển.

> ⚠️ **RAG đang phục vụ live** cho CloudPTalk KHÔNG nằm ở repo này mà là `rag_server.py` trong CloudPTalk (chạy `:8888` trên server, embedding **BGE-M3**, truy vấn **Neo4j edu**). Repo này là nguồn **dữ liệu/tri thức** mà rag_server truy vấn, cộng một microservice serving riêng. Khi đụng RAG, xác minh bản nào đang chạy (`/proc/<pid>/cmdline` của process nghe `:8888`).

## 2. Pipeline ingest (rag_edu/)
```
source_config.yaml → crawl_index.py → parse_* (math / khtn / lichsu / vietjack) →
validate_records.py → normalized_jsonl/*.jsonl → embed_and_upsert_neo4j.py → Neo4j
```
Embedding ingest: **BAAI/bge-m3** (1024D) cho nhánh Neo4j; microservice `rag_edu` dùng `intfloat/multilingual-e5-large` (prefix `query:`/`passage:`).

## 3. Kho dữ liệu

| Backend | Địa chỉ | Dùng cho |
|---|---|---|
| **Neo4j edu** | container `edu_neo4j` — bolt `:7688`, http `:7475`, proxy `:9100`; `bolt://171.226.10.121:9100` | RAG live (rag_server BGE-M3): node `KnowledgeChunk`, `LiteratureText`, `FullDocument`, `Section`… |
| **Qdrant** | `:6333` | Vector fallback / microservice `rag_edu` (collections `sgk_readings`, `language_concepts`, `writing_outlines`, `writing_samples`) |
| **Postgres `rag_edu`** | container `rag_postgres` `:5433` | Metadata cho microservice `rag_edu` |

Schema Neo4j (đại lượng): `Grade`(9) · `Subject` · `BookSeries`(KNTT/Chân trời/Cánh diều) · `Unit` · `LessonGuide` · `KnowledgeChunk` (đã làm sạch, lọc `production_ready=true`) · `LiteratureText`/`RecitationSegment` (thơ/văn để đọc nguyên văn).

## 4. API serving (microservice rag_edu)
- `POST /retrieve` ⇐ `{query, user_profile?}` ⇒ `{context, retrieved_sources, intent}`.
- Orchestrator: phân loại intent (explain / recite_full_text / chat) → chọn subject → vector search.
- File: `rag_edu/src/api/main.py`, `database.py`, `qdrant_client_mgr.py`, `embeddings.py`, `retrieval/orchestrator.py`.

## 5. Liên kết với các service khác

| Chiều | Đối tác | Giao thức | Dữ liệu |
|---|---|---|---|
| ◄ được gọi | **CloudPTalk** workers (qua `rag_server.py`) | `POST /retrieve` :8888 | câu hỏi → context |
| ► đọc/ghi | **Neo4j edu** | Bolt | nạp & truy vấn KnowledgeChunk |
| ► đọc/ghi | **Qdrant** :6333 | HTTP/gRPC | vector embeddings |
| ► đọc/ghi | **Postgres `rag_edu`** :5433 | psycopg2 | metadata (microservice) |

→ Quan hệ chính: **CloudPTalk là consumer, Knowledgeforptalk là provider tri thức**. Hai bên ghép nối qua HTTP `/retrieve` và qua Neo4j edu graph.

## 6. Server-only / lưu ý
Bản chạy thật ở server: `/home/namnx/knowledgeforptalk` (ingest) và `rag_server.py` trong `/home/namnx/Ptalk_project/CloudPTalk` (serving). Log: `rag_server.log`, `rag_canary.log`.
