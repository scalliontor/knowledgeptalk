import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.database import get_db_connection, init_db_pool
from src.qdrant_client_mgr import get_qdrant_client
from src.embeddings import embed_text
from src.retrieval.classifier import QueryClassifier
from src.retrieval.orchestrator import RAGOrchestrator

def main():
    print("Initializing RAG CLI Tester...")
    init_db_pool()
    q_client = get_qdrant_client()
    classifier = QueryClassifier()
    
    user_profile = {"lop": 4, "bo_sach_chinh": "KNTT"}
    
    with get_db_connection() as conn:
        orchestrator = RAGOrchestrator(conn, q_client, embed_text, classifier)
        
        while True:
            query = input("\\n[User Lớp 4]> ")
            if query.lower() in ["exit", "quit"]:
                break
            
            # Retrieve
            ctx, items = orchestrator.retrieve(query, user_profile)
            print(f"\\n--- Intent Detected: {ctx.intent} ---")
            for item in items:
                print(f"- Retrieved: {item.title} (Score: {item.score:.2f})")
                
            # Generation
            reply = orchestrator.generate_response(query, user_profile)
            print(f"\\n[AI Bot]: {reply}")

if __name__ == "__main__":
    main()
