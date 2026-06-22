# Knowledge PTalk — Canonical Project State (2026-06-22)

> **Đây là source-of-truth của thread refactor.** Mọi subagent/PR phải đọc file này trước khi sửa code.
> Cập nhật khi baseline thay đổi (kèm run-id backtest). Không sửa số liệu mà không có report tương ứng trong `reports/backtest/`.

## North star

> Knowledge PTalk là lớp tri thức biến loa AI thành **bạn đồng hành học bài**, bám đúng **bài/trang SGK đang mở** để **giảng · đọc · luyện**, **sạch nguồn**, **độ trễ thấp**, và **từ chối khi ngoài bài** thay vì đoán.

## Baseline đo thực (full sweep 2026-06-17, run trên MERGED candidate :8890)

- Corpus: **65 quyển / 1852 bài / 6 môn** (Toán, KHTN, Sử, Địa, GDCD, Văn), lớp 4–9, CTST + KNTT + CD.
- Full sweep: **81 (subject,grade,book,tap) × 500 câu ≈ 40.000 case** (32.738 lesson-case + ~7k guard).
- **Anchor (đường production/anchored): 97.0%**
- **Guard: 98.1%**
- **Real source cruft: 0**
- **Runtime errors: 0 / ~40k**
- **Latency P95: 193–368 ms** (serve path Gemma-free)
- Volume separation (chống trùng tập): toan 8 KNTT **t1 = 96.4% / t2 = 98.8%** ✅
- Anchored theo môn: gdcd 99.8 · ngu_van 99.1 · dia_li 97.7 · khtn 96.8 · toan 95.8 · **lich_su 95.5**.
- Artifact: `reports/backtest/2026-06-17_full-sweep/` (81 JSON + log).

## ⚠️ Đính chính quan trọng (đừng lặp lại lỗi cũ)

**"204 cruft" trong backtest = FALSE-POSITIVE** do danh sách CRUFT chứa keyword `"giáo viên"` — bắt nhầm **từ vựng hợp lệ** (GDCD/môn khác nói về thầy cô). Verify trực tiếp Neo4j trên **toàn bộ 1852 theory chunk**:

```
vietjack = 0 · xem lời giải = 0 · video giải = 0 · loigiaihay = 0 · "giáo viên" = 11 (hợp lệ)
```

→ **Rác nguồn THẬT = 0.** Goal "sạch nguồn" ĐẠT. Cần siết keyword test (`"giáo viên"` → `"Giáo viên VietJack"` / `"(Giáo viên"`), và **tách `cruft_real` khỏi `cruft_test_false_positive`** trong metric.

## Fix đã áp (2026-06-22, data-only, live trên edu Neo4j)

**En-dash + suffix norm fix** (`/tmp/fix_norm.py`, APPLIED 29 bài): `work_name_norm` lưu en-dash "–" còn runtime `_fold` ra hyphen "-" → lệch → `none`. Re-backfill `work_name_norm = runtime_fold(work_name)` cho 25 bài en-dash (Toán/KHTN/Sử/Địa) + dọn 4 work_name suffix "- Kết nối tri thức…" (3 lich_su + 1 dia_li). Không đổi code; query_lesson_card đọc Neo4j live → hiệu lực ngay canary/merged/prod.
- Re-backtest chính thức: **toan 8 CTST t1 anchored 90.2→97.2%** (current_lesson 76.8→100, practice 79→100); **lich_su 6 KNTT anchored 93.0→95.1%** (name_query 88→95). Guard giữ 100%, 0 regression. Áp toàn corpus (mọi tên có "–").
- → Gap "Toán tiểu học / anchoring lệch" coi như **đã xử lý** (Toán TH vốn 100% trên current_lesson; toan8CTSTt1 nay 97.2%). Còn lại chủ yếu là content_only (refusal-by-design) + client context.

## Gap thật còn lại (theo mức ưu tiên)

1. **Toán tiểu học lớp 4–6 anchoring 82–86%** (toan4 CTST 82.0 · toan5 CTST 83.8 · toan6 KNTT 86.3 · toan8 CD t1 89.9) — nghi tên bài dài/định dạng lạ làm lệch. **Điểm yếu thật số 1.**
2. **Lịch sử 95.5%** — nghi `work_name_norm` lệch ở vài bài (số La Mã, gạch ngang, năm).
3. **Chưa promote prod :8888** — prod vẫn chạy code cũ (chưa có companion). Bản merged (giữ moderation) đã test 8890 đạt chuẩn, sẵn ở server `/tmp/rag_server_merged.py`.
4. **Client gửi `{}`** — anchor 97% chỉ đạt khi app gửi `current_lesson`/`trang`+`tap`. `rag_client` hiện gửi rỗng → cần contract + integration.

> `content_only` 25–47% KHÔNG phải gap: đa số là **từ chối an toàn** (không có neo → không đoán bừa), production gần như không gặp vì luôn có `current_lesson`.

