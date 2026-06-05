# Khảo sát đặc thù từng môn - Dựa trên research thực tế loigiaihay.com
## Chuẩn bị cho RAG bot PTalk multi-subject

> **Nguyên tắc**: Mỗi môn có cách tổ chức kiến thức, cách học sinh đặt câu hỏi, cách cần retrieve rất khác nhau. Không thể dùng 1 schema chung.

---

## 1. TOÁN (Tiểu học 1-5 + THCS 6-9)

### Đặc thù content trên loigiaihay

Có **5 loại trang khác nhau** cho mỗi bài học:

| Loại trang | URL pattern | Content | Vai trò |
|---|---|---|---|
| **Lý thuyết** | `/ly-thuyet-*-a{id}.html` | Định nghĩa + công thức + ví dụ minh họa | Giải thích khái niệm |
| **Giải SGK** | `/giai-toan-lop-N-bai-X-*-a{id}.html` | Tất cả bài tập SGK + lời giải chi tiết | Làm bài tập trong SGK |
| **Vở bài tập (VBT)** | `/bai-X-*-tiet-T-trang-P-vo-bai-tap-*-a{id}` | Bài tập bổ sung theo tiết | Luyện tập thêm |
| **SBT** | `/sbt-toan-*` | Sách bài tập (nâng cao) | Học sinh giỏi |
| **Đề kiểm tra** | `/de-kiem-tra-*` | Đề thi + đáp án | Ôn thi |

### Cấu trúc kiến thức Toán

Toán tổ chức theo **cây 4 tầng**:
```
Lớp → Tập → Chủ đề → Bài
        │
        └─ Mỗi bài có nhiều tiết (lớp 5 thường 4 tiết/bài)
```

Ví dụ thực tế từ Toán 5 KNTT:
```
Lớp 5 / Tập 1
├── Chủ đề 1: Ôn tập và bổ sung (Bài 1-9)
├── Chủ đề 2: Số thập phân (Bài 10-14)
├── Chủ đề 3: Các phép tính với số thập phân
├── Chủ đề 4: Tỉ số phần trăm
├── Chủ đề 5: Một số hình phẳng (Bài 25 Hình tam giác → Bài 29)
└── Chủ đề 6: Ôn tập học kì 1
```

### 3 dạng kiến thức cần tách biệt

1. **Khái niệm + công thức** (không đổi theo bài tập):
   - "Diện tích hình tam giác = (đáy × chiều cao) / 2"
   - Cần: lookup nhanh, không cần vector khi đã biết tên công thức

2. **Bài tập cụ thể + lời giải** (mỗi bài có đề riêng):
   - "Bài 1 trang 92: Mỗi đồ vật dưới đây có dạng hình tam giác gì?"
   - Cần: link đến lý thuyết liên quan, có bước giải

3. **Bài tập tương tự** (retrieve để gợi ý):
   - Học sinh hỏi "làm giúp bài này" + chụp đề → tìm bài tương tự trong DB

### Vấn đề lớn với crawler hiện tại

**LaTeX bị strip!** Trafilatura không hiểu MathJax. Ví dụ:
- HTML gốc: `<span class="MathJax">S = \frac{1}{2} \cdot a \cdot h</span>`
- Sau trafilatura: `S = ` (mất công thức!)

**Hình vẽ quan trọng nhưng không crawl được**:
- "Quan sát Hình 2.1..." → không có hình → context vô nghĩa
- Bài Toán hình học: đề tham chiếu hình → mất hình = mất đề

### Schema đề xuất cho Toán

