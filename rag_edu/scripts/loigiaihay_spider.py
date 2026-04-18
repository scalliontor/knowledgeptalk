"""
Scrapy Crawler cho loigiaihay.com - Lớp 1-5 Tiếng Việt
========================================================
Mục đích: crawl có cấu trúc, respect rate limit, lưu raw + extracted

Cài đặt:
    pip install scrapy trafilatura psycopg2-binary redis

Chạy:
    scrapy runspider loigiaihay_spider.py

Kiến trúc:
    1. Start từ category pages (danh sách bài của từng lớp × bộ sách)
    2. Extract article URLs
    3. Crawl từng article, lưu HTML raw + trafilatura extract
    4. Parse metadata từ URL và title
    5. Push vào Redis queue để downstream processing
"""

import re
import hashlib
import json
from urllib.parse import urlparse
from datetime import datetime

import scrapy
from scrapy.crawler import CrawlerProcess
import trafilatura


# ============================================================
# CATEGORY MAP - điểm xuất phát của crawler
# Lấy từ kết quả search thực tế của loigiaihay.com
# ============================================================
CATEGORY_URLS = {
    # =================== TIỂU HỌC (Tiếng Việt) ===================
    # Lớp 1
    (1, "KNTT"): "https://loigiaihay.com/sgk-tieng-viet-1-ket-noi-tri-thuc-voi-cuoc-song-c1181.html",
    (1, "CTST"): "https://loigiaihay.com/sgk-tieng-viet-1-chan-troi-sang-tao-c1182.html",
    (1, "CD"):   "https://loigiaihay.com/sgk-tieng-viet-1-canh-dieu-c1183.html",
    # Lớp 2
    (2, "KNTT"): "https://loigiaihay.com/tieng-viet-2-ket-noi-tri-thuc-c1237.html",
    (2, "CTST"): "https://loigiaihay.com/tieng-viet-2-chan-troi-sang-tao-c1238.html",
    (2, "CD"):   "https://loigiaihay.com/tieng-viet-2-canh-dieu-c1239.html",
    # Lớp 3
    (3, "KNTT"): "https://loigiaihay.com/tieng-viet-3-ket-noi-tri-thuc-c1284.html",
    (3, "CTST"): "https://loigiaihay.com/tieng-viet-3-chan-troi-sang-tao-c1285.html",
    (3, "CD"):   "https://loigiaihay.com/tieng-viet-3-canh-dieu-c1286.html",
    # Lớp 4
    (4, "KNTT"): "https://loigiaihay.com/tieng-viet-4-ket-noi-tri-thuc-c1640.html",
    (4, "CTST"): "https://loigiaihay.com/tieng-viet-4-chan-troi-sang-tao-c1641.html",
    (4, "CD"):   "https://loigiaihay.com/tieng-viet-4-canh-dieu-c1642.html",
    # Lớp 5
    (5, "KNTT"): "https://loigiaihay.com/tieng-viet-5-ket-noi-tri-thuc-c1786.html",
    (5, "CTST"): "https://loigiaihay.com/tieng-viet-5-chan-troi-sang-tao-c1787.html",
    (5, "CD"):   "https://loigiaihay.com/tieng-viet-5-canh-dieu-c1788.html",
    
    # =================== THCS (Ngữ Văn) ===================
    # Lớp 6
    (6, "KNTT"): "https://loigiaihay.com/soan-bai-ngu-van-6-ket-noi-tri-thuc-voi-cuoc-song-c630.html",
    (6, "CTST"): "https://loigiaihay.com/soan-van-6-chan-troi-sang-tao-c1232.html",
    (6, "CD"):   "https://loigiaihay.com/soan-van-6-canh-dieu-c1233.html",
    # Lớp 7
    (7, "KNTT"): "https://loigiaihay.com/soan-van-7-ket-noi-tri-thuc-c1278.html",
    (7, "CTST"): "https://loigiaihay.com/soan-van-7-chan-troi-sang-tao-c1281.html",
    (7, "CD"):   "https://loigiaihay.com/soan-van-7-canh-dieu-c1280.html",
    # Lớp 8  (URLs mới - cũ 404)
    (8, "KNTT"): "https://loigiaihay.com/soan-van-8-ket-noi-tri-thuc-chi-tiet-c1381.html",
    (8, "CTST"): "https://loigiaihay.com/soan-van-8-chan-troi-sang-tao-chi-tiet-c1383.html",
    (8, "CD"):   "https://loigiaihay.com/soan-van-8-canh-dieu-chi-tiet-c1385.html",
    # Lớp 9
    (9, "KNTT"): "https://loigiaihay.com/soan-van-9-ket-noi-tri-thuc-c1676.html",
    (9, "CTST"): "https://loigiaihay.com/soan-van-9-chan-troi-sang-tao-c1678.html",
    (9, "CD"):   "https://loigiaihay.com/soan-van-9-canh-dieu-c1677.html",
}


