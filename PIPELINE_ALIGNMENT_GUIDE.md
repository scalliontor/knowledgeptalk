# Pipeline Alignment Guide — RAG ↔ STT/LLM/TTS/App (2026-07-09)

> Sau 3 thay đổi đã LIVE prod :8888: **(1) Wiki-orchestrator router**, **(2) Grade-anchor recite**, **(3) Recite data cleaning**.
> Guide này = hợp đồng để sửa khớp `pipeline tổng` (stt_worker / rag_client / llm_worker / app-ESP32) + test end-to-end.
> Nguồn sự thật code = `rag_server.py` TRÊN SERVER (`/home/namnx/Ptalk_project/CloudPTalk/`), KHÔNG phải repo.

---

## 0. Trạng thái LIVE (prod :8888)
| Thành phần | Trạng thái |
|---|---|
| Wiki-orchestrator (router 4 nguồn sgk/wiki/realtime/chat) | ✅ LIVE (WIKI_ENABLED=1) |
| Grade-anchor recite (câu nêu lớp → đúng bản; grade-free → recite_default) | ✅ LIVE |
| Recite cleaning (HTML/footnote/uơ→ươ/metadata/tách-chữ, 287 node) | ✅ LIVE (data) |
| Dup-title tag (recite_default×61, recite_dup_of×24) | ✅ LIVE (data) |
| stt_worker provenance tag `<KIẾN_THỨC_THAM_KHẢO_NGOÀI_SGK>` cho wiki | ✅ LIVE |
| **Recite-bypass (đọc thẳng, không LLM)** | ⏳ CHƯA — Restart #2 sau soak (xem §6) |

Rollback: `cp rag_server.py.bak_pre_gradeanchor_20260709 rag_server.py` + restart screen ptalk_rag. Tắt mềm wiki: `WIKI_ENABLED=0`.

---

## 1. HỢP ĐỒNG `retrieve()` — cái mọi consumer phải bám

**Endpoint:** `POST /v2/rag/retrieve` (đầy đủ) hoặc `POST /retrieve` (legacy → `{context, retrieved_sources, intent}`).
**Request:** `{"query": str, "session_id": str, "user_profile": dict|null}`.
**Response:** `{"context": str, "intent": dict, "sources": list}`.

### 1.1 `context` — nhận DẠNG bằng MARKER (⚠️ không đồng nhất)
| Loại | Dấu hiệu đầu context | query_type |
|---|---|---|
| Recite JSON | `{"type":"full_recitation_lines","lines":[{text,pause_ms}]}` | recite_full_text |
| Recite text-block | `[ĐỌC THUỘC - NGUYÊN VĂN]` | recite_full_text / lesson_recite |
| Companion (giảng) | `[ĐỒNG HÀNH BÀI HỌC]` (tier=lesson_card) | companion |
| **Wiki (ngoài SGK)** | `[NGUỒN NGOÀI SGK - Wikipedia: <title>]` | wiki / wiki_fallback |
| **Realtime** | `[THỜI GIAN THỰC]` | realtime |
| Tier A (bài số/trang) | `[DU LIEU EXACT - TIER A]` | A_structured |
| Kiến thức nội bộ | `[DỮ LIỆU CẤU TRÚC - NEO4J…]` | explain |
| **MISS (thật thà)** | `[KHÔNG TÌM THẤY]` HOẶC `chưa tìm thấy dữ liệu nội bộ` | not_found |
| Chat | `""` (rỗng) | chat (need_rag=False) |

### 1.2 `intent` — field mới cần biết
`need_rag`(bool) · `query_type`(bảng trên) · `tier` · `source`(="wikipedia" khi wiki) · `source_title`(tựa wiki) · `work_name` · `grade` · `bo_sach` · `subject` · `learning_mode`.

---

## 2. `stt_worker.py` — đã khớp HOÀN TOÀN (grade-anchor tự động qua profile, 0 sửa)

