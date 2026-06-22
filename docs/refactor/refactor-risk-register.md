# Refactor Risk Register — Knowledge PTalk

> Lập bởi Repo Cartographer (2026-06-22). Đi kèm `docs/architecture/current-code-map.md` + `module-ownership.md`.
> Phạm vi: rủi ro khi refactor repo này. **Mô tả + cảnh báo, KHÔNG đề xuất xoá file.** Gate = `docs/project_state/2026-06-22-canonical.md` §Release gate.
> Thang mức: **CAO** (có thể tụt anchor/guard prod hoặc hỏng DB) · **TRUNG** (lệch ngầm / nợ kỹ thuật) · **THẤP** (nhiễu).

## R1 — Mismatch repo ↔ server (runtime không nằm trong repo) — **CAO**
- Production = single-file `rag_server.py`/`rag_server_canary.py` trên SERVER; repo CHỈ có builder + backtest + patch-diff. Refactor "code trong repo" KHÔNG tự động đổi runtime.
- **Bẫy:** package hoá `/packages/*` từ script repo rồi tưởng đã deploy → runtime vẫn là single-file cũ; backtest lệch kỳ vọng.
- **Giảm thiểu:** mọi PR refactor ghi rõ "phạm vi = repo (build/eval), KHÔNG đụng runtime". Áp vào runtime cần **migration plan riêng (Agent 2)**: copy file server vào repo có version → refactor → backtest 8889/8890 → promote 8888. Không refactor mù.

## R2 — Single-file `rag_server.py` không version trong repo — **CAO**
- Không có bản tham chiếu của file server trong repo → không diff được, không test unit, không biết patch script còn khớp.
- **Giảm thiểu:** bước 0 của bất kỳ refactor runtime = **mang `rag_server*.py` vào repo (read-only snapshot, có SHA)** rồi mới chia module. Trước đó: cấm sửa logic anchor "từ trí nhớ".

## R3 — Patch script `str.replace` vào file server — **CAO**
- `patch_tc_canary.py`, `patch_tc2_concept_match.py` ghi đè `rag_server_canary.py` bằng `assert old in src` + `replace`. Nếu file server đã đổi (drift), `assert` fail hoặc tệ hơn replace nhầm vùng.
- Một phần logic anchor (grade-propagation, Tier-A concept-exact) **chỉ tồn tại dạng patch** trong repo, không phải mã nguồn liền mạch.
- **Giảm thiểu:** coi patch script là **migration một chiều đã tiêu thụ**; sau khi snapshot file server (R2), gấp các patch vào source chính, ngừng dùng `str.replace`. Luôn giữ `.bak` (script đã có) + verify `py_compile` (đã có) trước khi tin.

