#!/usr/bin/env bash
# Back up the LOCAL Postgres database to a dated dump file.
#
# Uses pg_dump from your existing Docker container (`digitaltwin_db`) so you don't
# need Postgres tools installed on the Mac. Output goes to backups/ in the repo.
#
# Usage:  apps/api/scripts/backup_db.sh
set -euo pipefail

CONTAINER="${DB_CONTAINER:-digitaltwin_db}"
DB_USER="${POSTGRES_USER:-digitaltwin}"
DB_NAME="${POSTGRES_DB:-digitaltwin}"
OUT_DIR="${BACKUP_DIR:-backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${OUT_DIR}/digitaltwin_${STAMP}.dump"

mkdir -p "$OUT_DIR"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Error: Docker container '$CONTAINER' is not running." >&2
  echo "Start it with: make db-up" >&2
  exit 1
fi

echo "Dumping ${DB_NAME} from container ${CONTAINER} -> ${OUT}"
# Custom format (-Fc) so it restores cleanly with pg_restore into any Postgres.
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$OUT"
echo "Done. Backup written to ${OUT} ($(du -h "$OUT" | cut -f1))."
echo "Keep this file safe; restore with apps/api/scripts/restore_db.sh ${OUT}"
