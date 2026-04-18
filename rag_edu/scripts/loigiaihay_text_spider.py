import os
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time
import hashlib

def create_grounding(char_start, char_end, dom_order, tag_name, source_id):
    return {
        "source_document_id": source_id,
        "char_start": char_start,
        "char_end": char_end,
        "dom_order": dom_order,
        "tag_name": tag_name
    }

def create_extraction(label_confidence, boundary_confidence, method):
    return {
        "method": method,
        "label_confidence": label_confidence,
        "boundary_confidence": boundary_confidence
    }

async def fetch_html(session, url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 200:
                return await response.text()
    except Exception as e:
        print(f"[FETCH ERROR] {url}: {e}")
    return None

async def index_spider():
    print("[SPIDER] Scraping Loigiaihay Index Page...")
    index_url = 'https://loigiaihay.com/soan-van-9-chan-troi-sang-tao-tap-2-e34885.html'
    
    async with aiohttp.ClientSession() as session:
        html = await fetch_html(session, index_url)
        if not html:
            return []
            
        soup = BeautifulSoup(html, 'html.parser')
        valid_links = []
        
        # Loigiaihay puts lesson lists in `.list-articles` or similar. We just scan all <a> tags for "van-ban"
        for a in soup.find_all('a'):
            href = a.get('href')
            text = a.text.strip()
            if href and ('van-ban' in href):
                if href.startswith('/'):
                    full_url = "https://loigiaihay.com" + href
                else:
                    full_url = href
                
                # ONLY pick "van-ban" links which contain the reading texts directly!
                if 'van-ban' in full_url:
                    valid_links.append((text, full_url))
        
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for text, url in valid_links:
            if url not in seen:
                seen.add(url)
                deduped.append((text, url))
                
        print(f"[SPIDER] Found {len(deduped)} 'Văn bản' links.")
        return deduped

async def process_url(session, url_info):
    title, url = url_info
    print(f"[*] Fetching: {title} ...")
    html = await fetch_html(session, url)
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    
    # Try different selectors for main content in Loigiaihay
    main_content = soup.select_one('#box-content') or soup.select_one('.box-content')
    if not main_content:
        print(f"    -> [SKIP] No main content found for {url}")
        return []

    # Clean up garbage
    for bad in main_content.find_all(['script', 'style', 'nav', 'form', 'iframe', 'ins', 'svg', 'img']):
        bad.decompose()
    for adv in main_content.find_all('div', class_=['quangcao', 'box-adv']):
        adv.decompose()

    doc_id = "doc_lgh_" + hashlib.md5(url.encode()).hexdigest()[:8]
    
    nodes = []
    char_counter = 0
    dom_order = 0
    
    # Break the reading text into reasonably sized blocks (e.g. per paragraph)
    import unicodedata
    for element in main_content.find_all(['p', 'div', 'br']):
        text = element.get_text(separator='\n', strip=True)
        text = unicodedata.normalize('NFC', text)
        if not text or len(text) < 20:  # Skip very short stubs
            continue
        if "Loigiaihay.com" in text or "Bài tiếp theo" in text or "Bài trước" in text:
            continue
            
        length = len(text)
        node_id = f"node_{doc_id}_blk{dom_order}"
        
        # Clean up title: e.g. "Văn bản Nhớ Rừng (Thế Lữ) CTST" -> "Nhớ Rừng"
        clean_title = title.replace("Văn bản", "").replace("Văn bản", "").replace("CTST", "").strip()
        clean_title = unicodedata.normalize('NFC', clean_title)
        
        ctx_text = f"SGK Ngữ Văn 9 CTST. Bài đọc: {clean_title}.\n{text}"
        
        grounding = create_grounding(char_counter, char_counter + length, dom_order, element.name, doc_id)
        extraction = create_extraction(1.0, 1.0, "loigiaihay_crawler")
        
        nodes.append({
            "node_label": "Passage_Span",
            "node_id": node_id,
            "metadata": {"title": clean_title, "url": url},
            "raw_text": text,
            "contextualized_text": ctx_text,
            "grounding": grounding,
            "extraction": extraction
        })
        
        char_counter += length + 1
        dom_order += 1
        
        # We only want elements directly in the root to avoid nested parsing duplication
        # Just a simple hack: decompose after reading to avoid children being parsed again by iterate
        element.decompose()

    print(f"    -> [SUCCESS] Extracted {len(nodes)} Passage_Span nodes.")
    return nodes

async def main():
    t0 = time.time()
    targets = await index_spider()
    
    all_nodes = []
    chunk_size = 3
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(targets), chunk_size):
            chunk = targets[i:i+chunk_size]
            tasks = [process_url(session, target) for target in chunk]
            results = await asyncio.gather(*tasks)
            for res in results:
                all_nodes.extend(res)
    
    out_path = "mass_graph_nodes_lgh_reading.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_nodes, f, ensure_ascii=False, indent=2)
        
    t1 = time.time()
    print(f"\n======== REPORT ========")
    print(f"Total Nodes: {len(all_nodes)}")
    print(f"Time Taken: {t1-t0:.2f} seconds")
    print(f"File Saved: {out_path}")
    print(f"========================")

if __name__ == "__main__":
    asyncio.run(main())