### 2.1 Đã đúng (giữ nguyên)
- **MISS detect:** `_RAG_MISS = (not ctx) or ("[KHÔNG TÌM THẤY]" in ctx) or ("chưa tìm thấy dữ liệu nội bộ" in ctx)`. Wiki/realtime KHÔNG chứa marker miss → tự vào nhánh HIT. ✅
- **Provenance (đã patch):** context bắt đầu `[NGUỒN NGOÀI SGK` → nhồi dưới thẻ `<KIẾN_THỨC_THAM_KHẢO_NGOÀI_SGK>` + hạ tông; còn lại → `<KIẾN_THỨC_SGK_NỘI_BỘ>`. ✅
- **Input screening:** `shared.moderation.screen_input` (banned-words) chạy TRƯỚC RAG. ✅ (Lưu ý: KHÔNG bắt nội dung độc trong OUTPUT wiki — đã bỏ safety-pass output theo quyết định trước.)

### 2.2 ✅ GRADE-ANCHOR (option B) — ĐÃ IMPLEMENT TRONG RAG, KHÔNG cần sửa pipeline
Grade-anchor chỉ đúng bản khi biết lớp của bé. RAG (canary đã test XANH) tự đọc grade từ `user_profile` — **chuỗi ĐÃ có sẵn end-to-end, không sửa gì**:
`resolve_student_profile → {"lop","bo_sach"}` → `stt_worker:175 fetch_knowledge(text, student_profile)` → `rag_client:11 payload{user_profile}` → `retrieve()` đọc `req.user_profile.lop/bo_sach`.

Thiết kế (đã test):
- **SOFT tie-break** (KHÔNG hard-filter): bé lớp 12 hỏi "đọc bài Lượm" (lớp 6) → **vẫn đọc được, KHÔNG false-MISS**. Grade chỉ ưu tiên bản đúng lớp GIỮA các dup-title.
- **Strict-grade-exact pre-check**: có lớp → thử LiteratureText đúng lớp TRƯỚC lesson_card. Fix ca "Mẹ" (bản L7 Đỗ Trung Lai chỉ là LiteratureText không có :Lesson, bản L2 Trần Quốc Minh có :Lesson → không có strict thì lesson_card luôn trả L2).
- **Verbal override thắng profile**: bé nói "lớp 8 cánh diều" (Gemma trích) → dùng lớp trong câu; câu không nêu → dùng profile.
- Giữ nguyên tắc **RAG account-agnostic**: grade do app KHAI qua profile, RAG không tự đoán.

→ **Việc pipeline cần làm: KHÔNG có** (khác với dự thảo cũ khuyến nghị option A). Chỉ cần deploy bản RAG soft+strict (1 restart, canary đã xanh). Đảm bảo `student_profile` trong DB đúng lớp/bộ của từng bé để anchor chuẩn.

---

