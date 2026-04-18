#!/bin/bash
# ============================================================
# RAG EDU - AUTO BACKUP TO GOOGLE DRIVE
# Configured via Rclone (gdrive:)
# ============================================================
set -e

# Configuration
WORKSPACE="/home/namnx/knowledgeforptalk/rag_edu"
BACKUP_DIR="${WORKSPACE}/data/backup_tmp"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
QDRANT_CONTAINER="qdrant"
POSTGRES_CONTAINER="rag_postgres"

# GDrive Target Configuration
GDRIVE_BASE="gdrive:1yP2nkztnrCNrIuvy_pHBNCFs0HSB6EhC"
GDRIVE_CODE="${GDRIVE_BASE}/1_Source_Code"
GDRIVE_DB="${GDRIVE_BASE}/2_Database_SQL"
GDRIVE_VECTORS="${GDRIVE_BASE}/3_Qdrant_VectorDB"

echo "============================================================"
echo " Starting Auto-Backup at $TIMESTAMP"
echo "============================================================"

mkdir -p "$BACKUP_DIR/sql"
mkdir -p "$BACKUP_DIR/qdrant"

# ------------------------------------------------------------
# 1. PostgreSQL Database Dump
# ------------------------------------------------------------
echo "[1/4] Dumping PostgreSQL Database (rag_edu)..."
SQL_FILE="${BACKUP_DIR}/sql/rag_db_dump_${TIMESTAMP}.sql"
if docker ps | grep -q "$POSTGRES_CONTAINER"; then
    docker exec "$POSTGRES_CONTAINER" pg_dump -U postgres -d rag_edu -F c -f "/tmp/rag_db_dump.sql"
    docker cp "${POSTGRES_CONTAINER}:/tmp/rag_db_dump.sql" "$SQL_FILE"
    docker exec "$POSTGRES_CONTAINER" rm "/tmp/rag_db_dump.sql"
    echo " -> Database dumped successfully."
else
    echo " -> ERROR: PostgreSQL Container not running! Skipping SQL backup."
fi

# ------------------------------------------------------------
# 2. Qdrant Vector Database Compression
# ------------------------------------------------------------
echo "[2/4] Zipping Qdrant Storage..."
QDRANT_ZIP="${BACKUP_DIR}/qdrant/qdrant_storage_${TIMESTAMP}.zip"
if docker ps | grep -q "$QDRANT_CONTAINER"; then
    echo " -> Pausing Qdrant to ensure data integrity..."
    docker stop "$QDRANT_CONTAINER"
    cd "${WORKSPACE}/data"
    zip -r -q "$QDRANT_ZIP" "qdrant_storage/"
    docker start "$QDRANT_CONTAINER"
    echo " -> Qdrant zipped and container restarted."
else
    echo " -> ERROR: Qdrant Container not running! Zipping offline data anyway..."
    cd "${WORKSPACE}/data"
    zip -r -q "$QDRANT_ZIP" "qdrant_storage/" || echo " -> Error zipping Qdrant!"
fi
cd "$WORKSPACE"

# ------------------------------------------------------------
# 3. Clean up OLD LOCAL backups before SYNCING
# ------------------------------------------------------------
echo "[3/4] Cleaning up local temporary backups (keeping 2 days)..."
# This ensures that when we rclone sync, the remote will NOT keep infinitely old backups either.
find "$BACKUP_DIR/sql" -type f -name "*.sql" -mtime +2 -delete || true
find "$BACKUP_DIR/qdrant" -type f -name "*.zip" -mtime +2 -delete || true

# ------------------------------------------------------------
# 4. Rclone Sync to GDrive
# ------------------------------------------------------------
echo "[4/4] Syncing to Google Drive via rclone..."
echo " -> Uploading Code..."
rclone sync "${WORKSPACE}/scripts/" "${GDRIVE_CODE}/scripts/" -v
rclone sync "${WORKSPACE}/src/" "${GDRIVE_CODE}/src/" -v
rclone copy "${WORKSPACE}/.env" "${GDRIVE_CODE}/.env" -v || true
rclone copy "${WORKSPACE}/setup_server.sh" "${GDRIVE_CODE}/" -v || true

echo " -> Syncing Database Dumps..."
rclone sync "$BACKUP_DIR/sql/" "$GDRIVE_DB/" -v

echo " -> Syncing Vector Storage Zips..."
rclone sync "$BACKUP_DIR/qdrant/" "$GDRIVE_VECTORS/" -v

echo "============================================================"
echo " Backup Completed Successfully!"
echo "============================================================"
