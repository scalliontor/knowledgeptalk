# RAG Edu — Knowledge Base & System Walkthrough

## Tổng quan hệ thống

**Mục tiêu:** RAG chatbot hỗ trợ học sinh lớp 1-9 môn Tiếng Việt / Ngữ Văn, deploy trên L40S server.

**Stack:**
- **Crawler:** Scrapy → loigiaihay.com
- **Storage:** PostgreSQL (port 5433, Docker `rag_postgres`) + Qdrant (port 6333)
- **Embedding:** `intfloat/multilingual-e5-large`
- **API:** FastAPI on port 8888 (SSH tunnel: `ssh -L 8888:localhost:8888 namnx@171.226.10.121`)
- **LLM:** OpenAI (hiện chưa có API key → dùng template fallback)

---

## Data Coverage — Nguồn dữ liệu

### Trang crawl: loigiaihay.com

| Lớp | Bộ sách | URL Category | Môn |
|-----|---------|--------------|-----|
| 1 | KNTT | `/sgk-tieng-viet-1-ket-noi-tri-thuc-voi-cuoc-song-c1181.html` | Tiếng Việt |
| 1 | CTST | `/sgk-tieng-viet-1-chan-troi-sang-tao-c1182.html` | Tiếng Việt |
| 1 | CD | `/sgk-tieng-viet-1-canh-dieu-c1183.html` | Tiếng Việt |
| 2 | KNTT | `/tieng-viet-2-ket-noi-tri-thuc-c1237.html` | Tiếng Việt |
| 2 | CTST | `/tieng-viet-2-chan-troi-sang-tao-c1238.html` | Tiếng Việt |
| 2 | CD | `/tieng-viet-2-canh-dieu-c1239.html` | Tiếng Việt |
| 3 | KNTT | `/tieng-viet-3-ket-noi-tri-thuc-c1284.html` | Tiếng Việt |
| 3 | CTST | `/tieng-viet-3-chan-troi-sang-tao-c1285.html` | Tiếng Việt |
| 3 | CD | `/tieng-viet-3-canh-dieu-c1286.html` | Tiếng Việt |
| 4 | KNTT | `/tieng-viet-4-ket-noi-tri-thuc-c1640.html` | Tiếng Việt |
| 4 | CTST | `/tieng-viet-4-chan-troi-sang-tao-c1641.html` | Tiếng Việt |
| 4 | CD | `/tieng-viet-4-canh-dieu-c1642.html` | Tiếng Việt |
| 5 | KNTT | `/tieng-viet-5-ket-noi-tri-thuc-c1786.html` | Tiếng Việt |
| 5 | CTST | `/tieng-viet-5-chan-troi-sang-tao-c1787.html` | Tiếng Việt |
| 5 | CD | `/tieng-viet-5-canh-dieu-c1788.html` | Tiếng Việt |
| 6 | KNTT | `/soan-bai-ngu-van-6-ket-noi-tri-thuc-voi-cuoc-song-c630.html` | Ngữ Văn |
| 6 | CTST | `/soan-van-6-chan-troi-sang-tao-c1232.html` | Ngữ Văn |
| 6 | CD | `/soan-van-6-canh-dieu-c1233.html` | Ngữ Văn |
| 7 | KNTT | `/soan-van-7-ket-noi-tri-thuc-c1278.html` | Ngữ Văn |
| 7 | CTST | `/soan-van-7-chan-troi-sang-tao-c1281.html` | Ngữ Văn |
| 7 | CD | `/soan-van-7-canh-dieu-c1280.html` | Ngữ Văn |
| 8 | KNTT | `/soan-van-8-ket-noi-tri-thuc-c1321.html` | Ngữ Văn |
| 8 | CTST | `/soan-van-8-chan-troi-sang-tao-c1323.html` | Ngữ Văn |
| 8 | CD | `/soan-van-8-canh-dieu-c1322.html` | Ngữ Văn |
| 9 | KNTT | `/soan-van-9-ket-noi-tri-thuc-c1676.html` | Ngữ Văn |
| 9 | CTST | `/soan-van-9-chan-troi-sang-tao-c1678.html` | Ngữ Văn |
| 9 | CD | `/soan-van-9-canh-dieu-c1677.html` | Ngữ Văn |

