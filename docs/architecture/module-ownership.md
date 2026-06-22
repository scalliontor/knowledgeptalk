# Module Ownership — Knowledge PTalk

> Lập bởi Repo Cartographer (2026-06-22). Đi kèm `current-code-map.md`. **Mô tả, không sửa logic.**
> Cột "Repo hay server-only": **REPO** = có trong repo này · **SERVER** = chỉ trên server · **DEAD** = trong repo nhưng ngoài đường production.

## Bảng module → file → vai trò → vị trí → rủi ro

| Module | File chính | Vai trò | Repo/Server | Rủi ro |
|---|---|---|---|---|
| **Serving runtime (prod)** | `rag_server.py` (:8888) | Đường thoại thật: route → anchor → retrieve → sanitize → trả về. Gemma-free serve path. | **SERVER** | Single-file; không có bản trong repo → mọi refactor mù dễ lệch. Restart = ESP32 downtime. |
| **Serving runtime (canary)** | `rag_server_canary.py` (:8889) | Bản thử patch trước prod; backtest chấm ở đây. | **SERVER** | Bị patch bằng `str.replace` từ repo; thiếu moderation endpoint so với merged. |
| **Serving runtime (merged)** | `rag_server_merged.py` (`/tmp`, test 8890) | Giữ moderation + companion; ứng viên promote :8888. | **SERVER** | Chưa promote; là baseline đo của canonical. |
| **Router/Anchor (logic thật)** | `route_query()`, `query_structured_exact()`, `query_concept_exact()` trong rag_server* | Structured-first: `current_lesson`→tên bài→trang+tập→content-vec; scope môn+lớp+bộ+tập. | **SERVER** | Invariant cốt lõi (canonical §Invariant). Hỏng = tụt anchor/guard. |
| **Router/Anchor (diff trong repo)** | `patch_tc_canary.py`, `patch_tc2_concept_match.py` | Vá grade-propagation + Tier-A concept-exact vào file server. | **REPO (nguy hiểm)** | Ghi đè file server; phụ thuộc anchor `assert old in src`. Một phần logic anchor chỉ tồn tại ở dạng patch. |
| **Graph builder (companion)** | `build_book_generic.py` | Dựng `:Lesson` + theory(BGE) + practice_json + trang cho 1 quyển. Gemma synth theo FAMILY môn. Idempotent MERGE. | **REPO (ghi Neo4j + gọi Gemma)** | Ghi DB production :7688; sai manifest → node lệch bài/trang. |
| **Graph backfill/norm** | `backfill_worknorm.py`, `backfill_g15.py`, `fix_concept_norm.py`, `v_a_work_name.py`, `t_b2_fine_concepts.py`, `tv_migrate.py` | SET `work_name_norm`/grade/Concept norm; migrate TV. | **REPO (ghi Neo4j)** | Ghi DB; liên quan trực tiếp gap Lịch sử `work_name_norm` lệch. |
| **Graph ingest (legacy)** | `loigiaihay_neo4j_import.py`, `mass_graph_ingestion.py`, `graph_ingestion_crawler.py`, `poc_neo4j_import.py` | Ingest schema cũ vào Neo4j. | **REPO (ghi Neo4j, legacy)** | Schema khác hiện tại → chạy nhầm tạo node rác. |
| **Vector/Embedding (serve)** | BGE trong rag_server* | Encode query + content-vec gate. | **SERVER** | Load ~30s; không đưa LLM vào path này (invariant). |
| **Vector/Embedding (build)** | SentenceTransformer trong `build_book_generic.py`; `exp_vector_rerank.py` | Embed theory lúc build; experiment rerank. | **REPO** | `exp_vector_rerank` có thể dead. |
| **Vector/Embedding (cũ Qdrant)** | `src/embeddings.py`, `src/qdrant_client_mgr.py`, `embed_*.py` | Qdrant + BGE kiến trúc cũ. | **DEAD** | Production không dùng Qdrant; gây nhầm nếu tưởng là live. |
| **Backtest/Eval (gate)** | `backtest_book.py`, `megatest.py`, `bench_fullflow.py`, `latency_bench.py`, `eval_*` , `diag_weak.py`, `verify_arch_toan.py` | Gọi `/retrieve` server, chấm anchor/mode/guard/cruft + latency. Gate merge. | **REPO (gọi server + Gemma)** | Tạo tải lên prod/canary; tốn token; cần server đang chạy. |
| **Backtest artifact** | `reports/backtest/2026-06-17_full-sweep/*.json` (81) | Kết quả full sweep offline (by_dimension, sample_fails, latency). | **REPO (data, offline)** | An toàn; nguồn phân tích weak slice không cần server. |
| **Ingest/Crawl** | `build_pagemap_vietjackme.py`; `*_spider.py`, `crawl_*.py`, `post_process_*.py`, `llm_metadata_cleaner.py` | Crawl nguồn + map trang + post-process. | **REPO (phần lớn legacy/1 lần)** | Đụng nguồn ngoài; một số ghi Postgres cũ. |
| **Moderation/Sanitize (serve)** | sanitize/moderation trong rag_server* (+ endpoint ở merged) | Lọc cruft nguồn (vietjack/lời giải/cô VietJack) ở serve path. | **SERVER** | Canary thiếu endpoint; "sạch nguồn" invariant. |
| **Sanitize (build)** | `sanitize()` trong `build_book_generic.py` | Bóc cruft nguồn lúc ingest (regex). | **REPO** | Tuyến phòng thủ sạch-nguồn phía build; sửa regex sai → leak. |
| **Client** | `rag_client` (CloudPTalk) | Gửi context `current_lesson`/`trang`/`tap` tới server. | **SERVER** | Hiện gửi `{}` → anchor 97% chỉ đạt khi có context. Gap canonical #4. |
| **API cũ (FastAPI)** | `src/api/main.py`, `src/database.py`, `src/llm.py`, `src/retrieval/{orchestrator,classifier,retrievers,taxonomy,subject_detector}.py` | RAG multi-file Postgres+Qdrant+Neo4j, 9 retriever class. | **DEAD** | Sửa lần cuối 2026-04; KHÔNG production. Đừng dùng làm cơ sở refactor runtime. |
| **Tài liệu** | `docs/**`, `ARCHITECTURE.md`, `graphify-out/**`, `old/**` | Thiết kế, state, KG snapshot, lịch sử. | **REPO (docs)** | `graphify-out` phần lớn mirror; `old/` lịch sử. |
| **Môi trường** | `rag_edu/venv/` (python3.8), `rag_edu/data/` | Virtualenv + data crawl. | **REPO (gitignored)** | Không tracked nhưng nằm vật lý trong repo → nhiễu khi build tool/scan toàn cây. |

## Owner đề xuất (để Agent refactor giao việc — chưa thực thi)

- **Runtime anchor/route/sanitize** → owner = người có quyền server (Agent 2, migration plan riêng). Repo KHÔNG được tự ý "package hoá" rồi coi như deployed.
- **Graph builder + backfill/norm** → owner = data/ingest; mọi run phải có backup Neo4j (release gate).
- **Backtest/eval** → owner = Backtest Engineer; là gate bắt buộc trước promote.
- **Dead `src/` + legacy scripts** → để nguyên (không xoá vòng này); cần quyết định archive ở PR riêng có ghi rõ.

## Quy ước "repo có thật chạy không"

1. Nếu file hardcode `bolt://localhost:7688` hoặc `localhost:8080` hoặc path `/home/namnx/...` → **mặc định chạy TRÊN server**, không phải local.
2. Nếu file import `src.retrieval.*` / `psycopg2` / `qdrant_client` → thuộc kiến trúc **DEAD**.
3. Logic production sống ở `rag_server*.py` (server) — repo chỉ có **builder + backtest + patch-diff**.
