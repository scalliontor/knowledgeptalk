# Wiki-Orchestrator — Guide (canary LIVE)

> Biến `_normalize_query_gemma` thành **router 4 nguồn** (`sgk|wiki|realtime|chat`) ngay trong `rag_server.retrieve()`.
> Wikipedia là **lưới đỡ** cho câu hỏi ngoài SGK, KHÔNG bao giờ cướp lượt của kho recite/companion đã curate.
> **Trạng thái:** đang chạy canary **:8893** (đã test PASS). Prod **:8888 KHÔNG đụng**. 2026-07-08.

---

## 0. Luồng chính CloudPTalk có phải sửa không? → **KHÔNG. Chỉ sửa `rag_server.py`.**

| Thành phần | Có đổi? | Vì sao |
|---|---|---|
| `rag_server.py` | ✅ **chỉ ở đây** | thêm router + `_try_wiki`; xem §3 |
| `shared/rag_client.py` | ❌ | vẫn `POST /retrieve`, nhận `context` — shape `RetrieveResponse` giữ nguyên |
| `workers/stt_worker.py` | ⚠️ **1 patch NHỎ, TÙY CHỌN** | context wiki `[NGUỒN NGOÀI SGK…]` **không** có marker miss → tự vào nhánh **HIT** hiện có, chạy được ngay. Patch chỉ để đổi thẻ provenance + hạ tông (§6) — **để dành nhịp restart** |
| `workers/llm_worker.py`, `tts_worker.py`, Redis Streams | ❌ | không liên quan |

**Kết luận:** feature hoạt động **end-to-end mà không cần chạm luồng chính**. `stt_worker` đã chừa sẵn nhánh MISS ghi chú *"Wikipedia sau này"*. Patch provenance (§6) là *nên có* nhưng không bắt buộc để chạy.

---

## 1. Thiết kế cuối — 1 luật nhất quán (đã chốt sau review 5 lăng kính)

```
retrieve(): sau khi Gemma-router trả {intent, source, work, wiki_query, ...}

1. REALTIME   source=realtime & câu THUẦN hỏi giờ (không "học/bài/đọc/giảng/thơ/văn/toán")
              → [THỜI GIAN THỰC] datetime.now(Asia/Ho_Chi_Minh)              [HIGH#11]

2. CÓ work SGK (gwork)  → LUÔN chạy B2 (lesson_card → recite) TRƯỚC          [#3]
   • B2 hit                        → recite/companion (kho curate) — wiki KHÔNG chạm được
   • B2 miss & intent=explain & wiki_query → _try_wiki() (lưới đỡ)          [B2b, bỏ #2]
   • B2 miss & recite/practice     → _not_found TỨC THÌ (không wiki)         [HIGH#5]
   • anchor _SESSION_WORK CHỈ khi source=sgk                                 [HIGH#6]

3. KHÔNG có work (gwork=None):
   • source=wiki & explain & wiki_query → _try_wiki() (EAGER)                [#3: eager chỉ khi gwork=None]
   • B3 Tier A (bài số/trang) — như cũ
   • B4 retrieval — như cũ; B4-miss & explain & wiki_query → _try_wiki()     [HIGH#5]

4. chat & !gwork → need_rag=False (nguyên)
```

**Bất biến an toàn (đã test):** wiki trả **text-block** `[NGUỒN NGOÀI SGK - Wikipedia: …]` — KHÔNG phải JSON `full_recitation_lines` → **không bao giờ** rơi vào nhánh recite-verbatim-to-TTS của `stt_worker`. Không luật nào cho phép wiki chạy khi đang có work SGK hoặc khi intent là recite/practice.

**Câu hỏi "bổ sung vs thay thế":** CHỈ **thay-thế-khi-miss**, KHÔNG nhồi 2 nguồn. Kho SGK luôn thắng; wiki chỉ là lưới đỡ ở đúng 2 chỗ `gwork=None` (+ B2b explain-miss).

---

## 2. Router mở rộng (Gemma `_NORM_SYS`)

JSON output thêm 2 field:
```json
{"intent":"recite|explain|practice|chat","source":"sgk|wiki|realtime|chat", ...,
 "wiki_query":"tên thực thể gọn để tra Wikipedia khi source=wiki, hoặc null"}
```
Luật dạy Gemma: `sgk` = bài/tác phẩm trong SGK (mặc định) · `wiki` = kiến thức đời/lịch sử/nhân vật/tổ chức/trường/khoa học phổ thông KHÔNG gắn bài SGK + **tự viết `wiki_query` = TÊN THỰC THỂ** (không phải cả câu) · `realtime` = giờ/ngày · `chat` = tán gẫu.
→ Chính việc Gemma trích thực thể là thứ fix lỗi search cả-câu (PTIT→VNPT, EU→trang chung). Test B2 xác nhận PTIT ra đúng.

---

## 3. Thêm gì vào `rag_server.py` (tái tạo bằng `make_canary.py`)

Toàn bộ thay đổi = 14 phép thay chuỗi có anchor (patch script `scratchpad/make_canary.py`, assert count==1 mỗi anchor). Khối chính:

- **imports:** `time`, `urllib.parse`, `datetime`, `ZoneInfo(Asia/Ho_Chi_Minh)`.
- **`_NORM_SYS` / `_normalize_query_gemma`:** parse `source` (default `sgk`), `wiki_query` (chỉ giữ khi source=wiki).
- **Khối WIKI ORCHESTRATOR** (đặt ngay trước `async def retrieve`):
  - `_wiki_fetch_sync(term)` — **1 request gộp** `generator=search&prop=extracts&exintro&explaintext&exchars` (nửa round-trip).
  - `_wiki_title_ok(title, term)` — **verify title ≈ term** + loại trang `(định hướng)` (chống "Sông Đáy"→con sông). [HIGH#8]
  - `_try_wiki(term)` — **async** `asyncio.to_thread` (KHÔNG block event loop) + `asyncio.wait_for(WIKI_BUDGET_S)` + **circuit-breaker** (3 lỗi→cooldown 60s) + **cache tách** hit 24h / stable-negative 6h / transient-fail 45s. [#4, HIGH#5/#8/#10]
  - `_wiki_response(...)` — đóng gói marker `[NGUỒN NGOÀI SGK - Wikipedia: <title>]`.
- **`retrieve()`:** realtime branch + gate wiki ở B2b/eager/B4 + session hygiene (chỉ anchor khi `source=sgk`). Term wiki **luôn = `wiki_query`** (bỏ ladder `subj/q` → hết lỗi tra bằng mã môn). [HIGH#9]

### Env knobs (van vận hành)
| Biến | Default | Ý nghĩa |
|---|---|---|
| `WIKI_ENABLED` | `1` | **van tắt-nhanh** — sự cố thì set `0`, hết wiki, không cần sửa code |
| `WIKI_BUDGET_S` | `2.5` | ngân sách TỔNG wall-clock 1 lượt wiki (timeout + wait_for) |
| `WIKI_LANG` | `vi` | wiki ngôn ngữ |
| `WIKI_CHARS` | `2200` | độ dài extract (intro) |

---

## 4. Kết quả test canary (`scratchpad/test_canary.py`, mỗi câu 1 session_id riêng)

```
A. BẤT BIẾN recite KHÔNG bị wiki cướp
  ✅ Nam quốc sơn hà / Sóng / Nhớ rừng / Đất nước / Bình Ngô đại cáo → RECITE (~0.5s)
  ✅ giảng Lão Hạc → LESSON
B. WIKI EAGER (ngoài SGK)
  ✅ Nguyễn Hiền✓ · Học viện CN BCVT✓ (hết lỗi VNPT) · Liên minh châu Âu✓ · Pháp✓   (2.1–2.8s)
C. REALTIME + guard
  ✅ "mấy giờ rồi"→REALTIME · "hôm nay học bài gì"→KHÔNG realtime (guard)
D. HONEST-MISS
  ✅ recite bài-bịa → NOTFOUND, KHÔNG wiki (~1s = chi phí Neo4j cũ, không hồi quy)
E. SESSION HYGIENE
  ✅ turn1 wiki "Nguyễn Hiền" → turn2 "đọc thơ ông ấy" KHÔNG bị neo Nguyễn Hiền
```
Latency: recite/realtime ~0.5s (không đổi vs baseline) · wiki explain ~2.1–2.8s (đúng budget, chỉ trên nhánh explain-miss, KHÔNG chạm hot path recite).

### 4b. Adversarial battery (166 tựa thật + 5 nhóm khó, 2026-07-08) — PASS
- **Backtest 166 tựa thật (12 lớp + 22 tựa-nguy-hiểm):** recite giữ 98%, **wiki-cướp-recite = 0** (metric chặn-prob). 2 NOTFOUND = data-gap cũ (Ăng-Co Vát/ga-vrốt).
- **Nhóm 1 (tựa trùng thực-thể):** Tây Tiến/Việt Bắc/Sóng/Đất Nước→RECITE; "sóng là gì"→WIKI, "đất nước…bao nhiêu tỉnh"→WIKI (phân đôi đúng); Chí Phèo→LESSON. ✅
- **Nhóm 3 (realtime guard):** "hôm nay thứ mấy"→REALTIME; "giờ HỌC tiếng Việt mấy giờ"→KHÔNG realtime. ✅
- **Nhóm 4 (failure-mode):** budget=0.1→timeout graceful ~0.6s (không treo); **circuit-breaker mở sau 3 lỗi, câu 4 skip không gọi mạng**; WIKI_ENABLED=0→baseline sạch, router vẫn chạy. ✅
- **Nhóm 5 (hygiene 2 chiều):** "đọc Nhớ rừng"→"đọc tiếp đi" giữ Nhớ rừng (anchor SGK sống); wiki "Nguyễn Hiền"→"còn Mạc Đĩnh Chi" ra Mạc Đĩnh Chi (không dính). ✅
- **Latency:** solo p50=508ms (không hồi quy); mixed 5recite+3wiki đồng thời → recite KHÔNG bị async-wiki chặn.
- ⚠️ **2 điểm AMBER (không chặn prod):** (1) "ai phát minh bóng đèn" → Gemma tag `sgk` → B4 tìm được chunk → KHÔNG rơi wiki (lưới 2-chiều chỉ bắt khi B4 *rỗng hẳn*; = router-tuning `_NORM_SYS`, không phải lỗi code). (2) recite dưới 8-đồng-thời ~2.5s do `call_gemma` SYNC serialize (PRE-EXISTING, prod hiện cũng vậy; wiki async KHÔNG làm tệ hơn). Cải tiến tùy chọn: `await asyncio.to_thread(call_gemma,…)`.

---

## 5. Vận hành canary

```bash
# đang chạy: RAG_PORT=8893, file rag_server_canary8892.py, log /tmp/canary8893.log
ssh namnx@171.226.10.121
cd /home/namnx/Ptalk_project/CloudPTalk

bash launch_canary8892.sh            # (re)start canary (pkill CHỈ canary, không đụng prod)
tail -f /tmp/canary8893.log          # log
venv/bin/python /tmp/test_canary.py  # chạy lại test matrix
pkill -9 -f 'rag_server_canary8892\.py'   # dừng canary (an toàn: pattern không khớp prod)

# tắt wiki mà vẫn giữ router:  WIKI_ENABLED=0 trong launch script
```
⚠️ `pkill` prod PHẢI dùng literal-dot `'rag_server\.py'`; canary dùng `'rag_server_canary8892\.py'` — hai pattern KHÔNG giẫm nhau.

---

## 6. Patch `stt_worker.py` (provenance — HIGH#7) — ĐỂ DÀNH NHỊP RESTART

Hiện wiki context vào nhánh HIT và bị nhồi dưới thẻ `<KIẾN_THỨC_SGK_NỘI_BỘ>` ("coi là kiến thức con sẵn có") → LLM trình wiki với thẩm quyền "sách của con". Nên tách nguồn. Sửa chỗ build `system_prompt` cho nhánh HIT (`stt_worker.py:260`):

```python
# THAY block nhồi <KIẾN_THỨC_SGK_NỘI_BỘ> bằng: phân biệt nguồn wiki vs SGK
if clean_context.startswith("[NGUỒN NGOÀI SGK"):
    llm_job["llm_config"]["system_prompt"] = (
        f"{sys_prompt}\n\n<KIẾN_THỨC_THAM_KHẢO_NGOÀI_SGK>\n"
        "Đây là thông tin THAM KHẢO từ Wikipedia (KHÔNG nằm trong sách giáo khoa của con). "
        "Dùng để trả lời đúng trọng tâm, NHƯNG nói tự nhiên kiểu 'theo tớ biết…' — "
        "diễn đạt đơn giản hợp tuổi, bỏ ký hiệu phiên âm/ngày tháng rườm rà, "
        "và KHÔNG kể chi tiết bạo lực/tệ nạn/người lớn.\n"
        f"[THÔNG TIN]:\n{clean_context}\n</KIẾN_THỨC_THAM_KHẢO_NGOÀI_SGK>"
    )
else:
    # ... giữ nguyên nhánh <KIẾN_THỨC_SGK_NỘI_BỘ> hiện tại ...
```
→ áp cùng nhịp deploy prod (vì `stt_worker` chỉ có 1, không canary riêng được).

---

## 7. Rollout lên prod (⛔ PHẢI XIN PHÉP TRƯỚC KHI RESTART :8888)

1. Shadow/canary (**đang ở đây**): đã PASS test matrix. Nên chạy thêm backtest ~81 quyển + tập tựa-trùng-danh-từ để chốt recite không tụt <94%.
2. Copy `rag_server_canary8892.py` → nội dung mới cho `rag_server.py` (đã bao gồm mọi thay đổi; RAG_PORT vẫn đọc env → prod bind 8888).
3. Áp patch §6 vào `stt_worker.py`.
4. **XIN anh 1 nhịp restart** (ESP32 downtime). Deploy: backup `rag_server.py.bak_pre_wiki` → cp bản mới → restart screen `ptalk_rag` → restart stt_worker. Bật `WIKI_ENABLED=1`; nếu sự cố set `0` là tắt ngay.
5. Sau prod: theo dõi log `[wiki]` (hit-rate, fail, circuit-open) + tỉ lệ Gemma dán `source` để chỉnh prompt.

---

## 8. Đã BẢO LƯU theo yêu cầu (không làm đợt này)
- **#1 safety-pass OUTPUT** trên extract wiki: **bỏ**. Wiki tới trẻ chưa lọc-nghĩa (chỉ còn lọc từ-cấm INPUT ở `stt_worker:131`). Van tối thiểu giữ lại: cờ `WIKI_ENABLED`. Muốn "van rẻ" sau: thêm allow-list vài môn học-thuật cho `source=wiki`.
- **#2 recite/practice-never-wiki (hard-gate + telemetry corpus-gap):** hạ xuống — thực tế HIGH#5 (recite-miss→not_found tức thì) đã cho cùng hành vi; B2b vẫn cho explain-miss rơi wiki.