```sql
-- Table 1: Khái niệm/công thức (đơn vị kiến thức độc lập)
CREATE TABLE kb_math_concepts (
    id BIGSERIAL PRIMARY KEY,
    ten_khai_niem VARCHAR(255),           -- "Diện tích hình tam giác"
    lop INT, bo_sach VARCHAR(10),
    chu_de VARCHAR(100),                   -- "Hình học phẳng"
    
    dinh_nghia TEXT,                       -- Định nghĩa text
    cong_thuc_latex TEXT,                  -- Giữ LaTeX gốc
    cong_thuc_text TEXT,                   -- "S bằng đáy nhân chiều cao chia 2" (cho voice)
    
    kien_thuc_tien_quyet TEXT[],           -- ["đường cao", "đáy"]
    vi_du_minh_hoa JSONB,                  -- [{de, giai}]
    
    vector_id UUID
);

-- Table 2: Bài tập cụ thể (có đề, có vị trí trong sách)
CREATE TABLE kb_math_exercises (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(10),
    bai_so VARCHAR(20),                    -- "Bài 25"
    tiet INT,                              -- Tiết mấy trong bài
    trang INT,
    
    de_bai TEXT,                           -- Đề bài (có thể có reference hình)
    co_hinh BOOLEAN DEFAULT FALSE,         -- Flag: đề bài cần hình
    hinh_mo_ta TEXT,                       -- Mô tả hình bằng text nếu được
    
    dang_bai VARCHAR(50),                  -- "tinh_dien_tich", "tim_x", "bai_toan_co_loi_van"
    muc_do VARCHAR(20),                    -- "co_ban", "van_dung", "nang_cao"
    
    loi_giai TEXT,                         -- Full solution
    buoc_giai JSONB,                       -- [{buoc: 1, noi_dung: "..."}]
    dap_so TEXT,
    
    khai_niem_lien_quan INT[],             -- FK đến kb_math_concepts
    
    vector_id UUID
);
```

### Retrieval strategy cho Toán

```
Query "Công thức tính diện tích hình tam giác"
  → SQL exact: SELECT * FROM kb_math_concepts WHERE ten_khai_niem ILIKE '%tam giác%'
  → Trả về công thức + định nghĩa

Query "Giải bài 1 trang 92 toán 5 KNTT"  
  → SQL exact: WHERE lop=5 AND trang=92 AND bai_so='1'
  → Trả về đề + lời giải

Query "Làm giúp em bài tính diện tích tam giác có đáy 8, cao 5"
  → Classify: user có đề → cần lookup concept + tìm bài tương tự
  → Vector search trong kb_math_exercises với filter dang_bai='tinh_dien_tich'
  → Join với concept để hướng dẫn
```

---

## 2. KHTN (Khoa học tự nhiên 6-9) + Khoa học (lớp 4-5)

### Đặc thù cực kỳ quan trọng

**KHTN là môn TÍCH HỢP** Vật lý + Hóa + Sinh trong 1 cuốn sách. Học sinh hỏi "thí nghiệm X" — phải biết X thuộc nhánh nào.

Ví dụ từ KHTN 7 KNTT:
```
Chương I:   Nguyên tử (Hóa học)
Chương II:  Phân tử - Liên kết hóa học (Hóa)
Chương III: Tốc độ (Vật lý)
Chương IV:  Âm thanh (Vật lý)
Chương V:   Ánh sáng (Vật lý)
Chương VI:  Từ (Vật lý)
Chương VII: Trao đổi chất (Sinh)
Chương VIII: Cảm ứng ở sinh vật (Sinh)
Chương IX-X: Sinh trưởng, sinh sản (Sinh)
```

### Cấu trúc 1 bài KHTN điển hình

```
Bài 2: Nguyên tử
├── Quan niệm ban đầu (lịch sử)
├── Mô hình nguyên tử Rutherford-Bohr (lý thuyết)
│   └── Hình 2.1, Hình 2.2, Hình 2.3 (HÌNH QUAN TRỌNG)
├── Cấu tạo nguyên tử
│   └── Bảng 2.1: khối lượng các hạt
├── Câu hỏi vận dụng (?)
└── Bài tập
```

### Đặc thù về loại kiến thức

