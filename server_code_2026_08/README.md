# Code server (bản cứu từ backup) — 2026-08

> ⚠️ **Vì sao có thư mục này:** `rag_server_canary8892.py` trên server chứa toàn bộ công việc
> T1 (subject-gate môn Sử) + T2 (tầng thẻ sự kiện `:HistEvent`) nhưng **KHÔNG được git theo dõi**
> ở repo `AvisCTS-Lab/CloudPTalk`, và **đã biến mất khỏi server** (phát hiện 2026-09-02).
> Bản ở đây được trích từ gói backup `cloudptalk_code_2026-08-11.tar.gz` (mtime gốc 2026-08-02 16:30).

## File

| File | Ghi chú |
|---|---|
| `rag_server_canary8892.py` | 2035 dòng, đủ T1+T2, `py_compile` OK. **ĐÃ SANITIZE** (xem dưới). |
| `launch_canary8892.sh` | script khởi động canary `:8893` |

## ĐÃ SANITIZE — phải set env trước khi chạy

Bản gốc hardcode secret; bản này đọc từ biến môi trường:

```bash
export LLM_API_KEY=...        # key Gemma :8080
export EDU_NEO4J_USER=neo4j
export EDU_NEO4J_PASS=...     # mật khẩu Neo4j edu
export PG_PASS=...            # postgres rag_edu (nếu dùng)
export RAG_PORT=8893 WIKI_ENABLED=1 HISTEVENT_ENABLED=1
python3 -u rag_server_canary8892.py
```

Giá trị thật tra trong `server.txt` / `.env` trên server — **KHÔNG chép vào repo**.
Bản gốc chưa sanitize nằm trong gói backup trên Google Drive (thư mục riêng tư).

## Nội dung T1 + T2 trong file

- **T1 subject-gate**: mở rộng `LICHSU_FORCE_KEYWORDS` + few-shot trong `_NORM_SYS` ép câu sự kiện → `subject="lich_su"`.
- **T2 fact-node**: `query_hist_event()` đặt TRƯỚC nhánh wiki/B2 — alias-longest qua `:HistAlias`
  → lọc năm → gộp trùng-lặp-dữ-liệu → sibling-guard (chỉ hỏi lại khi khác NĂM) → dựng "THẺ SỰ KIỆN".
- **Cầu ngữ-âm STT**: `_spoken_years()` (năm đọc thành chữ), `_hist_is_factoid()` khớp cả bản bỏ dấu.
- **`_hfold()`**: chuẩn hoá GIỐNG lúc ingest alias (khác `_fold` của server vốn giữ dấu gạch nối).
- Kill-switch: `HISTEVENT_ENABLED=0`.

Đo được: battery 40 câu **30/40** (prod chưa có T2: 18/40); test theo từng bài L7–L12 **83%**.

## Việc còn phải làm

- [ ] Commit bản này (hoặc bản có secret, tuỳ chính sách) vào chính repo `AvisCTS-Lab/CloudPTalk` —
      hiện `rag_server_canary8892.py` **chưa từng lên GitHub**.
- [ ] Trên repo CloudPTalk còn **37 file untracked + `watchdog.sh` sửa chưa commit**, và
      **2 commit local chưa push** (`b660243`, `0db9c26`).

---

## 2026-09-02 — `rag_server_next.py`: bản GHÉP an toàn để deploy (CHƯA deploy)

**Vì sao không deploy thẳng canary:** diff prod (26/07, 1791 dòng) vs canary (02/08, 2035 dòng) = 7 khối.
Prod đã đi thêm **1 khối 16 dòng** sau khi canary fork: secret đọc từ `.env` qua `dotenv`
(`RAG_LLM_API_KEY`, `RAG_LLM_API_URL`, `RAG_LLM_MODEL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`).
Canary (và cả bản sanitize ở trên) dùng **tên biến khác, không đọc `.env`** → deploy thẳng = mật khẩu rỗng, server chết.

**`rag_server_next.py` = canary + khối `.env` của prod + vá rủi ro #2.** Diff so với prod: **0 dòng prod bị mất, 261 dòng thêm** (2052 dòng, `py_compile` OK, không hardcode secret).

### Bảng rủi ro khi deploy
| # | Thay đổi | Rủi ro | Xử lý |
|---|---|---|---|
| 1 | Khối secret | canary hardcode ≠ prod `.env` → **server chết** | ✅ lấy khối của prod |
| 2 | `LICHSU_FORCE_KEYWORDS` mở rộng ("phong trào", "chiến dịch", "vua nào"…) | hàm override **đè cả khi Gemma đã bảo ngu_van** → "phong trào Thơ mới" bị đẩy sang kho Sử | ✅ tách `LICHSU_T1_KEYWORDS`, chỉ áp khi `subject in (None, lich_su)` |
| 3–5 | 3 dòng thêm vào `_NORM_SYS` (luật subject Sử, GIỮ NGUYÊN tên bài, 3 few-shot) | đổi normalizer toàn cục; mới test mẫu nhỏ | ⏳ chạy đủ regression Văn trước khi deploy |
| 6 | 220 dòng hàm T2 | không chạy nếu không gọi | — |
| 7 | Hook T2 trước B2 | gate 3 lớp (`kind!=recite` ∧ subject Sử ∧ factoid) | kill-switch `HISTEVENT_ENABLED=0` |

**Không phải rủi ro:** script test không được deploy; 608 thẻ đã nằm trong Neo4j mà battery prod vẫn 18/40 y hệt → prod không nhìn thấy dữ liệu mới.

### Quy trình deploy (gate từng bước, dừng nếu bước nào đỏ)
1. Bật canary `:8893` bằng `rag_server_next.py` (cần ~2,7 GB VRAM — **xin trước**).
2. Regression trên **cả prod `:8888` lẫn canary `:8893`**, so từng cặp:
   - `regression/test_van_recite.py <port> cap2` (570 bài) và `cap3` (425 bài) — **Văn không được tụt**
   - `regression/van_collision_probe.py <port>` — câu Văn chứa từ khoá T1, kỳ vọng **0** bị hút sang Sử
   - `../hist_build_2026_07/run_battery.py <port>` — Sử, kỳ vọng ≥30/40 (prod 18/40)
   - `../hist_build_2026_07/test_stt_style.py`, `test_t2.py` — STT + 12 ca chi tiết
3. Chỉ khi Văn ≥ prod và collision = 0: `cp rag_server.py rag_server.py.bak_pre_t2_<ngày>` → `cp rag_server_next.py rag_server.py` → `py_compile` → restart screen `ptalk_rag` (**xin trước**, ~15–30 s).
4. Đo lại battery Sử trên prod ngay sau restart.
5. Rollback 1 lệnh: `cp rag_server.py.bak_pre_t2_<ngày> rag_server.py && bash deploy_rag_prod.sh`; tắt mềm T2: `HISTEVENT_ENABLED=0`.

Còn treo trước deploy: nạp ~530 thẻ L4–L7 đã verify vào Neo4j (data-only) và verify nốt 3 chunk L4.
