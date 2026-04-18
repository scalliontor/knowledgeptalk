import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import hashlib
import unicodedata
import os
import re

SEEDS = {
    # Grade 1
    "1": [
        "https://loigiaihay.com/sgk-tieng-viet-1-canh-dieu-c1350.html",
        "https://loigiaihay.com/sgk-tieng-viet-1-chan-troi-sang-tao-c1186.html",
        "https://loigiaihay.com/sgk-tieng-viet-1-ket-noi-tri-thuc-voi-cuoc-song-c1181.html"
    ],
    # Grade 2
    "2": [
        "https://loigiaihay.com/tieng-viet-2-canh-dieu-c636.html",
        "https://loigiaihay.com/tieng-viet-2-chan-troi-sang-tao-c639.html",
        "https://loigiaihay.com/tieng-viet-2-ket-noi-tri-thuc-voi-cuoc-song-c640.html"
    ],
    # Grade 3
    "3": [
        "https://loigiaihay.com/tieng-viet-3-canh-dieu-c849.html",
        "https://loigiaihay.com/tieng-viet-3-chan-troi-sang-tao-c848.html",
        "https://loigiaihay.com/tieng-viet-3-ket-noi-tri-thuc-c847.html"
    ],
    # Grade 4
    "4": [
        "https://loigiaihay.com/tieng-viet-4-canh-dieu-c1437.html",
        "https://loigiaihay.com/tieng-viet-4-chan-troi-sang-tao-c1436.html",
        "https://loigiaihay.com/tieng-viet-4-ket-noi-tri-thuc-c1424.html"
    ],
    # Grade 5
    "5": [
        "https://loigiaihay.com/tieng-viet-5-canh-dieu-c1788.html",
        "https://loigiaihay.com/tieng-viet-5-chan-troi-sang-tao-c1787.html",
        "https://loigiaihay.com/tieng-viet-5-ket-noi-tri-thuc-c1786.html"
    ],
    # Grade 6
    "6": [
        "https://loigiaihay.com/soan-van-6-canh-dieu-chi-tiet-c635.html",
        "https://loigiaihay.com/soan-van-6-chan-troi-sang-tao-chi-tiet-c629.html",
        "https://loigiaihay.com/soan-van-6-ket-noi-tri-thuc-voi-cuoc-song-chi-tiet-c630.html"
    ],
    # Grade 7
    "7": [
        "https://loigiaihay.com/soan-van-7-canh-dieu-chi-tiet-c836.html",
        "https://loigiaihay.com/soan-van-7-chan-troi-sang-tao-chi-tiet-c843.html",
        "https://loigiaihay.com/soan-van-7-ket-noi-tri-thuc-chi-tiet-c839.html"
    ],
    # Grade 8
    "8": [
        "https://loigiaihay.com/soan-van-8-canh-dieu-chi-tiet-c1385.html",
        "https://loigiaihay.com/soan-van-8-chan-troi-sang-tao-chi-tiet-c1383.html",
        "https://loigiaihay.com/soan-van-8-ket-noi-tri-thuc-chi-tiet-c1381.html"
    ],
    # Grade 9
    "9": [
        "https://loigiaihay.com/soan-van-9-canh-dieu-c1742.html",
        "https://loigiaihay.com/soan-van-9-chan-troi-sang-tao-c1743.html",
        "https://loigiaihay.com/soan-van-9-ket-noi-tri-thuc-c1740.html"
    ]
}

IGNORED_URL_PATTERNS = ["kiem-tra", "on-tap", "thuc-hanh", "noi-va-nghe", "viet", "vbt", "vo-bai-tap"]

def is_valid_lesson(url):
    for pattern in IGNORED_URL_PATTERNS:
        if pattern in url:
            return False
    # Only keep typical text-reading URLs: soan-bai, van-ban, tieng-viet, hoc-tot
    if "soan-bai" in url or "van-ban" in url or "tieng-viet" in url or "doc-hieu" in url:
        return True
    return False

def create_grounding(start, end, block_idx, element_type, doc_id):
    return f"span{{{start}:{end}:{block_idx}:{element_type}::{doc_id}}}"

def create_extraction(c_score, i_score, generator):
    return {"confidence_score": c_score, "importance_score": i_score, "generator": generator}

