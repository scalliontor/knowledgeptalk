# 📚 RAG Edu — Data Sources & Organization

**Last updated**: 2026-05-11

---

## 1. Tổng quan kiến trúc dữ liệu

```
Sources (loigiaihay.com, vietjack.com)
    ↓  Scrapy spiders
JSONL files (data/jsonl/)
    ↓  post_process_*.py
PostgreSQL (extracted_content, kb_*)
    ↓  embed_*.py
Qdrant Vector DB (semantic search)
    ↓  (Ngữ Văn only)
Neo4j Graph DB (full-text literature, Schema V2)
```

| Store | Port | Vai trò |
|---|---|---|
| PostgreSQL | 5433 | Structured data, exercises, concepts |
| Qdrant | 6333 | Vector embeddings (multilingual-e5-large, dim=1024) |
| Neo4j | 7688 | Knowledge graph — toàn văn tác phẩm văn học |

---

## 2. Nguồn dữ liệu theo môn học

### 2.1 TOÁN (Lớp 1-9)

**Spider**: `scripts/math_spider.py` | **Post-process**: `post_process_math.py` → `embed_math.py`

| Lớp | KNTT | CTST | CD |
|---|---|---|---|
| 1 | [c1139](https://loigiaihay.com/sgk-toan-1-ket-noi-tri-thuc-c1139.html) | [c1141](https://loigiaihay.com/sgk-toan-1-chan-troi-sang-tao-c1141.html) | [c1140](https://loigiaihay.com/sgk-toan-1-canh-dieu-c1140.html) |
| 2 | [c1234](https://loigiaihay.com/sgk-toan-2-ket-noi-tri-thuc-c1234.html) | [c1235](https://loigiaihay.com/sgk-toan-2-chan-troi-sang-tao-c1235.html) | [c1236](https://loigiaihay.com/sgk-toan-2-canh-dieu-c1236.html) |
| 3 | [c813](https://loigiaihay.com/sgk-toan-3-ket-noi-tri-thuc-c813.html) | [c860](https://loigiaihay.com/sgk-toan-3-chan-troi-sang-tao-c860.html) | [c861](https://loigiaihay.com/sgk-toan-3-canh-dieu-c861.html) |
| 4 | [c1398](https://loigiaihay.com/sgk-toan-4-ket-noi-tri-thuc-c1398.html) | [c1399](https://loigiaihay.com/sgk-toan-4-chan-troi-sang-tao-c1399.html) | [c1400](https://loigiaihay.com/sgk-toan-4-canh-dieu-c1400.html) |
| 5 | [c1728](https://loigiaihay.com/sgk-toan-5-ket-noi-tri-thuc-c1728.html) | [c1729](https://loigiaihay.com/sgk-toan-5-chan-troi-sang-tao-c1729.html) | [c1730](https://loigiaihay.com/sgk-toan-5-canh-dieu-c1730.html) |
| 6 | [c599](https://loigiaihay.com/sgk-toan-6-ket-noi-tri-thuc-c599.html) | [c601](https://loigiaihay.com/sgk-toan-6-chan-troi-sang-tao-c601.html) | [c600](https://loigiaihay.com/sgk-toan-6-canh-dieu-c600.html) |
| 7 | [c807](https://loigiaihay.com/sgk-toan-7-ket-noi-tri-thuc-c807.html) | [c808](https://loigiaihay.com/sgk-toan-7-chan-troi-sang-tao-c808.html) | [c809](https://loigiaihay.com/sgk-toan-7-canh-dieu-c809.html) |
| 8 | [c1390](https://loigiaihay.com/sgk-toan-8-ket-noi-tri-thuc-c1390.html) | [c1391](https://loigiaihay.com/sgk-toan-8-chan-troi-sang-tao-c1391.html) | [c1392](https://loigiaihay.com/sgk-toan-8-canh-dieu-c1392.html) |
| 9 | [c1748](https://loigiaihay.com/sgk-toan-9-ket-noi-tri-thuc-c1748.html) | [c1749](https://loigiaihay.com/sgk-toan-9-chan-troi-sang-tao-c1749.html) | [c1750](https://loigiaihay.com/sgk-toan-9-canh-dieu-c1750.html) |

### 2.2 TIẾNG VIỆT (Tiểu học, Lớp 1-5)

**Spider**: `scripts/loigiaihay_spider.py`

| Lớp | KNTT | CTST | CD |
|---|---|---|---|
| 1 | [c1181](https://loigiaihay.com/sgk-tieng-viet-1-ket-noi-tri-thuc-voi-cuoc-song-c1181.html) | [c1182](https://loigiaihay.com/sgk-tieng-viet-1-chan-troi-sang-tao-c1182.html) | [c1183](https://loigiaihay.com/sgk-tieng-viet-1-canh-dieu-c1183.html) |
| 2 | [c1237](https://loigiaihay.com/tieng-viet-2-ket-noi-tri-thuc-c1237.html) | [c1238](https://loigiaihay.com/tieng-viet-2-chan-troi-sang-tao-c1238.html) | [c1239](https://loigiaihay.com/tieng-viet-2-canh-dieu-c1239.html) |
| 3 | [c1284](https://loigiaihay.com/tieng-viet-3-ket-noi-tri-thuc-c1284.html) | [c1285](https://loigiaihay.com/tieng-viet-3-chan-troi-sang-tao-c1285.html) | [c1286](https://loigiaihay.com/tieng-viet-3-canh-dieu-c1286.html) |
| 4 | [c1640](https://loigiaihay.com/tieng-viet-4-ket-noi-tri-thuc-c1640.html) | [c1641](https://loigiaihay.com/tieng-viet-4-chan-troi-sang-tao-c1641.html) | [c1642](https://loigiaihay.com/tieng-viet-4-canh-dieu-c1642.html) |
| 5 | [c1786](https://loigiaihay.com/tieng-viet-5-ket-noi-tri-thuc-c1786.html) | [c1787](https://loigiaihay.com/tieng-viet-5-chan-troi-sang-tao-c1787.html) | [c1788](https://loigiaihay.com/tieng-viet-5-canh-dieu-c1788.html) |

### 2.3 NGỮ VĂN (THCS, Lớp 6-9)

**Spider**: `scripts/loigiaihay_spider.py` + `scripts/crawl_ngu_van_full.py` (lớp 9 toàn văn)

| Lớp | KNTT | CTST | CD |
|---|---|---|---|
| 6 | [c630](https://loigiaihay.com/soan-bai-ngu-van-6-ket-noi-tri-thuc-voi-cuoc-song-c630.html) | [c1232](https://loigiaihay.com/soan-van-6-chan-troi-sang-tao-c1232.html) | [c1233](https://loigiaihay.com/soan-van-6-canh-dieu-c1233.html) |
| 7 | [c1278](https://loigiaihay.com/soan-van-7-ket-noi-tri-thuc-c1278.html) | [c1281](https://loigiaihay.com/soan-van-7-chan-troi-sang-tao-c1281.html) | [c1280](https://loigiaihay.com/soan-van-7-canh-dieu-c1280.html) |
| 8 | [c1381](https://loigiaihay.com/soan-van-8-ket-noi-tri-thuc-chi-tiet-c1381.html) | [c1383](https://loigiaihay.com/soan-van-8-chan-troi-sang-tao-chi-tiet-c1383.html) | [c1385](https://loigiaihay.com/soan-van-8-canh-dieu-chi-tiet-c1385.html) |
| 9 | [c1676](https://loigiaihay.com/soan-van-9-ket-noi-tri-thuc-c1676.html) | [c1678](https://loigiaihay.com/soan-van-9-chan-troi-sang-tao-c1678.html) | [c1677](https://loigiaihay.com/soan-van-9-canh-dieu-c1677.html) |

**Bổ sung từ Vietjack** (`scripts/vietjack_qa_spider.py`):

| Lớp 6 | Lớp 7 | Lớp 8 | Lớp 9 |
|---|---|---|---|
| [CD](https://vietjack.com/soan-van-6-cd/index.jsp) | [CD](https://vietjack.com/soan-van-7-cd/index.jsp) | [CD](https://vietjack.com/soan-van-8-cd/index.jsp) | [CD](https://vietjack.com/soan-van-9-cd/index.jsp) |
| [CT](https://vietjack.com/soan-van-6-ct/index.jsp) | [CT](https://vietjack.com/soan-van-7-ct/index.jsp) | [CT](https://vietjack.com/soan-van-8-ct/index.jsp) | [CT](https://vietjack.com/soan-van-9-ct/index.jsp) |
| [KN](https://vietjack.com/soan-van-6-kn/index.jsp) | [KN](https://vietjack.com/soan-van-7-kn/index.jsp) | [KN](https://vietjack.com/soan-van-8-kn/index.jsp) | [KN](https://vietjack.com/soan-van-9-kn/index.jsp) |

### 2.4 KHTN — Khoa học tự nhiên (Lớp 6-9)

**Spider**: `scripts/khtn_spider.py` | **Post-process**: `post_process_khtn.py` → `embed_khtn.py`

| Lớp | KNTT | CTST | CD |
|---|---|---|---|
| 6 | [c615](https://loigiaihay.com/khoa-hoc-tu-nhien-lop-6-ket-noi-tri-thuc-voi-cuoc-song-c615.html) | [c616](https://loigiaihay.com/khoa-hoc-tu-nhien-lop-6-chan-troi-sang-tao-c616.html) | [c610](https://loigiaihay.com/khoa-hoc-tu-nhien-lop-6-canh-dieu-c610.html) |
| 7 | [c856](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-7-ket-noi-tri-thuc-c856.html) | [c857](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-7-chan-troi-sang-tao-c857.html) | [c858](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-7-canh-dieu-c858.html) |
| 8 | [c1378](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-8-ket-noi-tri-thuc-c1378.html) | [c1379](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-8-chan-troi-sang-tao-c1379.html) | [c1380](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-8-canh-dieu-c1380.html) |
| 9 | [c1744](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-9-ket-noi-tri-thuc-c1744.html) | [c1736](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-9-chan-troi-sang-tao-c1736.html) | [c1733](https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-9-canh-dieu-c1733.html) |

### 2.5 LỊCH SỬ & ĐỊA LÝ (Lớp 6-9)

**Spider**: `scripts/soc_spider.py` | **Post-process**: `post_process_soc.py` → `embed_soc.py`

| Lớp | KNTT | CTST | CD |
|---|---|---|---|
| 6 | [c618](https://loigiaihay.com/lich-su-va-dia-li-lop-6-ket-noi-tri-thuc-c618.html) | [c617](https://loigiaihay.com/lich-su-va-dia-li-lop-6-chan-troi-sang-tao-c617.html) | [c620](https://loigiaihay.com/lich-su-va-dia-li-lop-6-canh-dieu-c620.html) |
| 7 | [c829](https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-7-ket-noi-tri-thuc-c829.html) | [c825](https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-7-chan-troi-sang-tao-c825.html) | [c845](https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-7-canh-dieu-c845.html) |
| 8 | [c1604](https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-8-ket-noi-tri-thuc-c1604.html) | [c1615](https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-8-chan-troi-sang-tao-c1615.html) | [c1605](https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-8-canh-dieu-c1605.html) |
| 9 | [c1827](https://loigiaihay.com/sgk-lich-su-va-dia-li-9-ket-noi-tri-thuc-c1827.html) | [c1829](https://loigiaihay.com/sgk-lich-su-va-dia-li-9-chan-troi-sang-tao-c1829.html) | [c1828](https://loigiaihay.com/sgk-lich-su-va-dia-ly-9-canh-dieu-c1828.html) |

### 2.6 GIÁO DỤC CÔNG DÂN (Lớp 6-9)

**Spider**: `scripts/soc_spider.py` (cùng spider)

| Lớp | KNTT | CTST | CD |
|---|---|---|---|
| 6 | [c654](https://loigiaihay.com/sgk-giao-duc-cong-dan-lop-6-ket-noi-tri-thuc-c654.html) | ❌ Thiếu | ❌ Thiếu |
| 7 | [c924](https://loigiaihay.com/sgk-giao-duc-cong-dan-7-ket-noi-tri-thuc-c924.html) | [c925](https://loigiaihay.com/sgk-giao-duc-cong-dan-7-chan-troi-sang-tao-c925.html) | [c926](https://loigiaihay.com/sgk-giao-duc-cong-dan-7-canh-dieu-c926.html) |
| 8 | [c1592](https://loigiaihay.com/giao-duc-cong-dan-8-ket-noi-tri-thuc-c1592.html) | [c1593](https://loigiaihay.com/giao-duc-cong-dan-8-chan-troi-sang-tao-c1593.html) | [c1594](https://loigiaihay.com/giao-duc-cong-dan-8-canh-dieu-c1594.html) |
| 9 | [c1818](https://loigiaihay.com/giao-duc-cong-dan-9-ket-noi-tri-thuc-c1818.html) | [c1819](https://loigiaihay.com/giao-duc-cong-dan-9-chan-troi-sang-tao-c1819.html) | [c1820](https://loigiaihay.com/giao-duc-cong-dan-9-canh-dieu-c1820.html) |

---

## 3. Neo4j Graph (Schema V2) — Ngữ Văn lớp 9

```
(Grade:9) → (Subject:Ngữ Văn) → (BookSeries:CTST/KNTT/CD)
                                        ↓ HAS_UNIT
                                    (Unit: tên bài)
                                   /       |       \
                      HAS_LITERATURE  HAS_LESSON  HAS_SUMMARY
                            ↓            ↓           ↓
                     LiteratureText  LessonGuide   Summary
```

**Stats**: 95 LiteratureText, 125 LessonGuide, 45 Summary, 261 Units

---

## 4. Pipeline xử lý

```bash
# 1. CRAWL
scrapy runspider scripts/math_spider.py -a start_grades=6,7,8,9

# 2. POST-PROCESS → PostgreSQL
python scripts/post_process_math.py

# 3. EMBED → Qdrant
python scripts/embed_math.py

# 4. (Văn only) Graph ingest → Neo4j
python scripts/ingest_neo4j_v2.py
```

---

## 5. Crawled Data Files

| File | Size | Content |
|---|---|---|
| `loigiaihay_full_1to9.jsonl` | 185 MB | Ngữ Văn/Tiếng Việt lớp 1-9 |
| `math_loigiaihay_*.jsonl` | 17 MB | Toán (lớp 1,3,4,5 chủ yếu) |
| `khtn_loigiaihay_*.jsonl` | 7.3 MB | KHTN lớp 6-8 |
| `soc_loigiaihay_*.jsonl` | 1 GB | Sử/Địa/GDCD (raw, cần filter) |
| `grade9_new/literature_text.jsonl` | 555 KB | Toàn văn tác phẩm lớp 9 |
| `grade9_new/lesson_guide.jsonl` | 2.2 MB | Soạn bài lớp 9 |
| `grade9_new/summary.jsonl` | 29 KB | Tóm tắt tác phẩm lớp 9 |
