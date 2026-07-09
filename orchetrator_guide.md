# RAG server — Luồng đọc & chỗ ráp Wiki-orchestrator

> File: `rag_server.py` (~1601 dòng), chạy port **8888** (`RAG_PORT`).
> Client gọi: `shared/rag_client.py::fetch_knowledge(query, user_profile)` → POST `/retrieve`.
> Consumer chính: `workers/stt_worker.py` (nhồi context vào prompt LLM).
> Cập nhật: 2026-07 — thiết kế "Gemma làm orchestrator (SGK vs Wikipedia)".

---

## 1. Tổng quan luồng hiện tại (Gemma-anchor)

```
fetch_knowledge(query, profile)  ── POST /retrieve ──►  retrieve(req)
                                                            │
   ┌────────────────────────────────────────────────────────┘
   │ B0/B1  _normalize_query_gemma(q, prev_work)   ← GEMMA (call_gemma, temp 0.01)
   │        → {intent, work(gwork), author, subject, grade, bo_sach, bai_no, trang}
   │        prev_work = _SESSION_WORK[session_id]  (follow-up cùng phiên)
   │        (Gemma lỗi/tắt → KHÔNG regex fallback, gwork=None)
   │
   │ parsed = {lop:None, bo_sach:None, subject, bai_no, trang}   ← GRADE-FREE (bỏ lọc lớp)
   │ _SESSION_WORK[sid] = gwork    (nhớ cho lượt sau)
   │
   ├─ kind=="chat" & !gwork ───────────────► context="", need_rag=False   (không RAG)
   │
   ├─ B2  gwork có ► query_lesson_card(anchor_prof={current_lesson:gwork}, pa,
   │        gwork, allow_vec=False, force_recite, force_practice)
   │        │  lc có → return lc   (recite HOẶC giảng/companion tier=lesson_card)
   │        ├─ B2a recite_intent & !lc → recite_from_literature_text / _reading_text
   │        │        / _full_document (gwork) → nếu có → return
   │        └─ B2b → _not_found_response(gwork, None)   ("[KHÔNG TÌM THẤY]…")
   │
   ├─ B3  bai_no|trang có (không gwork) ► query_structured_exact → TIER A
   │
   └─ B4  còn lại (câu kiến thức/chủ đề) ► route_query_rule_based(q)
            → query_neo4j_knowledge_chunk  ("[DỮ LIỆU CẤU TRÚC - NEO4J KNOWLEDGE CHUNK]")
            → query_neo4j_lesson_guide      ("[DỮ LIỆU HƯỚNG DẪN - NEO4J LESSON GUIDE]")
            → fallback qdrant / neo4j vector
            → nếu rỗng: "Hệ thống RAG chưa tìm thấy dữ liệu nội bộ phù hợp…"
```

**Trả về:** `RetrieveResponse{ context: str, intent: dict, sources: list }`

---

## 2. Các hàm chính (bảng tra)

| Hàm | Dòng | Vai trò |
|---|---|---|
| `retrieve(req)` | ~1487 | **Điểm điều phối chính** (B0→B4). Sửa orchestrator ở ĐÂY |
| `_normalize_query_gemma(query, prev_work)` | ~1411 | Gọi Gemma → JSON {intent, work, subject…}. **Mở rộng schema router ở ĐÂY** |
| `_NORM_SYS` | ~1390 | **Prompt hệ thống** dạy Gemma normalize. **Sửa prompt router ở ĐÂY** |
| `call_gemma(sys, usr, max_tokens, timeout)` | ~155 | POST vLLM (`LLM_API_URL`, `LLM_MODEL`, temp 0.01) |
| `query_lesson_card(profile, parsed, query, allow_vec, force_recite, force_practice)` | ~1228 | Neo bài :Lesson → recite (nếu có recite_text) hoặc giảng/companion |
| `recite_from_literature_text / _reading_text / _full_document(title, …)` | 438/501/550 | Lấy NGUYÊN VĂN từ các loại node khác nhau |
| `lines_payload(title, lines, intent, source)` | ~145 | Đóng gói recite dạng **JSON** `full_recitation_lines` |
| `_not_found_response(work, grade)` | ~1463 | Trả marker `[KHÔNG TÌM THẤY]` (RAG thật thà) |
| `route_query_rule_based(q)` | ~288 | Suy intent bằng luật (tầng B4) |
| `parse_structured_query(query, user_profile)` | ~1012 | Trích lop/bo_sach/subject/trang (user_profile HIỆN KHÔNG dùng) |
| `_SESSION_WORK` (dict toàn cục) | — | `{session_id: gwork}` để follow-up giữ bài |

---

## 3. Định dạng `context` trả về (⚠️ KHÔNG đồng nhất — cần biết khi parse)

