# MASTER PLAN — RAG Edu Multi-Subject
## Từ hiện trạng (TV/NV lớp 1-9) → Sản phẩm RAG full môn cho PTalk

---

## Context nhanh

**Đã có:**
- 10,927 articles Tiếng Việt/Ngữ Văn (walkthrough.md)
- Pipeline: Scrapy → JSONL → PostProcess → PostgreSQL + Qdrant
- Classifier rule-based + LLM fallback
- 4 retrievers (SGKReading, LanguageConcept, WritingOutline, Curriculum)
- FastAPI /chat endpoint
- Server L40S, intfloat/multilingual-e5-large embedding

**Mục tiêu cuối:**
- RAG cho tất cả môn chính: TV/NV, Toán, KHTN (+Khoa học), Tiếng Anh, Sử/Địa, GDCD
- Lớp 1-9 × 3 bộ sách (Tiếng Anh có 5 bộ)
- Hỗ trợ voice-first PTalk bot

**Ước tính scope:** ~42,000 articles sau mở rộng (gấp 4x hiện tại)

---

## NGUYÊN TẮC TRONG SUỐT PLAN

### Nguyên tắc 1: Ship thứ hoàn chỉnh, không ship "gần xong"
Thà có Toán lớp 5 hoàn chỉnh chạy tốt còn hơn có Toán + KHTN + Anh lớp 1-9 nhưng chất lượng kém. Mỗi phase phải có deliverable test được end-to-end.

### Nguyên tắc 2: Validate rủi ro cao trước
LaTeX handling là rủi ro lớn nhất. Test nó ở phase 2 với data nhỏ trước khi invest crawl 4000 articles toán. Sub-subject detection cũng vậy.

### Nguyên tắc 3: Đo lường từ đầu
Mỗi phase phải có metric cụ thể. Không có metric = không biết xong chưa.

### Nguyên tắc 4: Giữ TV/NV hiện tại luôn hoạt động
Schema migration phải backward compatible. Không được làm vỡ những gì đang chạy.

---

## PHASE 0: Cleanup & Stabilize (3-5 ngày)
*Fix những gì đang hỏng TRƯỚC KHI mở rộng.*

### Deliverables
- [ ] Bug lớp 8 crawl fix xong → có data lớp 8 trong DB
- [ ] WritingOutlineRetriever fallback sang writing_samples
- [ ] THCS re-index v5 hoàn thành → verify queries lớp 6-9 pass
- [ ] OpenAI key setup HOẶC self-hosted LLM trên L40S (Qwen 2.5 14B)

### Tasks cụ thể

**Task 0.1: Debug crawler lớp 8**
```bash
# Chạy spider chỉ cho lớp 8 với verbose log
scrapy runspider loigiaihay_spider.py -a grades=8 -L DEBUG 2>&1 | tee debug_lop8.log
```

Khả năng cao: URL category c1321, c1322, c1323 có structure khác lớp 7/9. Cần xem raw HTML của các trang này, check CSS selector.

**Task 0.2: Fix WritingOutlineRetriever**
```python
# Trong src/retrieval/retrievers.py
class WritingOutlineRetriever:
    def retrieve(self, writing_type, grade):
        # Existing code: query kb_writing_outlines
        items = self._query_outlines(writing_type, grade)
        
        # NEW: Fallback sang writing_samples
        if not items:
            items = self._query_samples(writing_type, grade)
        
        return items
```

**Task 0.3: LLM setup**
Nếu chưa có OpenAI key:
```bash
# Deploy Qwen 2.5 14B Instruct lên L40S bằng vLLM
pip install vllm
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-14B-Instruct \
    --port 8000 \
    --tensor-parallel-size 1
```
→ Dùng làm "OpenAI-compatible" endpoint cho classifier + generation.

### Checkpoint Phase 0
- Tất cả 9 lớp TV/NV đều query được
- 100% queries trong test set hiện tại pass
- LLM endpoint (OpenAI hoặc local) sẵn sàng

**KHÔNG bắt đầu Phase 1 khi chưa đủ checkpoint này.**

---

## PHASE 1: Schema Migration — Sẵn sàng multi-subject (5-7 ngày)

### Mục tiêu
Chuyển schema từ "chỉ TV/NV" sang "multi-subject ready" **mà không làm vỡ TV/NV hiện tại**.

### Deliverables
- [ ] Schema mới với `subject` column ở mọi bảng
- [ ] Migration script chạy an toàn trên DB production
- [ ] Qdrant payloads thêm `subject` field
- [ ] Classifier thêm layer 1: subject detector
- [ ] TV/NV vẫn hoạt động 100% sau migration

### Tasks

**Task 1.1: Tạo migration SQL**