**Tình hình Crawl Thực Tế (Số lượng links JSONL đã lấy):**
Tổng số URL thu thập được: **10,927 articles**

| Cấp | Lớp | Số URL lấy được | Tình trạng |
|---|---|---|---|
| Tiểu học | Lớp 1 | 1,056 | ✅ Hoàn thiện |
| Tiểu học | Lớp 2 | 1,123 | ✅ Hoàn thiện |
| Tiểu học | Lớp 3 | 1,127 | ✅ Hoàn thiện |
| Tiểu học | Lớp 4 | 1,283 | ✅ Hoàn thiện |
| Tiểu học | Lớp 5 | 1,538 | ✅ Hoàn thiện |
| THCS | Lớp 6 | 1,057 | ✅ Hoàn thiện |
| THCS | Lớp 7 | 2,021 | ✅ Hoàn thiện |
| THCS | Lớp 8 | 0 | ❌ **Lỗi missing rate:** Spider không cào được url `lop-8` |
| THCS | Lớp 9 | 1,722 | ✅ Hoàn thiện |

> [!WARNING]
> **Bug Missing Lớp 8:** Mặc dù spider có setup URL category cho lớp 8 nhưng kết quả crawler log cho thấy chưa thu được link nào cho Lớp 8. Cần kiểm tra lại regex pattern hoặc selector trên trang của khối 8.

---

## Content Types — Phân loại nội dung

| Content Type | Mô tả | Nguồn URL | Indexed vào |
|---|---|---|---|
| `van_ban` | Văn bản gốc đầy đủ (để đọc) | `/van-ban-*` | `kb_sgk_reading` |
| `bai_doc` | Bài đọc hiểu tiểu học | `/tap-doc-*`, `/bai-doc-*` | `kb_sgk_reading` |
| `soan_van` | Soạn văn THCS (trả lời câu hỏi SGK) | `/soan-bai-*`, `/soan-van-*` | `kb_sgk_reading` |
| `phan_tich` | Phân tích / nghị luận / cảm nhận | `/phan-tich-*`, `/cam-nhan-*` | `kb_sgk_reading` |
| `tom_tat` | Tóm tắt / bố cục | `/tom-tat-*`, `/bo-cuc-*` | `kb_sgk_reading` |
| `on_tap` | Ôn tập | `/on-tap-*` | `kb_sgk_reading` |
| `ke_chuyen` | Kể chuyện | `/ke-chuyen-*` | `kb_sgk_reading` |
| `luyen_tu_va_cau` | Luyện từ và câu / ngữ pháp | `/luyen-tu-*`, `/thuc-hanh-tieng-viet-*` | `kb_language_concepts` |
| `tap_lam_van` | Tập làm văn / văn mẫu | `/tap-lam-van-*`, `/van-mau-*` | `kb_writing_samples` |
| `chinh_ta` | Chính tả | `/chinh-ta-*` | (other) |
| `de_kiem_tra` | Đề kiểm tra / đề thi | `/de-kiem-tra-*` | (other) |
| `unknown` | Chưa phân loại được | — | (other) |

---

## Retrieval Methods — Phương pháp truy xuất

### Intent Classifier (`src/retrieval/classifier.py`)

**Ưu tiên xử lý:**
1. **Rule-based (fast path)** — regex patterns, không cần LLM
2. **LLM classify (slow path)** — gọi OpenAI, có fallback
3. **Fallback khi LLM fail** → default về `lookup_reading` + semantic search

**Các intent hỗ trợ:**

