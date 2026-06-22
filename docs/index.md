# Knowledge PTalk — Index tài liệu ("đọc từ đâu")

> Cổng vào tài liệu cho **người mới**. Mục tiêu: hiểu hệ thống trong ~30 phút.
> RAG live chạy ở **server** (single-file `rag_server.py`), KHÔNG phải repo này. Xem [operations/](operations/).

## 0. Đọc đầu tiên (north star + sự thật hiện tại)

| # | File | Vì sao đọc |
|---|---|---|
| 1 | [**project_state/2026-06-22-canonical.md**](project_state/2026-06-22-canonical.md) ⭐ | **Source-of-truth.** North star, baseline đo thực, gap còn lại, invariant, release gate, thực tế hạ tầng. Mọi PR đọc trước. |
| 2 | [**product/north-star.md**](product/north-star.md) | Vì sao PTalk = bạn đồng hành theo bài, không phải Q&A mở. |
| 3 | [**product/lesson-card-model.md**](product/lesson-card-model.md) | Mô hình dữ liệu sản phẩm: node `:Lesson` + 4 thành phần + companion flow. |

## 1. Sơ đồ đọc cho người mới (30 phút)

```
[5']  product/north-star.md            → "PTalk là gì, tại sao"
[5']  product/goals-and-anti-goals.md  → "LÀ gì / KHÔNG phải gì" (đặt kỳ vọng đúng)
[8']  product/lesson-card-model.md     → "1 bài học trông như thế nào trong graph"
[5']  product/user-journeys.md         → "bé hỏi → hệ thống làm gì" (4 hành trình thật)
[5']  project_state/2026-06-22-canonical.md → "đang ở đâu: số liệu, gap, invariant"
[2']  operations/canary-prod-ports.md  → "8888/8889/8890 là gì, restart sao"
```
Sau 30': mở [design/kg-schema-v3.md](design/kg-schema-v3.md) để đào sâu schema, hoặc [operations/release-checklist.md](operations/release-checklist.md) nếu sắp promote.

## 2. Bản đồ thư mục `docs/`

### product/ — Sản phẩm là gì & cho ai (đọc trước nếu mới)
- [north-star.md](product/north-star.md) — mục tiêu tối thượng + lý do thiết kế companion.
- [goals-and-anti-goals.md](product/goals-and-anti-goals.md) — bảng **LÀ vs KHÔNG phải**.
- [lesson-card-model.md](product/lesson-card-model.md) — node `:Lesson` + 4 thành phần (giảng / đọc thuộc / luyện có dẫn dắt / gợi mở) + companion flow.
- [user-journeys.md](product/user-journeys.md) — 4 hành trình thật (giảng Văn, đọc thuộc, luyện Toán, từ chối lạc đề).

### project_state/ — Ta đang ở đâu (source-of-truth)
- [2026-06-22-canonical.md](project_state/2026-06-22-canonical.md) ⭐ — baseline, gap, invariant, release gate.
- [../docs/00_STATE.md](00_STATE.md) — snapshot trạng thái services/data (bổ trợ).

### design/ — Kiến trúc & quyết định *(agent khác phụ trách architecture docs)*
- [kg-schema-v3.md](design/kg-schema-v3.md) — schema 3 lớp (Document/Concept/Structure), Toán PREREQ, Văn Work/Section/Variant, fix F1, Cypher + migration.
- [dashboard-kg-viewer-v2.md](design/dashboard-kg-viewer-v2.md) — guide hiển thị KG trên Dashboard.

### data/ — Dữ liệu & ingest *(agent khác phụ trách)*
- Corpus 65 quyển / 1852 bài / 6 môn (Toán, KHTN, Sử, Địa, GDCD, Văn), lớp 4–9, CTST + KNTT + CD. Chi tiết build/ingest xem audit + pilot.
- [audit/rag_subject_audit_2026_06_14.md](audit/rag_subject_audit_2026_06_14.md) — audit nền theo môn.

### backtest/ & evaluation/ — Đo lường *(agent khác phụ trách backtest docs)*
- Artifact full-sweep: `reports/backtest/2026-06-17_full-sweep/` (81 JSON: by_dimension + sample_fails + latency).
- [evaluation/](evaluation/) — kết quả test theo môn + voice gate (lịch sử).
- [pilot/RESULTS.md](pilot/RESULTS.md) · [pilot/MULTISUBJECT_SCALE_2026_06_14.md](pilot/MULTISUBJECT_SCALE_2026_06_14.md) — kết quả pilot companion.

### research/ — Bằng chứng nền
- [research/2026-06-03_graph-rag-companion.md](research/2026-06-03_graph-rag-companion.md) — deep research, 17 patterns confirmed.

### operations/ — Vận hành & phát hành *(file mới — xem mục 3)*
- [canary-prod-ports.md](operations/canary-prod-ports.md) · [release-checklist.md](operations/release-checklist.md) · [rollback.md](operations/rollback.md) · [backup-restore.md](operations/backup-restore.md)
- Vận hành chi tiết (debug playbook, start service): [RUNBOOK.md](RUNBOOK.md).

### client/ — Hợp đồng client ↔ RAG *(agent khác phụ trách)*
- Contract `current_lesson`/`trang`+`tap` (xem [product/lesson-card-model.md](product/lesson-card-model.md) §companion flow + canonical §gap #4).

## 3. operations/ — Phát hành an toàn (mới)
| File | Khi nào cần |
|---|---|
| [operations/canary-prod-ports.md](operations/canary-prod-ports.md) | Hiểu 8888 (prod) / 8889 (canary) / 8890 (merged candidate), cách launch. |
| [operations/release-checklist.md](operations/release-checklist.md) | Trước khi promote lên prod :8888. |
| [operations/rollback.md](operations/rollback.md) | Khi release hỏng — quay về `.bak`. |
| [operations/backup-restore.md](operations/backup-restore.md) | Backup/restore Neo4j edu (dump → Drive). |

## 4. Nguyên tắc xuyên suốt (nhắc nhanh)
- Chunk **doc-level** · **structured-first** (`current_lesson` → tên bài → trang+tập → content-vector) · scope chặt môn+lớp+bộ sách+**tập**.
- **Gemma-free serve path** (regex/embedding đủ + nhanh; LLM chỉ ở build/compose).
- **Sạch nguồn** (không leak vietjack/lời giải) · **từ chối khi ngoài bài** thay vì đoán.
- **Backtest là gate** — không merge nếu không có report mới + diff.

---
Liên quan: [project_state/2026-06-22-canonical.md](project_state/2026-06-22-canonical.md) · [README.md](README.md) · [RUNBOOK.md](RUNBOOK.md)
