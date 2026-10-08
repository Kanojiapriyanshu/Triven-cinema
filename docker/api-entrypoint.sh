#!/bin/sh
# Triven Cinema API container entrypoint.
# Starts as root only long enough to make the mounted storage writable, then drops to the unprivileged
# "triven" user. Only files that are not already owned by that user are touched, so restarts stay fast
# even with thousands of generated clips.
set -eu

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/storage/generated /app/storage/metrics /app/storage/jobs /app/storage/billing \
        /app/storage/integrations /app/storage/backups /app/storage/logs /app/storage/auth \
        /app/storage/chats /app/storage/elements
    find /app/storage \( ! -user triven -o ! -group triven \) -exec chown triven:triven {} + 2>/dev/null || true
    exec gosu triven "$@"
fi

exec "$@"