```sql
-- migration_v1_add_subject.sql

BEGIN;

-- Thêm subject column nếu chưa có
ALTER TABLE extracted_content 
    ADD COLUMN IF NOT EXISTS subject VARCHAR(30) DEFAULT 'tieng_viet_ngu_van';

ALTER TABLE kb_sgk_reading 
    ADD COLUMN IF NOT EXISTS subject VARCHAR(30) DEFAULT 'tieng_viet_ngu_van';

ALTER TABLE kb_language_concepts 
    ADD COLUMN IF NOT EXISTS subject VARCHAR(30) DEFAULT 'tieng_viet_ngu_van';

-- Tiểu học lớp 1-5: 'tieng_viet'
-- THCS 6-9: 'ngu_van'
-- Update để chính xác hơn:
UPDATE kb_sgk_reading SET subject='tieng_viet' WHERE lop BETWEEN 1 AND 5;
UPDATE kb_sgk_reading SET subject='ngu_van' WHERE lop BETWEEN 6 AND 9;

-- Index để query nhanh
CREATE INDEX IF NOT EXISTS idx_extracted_subject ON extracted_content(subject, lop);
CREATE INDEX IF NOT EXISTS idx_sgk_reading_subject ON kb_sgk_reading(subject, lop, bo_sach);

COMMIT;
```

**Task 1.2: Bảng mới cho các môn**

Đừng tạo hết 1 lần. Chỉ tạo bảng cho môn sắp crawl (Toán trong Phase 2):

```sql
-- migration_v2_add_math_tables.sql
CREATE TABLE IF NOT EXISTS kb_math_concepts (
    id BIGSERIAL PRIMARY KEY,
    extracted_content_id BIGINT REFERENCES extracted_content(id),
    
    ten_khai_niem VARCHAR(255) NOT NULL,
    lop INT NOT NULL CHECK (lop BETWEEN 1 AND 9),
    bo_sach VARCHAR(20),
    chu_de VARCHAR(100),
    
    dinh_nghia TEXT,
    cong_thuc_latex TEXT,
    cong_thuc_text TEXT,      -- Voice-friendly form
    
    kien_thuc_tien_quyet TEXT[],
    vi_du_minh_hoa JSONB,
    
    vector_id UUID UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_math_concepts_lookup ON kb_math_concepts(ten_khai_niem, lop);

CREATE TABLE IF NOT EXISTS kb_math_exercises (
    id BIGSERIAL PRIMARY KEY,
    extracted_content_id BIGINT REFERENCES extracted_content(id),
    
    lop INT NOT NULL CHECK (lop BETWEEN 1 AND 9),
    bo_sach VARCHAR(20),
    bai_so VARCHAR(20),
    tiet INT,
    trang INT,
    
    de_bai TEXT NOT NULL,
    co_hinh BOOLEAN DEFAULT FALSE,
    hinh_mo_ta TEXT,
    
    dang_bai VARCHAR(50),
    muc_do VARCHAR(20),
    
    loi_giai TEXT,
    buoc_giai JSONB,
    dap_so TEXT,
    
    khai_niem_lien_quan BIGINT[],
    
    vector_id UUID UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_math_exercises_lookup ON kb_math_exercises(lop, bo_sach, trang);
```

**Task 1.3: Qdrant payload migration**

```python
# scripts/migrate_qdrant_subject.py
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

# Đối với collection sgk_readings hiện tại:
# Bulk update payload thêm subject dựa trên lop
for point_batch in client.scroll("sgk_readings", limit=1000):
    for point in point_batch[0]:
        lop = point.payload.get('lop')
        subject = 'tieng_viet' if lop <= 5 else 'ngu_van'
        client.set_payload(
            collection_name="sgk_readings",
            payload={"subject": subject},
            points=[point.id]
        )
```

**Task 1.4: Subject classifier**

```python
# src/retrieval/subject_detector.py

SUBJECT_KEYWORDS = {
    "toan": [
        "cộng", "trừ", "nhân", "chia", "phân số", "hỗn số", "phần trăm",
        "tam giác", "hình thang", "hình tròn", "diện tích", "chu vi", "thể tích",
        "phương trình", "bất phương trình", "số thập phân", "số tự nhiên",
        "ước", "bội", "tỉ số", "căn bậc", "lũy thừa",
    ],
    "khtn": [
        "nguyên tử", "phân tử", "hóa trị", "liên kết", "axit", "bazơ", "muối",
        "phản ứng", "oxygen", "hydrogen", "quang hợp", "hô hấp", "tế bào",
        "gene", "di truyền", "vận tốc", "lực", "năng lượng", "điện", "từ trường",
        "âm thanh", "ánh sáng", "nhiệt độ", "dung dịch",
    ],
    "tieng_anh": [
        "english", "grammar", "vocabulary", "pronunciation", "tense",
        "present simple", "past", "future", "unit \\d+",
        "từ vựng anh", "ngữ pháp anh",
    ],
    "lich_su": [
        "triều đại", "cách mạng", "kháng chiến", "khởi nghĩa", "chiến tranh",
        "vua", "hoàng đế", "nhà \\w+", "thế kỉ", "năm \\d{3,4}",
        "độc lập", "giải phóng",
    ],
    "dia_li": [
        "khí hậu", "địa hình", "dân số", "châu", "đại dương", "khoáng sản",
        "đồng bằng", "cao nguyên", "kinh tế vùng", "công nghiệp", "nông nghiệp",
    ],
    "gdcd": [
        "đạo đức", "trung thực", "tôn trọng", "pháp luật", "quyền và nghĩa vụ",
        "nhân quyền", "công dân", "tiết kiệm",
    ],
}

def detect_subject(query: str, user_profile: dict = None) -> tuple[str, float]:
    """
    Return (subject, confidence).
    subject in: toan, khtn, tieng_anh, lich_su, dia_li, gdcd, 
                tieng_viet (lớp 1-5), ngu_van (lớp 6-9), unknown
    """
    q = query.lower()
    scores = {}
    
    for subj, keywords in SUBJECT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if re.search(kw, q):
                score += 1
        scores[subj] = score
    
    # TV/NV fallback dựa trên context (bài đọc, tác giả, tập làm văn)
    tv_nv_keywords = ["bài đọc", "tập làm văn", "văn mẫu", "bài thơ", 
                      "nhân vật", "tác giả", "phân tích", "soạn văn"]
    tv_nv_score = sum(1 for kw in tv_nv_keywords if kw in q)
    
    if user_profile and user_profile.get("lop"):
        scores["tieng_viet" if user_profile["lop"] <= 5 else "ngu_van"] = tv_nv_score
    
    # Pick highest
    max_subj = max(scores, key=scores.get)
    max_score = scores[max_subj]
    
    if max_score == 0:
        return "unknown", 0.0
    
    # Confidence: ratio giữa best và runner-up
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) > 1 and sorted_scores[1] > 0:
        confidence = sorted_scores[0] / (sorted_scores[0] + sorted_scores[1])
    else:
        confidence = 1.0
    
    return max_subj, confidence
```