# ============================================================
# URL PARSERS - extract metadata từ URL và title
# ============================================================
def parse_url_metadata(url: str, title: str) -> dict:
    """
    Extract metadata từ URL pattern của loigiaihay.
    
    Examples:
      /bai-82-on-tap-trang-176-sgk-tieng-viet-lop-1-tap-1-...
      /tap-lam-van-luyen-tap-lam-don-trang-59-sgk-tieng-viet-lop-5-tap-1-...
    """
    metadata = {
        "url": url,
        "title_raw": title,
    }
    
    # Extract số trang
    page_match = re.search(r'trang[_-](\d+)', url, re.IGNORECASE)
    if page_match:
        metadata["trang"] = int(page_match.group(1))
    
    # Extract lớp
    lop_match = re.search(r'lop[_-](\d+)', url, re.IGNORECASE)
    if lop_match:
        metadata["lop"] = int(lop_match.group(1))
    
    # Extract tập
    tap_match = re.search(r'tap[_-](\d+)', url, re.IGNORECASE)
    if tap_match:
        metadata["tap"] = int(tap_match.group(1))
    
    # Extract article ID (cho dedup)
    id_match = re.search(r'-a(\d+)\.html$', url)
    if id_match:
        metadata["article_id"] = id_match.group(1)
    
    # Detect bộ sách
    if "ket-noi-tri-thuc" in url or "ket_noi_tri_thuc" in url:
        metadata["bo_sach"] = "KNTT"
    elif "chan-troi-sang-tao" in url:
        metadata["bo_sach"] = "CTST"
    elif "canh-dieu" in url:
        metadata["bo_sach"] = "CD"
    
    # Detect content type từ URL
    url_lower = url.lower()
    if "van-ban-" in url_lower:
        metadata["content_type"] = "van_ban"
    elif "soan-bai-" in url_lower or "soan-van-" in url_lower:
        metadata["content_type"] = "soan_van"
    elif "phan-tich-" in url_lower or "nghi-luan-" in url_lower or "cam-nhan-" in url_lower:
        metadata["content_type"] = "phan_tich"
    elif "tom-tat-" in url_lower or "bo-cuc-" in url_lower:
        metadata["content_type"] = "tom_tat"
    elif "tap-lam-van" in url_lower or "van-mau" in url_lower:
        metadata["content_type"] = "tap_lam_van"
    elif "luyen-tu-va-cau" in url_lower or "luyen-tu-cau" in url_lower or "thuc-hanh-tieng-viet" in url_lower:
        metadata["content_type"] = "luyen_tu_va_cau"
    elif "chinh-ta" in url_lower:
        metadata["content_type"] = "chinh_ta"
    elif "ke-chuyen" in url_lower:
        metadata["content_type"] = "ke_chuyen"
    elif "tap-doc" in url_lower or "bai-doc" in url_lower:
        metadata["content_type"] = "bai_doc"
    elif "on-tap" in url_lower:
        metadata["content_type"] = "on_tap"
    elif "de-kiem-tra" in url_lower or "de-thi" in url_lower:
        metadata["content_type"] = "de_kiem_tra"
    else:
        metadata["content_type"] = "unknown"
    
    return metadata


