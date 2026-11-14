#!/bin/sh
# Daily backup:   DATABASE_URL_PLAIN=postgresql://user:pass@host/db ./scripts/backup_postgres.sh
# Test a restore regularly:   createdb restore_test && pg_restore -d restore_test backups/<file>.dump
set -eu
mkdir -p backups
pg_dump --format=custom "$DATABASE_URL_PLAIN" > "backups/iammendexmendle-$(date +%F).dump"
find backups -name '*.dump' -mtime +14 -delete
