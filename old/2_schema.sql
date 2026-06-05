-- ============================================================
-- SCHEMA POSTGRESQL - KNOWLEDGE BASE CHATBOT TIỂU HỌC
-- ============================================================
-- Thiết kế theo triết lý: tách biệt raw crawl / processed / curated
-- Mỗi bảng có trách nhiệm rõ ràng, không nhồi mọi thứ vào 1 bảng
-- ============================================================

-- --------------------------------------------------------
-- LAYER 1: RAW CRAWL DATA
-- Mục đích: lưu HTML gốc để có thể re-process khi cần
-- Không bao giờ query trực tiếp từ đây cho RAG
-- --------------------------------------------------------
CREATE TABLE raw_pages (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    source_domain VARCHAR(100) NOT NULL,  -- 'loigiaihay.com', 'vndoc.com', ...
    html_content TEXT,                     -- HTML gốc
    http_status INT,
    content_hash VARCHAR(64),              -- SHA256 để detect changes
    crawled_at TIMESTAMP DEFAULT NOW(),
    last_modified TIMESTAMP,
    crawl_version INT DEFAULT 1
);
CREATE INDEX idx_raw_pages_domain ON raw_pages(source_domain);
CREATE INDEX idx_raw_pages_hash ON raw_pages(content_hash);