1. **Lý thuyết/khái niệm** — giống Toán
2. **Định luật/nguyên lý** — câu chữ cố định, không đổi
3. **Mô tả thí nghiệm** — nhiều bước, có hình
4. **Phản ứng hóa học** — có công thức đặc biệt (H₂O, NaCl)
5. **Công thức Vật lý** — có LaTeX

### Vấn đề đặc thù

- **Ký hiệu hóa học bị mất**: `H₂SO₄` → `H2SO4` (vẫn OK) nhưng `6,022 × 10²³` → `6,022 x 1023` (sai!)
- **Bảng tuần hoàn**: nếu crawler không xử lý table → mất hết
- **Tên khoa học tiếng Anh**: "oxygen", "carbon" xen tiếng Việt → embedding phải handle bilingual

### Schema đề xuất cho KHTN

```sql
CREATE TABLE kb_science_topics (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(10),
    chuong VARCHAR(100),                   -- "Chương I. Nguyên tử"
    bai_so VARCHAR(20),                    -- "Bài 2"
    ten_bai VARCHAR(255),
    
    sub_subject VARCHAR(20),               -- 'vat_li', 'hoa_hoc', 'sinh_hoc' (AUTO-DETECT)
    loai_kien_thuc VARCHAR(30),            -- 'khai_niem', 'dinh_luat', 'thi_nghiem', 'phan_ung'
    
    noi_dung TEXT,
    cong_thuc_latex TEXT,                  -- Cho Vật lý
    phuong_trinh_hoa_hoc TEXT,             -- Cho Hóa: "2H₂ + O₂ → 2H₂O"
    
    co_hinh BOOLEAN,
    co_thi_nghiem BOOLEAN,
    mo_ta_thi_nghiem JSONB,                -- {dung_cu, cach_tien_hanh, hien_tuong, ket_luan}
    
    vector_id UUID
);
```

### Sub-subject auto-detection (rule-based)

```python
SUB_SUBJECT_KEYWORDS = {
    "hoa_hoc": ["nguyên tử", "phân tử", "hóa trị", "liên kết", "axit", "bazơ", 
                "muối", "phản ứng", "oxi", "hydrogen", "H2O", "NaCl"],
    "vat_li": ["tốc độ", "vận tốc", "âm thanh", "ánh sáng", "từ trường", "lực",
               "năng lượng", "điện", "nhiệt độ"],
    "sinh_hoc": ["tế bào", "sinh trưởng", "phát triển", "quang hợp", "hô hấp",
                 "sinh sản", "di truyền", "gene"],
}
```

---

## 3. TIẾNG ANH (Lớp 3-9)

### Đặc thù HOÀN TOÀN khác các môn khác

Mỗi Unit chia thành **~10 section con**, mỗi section = 1 trang riêng:

```
Unit 1: My New School
├── Getting Started          (intro, listening)
├── A Closer Look 1          (vocabulary + pronunciation)
├── A Closer Look 2          (grammar)
├── Communication            (speaking)
├── Skills 1                 (reading + speaking)
├── Skills 2                 (listening + writing)
├── Looking Back             (review exercises)
├── Project                  (group activity)
├── Vocabulary (standalone)  (full vocab list)
├── Grammar (standalone)     (grammar notes)
└── Pronunciation (standalone)
```

**→ 1 Unit = ~11 articles trên loigiaihay.** Lớp 6 có 12 Units = ~130 articles cho chỉ 1 bộ sách!

### Content bilingual

Câu hỏi tiếng Việt + answer tiếng Anh. Ví dụ:
- **Câu hỏi**: "Hoàn thành câu sau với từ cho sẵn"
- **Đáp án**: "The book is *on* the table"
- **Giải thích**: "Giới từ chỉ vị trí là 'on' vì..."

### Nhiều bộ sách tiếng Anh

Lớp 6 có 5 bộ: Global Success (KNTT), Friends Plus, iLearn Smart World, Right On!, English Discovery. Gấp 1.67x so với Văn/Toán (3 bộ).

