#!/bin/bash
# ============================================================
# FULL PIPELINE: Crawl → Process → Index
# Chạy SAU khi đã chạy setup_server.sh
# ============================================================
set -e

source venv/bin/activate

echo "============================================"
echo "  STEP 1: Crawling loigiaihay.com Lớp 1-5"
echo "============================================"
cd scripts
python3 loigiaihay_spider.py
cd ..

echo ""
echo "============================================"
echo "  STEP 2: Finding latest JSONL output"
echo "============================================"
LATEST_JSONL=$(ls -t data/jsonl/*.jsonl 2>/dev/null | head -n 1)

if [ -z "$LATEST_JSONL" ]; then
    echo "ERROR: No JSONL output found in data/jsonl/"
    exit 1
fi
echo "  Found: $LATEST_JSONL"

echo ""
echo "============================================"
echo "  STEP 3: Post-processing → PostgreSQL + Qdrant"
echo "============================================"
cd scripts
python3 post_process_crawl.py "../$LATEST_JSONL"
cd ..

echo ""
echo "============================================"
echo "  STEP 4: Syncing results to Google Drive"
echo "============================================"
if command -v rclone &> /dev/null; then
    rclone copy data/ gdrive:knowledgeforptalk/rag_edu/data/ --progress 2>/dev/null || echo "  rclone sync skipped (no config or error)."
else
    echo "  rclone not installed, skipping sync."
fi

echo ""
echo "============================================"
echo "  Pipeline complete!"
echo "  Crawled data: $LATEST_JSONL"
echo "  Test with: cd scripts && python3 test_cli.py"
echo "============================================"
