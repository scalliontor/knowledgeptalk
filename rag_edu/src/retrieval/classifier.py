import re
from typing import Optional
from src.retrieval.taxonomy import QueryIntent, QueryContext
from src.llm import generate_json

class QueryClassifier:
    """Classifies user queries to appropriate intents using rule-based and LLM approaches."""
    
    GREETING_PATTERNS = [
        r'^(chào|hi|hello|xin chào|chị ơi|anh ơi)\s*[\.\!\?]*$',
        r'^(con|em|mình)\s+(đây|đến rồi|về rồi)',
    ]
    WEEK_LOOKUP_PATTERNS = [
        r'tuần\s+(này|nay|hiện tại).*học.*gì',
        r'hôm nay.*học.*bài\s+gì',
    ]
    SPECIFIC_LESSON_PATTERNS = [
        r'bài\s+(\d+).*trang\s+(\d+)',
        r'trang\s+(\d+).*lớp\s+(\d+)',
    ]
    CONCEPT_PATTERNS = [
        r'(từ ghép|từ láy|danh từ|động từ|tính từ|câu kể|câu hỏi|câu cảm|dấu\s+\w+)\s+là\s+gì',
        r'phân biệt\s+(\w+)\s+(và|với)\s+(\w+)',
        r'khi nào (viết|dùng)',
        r'(thực hành tiếng việt|luyện từ)',
    ]
    WRITING_PATTERNS = [
        r'(tả|kể|viết|miêu tả).*(con|cây|người|cảnh|chuyện)',
        r'không biết (tả|kể|viết|làm)',
        r'giúp em (tả|kể|viết)',
        r'bài văn.*mẫu',
        r'văn mẫu',
        r'dàn ý',
    ]
    # lookup_reading patterns — checked AFTER writing to avoid conflicts
    READING_PATTERNS = [
        r'đọc\s+(bài\s+)?.+\s+cho\s+(em|con|mình|tớ)',
        r'đọc\s+(cho\s+(em|con|mình|tớ)\s+)?bài\s+',
        r'cho\s+(em|con|tớ)\s+nghe\s+bài',
        r'bài\s+đọc\s+',
        r'soạn\s+(bài|văn)\s+',
        r'soạn\s+bài\s+',
        r'phân\s+tích\s+bài\s+',
        r'phân\s+tích\s+tác\s+phẩm',
        r'cảm\s+nhận\s+(về\s+)?bài\s+',
        r'tóm\s+tắt\s+bài\s+',
        r'nội\s+dung\s+(bài|của)\s+',
        r'văn\s+bản\s+',
    ]

    def classify(self, query: str, user_profile: Optional[dict] = None) -> QueryContext:
        query_lower = query.lower().strip()
        user_profile = user_profile or {}
        
        fast_result = self._try_rule_based(query_lower, user_profile)
        if fast_result:
            fast_result.user_grade = user_profile.get("lop")
            fast_result.user_book_series = user_profile.get("bo_sach_chinh")
            return fast_result
            
        # Vô hiệu hóa LLM phân loại Intent theo yêu cầu để tăng tốc (chỉ giữ rule-based)
        # Fallback về LOOKUP_READING để Semantic Search quét nội dung.
        return QueryContext(
            raw_query=query,
            intent=QueryIntent.LOOKUP_READING,
            lesson_name=self._extract_lesson_name(query.lower()),
            user_grade=user_profile.get("lop"),
            user_book_series=user_profile.get("bo_sach_chinh"),
            confidence=0.4
        )
    def _try_rule_based(self, query: str, user_profile: dict = {}) -> Optional[QueryContext]:
        for pat in self.GREETING_PATTERNS:
            if re.search(pat, query):
                return QueryContext(raw_query=query, intent=QueryIntent.GREETING)
                
        for pat in self.WEEK_LOOKUP_PATTERNS:
            if re.search(pat, query):
                return QueryContext(raw_query=query, intent=QueryIntent.LOOKUP_CURRICULUM)
                
        for pat in self.SPECIFIC_LESSON_PATTERNS:
            m = re.search(pat, query)
            if m:
                ctx = QueryContext(raw_query=query, intent=QueryIntent.LOOKUP_SPECIFIC)
                numbers = [int(x) for x in re.findall(r'\d+', query)]
                if numbers:
                    ctx.page = numbers[0]
                grade_m = re.search(r'lớp\s+(\d+)', query)
                if grade_m:
                    ctx.grade = int(grade_m.group(1))
                return ctx
                
        for pat in self.CONCEPT_PATTERNS:
            m = re.search(pat, query)
            if m:
                ctx = QueryContext(raw_query=query, intent=QueryIntent.EXPLAIN_CONCEPT)
                ctx.concept = m.group(1) if m.groups() else None
                return ctx
                
        for pat in self.WRITING_PATTERNS:
            if re.search(pat, query):
                ctx = QueryContext(raw_query=query, intent=QueryIntent.WRITING_OUTLINE)
                if re.search(r'tả.*cây', query):
                    ctx.writing_type = "ta_cay"
                elif re.search(r'tả.*con\s+\w+', query):
                    ctx.writing_type = "ta_con_vat"
                elif re.search(r'tả.*người', query):
                    ctx.writing_type = "ta_nguoi"
                elif re.search(r'kể.*chuyện', query):
                    ctx.writing_type = "ke_chuyen"
                return ctx

 
        return None

    def _extract_lesson_name(self, query: str) -> Optional[str]:
        cleaned = re.sub(
            r'^(đọc\s+(cho\s+(em|con|mình|tớ)\s+)?(bài\s+)?|'
            r'soạn\s+(bài\s+)?|phân\s+tích\s+(bài\s+)?|'
            r'cảm\s+nhận\s+(về\s+)?(bài\s+)?|tóm\s+tắt\s+(bài\s+)?|'
            r'nội\s+dung\s+(bài\s+)?|văn\s+bản\s+|cho\s+(em|con|tớ)\s+nghe\s+(bài\s+)?)',
            '', query.lower().strip()
        )
        cleaned = re.sub(r'\s+(cho\s+(em|con|mình|tớ)\s+nghe|nhé|đi|nào|ạ)\s*$', '', cleaned)
        cleaned = re.sub(r'lớp\s+\d+.*$', '', cleaned).strip()
        return cleaned if len(cleaned) > 2 else None

    def _llm_classify(self, query: str, user_profile: dict) -> QueryContext:
        prompt = f"""Phân loại câu hỏi của học sinh tiểu học và THCS.

Câu hỏi: "{query}"
Thông tin HS: lớp {user_profile.get('lop', '?')}, bộ sách {user_profile.get('bo_sach_chinh', '?')}

Các intent có thể:
- lookup_reading: hỏi nội dung bài đọc, soạn văn, phân tích tác phẩm THCS
- lookup_curriculum: hỏi chương trình tuần/môn
- explain_concept: hỏi khái niệm ngữ pháp
- writing_outline: xin hướng dẫn viết văn/dàn ý
- writing_sample: xin bài văn mẫu
- character_info: hỏi về nhân vật
- story_summary: tóm tắt
- greeting, encouragement, off_topic

Trả về JSON:
{{
  "intent": "<một trong các enum>",
  "grade": <số 1-9 hoặc null>,
  "book_series": "<KNTT|CTST|CD hoặc null>",
  "lesson_name": "<tên bài hoặc null>",
  "concept": "<khái niệm ngữ pháp hoặc null>",
  "writing_type": "<ta_cay|ta_con_vat|ta_nguoi|ke_chuyen hoặc null>",
  "search_query": "<câu hỏi được viết lại ngắn gọn thành từ khóa để query DB. ví dụ 'soạn bài Về thăm mẹ' -> 'về thăm mẹ'>",
  "confidence": <float 0-1>
}}
"""
        try:
            result = generate_json(prompt)
            if not result:
                raise ValueError("Empty LLM response")
        except Exception:
            # LLM unavailable → default to lookup_reading (semantic search will handle it)
            return QueryContext(
                raw_query=query,
                intent=QueryIntent.LOOKUP_READING,
                lesson_name=self._extract_lesson_name(query.lower()),
                user_grade=user_profile.get("lop"),
                user_book_series=user_profile.get("bo_sach_chinh"),
                confidence=0.4
            )
        
        intent_str = result.get("intent", "off_topic")
        try:
            intent_enum = QueryIntent(intent_str)
        except ValueError:
            intent_enum = QueryIntent.OFF_TOPIC

        return QueryContext(
            raw_query=query,
            intent=intent_enum,
            search_query_rewrite=result.get("search_query"),
            grade=result.get("grade"),
            book_series=result.get("book_series"),
            lesson_name=result.get("lesson_name"),
            concept=result.get("concept"),
            writing_type=result.get("writing_type"),
            confidence=result.get("confidence", 0.5),
            user_grade=user_profile.get("lop"),
            user_book_series=user_profile.get("bo_sach_chinh")
        )