### 4 dạng kiến thức khác biệt

1. **Từ vựng**: word + pronunciation + meaning + example
2. **Ngữ pháp**: structure + formula + examples + exercises
3. **Bài đọc hiểu**: passage + comprehension questions
4. **Phát âm**: IPA symbols + example words

### Schema đề xuất cho Tiếng Anh

```sql
-- Từ vựng (đơn vị nhỏ nhất)
CREATE TABLE kb_english_vocabulary (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(30),
    unit_so INT, unit_ten VARCHAR(100),
    
    tu VARCHAR(100),                       -- "school"
    phien_am VARCHAR(100),                 -- "/skuːl/"
    loai_tu VARCHAR(20),                   -- 'noun', 'verb', 'adj'
    nghia_vi TEXT,                         -- "trường học"
    vi_du_en TEXT,
    vi_du_vi TEXT,
    
    vector_id UUID
);

-- Ngữ pháp
CREATE TABLE kb_english_grammar (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(30),
    
    ten_cau_truc VARCHAR(255),             -- "Thì hiện tại đơn"
    muc_do VARCHAR(20),                    -- 'A1', 'A2', 'B1'
    cong_thuc TEXT,                        -- "S + V(s/es) + O"
    cach_dung TEXT,
    dau_hieu_nhan_biet TEXT[],             -- ["always", "usually", "every day"]
    vi_du JSONB,                           -- [{en, vi, giai_thich}]
    
    vector_id UUID
);

-- Bài học (section)
CREATE TABLE kb_english_sections (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(30),
    unit_so INT,
    section_type VARCHAR(30),              -- 'getting_started', 'closer_look_1', 'skills_1', ...
    
    noi_dung TEXT,
    bai_tap JSONB,                         -- Structured exercises
    
    vector_id UUID
);
```

---

## 4. LỊCH SỬ + ĐỊA LÍ (LSĐL 4-9 tích hợp)

### Đặc thù: TÍCH HỢP như KHTN nhưng yếu hơn

Trong SGK lớp 4-9, Lịch sử và Địa lí **in chung 1 cuốn** nhưng nội dung tách biệt rõ hơn KHTN. Loigiaihay crawl theo bài, cần detect sub-subject.

### Đặc thù Lịch sử — TIMELINE là cốt lõi

Kiến thức Lịch sử tổ chức theo **thời gian tuyến tính**:
```
Trận Bạch Đằng (938)   → Ngô Quyền đánh Nam Hán
Trận Bạch Đằng (981)   → Lê Hoàn đánh Tống  
Trận Bạch Đằng (1288)  → Trần Hưng Đạo đánh Nguyên
```

**Học sinh hay nhầm!** Cùng tên "Bạch Đằng", 3 trận khác nhau. Retrieval phải trả về đúng trận theo lớp học.

### Đặc thù Địa lí

- **Số liệu cần chính xác**: diện tích, dân số, khí hậu
- **Tham chiếu bản đồ**: "Dựa vào hình 2, nêu..." → không có bản đồ = vô nghĩa
- **Đặc trưng vùng**: địa hình đồng bằng, khí hậu nhiệt đới...

### Schema đề xuất

```sql
-- Lịch sử: event-centric
CREATE TABLE kb_history_events (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(10),
    bai_so VARCHAR(20),
    
    ten_su_kien VARCHAR(255),              -- "Trận Bạch Đằng"
    nam INT,                               -- 938, 981, 1288
    thoi_ky VARCHAR(100),                  -- "Thời Ngô", "Thời Lý"
    
    nhan_vat_chinh TEXT[],                 -- ["Ngô Quyền", "Lưu Hoằng Tháo"]
    dia_diem VARCHAR(255),
    dien_bien TEXT,
    ket_qua TEXT,
    y_nghia TEXT,
    
    su_kien_lien_quan INT[],               -- FK đến events khác
    
    vector_id UUID
);

-- Địa lí: region-centric
CREATE TABLE kb_geography_regions (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(10),
    
    ten_vung VARCHAR(255),                 -- "Đồng bằng sông Hồng"
    loai_vung VARCHAR(50),                 -- 'dong_bang', 'mien_nui', 'bien'
    
    dien_tich FLOAT,
    dan_so BIGINT,
    khi_hau TEXT,
    dia_hinh TEXT,
    kinh_te TEXT,
    
    vector_id UUID
);
```

