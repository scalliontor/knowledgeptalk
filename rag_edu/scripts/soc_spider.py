import scrapy
import re
from bs4 import BeautifulSoup
from lxml import html, etree
import trafilatura
from datetime import datetime

class SocSpider(scrapy.Spider):
    name = 'soc_spider'
    allowed_domains = ['loigiaihay.com']
    
    start_urls = [
        # Lịch sử và Địa lí 6-9
        "https://loigiaihay.com/lich-su-va-dia-li-lop-6-ket-noi-tri-thuc-c618.html",
        "https://loigiaihay.com/lich-su-va-dia-li-lop-6-chan-troi-sang-tao-c617.html",
        "https://loigiaihay.com/lich-su-va-dia-li-lop-6-canh-dieu-c620.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-7-ket-noi-tri-thuc-c829.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-7-chan-troi-sang-tao-c825.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-7-canh-dieu-c845.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-8-ket-noi-tri-thuc-c1604.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-8-chan-troi-sang-tao-c1615.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-lop-8-canh-dieu-c1605.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-9-ket-noi-tri-thuc-c1827.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-li-9-chan-troi-sang-tao-c1829.html",
        "https://loigiaihay.com/sgk-lich-su-va-dia-ly-9-canh-dieu-c1828.html",
        
        # GDCD 6-9
        "https://loigiaihay.com/sgk-giao-duc-cong-dan-lop-6-ket-noi-tri-thuc-c654.html",
        "https://loigiaihay.com/sgk-giao-duc-cong-dan-7-ket-noi-tri-thuc-c924.html",
        "https://loigiaihay.com/sgk-giao-duc-cong-dan-7-chan-troi-sang-tao-c925.html",
        "https://loigiaihay.com/sgk-giao-duc-cong-dan-7-canh-dieu-c926.html",
        "https://loigiaihay.com/giao-duc-cong-dan-8-ket-noi-tri-thuc-c1592.html",
        "https://loigiaihay.com/giao-duc-cong-dan-8-chan-troi-sang-tao-c1593.html",
        "https://loigiaihay.com/giao-duc-cong-dan-8-canh-dieu-c1594.html",
        "https://loigiaihay.com/giao-duc-cong-dan-9-ket-noi-tri-thuc-c1818.html",
        "https://loigiaihay.com/giao-duc-cong-dan-9-chan-troi-sang-tao-c1819.html",
        "https://loigiaihay.com/giao-duc-cong-dan-9-canh-dieu-c1820.html"
    ]

    custom_settings = {
        'FEED_FORMAT': 'jsonlines',
        'FEED_URI': '/home/namnx/knowledgeforptalk/rag_edu/data/jsonl/soc_loigiaihay_%(time)s.jsonl',
        'DEPTH_LIMIT': 3,
        'DOWNLOAD_DELAY': 0.5,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        'LOG_LEVEL': 'DEBUG'
    }

    def parse(self, response):
        # Determine grade and book from URL
        url = response.url
        lop = None
        m = re.search(r'lop-(\d+)', url) or re.search(r'-(\d+)-', url)
        if m:
            lop = int(m.group(1))
            
        bo_sach = 'KNTT'
        if 'chan-troi' in url:
            bo_sach = 'CTST'
        elif 'canh-dieu' in url:
            bo_sach = 'CD'
            
        subject = 'gdcd' if 'giao-duc-cong-dan' in url else 'lich_su_dia_li'

        # Find category links
        category_links = response.css('a::attr(href)').re(r'[^"\s]+-c\d+\.html')
        for link in set(category_links):
            yield response.follow(link, self.parse_category, meta={'lop': lop, 'bo_sach': bo_sach, 'subject': subject})
            
        # If it's already a lesson/exercise page
        lesson_links = response.css('a::attr(href)').re(r'[^"\s]+-[ea]\d+\.html')
        for link in set(lesson_links):
            yield response.follow(link, self.parse_lesson, meta={'lop': lop, 'bo_sach': bo_sach, 'subject': subject})

    def parse_category(self, response):
        meta = response.meta
        # Find lessons
        lesson_links = response.css('a::attr(href)').re(r'[^"\s]+-[ea]\d+\.html')
        for link in set(lesson_links):
            yield response.follow(link, self.parse_lesson, meta=meta)

    def parse_lesson(self, response):
        meta = response.meta
        title = response.css('h1::text').get(default='').strip()
        content_html = response.css('div.box_content').get()
        
        if content_html:
            # Follow sub-answer links if present
            sub_links = response.css('*::attr(href)').re(r'[^"\s]+-a\d+\.html')
            for sub_link in set(sub_links):
                yield response.follow(sub_link, self.parse_lesson, meta=meta)

            # We want to preserve logic/historical context precisely
            soup = BeautifulSoup(content_html, 'html.parser')
            tree = html.fromstring(str(soup))
            text = trafilatura.extract(tree, include_links=False, include_images=False, include_formatting=True)
            
            if text and len(text) > 50:
                yield {
                    'url': response.url,
                    'title': title,
                    'content': text,
                    'word_count': len(text.split()),
                    'metadata': {
                        'subject': meta['subject'],
                        'lop': meta['lop'],
                        'bo_sach': meta['bo_sach'],
                        'content_type': 'soc_lesson'
                    }
                }

    def extract_meta_from_url(self, url):
        # Default Social Sciences
        meta = {
            "subject": "lich_su_dia_li", 
            "lop": None,
            "bo_sach": "KNTT", # default
            "content_type": "soc_lesson"
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
