import scrapy
import re
from bs4 import BeautifulSoup
from lxml import html, etree
import trafilatura
from datetime import datetime

class KHTNSpider(scrapy.Spider):
    name = 'khtn_spider'
    allowed_domains = ['loigiaihay.com']
    
    # 12 Category URLs for Grades 6-9
    start_urls = [
        # Grade 6
        'https://loigiaihay.com/khoa-hoc-tu-nhien-lop-6-ket-noi-tri-thuc-voi-cuoc-song-c615.html',
        'https://loigiaihay.com/khoa-hoc-tu-nhien-lop-6-chan-troi-sang-tao-c616.html',
        'https://loigiaihay.com/khoa-hoc-tu-nhien-lop-6-canh-dieu-c610.html',
        # Grade 7
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-7-ket-noi-tri-thuc-c856.html',
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-7-chan-troi-sang-tao-c857.html',
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-7-canh-dieu-c858.html',
        # Grade 8
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-8-ket-noi-tri-thuc-c1378.html',
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-8-chan-troi-sang-tao-c1379.html',
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-8-canh-dieu-c1380.html',
        # Grade 9
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-9-ket-noi-tri-thuc-c1744.html',
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-9-chan-troi-sang-tao-c1736.html',
        'https://loigiaihay.com/sgk-khoa-hoc-tu-nhien-9-canh-dieu-c1733.html'
    ]

    custom_settings = {
        'DOWNLOAD_DELAY': 0.2, # Fast crawl
        'CONCURRENT_REQUESTS': 8,
        'HTTPCACHE_ENABLED': False,
        'FEEDS': {
            f'/home/namnx/knowledgeforptalk/rag_edu/data/jsonl/khtn_loigiaihay_{datetime.now().strftime("%Y-%m-%dT%H-%M-%S")}.jsonl': {
                'format': 'jsonlines',
                'encoding': 'utf8',
            }
        }
    }

    def parse(self, response):
        # 1. Follow lesson links
        lesson_links = response.css('a::attr(href)').re(r'[^"\s]+-[ae]\d+\.html')
        for link in set(lesson_links):
            yield response.follow(link, self.parse_lesson)
            
        # 2. Extract metadata based on url
        meta = self.extract_meta_from_url(response.url)
        
        # 3. If there's pagination, follow it 
        # (Though usually category links just list all chapters & lessons)

    def parse_lesson(self, response):
        meta = self.extract_meta_from_url(response.url)
        content_html = response.css('div.box_content').get()
        
        if content_html:
            # Follow sub-answer links if present
            sub_links = response.css('*::attr(href)').re(r'[^"\s]+-a\d+\.html')
            for sub_link in set(sub_links):
                yield response.follow(sub_link, self.parse_lesson)

            # We want to preserve math/chemistry formulas
            soup = BeautifulSoup(content_html, 'html.parser')
            tree = html.fromstring(str(soup))
            text = trafilatura.extract(tree, include_links=False, include_images=False, include_formatting=True)
            
            if text:
                yield {
                    'url': response.url,
                    'title': response.css('h1.title-box-bai::text').get(default="").strip(),
                    'content': text,
                    'word_count': len(text.split()),
                    'metadata': meta
                }

    def extract_meta_from_url(self, url):
        # Default KHTN 
        meta = {
            "subject": "khtn", 
            "lop": None,
            "bo_sach": "KNTT", # default
            "content_type": "khtn_lesson"
        }
        
        # Detect Grade
        for grade in range(6, 10):
            if f"-{grade}-" in url or f"lop-{grade}" in url:
                meta["lop"] = grade
                break
                
        # Detect Book series
        if "ket-noi-tri-thuc" in url or "kntt" in url:
            meta["bo_sach"] = "KNTT"
        elif "chan-troi-sang-tao" in url or "ctst" in url:
            meta["bo_sach"] = "CTST"
        elif "canh-dieu" in url or "cd" in url:
            meta["bo_sach"] = "CD"
            
        return meta
