# Graph Report - .  (2026-06-13)

## Corpus Check
- 112 files · ~437,962 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 557 nodes · 839 edges · 75 communities (61 shown, 14 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 118 edges (avg confidence: 0.63)
- Token cost: 226,173 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_RAG Edu Retrieval Core|RAG Edu Retrieval Core]]
- [[_COMMUNITY_rag_edu FastAPI Service & DB Init|rag_edu FastAPI Service & DB Init]]
- [[_COMMUNITY_Graph Ingestion Crawler|Graph Ingestion Crawler]]
- [[_COMMUNITY_Grade-9 Crawler|Grade-9 Crawler]]
- [[_COMMUNITY_Ngữ Văn Full Crawler|Ngữ Văn Full Crawler]]
- [[_COMMUNITY_Multi-Subject Master Plan|Multi-Subject Master Plan]]
- [[_COMMUNITY_Neo4j RepairAudit|Neo4j Repair/Audit]]
- [[_COMMUNITY_Loigiaihay Spider (legacy)|Loigiaihay Spider (legacy)]]
- [[_COMMUNITY_Schema-v3 RAG State & Runbook|Schema-v3 RAG State & Runbook]]
- [[_COMMUNITY_Loigiaihay TV Spider|Loigiaihay TV Spider]]
- [[_COMMUNITY_Math Spider|Math Spider]]
- [[_COMMUNITY_RAG System Architecture|RAG System Architecture]]
- [[_COMMUNITY_Structured Retrieval Pipeline (design)|Structured Retrieval Pipeline (design)]]
- [[_COMMUNITY_Schema-v3 Migration & Evals|Schema-v3 Migration & Evals]]
- [[_COMMUNITY_Data Sources & Crawl Strategy|Data Sources & Crawl Strategy]]
- [[_COMMUNITY_Mass Graph Ingestion|Mass Graph Ingestion]]
- [[_COMMUNITY_Postgres Schema (rag_edu)|Postgres Schema (rag_edu)]]
- [[_COMMUNITY_Companion Layer & Lesson Card Pilot|Companion Layer & Lesson Card Pilot]]
- [[_COMMUNITY_KG Schema-v3 Design & Research|KG Schema-v3 Design & Research]]
- [[_COMMUNITY_Evaluation Strategy & Benchmark|Evaluation Strategy & Benchmark]]
- [[_COMMUNITY_Literature KG (Văn structure)|Literature KG (Văn structure)]]
- [[_COMMUNITY_LLM Backends & Migration Scripts|LLM Backends & Migration Scripts]]
- [[_COMMUNITY_Ingest Pipeline & Walkthrough|Ingest Pipeline & Walkthrough]]
- [[_COMMUNITY_Văn Eval Harness|Văn Eval Harness]]
- [[_COMMUNITY_Toán Arch Verify Harness|Toán Arch Verify Harness]]
- [[_COMMUNITY_Mass Spider|Mass Spider]]
- [[_COMMUNITY_Toán Eval Harness|Toán Eval Harness]]
- [[_COMMUNITY_Loigiaihay Text Spider|Loigiaihay Text Spider]]
- [[_COMMUNITY_Primary TV Spider|Primary TV Spider]]
- [[_COMMUNITY_Subject Detector (Layer 1)|Subject Detector (Layer 1)]]
- [[_COMMUNITY_KHTN Post-Process|KHTN Post-Process]]
- [[_COMMUNITY_Social Science Post-Process|Social Science Post-Process]]
- [[_COMMUNITY_Social Science Spider|Social Science Spider]]
- [[_COMMUNITY_VietJack QA Spider|VietJack QA Spider]]
- [[_COMMUNITY_ESP32CloudPTalk Integration|ESP32/CloudPTalk Integration]]
- [[_COMMUNITY_Natural-Language Eval|Natural-Language Eval]]
- [[_COMMUNITY_KHTN Spider|KHTN Spider]]
- [[_COMMUNITY_Math Post-Process|Math Post-Process]]
- [[_COMMUNITY_Tiếng Việt Eval|Tiếng Việt Eval]]
- [[_COMMUNITY_Fine Concept Extraction|Fine Concept Extraction]]
- [[_COMMUNITY_Tiếng Việt Migration|Tiếng Việt Migration]]
- [[_COMMUNITY_Loigiaihay Single Spider|Loigiaihay Single Spider]]
- [[_COMMUNITY_Benchmark Runner|Benchmark Runner]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]