**Task 1.5: Test classifier không làm hỏng TV/NV**

```python
# tests/test_subject_compat.py
TV_NV_QUERIES = [
    ("Đọc bài Lượm", "tieng_viet"),  # user lớp 2-5
    ("Phân tích bài Sóng của Xuân Quỳnh", "ngu_van"),
    ("Giúp em tả con mèo", "tieng_viet"),
    ("Từ ghép là gì lớp 4", "tieng_viet"),
]

for query, expected in TV_NV_QUERIES:
    subj, conf = detect_subject(query, user_profile={"lop": 4})
    assert subj == expected, f"FAIL: '{query}' → {subj}, expected {expected}"
```

### Checkpoint Phase 1
- Migration chạy trên staging DB không lỗi
- 50 queries TV/NV hiện tại vẫn pass
- Subject detector precision > 85% trên test set 100 câu
- Rollback script sẵn sàng nếu production có vấn đề

---

## PHASE 2: Toán lớp 5 Pilot (7-10 ngày)
*Validate toàn bộ pipeline mới với 1 lớp × 1 môn × 1 bộ sách trước khi scale.*

### Vì sao Toán lớp 5?
- Content đặc thù nhất (LaTeX, công thức, bước giải) → test được edge cases khó
- Lớp 5 có bài Hình tam giác, Hình thang → tốt để test LaTeX
- Demand cao (học sinh ôn thi vào 6)
- Vừa đủ nhỏ (~400 articles) để iterate nhanh

### Deliverables
- [ ] `preserve_mathjax()` function tested
- [ ] Math spider chạy được, crawl 400 bài Toán 5 KNTT
- [ ] PostProcess classify + extract công thức + bước giải
- [ ] Math retrievers (ConceptRetriever, ExerciseRetriever)
- [ ] 30 queries Toán lớp 5 → test pass
- [ ] Voice output test: TTS đọc được `cong_thuc_text`

### Tasks

**Task 2.1: LaTeX/MathJax preservation (CRITICAL)**

```python
# scripts/preserve_mathjax.py
from bs4 import BeautifulSoup
import re

def preserve_mathjax(html: str) -> str:
    """
    Convert MathJax elements to plain $...$ before trafilatura.
    Preserves formulas that would otherwise be lost.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Pattern 1: <span class="MathJax">...</span>
    for el in soup.select('span.MathJax, span.mjx-chtml'):
        # Prefer data-latex attribute if exists
        latex = el.get('data-latex')
        if not latex:
            # Fallback: check nested script
            script = el.find_next('script', type=re.compile(r'math/tex'))
            if script:
                latex = script.get_text()
            else:
                latex = el.get_text()
        el.replace_with(f" $${latex}$$ ")
    
    # Pattern 2: <script type="math/tex">LATEX</script>
    for script in soup.find_all('script', type=re.compile(r'math/tex')):
        latex = script.get_text()
        script.replace_with(f" $${latex}$$ ")
    
    # Pattern 3: images alt text (loigiaihay có thể render LaTeX thành image)
    for img in soup.select('img[alt]'):
        alt = img.get('alt', '')
        if '\\' in alt or '_' in alt or '^' in alt:  # Có vẻ là LaTeX
            img.replace_with(f" $${alt}$$ ")
    
    return str(soup)


def test_preserve_mathjax():
    """Unit test với sample HTML thật từ loigiaihay."""
    test_html = '''
    <p>Diện tích hình tam giác: 
    <span class="MathJax" data-latex="S = \\frac{1}{2} \\cdot a \\cdot h">S = ...</span>
    </p>
    '''
    result = preserve_mathjax(test_html)
    assert "$$S = \\frac{1}{2} \\cdot a \\cdot h$$" in result
    print("✅ LaTeX preservation works")

if __name__ == "__main__":
    test_preserve_mathjax()
```

**Test với data thật** (trước khi dùng cho 400 articles):
```bash
# Fetch 5 trang Toán lớp 5 về, chạy preserve_mathjax, verify bằng mắt
python scripts/test_latex_on_real_pages.py
```

**Task 2.2: LaTeX → Voice text converter**

