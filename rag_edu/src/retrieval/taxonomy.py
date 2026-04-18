from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class QueryIntent(str, Enum):
    # Factual lookup
    LOOKUP_READING = "lookup_reading"
    LOOKUP_CURRICULUM = "lookup_curriculum"
    LOOKUP_SPECIFIC = "lookup_specific"
    
    # Conceptual
    EXPLAIN_CONCEPT = "explain_concept"
    SPELLING_RULE = "spelling_rule"
    
    # Writing help
    WRITING_OUTLINE = "writing_outline"
    WRITING_SAMPLE = "writing_sample"
    WRITING_FEEDBACK = "writing_feedback"
    
    # Reading comprehension
    CHARACTER_INFO = "character_info"
    STORY_SUMMARY = "story_summary"
    
    # Social / chitchat
    GREETING = "greeting"
    ENCOURAGEMENT = "encouragement"
    OFF_TOPIC = "off_topic"


@dataclass
class QueryContext:
    raw_query: str
    intent: QueryIntent
    search_query_rewrite: Optional[str] = None
    
    grade: Optional[int] = None
    book_series: Optional[str] = None
    subject: Optional[str] = None
    lesson_name: Optional[str] = None
    author: Optional[str] = None
    concept: Optional[str] = None
    writing_type: Optional[str] = None
    page: Optional[int] = None
    week: Optional[int] = None
    
    user_grade: Optional[int] = None
    user_book_series: Optional[str] = None
    
    confidence: float = 1.0


@dataclass
class RetrievedItem:
    source: str
    id: str
    title: str
    content: str
    score: float
    metadata: dict = field(default_factory=dict)
