#!/usr/bin/env bash
# Poll docker-compose until all services report healthy (or started for those without healthchecks).
set -euo pipefail
MAX_WAIT=${MAX_WAIT:-240}
start=$(date +%s)
while :; do
  total=$(docker compose ps --format json | wc -l | tr -d ' ')
  bad=$(docker compose ps --format json \
    | jq -r '. | select(.Health != "" and .Health != "healthy") | .Name' 2>/dev/null || true)
  if [[ -z "${bad:-}" && "${total}" != "0" ]]; then
    echo "All services healthy."
    exit 0
  fi
  now=$(date +%s)
  if (( now - start > MAX_WAIT )); then
    echo "Timeout after ${MAX_WAIT}s waiting for: ${bad:-<unknown>}" >&2
    docker compose ps
    exit 1
  fi
  sleep 3
done