```python
# src/utils/latex_to_speech.py

SYMBOL_MAP = {
    "+": "cộng", "-": "trừ", "×": "nhân", "÷": "chia", "=": "bằng",
    "<": "nhỏ hơn", ">": "lớn hơn", "≤": "nhỏ hơn hoặc bằng",
    "≥": "lớn hơn hoặc bằng", "≠": "khác",
    "²": "bình phương", "³": "lập phương",
    "π": "pi", "∞": "vô cực",
}

LATEX_COMMANDS = {
    r"\\frac\{([^{}]+)\}\{([^{}]+)\}": r"\1 chia \2",
    r"\\sqrt\{([^{}]+)\}": r"căn bậc hai của \1",
    r"\\cdot": " nhân ",
    r"\\times": " nhân ",
    r"\\div": " chia ",
    r"\\pm": " cộng hoặc trừ ",
}

def latex_to_speech(latex: str) -> str:
    """
    Convert LaTeX formula to Vietnamese voice-friendly text.
    Example: "S = \\frac{1}{2} \\cdot a \\cdot h"
          → "S bằng 1 chia 2 nhân a nhân h"
    """
    text = latex
    # Remove delimiters
    text = text.replace("$$", "").replace("$", "").strip()
    
    # Apply LaTeX command replacements
    for pattern, replacement in LATEX_COMMANDS.items():
        text = re.sub(pattern, replacement, text)
    
    # Symbol replacements
    for sym, word in SYMBOL_MAP.items():
        text = text.replace(sym, f" {word} ")
    
    # Clean up
    text = re.sub(r'\s+', ' ', text).strip()
    return text
```

**Task 2.3: Math spider**

```python
# scripts/math_spider.py  
# Tương tự loigiaihay_spider.py nhưng cho Toán

MATH_CATEGORIES_LOP5 = {
    "KNTT": "https://loigiaihay.com/sgk-toan-5-ket-noi-tri-thuc-c1728.html",
    "CTST": "...",  # TODO lookup
    "CD":   "...",
}

class MathSpider(LoigiaihaySpider):
    name = "loigiaihay_math"
    
    def parse_article(self, response):
        # TRƯỚC khi trafilatura, preserve MathJax
        preserved_html = preserve_mathjax(response.text)
        
        extracted = trafilatura.extract(
            preserved_html,
            include_formatting=True,  # Giữ cấu trúc
        )
        
        # Detect content type từ URL
        url = response.url
        if '/ly-thuyet-' in url:
            content_type = 'math_theory'
        elif '/giai-toan-' in url:
            content_type = 'math_exercise'
        elif '/vo-bai-tap-' in url or '-vbt-' in url:
            content_type = 'math_workbook'
        elif '/sbt-' in url:
            content_type = 'math_sbt'
        elif '/de-kiem-tra-' in url:
            content_type = 'math_test'
        else:
            content_type = 'math_unknown'
        
        yield {
            "url": url,
            "source_domain": "loigiaihay.com",
            "subject": "toan",
            "content_type": content_type,
            "title": response.css("title::text").get().strip(),
            "content": extracted,
            "has_latex": "$$" in extracted,
            "has_image_ref": bool(re.search(r'[Hh]ình \d+', extracted)),
            # ... metadata khác
        }
```

**Task 2.4: Math post-processor**

```python
# scripts/post_process_math.py

def process_theory_page(item):
    """Xử lý trang lý thuyết: extract định nghĩa + công thức."""
    content = item['content']
    
    # Parse theo heading
    sections = split_by_headings(content)
    
    # Detect công thức
    latex_formulas = re.findall(r'\$\$(.+?)\$\$', content)
    
    # Detect tên khái niệm từ title
    title = item['title']
    concept_name = extract_concept_name(title)  # "Diện tích hình tam giác"
    
    return {
        "ten_khai_niem": concept_name,
        "dinh_nghia": sections.get('dinh_nghia', content[:500]),
        "cong_thuc_latex": latex_formulas[0] if latex_formulas else None,
        "cong_thuc_text": latex_to_speech(latex_formulas[0]) if latex_formulas else None,
        # ...
    }


def process_exercise_page(item):
    """Xử lý trang giải bài tập."""
    content = item['content']
    
    # Detect đề bài + lời giải (loigiaihay thường có pattern "Bài X: ... Lời giải:")
    exercises = split_exercises(content)
    
    results = []
    for ex in exercises:
        results.append({
            "de_bai": ex['de'],
            "loi_giai": ex['giai'],
            "buoc_giai": extract_steps(ex['giai']),
            "dap_so": extract_answer(ex['giai']),
            "co_hinh": '[Hình' in ex['de'] or 'hình vẽ' in ex['de'].lower(),
        })
    return results
```

**Task 2.5: Math retrievers**

