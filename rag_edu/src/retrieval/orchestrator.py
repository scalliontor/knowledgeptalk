from src.retrieval.taxonomy import QueryIntent, QueryContext, RetrievedItem
from src.retrieval.classifier import QueryClassifier
from src.retrieval.subject_detector import detect_subject
from src.retrieval.retrievers import CurriculumRetriever, SGKReadingRetriever, LanguageConceptRetriever, WritingOutlineRetriever, MathExerciseRetriever, KHTNRetriever, SocialScienceRetriever, GraphRetriever
from src.llm import generate_text

class RAGOrchestrator:
    def __init__(self, pg_conn, qdrant_client, embed_fn, classifier: QueryClassifier):
        self.classifier = classifier
        self.curriculum_retriever = CurriculumRetriever(pg_conn)
        self.reading_retriever = SGKReadingRetriever(pg_conn, qdrant_client, embed_fn)
        self.concept_retriever = LanguageConceptRetriever(pg_conn, qdrant_client, embed_fn)
        self.outline_retriever = WritingOutlineRetriever(pg_conn)
        self.math_exercise_retriever = MathExerciseRetriever(pg_conn, qdrant_client, embed_fn)
        self.khtn_retriever = KHTNRetriever(pg_conn, qdrant_client, embed_fn)
        self.social_retriever = SocialScienceRetriever(pg_conn, qdrant_client, embed_fn)
        self.graph_retriever = GraphRetriever()
        self.embed_fn = embed_fn
        
    def retrieve(self, query: str, user_profile: dict) -> tuple[QueryContext, list[RetrievedItem]]:
        # --- QUERY REWRITE LAYER (Gemma) ---
        rewrite_prompt = (
            "Viết lại câu hỏi sau thành các từ khóa ngắn gọn, tối ưu để tìm kiếm bằng Vector Search/Graph. "
            "Chỉ trả về câu viết lại, KHÔNG giải thích. Ví dụ: 'Đọc cho tớ bài cây tre quê tôi' -> 'văn bản Cây tre quê hương'."
        )
        try:
            # Tăng timeout lên 2.5s để đủ thời gian sinh ra text
            rewritten_query = generate_text(rewrite_prompt, f"Câu hỏi: {query}", max_tokens=30, timeout=2.5).strip()
            if "Xin lỗi" in rewritten_query:
                rewritten_query = query
            rewritten_query = rewritten_query.replace('"', '').replace('Câu viết lại:', '').replace('Từ khóa:', '').strip()
            search_query = rewritten_query if rewritten_query and len(rewritten_query) > 2 else query
        except:
            search_query = query

        subject, _ = detect_subject(search_query, user_profile)
        user_profile["subject_detected"] = subject
        ctx = self.classifier.classify(search_query, user_profile)
        
        print(f"[RAG] Original: '{query}' -> Rewrite: '{search_query}' | Intent: {ctx.intent.value}")
        
        # === COMPUTE EMBEDDING EXACTLY ONCE! ===
        query_vector = self.embed_fn(search_query)
        
        # === Intent-based subject override (Aggressive) ===
        # If the LLM classifier confidently identifies a literature intent,
        # FORCE override subject to ngu_van, wiping out any bad regex detections (e.g. 'phân tích' -> toán).
        if ctx.intent in (QueryIntent.LOOKUP_READING, QueryIntent.CHARACTER_INFO,
                          QueryIntent.STORY_SUMMARY, QueryIntent.EXPLAIN_CONCEPT,
                          QueryIntent.WRITING_OUTLINE, QueryIntent.WRITING_SAMPLE):
            subject = "ngu_van"
            user_profile["subject_detected"] = subject
        
        effective_grade = ctx.grade or ctx.user_grade
        effective_book = ctx.book_series or ctx.user_book_series
        items = []
        
        if ctx.intent in (QueryIntent.GREETING, QueryIntent.ENCOURAGEMENT, QueryIntent.OFF_TOPIC):
            pass # No retrieval needed
            
        elif subject == "toan":
            # For Math, route to Math Retrievers
            ctx.intent = QueryIntent.LOOKUP_SPECIFIC
            items = self.math_exercise_retriever.semantic_search(search_query, grade=effective_grade, top_k=3)
            
        elif subject == "khtn":
            ctx.intent = QueryIntent.LOOKUP_SPECIFIC
            items = self.khtn_retriever.semantic_search(search_query, grade=effective_grade, top_k=3)
            
        elif subject in ["lich_su", "dia_li", "gdcd"]:
            ctx.intent = QueryIntent.LOOKUP_SPECIFIC
            items = self.social_retriever.semantic_search(search_query, grade=effective_grade, top_k=3)
            
        elif subject == "ngu_van" or subject == "tieng_viet":
            lesson = ctx.lesson_name or search_query

            if ctx.intent == QueryIntent.LOOKUP_READING:
                # === 1. Schema V2: tìm toàn văn tác phẩm ===
                items = self.graph_retriever.lookup_literature(lesson, series=effective_book, grade=effective_grade or 9)

                # === 2. Fallback: summary nếu không có toàn văn ===
                if not items:
                    items = self.graph_retriever.lookup_summary(lesson, series=effective_book, grade=effective_grade or 9)

                # === 3. Fallback: Qdrant vector search ===
                if not items:
                    if ctx.lesson_name:
                        items = self.reading_retriever.exact_lookup(ctx.lesson_name, effective_grade, effective_book)
                    if not items:
                        items = self.reading_retriever.semantic_search(search_query, grade=effective_grade, book_series=effective_book, top_k=3)

            elif ctx.intent == QueryIntent.EXPLAIN_CONCEPT:
                items = self.concept_retriever.retrieve(query, user_grade=effective_grade, top_k=2)
            elif ctx.intent == QueryIntent.WRITING_OUTLINE:
                if ctx.writing_type and effective_grade:
                    items = self.outline_retriever.retrieve(ctx.writing_type, effective_grade)
            elif ctx.intent in (QueryIntent.CHARACTER_INFO, QueryIntent.STORY_SUMMARY):
                # Tóm tắt nhân vật / truyện → dùng summary V2 trước
                items = self.graph_retriever.lookup_summary(lesson, series=effective_book, grade=effective_grade or 9)
                if not items:
                    items = self.graph_retriever.lookup_lesson_guide(lesson, series=effective_book, grade=effective_grade or 9)
                if not items:
                    items = self.reading_retriever.semantic_search(search_query, grade=effective_grade, book_series=effective_book, top_k=2)
            elif ctx.intent == QueryIntent.WRITING_SAMPLE:
                items = self.graph_retriever.fulltext_search(search_query, grade=effective_grade or 9, top_k=2)
                if not items:
                    items = self.reading_retriever.semantic_search(search_query, grade=effective_grade, book_series=effective_book, top_k=2)

                
        elif ctx.intent == QueryIntent.LOOKUP_CURRICULUM:
            current_week = user_profile.get("tuan_hien_tai", 1)
            if effective_grade and effective_book:
                items = self.curriculum_retriever.get_current_week_lessons(effective_grade, effective_book, current_week)
                
        else:
            # === GLOBAL SEMANTIC SEARCH FALLBACK (subject is None or unknown) ===
            global_items = []
            
            # 1. Math exercises
            global_items.extend(self.math_exercise_retriever.semantic_search(search_query, grade=effective_grade, top_k=2))
            # 2. KHTN exercises
            global_items.extend(self.khtn_retriever.semantic_search(search_query, grade=effective_grade, top_k=2))
            # 3. Social Sciences
            global_items.extend(self.social_retriever.semantic_search(search_query, grade=effective_grade, top_k=2))
            # 4. Reading / Textbooks (Ngữ Văn)
            global_items.extend(self.reading_retriever.semantic_search(search_query, grade=effective_grade, book_series=effective_book, top_k=2))
            # 5. Language Concepts (Ngữ Văn)
            global_items.extend(self.concept_retriever.retrieve(query, user_grade=effective_grade, top_k=2))
            
            # Sort all items by scalar similarity score descending
            global_items.sort(key=lambda x: x.score, reverse=True)
            
            # Keep top K (e.g. top 3 context documents across all subjects)
            items = global_items[:3]
            
            # Optionally rewrite the detected intent/subject if strongly confident
            if items:
                top_item = items[0]
                # Adjust subject based on what retrieved it
                if "Math" in top_item.source or "Toán" in top_item.source:
                    user_profile["subject_detected"] = "toan"
                    ctx.intent = QueryIntent.LOOKUP_SPECIFIC
                elif "KHTN" in top_item.source or "Khoa học" in top_item.source:
                    user_profile["subject_detected"] = "khtn"
                    ctx.intent = QueryIntent.LOOKUP_SPECIFIC
                elif "Xã hội" in top_item.title:
                    user_profile["subject_detected"] = "soc"
                    ctx.intent = QueryIntent.LOOKUP_SPECIFIC
                elif "Tiếng Việt" in top_item.source or "Ngữ văn" in top_item.source or "Khái niệm" in top_item.source:
                    user_profile["subject_detected"] = "ngu_van"
            
        return ctx, items

    def format_context_for_llm(self, items: list[RetrievedItem]) -> str:
        if not items:
            return ""
        parts = ["=== KIẾN THỨC THAM KHẢO ==="]
        for i, item in enumerate(items, 1):
            parts.append(f"\n[{i}] Nguồn: {item.source} | {item.title}\n{item.content}")
        parts.append("\n=== HẾT ===\n")
        return "\n".join(parts)

    def generate_response(self, query: str, user_profile: dict) -> str:
        ctx, items = self.retrieve(query, user_profile)
        context_str = self.format_context_for_llm(items)
        
        grade_str = f" lớp {user_profile.get('lop')}" if user_profile.get('lop') else ""
        system_prompt = f"""Bạn là gia sư AI vui vẻ, thân thiện, trả lời cho học sinh tiểu học{grade_str}.
Dựa vào kiến thức được cung cấp (nếu có), hãy trả lời ngắn gọn, dễ hiểu. Nếu học sinh chỉ chào hỏi, hãy chào lại thân thiện.
Tuyệt đối không giải bài tập thay học sinh, mà hãy gợi ý cách làm.

{context_str}"""
        
        try:
            result = generate_text(system_prompt, query)
            # If LLM returned the default error message, use template instead
            if "trục trặc" in result:
                raise Exception("LLM unavailable")
            return result
        except Exception:
            # Template-based fallback when no LLM API key
            if ctx.intent in (QueryIntent.GREETING, QueryIntent.ENCOURAGEMENT):
                return "Chào em! Chị có thể giúp gì cho em nào? 😊"
            if ctx.intent == QueryIntent.OFF_TOPIC:
                return "Hmm, câu này không liên quan đến bài học lắm đâu em ơi. Em hỏi chị về bài học nhé!"
            if items:
                parts = [f"Chị tìm được {len(items)} kết quả cho em nè:"]
                for i, item in enumerate(items, 1):
                    parts.append(f"📖 [{i}] {item.title}")
                    parts.append(f"   {item.content[:200]}...")
                return "\n".join(parts)
            return f"Chị chưa tìm thấy thông tin phù hợp cho câu hỏi của em. Intent detected: {ctx.intent.value}"

