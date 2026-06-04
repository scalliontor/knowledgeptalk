# docs/ — Tri thức RAG cho PTalk

> Knowledge base về **cách xây RAG graph document-level** cho chatbot đồng hành học tập PTalk.
> Repo này là **nguồn dữ liệu/tri thức**; RAG live chạy ở `CloudPTalk/rag_server.py` trên server (xem [../ARCHITECTURE.md](../ARCHITECTURE.md)).

## Mục lục

### design/ — Quyết định kiến trúc (actionable)
- [**kg-schema-v3.md**](design/kg-schema-v3.md) ⭐ — Schema v3 Toán & Văn + companion layer. **Quyết định chính**: 3-lớp tách biệt (Document/Concept/Structure), Toán có PREREQ DAG, Văn dùng Work/Section/Variant không prereq, fix F1 collision + work_name. Kèm migration plan.
- [**dashboard-kg-viewer-v2.md**](design/dashboard-kg-viewer-v2.md) ⭐ — Guide tự sửa Dashboard `/kg-browse` + `/kg-analytics` để hiển thị lớp Concept/Tác phẩm/Section/Variant mới (schema v3). Cypher từng level per-subject + files cần sửa + checklist.
- [**../docs/viz/kg-showcase.html**](viz/kg-showcase.html) — trang showcase nhanh (sunburst + heatmap, self-contained, mở browser trực tiếp).

### evaluation/ — Kết quả test (5 môn)
- Toán 90.1% · Văn 96.4% · Xã hội ~95% · KHTN 96.9% · Tiếng Việt 99%(template). Natural-language eval: structured 75-100% robust, concept ~33% (paraphrase). Latency 8-40ms. Leak=0.

### research/ — Evidence base (cited)
- [**2026-06-03_graph-rag-companion.md**](research/2026-06-03_graph-rag-companion.md) ⭐ — Deep research 107 agents, 17 patterns confirmed / 8 refuted, 25 primary sources. Concept-decoupled-from-chunk, explicit COVERS edge, math 3-layer + curriculum-seeded prereq, literature recitation separation, no-quiz implicit mastery.

### Tài liệu gốc (April 2026 — historical)
- [1_khao_sat_nguon.md](../1_khao_sat_nguon.md) — survey nguồn crawl
- [7_khao_sat_dac_thu_tung_mon.md](../7_khao_sat_dac_thu_tung_mon.md) — đặc thù từng môn (loigiaihay)
- [8_master_plan.md](../8_master_plan.md) — 5-phase plan multi-subject
- [rag_edu/DATA_SOURCES.md](../rag_edu/DATA_SOURCES.md) — catalog nguồn dữ liệu theo môn

## Cách dùng

1. Cần **quyết định schema** → đọc `design/kg-schema-v3.md`.
2. Cần **bằng chứng/lý do** đằng sau quyết định → `research/2026-06-03_graph-rag-companion.md`.
3. Cần **state runtime hiện tại** (ports, data counts, services) → memory bank `session_2026_06_01_complete` + SSH verify.

## Nguyên tắc xuyên suốt (đừng quên)

- Chunk **document-level** — granularity qua metadata + edge, KHÔNG split nhỏ.
- **Structured-first** — Cypher exact (grade+bộ sách+bài) trước, vector fallback sau.
- **KHÔNG model mới** — Neo4j + BGE-m3 + LLM router sẵn có.
- PTalk = **bạn đồng hành học 1 bài cụ thể**, không phải Q&A mở.
- Concept = **node riêng + explicit edge**, không nhúng property.