```python
# src/retrieval/math_retrievers.py

class MathConceptRetriever:
    """Lookup công thức/định nghĩa toán."""
    
    def __init__(self, pg_conn, qdrant, embed_fn):
        self.conn = pg_conn
        self.qdrant = qdrant
        self.embed = embed_fn
    
    def exact_lookup(self, concept_name: str, grade: int = None):
        """User hỏi đúng tên khái niệm."""
        query = """
            SELECT * FROM kb_math_concepts
            WHERE ten_khai_niem ILIKE %s
        """
        params = [f"%{concept_name}%"]
        if grade:
            query += " AND lop <= %s"
            params.append(grade)
        query += " ORDER BY lop LIMIT 3"
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    
    def semantic_search(self, query: str, grade: int = None, top_k: int = 3):
        """Fuzzy search khi không biết tên chính xác."""
        query_vec = self.embed(query)
        
        filter_conditions = [{"key": "subject", "match": {"value": "toan"}}]
        if grade:
            filter_conditions.append({
                "key": "lop", "range": {"lte": grade}
            })
        
        results = self.qdrant.search(
            collection_name="math_concepts",
            query_vector=query_vec,
            query_filter={"must": filter_conditions},
            limit=top_k,
        )
        # Hydrate từ PostgreSQL
        return self._hydrate(results)


class MathExerciseRetriever:
    """Tìm bài tập tương tự hoặc bài cụ thể."""
    
    def exact_by_page(self, grade: int, book: str, page: int, bai_so: str = None):
        """Query: 'bài 5 trang 92 toán 5 KNTT'."""
        query = """
            SELECT * FROM kb_math_exercises
            WHERE lop = %s AND bo_sach = %s AND trang = %s
        """
        params = [grade, book, page]
        if bai_so:
            query += " AND bai_so = %s"
            params.append(bai_so)
        # ...
    
    def similar_exercise(self, query: str, grade: int, dang_bai: str = None):
        """Tìm bài tương tự. Query có thể là đề bài do user cung cấp."""
        # Vector search với filter dang_bai nếu detect được
```

**Task 2.6: Integration test Toán lớp 5**

```python
# tests/test_math_lop5.py
MATH_TEST_QUERIES = [
    # Concept queries
    ("Công thức tính diện tích hình tam giác", "math_concepts", ["tam giác"]),
    ("Diện tích hình thang tính như nào", "math_concepts", ["hình thang"]),
    ("Phân số thập phân là gì", "math_concepts", ["phân số thập phân"]),
    
    # Exercise queries
    ("Bài 1 trang 92 toán 5 KNTT", "math_exercises", ["bài 1"]),
    ("Giải bài tập về hỗn số", "math_exercises", ["hỗn số"]),
    
    # Voice-specific queries
    ("Cho em công thức tính diện tích hình tròn", "math_concepts", 
     # Check response có cong_thuc_text, không chỉ LaTeX
    ),
    
    # Edge: bài cần hình
    ("Quan sát hình vẽ rồi tính diện tích", None,  
     # Expect: response note về hình hoặc redirect
    ),
]

def test_all():
    for query, expected_collection, expected_keywords in MATH_TEST_QUERIES:
        resp = requests.post("http://localhost:8888/chat", json={
            "message": query,
            "metadata": {"lop": 5, "bo_sach": "KNTT"}
        })
        result = resp.json()
        
        # Verify collection
        if expected_collection:
            sources = result.get("sources", [])
            assert any(s["collection"] == expected_collection for s in sources), \
                f"Wrong collection for: {query}"
        
        # Verify content
        if expected_keywords:
            for kw in expected_keywords:
                assert kw in result["answer"].lower(), \
                    f"Missing keyword '{kw}' for: {query}"
```

### Checkpoint Phase 2
- ≥ 90% LaTeX được preserve đúng trên 50 sample pages
- `latex_to_speech` converter pass unit tests
- 400 articles Toán 5 KNTT indexed
- 25/30 queries test pass (83% minimum)
- Voice output của công thức đọc tự nhiên (human QA)

**Đây là checkpoint QUYẾT ĐỊNH nhất.** Nếu LaTeX fail → mọi thứ Toán/KHTN sau đều fail. Đừng qua phase 3 khi chưa OK.

---

## PHASE 3: Mở rộng Toán 1-9 (5-7 ngày)
*Sau khi validate với lớp 5, scale ra các lớp còn lại.*

### Deliverables
- [ ] Crawl Toán lớp 1-4, 6-9 × 3 bộ sách (~4000 articles)
- [ ] Post-process + index vào Qdrant
- [ ] 50 queries Toán cross-grade pass

### Lưu ý scale
- 27 categories × ~150 articles trung bình × 3s delay = ~3.5 giờ crawl
- Nên chia batch: crawl 1 lớp rồi post-process, test, rồi lớp tiếp
- Monitor HTTP errors, respect rate limit

### Classifier updates
```python
# Thêm patterns lớp-specific nếu cần:
MATH_GRADE_HINTS = {
    "lớp 1-2": ["đếm", "cộng trong phạm vi 10", "hình vuông"],
    "lớp 3-5": ["nhân", "chia", "phân số", "số thập phân", "diện tích"],
    "lớp 6-7": ["số nguyên", "phân số âm", "hệ tọa độ", "hàm số"],
    "lớp 8-9": ["phương trình", "bất phương trình", "căn bậc", "hình học không gian"],
}
```

### Checkpoint Phase 3
- Toán 1-9 coverage ≥ 80%
- Retrieval recall@3 ≥ 80% trên 100 queries eval
- Cross-grade isolation: query lớp 3 không trả bài lớp 9

---

## PHASE 4: KHTN + Khoa học (7-10 ngày)

### Deliverables
- [ ] Sub-subject detector (lý/hóa/sinh) accuracy > 85%
- [ ] KHTN 6-9 crawl (~1200 articles)
- [ ] Khoa học 4-5 crawl (~500 articles)
- [ ] Schema `kb_science_topics` với `sub_subject` field