| Loại | Dấu hiệu trong context | Nguồn |
|---|---|---|
| **Recite JSON** | `{"type":"full_recitation_lines","title":…,"lines":[{text,pause_ms}]}` | `lines_payload` (vd bài **Lượm**) |
| **Recite text block** | `[ĐỌC THUỘC - NGUYÊN VĂN]\nNguồn chính:\n<tên>\n<TÊN>\n<thân bài>` | `recite_from_*` (vd **Nhớ rừng**) |
| **Giảng / companion** | lesson_card, `intent.query_type="companion"`, `tier="lesson_card"` | `query_lesson_card` |
| **Kiến thức** | `[DỮ LIỆU CẤU TRÚC - NEO4J KNOWLEDGE CHUNK]` / `[DỮ LIỆU HƯỚNG DẪN - NEO4J LESSON GUIDE]` / `[… VECTOR …]` | tầng B4 |
| **Không có (thật thà)** | `[KHÔNG TÌM THẤY] Kho tri thức hiện CHƯA có…` | `_not_found_response` |
| **Miss (B4 rỗng)** | `Hệ thống RAG chưa tìm thấy dữ liệu nội bộ…` | cuối `retrieve` |

**stt_worker dò MISS bằng marker:** `_RAG_MISS = (not ctx) or ("[KHÔNG TÌM THẤY]" in ctx) or ("chưa tìm thấy dữ liệu nội bộ" in ctx)`.
- HIT → nhồi `<KIẾN_THỨC_SGK_NỘI_BỘ>…context…</…>`
- MISS → nhồi `<KHÔNG_CÓ_TRONG_KHO_SGK>` (trả lời hiểu-biết-chung).

`intent.query_type` hay gặp: `recite_full_text`, `companion`, `explain`, `not_found`, `chat`, `A_structured`.

---

## 4. THIẾT KẾ: Gemma làm ORCHESTRATOR (SGK ↔ Wikipedia)

Ý tưởng: `_normalize_query_gemma` thành **ROUTER**. Nó phân loại NGUỒN (`sgk` / `wiki` / `realtime` / `chat`) và **tự viết `wiki_query`** (tên thực thể gọn để search Wiki). `retrieve()` điều phối theo `source`. **stt_worker KHÔNG phải đổi** (vẫn nhận context).

### 4.1 Sửa `_NORM_SYS` (thêm 2 field vào JSON output)
Thêm vào schema + quy tắc:
```
"source":"sgk|wiki|realtime|chat",
"wiki_query":"tên thực thể để tra Wikipedia, hoặc null"
```
Quy tắc dạy Gemma:
- `sgk`: hỏi/đọc/giảng/làm **bài trong SGK, tác phẩm văn học, bài học có trong sách**.
- `wiki`: **kiến thức đời/lịch sử/nhân vật/tổ chức/khoa học phổ thông/thông tin trường** KHÔNG gắn 1 bài SGK cụ thể → viết `wiki_query` = tên thực thể (vd "Nguyễn Hiền", "Tạm ước Việt Pháp 1946", "Mở rộng Liên minh châu Âu", "Học viện Công nghệ Bưu chính Viễn thông").
- `realtime`: hỏi ngày/giờ hiện tại.
- `chat`: tán gẫu.

### 4.2 Sửa `_normalize_query_gemma` (parse thêm)
Sau khi đã có `d` (dict JSON), thêm:
```python
source = str(d.get("source") or "").strip().lower()
if source not in ("sgk", "wiki", "realtime", "chat"):
    source = "sgk"           # mặc định an toàn: đi kho trước
wiki_query = d.get("wiki_query")
wiki_query = wiki_query.strip() if isinstance(wiki_query, str) and wiki_query.strip().lower() not in ("null","none","") else None
# ...thêm "source": source, "wiki_query": wiki_query vào dict return
```

### 4.3 Hàm mới `fetch_wikipedia(term)` (urllib, có cache)
```python
import urllib.request, urllib.parse
_WIKI_CACHE = {}   # {term: (expire_ts, (title, extract))}
_WIKI_UA = "PTalkEdu/1.0 (namnx@ptalk.vn)"
def fetch_wikipedia(term, chars=2500):
    now = time.time()
    c = _WIKI_CACHE.get(term)
    if c and c[0] > now: return c[1]
    def _api(p):
        url="https://vi.wikipedia.org/w/api.php?"+urllib.parse.urlencode(p)
        req=urllib.request.Request(url, headers={"User-Agent":_WIKI_UA})
        with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read().decode())
    try:
        s=_api({"action":"query","list":"search","srsearch":term,"format":"json","srlimit":1,"utf8":1})
        hits=s.get("query",{}).get("search",[])
        if not hits: return ("","")
        title=hits[0]["title"]
        e=_api({"action":"query","prop":"extracts","explaintext":1,"exchars":chars,
                "titles":title,"format":"json","redirects":1,"utf8":1})
        ext=""
        for pg in e.get("query",{}).get("pages",{}).values(): ext=pg.get("extract","")
        out=(title, ext)
    except Exception as ex:
        print("[wiki] err", ex); out=("","")
    _WIKI_CACHE[term]=(now+86400, out)   # cache 24h
    return out
```

