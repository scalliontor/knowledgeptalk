import os
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
import traceback
import time

# --- Pydantic Models for Schema (Mocked as dicts for simple JSON dump) ---
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

class AsyncGraphIngester:
    def __init__(self):
        self.api_key = "gemma4-openclaw-2026"
        self.base_url = "http://localhost:8080/v1"
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        self.semaphore = asyncio.Semaphore(15) # Max 15 concurrent LLM calls
        
    async def fetch_html(self, session, url):
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            print(f"[FETCH ERROR] {url}: {e}")
        return None

    def tier1_filter(self, text, tag_name):
        # Additional robust tier 1 heuristics
        text_lower = text.lower()
        if "tóm tắt cốt truyện" in text_lower or "nội dung chính" in text_lower or "soạn bài" in text_lower:
            return "EDITORIAL_INTRO"
        if tag_name in ['h1', 'h2'] and "bài" in text_lower:
            return "EDITORIAL_INTRO"
        if text.startswith("Câu ") and ":" in text[:30]:
            return "QUESTION"
        if text.startswith("Trả lời:") or text.startswith("Lời giải:") or text.startswith("- "):
            return "SOLUTION"
        return None

    def extract_blocks_sync(self, html, doc_id):
        soup = BeautifulSoup(html, 'html.parser')
        main_content = soup.find('div', class_='middle-col') or soup.find('article') or soup.find('div', class_='content')
        if not main_content:
            return []

        # Remove boilerplates
        for bad in main_content.find_all(['script', 'style', 'nav', 'form', 'iframe', 'ins']):
            bad.decompose()
        for qc in main_content.find_all('div', class_='quang-cao'):
            qc.decompose()

        blocks = []
        char_counter = 0
        dom_order = 0
        
        for element in main_content.find_all(['p', 'h2', 'h3', 'h4', 'ul', 'div']):
            if element.name == 'div' and element.get('class') and 'box' not in element.get('class'):
                continue
            
            text = element.get_text(separator=' ', strip=True)
            if not text or len(text) < 15:
                continue
            if "Quảng cáo" in text or "Theo dõi chúng tôi" in text or "Bình luận" in text:
                continue

            length = len(text)
            hard_label = self.tier1_filter(text, element.name)

            blocks.append({
                "dom_order": dom_order,
                "raw_text": text,
                "tag_name": element.name,
                "char_start": char_counter,
                "char_end": char_counter + length,
                "hard_label": hard_label,
                "doc_id": doc_id
            })
            char_counter += length + 1
            dom_order += 1
            
        return blocks

    async def classify_with_llm(self, text: str) -> dict:
        prompt = f"""Bạn là chuyên gia bóc tách dữ liệu SGK Ngữ Văn. Phân loại đoạn văn bản sau.
Văn bản: "{text}"

Nhãn được chọn:
- TEXT_PASSAGE: Văn bản văn học được trích dẫn (ngữ liệu).
- QUESTION: Câu hỏi học tập.
- SOLUTION: Lời giải, đáp án.
- CONCEPT_EXPLANATION: Giải thích khái niệm học thuật.
- EDITORIAL_INTRO: Phần lời dẫn của website ("Sau đây là bài soạn...").
- NOISE: Rác web, quảng cáo.

Trả về cú pháp JSON duy nhất: {{"label": "<Nhãn_đã_chọn>", "confidence": 0.95}}"""

        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model="gemma-4",
                    messages=[
                        {"role": "system", "content": "You are a precise JSON classifier."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=60,
                    response_format={"type": "json_object"}
                )
                raw_res = response.choices[0].message.content.strip()
                if raw_res.startswith('```json'):
                    raw_res = raw_res.split('```json')[1].split('```')[0].strip()
                elif raw_res.startswith('```'):
                    raw_res = raw_res.split('```')[1].split('```')[0].strip()
                    
                return json.loads(raw_res)
            except Exception as e:
                return {"label": "NOISE", "confidence": 0.0}

    async def process_url(self, session, url_info):
        title, url = url_info
        print(f"[*] Fetching: {title} ...")
        html = await self.fetch_html(session, url)
        if not html:
            return []

        # Identifier
        doc_id = "doc_" + url.split("/")[-1].replace(".jsp", "")
        
        # CPU parse
        blocks = self.extract_blocks_sync(html, doc_id)
        if not blocks:
            return []

        print(f"    -> Extracted {len(blocks)} blocks for {doc_id}. Classifying...")
        
        # Parallel LLM evaluations for unmarked blocks
        tasks = []
        for b in blocks:
            if not b['hard_label']:
                tasks.append(self.classify_with_llm(b['raw_text']))
            else:
                tasks.append(asyncio.sleep(0)) # placeholder
        
        results = await asyncio.gather(*tasks)
        
        # Assembly
        nodes = []
        last_question_id = None
        
        for i, b in enumerate(blocks):
            label = b['hard_label']
            confidence = 1.0
            method = "rule_based"
            
            if not label:
                res = results[i]
                if isinstance(res, dict):
                    label = res.get("label", "NOISE")
                    confidence = res.get("confidence", 0.7)
                else:
                    label = "NOISE"
                method = "llm_classification"
                
            if label in ["NOISE", "EDITORIAL_INTRO", "RELATED_CONTENT"]:
                continue
                
            node_id = f"node_{doc_id}_blk{b['dom_order']}"
            base_ctx = f"SGK Ngữ Văn 9 CTST. Bài: {title}. "
            
            grounding = create_grounding(b['char_start'], b['char_end'], b['dom_order'], b['tag_name'], doc_id)
            extraction = create_extraction(confidence, 0.9, method)
            
            if label == "QUESTION":
                ctx_text = base_ctx + "Câu hỏi: " + b['raw_text']
                nodes.append({
                    "node_label": "Question",
                    "node_id": node_id,
                    "metadata": {"title": title, "url": url},
                    "raw_text": b['raw_text'],
                    "contextualized_text": ctx_text,
                    "grounding": grounding,
                    "extraction": extraction
                })
                last_question_id = node_id
                
            elif label == "SOLUTION":
                ctx_text = base_ctx + "Lời giải: " + b['raw_text']
                edges = []
                if last_question_id:
                    edges.append({"relation_type": "SOLVES", "target_id": last_question_id})
                nodes.append({
                    "node_label": "Solution",
                    "node_id": node_id,
                    "raw_text": b['raw_text'],
                    "contextualized_text": ctx_text,
                    "grounding": grounding,
                    "extraction": extraction,
                    "edges": edges
                })
                
            elif label in ["TEXT_PASSAGE", "CONCEPT_EXPLANATION"]:
                ctx_text = base_ctx + b['raw_text']
                nodes.append({
                    "node_label": "Passage_Span",
                    "node_id": node_id,
                    "raw_text": b['raw_text'],
                    "contextualized_text": ctx_text,
                    "grounding": grounding,
                    "extraction": extraction
                })
                
        print(f"    -> [SUCCESS] Assembly mapped {len(nodes)} Graph Nodes for {doc_id}.")
        return nodes

async def index_spider():
    print("[SPIDER] Scraping Index Page...")
    index_url = 'https://vietjack.com/soan-van-lop-9-ct/index.jsp'
    async with aiohttp.ClientSession() as session:
        async with session.get(index_url) as res:
            html = await res.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    valid_links = []
    for ul in soup.find_all('ul', class_='list'):
        for li in ul.find_all('li'):
            a = li.find('a')
            if a:
                href = a.get('href')
                text = a.text.strip()
                if href and href.endswith('.jsp') and not href.startswith('http'):
                    full_url = "https://vietjack.com/soan-van-lop-9-ct/" + href.split("/")[-1]
                    valid_links.append((text, full_url))
                    
    # Tập 2 = index [50:100] (starts at "Tri thức ngữ văn trang 5" which resets page numbering)
    tap2_links = valid_links[50:100]
    print(f"[SPIDER] Filtered to {len(tap2_links)} Tập 2 lesson links.")
    return tap2_links

async def main():
    t0 = time.time()
    targets = await index_spider()
    print(f"[SPIDER] Found targets. Using {len(targets)} links for this batch ingestion.")
    
    ingester = AsyncGraphIngester()
    all_nodes = []
    
    # Process URLs in chunks of 5 parallel items (to not blast Vietjack with too many concurrent requests)
    chunk_size = 5
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(targets), chunk_size):
            chunk = targets[i:i+chunk_size]
            tasks = [ingester.process_url(session, target) for target in chunk]
            results = await asyncio.gather(*tasks)
            for res in results:
                all_nodes.extend(res)
    
    # Save Output
    out_path = "mass_graph_nodes_NV9_CTST.json"
    if os.path.exists("/home/namnx/knowledgeforptalk/rag_edu/data"):
        out_path = "/home/namnx/knowledgeforptalk/rag_edu/data/mass_graph_nodes_NV9_CTST.json"
        
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_nodes, f, ensure_ascii=False, indent=2)
        
    t1 = time.time()
    print(f"\n======== REPORT ========")
    print(f"Total Nodes Extracted: {len(all_nodes)}")
    print(f"Time Taken: {t1-t0:.2f} seconds")
    print(f"File Saved: {out_path}")
    print(f"========================")

if __name__ == "__main__":
    asyncio.run(main())