### Tasks đặc thù

**Task 4.1: Sub-subject detector**
```python
# Dựa trên phần khảo sát, có 3 nhánh trong KHTN
# Đã có SUB_SUBJECT_KEYWORDS trong file khảo sát

def detect_khtn_sub_subject(title, content):
    # Ưu tiên chương (từ SGK)
    if "chương" in title.lower():
        if any(kw in title.lower() for kw in ["nguyên tử", "phân tử", "phản ứng"]):
            return "hoa_hoc"
        elif any(kw in title.lower() for kw in ["tốc độ", "âm", "ánh sáng", "từ"]):
            return "vat_li"
        elif any(kw in title.lower() for kw in ["tế bào", "sinh", "trao đổi chất"]):
            return "sinh_hoc"
    
    # Fallback: weighted keyword count trong content
    # ...
```

**Task 4.2: Phản ứng hóa học preservation**

H₂O, CO₂ hay bị corrupt khi crawl. Cần preserve:
```python
def preserve_chemistry(html):
    # Subscript: H<sub>2</sub>O → H₂O (Unicode)
    soup = BeautifulSoup(html, 'html.parser')
    SUB = {"0":"₀","1":"₁","2":"₂","3":"₃","4":"₄","5":"₅","6":"₆","7":"₇","8":"₈","9":"₉"}
    for sub in soup.find_all('sub'):
        digit = sub.get_text().strip()
        if digit in SUB:
            sub.replace_with(SUB[digit])
    # Similar for superscript (charges): Na<sup>+</sup> → Na⁺
    return str(soup)
```

**Task 4.3: Hình thí nghiệm**

KHTN rất nhiều `Hình 2.1`, `Bảng 2.2`. Implement flag:
```python
def flag_image_dependency(content):
    # Count references
    img_refs = len(re.findall(r'[Hh]ình \d+\.\d+', content))
    tab_refs = len(re.findall(r'[Bb]ảng \d+\.\d+', content))
    
    # Nếu > 2 references → content phụ thuộc visual → downweight
    return img_refs + tab_refs > 2
```

### Checkpoint Phase 4
- Sub-subject accuracy ≥ 85%
- KHTN queries pass rate ≥ 75% (thấp hơn Toán vì hình)
- Hóa học có reference đúng: `H₂SO₄`, không phải `H2SO4` hoặc `HSO4`

---

## PHASE 5: Tiếng Anh (7-10 ngày)

### Deliverables
- [ ] 3 bảng: `kb_english_vocabulary`, `kb_english_grammar`, `kb_english_sections`
- [ ] Crawl Tiếng Anh 3-9 × 2-3 bộ sách phổ biến nhất (~4000-5000 articles)
- [ ] Bilingual query handling (Việt + Anh trong 1 câu)

### Decision: crawl bộ nào?

Không nên crawl cả 5 bộ. Ưu tiên:
1. **Global Success** (KNTT) — phổ biến nhất
2. **Friends Plus / Friends Global** (CTST)
3. **iLearn Smart World** (CD)

Bỏ Right On!, English Discovery, Bright trong phase này. Add sau nếu demand.

### Tasks đặc thù

**Task 5.1: Unit structure extractor**

Tiếng Anh có ~10 sections per unit. URL pattern:
```
/getting-started-unit-1-*          → section_type='getting_started'
/a-closer-look-1-unit-1-*          → 'closer_look_1'
/a-closer-look-2-unit-1-*          → 'closer_look_2'
/communication-unit-1-*            → 'communication'
/skills-1-unit-1-*                 → 'skills_1'
/skills-2-unit-1-*                 → 'skills_2'
/looking-back-unit-1-*             → 'looking_back'
/project-unit-1-*                  → 'project'
/vocabulary-unit-1-*               → 'vocabulary'
/grammar-unit-1-*                  → 'grammar'
/pronunciation-unit-1-*            → 'pronunciation'
```

**Task 5.2: Vocabulary extraction**

Trang vocabulary thường có dạng:
```
school /skuːl/ (n): trường học
Example: I go to school every day.
```

Parse structured:
```python
VOCAB_PATTERN = re.compile(
    r'(\w+(?:\s\w+)?)\s*(/[^/]+/)?\s*\((\w+)\)[:\-]\s*(.+?)(?=\n[\w/]|\Z)',
    re.DOTALL
)

def extract_vocab(text):
    matches = VOCAB_PATTERN.findall(text)
    return [
        {"tu": m[0], "phien_am": m[1], "loai_tu": m[2], "nghia": m[3].strip()}
        for m in matches
    ]
```

### Checkpoint Phase 5
- Vocabulary extraction precision ≥ 80%
- Grammar queries retrieve đúng structure
- Bilingual queries work (nửa Việt nửa Anh)

---

## PHASE 6: Sử/Địa + GDCD (5-7 ngày)

### Deliverables
- [ ] Bảng `kb_history_events`, `kb_geography_regions`, `kb_ethics_content`
- [ ] Disambiguation logic cho sự kiện trùng tên (Bạch Đằng!)
- [ ] Crawl LS-ĐL 6-9 (~1500 articles), GDCD 6-9 (~400), Đạo đức 1-5 (~200)

