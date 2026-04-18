from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException

from src.database import get_db_connection, init_db_pool
from src.qdrant_client_mgr import get_qdrant_client
from src.embeddings import embed_text, get_embedding_model
from src.retrieval.classifier import QueryClassifier
from src.retrieval.orchestrator import RAGOrchestrator

# Global state
app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Initialize resources...")
    init_db_pool()
    get_embedding_model() # Load embedding model to memory
    app_state['qdrant_client'] = get_qdrant_client()
    app_state['classifier'] = QueryClassifier()
    yield
    # Shutdown
    print("Shutting down resources...")
    # Add any cleanup if needed

app = FastAPI(title="Vietnamese Educational RAG Chatbot", lifespan=lifespan)

class ChatRequest(BaseModel):
    query: str
    user_profile: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    reply: str
    # Could also include debug info about retrieval
    retrieved_sources: int

@app.post("/retrieve")
def retrieve_endpoint(req: ChatRequest):
    user_profile = req.user_profile or {}
    
    with get_db_connection() as conn:
        orchestrator = RAGOrchestrator(
            pg_conn=conn,
            qdrant_client=app_state['qdrant_client'],
            embed_fn=embed_text,
            classifier=app_state['classifier']
        )
        
        ctx, items = orchestrator.retrieve(req.query, user_profile)
        
        # Build context string
        context_str = ""
        for idx, item in enumerate(items, 1):
            context_str += f"- Đoạn {idx} [{item.id}] ({item.title}): {item.content}\n"
            
        return {
            "context": context_str.strip(),
            "retrieved_sources": len(items),
            "intent": ctx.intent.value if ctx else "unknown"
        }

@app.get("/health")
def health_check():
    return {"status": "ok"}
