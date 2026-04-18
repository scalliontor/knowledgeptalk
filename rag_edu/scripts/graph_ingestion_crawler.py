import os
import requests
import json
import re
from bs4 import BeautifulSoup, NavigableString
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Literal
from openai import OpenAI

# ---------------------------------------------------------
# GRAPH SCHEMA MODELS
# ---------------------------------------------------------
class Grounding(BaseModel):
    source_document_id: str
    char_start: int
    char_end: int
    dom_order: int
    tag_name: str

class Extraction(BaseModel):
    method: Literal["rule_based", "llm_classification", "rule_llm_hybrid"]
    label_confidence: float
    boundary_confidence: float

class PassageSpan(BaseModel):
    node_id: str
    node_label: Literal["Passage_Span"] = "Passage_Span"
    metadata: Dict
    raw_text: str
    contextualized_text: Optional[str] = None
    grounding: Grounding
    extraction: Extraction
    edges: List[Dict] = []

class Question(BaseModel):
    node_id: str
    node_label: Literal["Question"] = "Question"
    metadata: Dict
    question_metadata: Dict
    raw_text: str
    contextualized_text: Optional[str] = None
    grounding: Grounding
    extraction: Extraction
    edges: List[Dict] = []

class Solution(BaseModel):
    node_id: str
    node_label: Literal["Solution"] = "Solution"
    pedagogical_policy: Dict
    raw_text: str
    contextualized_text: Optional[str] = None
    grounding: Grounding
    extraction: Extraction
    edges: List[Dict] = []

# ---------------------------------------------------------
# TIER 1: RULE-BASED DOM PARSING
# ---------------------------------------------------------
class VietjackParser:
    def __init__(self, url: str, book_manifest: dict):
        self.url = url
        self.doc_id = f"vietjack_{url.split('/')[-1].replace('.jsp', '')}"
        self.book_manifest = book_manifest
        self.html_content = ""
        self.soup = None
        self.blocks = []

    def fetch(self):
        print(f"[FETCH] Loading {self.url}...")
        res = requests.get(self.url)
        res.encoding = 'utf-8'
        self.html_content = res.text
        self.soup = BeautifulSoup(self.html_content, 'html.parser')

    def extract_dom_blocks(self):
        """Tier 1: Traverse the DOM and apply negative filtering & strict heuristic tags."""
        print("[PARSE] Traversing DOM and chunking by paragraph/headings...")
        article = self.soup.find('article') or self.soup.find('div', class_='content')
        if not article:
            print("Could not find main article body.")
            return

        char_offset = 0
        dom_order = 0
        
        for element in article.descendants:
            if isinstance(element, NavigableString):
                continue
            
            if element.name in ['p', 'h2', 'h3', 'h4', 'ul', 'div', 'blockquote']:
                # Skip if nested inside another block we already captured
                valid_parents = ['article', 'div', 'body']
                parent_name = element.parent.name if element.parent else ''
                # Only grab top-level recognizable blocks
                if element.name == 'p' and parent_name not in ['div', 'article']:
                    continue
                
                text = element.get_text(separator=' ', strip=True)
                if not text or len(text) < 15:
                    continue

                if self._is_garbage(text, element.name):
                    continue

                heuristic_label = self._apply_tier1_heuristics(text, element.name)
                
                block_len = len(text)
                self.blocks.append({
                    "raw_text": text,
                    "tag_name": element.name,
                    "dom_order": dom_order,
                    "char_start": char_offset,
                    "char_end": char_offset + block_len,
                    "hard_label": heuristic_label
                })
                
                char_offset += block_len + 1
                dom_order += 1

        print(f"[PARSE] Extracted {len(self.blocks)} clean blocks.")

    def _is_garbage(self, text: str, tag: str) -> bool:
        text_lower = text.lower()
        garbage_patterns = [
            "xem thêm", "các bài giải", "quảng cáo", "mục lục",
            "hot sale", "sách cấp tốc", "trang trước", "trang sau",
            "adsbygoogle", "top 20", "tổng hợp đề thi", "toán - văn - anh"
        ]
        if tag in ['h1', 'header', 'nav', 'footer']:
            return True
        for p in garbage_patterns:
            if p in text_lower:
                return True
            
        # specifically drop script/style leftovers
        if "function()" in text_lower or "window." in text_lower:
            return True
            
        return False

    def _apply_tier1_heuristics(self, text: str, tag: str) -> Optional[str]:
        text_lower = text.lower()
        if re.match(r'^câu\s+\d+.*', text_lower) or re.match(r'^trả lời câu hỏi\s*\d+', text_lower):
            return "QUESTION"
        if text_lower.startswith("trả lời:") or text_lower.startswith("lời giải chi tiết:"):
            return "SOLUTION"
        if text_lower.startswith("hướng dẫn giải") or text_lower.startswith("phương pháp giải:"):
            return "EDITORIAL_INTRO"
        if tag in ['h2', 'h3'] and ("soạn bài" in text_lower or "hướng dẫn phân tích" in text_lower):
            return "EDITORIAL_INTRO"
            
        return None  # Needs LLM classification