-- --------------------------------------------------------
-- LAYER 2: EXTRACTED & CLASSIFIED
-- Mục đích: content đã được làm sạch và phân loại
-- LLM enrichment chạy ở layer này
-- --------------------------------------------------------
CREATE TABLE extracted_content (
    id BIGSERIAL PRIMARY KEY,
    raw_page_id BIGINT REFERENCES raw_pages(id),
    
    -- Core content
    title TEXT NOT NULL,
    clean_text TEXT NOT NULL,              -- Text đã strip HTML
    content_type VARCHAR(50),              -- 'bai_doc', 'tap_lam_van', 'luyen_tu_cau', ...
    
    -- Metadata giáo dục
    grade INT CHECK (grade BETWEEN 1 AND 5),
    subject VARCHAR(50) DEFAULT 'tieng_viet',  -- mở rộng sau: 'toan', 'tnxh', ...
    book_series VARCHAR(50),               -- 'KNTT', 'CTST', 'CD'
    volume INT,                            -- tập 1 hoặc 2
    week_number INT,
    page_number INT,
    lesson_number VARCHAR(20),             -- 'Bài 5', 'Bài 82', ...
    theme VARCHAR(100),                    -- 'gia_dinh', 'que_huong', 'thien_nhien'
    
    -- Quality signals
    word_count INT,
    quality_score FLOAT,                   -- 0-10, do LLM chấm
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of_id BIGINT REFERENCES extracted_content(id),
    
    -- Audit
    extracted_at TIMESTAMP DEFAULT NOW(),
    classified_at TIMESTAMP,
    classifier_model VARCHAR(50),
    
    -- Flexible extra metadata
    extra_metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_extracted_content_type ON extracted_content(content_type);
CREATE INDEX idx_extracted_grade_book ON extracted_content(grade, book_series);
CREATE INDEX idx_extracted_quality ON extracted_content(quality_score);
CREATE INDEX idx_extracted_metadata ON extracted_content USING GIN (extra_metadata);

-- --------------------------------------------------------
-- LAYER 3: CURATED KNOWLEDGE
-- Đây là layer production cho RAG
-- Chỉ chứa content đã qua quality filter và dedup
-- --------------------------------------------------------

-- Bài đọc SGK gốc - GIỮ NGUYÊN, KHÔNG CHUNK
CREATE TABLE kb_sgk_reading (
    id BIGSERIAL PRIMARY KEY,
    extracted_content_id BIGINT REFERENCES extracted_content(id),
    
    ten_bai VARCHAR(255) NOT NULL,
    tac_gia VARCHAR(255),
    the_loai VARCHAR(50),                  -- 'tho', 'van_xuoi', 'truyen_ngan', 'truyen_dong_phi'
    lop INT NOT NULL,
    bo_sach VARCHAR(50) NOT NULL,
    tap INT,
    tuan INT,
    trang INT,
    chu_de VARCHAR(100),
    
    noi_dung_goc TEXT NOT NULL,            -- Full text bài đọc
    tom_tat TEXT,                          -- 1-2 câu tóm tắt
    cau_hoi_kem TEXT[],                    -- Các câu hỏi SGK đi kèm
    
    -- Vector ID để link với Qdrant
    vector_id UUID UNIQUE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (ten_bai, bo_sach, lop, tap)
);
CREATE INDEX idx_kb_reading_lookup ON kb_sgk_reading(lop, bo_sach, tuan);

-- Khái niệm ngữ pháp / ngôn ngữ
CREATE TABLE kb_language_concepts (
    id BIGSERIAL PRIMARY KEY,
    extracted_content_id BIGINT REFERENCES extracted_content(id),
    
    ten_khai_niem VARCHAR(255) NOT NULL,
    dinh_nghia TEXT NOT NULL,
    
    lop_xuat_hien_dau INT,                 -- Khái niệm này xuất hiện lần đầu ở lớp mấy
    mon VARCHAR(50) DEFAULT 'luyen_tu_va_cau',
    
    vi_du JSONB,                           -- [{"text": "...", "giai_thich": "..."}]
    khai_niem_lien_quan TEXT[],
    
    vector_id UUID UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_kb_concepts_name ON kb_language_concepts(ten_khai_niem);

-- Dàn ý mẫu cho tập làm văn
CREATE TABLE kb_writing_outlines (
    id BIGSERIAL PRIMARY KEY,
    extracted_content_id BIGINT REFERENCES extracted_content(id),
    
    dang_bai VARCHAR(100) NOT NULL,        -- 'ta_cay_coi', 'ta_nguoi_than', 'ke_chuyen'
    lop INT NOT NULL,
    
    -- Cấu trúc dàn ý
    cau_truc JSONB NOT NULL,               
    /* Example:
    {
      "mo_bai": {
        "goi_y": "Giới thiệu cây muốn tả, cây đó ở đâu",
        "vi_du_cau": ["Nhà em có một cây phượng...", "Sân trường em có..."]
      },
      "than_bai": {
        "ta_bao_quat": ["Cây cao bao nhiêu?", "Dáng cây như thế nào?"],
        "ta_chi_tiet": ["Thân cây", "Lá cây", "Hoa", "Quả"]
      },
      "ket_bai": {
        "goi_y": "Cảm xúc của em với cây",
        "vi_du_cau": ["Em rất yêu cây phượng này..."]
      }
    }
    */
    
    tu_vung_goi_y TEXT[],                  -- Từ ngữ hay dùng cho dạng bài này
    vector_id UUID UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_kb_outlines_type ON kb_writing_outlines(dang_bai, lop);

-- Bài văn mẫu tham khảo (CHỌN LỌC, không phải tất cả scraped)
CREATE TABLE kb_writing_samples (
    id BIGSERIAL PRIMARY KEY,
    extracted_content_id BIGINT REFERENCES extracted_content(id),
    
    dang_bai VARCHAR(100) NOT NULL,
    chu_de VARCHAR(255),                   -- 'ta_cay_phuong', 'ke_chuyen_co_tich'
    lop INT NOT NULL,
    
    tieu_de VARCHAR(255),
    noi_dung TEXT NOT NULL,
    word_count INT,
    
    -- Quality signals
    quality_score FLOAT,                   -- từ LLM chấm
    review_status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'approved', 'rejected'
    reviewed_by VARCHAR(100),              -- teacher name nếu có human review
    
    vector_id UUID UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_kb_samples_topic ON kb_writing_samples(dang_bai, chu_de, lop);
CREATE INDEX idx_kb_samples_quality ON kb_writing_samples(quality_score) WHERE review_status = 'approved';

-- --------------------------------------------------------
-- LAYER 4: CURRICULUM STRUCTURE (tự tạo, không crawl)
-- Bảng chương trình học theo tuần - essential cho "tuần này con học gì"
-- --------------------------------------------------------
CREATE TABLE curriculum_schedule (
    id BIGSERIAL PRIMARY KEY,
    lop INT NOT NULL,
    bo_sach VARCHAR(50) NOT NULL,
    mon VARCHAR(50) NOT NULL,
    tuan INT NOT NULL,
    tap INT,
    
    chu_diem VARCHAR(255),                 -- Chủ điểm của tuần
    bai_doc_chinh VARCHAR(255),            -- Tên bài đọc chính
    bai_doc_id BIGINT REFERENCES kb_sgk_reading(id),
    kien_thuc_ngon_ngu TEXT[],             -- Các khái niệm ngữ pháp của tuần
    bai_tap_lam_van VARCHAR(255),          -- Dạng tập làm văn
    
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (lop, bo_sach, mon, tuan, tap)
);
CREATE INDEX idx_curriculum_lookup ON curriculum_schedule(lop, bo_sach, tuan);

-- --------------------------------------------------------
-- LAYER 5: USER MEMORY (separate concern từ knowledge)
-- --------------------------------------------------------
CREATE TABLE user_profiles (
    user_id VARCHAR(100) PRIMARY KEY,
    ten_goi VARCHAR(100),                  -- Tên chatbot gọi user
    lop INT,
    bo_sach_chinh VARCHAR(50),
    so_thich TEXT[],                       -- Trẻ thích cái gì
    
    diem_manh JSONB,                       -- {"tieng_viet": ["doc_hieu"], ...}
    diem_yeu JSONB,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE conversation_history (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100) REFERENCES user_profiles(user_id),
    session_id VARCHAR(100),
    role VARCHAR(20),                      -- 'user' | 'assistant'
    content TEXT,
    
    -- Metadata về retrieval (để debug)
    retrieved_items JSONB,                 -- [{kb_type, kb_id, score}, ...]
    tool_calls JSONB,
    
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_conv_user_session ON conversation_history(user_id, session_id, created_at);

-- --------------------------------------------------------
-- LAYER 6: EVAL SET
-- --------------------------------------------------------
CREATE TABLE eval_questions (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    question_type VARCHAR(50),             -- 'tra_cuu_bai_doc', 'giai_thich_khai_niem', ...
    expected_retrieval_type VARCHAR(50),   -- Nhóm KB nào nên được retrieve
    expected_keywords TEXT[],              -- Keywords phải xuất hiện trong answer
    grade_target INT,
    difficulty VARCHAR(20),                -- 'easy', 'medium', 'hard'
    source VARCHAR(100),                   -- 'real_child', 'teacher', 'synthetic'
    
    ideal_answer TEXT,                     -- Câu trả lời mẫu
    created_at TIMESTAMP DEFAULT NOW()
);

-- --------------------------------------------------------
-- CHIẾN LƯỢC QDRANT (Vector DB)
-- --------------------------------------------------------
/*
Tạo các collections RIÊNG BIỆT, không gộp chung:

1. Collection: sgk_readings
   - 1 vector per bài đọc (không chunk)
   - payload: {ten_bai, lop, bo_sach, tuan, chu_de, content_type}
   
2. Collection: language_concepts  
   - 1 vector per khái niệm
   - payload: {ten_khai_niem, lop_xuat_hien_dau}

3. Collection: writing_outlines
   - 1 vector per dàn ý
   - payload: {dang_bai, lop}

4. Collection: writing_samples
   - 1 vector per bài mẫu (chỉ approved)
   - payload: {dang_bai, chu_de, lop, quality_score}

Lý do tách collections:
- Query classifier route đến đúng collection → precision cao hơn
- Filter metadata nhanh hơn
- Có thể tuning embedding khác nhau cho từng loại content

Embedding model đề xuất:
- bge-m3 (multilingual, hiểu tiếng Việt tốt, 1024 dims)
- Hoặc multilingual-e5-large (1024 dims)
- KHÔNG dùng OpenAI text-embedding-3 vì tiếng Việt kém hơn bge-m3
*/
