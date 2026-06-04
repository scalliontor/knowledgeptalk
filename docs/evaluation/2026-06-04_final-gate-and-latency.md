# Final pre-production gate — accuracy + full-flow latency

> **Ngày**: 2026-06-04 · Siêu test toàn bộ tri thức 5 môn K-9 + benchmark full luồng RAG trước khi merge code mới vào production.

## A. Accuracy scorecard (5 môn, Cypher-emulated = logic retrieval thật)

| Môn | theo_bài | theo_trang | concept/kiến thức | đặc thù | OVERALL | leak |
|---|---|---|---|---|---|---|
| **Toán** G1-9 | 100% | 98.8% | 80.7-80.9% | — | **90.1%** | 0 |
| **Văn** G6-9 | 100% | 96.0% | 100% (tác phẩm/section/nội dung) | variant 69.5% | **96.4%** | 0 |
| **Xã hội** G6-9 | 100% | — | 93-100% | — | **~95%** | 0 |
| **KHTN** G5-10 | 100% | 100% | 94.4% | vận dụng 93.2% | **96.9%** | 0 |
| **Tiếng Việt** G1-5 | 100% | 97.0% | 100% | — | **99%** | 0 |

**Natural-language gate (Gemma4 voice, 75 case)**: structured (bài/trang/tác phẩm) **93-100%** · concept **33-50%** (paraphrase) · **OVERALL 81.3%**. Cross-grade leak = **0** trên toàn bộ (~13.000 test case).

→ **Kết luận accuracy**: core companion (hỏi bài/trang/tác phẩm) ready cho production. Concept paraphrase là điểm yếu còn lại (cần routing thông minh + clarify-dialogue, không phải blocker).

## B. ⚠️ Full-flow latency benchmark (live HTTP `/retrieve`)

### Đo thực tế prod `:8888` (đang chạy production)
| Loại query | p50 | p95 | mean |
|---|---|---|---|
| structured (bài/trang) | **2755ms** | 3280ms | 2701ms |
| concept/explain | 2039ms | 2447ms | 2078ms |
| literature/recite | 2475ms | 2763ms | 2245ms |

→ **Prod = 2-3 GIÂY mọi query, VƯỢT budget 1-2s.** ❌

### Root cause (xác nhận bằng code diff)
- `rag_server.py` (prod): **KHÔNG có Tier A**. `retrieve()` gọi `route_query()` → `call_gemma()` (LLM ~2s) **cho MỌI query** trước khi retrieve.
- `rag_server_canary.py` (code mới): **CÓ Tier A** (`query_structured_exact` + `query_concept_exact`) return **TRƯỚC** Gemma router.

### Latency code MỚI (canary) — đo thành phần (canary HTTP chưa ổn định để bench trực tiếp)
| Thành phần (hot path) | Đo được |
|---|---|
| Tier A structured Cypher | p50 38ms / p95 48ms |
| Tier A concept Cypher | p50 8ms / p95 10ms |
| HTTP local overhead | ~5-15ms |
| **→ Full-flow structured/concept (90%+ query)** | **≈ 50ms** (KHÔNG gọi Gemma, KHÔNG BGE) |
| Vague/fallback tail (Gemma router) | ~2s (hiếm, như prod) |

→ **Code mới đưa case phổ biến 2.700ms → ~50ms (nhanh 50×), đạt budget thừa sức.**

## C. Kết luận gate + khuyến nghị merge

| Hạng mục | Trạng thái |
|---|---|
| Tri thức (data) 5 môn schema v3 | ✅ READY (Neo4j, leak=0) |
| Accuracy structured-first | ✅ READY (93-100% voice) |
| Accuracy concept paraphrase | ⚠️ 33-50% — cần routing+clarify (không block) |
| **Latency** | ❌ prod 2-3s · ✅ code mới ~50ms — **PHẢI merge canary code mới đạt budget** |

**Điều kiện merge vào production:**
1. ✅ Data đã sẵn (đã live trên Neo4j edu, dùng chung prod+canary).
2. ⛔ **Swap prod `:8888` ← canary code** (Tier A short-circuit) — đây là thứ mang latency từ 2.7s về ~50ms. **Bắt buộc** để đạt 1-2s.
3. Trước swap: cần canary chạy ổn định 1 lần để bench trực tiếp xác nhận (~50ms) — tốt nhất start trong session interactive trên server (`bash start_canary_tmux.sh`).
4. Sau swap: re-bench prod để xác nhận, theo dõi P95.

Harness: `bench_fullflow.py` (full luồng) · `latency_bench.py` (Cypher) · `eval_*.py` (accuracy).
