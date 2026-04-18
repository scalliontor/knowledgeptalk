import requests
from bs4 import BeautifulSoup
import json
import hashlib
import unicodedata

def create_grounding(start, end, block_idx, element_type, doc_id):
    return f"span{{{start}:{end}:{block_idx}:{element_type}::{doc_id}}}"

def create_extraction(c_score, i_score, generator):
    return {"confidence_score": c_score, "importance_score": i_score, "generator": generator}

def scrape_single(url, title):
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    main_content = soup.find('div', class_='box-content')
    if not main_content:
        return []

    doc_id = "doc_lgh_" + hashlib.md5(url.encode()).hexdigest()[:8]
    nodes = []
    char_counter = 0
    dom_order = 0

    for element in main_content.find_all(['p', 'div', 'br']):
        text = element.get_text(separator='\n', strip=True)
        text = unicodedata.normalize('NFC', text)
        if not text or len(text) < 20: continue
        if "Loigiaihay.com" in text or "Bài tiếp theo" in text or "Bài trước" in text: continue
            
        length = len(text)
        node_id = f"node_{doc_id}_blk{dom_order}"
        clean_title = unicodedata.normalize('NFC', title)
        ctx_text = f"SGK Ngữ Văn 9 CTST. Bài đọc: {clean_title}.\n{text}"
        
        grounding = create_grounding(char_counter, char_counter + length, dom_order, element.name, doc_id)
        extraction = create_extraction(1.0, 1.0, "loigiaihay_crawler")
        
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

nodes = scrape_single(
    "https://loigiaihay.com/soan-bai-dau-tranh-cho-mot-the-gioi-hoa-binh-sgk-ngu-van-9-tap-2-chan-troi-sang-tao-a161132.html",
    "Đấu tranh cho một thế giới hòa bình"
)
print(f"Extracted {len(nodes)} nodes.")
with open("single_passage.json", "w", encoding="utf-8") as f:
    json.dump(nodes, f, ensure_ascii=False, indent=2)