### Tasks đặc thù

**Task 6.1: Event disambiguation**

```python
def disambiguate_historical_event(event_name, user_grade):
    """
    'Trận Bạch Đằng' → 3 trận (938, 981, 1288)
    Use user_grade để chọn đúng.
    """
    # Query all events with that name
    candidates = db.query("""
        SELECT * FROM kb_history_events 
        WHERE ten_su_kien ILIKE %s
        ORDER BY lop
    """, [f"%{event_name}%"])
    
    if len(candidates) == 1:
        return candidates
    
    # Filter theo lớp user
    matching = [c for c in candidates if c['lop'] == user_grade]
    if matching:
        return matching
    
    # Nếu không có lớp match → trả tất cả với note
    return candidates  # LLM sẽ disambiguate trong response
```

**Task 6.2: LS-ĐL split**

LS và ĐL chung 1 cuốn nhưng nội dung tách. Detect từ chương/bài:
```python
def detect_ls_or_dl(title, content):
    if re.search(r'chương.*lịch sử|triều đại|chiến tranh', title.lower()):
        return 'lich_su'
    elif re.search(r'chương.*địa lí|khí hậu|đồng bằng', title.lower()):
        return 'dia_li'
    # Fallback to keyword count
    # ...
```

### Checkpoint Phase 6
- Event disambiguation: 5 test queries trùng tên → trả đúng event theo lớp
- LS-ĐL split accuracy > 90%

---

## PHASE 7: Eval Set & A/B Test (5-7 ngày)

### Deliverables
- [ ] Eval set 300 câu với ground truth
- [ ] A/B test framework
- [ ] Metrics dashboard
- [ ] Production readiness report

### Tasks

**Task 7.1: Build eval set 300 câu**

Phân bổ theo khảo sát:
- TV/NV: 80 (đã có baseline)
- Toán: 80
- KHTN: 50
- Tiếng Anh: 40
- Sử/Địa: 30
- GDCD: 20

**Cách collect**:
1. **Real queries** (100 câu): ghi âm trẻ em thật, transcribe
2. **Teacher-written** (100 câu): thuê giáo viên viết câu hỏi học sinh hay hỏi
3. **Synthetic** (100 câu): LLM tạo dựa trên SGK, review bởi người

**Format** (CSV hoặc JSON):
```json
{
  "id": "eval_001",
  "query": "Công thức tính diện tích hình tam giác là gì?",
  "expected_subject": "toan",
  "expected_intent": "explain_concept",
  "expected_keywords": ["diện tích", "tam giác", "đáy", "chiều cao"],
  "expected_kb_ids": [142, 156],  # IDs trong DB
  "ideal_answer": "Diện tích hình tam giác bằng một nửa đáy nhân chiều cao...",
  "grade_target": 5,
  "difficulty": "easy",
  "source": "teacher_written"
}
```

**Task 7.2: Metrics script**

```python
# scripts/run_eval.py
def run_full_eval(eval_set, api_url):
    results = {"subject_acc": 0, "recall@3": 0, "faithfulness": 0}
    
    for case in eval_set:
        resp = requests.post(api_url, json={"message": case["query"]}).json()
        
        # Subject accuracy
        if resp["detected_subject"] == case["expected_subject"]:
            results["subject_acc"] += 1
        
        # Recall@3
        retrieved_ids = [s["id"] for s in resp["sources"][:3]]
        if any(eid in retrieved_ids for eid in case["expected_kb_ids"]):
            results["recall@3"] += 1
        
        # Faithfulness (LLM judge)
        judge_prompt = f"""
        Question: {case['query']}
        Ideal answer: {case['ideal_answer']}
        Generated answer: {resp['answer']}
        
        Rate 1-5: Does generated answer contain correct facts from ideal?
        """
        faith_score = call_judge_llm(judge_prompt)
        results["faithfulness"] += faith_score / 5
    
    # Normalize
    n = len(eval_set)
    return {k: v/n for k, v in results.items()}
```

**Task 7.3: A/B test RAG vs baseline**

QUAN TRỌNG — đừng skip:
```python
# A: Chỉ LLM (Claude/GPT/Qwen) + system prompt, no RAG
# B: Full RAG pipeline

# Run same 300 queries qua cả 2
# Blind review bởi 2 giáo viên: chọn câu trả lời tốt hơn

# Phân tích theo môn:
# - Nếu RAG thắng >70% ở Toán → RAG có giá trị
# - Nếu RAG thua <50% ở Văn → có lẽ Văn không cần RAG, dùng LLM thuần
```

### Checkpoint Phase 7 (FINAL)
- Subject routing accuracy ≥ 90%
- Recall@3 theo môn:
  - TV/NV ≥ 80%
  - Toán ≥ 75%
  - KHTN ≥ 70%
  - Anh ≥ 75%
  - Sử/Địa ≥ 75%
- Faithfulness score ≥ 0.80
- Human evaluation ≥ 4.0/5
- A/B test: RAG thắng ≥ 60% overall

---

## PHASE 8: Production Hardening (3-5 ngày)

### Deliverables
- [ ] Monitoring dashboard (Grafana hoặc tự build)
- [ ] Error handling + graceful degradation
- [ ] Rate limiting
- [ ] Caching layer (Redis - bạn đã có)
- [ ] Documentation

### Tasks cụ thể