# ---------------------------------------------------------
# TIER 2: LLM CLASSIFICATION & ASSEMBLY
# ---------------------------------------------------------
class GraphAssembler:
    def __init__(self, blocks: list, manifest: dict):
        self.blocks = blocks
        self.manifest = manifest
        self.client = OpenAI(
            base_url="http://localhost:8080/v1",
            api_key="gemma4-openclaw-2026"
        )

    def classify_with_llm(self, text: str) -> dict:
        prompt = f"""Bạn là chuyên gia bóc tách dữ liệu SGK Ngữ Văn. Phân loại đoạn văn bản sau trích từ một bài soạn văn trên mạng.
Văn bản: "{text}"

Nhiệm vụ: Chọn MỘT trong các nhãn sau (trả về đúng định dạng JSON):
- TEXT_PASSAGE: Văn bản văn học, thơ, truyện ngắn được trích dẫn (ngữ liệu).
- QUESTION: Câu hỏi bài tập SGK.
- SOLUTION: Lời giải, đáp án.
- CONCEPT_EXPLANATION: Giải thích lý thuyết, khái niệm từ vựng/ngữ pháp.
- EDITORIAL_INTRO: Phần lời dẫn của website, tác giả ("Sau đây là bài soạn...", "Nội dung bài...").
- NOISE: Rác web, quảng cáo.

Trả về JSON ĐÚNG cấu trúc:
{{"label": "<Nhãn_đã_chọn>", "confidence": 0.95}}"""

        try:
            response = self.client.chat.completions.create(
                model="gemma-4",
                messages=[
                    {"role": "system", "content": "You are a precise data extraction AI. Output strictly valid JSON without markdown wrapping."},
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
            print(f"[LLM ERR] {e}")
            return {"label": "NOISE", "confidence": 0.0}

    def run_assembly(self):
        print("\n[ASSEMBLY] Applying Tier 2 Classification & Constructing Edges...")
        nodes = []
        last_question_id = None
        
        for i, b in enumerate(self.blocks):
            label = b['hard_label']
            confidence = 1.0
            extraction_method = "rule_based"
            
            if not label:
                res = self.classify_with_llm(b['raw_text'])
                label = res.get("label", "NOISE")
                confidence = res.get("confidence", 0.7)
                extraction_method = "llm_classification"
            
            b['final_label'] = label
            
            # Skip noise
            if label in ["NOISE", "EDITORIAL_INTRO", "RELATED_CONTENT"]:
                continue
                
            node_id = f"node_{self.manifest['book_id']}_{self.manifest['page_start']}_blk{b['dom_order']}"
            
            # Build Contextualized Text
            base_ctx = f"SGK Ngữ Văn 9 Tập 2 CTST, {self.manifest['unit_id']}, trang {self.manifest['page_start']}."
            
            grounding = Grounding(
                source_document_id=f"doc_{self.manifest['book_id']}_{self.manifest['page_start']}",
                char_start=b['char_start'],
                char_end=b['char_end'],
                dom_order=b['dom_order'],
                tag_name=b['tag_name']
            )
            
            extraction = Extraction(
                method=extraction_method,
                label_confidence=confidence,
                boundary_confidence=0.9
            )
            
            if label == "QUESTION":
                ctx_text = f"{base_ctx} Câu hỏi: {b['raw_text']}"
                q = Question(
                    node_id=node_id,
                    metadata=self.manifest,
                    question_metadata={"requires_source_text": True},
                    raw_text=b['raw_text'],
                    contextualized_text=ctx_text,
                    grounding=grounding,
                    extraction=extraction
                )
                nodes.append(q.dict())
                last_question_id = node_id
                
            elif label == "SOLUTION":
                ctx_text = f"{base_ctx} Lời giải: {b['raw_text']}"
                edges = []
                if last_question_id:
                     edges.append({"relation_type": "SOLVES", "target_id": last_question_id})
                     
                s = Solution(
                    node_id=node_id,
                    pedagogical_policy={"direct_exposure_to_student": "restricted"},
                    raw_text=b['raw_text'],
                    contextualized_text=ctx_text,
                    grounding=grounding,
                    extraction=extraction,
                    edges=edges
                )
                nodes.append(s.dict())
                
            elif label == "TEXT_PASSAGE":
                ctx_text = f"{base_ctx} Ngữ liệu: {b['raw_text']}"
                p = PassageSpan(
                    node_id=node_id,
                    metadata=self.manifest,
                    raw_text=b['raw_text'],
                    contextualized_text=ctx_text,
                    grounding=grounding,
                    extraction=extraction
                )
                nodes.append(p.dict())

        # Write to Output File
        out_path = "/home/namnx/knowledgeforptalk/rag_edu/data/graph_nodes_sample.json"
        
        # Fallback to local directory if not running on server
        if not os.path.exists("/home/namnx/knowledgeforptalk"):
            out_path = "graph_nodes_sample.json"
            
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(nodes, f, ensure_ascii=False, indent=2)
            
        print(f"\n[SUCCESS] Assembled {len(nodes)} Graph Nodes and saved to {out_path}.")

if __name__ == "__main__":
    url = "https://vietjack.com/soan-van-lop-9-ct/viet-mot-truyen-ke-sang-tao.jsp"
    manifest = {
        "book_id": "NV9_CTST_V2",
        "unit_id": "Unit_6",
        "module_type": "Module_Writing",
        "page_start": 56
    }
    
    parser = VietjackParser(url, manifest)
    parser.fetch()
    parser.extract_dom_blocks()
    
    assembler = GraphAssembler(parser.blocks, manifest)
    assembler.run_assembly()
