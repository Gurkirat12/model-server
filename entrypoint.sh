#!/bin/bash
set -euo pipefail

PROFILE="${PROFILE:-balanced}"
VALID_PROFILES="balanced throughput latency"

valid=false
for p in $VALID_PROFILES; do
    if [ "$PROFILE" = "$p" ]; then
        valid=true
        break
    fi
done

if [ "$valid" = "false" ]; then
    echo "FATAL: PROFILE='$PROFILE' is not a valid profile." >&2
    echo "Valid values: $VALID_PROFILES" >&2
    echo "Usage: docker run -e PROFILE=<profile> model-server:latest" >&2
    exit 1
fi

echo "[entrypoint] Profile: $PROFILE"
echo "[entrypoint] Starting model server on port 8000..."

exec python /opt/app/app/main.py
