#!/usr/bin/env python3
"""
Crawler lớp 9 — 3 bộ sách (CTST, KNTT, CD)
Crawl soan-bai, van-ban, tom-tat từ loigiaihay.com
Output: JSONL files phân loại theo content type
"""
import asyncio
import aiohttp
import json
import re
import time
import hashlib
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

OUTPUT_DIR = Path('/home/namnx/knowledgeforptalk/rag_edu/data/grade9_new')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = 'https://loigiaihay.com'
RATE_LIMIT = 2.0   # seconds between requests per domain
MAX_WORKERS = 8
TIMEOUT = 20

CATEGORY_PAGES = {
    'CTST': 'https://loigiaihay.com/soan-van-9-chan-troi-sang-tao-c1743.html',
    'KNTT': 'https://loigiaihay.com/soan-van-9-ket-noi-tri-thuc-c1740.html',
    'CD':   'https://loigiaihay.com/soan-van-9-canh-dieu-c1742.html',
}

# Van-ban category pages (loigiaihay có thêm mục van-ban riêng)
VAN_BAN_CATEGORY = {
    'CTST': 'https://loigiaihay.com/van-ban-ngu-van-9-chan-troi-sang-tao-c1897.html',
    'KNTT': 'https://loigiaihay.com/van-ban-ngu-van-9-ket-noi-tri-thuc-c1895.html',
    'CD':   'https://loigiaihay.com/van-ban-ngu-van-9-canh-dieu-c1896.html',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; EduBot/1.0)',
    'Accept': 'text/html',
    'Accept-Language': 'vi-VN,vi;q=0.9',
}


# ─────────────────── PARSER ───────────────────

def clean_text(text: str) -> str:
    """Làm sạch text — bỏ khoảng trắng thừa, link rác"""
    text = re.sub(r'>> Xem thêm.*', '', text, flags=re.DOTALL)
    text = re.sub(r'\[.*?\]\(http[^\)]+\)', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_soan_bai(soup: BeautifulSoup, url: str) -> dict | None:
    """Parse trang soạn bài → trích Q&A (loigiaihay dùng #box-content)"""
    title_tag = soup.find('h1')
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)

    # Content nằm trong #box-content
    content_div = (
        soup.find('div', id='box-content') or
        soup.find('div', class_='content_box') or
        soup.find('div', class_='detail_new') or
        soup.find('div', id='main-content')
    )
    if not content_div:
        return None

    # Lấy Q&A từ box-question và explanation-content
    qa_blocks = []
    for qbox in content_div.find_all('div', class_='box-question'):
        q_text = qbox.get_text(separator=' ', strip=True)
        # Tìm lời giải tương ứng (sibling)
        explanation = qbox.find_next_sibling('div', class_=lambda c: c and 'explanation-content' in c)
        a_text = explanation.get_text(separator=' ', strip=True) if explanation else ''
        if q_text:
            qa_blocks.append(f"Q: {q_text}\nA: {a_text}")

    if qa_blocks:
        content = '\n\n'.join(qa_blocks)
    else:
        # Fallback: lấy toàn bộ text của content div
        content = clean_text(content_div.get_text(separator='\n'))

    if len(content) < 80:
        return None

    # Tìm link van-ban liên quan
    linked_vanban = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/van-ban-' in href and 'loigiaihay.com' in href:
            linked_vanban.append(href)

    style = 'sieu_ngan' if 'sieu-ngan' in url else 'chi_tiet'

    return {
        'type': 'lesson_guide',
        'title': title,
        'content': content,
        'style': style,
        'url': url,
        'linked_van_ban': list(set(linked_vanban))[:5],
    }


def extract_van_ban(soup: BeautifulSoup, url: str) -> dict | None:
    """Parse trang văn bản → lấy toàn văn (loigiaihay dùng #box-content)"""
    title_tag = soup.find('h1')
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)

    content_div = (
        soup.find('div', id='box-content') or
        soup.find('div', class_='content_box') or
        soup.find('div', class_='detail_new')
    )
    if not content_div:
        return None

    raw = content_div.get_text(separator='\n')

    # Tìm phần toàn văn: sau dấu "[ ... ]" (loigiaihay dùng marker này)
    full_text_match = re.search(
        r'\[\s*\.\.\.\s*\](.*?)(?:Bình luận|👉|Luyện Bài|Báo lỗi|\Z)',
        raw, re.DOTALL
    )
    if full_text_match:
        full_text = full_text_match.group(1).strip()
    else:
        full_text = clean_text(raw)

    if len(full_text) < 50:
        return None

    author_match = re.search(r'\(([^)]{5,50})\)', title)
    author = author_match.group(1) if author_match else ''

    vtype = 'tho'
    if any(k in title.lower() for k in ['truyện', 'chuyện', 'đoạn trích', 'văn xuôi']):
        vtype = 'truyen'

    return {
        'type': 'literature_text',
        'title': title,
        'author': author,
        'full_text': clean_text(full_text),
        'text_type': vtype,
        'url': url,
    }