### Retrieval strategy đặc biệt cho Sử

```python
# Query: "Trận Bạch Đằng diễn ra năm nào?"
# Vấn đề: có 3 trận!

# Solution: dùng user profile (lớp) để disambiguate
if user_grade == 7:
    # Lớp 7 học trận 1288 trong bài "Ba lần kháng chiến Nguyên-Mông"
    filter: nam=1288
elif user_grade == 6:
    # Lớp 6 học trận 938 (Ngô Quyền)  
    filter: nam=938
else:
    # Trả cả 3 với note phân biệt
```

---

## 5. GDCD (6-9) + Đạo đức (1-5)

### Đặc thù content - đơn giản nhất

Hầu hết là **case study + đạo đức response**:
- Tình huống: "Bạn A nhặt được ví tiền..."
- Câu hỏi: "Em sẽ làm gì?"
- Đáp án: phân tích đạo đức + luật pháp

Không có công thức, không có timeline. Chỉ là **khái niệm đạo đức/pháp luật** + **tình huống minh họa**.

### Schema đơn giản

```sql
CREATE TABLE kb_ethics_content (
    id BIGSERIAL PRIMARY KEY,
    lop INT, bo_sach VARCHAR(10),
    
    chu_de VARCHAR(100),                   -- "Trung thực", "Tiết kiệm"
    loai VARCHAR(30),                      -- 'khai_niem', 'tinh_huong', 'quy_dinh_phap_luat'
    
    noi_dung TEXT,
    
    -- Cho tình huống:
    tinh_huong TEXT,
    cach_giai_quyet TEXT,
    bai_hoc TEXT,
    
    vector_id UUID
);
```

---

## 6. TỔNG HỢP - Kiến trúc RAG multi-subject

### Qdrant collections - Phương án cuối cùng

Sau khi khảo sát, tôi nhận ra **không nên** gộp tất cả vào 4 collections như tôi đề xuất trước đó. Lý do: embedding giữa các môn không so sánh được (công thức Toán vs bài văn vs event lịch sử).

**Phương án mới: collections theo "loại kiến thức" × "môn"**:

```
Collections:
├─ readings          (Văn bản đọc - TV/NV)
├─ writing_outlines  (Dàn ý văn - TV/NV)
├─ lang_concepts     (Khái niệm ngôn ngữ - TV/NV)
├─ math_concepts     (Công thức, định nghĩa toán)
├─ math_exercises    (Bài tập toán có lời giải)
├─ science_topics    (Lý thuyết KHTN, có sub_subject)
├─ english_vocab     (Từ vựng Anh)
├─ english_grammar   (Ngữ pháp Anh)
├─ english_sections  (Bài học Anh)
├─ history_events    (Sự kiện lịch sử)
├─ geography_regions (Vùng địa lí)
└─ ethics_content    (GDCD/Đạo đức)

=> Tổng: ~12 collections
```

### Vì sao không 4 collections?

- Công thức toán `S = 1/2 × a × h` và bài văn "Tả con mèo" có embedding space khác biệt
- Filter subject trong 1 collection không đảm bảo precision như collection riêng
- Với 42K vectors total, 12 collections nhỏ vẫn hiệu năng tốt

### Classifier flow mới

