#!/usr/bin/env bash
# Automated tour: bring stack up, seed, ingest, verify, hint at UI.
set -euo pipefail
cd "$(dirname "$0")/.."
make up
echo "⏳ Waiting 20s for services to settle…"
sleep 20
make seed || true
make ingest
sleep 10
python3 tests/e2e/verify_after_ingest.py || true
echo ""
echo "🎉 Demo ready."
echo "  UI:        http://localhost:5173"
echo "  GraphQL:   http://localhost:4000/graphql"
echo "  Jaeger:    http://localhost:16686"
echo "  OpenSearch http://localhost:9200"