def extract_tom_tat(soup: BeautifulSoup, url: str) -> dict | None:
    """Parse trang tóm tắt bố cục (loigiaihay dùng #box-content)"""
    title_tag = soup.find('h1')
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)

    content_div = (
        soup.find('div', id='box-content') or
        soup.find('div', class_='content_box') or
        soup.find('div', class_='detail_new')
    )
    if not content_div:
        return None

    content = clean_text(content_div.get_text(separator='\n'))
    if len(content) < 50:
        return None

    return {
        'type': 'summary',
        'title': title,
        'content': content,
        'url': url,
    }


def classify_url(url: str) -> str:
    if '/van-ban-' in url:
        return 'van_ban'
    elif '/soan-bai-' in url:
        # Lọc bỏ các bài viết/nói/luyện tập — chỉ giữ đọc hiểu
        if any(x in url for x in ['viet-', 'trinh-bay-', 'nghe-va-', 'luyen-tap', 'on-tap', 'tu-danh-gia', 'thuc-hanh-tieng-viet', 'cung-co-mo-rong', 'phieu-hoc-tap']):
            return 'skip'
        return 'soan_bai'
    elif '/tac-gia-' in url or '/tom-tat-' in url:
        return 'tom_tat'
    return 'skip'


# ─────────────────── CRAWLER ───────────────────

async def fetch(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore) -> str | None:
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                if resp.status == 200:
                    return await resp.text(errors='replace')
        except Exception as e:
            print(f'  [ERR] {url}: {e}')
        await asyncio.sleep(RATE_LIMIT / MAX_WORKERS)
        return None


async def crawl_category(session, url, semaphore) -> list[str]:
    """Lấy tất cả lesson links từ category page"""
    html = await fetch(session, url, semaphore)
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('/'):
            href = BASE_URL + href
        if 'loigiaihay.com' in href and ('/soan-bai-' in href or '/van-ban-' in href or '/tac-gia-' in href or '/tom-tat-' in href):
            links.append(href)
    return list(dict.fromkeys(links))  # deduplicate, preserve order


async def process_url(session, url, series, semaphore, writers):
    url_type = classify_url(url)
    if url_type == 'skip':
        return

    html = await fetch(session, url, semaphore)
    if not html:
        return

    soup = BeautifulSoup(html, 'html.parser')

    if url_type == 'soan_bai':
        doc = extract_soan_bai(soup, url)
        if doc:
            doc['series'] = series
            doc['grade'] = 9
            doc['subject'] = 'Ngữ Văn'
            writers['lesson'].write(json.dumps(doc, ensure_ascii=False) + '\n')
            writers['lesson'].flush()
            # Crawl linked van-ban
            for vb_url in doc.get('linked_van_ban', []):
                if vb_url not in writers.get('_seen', set()):
                    writers.setdefault('_seen', set()).add(vb_url)
                    await process_url(session, vb_url, series, semaphore, writers)

    elif url_type == 'van_ban':
        doc = extract_van_ban(soup, url)
        if doc:
            doc['series'] = series
            doc['grade'] = 9
            doc['subject'] = 'Ngữ Văn'
            writers['vanban'].write(json.dumps(doc, ensure_ascii=False) + '\n')
            writers['vanban'].flush()

    elif url_type == 'tom_tat':
        doc = extract_tom_tat(soup, url)
        if doc:
            doc['series'] = series
            doc['grade'] = 9
            doc['subject'] = 'Ngữ Văn'
            writers['tomtat'].write(json.dumps(doc, ensure_ascii=False) + '\n')
            writers['tomtat'].flush()


async def main():
    semaphore = asyncio.Semaphore(MAX_WORKERS)
    connector = aiohttp.TCPConnector(limit=MAX_WORKERS * 2)

    lesson_f = open(OUTPUT_DIR / 'lesson_guide.jsonl', 'w')
    vanban_f = open(OUTPUT_DIR / 'literature_text.jsonl', 'w')
    tomtat_f = open(OUTPUT_DIR / 'summary.jsonl', 'w')
    writers = {'lesson': lesson_f, 'vanban': vanban_f, 'tomtat': tomtat_f, '_seen': set()}

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        for series, cat_url in CATEGORY_PAGES.items():
            print(f'\n=== [{series}] Crawling category: {cat_url} ===')
            links = await crawl_category(session, cat_url, semaphore)
            print(f'  Found {len(links)} links')

            # Cũng thêm van-ban category (nếu có)
            vb_cat = VAN_BAN_CATEGORY.get(series)
            if vb_cat:
                vb_links = await crawl_category(session, vb_cat, semaphore)
                links.extend(vb_links)
                print(f'  Added {len(vb_links)} van-ban links')

            links = list(dict.fromkeys(links))
            tasks = [process_url(session, url, series, semaphore, writers) for url in links]

            # Run in batches
            batch = 20
            for i in range(0, len(tasks), batch):
                chunk = tasks[i:i+batch]
                await asyncio.gather(*chunk)
                print(f'  [{series}] Processed {min(i+batch, len(tasks))}/{len(links)}')
                await asyncio.sleep(0.5)

    lesson_f.close()
    vanban_f.close()
    tomtat_f.close()

    print('\n=== DONE ===')
    for fname in OUTPUT_DIR.iterdir():
        lines = sum(1 for _ in open(fname))
        print(f'  {fname.name}: {lines} documents')


if __name__ == '__main__':
    asyncio.run(main())