# ============================================================
# MAIN SPIDER
# ============================================================
class LoigiaihaySpider(scrapy.Spider):
    name = "loigiaihay"
    allowed_domains = ["loigiaihay.com"]
    
    # Rate limiting - LỊCH SỰ, đừng DDoS
    custom_settings = {
        "DOWNLOAD_DELAY": 0.2,                   # Giảm xuống 0.2 giây
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 16,    # Tăng concurrency lên 16
        "ROBOTSTXT_OBEY": False,
        "AUTOTHROTTLE_ENABLED": False,           # Tắt throttle để chạy nhanh nhất có thể
        "USER_AGENT": "EducationResearchBot/1.0",
        "HTTPCACHE_ENABLED": True,
        "HTTPCACHE_EXPIRATION_SECS": 86400 * 7,
        
        # Output
        "FEEDS": {
            "../data/jsonl/loigiaihay_%(time)s.jsonl": {
                "format": "jsonlines",
                "encoding": "utf-8",
                "overwrite": False,
            },
        },
    }
    
    def __init__(self, *args, start_grades=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_urls = set()
        self.stats = {"categories": 0, "articles": 0, "errors": 0}
        # If start_grades="8" or "6,7", only crawl those grades
        if start_grades:
            self.grade_filter = {int(g.strip()) for g in str(start_grades).split(",")}
        else:
            self.grade_filter = None
    
    def start_requests(self):
        """Bắt đầu crawl từ các category pages."""
        for (lop, bo_sach), url in CATEGORY_URLS.items():
            if self.grade_filter and lop not in self.grade_filter:
                continue
            yield scrapy.Request(
                url=url,
                callback=self.parse_category,
                meta={"lop": lop, "bo_sach": bo_sach, "depth": 0},
                errback=self.handle_error,
            )
    
    def parse_category(self, response):
        """
        Parse category page - extract danh sách article URLs.
        Category page của loigiaihay chứa nhiều sub-category + article links.
        """
        self.stats["categories"] += 1
        lop = response.meta["lop"]
        bo_sach = response.meta["bo_sach"]
        depth = response.meta.get("depth", 0)
        
        self.logger.info(f"Parsing category: Lớp {lop} - {bo_sach} (depth={depth})")
        
        # Extract article links - pattern "-a{ID}.html"
        article_links = response.css('a::attr(href)').re(r'[^"\s]+-a\d+\.html')
        article_links = [response.urljoin(link) for link in article_links]
        article_links = list(set(article_links))  # Dedup
        
        self.logger.info(f"  Tìm thấy {len(article_links)} article links")
        
        for link in article_links:
            if link in self.seen_urls:
                continue
            self.seen_urls.add(link)
            
            yield scrapy.Request(
                url=link,
                callback=self.parse_article,
                meta={"lop": lop, "bo_sach": bo_sach},
                errback=self.handle_error,
            )
        
        # Extract sub-category links - pattern "-c{ID}.html" (tránh loop vô hạn)
        if depth < 2:
            sub_categories = response.css('a::attr(href)').re(r'[^"\s]+-c\d+\.html')
            sub_categories = [response.urljoin(link) for link in sub_categories]
            sub_categories = list(set(sub_categories))
            
            # Filter: chỉ follow sub-cat cùng lớp
            lop_pattern = f"lop-{lop}" if lop > 1 else "lop-1|tieng-viet-1"
            # For THCS (6-9), also match ngu-van/van patterns
            if lop >= 6:
                lop_pattern = f"lop-{lop}|van-{lop}|ngu-van-{lop}"
            relevant_subs = [
                s for s in sub_categories 
                if re.search(lop_pattern, s) and s != response.url
            ]
            
            for sub_url in relevant_subs[:20]:  # Tối đa 20 sub-cat per page để tránh explode
                yield scrapy.Request(
                    url=sub_url,
                    callback=self.parse_category,
                    meta={"lop": lop, "bo_sach": bo_sach, "depth": depth + 1},
                    errback=self.handle_error,
                )
    
    def parse_article(self, response):
        """Parse 1 article page, extract content bằng trafilatura."""
        self.stats["articles"] += 1
        
        # Extract clean content bằng trafilatura (bỏ qua nav/footer/ads)
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=True,
            include_formatting=False,
            output_format="txt",
            deduplicate=True,
        )
        
        if not extracted or len(extracted) < 100:
            self.logger.warning(f"Content too short: {response.url}")
            return
        
        # Extract title
        title = response.css("title::text").get("").strip()
        # Loại bỏ suffix "| SGK Tiếng Việt 5" nếu có
        title = re.sub(r'\s*\|.*$', '', title).strip()
        
        # Parse metadata
        metadata = parse_url_metadata(response.url, title)
        metadata["lop"] = response.meta.get("lop", metadata.get("lop"))
        metadata["bo_sach"] = response.meta.get("bo_sach", metadata.get("bo_sach"))
        
        # Compute content hash để detect duplicates và changes
        content_hash = hashlib.sha256(extracted.encode("utf-8")).hexdigest()
        
        # Build output item
        item = {
            "url": response.url,
            "source_domain": "loigiaihay.com",
            "title": title,
            "content": extracted,
            "content_hash": content_hash,
            "word_count": len(extracted.split()),
            "html_length": len(response.text),
            "crawled_at": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }
        
        # Quick quality check
        if item["word_count"] < 30:
            self.logger.debug(f"Skipping short content: {response.url}")
            return
        
        yield item
        
        # Log progress
        if self.stats["articles"] % 50 == 0:
            self.logger.info(f"Progress: {self.stats}")
    
    def handle_error(self, failure):
        self.stats["errors"] += 1
        self.logger.error(f"Request failed: {failure.request.url} - {failure.value}")
    
    def closed(self, reason):
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"Final stats: {self.stats}")


