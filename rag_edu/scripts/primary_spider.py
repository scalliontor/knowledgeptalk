import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import hashlib
import unicodedata
import os
import re

SEEDS = {
    "1": ["https://loigiaihay.com/sgk-tieng-viet-1-canh-dieu-c1350.html", "https://loigiaihay.com/sgk-tieng-viet-1-chan-troi-sang-tao-c1186.html", "https://loigiaihay.com/sgk-tieng-viet-1-ket-noi-tri-thuc-voi-cuoc-song-c1181.html"],
    "2": ["https://loigiaihay.com/tieng-viet-2-canh-dieu-c636.html", "https://loigiaihay.com/tieng-viet-2-chan-troi-sang-tao-c639.html", "https://loigiaihay.com/tieng-viet-2-ket-noi-tri-thuc-voi-cuoc-song-c640.html"],
    "3": ["https://loigiaihay.com/tieng-viet-3-canh-dieu-c849.html", "https://loigiaihay.com/tieng-viet-3-chan-troi-sang-tao-c848.html", "https://loigiaihay.com/tieng-viet-3-ket-noi-tri-thuc-c847.html"],
    "4": ["https://loigiaihay.com/tieng-viet-4-canh-dieu-c1437.html", "https://loigiaihay.com/tieng-viet-4-chan-troi-sang-tao-c1436.html", "https://loigiaihay.com/tieng-viet-4-ket-noi-tri-thuc-c1424.html"],
    "5": ["https://loigiaihay.com/tieng-viet-5-canh-dieu-c1788.html", "https://loigiaihay.com/tieng-viet-5-chan-troi-sang-tao-c1787.html", "https://loigiaihay.com/tieng-viet-5-ket-noi-tri-thuc-c1786.html"]
}

IGNORED_PATTERNS = [
    "luyen-tap", "tim-hieu", "viet", "doc-mo-rong", "on-tap", "thu-tin", "goc-sang-tao", 
    "ke-chuyen", "tu-va-cau", "chinh-ta", "tap-lam-van", "kiem-tra", "nghe-viet",
    "mo-rong-von-tu", "luyen-tu", "danh-tu", "dong-tu", "tinh-tu", "dai-tu", "viet-bai"
]

def is_valid_primary_lesson(url):
    for pat in IGNORED_PATTERNS:
        if pat in url: return False
    # Needs to be a lesson link: e.g., bai-1-thanh-am-cua-gio-...
    if "-bai-" in url or re.match(r'^/bai-\d+', url):
        return True
    return False

def create_grounding(s, e, b, t, doc_id):
    return f"span{{{s}:{e}:{b}:{t}::{doc_id}}}"

async def fetch_html(session, url, sem):
    async with sem:
        try:
            async with session.get(url, timeout=10) as r:
                if r.status == 200: return (await r.read()).decode('utf-8', 'ignore')
        except: pass
    return ""

async def crawl_lesson(session, url, title, grade, sem):
    html = await fetch_html(session, url, sem)
    if not html: return []
    soup = BeautifulSoup(html, 'html.parser')
    
    # In primary grades, reading text is also in box-content, usually at the beginning!
    main_col = soup.find('div', id='box-content')
    if not main_col: return []
    
    doc_id = f"doc_grade{grade}_" + hashlib.md5(url.encode()).hexdigest()[:8]
    nodes = []
    dom_order, char_counter = 0, 0
    
    for p in main_col.find_all(['p', 'div']):
        text = p.get_text(separator=' ', strip=True)
        text = unicodedata.normalize('NFC', text)
        if len(text) < 20: continue
        
        # Stop early when hitting QA
        if "Lời giải chi tiết:" in text or "Phương pháp giải:" in text or "Trả lời câu" in text:
            break
            
        ctx = f"Tiếng Việt Lớp {grade}. Bài đọc: {title}. \n{text}"
        node = {
            "node_label": "Passage_Span", "node_id": f"{doc_id}_{dom_order}",
            "raw_text": text, "contextualized_text": ctx, "title": title,
            "url": url, "dom_order": dom_order,
            "grounding": create_grounding(char_counter, char_counter+len(text), dom_order, p.name, doc_id),
            "extraction": {"confidence_score": 1.0, "importance_score": 1.0, "generator": "primary_crawler"}
        }
        nodes.append(node)
        char_counter += len(text)
        dom_order += 1
    return nodes

async def process_seed(session, seed_url, grade, sem):
    html = await fetch_html(session, seed_url, sem)
    if not html: return []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Level 1: Find Volume Links OR direct Lesson Links
    links_to_scan = [seed_url]
    for a in soup.find_all('a'):
        href = a.get('href')
        if not href or '-e' not in href or 'tap' not in href: continue
        full_url = "https://loigiaihay.com" + href if href.startswith('/') else href
        if full_url not in links_to_scan: links_to_scan.append(full_url)
        
    lesson_links = {}
    for scan_url in links_to_scan:
        sub_html = await fetch_html(session, scan_url, sem)
        if not sub_html: continue
        sub_soup = BeautifulSoup(sub_html, 'html.parser')
        
        for a in sub_soup.find_all('a'):
            href = a.get('href')
            if not href: continue
            if is_valid_primary_lesson(href):
                full_url = "https://loigiaihay.com" + href if href.startswith('/') else href
                title = a.get_text(strip=True).split(' - ')[0] if ' - ' in a.get_text() else a.get_text(strip=True)
                lesson_links[full_url] = title
                
    print(f"[Grade {grade}] Found {len(lesson_links)} primary reading lessons.")
    
    # Process them
    tasks = [crawl_lesson(session, u, t, grade, sem) for u, t in lesson_links.items()]
    results = await asyncio.gather(*tasks)
    
    all_nodes = []
    for r in results: all_nodes.extend(r)
    return all_nodes

async def main():
    sem = asyncio.Semaphore(15)
    out_dir = "/mnt/DA0054DE0054C365/STEAM_LAB/cloud_ptalk/Knowledgeforptalk/rag_edu/data/mass_corpus"
    async with aiohttp.ClientSession() as session:
        for grade in range(1, 6):
            grade_str = str(grade)
            tasks = [process_seed(session, url, grade_str, sem) for url in SEEDS[grade_str]]
            results = await asyncio.gather(*tasks)
            nodes = []
            for r in results: nodes.extend(r)
            
            # Save
            if nodes:
                out_path = os.path.join(out_dir, f'clean_grade_{grade}.json')
                with open(out_path, 'w', encoding='utf-8') as f:
                    json.dump(nodes, f, ensure_ascii=False, indent=2)
                print(f"✅ Grade {grade}: Saved {len(nodes)} perfectly clean reading nodes.")

if __name__ == "__main__":
    asyncio.run(main())
