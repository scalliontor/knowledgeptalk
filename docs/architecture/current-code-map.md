# Current Code Map — Knowledge PTalk (Repo Cartographer)

> Lập bởi Repo Cartographer (2026-06-22). **Chỉ phân tích, KHÔNG sửa logic.** Nguồn sự thật trạng thái: `docs/project_state/2026-06-22-canonical.md`.
> Mục tiêu: bản đồ dependency của repo LOCAL để chuẩn bị refactor, phân biệt rõ **repo** vs **server-only**.

## 0. Tóm tắt 30 giây (đọc trước)

- **Runtime production KHÔNG nằm trong repo này.** Production = single-file `rag_server.py` (:8888) + `rag_server_canary.py` (:8889) trên SERVER `/home/namnx/Ptalk_project/CloudPTalk`. Repo local = **scripts build/ingest/backtest + patch-server + docs + graphify-out**.
- Repo có **HAI thế hệ code không liên thông**:
  - `rag_edu/src/` = kiến trúc **CŨ / DEAD** (FastAPI multi-file, Postgres + Qdrant + Neo4j, orchestrator + 9 retriever class). Sửa lần cuối **2026-04**. KHÔNG phải đường production.
  - `rag_edu/scripts/schema_v3_2026_06/` = **bộ làm việc LIVE** (build companion Lesson Card, backtest đối thực server đang chạy, patch trực tiếp file server). Sửa tới **2026-06-16**.
- Logic anchor/retrieval THẬT chỉ tồn tại trong `rag_server*.py` (server-only) **+ các patch script** trong repo dùng `str.replace` để vá file server đó. Đây là điểm rủi ro lớn nhất khi refactor.

## 1. Nhóm chức năng → file (repo vs server)

Ký hiệu: **[REPO]** có trong repo · **[SERVER-ONLY]** chỉ trên server (không có trong repo) · **[DEAD]** còn trong repo nhưng không thuộc đường production hiện tại.

### A. Serving API (đường latency-critical — production)
| File | Vị trí | Trạng thái |
|---|---|---|
| `rag_server.py` (:8888 prod) | `/home/namnx/Ptalk_project/CloudPTalk/` | **[SERVER-ONLY]** — `route_query()`, `query_structured_exact()`, anchor theo `current_lesson`/tên bài/trang+tập, content-vector gate, sanitize nguồn. **KHÔNG có trong repo.** |
| `rag_server_canary.py` (:8889) | same server | **[SERVER-ONLY]** — bản canary nhận patch trước; backtest chấm ở đây. |
| `rag_server_merged.py` | server `/tmp/` | **[SERVER-ONLY]** — bản merged giữ moderation, đã test 8890, chưa promote. |
| `rag_edu/src/api/main.py` | repo | **[DEAD]** — FastAPI `/retrieve` cũ, lifespan init Postgres pool + BGE + Qdrant. KHÁC hẳn rag_server.py. |

> **GAP:** Không có bản copy/mirror của `rag_server*.py` trong repo. Mọi phân tích logic anchor thật phải đọc trên server (read-only) hoặc suy từ patch script. Cartographer KHÔNG được SSH vòng này → đánh dấu là điểm mù.

### B. Router / Anchor (logic định tuyến structured-first)
| File | Vị trí | Trạng thái |
|---|---|---|
| `route_query()`, `query_structured_exact()`, `query_concept_exact()` | `rag_server_canary.py` | **[SERVER-ONLY]** (định nghĩa thật) |
| `patch_tc_canary.py` | `scripts/schema_v3_2026_06/` | **[REPO] — NGUY HIỂM**: `str.replace` vá `rag_server_canary.py` (grade propagation + Tier-A concept-exact). Nguồn sự thật của một phần logic anchor sống ở ĐÂY dạng diff. |
| `patch_tc2_concept_match.py` | same | **[REPO] — NGUY HIỂM**: patch thứ 2 vá cùng file server. |
| `rag_edu/src/retrieval/classifier.py` | repo | **[DEAD]** — QueryClassifier rule-based + LLM của kiến trúc cũ. Không phải router production. |
| `rag_edu/src/retrieval/orchestrator.py` | repo | **[DEAD]** — RAGOrchestrator điều phối 9 retriever cũ. |
| `rag_edu/src/retrieval/subject_detector.py`, `taxonomy.py` | repo | **[DEAD]** — taxonomy/intent của kiến trúc cũ. |

