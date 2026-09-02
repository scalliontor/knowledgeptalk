#!/usr/bin/env bash
# Dump Neo4j edu (Community -> phải offline). Ngắt tối thiểu, tự bật lại, verify.
set -u
OUT=/home/namnx/ptalk_migration_backup/$(date +%Y-%m-%d)/neo4j
mkdir -p "$OUT"
LOG="$OUT/dump.log"
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "=== NEO4J DUMP (edu_neo4j) ==="

# 0. đếm node TRƯỚC (để đối chiếu sau khi bật lại)
BEFORE=$(docker exec edu_neo4j cypher-shell -u neo4j -p "$EDU_NEO4J_PASS" --format plain \
         "MATCH (n) RETURN count(n)" 2>/dev/null | tail -1 | tr -d '"')
say "node trước khi dump: $BEFORE"

# 1. DỪNG
say "--- STOP edu_neo4j ---"
T0=$(date +%s)
docker stop edu_neo4j >>"$LOG" 2>&1 || { say "!! stop lỗi"; exit 1; }

# 2. DUMP bằng container tạm (cùng image, mount cùng volume)
say "--- dump ---"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v edu_neo4j_data:/data \
  -v "$OUT":/backups \
  neo4j:5-community \
  neo4j-admin database dump neo4j --to-path=/backups --overwrite-destination=true \
  >>"$LOG" 2>&1
RC=$?

# 3. BẬT LẠI NGAY (kể cả khi dump lỗi — ưu tiên khôi phục dịch vụ)
say "--- START lại edu_neo4j ---"
docker start edu_neo4j >>"$LOG" 2>&1
T1=$(date +%s)
say "THỜI GIAN NGẮT: $((T1-T0)) giây"

if [ $RC -ne 0 ]; then say "!! DUMP LỖI (rc=$RC) — xem $LOG"; fi

# 4. chờ DB sẵn sàng + verify node count khớp
say "--- chờ DB sẵn sàng ---"
for i in $(seq 1 60); do
  sleep 3
  AFTER=$(docker exec edu_neo4j cypher-shell -u neo4j -p "$EDU_NEO4J_PASS" --format plain \
          "MATCH (n) RETURN count(n)" 2>/dev/null | tail -1 | tr -d '"')
  if [ -n "${AFTER:-}" ] && [ "$AFTER" != "" ]; then break; fi
done
say "node sau khi bật lại: ${AFTER:-KHÔNG ĐỌC ĐƯỢC}"
if [ "${AFTER:-x}" = "$BEFORE" ]; then say "✓ node count KHỚP"; else say "!! node count LỆCH ($BEFORE -> ${AFTER:-?})"; fi

# 5. verify file dump
say "--- file dump ---"
ls -la "$OUT"/*.dump 2>/dev/null | tee -a "$LOG"
for f in "$OUT"/*.dump; do
  [ -f "$f" ] || continue
  SZ=$(stat -c%s "$f")
  say "  $(basename "$f") = $(numfmt --to=iec $SZ)"
  [ "$SZ" -gt 1000000 ] && say "  ✓ size hợp lý" || say "  !! size ĐÁNG NGỜ"
  say "  sha256: $(sha256sum "$f" | cut -d' ' -f1)"
done
say "=== XONG ==="
