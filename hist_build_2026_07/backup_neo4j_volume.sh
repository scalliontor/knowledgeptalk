#!/usr/bin/env bash
# Backup Neo4j edu bằng SAO CHÉP NGUYÊN VOLUME (chuẩn cho việc chuyển server).
# Giảm downtime: chỉ COPY khi DB dừng, việc NÉN làm sau khi DB đã chạy lại.
set -u
OUT=/home/namnx/ptalk_migration_backup/$(date +%Y-%m-%d)/neo4j
STAGE=/home/namnx/_neo4j_stage
mkdir -p "$OUT" "$STAGE"
LOG="$OUT/volume_backup.log"
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "=== BACKUP VOLUME edu_neo4j_data ==="
BEFORE=$(docker exec edu_neo4j cypher-shell -u neo4j -p "$EDU_NEO4J_PASS" --format plain \
         "MATCH (n) RETURN count(n)" 2>/dev/null | tail -1 | tr -d '"')
say "node trước: $BEFORE"

say "--- STOP edu_neo4j ---"
T0=$(date +%s)
docker stop edu_neo4j >>"$LOG" 2>&1 || { say "!! stop lỗi"; exit 1; }

# copy KHÔNG nén (nhanh nhất) -> giảm tối đa thời gian ngắt
say "--- copy volume (không nén) ---"
rm -rf "$STAGE/data"
docker run --rm -v edu_neo4j_data:/src -v "$STAGE":/dst alpine \
  sh -c "cp -a /src /dst/data" >>"$LOG" 2>&1
RC=$?

say "--- START lại edu_neo4j ---"
docker start edu_neo4j >>"$LOG" 2>&1
T1=$(date +%s)
say "THỜI GIAN NGẮT: $((T1-T0)) giây"
[ $RC -ne 0 ] && say "!! copy lỗi rc=$RC"

say "--- chờ DB sẵn sàng + verify ---"
for i in $(seq 1 60); do
  sleep 3
  AFTER=$(docker exec edu_neo4j cypher-shell -u neo4j -p "$EDU_NEO4J_PASS" --format plain \
          "MATCH (n) RETURN count(n)" 2>/dev/null | tail -1 | tr -d '"')
  [ -n "${AFTER:-}" ] && break
done
say "node sau: ${AFTER:-?}"
[ "${AFTER:-x}" = "$BEFORE" ] && say "✓ KHỚP" || say "!! LỆCH"

# nén SAU khi DB đã chạy lại (không tính vào downtime)
say "--- nén bản sao (DB đã chạy lại, không ảnh hưởng dịch vụ) ---"
tar czf "$OUT/edu_neo4j_data_$(date +%Y-%m-%d).tar.gz" -C "$STAGE" data 2>>"$LOG"
SZ=$(stat -c%s "$OUT"/edu_neo4j_data_*.tar.gz 2>/dev/null | head -1)
say "  -> $(numfmt --to=iec ${SZ:-0})"
say "  sha256: $(sha256sum "$OUT"/edu_neo4j_data_*.tar.gz | cut -d' ' -f1)"
rm -rf "$STAGE"
say "=== XONG ==="