### C. Graph / Schema (Neo4j edu — bolt:7688)
| File | Vị trí | Trạng thái | Ghi chú |
|---|---|---|---|
| `build_book_generic.py` | `schema_v3_2026_06/` | **[REPO] — GHI DB**: MERGE `:Lesson` + theory(BGE) + practice_json + trang. Idempotent (MERGE, không DELETE). Gọi Gemma. |
| `backfill_worknorm.py`, `backfill_g15.py` | same | **[REPO] — GHI DB**: SET `work_name_norm`/grade backfill. |
| `fix_concept_norm.py`, `v_a_work_name.py`, `t_b2_fine_concepts.py` | same | **[REPO] — GHI DB**: MERGE/SET Concept norm + work_name. |
| `tv_migrate.py` | same | **[REPO] — GHI DB**: migrate Tiếng Việt schema. |
| `pull_kg_tree.py` | same | **[REPO]** read-only dump cây KG. |
| `loigiaihay_neo4j_import.py`, `poc_neo4j_import.py`, `mass_graph_ingestion.py`, `graph_ingestion_crawler.py` | `scripts/` | **[REPO] — GHI DB (legacy ingest)**. Schema cũ; rủi ro nếu chạy nhầm lên DB hiện tại. |
| `neo4j_reorganize_audit.py`, `poc_neo4j_query.py` | `scripts/` | **[REPO]** audit/query read. |

> Tất cả script Neo4j hardcode `bolt://localhost:7688` (**19 file**) → ngầm định chạy TRÊN server. Chạy từ máy local sẽ fail/đụng DB sai tuỳ tunnel.

### D. Vector / Embedding (BGE)
| File | Vị trí | Trạng thái |
|---|---|---|
| Embedding ở serve path | `rag_server*.py` | **[SERVER-ONLY]** — BGE load ~30s lúc khởi động. |
| `build_book_generic.py` (SentenceTransformer encode theory) | `schema_v3_2026_06/` | **[REPO]** — embed lúc build, ghi vào Neo4j. |
| `exp_vector_rerank.py` | same | **[REPO]** experiment vector rerank (gọi Gemma + concept_exact). Không chắc còn dùng → ứng viên dead. |
| `rag_edu/src/embeddings.py`, `qdrant_client_mgr.py` | repo | **[DEAD]** — Qdrant + BGE của kiến trúc cũ. Production KHÔNG dùng Qdrant. |
| `embed_math.py`, `embed_khtn.py`, `embed_soc.py` | `scripts/` | **[DEAD/legacy]** — embed Qdrant cũ. |

### E. Backtest / Eval (gate — đối thực server đang chạy)
| File | Vị trí | Trạng thái |
|---|---|---|
| `backtest_book.py` | `schema_v3_2026_06/` | **[REPO]** — gọi `http://localhost:{PORT}/retrieve` (mặc định :8889), chấm anchor/mode/cruft/guard + P50/P95. **Gate chính.** Cũng gọi Gemma để sinh câu hỏi test. |
| `megatest.py` | same | **[REPO]** — sweep :8889 theo dimension, report per-book/per-dim/fails. |
| `bench_fullflow.py` | same | **[REPO]** — bench prod_8888 + canary_8889 song song. |
| `latency_bench.py` | same | **[REPO]** — đo latency. |
| `eval_toan_full.py`, `eval_van_full.py`, `eval_van_struct.py`, `eval_tv.py`, `eval_natural.py`, `diag_weak.py`, `verify_arch_toan.py` | same | **[REPO]** — eval theo môn / chẩn weak slice. Một số gọi Gemma. |
| `run_benchmark.py`, `generate_benchmark.py`, `test_*_retrieval.py` | `scripts/` | **[DEAD/legacy]** — benchmark kiến trúc cũ (gọi `src/`). |
| Artifact: `reports/backtest/2026-06-17_full-sweep/*.json` (81 file) | repo | **[REPO]** — keys: `by_dimension`, `sample_fails`, `latency_ms`, `anchor_acc`, `guard_acc`, `cruft_on_cards`. Dùng OFFLINE, không cần server. |

### F. Ingest / Crawl (nguồn → DB)
| File | Vị trí | Trạng thái |
|---|---|---|
| `build_pagemap_vietjackme.py` | `schema_v3_2026_06/` | **[REPO]** — map trang từ sitemap vietjack.me. |
| `crawl_grade9.py`, `crawl_ngu_van_full.py`, `mass_spider.py`, `math_spider.py`, `khtn_spider.py`, `soc_spider.py`, `primary_spider.py`, `loigiaihay_*_spider.py`, `vietjack_qa_spider.py` | `scripts/` | **[REPO/legacy]** — crawler 2 stack song song (xem memory `crawler_ingestion_state`). Phần lớn dùng 1 lần. |
| `post_process_*.py`, `llm_metadata_cleaner.py`, `init_db.py`, `init_dummy_data.py` | `scripts/` | **[REPO/legacy]** post-process + init Postgres cũ. |

### G. Moderation / Sanitize (sạch nguồn)
| File | Vị trí | Trạng thái |
|---|---|---|
| sanitize/moderation serve path | `rag_server*.py` | **[SERVER-ONLY]** — lọc `vietjack`/`Xem lời giải`/`Giáo viên VietJack`. Bản merged giữ moderation endpoint, canary thiếu. |
| `sanitize()` trong `build_book_generic.py` | `schema_v3_2026_06/` | **[REPO]** — regex bóc cruft nguồn LÚC BUILD (`(Giáo viên VietJack)`, `Xem lời giải`, `Video Giải`...). Đây là tuyến phòng thủ "sạch nguồn" phía ingest. |

