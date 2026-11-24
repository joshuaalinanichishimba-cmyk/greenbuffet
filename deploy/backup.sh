#!/bin/sh
# Nightly backup on a server. Add to the host's crontab:
#   30 23 * * *  /srv/greenbuffet/deploy/backup.sh >> /var/log/greenbuffet-backup.log 2>&1
set -eu
cd "$(dirname "$0")"
stamp=$(date +%Y%m%d-%H%M%S)
docker compose exec -T database pg_dump -U "${DB_USER:-greenbuffet}" -F c "${DB_NAME:-greenbuffet}" \
  > "/var/backups/greenbuffet-${stamp}.dump"
# Keep 30 days here; copy them somewhere else as well.
find /var/backups -name 'greenbuffet-*.dump' -mtime +30 -delete
echo "$(date -Is) backup written: greenbuffet-${stamp}.dump"
