#!/bin/bash
# Canary :8893 — WIKI ORCHESTRATOR. Env overridable: WIKI_ENABLED / WIKI_BUDGET_S.
cd /home/namnx/Ptalk_project/CloudPTalk || exit 1
pkill -9 -f 'rag_server_canary8892\.py' 2>/dev/null
sleep 1
WIKI_ENABLED=${WIKI_ENABLED:-1} RAG_PORT=8893 WIKI_BUDGET_S=${WIKI_BUDGET_S:-2.5} \
  nohup venv/bin/python rag_server_canary8892.py > /tmp/canary8893.log 2>&1 &
echo "launched pid $! (WIKI_ENABLED=${WIKI_ENABLED:-1} BUDGET=${WIKI_BUDGET_S:-2.5})"