## ⚠️ Thực tế hạ tầng (ràng buộc mọi refactor)

> Chi tiết topology + giao diện (verified docker ps/ss/nginx 2026-06-22): [architecture/infrastructure-and-interfaces](../architecture/infrastructure-and-interfaces.md). Tóm tắt: RAG :8888 là **microservice nội bộ** (KHÔNG expose nginx); client = app thoại ptalk_v1/v2/eldercare (:8001/2/3) + Dashboard (moderation). Prod đã promote (companion+en-dash+moderation live).

- **Runtime KHÔNG ở repo này.** Production = single-file `rag_server.py` (:8888) + `rag_server_canary.py` (:8889) trên **server** `/home/namnx/Ptalk_project/CloudPTalk`. Repo local = scripts (`rag_edu/`) + docs + graphify-out (phần lớn mirror/dead-code).
- Target `/packages/*` trong plan = **đề xuất tổ chức**; muốn áp vào runtime phải có migration plan riêng (Agent 2), không refactor mù single-file thành package rồi tưởng đã deploy.
- Neo4j edu: `bolt://localhost:7688` (server). Gemma local :8080 (chỉ dùng lúc build/ingest, KHÔNG ở serve path).
- Launch service = script file + nohup (BGE ~30s). Restart prod = ESP32 downtime ngắn → low-traffic + ask trước.
- SSH server flaky (fail2ban khi nhiều kết nối nhanh) → lệnh đơn, transfer rời launch.

## Quyết định kiến trúc: THIN SERVER + LÕI Ở REPO (2026-06-22)

**Research `rag_server.py` (1271 dòng, canary):** KHÔNG phải thin API caller — nó CHÍNH LÀ RAG (10× Neo4j driver, 16 Qdrant ref, 3 Postgres, 7 BGE.encode, 12 Cypher MATCH, toàn bộ logic inline, 0 import package; chỉ 1 call Gemma và KHÔNG ở serve path).

**Hướng đi (chốt):** ĐẢO monolith → rút **~75% là lõi logic** về repo này thành package có test + backtest; server thành **vỏ mỏng** import package.
- `packages/knowledge_core` (pure, ~380 dòng): fold/normalize, parse_structured_query, route_query_rule_based, _classify_intent (inject model), canonicalize/override subject, detect_learning_mode, sanitize_chunk_text, _is_recite, lines_payload.
- `packages/retrieval` (~600 dòng, inject driver/client): query_lesson_card + content-vector, query_structured_exact, query_concept_exact, query_neo4j_*, query_qdrant, recite_from_*. Cypher + scoring là IP; driver/Qdrant/BGE là dependency truyền vào.
- `packages/rag_router`: orchestrator `retrieve()` (~150 dòng).
- Server `rag_server.py` THIN (~150 dòng): FastAPI endpoints + init model/driver/client + wiring → `from rag_router import retrieve`.
- **Deploy**: sync package dir + thin server lên server rồi restart (thay vì SSH-sửa monolith). Cần script sync + PYTHONPATH/pip -e trên server.

**Điều kiện thực thi (Agent 2, có gate):** characterization-test từng hàm (output trước==sau) + backtest-gated (không tụt anchor 97/guard 98/real cruft 0). KHÔNG refactor mù. Lần rút lõi đầu tiên = pure-refactor-no-behavior-change, deploy + full sweep PASS mới merge.

## Invariant không được phá (mọi PR)

| Invariant | Không được làm hỏng |
|---|---|
| Structured-first routing | `current_lesson` → tên bài → trang+tập → content-vector |
| Scope chặt | môn + lớp + bộ sách + **tập** |
| Không trùng tập 1/2 | page reset phải xử lý theo `tap_no` |
| Gemma-free serve path | không đưa LLM vào đường latency-critical |
| Sạch nguồn | không leak vietjack/lời giải/cô-giáo-VietJack |
| Refuse ngoài bài | không hallucinate khi ngoài scope |
| Backtest là gate | không merge nếu không có report mới + diff |

## Release gate (promote :8888)

```
[ ] Full sweep mới PASS (report trong reports/backtest/<run>/)
[ ] Anchor ≥ 97.0 · Guard ≥ 98.1 · real cruft = 0 · error = 0 · P95 trong ngưỡng
[ ] Toán 4–6 tăng hoặc không tụt · Lịch sử tăng hoặc không tụt
[ ] Volume collision = 0 critical
[ ] Canary 8889/8890 smoke pass
[ ] Client context contract confirmed (không còn {})
[ ] Backup Neo4j verified · Git SHA ghi trong release note
[ ] Rollback command documented
[ ] Restart prod 8888 → post-release smoke pass
```

## Thứ tự thực thi (anh chốt)

**Backtest Engineer → Repo Cartographer → (rồi mới) Architecture Refactor → Fix weak slices → Client integration → Promote.**
Lý do: hệ thống đang có metric tốt; rủi ro lớn nhất là refactor làm tụt anchor/guard mà không có backtest diff để bắt.