### 4.4 Ráp vào `retrieve()` — CHỖ SỬA CHÍNH
Ngay sau khi có `norm` (B0/B1), TRƯỚC nhánh B2, thêm điều phối theo `source`:
```python
source = (norm or {}).get("source") if norm else None
wq = (norm or {}).get("wiki_query")

# --- REALTIME ---
if source == "realtime":
    from datetime import datetime
    now = datetime.now().strftime("Hôm nay là %d/%m/%Y, %H giờ %M phút")
    return RetrieveResponse(context=f"[THỜI GIAN THỰC]\n{now}",
        intent={"need_rag":True,"query_type":"realtime"}, sources=["clock"])

# --- WIKI (kiến thức ngoài SGK) ---
if source == "wiki":
    title, ext = fetch_wikipedia(wq or gwork or q)
    if ext:
        ctx = f"[NGUỒN WIKIPEDIA - {title}]\n{ext}"
        return RetrieveResponse(context=unicodedata.normalize('NFC', ctx),
            intent={"need_rag":True,"query_type":"wiki","source_title":title}, sources=["wikipedia"])
    # wiki rỗng → rơi xuống not_found/hiểu-biết-chung
```

### 4.5 Fallback SGK-miss → Wiki (MẤU CHỐT chống bịa)
Ở **B2b** (chỗ đang `return _not_found_response(gwork, None)`) và ở cuối **B4** (chỗ "chưa tìm thấy dữ liệu nội bộ"), thay vì trả miss ngay → thử Wiki trước:
```python
# B2b / cuối B4:
title, ext = fetch_wikipedia(wq or gwork or subj or q)
if ext:
    ctx = f"[NGUỒN WIKIPEDIA - {title}]\n{ext}"
    return RetrieveResponse(context=unicodedata.normalize('NFC', ctx),
        intent={"need_rag":True,"query_type":"wiki_fallback","source_title":title}, sources=["wikipedia"])
return _not_found_response(gwork, None)   # wiki cũng rỗng → thật thà
```

### 4.6 stt_worker (KHÔNG bắt buộc đổi)
- Context Wiki KHÔNG chứa marker miss → tự động vào nhánh HIT → nhồi `<KIẾN_THỨC_SGK_NỘI_BỘ>`.
- (Tùy chọn) Nếu muốn LLM phân biệt nguồn, đổi tên thẻ thành `<KIẾN_THỨC_NỀN>` chung, hoặc thêm 1 câu "nếu [NGUỒN WIKIPEDIA] thì trích dẫn chính xác, không bịa".

---

## 5. Nguyên tắc điều phối (tóm)
1. **Ưu tiên kho SGK** (giọng đúng sách) — `source=sgk` chạy B2/B3/B4 như hiện tại.
2. **Wiki chỉ khi**: (a) router phán `source=wiki`, hoặc (b) SGK **miss** (fallback). → tránh nhồi 2 nguồn/lệch giọng.
3. **Wiki tự viết `wiki_query`** = tên thực thể → nhắm đúng trang (fix lỗi search cả-câu ra trang sai: PTIT→VNPT, EU→trang chung).
4. **Wiki rỗng → thật thà** ("chưa chắc"), KHÔNG bịa.
5. **Cache Wiki 24h** theo term → giảm latency + gọi API. Chỉ nhánh wiki mới +~1.5s.
6. **An toàn trẻ em**: input vẫn qua `screen_input`/`banned_topics`; có thể whitelist môn cho Wiki.

## 6. Env/knobs liên quan
- `RAG_PORT=8888`; Gemma: `LLM_API_URL`/`LLM_MODEL`/`LLM_API_KEY` (call_gemma).
- `NORMALIZE_ENABLED` (bật normalizer). Neo4j edu: `bolt://127.0.0.1:7688` (auth neo4j/REDACTED).
- (mới) có thể thêm: `WIKI_ENABLED`, `WIKI_LANG=vi`, `WIKI_CACHE_TTL`.

## 7. Test lại sau khi sửa
Chạy các script đã lưu ở `/home/namnx/recite_tests/` (hoặc /tmp):
- `factcheck.py` — 6 câu factual (RAG ra gì + LLM đáp gì).
- `wiki_grounded.py` — nhồi Wiki + Gemma, xem đáp đúng chưa (Nguyễn Hiền, Tạm ước, EU, PTIT, số nguyên âm).
- So trước/sau: R015/R017/R009 phải hết bịa; R005/R042 cần `wiki_query` tốt (router viết).
