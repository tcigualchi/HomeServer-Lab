#!/usr/bin/env bash
set -euo pipefail
mkdir -p backups
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
db="data/homelab.db"
if [[ ! -f "$db" ]]; then echo "Banco não encontrado: $db" >&2; exit 1; fi
archive="backups/homelab-$timestamp.tar.gz"
tar --exclude='.env' --exclude='backups' -czf "$archive" "$db" config 2>/dev/null || tar --exclude='.env' --exclude='backups' -czf "$archive" "$db"
echo "Backup criado sem secrets: $archive"