| Intent | Trigger patterns | Retriever |
|---|---|---|
| `lookup_reading` | "đọc bài X", "soạn bài X", "phân tích X", "van ban X" | `SGKReadingRetriever` |
| `explain_concept` | "từ ghép là gì", "phân biệt X và Y" | `LanguageConceptRetriever` |
| `writing_outline` | "giúp em tả...", "dàn ý", "văn mẫu" | `WritingOutlineRetriever` |
| `lookup_curriculum` | "tuần này học gì", "hôm nay học bài gì" | `CurriculumRetriever` |
| `greeting` | "chào chị", "hi" | (no retrieval) |
| `off_topic` | không match | (no retrieval) |

### SGKReadingRetriever

1. **Exact lookup** — tìm `ten_bai` chứa tên bài trong PostgreSQL
2. **Semantic search** — embed query → Qdrant `sgk_readings` collection, filter by `lop` + `bo_sach`

### LanguageConceptRetriever

- Semantic search → Qdrant `language_concepts` collection

### WritingOutlineRetriever

- Query PostgreSQL `kb_writing_outlines` (hiện chưa có data)
- **Bug:** chưa fallback sang `kb_writing_samples`

---

## Vấn đề đã gặp & Cách giải quyết

### 1. Content classification quá hẹp (v1)
**Vấn đề:** Post-processor chỉ index `bai_doc` → chỉ 5 articles.
**Fix:** Mở rộng routing: `van_ban`, `soan_van`, `phan_tich`, `tom_tat`, `on_tap`, `ke_chuyen` → tất cả vào `kb_sgk_reading`.

### 2. Truncation nội dung (v1)
**Vấn đề:** Cắt content ở 2,000 chars → mất nội dung bài đọc dài.
**Fix:** Lưu full content vào DB, chỉ truncate 1,500 chars khi embed.

### 3. Spider chỉ crawl lớp 1 + lớp 5 (v1)
**Vấn đề:** `CATEGORY_URLS` chỉ có 4 entries.
**Fix:** Mở rộng lên 27 entries (9 lớp × 3 bộ sách). Crawl thêm 7,271 articles THCS.

### 4. THCS không có trong DB
**Vấn đề:** 4,800 THCS articles trong JSONL nhưng post-process chỉ index lớp 1-5.
**Root cause:** Spider gán `content_type=unknown` cho phần lớn THCS articles (2,710/4,800). DB routing chỉ index các type đã biết → `unknown` → `other` → không vào `kb_sgk_reading`.
**Fix v4:** Alias `unknown + grade >= 6` → `soan_van` trước khi routing:
```python
if content_type == "unknown" and grade and grade >= 6:
    content_type = "soan_van"  # treat as soạn văn
```
**Kết quả:** Re-index đang chạy, expect ~4,000 THCS articles vào KB.

### 5. Intent classifier gọi LLM → fail → off_topic
**Vấn đề:** Không có OpenAI API key → `_llm_classify()` fail → trả `{intent: off_topic}` → 0 sources.
**Fix v3:**
- Thêm `READING_PATTERNS` rule-based cho "đọc bài", "soạn bài", "văn bản"
- Fallback trong `_llm_classify` → default `lookup_reading` khi exception
- Kết quả: lớp 1-5 retrieve đúng ✅, THCS chờ re-index

### 6. `van_ban` chưa phân biệt được (v2)
**Vấn đề:** Không phân biệt bài soạn vs toàn văn tác phẩm.
**Fix:** Thêm `van_ban` content type, detect từ URL pattern `/van-ban-*` và title "Văn bản ...".

