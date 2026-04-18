#!/bin/bash
echo "Starting RAG Edu FastAPI Interface on port 8888..."
source venv/bin/activate
export PYTHONPATH=.
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8888 --workers 1 > rag_api.log 2>&1 &
echo "RAG API is now running in the background. Tail rag_api.log for details."
