import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import hashlib
import unicodedata
import os
import re
from urllib.parse import urljoin

SEEDS = {
    # Grade 6
    "6": {
        "cd": "https://vietjack.com/soan-van-6-cd/index.jsp",
        "ct": "https://vietjack.com/soan-van-6-ct/index.jsp",
        "kn": "https://vietjack.com/soan-van-6-kn/index.jsp"
    },
    # Grade 7
    "7": {
        "cd": "https://vietjack.com/soan-van-7-cd/index.jsp",
        "ct": "https://vietjack.com/soan-van-7-ct/index.jsp",
        "kn": "https://vietjack.com/soan-van-7-kn/index.jsp"
    },
    # Grade 8
    "8": {
        "cd": "https://vietjack.com/soan-van-8-cd/index.jsp",
        "ct": "https://vietjack.com/soan-van-8-ct/index.jsp",
        "kn": "https://vietjack.com/soan-van-8-kn/index.jsp"
    },
    # Grade 9
    "9": {
        "cd": "https://vietjack.com/soan-van-9-cd/index.jsp",
        "ct": "https://vietjack.com/soan-van-9-ct/index.jsp",
        "kn": "https://vietjack.com/soan-van-9-kn/index.jsp"
    }
}

def to_safe_id(text):
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = text.lower()
    text = re.sub(r'[^a-z0-9_]+', '_', text)
    return text.strip('_')

async def fetch_html(session, url, sem):
    async with sem:
        try:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    html = await response.read()
                    return html.decode('utf-8', 'ignore')
        except Exception as e:
            return ""
    return ""

async def crawl_qa(session, url, grade, book, sem):
    html = await fetch_html(session, url, sem)
    if not html: return []
    
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    if not h1: return []
    
    # Extract Title "Soạn bài Nhớ rừng" -> "Nhớ rừng"
    raw_title = h1.get_text(strip=True)
    clean_title = re.sub(r'^(Soạn bài|Văn bản thô|Tóm tắt|Soạn văn)\s+', '', raw_title, flags=re.IGNORECASE)
    clean_title = re.sub(r' - Ngắn gọn.*', '', clean_title)
    
    dedupe_key = f"text_passage|{to_safe_id(clean_title)}|G{grade}_{book.upper()}"
    
    main_col = soup.find('div', class_='middle-col')
    if not main_col: return []

    nodes = []
    
    current_q_text = []
    current_s_text = []
    state = 0 # 0=Scan, 1=In_Question, 2=In_Solution
    q_num = 1
    
    doc_id = "doc_vj_" + hashlib.md5(url.encode()).hexdigest()[:8]
    dom_order = 0
    char_counter = 0

    for elem in main_col.find_all(['p', 'h3', 'ul', 'ol', 'table']):
        text = elem.get_text(separator='\n', strip=True)
        if not text: continue
            
        is_q_header = re.search(r'^(Câu\s*\d+|Câu hỏi)\s*\(.*?\)', text, re.IGNORECASE)
        is_a_header = re.match(r'^(Trả lời|Hướng dẫn giải):?', text, re.IGNORECASE)
        
        if is_q_header:
            # Save previous QA if exists
            if state == 2 and current_q_text and current_s_text:
                q_text_full = "\n".join(current_q_text)
                s_text_full = "\n".join(current_s_text)
                
                q_id = f"question_{q_num}_{doc_id}"
                nodes.append({
                    "node_id": q_id,
                    "node_label": "Question",
                    "metadata": {"book_id": f"G{grade}_{book.upper()}", "academic_role": "analysis_question"},
                    "raw_text": q_text_full,
                    "edges": [{"relation_type": "USES_TEXT", "target_id": dedupe_key}]
                })
                
                nodes.append({
                    "node_id": f"solution_{q_num}_{doc_id}",
                    "node_label": "Solution",
                    "pedagogical_policy": {"direct_exposure_to_student": "restricted", "requires_hint_first": True},
                    "raw_text": s_text_full,
                    "edges": [{"relation_type": "SOLVES", "target_id": q_id}]
                })
                q_num += 1
            
            state = 1
            current_q_text = [text]
            current_s_text = []
        elif is_a_header:
            state = 2
            if not text.lower() in ['trả lời:', 'hướng dẫn giải:', 'trả lời', 'hướng dẫn giải']:
                # The answer might be on the same line as "Trả lời: ABC"
                ans_text = re.sub(r'^(Trả lời|Hướng dẫn giải):\s*', '', text, flags=re.IGNORECASE)
                if ans_text: current_s_text.append(ans_text)
        else:
            if state == 1:
                current_q_text.append(text)
            elif state == 2:
                current_s_text.append(text)

    # Save last QA
    if state == 2 and current_q_text and current_s_text:
        q_text_full = "\n".join(current_q_text)
        s_text_full = "\n".join(current_s_text)
        q_id = f"question_{q_num}_{doc_id}"
        nodes.append({
            "node_id": q_id,
            "node_label": "Question",
            "metadata": {"book_id": f"G{grade}_{book.upper()}", "academic_role": "analysis_question"},
            "raw_text": q_text_full,
            "edges": [{"relation_type": "USES_TEXT", "target_id": dedupe_key}]
        })
        nodes.append({
            "node_id": f"solution_{q_num}_{doc_id}",
            "node_label": "Solution",
            "pedagogical_policy": {"direct_exposure_to_student": "restricted", "requires_hint_first": True},
            "raw_text": s_text_full,
            "edges": [{"relation_type": "SOLVES", "target_id": q_id}]
        })

    return nodes

