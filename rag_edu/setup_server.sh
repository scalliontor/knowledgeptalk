#!/bin/bash
# ============================================================
# SETUP SCRIPT CHO GPU SERVER (L40S)
# Chạy trên server: /home/namnx/knowledgeforptalk/rag_edu/
# ============================================================
set -e

echo "============================================================"
echo "  RAG EDU - Server Setup (GPU L40S)"
echo "============================================================"

# 1. Tạo virtualenv nếu chưa có
if [ ! -d "venv" ]; then
    echo "[1/5] Creating Python virtual environment..."
    python3 -m venv venv
else
    echo "[1/5] Virtual environment already exists."
fi
source venv/bin/activate

# 2. Install dependencies
echo "[2/5] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Tạo data directories
echo "[3/5] Creating data directories..."
mkdir -p data/raw_html data/jsonl data/qdrant_storage data/postgres_dumps data/eval_data models

# 4. Start Qdrant (Docker) nếu chưa chạy
echo "[4/5] Starting Qdrant via Docker..."
if ! docker ps | grep -q qdrant; then
    docker run -d --name qdrant \
        -p 6333:6333 -p 6334:6334 \
        -v $(pwd)/data/qdrant_storage:/qdrant/storage \
        qdrant/qdrant:latest
    echo "  Qdrant started."
else
    echo "  Qdrant already running."
fi

# 5. Start PostgreSQL (Docker) nếu chưa chạy
echo "[5/5] Starting PostgreSQL via Docker..."
if ! docker ps | grep -q rag_postgres; then
    docker run -d --name rag_postgres \
        -p 5432:5432 \
        -e POSTGRES_USER=postgres \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=rag_edu \
        -v $(pwd)/data/postgres_dumps:/var/lib/postgresql/data \
        postgres:16-alpine
    echo "  PostgreSQL started. Waiting 5s for it to initialize..."
    sleep 5
else
    echo "  PostgreSQL already running."
fi

# 6. Apply schema
echo "[BONUS] Applying PostgreSQL schema..."
source venv/bin/activate
cd scripts && python3 init_db.py && cd ..

echo ""
echo "============================================================"
echo "  Setup complete! You can now run:"
echo "    source venv/bin/activate"
echo "    cd scripts && python3 loigiaihay_spider.py"
echo "    python3 post_process_crawl.py ../data/jsonl/<file>.jsonl"
echo "============================================================"
