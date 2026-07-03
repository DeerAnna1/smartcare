#!/bin/sh
set -eu

mkdir -p /backups

while true; do
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    destination="/backups/${POSTGRES_DB}_${timestamp}.sql.gz"

    if pg_dump --host=postgres --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" --no-owner --no-privileges | gzip > "${destination}"; then
        echo "PostgreSQL backup created: ${destination}"
        find /backups -type f -name '*.sql.gz' -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
    else
        echo "PostgreSQL backup failed" >&2
        rm -f "${destination}"
    fi

    sleep "${BACKUP_INTERVAL_SECONDS:-86400}"
done