## R4 — Script ghi Neo4j production (:7688) — **TRUNG-CAO**
- `build_book_generic.py`, `backfill_*`, `fix_concept_norm.py`, `v_a_work_name.py`, `t_b2_fine_concepts.py`, `tv_migrate.py`, các legacy import → MERGE/SET vào DB thật. (Không thấy `DETACH DELETE`/`DROP` → đỡ rủi ro xoá, nhưng vẫn mutate.)
- **Bẫy:** refactor "gom util" có thể vô tình đổi hành vi normalize (`fold`/`wslug`) → `work_name_norm`/`name_norm` khác → lệch anchor (đặc biệt Lịch sử 95.5%, gap thật #2).
- **Giảm thiểu:** trước khi gom `fold()` (15 bản) thành 1 module, viết **golden test** so output từng bản hiện tại → bản gộp phải bit-identical trên tập mẫu. Mọi run builder cần **backup Neo4j** (release gate) + guard `EDU_NEO4J_PW` env, chặn chạy nhầm máy local.

## R5 — venv + data nằm vật lý trong repo — **TRUNG**
- `rag_edu/venv/` (python3.8) và `rag_edu/data/` nằm trong cây repo (đã gitignore, 0 file tracked). Tool refactor / graphify / lint quét toàn cây dễ ăn nhầm venv → kết quả nhiễu, chậm, false-positive.
- python3.8 trong venv cũ ≠ runtime server (cần xác nhận phiên bản server).
- **Giảm thiểu:** giữ gitignore; khi chạy tool dùng path scope hẹp (`rag_edu/src`, `rag_edu/scripts`), loại `venv/`, `data/`, `__pycache__/`. Không tin python local = python server.

## R6 — Hardcoded endpoints/secret-path rải rác — **TRUNG**
- `bolt://localhost:7688` (19 script), `localhost:8080` Gemma (6 script), path `/home/namnx/...`, env `EDU_NEO4J_PW`/`GEMMA_KEY`/`GKEY`. Gom thành config là mục tiêu refactor, nhưng đổi nơi đọc env có thể vỡ runtime build.
- **Giảm thiểu:** tạo `packages/config` đọc đúng env hiện hành; **không đổi tên env** đang dùng trên server; migrate từng script kèm chạy thử trên canary trước. Không commit secret (chỉ tham chiếu `.env`/`server.txt`).

## R7 — Gemma trong build/eval, phải tránh lọt vào serve path — **CAO (nếu vi phạm)**
- `build_book_generic.py`, `backtest_book.py`, `eval_*`, `exp_vector_rerank.py` gọi Gemma. Invariant: **serve path Gemma-free**.
- **Bẫy:** refactor "gom LLM client" rồi vô tình import vào module dùng chung serve path → thêm latency/LLM vào đường thoại.
- **Giảm thiểu:** đặt `llm_client` ở tầng **build/ingest only**, cấm import từ module serving. Backtest P95 (193–368ms) là canary phát hiện vi phạm.

## R8 — Thiếu test tự động — **CAO**
- Không có unit/integration test cho normalize/anchor/router trong repo; gate duy nhất là full backtest (đắt, cần server + token + ~40k case).
- **Bẫy:** refactor nhỏ tụt anchor/guard mà không bắt được trước promote (đúng lý do canonical xếp Cartographer trước Refactor).
- **Giảm thiểu:** trước refactor, dựng **bộ test rẻ**: (a) golden test cho `fold/wslug/sanitize`; (b) replay offline trên `reports/backtest/2026-06-17_full-sweep/*.json` (`sample_fails`) không cần server; (c) smoke `/retrieve` canary. Full sweep chỉ chạy ở cổng release.

## R9 — Hai thế hệ code dễ nhầm (DEAD `src/` trông như live) — **TRUNG**
- `rag_edu/src/` (FastAPI Postgres+Qdrant) còn nguyên, import sạch, graphify hiện node `FastAPI/retrieve_endpoint` → dễ tưởng là runtime.
- **Giảm thiểu:** đánh dấu DEAD ngay trong code map (đã làm); refactor KHÔNG bắt đầu từ `src/`. Quyết định archive (không xoá) để ở PR riêng có owner duyệt.

## R10 — Backtest gate phụ thuộc server đang chạy + tạo tải prod — **TRUNG**
- `backtest_book.py`/`megatest.py`/`bench_fullflow.py` gọi `/retrieve` :8889/:8888. Chạy lúc giờ cao điểm = đụng ESP32 thật; SSH flaky (fail2ban).
- **Giảm thiểu:** chạy backtest giờ thấp tải, ưu tiên canary :8889/:8890, ask trước khi đụng :8888. Ưu tiên phân tích offline từ artifact JSON khi đủ.

## R11 — Drift docs ↔ thực tế — **THẤP-TRUNG**
- `graphify-out` phần lớn mirror/dead; memory MEMORY.md có mục cũ ("204 cruft" đã đính chính = false-positive). Refactor theo doc cũ → quyết định sai.
- **Giảm thiểu:** chỉ tin `docs/project_state/2026-06-22-canonical.md` cho số liệu; cập nhật graphify (`graphify update .`) sau khi đổi code; không lặp lại "204 cruft".

## Thứ tự an toàn (khớp canonical §Thứ tự thực thi)
1. (R2) Snapshot `rag_server*.py` vào repo có SHA — **trước mọi refactor runtime**.
2. (R8) Dựng test rẻ + replay offline artifact.
3. (R4/R6) Golden test cho `fold/normalize` → mới gom util.
4. (R7) Tách `llm_client` build-only, cấm import serve.
5. Refactor theo lát mỏng → backtest diff canary mỗi bước → promote theo §Release gate.

> **Nguyên tắc chốt:** muốn áp `/packages/*` vào runtime = migration plan riêng (Agent 2). Repo refactor (build/eval) và runtime refactor (server single-file) là HAI việc khác nhau; không trộn trong một PR.