## 3. `rag_client.py` / `llm_worker.py` / `tts_worker.py`
- **rag_client:** KHÔNG đổi (vẫn POST /retrieve, nhận context). Shape response giữ nguyên.
- **llm_worker:** KHÔNG đổi bắt buộc. Wiki context đã được stt_worker đóng khung "nguồn ngoài SGK, hạ tông". Nếu muốn chắc: thêm 1 câu safety-prompt cho nhánh có `<KIẾN_THỨC_THAM_KHẢO_NGOÀI_SGK>`.
- **tts_worker:** KHÔNG đổi. (Khi bật recite-bypass ở Restart #2, stt_worker sẽ đẩy thẳng từng dòng recite vào STREAM_TTS — tts_worker đã xử lý được luồng đó.)

---

## 4. App / ESP32
- KHÔNG bắt buộc đổi. Câu hỏi kiến-thức-đời ("Nguyễn Hiền là ai") giờ có đáp (wiki) thay vì "chưa biết".
- Nếu app có UI hồ sơ bé (lớp/bộ sách) → đảm bảo `student_profile` trong DB đúng để cách (A) §2.2 anchor chuẩn.
- (Tùy chọn) Hiển thị nguồn: `intent.source=="wikipedia"` → badge "Tham khảo Wikipedia" cho phụ huynh.

---

## 5. TEST end-to-end (chạy được ngay)

### 5.1 RAG contract (script sẵn trên server, KHÔNG cần pipeline)
```bash
ssh namnx@171.226.10.121
cd /home/namnx/Ptalk_project/CloudPTalk
venv/bin/python /tmp/test_grade_anchor.py     # grade-anchor: Đất Nước/Mẹ/Mưa xuân theo lớp
venv/bin/python /tmp/test_adv.py              # wiki router + realtime + hygiene (đổi URL :8888)
```
Kỳ vọng: nêu lớp→đúng bản; grade-free→recite_default; wiki/realtime/recite đúng loại.

### 5.2 Sau khi sửa §2.2 (grade injection) — test cách (A)
Giả lập student_profile.lop=12 rồi hỏi "đọc bài Đất Nước" (KHÔNG nói lớp) → phải ra **Nguyễn Khoa Điềm** (không phải recite_default). Đổi lop=10 → **Nguyễn Đình Thi**. Đây là bằng chứng grade-injection hoạt động trên câu trẻ nói tự nhiên.

### 5.3 End-to-end thật (STT→TTS) — checklist tay trên loa
| Câu bé nói | Kỳ vọng loa |
|---|---|
| "đọc bài Nhớ rừng" | đọc nguyên văn (đã sạch "tấm thân như") |
| "Nguyễn Hiền là ai" | trả lời theo Wikipedia, giọng "theo tớ biết…" |
| "mấy giờ rồi" | báo giờ VN |
| "đọc bài Đất Nước" (bé hồ sơ lớp 12) | bản Nguyễn Khoa Điềm (sau khi sửa §2.2) |
| "ma túy là gì" | ⚠️ hiện KHÔNG có safety-pass output — kiểm phản hồi, chấp nhận rủi ro theo quyết định trước |

---

## 6. SẮP TỚI — Restart #2 (recite-bypass), CHƯA làm
Sau **soak vài ngày** xác nhận grade-anchor ra đúng bản trên traffic thật:
- Bật **recite-bypass**: stt_worker đọc THẲNG verbatim (bỏ LLM) khi recite JSON. Hiện gate `os.getenv("RECITE_VIA_LLM","1")!="1"` (mặc định=1 → tắt).
- **GATE BẢO THỦ (bắt buộc):** chỉ bypass khi ĐÚNG 1 ứng viên rõ (grade resolved HOẶC chỉ 1 bản, KHÔNG dính EXCERPT_VS_FULL mập mờ) → mập mờ rơi về LLM.
- **Kill-switch** env `RECITE_BYPASS_ENABLED` (giống WIKI_ENABLED, tắt không cần restart).
- Lý do tách restart: bypass gỡ lưới LLM → anchor sai kiểu canary không bắt sẽ thành audio sai nghe rõ.

---

## 7. Env knobs (prod)
`WIKI_ENABLED=1` (tắt wiki=0) · `WIKI_BUDGET_S=2.5` · `WIKI_LANG=vi` · `RAG_QUERY_NORMALIZE=1` (Gemma router) · `RECITE_VIA_LLM=1` (recite qua LLM; =0 để bypass — chờ Restart #2 + gate) · (sắp) `RECITE_BYPASS_ENABLED`.

## 8. Nguyên tắc xuyên suốt
- Sửa data Neo4j = OK không cần hỏi; **restart prod PHẢI xin** (ESP32 downtime).
- Phán đoán agent/LLM phải có **cổng tất định** gác (bài học difflib cứu 4 ca dup-title khỏi xoá nhầm).
- Backup per-node trước mọi ghi data; backup file rag_server.py.bak_* trước mọi deploy.
