# docs/ — Tri thức & vận hành RAG PTalk

> Knowledge base + runbook cho RAG voice-tutor K-9 (graph document-level, structured-first companion).
> RAG live chạy ở **server** `CloudPTalk/rag_server.py` (xem [RUNBOOK](RUNBOOK.md)), KHÔNG phải repo này.

## Đọc theo thứ tự
1. [**00_STATE.md**](00_STATE.md) ⭐ — **ta đang ở đâu** (services, data 5 môn, code mới, việc còn lại).
2. [**RUNBOOK.md**](RUNBOOK.md) ⭐ — **vận hành/debug**: vị trí code server, cách start rag_server (script+nohup), Neo4j, debug playbook, an toàn.
3. [**design/kg-schema-v3.md**](design/kg-schema-v3.md) — quyết định schema (Concept tách Chunk, Toán PREREQ, Văn Work/Section/Variant, fix F1, Cypher + migration).

## design/ — Kiến trúc & quyết định
- [kg-schema-v3.md](design/kg-schema-v3.md) — schema v3 đầy đủ.
- [dashboard-kg-viewer-v2.md](design/dashboard-kg-viewer-v2.md) — guide tự sửa Dashboard `/kg-browse` + `/kg-analytics` hiển thị Concept/Tác phẩm (+ map nhãn, ẩn "vietjack").

## research/ — Bằng chứng
- [2026-06-03_graph-rag-companion.md](research/2026-06-03_graph-rag-companion.md) — deep research 107 agents, 17 patterns confirmed (concept-decoupled-from-chunk, structured-first, recite separation...).

## evaluation/ — Kết quả test (5 môn + voice gate)
- [2026-06-03_verify-arch-toan.md](evaluation/2026-06-03_verify-arch-toan.md) · [2026-06-04_verify-arch-van.md](evaluation/2026-06-04_verify-arch-van.md) · [2026-06-04_khtn-migration.md](evaluation/2026-06-04_khtn-migration.md) · [2026-06-04_xahoi-migration.md](evaluation/2026-06-04_xahoi-migration.md) · [2026-06-04_tieng-viet-migration.md](evaluation/2026-06-04_tieng-viet-migration.md)
- [2026-06-04_natural-language-eval.md](evaluation/2026-06-04_natural-language-eval.md) ⭐ — **Gemma4 voice gate** (template đánh giá cao quá; structured robust, concept yếu paraphrase).
- [2026-06-04_final-gate-and-latency.md](evaluation/2026-06-04_final-gate-and-latency.md) — scorecard + latency (prod 2.7s vs code mới ~50ms).

## viz/ — Showcase
- [viz/kg-showcase.html](viz/kg-showcase.html) — sunburst + heatmap self-contained (mở browser).

## Scripts (tái lập) — `../rag_edu/scripts/schema_v3_2026_06/`
Migration + eval + experiment (secret đã placeholder). Xem README trong thư mục đó.

## Nguyên tắc xuyên suốt
- Chunk **doc-level** · **structured-first** (Cypher exact bài/trang/concept trước, vector fallback) · **KHÔNG Gemma trong retrieve** (regex đủ + nhanh hơn) · Concept = node riêng + edge · fold **đ→d** rồi strip dấu · PTalk = bạn đồng hành học 1 bài cụ thể.
