#!/usr/bin/env bash
# Restore a dump (from backup_db.sh) into the database named by DATABASE_URL —
# typically your NEW cloud Postgres. Uses pg_restore from the Docker container so
# no local Postgres tools are needed.
#
# Usage:  apps/api/scripts/restore_db.sh <dumpfile>
#   DATABASE_URL must point at the TARGET database (the cloud one). It is read from
#   the repo-root .env if not already exported.
set -euo pipefail

DUMP="${1:-}"
if [[ -z "$DUMP" || ! -f "$DUMP" ]]; then
  echo "Usage: $0 <dumpfile>   (a file made by backup_db.sh)" >&2
  exit 1
fi

# Load DATABASE_URL from .env if not set in the environment.
if [[ -z "${DATABASE_URL:-}" && -f .env ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' .env | tail -1 | cut -d= -f2-)"
fi
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Error: DATABASE_URL is not set (point it at the TARGET/cloud database)." >&2
  exit 1
fi

# pg_restore wants a libpq URL: strip the SQLAlchemy '+psycopg' driver tag.
PG_URL="${DATABASE_URL/+psycopg/}"
CONTAINER="${DB_CONTAINER:-digitaltwin_db}"

case "$PG_URL" in
  *localhost*|*127.0.0.1*)
    echo "Refusing to restore into a localhost database — set DATABASE_URL to the" >&2
    echo "cloud target first (this script is for pushing a backup UP to the cloud)." >&2
    exit 1 ;;
esac

echo "Restoring ${DUMP} into: ${PG_URL%%\?*} (SSL/params preserved)"
read -r -p "This overwrites matching tables in the TARGET. Continue? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "Aborted."; exit 1; }

# --clean --if-exists so re-running is safe; --no-owner for a fresh cloud role.
docker exec -i "$CONTAINER" pg_restore --clean --if-exists --no-owner \
  -d "$PG_URL" < "$DUMP"
echo "Restore complete. Verify by opening the app against the cloud database."