**Task 8.1: Fallback chain**

```python
def chat_endpoint(query, user_profile):
    try:
        # Path 1: Full RAG
        subject, conf = detect_subject(query, user_profile)
        if conf < 0.5:
            # Fallback to LLM-only
            return llm_only_response(query, user_profile)
        
        items = route_to_retriever(subject)(query, user_profile)
        if not items:
            # No retrieval → LLM tự trả lời + note "không tìm thấy"
            return llm_only_response(query, user_profile)
        
        return generate_with_context(query, items, user_profile)
        
    except Exception as e:
        logger.error(f"RAG failed: {e}")
        # Ultimate fallback
        return llm_only_response(query, user_profile)
```

**Task 8.2: Caching**

```python
# Cache retrievals - same query → same result trong 1 giờ
cache_key = f"rag:{hash(query)}:{user_profile['lop']}:{user_profile['bo_sach']}"
cached = redis.get(cache_key)
if cached:
    return json.loads(cached)
# ... retrieve ...
redis.setex(cache_key, 3600, json.dumps(result))
```

**Task 8.3: Monitoring**

Track per request:
- Latency (P50, P95, P99)
- Subject detected
- Retrieval count
- LLM tokens used
- Error rate
- User feedback (thumbs up/down)

---

## TIMELINE TỔNG

```
┌─────────────┬──────────────────────────────────────┬──────────┐
│ Phase       │ Deliverable                          │ Duration │
├─────────────┼──────────────────────────────────────┼──────────┤
│ 0. Cleanup  │ Fix bugs, LLM ready                  │ 3-5 d    │
│ 1. Schema   │ Multi-subject ready, TV/NV intact    │ 5-7 d    │
│ 2. Toán L5  │ Pilot validate LaTeX pipeline        │ 7-10 d   │
│ 3. Toán 1-9 │ Scale Toán all grades                │ 5-7 d    │
│ 4. KHTN     │ Sub-subject detection, chemistry     │ 7-10 d   │
│ 5. Anh      │ 3 bộ sách, bilingual                 │ 7-10 d   │
│ 6. Sử/Địa   │ Disambiguation, event-centric        │ 5-7 d    │
│ 7. Eval/AB  │ 300-query eval, measure real impact  │ 5-7 d    │
│ 8. Prod     │ Hardening, monitoring, caching       │ 3-5 d    │
├─────────────┼──────────────────────────────────────┼──────────┤
│ TOTAL                                              │ 47-68 d  │
│                                                    │ ~9-14 tuần│
└────────────────────────────────────────────────────┴──────────┘
```

---

## RỦI RO & MITIGATION

| Rủi ro | Phase | Mitigation |
|---|---|---|
| LaTeX preserve fail | 2 | Test trên 50 pages trước khi scale. Nếu fail → Playwright thay Scrapy |
| Crawler bị block | 3-6 | Rotate UA, respect robots.txt, monitor HTTP 429 |
| Sub-subject mis-detect | 4 | Manual label 200 KHTN articles, train classifier nếu rule không đủ |
| Embedding không hiểu LaTeX | 2-4 | Always lưu `cong_thuc_text` đi kèm để embed text, LaTeX chỉ để hiển thị |
| Eval set bias | 7 | Mix real + teacher + synthetic; review bởi 2-3 giáo viên |
| Production latency cao | 8 | Cache, smaller LLM for classification, pre-compute embeddings |
| Schema migration break prod | 1 | Staging test kỹ, migration script idempotent, có rollback |

---

## KHI NÀO CÓ THỂ BẮT ĐẦU VOICE INTEGRATION?

Bạn đã có pipeline voice (TTS/STT). Có thể integrate song song:

- **Sau Phase 2** (Toán lớp 5 pilot): test voice với công thức toán - validate `cong_thuc_text` approach
- **Sau Phase 3** (Toán đầy đủ): soft launch voice cho 1 nhóm user test
- **Sau Phase 7** (Full eval): production launch voice

Đừng đợi hết 8 phase mới integrate voice — sẽ miss nhiều insights.

---

## GỢI Ý PRIORITIZATION NẾU THIẾU THỜI GIAN

**Nếu chỉ có 1 tháng**: làm Phase 0 + 1 + 2 (Toán lớp 5) + 7 (eval nhỏ). Đó là MVP validate được market fit trước khi invest thêm.

**Nếu có 2 tháng**: + Phase 3 (Toán 1-9) + Phase 5 (Anh lớp 6-9 only). Toán + Anh là 2 môn demand cao nhất cho học sinh.

**Nếu có 3+ tháng**: full plan, bao gồm KHTN và Sử/Địa.

---

## CHECKLIST BẮT ĐẦU NGAY

Trước khi code Phase 0, confirm các điều sau:

- [ ] LLM endpoint sẵn sàng (OpenAI key hoặc Qwen 2.5 trên L40S)
- [ ] Staging PostgreSQL + Qdrant riêng với production (tránh ship bug ra prod)
- [ ] Backup DB production (đề phòng migration fail)
- [ ] Agreed KPI với stakeholder: cái gì là "done" cho mỗi phase
- [ ] Người review output: ít nhất 1 giáo viên tiểu học + 1 THCS để QA

Nếu thiếu 1 trong các mục trên → fix trước, không bắt đầu Phase 0.