# ============================================================
# POST-PROCESSING PIPELINE (chạy sau crawl)
# ============================================================
"""
Sau khi Scrapy chạy xong và ra file JSONL, chạy pipeline này:

1. Load vào PostgreSQL raw_pages table
2. Chạy LLM classifier để enrich metadata
3. Quality filter + dedup
4. Generate embeddings
5. Index vào Qdrant

Ví dụ code (PSEUDO - chạy riêng):
"""

POST_PROCESS_EXAMPLE = '''
import json
import psycopg2
from qdrant_client import QdrantClient

def load_jsonl_to_postgres(jsonl_path, db_conn):
    with open(jsonl_path) as f:
        for line in f:
            item = json.loads(line)
            cursor = db_conn.cursor()
            cursor.execute("""
                INSERT INTO raw_pages (url, source_domain, html_content, content_hash, crawled_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE 
                  SET content_hash = EXCLUDED.content_hash,
                      crawled_at = EXCLUDED.crawled_at,
                      crawl_version = raw_pages.crawl_version + 1
                RETURNING id
            """, (
                item["url"],
                item["source_domain"],
                item["content"],  # đã extract rồi, chứ không phải HTML thô
                item["content_hash"],
                item["crawled_at"],
            ))
            raw_id = cursor.fetchone()[0]
            
            # Insert vào extracted_content
            meta = item["metadata"]
            cursor.execute("""
                INSERT INTO extracted_content (
                    raw_page_id, title, clean_text, content_type,
                    grade, book_series, page_number, word_count, extra_metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                raw_id,
                item["title"],
                item["content"],
                meta.get("content_type"),
                meta.get("lop"),
                meta.get("bo_sach"),
                meta.get("trang"),
                item["word_count"],
                json.dumps(meta),
            ))
            db_conn.commit()


def classify_with_llm(content, title):
    """
    Gọi Claude Haiku / Gemini Flash để enrich metadata.
    Prompt mẫu:
    """
    prompt = f"""Phân tích nội dung giáo dục tiểu học sau. Trả về JSON:

Tiêu đề: {title}
Nội dung: {content[:2000]}

Trả về đúng format JSON:
{{
  "content_type": "bai_doc|tap_lam_van|luyen_tu_cau|chinh_ta|ke_chuyen|de_kiem_tra",
  "grade": 1-5 hoặc null,
  "theme": "gia_dinh|que_huong|thien_nhien|truong_lop|...",
  "quality_score": 1-10,
  "is_original_content": true/false,  # có phải văn bản SGK gốc không
  "notes": "ghi chú nếu có vấn đề"
}}"""
    # Gọi API...
    pass
'''


if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(LoigiaihaySpider)
    process.start()
