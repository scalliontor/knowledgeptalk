# Schema v3 migration & eval scripts (2026-06)

Recipe tái lập migration 5 môn K-9 lên KG schema v3 + eval. Chạy trên server (Neo4j bolt :7688, Gemma :8080).

**Secrets đã thay placeholder** — set trước khi chạy:
- `CHANGEME_NEO4J_PASS` → Neo4j edu password (xem server.txt / .env)
- `CHANGEME_GEMMA_KEY` → Gemma API key

## Migration (theo thứ tự)
- `t_b2_fine_concepts.py` — Toán: extract fine concept từ lesson title + COVERS
- `backfill_g15.py` — Toán G1-5: lesson_no/trang_no từ title
- `fix_concept_norm.py` — fix name_norm đ→d (quan trọng)
- `v_a_work_name.py` + `backfill_worknorm.py` — Văn: work_name + work_name_norm
- `tv_migrate.py` — Tiếng Việt G1-5 (hybrid)
- `patch_tc_canary.py` + `patch_tc2_concept_match.py` — patch rag_server_canary (concept-exact + grade-fix)

## Eval
- `eval_toan_full.py` `eval_van_full.py` `eval_van_struct.py` `eval_tv.py` — per-subject template eval
- `eval_natural.py` — Gemma4 natural-language eval (gate chuẩn)
- `exp_vector_rerank.py` — A/B vector vs concept-exact
- `latency_bench.py` — latency Cypher retrieval
- `diag_weak.py` `verify_arch_toan.py` `pull_kg_tree.py` — diagnostic + viz data