```
User query
  ↓
Layer 1: Subject detector (rule-based, rẻ)
  ↓ → toán / KHTN / anh / sử / địa / TV-NV / GDCD / chit-chat
  ↓
Layer 2: Intent classifier WITHIN subject
  ├─ Nếu toán: concept lookup | exercise solve | similar problem
  ├─ Nếu KHTN: theory | experiment | problem solve  
  ├─ Nếu Anh: vocab | grammar | exercise | pronunciation
  ├─ Nếu Sử: event | character | period
  ├─ Nếu Địa: region | statistics | map reference
  └─ (TV/NV giữ nguyên classifier hiện tại)
  ↓
Layer 3: Route to retriever + collection phù hợp
```

### Collection routing table

| Subject + Intent | Collection chính | Fallback |
|---|---|---|
| Toán + concept | math_concepts | - |
| Toán + exercise | math_exercises | math_concepts |
| KHTN + theory | science_topics (filter sub_subject) | - |
| Anh + vocab | english_vocab | english_sections |
| Anh + grammar | english_grammar | english_sections |
| Sử + event | history_events | - |
| Địa + region | geography_regions | - |
| GDCD | ethics_content | - |

---

## 7. Thay đổi crawler cần có

### Vấn đề nghiêm trọng nhất - MathJax/LaTeX

```python
# Trước khi chạy trafilatura, cần bảo toàn MathJax:
def preserve_mathjax(html):
    soup = BeautifulSoup(html, 'html.parser')
    
    # MathJax thường trong <span class="MathJax"> hoặc <script type="math/tex">
    for el in soup.select('.MathJax, script[type^="math/tex"]'):
        latex = el.get('data-latex') or el.get_text()
        el.replace_with(f"$${latex}$$")
    
    # Hoặc check raw content có \( ... \) / $...$
    ...
    return str(soup)

# Extract pipeline:
html_with_latex = preserve_mathjax(raw_html)
clean_text = trafilatura.extract(html_with_latex)
# LaTeX được giữ dưới dạng $$...$$ trong clean_text
```

### Hình ảnh - không crawl được nhưng phải flag

```python
def detect_image_dependency(text):
    """Flag content có reference hình - cần xử lý đặc biệt."""
    patterns = [
        r'[Hh]ình \d+\.\d+',       # Hình 2.1, Hình 3.5
        r'[Qq]uan sát hình',
        r'dựa vào (hình|bảng|biểu đồ|lược đồ)',
        r'như hình (bên|dưới|trên)',
    ]
    return any(re.search(p, text) for p in patterns)

# Nếu content có hình:
# - Không đẩy vào RAG (chất lượng kém vì thiếu context)
# - HOẶC đẩy vào với flag, và LLM response: "Bài này có hình minh họa..."
```

### Sub-subject detection cho KHTN

```python
def detect_khtn_sub_subject(text, title):
    # Ưu tiên title (rõ ràng hơn)
    for subj, keywords in SUB_SUBJECT_KEYWORDS.items():
        if any(kw in title.lower() for kw in keywords):
            return subj
    
    # Fallback: count keywords in content
    scores = {subj: 0 for subj in SUB_SUBJECT_KEYWORDS}
    text_lower = text.lower()
    for subj, keywords in SUB_SUBJECT_KEYWORDS.items():
        scores[subj] = sum(text_lower.count(kw) for kw in keywords)
    
    max_subj = max(scores, key=scores.get)
    return max_subj if scores[max_subj] > 3 else 'unknown'
```

---

## 8. Kế hoạch test theo môn

Mỗi môn cần **bộ eval riêng** với pattern query đặc thù:

### Toán - 50 câu
- Lookup công thức: "công thức tính diện tích hình tròn"
- Lookup bài cụ thể: "bài 5 trang 20 toán 3 KNTT"
- Giải bài có đề: "tính diện tích tam giác đáy 6 cao 4"
- Khái niệm: "phân số là gì"
- Bước giải: "cách làm bài toán có lời văn"

