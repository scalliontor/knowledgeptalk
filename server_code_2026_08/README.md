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
