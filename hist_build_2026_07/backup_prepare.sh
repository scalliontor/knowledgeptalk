#!/usr/bin/env bash
# Chuẩn bị gói backup TRƯỚC KHI ĐỔI SERVER — phần KHÔNG cần downtime.
# Chạy trên server. Kết quả gom vào /home/namnx/ptalk_migration_backup/<ngày>/
# Sau đó đẩy lên Drive bằng rclone (cần token còn hạn).
set -u
STAMP=$(date +%Y-%m-%d)
OUT=/home/namnx/ptalk_migration_backup/$STAMP
SRC=/home/namnx/Ptalk_project/CloudPTalk
mkdir -p "$OUT"/{neo4j,qdrant,code,meta}
LOG="$OUT/backup.log"
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "=== BACKUP CHUẨN BỊ ĐỔI SERVER → $OUT ==="

# ── 1. QDRANT: snapshot từng collection (online, không downtime) ──
say "--- Qdrant snapshots ---"
for c in $(curl -s http://localhost:6333/collections | python3 -c "import sys,json;print(' '.join(x['name'] for x in json.load(sys.stdin)['result']['collections']))"); do
  say "  snapshot: $c"
  snap=$(curl -s -X POST "http://localhost:6333/collections/$c/snapshots" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('result',{}).get('name',''))" 2>/dev/null)
  if [ -n "$snap" ]; then
    curl -s "http://localhost:6333/collections/$c/snapshots/$snap" -o "$OUT/qdrant/${c}__${snap}" && say "    -> $(du -h "$OUT/qdrant/${c}__${snap}" | cut -f1)"
  else
    say "    !! snapshot lỗi: $c"
  fi
done

# ── 2. CODE + CẤU HÌNH (bỏ audio_cache 34G, venv 7.1G — tái tạo được) ──
say "--- Code + config (bỏ audio_cache/venv/__pycache__) ---"
tar czf "$OUT/code/cloudptalk_code_$STAMP.tar.gz" \
  --exclude='audio_cache' --exclude='venv' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='audio_files' --exclude='*.wav' \
  --exclude='logs/*.log' \
  -C /home/namnx/Ptalk_project CloudPTalk 2>>"$LOG"
say "  -> $(du -h "$OUT/code/cloudptalk_code_$STAMP.tar.gz" | cut -f1)"

# ── 3. MODELS (ZipVoice/ZipFormer/SileroVAD/GTCRN ~700M) ──
say "--- Models ---"
tar czf "$OUT/code/models_$STAMP.tar.gz" -C "$SRC" models 2>>"$LOG"
say "  -> $(du -h "$OUT/code/models_$STAMP.tar.gz" | cut -f1)"

# ── 4. META: trạng thái hệ thống để dựng lại đúng ──
say "--- Meta (để dựng lại server mới) ---"
{
  echo "# PTalk migration snapshot — $STAMP"
  echo; echo "## docker ps"; docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
  echo; echo "## docker volumes"; docker volume ls
  echo; echo "## screen sessions"; screen -ls 2>/dev/null
  echo; echo "## listening ports"; ss -tlnp 2>/dev/null | grep -E ':(8001|8002|8003|8080|8888|8893|6333|7688|6379)'
  echo; echo "## nvidia"; nvidia-smi --query-gpu=name,memory.total --format=csv
  echo; echo "## disk"; df -h /
  echo; echo "## python packages (rag)"; "$SRC/venv/bin/pip" freeze 2>/dev/null | head -80
} > "$OUT/meta/system_state.txt" 2>&1
cp "$SRC"/*.sh "$OUT/meta/" 2>/dev/null
say "  -> meta/system_state.txt + launch scripts"

say "=== XONG phần không-downtime ==="
du -sh "$OUT"/* | tee -a "$LOG"
echo
say "CÒN THIẾU (cần cửa sổ dừng DB, phải xin phép): neo4j-admin dump edu_neo4j"