### 8. Database từ chối insert Lớp > 5
**Vấn đề:** Khi fix xong lỗi routing và re-index lại JSONL 10,927 dòng, script tiếp tục bỏ qua các bài trống của THCS (lớp 6,7,9). Nguyên nhân sâu xa là bảng DB `extracted_content` thuộc PostgreSQL vẫn giữ **Constraint Check** giới hạn `CHECK (grade >= 1 AND grade <= 5)` từ giai đoạn chỉ làm pilot Tiểu học, do đó mọi thao tác insert/update cho grade≥6 đều bị văng exception `violates check constraint`.
**Fix:**
- Đã chạy lệnh `ALTER TABLE extracted_content DROP CONSTRAINT IF EXISTS extracted_content_grade_check;` để xoá bỏ constraint này.
- Bổ sung lệnh catch `Exception` và in ra log trong script post-process để track.
- Hiện post-process script đang chạy lại `v5` để re-index toàn bộ data THCS.
**Vấn đề:** `writing_outline` intent → `WritingOutlineRetriever` → query `kb_writing_outlines` table nhưng table rỗng → 0 results.
**Fix cần làm:** Thêm fallback sang `kb_writing_samples` (đã có 116 items) hoặc dùng SGKReadingRetriever semantic.

---

## Test Results — Kết quả kiểm thử

### v3 (classifier fix + THCS re-index đang chạy):

| Query | Lớp | Sources | Status | Ghi chú |
|---|---|---|---|---|
| "Đọc bài Bộ sưu tập độc đáo" | 5 | 2 | ✅ | |
| "Đọc bài Lượm" | 2 | 3 | ✅ | |
| "Từ ghép là gì?" | 4 | 2 | ✅ | |
| "Đọc bài Bài học đường đời đầu tiên" | 6 | 0→? | ⏳ | Chờ re-index THCS v4 |
| "Soạn bài Lão Hạc lớp 8" | 8 | 0→? | ⏳ | Chờ re-index THCS v4 |
| "Giúp em tả con mèo" | 3 | 0 | ❌ | WritingOutlineRetriever bug |

---

## Các việc còn lại (TODO)

- [x] Crawl lớp 1-5 đầy đủ (3 bộ sách)
- [x] Crawl lớp 6-9 THCS (3 bộ sách) — 10,927 articles total
- [x] Phân loại `van_ban` (để đọc) vs `soan_van` (để học)
- [x] Fix intent classifier với rule-based patterns + LLM fallback
- [x] Fix routing THCS `unknown` → `soan_van`
- [x] **Xoá Check Constraint** bảng DB để cho phép insert Lớp 6-9
- [ ] **Chạy post-process:** Đang re-index full 10,927 urls vào Qdrant & Postgres
- [ ] **Sửa Crawler Lớp 8:** Chạy lại nhện Scrapy cho Lớp 8 vì bị sót.
- [ ] **Verify THCS queries** sau khi re-index xong
- [ ] Fix `WritingOutlineRetriever` fallback sang `kb_writing_samples`
- [ ] Cung cấp OpenAI API key vào `.env` để LLM generation hoạt động
- [ ] Optimize retriever: `exact_lookup` cho THCS cần search `ten_bai` khớp với title từ soan-bai pages
- [ ] Xây dựng bộ 200 câu hỏi eval

---

## File Paths quan trọng

```
/home/namnx/knowledgeforptalk/rag_edu/
├── scripts/
│   ├── loigiaihay_spider.py      # Scrapy spider — 27 category URLs
│   └── post_process_crawl.py     # JSONL → PostgreSQL + Qdrant
├── src/
│   ├── retrieval/
│   │   ├── classifier.py         # Intent classifier (rule-based + LLM)
│   │   ├── orchestrator.py       # RAG pipeline orchestrator
│   │   └── retrievers.py         # SGKReading, LanguageConcept, Writing, Curriculum
│   └── api/main.py               # FastAPI /chat endpoint
└── data/jsonl/
    └── loigiaihay_full_1to9.jsonl  # 10,927 articles (lớp 1-9 × 3 bộ sách)
```

## Server Info
```
Host: namnx@171.226.10.121
Pass: PtitCie@2026
API : http://localhost:8888 (via SSH tunnel -L 8888:localhost:8888)
DB  : PostgreSQL port 5433, db=rag_edu, user/pass=postgres
Qdrant: port 6333
Log : /tmp/rag_api_8888.log, /tmp/postprocess_v3.log
```
