#!/usr/bin/env bash
# Kills the projector, triggers a new event, restarts, and confirms reconciliation.
set -euo pipefail
echo "▶ killing projector"
docker compose kill projector || true
sleep 2
echo "▶ publishing a FileReceived event (would produce enrollments)"
make ingest F=tests/golden/834_replace.x12 || true
sleep 5
echo "▶ restarting projector"
docker compose up -d projector
sleep 10
echo "▶ running verify"
python3 tests/e2e/verify_after_ingest.py
echo "✅ chaos drill complete"