### H. Client
| File | Vị trí | Trạng thái |
|---|---|---|
| `rag_client` (gửi context tới rag_server) | CloudPTalk (server) | **[SERVER-ONLY]** — hiện gửi `{}` (gap canonical #4): chưa gửi `current_lesson`/`trang`+`tap` → cần contract. KHÔNG có trong repo này. |

## 2. Duplicated logic (ứng viên gom vào /packages/* về sau — chưa làm vòng này)

- **`fold()` / `_fold()` (bỏ dấu tiếng Việt)** lặp trong **15 script** `schema_v3_2026_06/*.py` (mỗi script tự định nghĩa lại). Có cả biến thể `wslug()`/`sanitize()`. → ứng viên #1 cho `packages/text_norm`.
- **`bolt://localhost:7688` + auth env** hardcode trong **19 script** → ứng viên `packages/db` (driver factory).
- **Gemma `http://localhost:8080/v1/chat/completions` + `gemma()` wrapper** lặp trong **6 script** → ứng viên `packages/llm_client` (build/ingest-only, KHÔNG vào serve path).
- **Schema synth (SCHEMAS/ROLE/FAMILY) + manifest inference** chỉ ở `build_book_generic.py` (chưa lặp) nhưng là core của builder → tách thành module có test trước khi đụng.

> ⚠️ **Lưu ý migration:** Logic anchor/route THẬT sống trong `rag_server*.py` single-file trên server, KHÔNG ở các script này. Gom script-utils thành `/packages/*` **không** đồng nghĩa đã refactor runtime. Áp `/packages/*` vào runtime cần **migration plan riêng** (single-file → package, deploy lại, backtest gate). Xem `docs/refactor/refactor-risk-register.md`.

## 3. Dead code (còn trong repo, KHÔNG thuộc đường production) — KHÔNG đề xuất xoá

- Toàn bộ `rag_edu/src/` (api/main.py, database.py psycopg2, embeddings.py, qdrant_client_mgr.py, llm.py, `retrieval/*`). Kiến trúc Postgres+Qdrant multi-file, sửa lần cuối 2026-04. Production đã chuyển sang Neo4j-first single-file. Giữ lại để tham chiếu thiết kế, **không** dùng làm cơ sở refactor runtime.
- `scripts/` thế hệ cũ: `embed_*`, `*_spider`, `post_process_*`, `run_benchmark.py`, `generate_benchmark.py`, `test_*_retrieval.py`, `init_db.py`, `init_dummy_data.py`, `poc_*`.
- `exp_vector_rerank.py` trong schema_v3 (experiment, không nằm trong builder/backtest live) — xác nhận với owner trước khi coi là dead.
- `old/` (PDF SGK, plan .md, spider mẫu) = tài liệu lịch sử, không phải code chạy.

## 4. Script NGUY HIỂM (đụng DB hoặc đụng file server) — bảng cảnh báo

| Script | Tác động | Mức |
|---|---|---|
| `patch_tc_canary.py`, `patch_tc2_concept_match.py` | `str.replace` GHI ĐÈ `rag_server_canary.py` trên server (có backup `.bak`) | **CAO** — sửa runtime. Chạy nhầm ngoài server / sai phiên bản file = hỏng anchor. |
| `build_book_generic.py` + `backfill_*` + `fix_concept_norm.py` + `*_norm`/`v_a_work_name`/`t_b2_fine_concepts` + `tv_migrate.py` | MERGE/SET vào Neo4j edu (:7688) | **TRUNG-CAO** — idempotent (MERGE, KHÔNG thấy DETACH DELETE) nhưng ghi DB production. |
| `loigiaihay_neo4j_import.py`, `mass_graph_ingestion.py`, `graph_ingestion_crawler.py`, `poc_neo4j_import.py` | Ingest schema CŨ vào Neo4j | **CAO nếu chạy nhầm** — schema khác hiện tại, có thể tạo node rác. |
| `backtest_book.py`, `megatest.py`, `bench_fullflow.py` | Gọi `/retrieve` server đang chạy (read) + Gemma (sinh test) | **THẤP-TRUNG** — read-only với DB nhưng tạo tải lên server prod/canary; tốn token Gemma. |

> Tin tốt: **không tìm thấy `DETACH DELETE` / `DROP` / `TRUNCATE`** trong `schema_v3_2026_06/`. Các ghi DB đều dạng MERGE/SET (idempotent). Vẫn cần guard env trước khi chạy.

## 5. Điểm mù của Cartographer (ghi rõ để Agent sau xử lý)

1. Nội dung thật `rag_server.py`/`rag_server_canary.py`/`rag_server_merged.py` — **chưa đọc** (server-only, không SSH vòng này). Logic anchor/route/sanitize production chỉ suy gián tiếp qua patch script.
2. `rag_client` contract thật (đang gửi `{}`) — server-only.
3. Quan hệ "patch script ↔ phiên bản file server hiện tại" — không verify được anchor `assert old1 in src` còn khớp file server hiện tại hay không.