async def fetch_html(session, url, sem):
    async with sem:
        try:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    html = await response.read()
                    return html.decode('utf-8', 'ignore')
        except Exception as e:
            print(f"[!] Fetch Error: {url} -> {e}")
    return ""

async def crawl_lesson_text(session, url, title, grade, sem):
    html = await fetch_html(session, url, sem)
    if not html: return []
    
    soup = BeautifulSoup(html, 'html.parser')
    main_content = soup.find('div', class_='box-content')
    if not main_content:
        # Fallback if different class
        main_content = soup.find('div', id='box-content')
    
    if not main_content: return []

    doc_id = f"doc_grade{grade}_lgh_" + hashlib.md5(url.encode()).hexdigest()[:8]
    nodes = []
    char_counter = 0
    dom_order = 0

    for element in main_content.find_all(['p', 'div', 'br']):
        text = element.get_text(separator='\n', strip=True)
        text = unicodedata.normalize('NFC', text)
        if not text or len(text) < 20: continue
        
        # negative filters
        if "Loigiaihay.com" in text or "Bài tiếp theo" in text or "Bài trước" in text:
            continue
            
        length = len(text)
        node_id = f"node_{doc_id}_blk{dom_order}"
        clean_title = unicodedata.normalize('NFC', title)
        
        ctx_text = f"Tài liệu Ngữ Văn / Tiếng Việt {grade}. Lớp {grade}. Bài: {clean_title}.\n{text}"
        
        grounding = create_grounding(char_counter, char_counter + length, dom_order, element.name, doc_id)
        extraction = create_extraction(1.0, 1.0, "loigiaihay_mass_crawler")
        
        nodes.append({
            "node_label": "Passage_Span",
            "node_id": node_id,
            "raw_text": text,
            "contextualized_text": ctx_text,
            "title": clean_title,
            "source": "loigiaihay",
            "url": url,
            "dom_order": dom_order,
            "grounding": grounding,
            "extraction": extraction
        })
        char_counter += length
        dom_order += 1
    
    return nodes

async def crawl_seed(session, seed_url, grade, sem):
    html = await fetch_html(session, seed_url, sem)
    if not html: return []
    
    soup = BeautifulSoup(html, 'html.parser')
    lesson_links = []
    
    for a in soup.find_all('a'):
        href = a.get('href')
        if not href: continue
        
        full_url = "https://loigiaihay.com" + href if href.startswith('/') else href
        if not full_url.startswith("https://loigiaihay.com"): continue
            
        title = a.get_text(strip=True)
        if not title: continue
            
        if is_valid_lesson(href):
            lesson_links.append((full_url, title))
            
    # Deduplicate
    unique_lessons = list({link: title for link, title in lesson_links}.items())
    print(f"[{seed_url}] Found {len(unique_lessons)} potential lessons.")
    
    tasks = []
    for link, title in unique_lessons:
        tasks.append(crawl_lesson_text(session, link, title, grade, sem))
        
    results = await asyncio.gather(*tasks)
    
    # Flatten list
    all_nodes = []
    for nodes in results:
        all_nodes.extend(nodes)
        
    return all_nodes

async def main():
    sem = asyncio.Semaphore(15) # Concurrent connections limit
    
    output_dir = "/home/namnx/knowledgeforptalk/rag_edu/data/mass_corpus"
    os.makedirs(output_dir, exist_ok=True)
    
    async with aiohttp.ClientSession() as session:
        for grade, seeds in SEEDS.items():
            print(f"=== CRAWLING GRADE {grade} ===")
            tasks = [crawl_seed(session, url, grade, sem) for url in seeds]
            results = await asyncio.gather(*tasks)
            
            grade_nodes = []
            for r in results: grade_nodes.extend(r)
            
            # Deduplicate nodes by text to reduce size heavily!
            seen_texts = set()
            unique_nodes = []
            for node in grade_nodes:
                if node['raw_text'] not in seen_texts:
                    seen_texts.add(node['raw_text'])
                    unique_nodes.append(node)
            
            out_file = os.path.join(output_dir, f"grade_{grade}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(unique_nodes, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Saved {len(unique_nodes)} unique nodes for Grade {grade} to {out_file}.")

if __name__ == "__main__":
    asyncio.run(main())