## God Nodes (most connected - your core abstractions)
1. `RAGOrchestrator` - 23 edges
2. `QueryClassifier` - 15 edges
3. `RetrievedItem` - 15 edges
4. `GraphRetriever` - 15 edges
5. `RetrievedItem` - 15 edges
6. `RetrievedItem` - 14 edges
7. `QueryClassifier` - 13 edges
8. `QueryContext` - 13 edges
9. `Neo4jRepair` - 11 edges
10. `KG Schema v3` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Tier A structured + concept short-circuit` --implements--> `rag_server.py (live RAG, prod :8888)`  [INFERRED]
  docs/00_STATE.md → ARCHITECTURE.md
- `Script-file + nohup launch method` --rationale_for--> `rag_server.py (live RAG, prod :8888)`  [EXTRACTED]
  docs/RUNBOOK.md → ARCHITECTURE.md
- `:KnowledgeChunk (doc-level retrieval unit)` --shares_data_with--> `Neo4j edu graph store`  [INFERRED]
  docs/design/kg-schema-v3.md → ARCHITECTURE.md
- `Lesson Card companion (:Lesson, lesson_card tier)` --calls--> `POST /retrieve endpoint`  [EXTRACTED]
  docs/pilot/TEST_GUIDE.md → ARCHITECTURE.md
- `Chiến lược 3 tầng nguồn (Gold/Silver/Bronze)` --conceptually_related_to--> `RAG Edu Data Sources & Organization`  [INFERRED]
  old/1_khao_sat_nguon.md → rag_edu/DATA_SOURCES.md

## Import Cycles
- 1-file cycle: `rag_edu/src/api/main.py -> rag_edu/src/api/main.py`

## Hyperedges (group relationships)
- **3-layer decouple: Chunk—COVERS—Concept—PREREQ backbone** — design_kg_schema_v3_knowledgechunk, design_kg_schema_v3_concept_node, design_kg_schema_v3_prereq_dag, research_2026_06_03_graph_rag_companion_f1_decouple [EXTRACTED 0.90]
- **Structured-first Gemma-free retrieve flow** — docs_runbook_structured_first_retrieve, 00_state_tier_a, 00_state_gemma_free_retrieve, evaluation_2026_06_04_final_gate_and_latency_latency [INFERRED 0.85]
- **5-subject K-9 schema v3 migration + eval** — evaluation_2026_06_03_verify_arch_toan_eval, evaluation_2026_06_04_verify_arch_van_eval, evaluation_2026_06_04_khtn_migration_migration, evaluation_2026_06_04_xahoi_migration_migration, evaluation_2026_06_04_tieng_viet_migration_migration [EXTRACTED 0.90]
- **Structure-based RAG pipeline (classify → route → retrieve)** — 5_structure_retrieval_query_classifier, 5_structure_retrieval_rag_orchestrator, 5_structure_retrieval_sgk_reading_retriever, 5_structure_retrieval_metadata_filter_first [EXTRACTED 0.85]
- **Multi-subject ingestion flow (crawl → Postgres → Qdrant → Neo4j)** — old_walkthrough_pipeline_stack, rag_edu_data_sources_three_store_topology, old_1_khao_sat_nguon_loigiaihay_source, rag_edu_data_sources_neo4j_schema_v2 [INFERRED 0.75]
- **LaTeX preservation + voice-text pipeline for math** — old_7_khao_sat_dac_thu_tung_mon_mathjax_loss, old_8_master_plan_preserve_mathjax, old_8_master_plan_latex_to_speech, old_7_khao_sat_dac_thu_tung_mon_voice_first_formula [INFERRED 0.85]

## Communities (75 total, 14 thin omitted)

### Community 0 - "RAG Edu Retrieval Core"
Cohesion: 0.07
Nodes (36): Enum, QueryClassifier, QueryContext, QueryContext, RetrievedItem, QdrantClient, RetrievedItem, main() (+28 more)

### Community 1 - "rag_edu FastAPI Service & DB Init"
Cohesion: 0.12
Nodes (23): ChatRequest, ChatResponse, lifespan(), retrieve_endpoint(), FastAPI, QdrantClient, init_qdrant(), insert_dummy_data() (+15 more)

### Community 2 - "Graph Ingestion Crawler"
Cohesion: 0.19
Nodes (9): BaseModel, Extraction, GraphAssembler, Grounding, PassageSpan, Question, Tier 1: Traverse the DOM and apply negative filtering & strict heuristic tags., Solution (+1 more)

### Community 3 - "Grade-9 Crawler"
Cohesion: 0.22
Nodes (17): ClientSession, BeautifulSoup, classify_url(), clean_text(), crawl_category(), extract_soan_bai(), extract_tom_tat(), extract_van_ban() (+9 more)

### Community 4 - "Ngữ Văn Full Crawler"
Cohesion: 0.23
Nodes (17): Path, BeautifulSoup, abs_url(), clean_text(), get(), get_cat_links(), load_done(), main() (+9 more)

### Community 5 - "Multi-Subject Master Plan"
Cohesion: 0.16
Nodes (16): Lịch sử disambiguation (Bạch Đằng 3 trận), KHTN sub-subject detection (Lý/Hóa/Sinh), MathJax/LaTeX bị strip bởi trafilatura, Per-subject schema (không 1 schema chung), Khảo sát đặc thù từng môn, Classifier 3 lớp (subject → intent → retriever), 12 Qdrant collections theo loại×môn, Voice-first: cong_thuc_latex + cong_thuc_text (+8 more)

### Community 6 - "Neo4j Repair/Audit"
Cohesion: 0.29
Nodes (5): Any, main(), Neo4jRepair, normalize_text(), RepairStats

### Community 7 - "Loigiaihay Spider (legacy)"
Cohesion: 0.14
Nodes (8): LoigiaihaySpider, parse_url_metadata(), Scrapy Crawler cho loigiaihay.com - Lớp 1-5 Tiếng Việt =========================, Bắt đầu crawl từ các category pages., Parse category page - extract danh sách article URLs.         Category page của, Parse 1 article page, extract content bằng trafilatura., # TODO: điền các URL category khác, Extract metadata từ URL pattern của loigiaihay.          Examples:       /bai-82

### Community 8 - "Schema-v3 RAG State & Runbook"
Cohesion: 0.22
Nodes (14): _fold đ→d + NFD normalization fix, Gemma-free retrieve (regex router), Project state snapshot 2026-06-05, Tier A structured + concept short-circuit, content_class → Vietnamese label mapping (hide provenance), Dashboard KG Viewer v2 guide, 3-layer decouple (Document/Concept/Structure), docs/ index (knowledge & runbook) (+6 more)

### Community 9 - "Loigiaihay TV Spider"
Cohesion: 0.15
Nodes (7): LoigiaihaySpider, parse_url_metadata(), Scrapy Crawler cho loigiaihay.com - Lớp 1-5 Tiếng Việt =========================, Bắt đầu crawl từ các category pages., Parse category page - extract danh sách article URLs.         Category page của, Parse 1 article page, extract content bằng trafilatura., Extract metadata từ URL pattern của loigiaihay.          Examples:       /bai-82

### Community 10 - "Math Spider"
Cohesion: 0.15
Nodes (7): LoigiaihaySpider, parse_url_metadata(), Scrapy Crawler cho loigiaihay.com - Lớp 1-5 Tiếng Việt =========================, Bắt đầu crawl từ các category pages., Parse category page - extract danh sách article URLs.         Category page của, Parse 1 article page, extract content bằng trafilatura., Extract metadata từ URL pattern của loigiaihay.          Examples:       /bai-82

### Community 11 - "RAG System Architecture"
Cohesion: 0.21
Nodes (13): BAAI/bge-m3 embedding (1024D), CloudPTalk (RAG consumer), Ingest pipeline (crawl→parse→validate→embed→Neo4j), Knowledgeforptalk RAG knowledge & ingest pipeline, intfloat/multilingual-e5-large embedding, Neo4j edu graph store, Postgres rag_edu metadata, Qdrant vector store (+5 more)

### Community 12 - "Structured Retrieval Pipeline (design)"
Cohesion: 0.18
Nodes (12): CurriculumRetriever, LanguageConceptRetriever, Metadata filter trước vector search, Structure-based Retrieval Pipeline, QueryClassifier (rule + LLM), QueryContext dataclass, QueryIntent taxonomy, RAGOrchestrator (routing logic) (+4 more)

### Community 13 - "Schema-v3 Migration & Evals"
Cohesion: 0.32
Nodes (12): F1 collision fix (lesson vs exercise + chuong), KG Schema v3, Verify arch Toán eval, Actor-tagged reversible mutation, KHTN migration to schema v3, KHTN subject mislabel G6-9 (Lý/Hóa/Sinh), Natural-language eval (Gemma4 voice gate), TV hybrid Toán+Văn structure (+4 more)

### Community 14 - "Data Sources & Crawl Strategy"
Cohesion: 0.18
Nodes (12): Phân tách loại content khi crawl (no mixed collections), Khảo sát nguồn Knowledge Base lớp 1-5, Cảnh báo pháp lý scraped content, loigiaihay.com (primary crawl source), 3 bộ SGK (KNTT, CTST, Cánh Diều), Chiến lược 3 tầng nguồn (Gold/Silver/Bronze), Phụ thuộc hình ảnh (Hình 2.1) không crawl được, RAG Edu Data Sources & Organization (+4 more)

### Community 15 - "Mass Graph Ingestion"
Cohesion: 0.30
Nodes (5): AsyncGraphIngester, create_extraction(), create_grounding(), index_spider(), main()

### Community 16 - "Postgres Schema (rag_edu)"
Cohesion: 0.33
Nodes (10): conversation_history, curriculum_schedule, eval_questions, extracted_content, kb_language_concepts, kb_sgk_reading, kb_writing_outlines, kb_writing_samples (+2 more)

### Community 17 - "Companion Layer & Lesson Card Pilot"
Cohesion: 0.20
Nodes (10): Canary RAG server (:8889), Companion layer (Student/Session/CURRENT_LESSON), PREREQ DAG (Toán only, curriculum-seeded), Script-file + nohup launch method, Xã hội concept-as-lesson-topic, no PREREQ, Lesson Card companion (:Lesson, lesson_card tier), Pilot Test Guide — Văn 9 CTST t2 companion, trang_from/trang_to page-range lookup (+2 more)

### Community 18 - "KG Schema-v3 Design & Research"
Cohesion: 0.24
Nodes (10): :Concept node + COVERS edge, Doc-level chunk invariant, Concept-only paraphrase weakness (33%), F1 — decouple Concept from Chunk, F2 — explicit named edges, F7 — extraction size ≠ retrieval size, HippoRAG (cited), Microsoft GraphRAG (cited) (+2 more)

### Community 19 - "Evaluation Strategy & Benchmark"
Cohesion: 0.28
Nodes (9): A/B Test RAG vs Non-RAG baseline, Chiến lược thử nghiệm & Evaluation, Bộ eval 200 câu hỏi từ trẻ thật, LLM judge (faithfulness/relevance), Đo lường trước khi build, RAGAS eval framework, Retrieval metrics (Recall@5, Precision@5, MRR), K-9 EduRAG Performance Benchmark (Phase 7) (+1 more)

### Community 20 - "Literature KG (Văn structure)"
Cohesion: 0.25
Nodes (8): /kg-browse per-subject hierarchy, :LiteraryWork node (Văn), :LiteratureText / RecitationSegment (verbatim), Variant depth selection (chi_tiet/sieu_ngan), work_name extraction gated by section_type, Variant-fallback behavior, work_name_norm per-chunk matching, F6 — literature: recitation vs analytical + variant

### Community 21 - "LLM Backends & Migration Scripts"
Cohesion: 0.25
Nodes (8): Qwen 2.5 14B local LLM (vLLM on L40S), Schema migration thêm subject column (backward-compat), Gemma 4 OpenAI-compatible endpoint (:8000/llm/v1), Gemma 4 MoE connection guide, Neo4j Graph Schema V2 (Ngữ Văn lớp 9), eval_natural.py (Gemma4 natural-language eval gate), Schema v3 migration scripts (per-subject), Schema v3 migration & eval scripts (2026-06)

### Community 22 - "Ingest Pipeline & Walkthrough"
Cohesion: 0.32
Nodes (8): multilingual-e5-large embedding model, DB CHECK constraint grade 1-5 chặn THCS, Bug missing Lớp 8 (spider 0 links), Pipeline Scrapy → JSONL → PostgreSQL + Qdrant, Fix routing unknown + grade>=6 → soan_van, RAG Edu KB & System Walkthrough, PostgreSQL + Qdrant + Neo4j topology, rag_edu requirements.txt

### Community 23 - "Văn Eval Harness"
Cohesion: 0.46
Nodes (5): detect_sec(), detect_var(), fold(), retrieve(), score()

### Community 24 - "Toán Arch Verify Harness"
Cohesion: 0.46
Nodes (7): fold(), gemma(), main(), make_query(), pull_anchors(), retrieve(), score()

### Community 25 - "Mass Spider"
Cohesion: 0.50
Nodes (7): crawl_lesson_text(), crawl_seed(), create_extraction(), create_grounding(), fetch_html(), is_valid_lesson(), main()

### Community 26 - "Toán Eval Harness"
Cohesion: 0.38
Nodes (3): fold(), parse(), score()

### Community 27 - "Loigiaihay Text Spider"
Cohesion: 0.57
Nodes (6): create_extraction(), create_grounding(), fetch_html(), index_spider(), main(), process_url()

### Community 28 - "Primary TV Spider"
Cohesion: 0.57
Nodes (6): crawl_lesson(), create_grounding(), fetch_html(), is_valid_primary_lesson(), main(), process_seed()

### Community 29 - "Subject Detector (Layer 1)"
Cohesion: 0.40
Nodes (5): detect_subject(), Subject detector — Layer 1 of multi-subject RAG classifier. Detects which school, Quick sanity check — run with python -m src.retrieval.subject_detector, Detect school subject from query.      Returns:         (subject, confidence) wh, test_subject_detector()

### Community 30 - "KHTN Post-Process"
Cohesion: 0.53
Nodes (5): extract_exercises(), get_db_conn(), process_all(), Split KHTN content into exercises using CH/Câu and Lời giải., setup_db()

### Community 31 - "Social Science Post-Process"
Cohesion: 0.53
Nodes (5): extract_exercises(), get_db_conn(), process_all(), Split Social Science content into exercises using CH/Câu and Lời giải., setup_db()

### Community 33 - "VietJack QA Spider"
Cohesion: 0.67
Nodes (5): crawl_book_index(), crawl_qa(), fetch_html(), main(), to_safe_id()

### Community 34 - "ESP32/CloudPTalk Integration"
Cohesion: 0.40
Nodes (5): Tách RAG service riêng (Port 8888) khỏi Gateway, Tích hợp RAG vào PTalk Kid Physic (ESP32), kid_physic pipeline (STT → RAG → LLM via Redis), fetch_knowledge() rag_client helper, FastAPI /chat endpoint (port 8888)

### Community 35 - "Natural-Language Eval"
Cohesion: 0.60
Nodes (3): fold(), toan_ret(), van_ret()

### Community 39 - "Math Post-Process"
Cohesion: 0.60
Nodes (4): extract_exercises(), get_db_conn(), process_all(), Very basic heuristic to split loigiaihay exercises based on ' Câu ' or 'Bài '

### Community 42 - "Tiếng Việt Migration"
Cohesion: 0.83
Nodes (3): extract(), fold(), slug()

### Community 43 - "Loigiaihay Single Spider"
Cohesion: 0.83
Nodes (3): create_extraction(), create_grounding(), scrape_single()

## Knowledge Gaps
- **27 isolated node(s):** `eval_questions`, `run_api.sh script`, `PYTHONPATH`, `run_pipeline.sh script`, `backup_rag.sh script` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RAGOrchestrator` connect `RAG Edu Retrieval Core` to `rag_edu FastAPI Service & DB Init`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Why does `old/ historical docs index` connect `Structured Retrieval Pipeline (design)` to `Multi-Subject Master Plan`, `Data Sources & Crawl Strategy`, `Evaluation Strategy & Benchmark`, `LLM Backends & Migration Scripts`, `Ingest Pipeline & Walkthrough`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `RAGOrchestrator` (e.g. with `ChatRequest` and `ChatResponse`) actually correct?**
  _`RAGOrchestrator` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `QueryClassifier` (e.g. with `ChatRequest` and `ChatResponse`) actually correct?**
  _`QueryClassifier` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `GraphRetriever` (e.g. with `QueryClassifier` and `QueryContext`) actually correct?**
  _`GraphRetriever` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `RetrievedItem` (e.g. with `QueryClassifier` and `QueryContext`) actually correct?**
  _`RetrievedItem` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `eval_questions`, `Scrapy Crawler cho loigiaihay.com - Lớp 1-5 Tiếng Việt =========================`, `Extract metadata từ URL pattern của loigiaihay.          Examples:       /bai-82` to the rest of the system?**
  _91 weakly-connected nodes found - possible documentation gaps or missing edges._