### KHTN - 40 câu
- Khái niệm: "nguyên tử là gì"
- Định luật: "định luật bảo toàn khối lượng"
- Phản ứng: "H2 + O2 ra gì"
- Thí nghiệm: "thí nghiệm chứng minh không khí có chứa oxi"
- Sub-subject accuracy: query có hàm ý Lý/Hóa/Sinh → trả đúng nhánh

### Tiếng Anh - 30 câu
- Từ vựng: "school nghĩa là gì"
- Ngữ pháp: "thì hiện tại đơn dùng khi nào"
- Phát âm: "âm /æ/ đọc như thế nào"
- Bilingual: queries hỗn hợp Việt-Anh

### Sử - 30 câu (CỰC KỲ CHÚ Ý disambiguation)
- Sự kiện đơn nghĩa: "Cách mạng tháng 8 năm nào"
- Sự kiện trùng tên: "trận Bạch Đằng năm nào" (3 trận!)
- Nhân vật: "Trần Hưng Đạo là ai"
- Theo thời kỳ: "nhà Lý có vua nào"

### Địa - 20 câu
- Vùng: "đồng bằng sông Hồng có đặc điểm gì"
- Số liệu: "dân số Việt Nam bao nhiêu"
- Đặc trưng: "khí hậu miền Bắc thế nào"

### GDCD - 20 câu
- Khái niệm: "trung thực là gì"
- Tình huống: "nhặt được của rơi nên làm gì"
- Luật: "quyền trẻ em gồm những gì"

### Cross-subject test (QUAN TRỌNG) - 30 câu

Test xem classifier có nhầm môn không:
- "nguyên tử" → KHTN (không phải Toán)
- "phân số" → Toán (không phải tiếng Việt)
- "Bạch Đằng" → Sử (không phải Địa hoặc Văn)
- "độc lập" → ambiguous! Có thể Sử (độc lập dân tộc) hoặc Văn (bài đọc)

---

## 9. Ưu tiên triển khai - đề xuất

Dựa trên **độ khó** + **impact**:

```
Week 1: Fix bugs hiện tại (lớp 8, WritingOutline) + Schema migration
Week 2: Toán lớp 1-9 
        ← Ưu tiên vì: khác biệt lớn nhất, validate được MathJax handling
        ← 9 lớp × 3 bộ = 27 categories, ~4000 articles
Week 3: KHTN 6-9 + Khoa học 4-5
        ← Test sub_subject detection
        ← Share MathJax handling với Toán
Week 4: Tiếng Anh 3-9 (lớp 1-2 ít nội dung)
        ← 5 bộ sách = nhiều nhất, ~6000 articles
Week 5: Sử/Địa 6-9
        ← Test disambiguation logic
Week 6: GDCD, Đạo đức, còn lại
        ← Đơn giản nhất
Week 7: Full eval + A/B test
Week 8: Iterate & production prep
```

---

## 10. Câu hỏi bạn cần quyết định

1. **LaTeX rendering ở output**: TTS có đọc được "S bằng đáy nhân chiều cao chia 2" không? Hay frontend sẽ render LaTeX thành speech riêng? Nếu voice-first, cần lưu song song cả `cong_thuc_latex` và `cong_thuc_text`.

2. **Hình ảnh**: loại bỏ hoàn toàn bài cần hình, hay vẫn retrieve và để LLM nói "bài này cần xem hình trong SGK"?

3. **Sub-subject KHTN**: thêm trường `sub_subject` và filter, hay tạo 3 collections riêng `khtn_hoa`, `khtn_li`, `khtn_sinh`?

4. **Tiếng Anh**: 5 bộ sách (Global Success, Friends Plus, Smart World, Right On, English Discovery) → crawl hết cả 5 hay chỉ 1-2 bộ phổ biến nhất?

5. **Ưu tiên voice output**: nếu sản phẩm chính là voice, thì Tiếng Anh phải có pronunciation audio, Toán phải có text form của công thức. Crawler có crawl được audio không, hay dùng TTS external?