async def crawl_book_index(session, base_url, grade, book, sem):
    html = await fetch_html(session, base_url, sem)
    if not html: return []
    soup = BeautifulSoup(html, 'html.parser')
    
    tasks = []
    # Vietjack lesson links are often local to index.jsp e.g. <a href="nho-rung.jsp">
    main_ul = soup.find('ul', class_='list')
    if not main_ul:
        # Alternative find logic
        a_tags = soup.find_all('a')
    else:
        a_tags = main_ul.find_all('a')
        
    unique_links = set()
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if not href or href.endswith('index.jsp') or href.endswith('/'): continue
        if href.startswith('http') and 'vietjack.com' not in href: continue
        
        full_url = urljoin(base_url, href)
        if "phan-tich" in full_url or "soan-bai" in full_url or "nho-rung" in full_url or ".jsp" in full_url:
            unique_links.add(full_url)
            
    print(f"[{grade}-{book.upper()}] Found {len(unique_links)} potential lessons from {base_url}")
    
    for url in list(unique_links)[:100]: # Cap to 100 max per book for safety/test
        tasks.append(crawl_qa(session, url, grade, book, sem))
        
    results = await asyncio.gather(*tasks)
    
    all_nodes = []
    for r in results: all_nodes.extend(r)
    return all_nodes

async def main():
    sem = asyncio.Semaphore(15)
    output_dir = "/home/namnx/knowledgeforptalk/rag_edu/data/mass_corpus"
    os.makedirs(output_dir, exist_ok=True)
    
    async with aiohttp.ClientSession() as session:
        all_nodes = []
        for grade, books in SEEDS.items():
            print(f"=== CRAWLING QA GRADE {grade} ===")
            for book, url in books.items():
                print(f"-> {grade} {book}: {url}")
                nodes = await crawl_book_index(session, url, grade, book, sem)
                all_nodes.extend(nodes)
                
            out_file = os.path.join(output_dir, f"vietjack_qa_grade_{grade}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump([n for n in all_nodes if f"G{grade}" in n.get('metadata', {}).get('book_id', '')], f, ensure_ascii=False, indent=2)
            print(f"✅ QA nodes for Grade {grade} saved!")

if __name__ == "__main__":
    asyncio.run(main())
