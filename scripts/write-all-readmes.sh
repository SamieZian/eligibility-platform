#!/usr/bin/env bash
# Write production-grade READMEs + .env.example for every repo.
# Idempotent.
set -euo pipefail

DESKTOP=/Users/sampathake/Desktop
OWNER=SamieZian

# ────────────────────────────────────────────────────────────────────────
# Per-service common .env.example (Python services share most vars)
# ────────────────────────────────────────────────────────────────────────
common_env() {
  local svc="$1" port="$2" db_port="$3"
  cat <<EOF
# ----- $svc service environment ---------------------------------------
# Required
SERVICE_NAME=$svc
DATABASE_URL=postgresql+psycopg://postgres:dev_pw@${svc}_db:5432/${svc}_db
PUBSUB_PROJECT_ID=local-eligibility
PUBSUB_EMULATOR_HOST=pubsub:8085

# Optional / observability
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
TENANT_DEFAULT=11111111-1111-1111-1111-111111111111

# Standalone (no docker-compose) overrides
# DATABASE_URL=postgresql+psycopg://postgres:dev_pw@localhost:$db_port/postgres
EOF
}

write_python_service_readme() {
  local repo_dir="$1" name="$2" port="$3" title="$4" desc="$5"
  cat > "$repo_dir/README.md" <<EOF
# eligibility-$name

$title

## What this service does

$desc

This is **one of 7 microservices** in the [Eligibility & Enrollment Platform](https://github.com/$OWNER/eligibility-platform). Each service has its own repo, its own database, its own Dockerfile, its own deployment lifecycle.

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker | 24+ | Container runtime |
| Docker Compose | v2 (the \`docker compose\` plugin) | Local orchestration |
| Python | 3.11+ | Standalone dev (optional) |
| GNU Make | any recent | Convenience targets (optional) |

The easiest way to use this service is via the orchestration repo:
\`\`\`bash
git clone https://github.com/$OWNER/eligibility-platform
cd eligibility-platform
./bootstrap.sh         # clones this repo and 6 siblings
make up                # boots the whole stack with this svc included
\`\`\`

## Companion repos

| Repo | What |
|---|---|
| [\`eligibility-platform\`](https://github.com/$OWNER/eligibility-platform) | Orchestration + docker-compose + sample 834 + demo |
| [\`eligibility-atlas\`](https://github.com/$OWNER/eligibility-atlas) | Bitemporal enrollment service |
| [\`eligibility-member\`](https://github.com/$OWNER/eligibility-member) | Members + dependents (KMS-encrypted SSN) |
| [\`eligibility-group\`](https://github.com/$OWNER/eligibility-group) | Payer / employer / subgroup / plan visibility |
| [\`eligibility-plan\`](https://github.com/$OWNER/eligibility-plan) | Plan catalog (Redis cache-aside) |
| [\`eligibility-bff\`](https://github.com/$OWNER/eligibility-bff) | GraphQL gateway + file upload |
| [\`eligibility-workers\`](https://github.com/$OWNER/eligibility-workers) | Stateless workers — ingestion / projector / outbox-relay |
| [\`eligibility-frontend\`](https://github.com/$OWNER/eligibility-frontend) | React + TS UI |

## Quickstart (standalone, with this repo only)

\`\`\`bash
# 1. Configure
cp .env.example .env
# (edit values if needed — defaults work for local docker)

# 2. Build the image
docker build -t eligibility-$name:local .

# 3. Spin a Postgres for it
docker run -d --name pg-$name \\
  -e POSTGRES_PASSWORD=dev_pw \\
  -p $port:5432 postgres:15-alpine

# 4. Run the service against that DB
docker run --rm -p $((port + 1000)):8000 \\
  --env-file .env \\
  -e DATABASE_URL=postgresql+psycopg://postgres:dev_pw@host.docker.internal:$port/postgres \\
  eligibility-$name:local

# 5. Health check
curl http://localhost:$((port + 1000))/livez
\`\`\`

## Develop locally without Docker

\`\`\`bash
# Python venv
python3.11 -m venv .venv && source .venv/bin/activate

# Install vendored shared lib + service deps
pip install -e libs/python-common
pip install fastapi 'uvicorn[standard]' sqlalchemy asyncpg 'psycopg[binary]' \\
  alembic httpx pydantic pydantic-settings structlog tenacity cryptography \\
  redis google-cloud-pubsub \\
  opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp \\
  opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy

# Configure
export \$(cat .env | xargs)

# Run
PYTHONPATH=.:libs/python-common/src python -m app.main
\`\`\`

## Test

\`\`\`bash
pip install pytest pytest-asyncio
PYTHONPATH=.:libs/python-common/src \\
  DATABASE_URL=postgresql+psycopg://x@x/x \\
  python -m pytest tests -q
\`\`\`

## Project layout (hexagonal)

\`\`\`
.
├── app/
│   ├── domain/         # Pure business logic — no I/O
│   ├── application/    # Use-cases, command handlers
│   ├── infra/          # SQLAlchemy repos, KMS, Redis, ORM models
│   ├── interfaces/     # FastAPI routers (HTTP)
│   ├── settings.py     # Pydantic env-driven config
│   └── main.py         # FastAPI app + lifespan
├── tests/              # pytest unit tests
├── migrations/         # Alembic (prod schema migrations)
├── libs/               # Vendored shared code
│   └── python-common/  # outbox, pubsub, errors, retry, circuit breaker, kms
├── .env.example        # All env vars documented
├── Dockerfile
├── pyproject.toml
└── README.md
\`\`\`

## Environment variables

See [\`.env.example\`](.env.example) for the full list with defaults. Required:

- \`SERVICE_NAME\` — used in logs/traces
- \`DATABASE_URL\` — Postgres connection string
- \`PUBSUB_PROJECT_ID\` — Pub/Sub project (any value for local emulator)
- \`PUBSUB_EMULATOR_HOST\` — \`pubsub:8085\` when running with compose, unset in prod

Optional:
- \`LOG_LEVEL\` (\`INFO\`)
- \`OTEL_EXPORTER_OTLP_ENDPOINT\` — when set, traces export to that endpoint
- \`TENANT_DEFAULT\` — fallback tenant id when no header

## API

See \`app/interfaces/api.py\` for the route list. Standard endpoints:

- \`GET /livez\` → liveness probe
- \`GET /readyz\` → readiness probe (checks deps reachable)

## Patterns used

- Hexagonal architecture (domain / application / infra / interfaces)
- Transactional outbox for at-least-once event delivery
- Idempotent commands (each command's effect is repeatable)
- Structured JSON logs with correlation ID propagation
- OpenTelemetry traces (BFF → service → DB)
- Circuit breakers on outbound HTTP

## License

MIT.
EOF
}

# ────────────────────────────────────────────────────────────────────────
# atlas
# ────────────────────────────────────────────────────────────────────────
write_python_service_readme \
  "$DESKTOP/eligibility-atlas" "atlas" "5441" \
  "**Bitemporal enrollment** — the core of the Eligibility & Enrollment Platform." \
  "Atlas owns member eligibility over time. It maintains a **bitemporal** \`enrollments\` table — every row has both a *valid time* (when coverage is true in the real world) and a *transaction time* (when the system learned that fact). Retro-active 834 corrections never overwrite history; they close the existing row's \`txn_to\` and open a new corrected row.

Atlas exposes a command API (\`ADD\`, \`CHANGE\`, \`TERMINATE\`, \`REINSTATE\`, \`CORRECTION\`) and a timeline query. Each write also lands in the \`outbox\` table so the relay worker can publish events to Pub/Sub atomically with the domain mutation.

Idempotency for 834 retries is keyed off \`(trading_partner, ISA13, GS06, ST02, INS_position)\` — repeated deliveries are silently dropped via the \`processed_segments\` table.

Saga orchestration lives here too — multi-step workflows like \`REPLACE_FILE\` (full-file enrollment refresh) are managed via a hand-rolled finite-state machine with compensating actions on failure."
common_env "atlas" "8001" "5441" > "$DESKTOP/eligibility-atlas/.env.example"

# ────────────────────────────────────────────────────────────────────────
# member
# ────────────────────────────────────────────────────────────────────────
write_python_service_readme \
  "$DESKTOP/eligibility-member" "member" "5442" \
  "**Members + dependents directory** with KMS-encrypted SSN." \
  "Stores subscriber and dependent demographics. SSN is **envelope-encrypted** at rest via KMS — only the last 4 digits are stored in the clear. Upserts by \`(tenant_id, card_number)\`. Emits \`MemberUpserted\` events when records change."
common_env "member" "8002" "5442" > "$DESKTOP/eligibility-member/.env.example"

# ────────────────────────────────────────────────────────────────────────
# group
# ────────────────────────────────────────────────────────────────────────
write_python_service_readme \
  "$DESKTOP/eligibility-group" "group" "5443" \
  "**Payer / employer / subgroup hierarchy + plan visibility**." \
  "Hierarchy: a payer (e.g. ICICI) contracts with employers (Swiggy, Zomato) which split into subgroups. The \`employer_plan_visibility\` table controls which plans each employer can offer to its members.

Powers the **Groups admin UI** (bonus assignment task) — full CRUD: create/delete payers, employers (with cascade), subgroups, attach/detach plan visibility per employer."
common_env "group" "8003" "5443" > "$DESKTOP/eligibility-group/.env.example"

# ────────────────────────────────────────────────────────────────────────
# plan
# ────────────────────────────────────────────────────────────────────────
write_python_service_readme \
  "$DESKTOP/eligibility-plan" "plan" "5444" \
  "**Plan catalog** with Redis cache-aside." \
  "Stores the list of insurance plans (Gold / Silver / Bronze). Reads are **cached in Redis** with write-through invalidation on \`PlanUpserted\`. Plan code is the natural key.

Supports both \`GET /plans?code=XYZ\` (single lookup) and \`GET /plans\` (full catalog list — used by the BFF to populate the Add Member form's plan dropdown)."
cat > "$DESKTOP/eligibility-plan/.env.example" <<EOF
$(common_env "plan" "8004" "5444")

# Redis (optional — service degrades gracefully if Redis is down)
REDIS_URL=redis://redis:6379/0
PLAN_CACHE_TTL_SECONDS=60
EOF

# ────────────────────────────────────────────────────────────────────────
# bff
# ────────────────────────────────────────────────────────────────────────
write_python_service_readme \
  "$DESKTOP/eligibility-bff" "bff" "5441" \
  "**GraphQL gateway + file upload** — the frontend's backend." \
  "FastAPI + Strawberry GraphQL at \`/graphql\`. REST \`POST /files/eligibility\` for 834 / CSV / XLSX uploads (streams to MinIO, publishes \`FileReceived\` to Pub/Sub).

Talks to atlas / member / group / plan over HTTP with **circuit breakers** (open after 5 failures in a 10s window) and **DataLoader batching** to avoid N+1 in GraphQL resolvers.

Provides an aggregated \`groupAdmin\` query that fans out to group service for the Groups admin page. Also orchestrates **\`addMember\`** mutation — POST member + POST atlas command in one call."
cat > "$DESKTOP/eligibility-bff/.env.example" <<EOF
$(common_env "bff" "8000" "5441")

# Downstream service URLs
ATLAS_URL=http://atlas:8000
MEMBER_URL=http://member:8000
GROUP_URL=http://group:8000
PLAN_URL=http://plan:8000

# Read model + search
ATLAS_DB_URL=postgresql+psycopg://postgres:dev_pw@atlas_db:5432/atlas_db
OPENSEARCH_URL=http://opensearch:9200

# Object storage (for file uploads)
MINIO_ENDPOINT=http://minio:9000
MINIO_BUCKET=eligibility-files
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio12345
EOF

# ────────────────────────────────────────────────────────────────────────
# workers (special — three workers in one repo)
# ────────────────────────────────────────────────────────────────────────
cat > "$DESKTOP/eligibility-workers/README.md" <<EOF
# eligibility-workers

Three stateless consumers that back the CQRS + event-driven side of the platform.

| Worker | Purpose |
|---|---|
| \`ingestion/\` | Subscribes to \`file.received\` Pub/Sub. Downloads uploaded 834/CSV from MinIO, parses with the streaming X12 parser, maps each INS loop to an atlas command, and POSTs. Idempotency via \`(trading_partner, ISA13, GS06, ST02, INS_position)\`. |
| \`projector/\` | Subscribes to all domain events (\`MemberUpserted\`, \`PlanUpserted\`, \`EmployerUpserted\`, \`EnrollmentAdded/Changed/Terminated\`). Maintains the denormalized \`eligibility_view\` table + OpenSearch \`eligibility\` index. Graceful fallback to pg-only on OpenSearch failure. |
| \`outbox-relay/\` | Polls the \`outbox\` table in each service DB (atlas / member / group / plan). Publishes unsent rows to Pub/Sub with retry + exponential backoff, marks \`published_at\` on success. Guarantees **at-least-once event delivery** without 2PC. |

## Prerequisites

| Tool | Version |
|---|---|
| Docker | 24+ |
| Docker Compose | v2 |
| Python | 3.11+ (standalone dev) |

## Run with the rest of the platform

\`\`\`bash
git clone https://github.com/$OWNER/eligibility-platform
cd eligibility-platform
./bootstrap.sh
make up
\`\`\`

## Run a worker standalone

Each worker has its own Dockerfile.

\`\`\`bash
# Configure
cp .env.example .env

# Build a single worker image
docker build -t eligibility-ingestion:local    -f ingestion/Dockerfile    .
docker build -t eligibility-projector:local    -f projector/Dockerfile    .
docker build -t eligibility-outbox-relay:local -f outbox-relay/Dockerfile .

# Run (requires Pub/Sub emulator + Postgres + MinIO running)
docker run --rm --env-file .env eligibility-ingestion:local
\`\`\`

## Develop locally

\`\`\`bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e libs/python-common -e libs/x12-834
pip install fastapi 'uvicorn[standard]' sqlalchemy asyncpg 'psycopg[binary]' \\
  httpx pydantic pydantic-settings structlog tenacity cryptography \\
  google-cloud-pubsub boto3 \\
  opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp \\
  opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy
\`\`\`

## Test

\`\`\`bash
pip install pytest pytest-asyncio
for w in ingestion projector outbox-relay; do
  echo "--- \$w"
  (cd \$w && PYTHONPATH=.:../libs/python-common/src:../libs/x12-834/src \\
     python -m pytest tests -q)
done
\`\`\`

## Environment variables

See [\`.env.example\`](.env.example).

## License

MIT.
EOF

cat > "$DESKTOP/eligibility-workers/.env.example" <<'EOF'
# ----- Workers environment --------------------------------------------
# All three workers (ingestion, projector, outbox-relay) read these.

LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

# Pub/Sub
PUBSUB_PROJECT_ID=local-eligibility
PUBSUB_EMULATOR_HOST=pubsub:8085

# Tenant fallback
TENANT_DEFAULT=11111111-1111-1111-1111-111111111111

# ----- ingestion worker -----------------------------------------------
SERVICE_NAME=ingestion
ATLAS_URL=http://atlas:8000
MEMBER_URL=http://member:8000
GROUP_URL=http://group:8000
PLAN_URL=http://plan:8000
MINIO_ENDPOINT=http://minio:9000
MINIO_BUCKET=eligibility-files
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio12345

# ----- projector worker -----------------------------------------------
# (Uncomment when running standalone; ATLAS_DB_URL holds the read model)
# SERVICE_NAME=projector
ATLAS_DB_URL=postgresql+psycopg://postgres:dev_pw@atlas_db:5432/atlas_db
MEMBER_DB_URL=postgresql+psycopg://postgres:dev_pw@member_db:5432/member_db
GROUP_DB_URL=postgresql+psycopg://postgres:dev_pw@group_db:5432/group_db
PLAN_DB_URL=postgresql+psycopg://postgres:dev_pw@plan_db:5432/plan_db
OPENSEARCH_URL=http://opensearch:9200

# ----- outbox-relay worker -------------------------------------------
# (uses the same DB_URLs above + Pub/Sub project)
EOF

# ────────────────────────────────────────────────────────────────────────
# frontend
# ────────────────────────────────────────────────────────────────────────
cat > "$DESKTOP/eligibility-frontend/README.md" <<EOF
# eligibility-frontend

React + TypeScript + Vite + TanStack UI for the **Eligibility & Enrollment Platform**.

## Features

- **Eligibility grid** — virtualized, server-side cursor pagination, per-column sort + filter (inline icons in headers), column show/hide, density toggle (comfortable / compact), saved views.
- **Status filter chips** at the top — Active / Pending / Terminated, toggleable.
- **Active filter chips** below toolbar — every Advanced Search filter shows as a removable chip, with "Clear all".
- **Advanced Search modal** — 15 fields grouped into Member / Group&Plan / Coverage dates sections.
- **Add Member modal** — orchestrated through the BFF GraphQL \`addMember\` mutation. Auto-generates Member ID Card if blank.
- **Member detail drawer** with bitemporal timeline (valid-time vs transaction-time, in-force flag).
- **Groups admin** (\`/groups\`) — full CRUD for payers, employers, subgroups, plan visibility.
- **File Upload + Job Status** — resumable upload, polls BFF \`fileJob\` until terminal.
- **Light + dark theme** (proper readable token palette).
- **Click-outside + Escape** closes every popover (modern UX).

## Prerequisites

| Tool | Version |
|---|---|
| Node | 20+ |
| npm | 10+ |
| Docker | 24+ (only if running the BFF backend stack) |

## Run

\`\`\`bash
# 1. Configure
cp .env.example .env
# (set VITE_BFF_URL — defaults to http://localhost:4000)

# 2. Install + dev
npm install
npm run dev    # → http://localhost:5173 (or 3000 in docker-compose)
\`\`\`

## Build for production

\`\`\`bash
npm run build       # outputs to dist/
npm run preview     # serves dist/ for sanity check
\`\`\`

## Test

\`\`\`bash
npm run typecheck   # strict tsc
npm run test --if-present
npm run lint
\`\`\`

## With Docker

This repo's Dockerfile runs Vite dev server on port 5173. The orchestration repo maps it to host port **3000**.

\`\`\`bash
docker build -t eligibility-frontend:local .
docker run --rm -p 3000:5173 eligibility-frontend:local
# → http://localhost:3000
\`\`\`

## Environment variables

See [\`.env.example\`](.env.example).

| Var | Default | Purpose |
|---|---|---|
| \`VITE_BFF_URL\` | \`http://localhost:4000\` | BFF GraphQL + REST endpoint |

## Project layout

\`\`\`
src/
├── api/               # GraphQL client (graphql-request) + typed wrappers
│   ├── bff.ts         # Queries + mutations for the BFF
│   └── types.ts       # Shared TS types (mirror BFF schema)
├── app/
│   ├── AppShell.tsx   # Layout: header nav, theme toggle, footer
│   └── GlobalStatus.tsx
├── components/        # Reusable: Button, Modal, Spinner, Banner, ...
├── features/
│   ├── eligibility/   # Grid, AdvancedSearchModal, AddMemberModal, SavedViews
│   ├── groups/        # GroupsAdmin (bonus task)
│   ├── member/        # Member detail drawer + timeline
│   └── upload/        # File upload + job status
├── lib/               # Hooks: useClickOutside, useDebounce, useLocalStorage, router
├── styles/            # Token palette (CSS vars, light + dark)
└── main.tsx           # React entrypoint
\`\`\`

## Talks to

- BFF GraphQL: \`POST {VITE_BFF_URL}/graphql\`
- BFF REST upload: \`POST {VITE_BFF_URL}/files/eligibility\`

Headers added on every request:
- \`X-Tenant-Id\` (multi-tenant routing)
- \`X-Correlation-Id\` (request tracing)

## License

MIT.
EOF

cat > "$DESKTOP/eligibility-frontend/.env.example" <<'EOF'
# ----- Frontend environment ------------------------------------------
# Vite reads vars prefixed with VITE_ at build time and exposes them as
# import.meta.env.VITE_<NAME>. Anything else is ignored.

# Where the BFF lives. In docker-compose this is reached from the
# browser at host port 4000 even though the BFF binds to 8000 inside the network.
VITE_BFF_URL=http://localhost:4000
EOF

# ────────────────────────────────────────────────────────────────────────
# eligibility-platform (orchestration / meta)
# ────────────────────────────────────────────────────────────────────────
echo "→ writing $DESKTOP/eligibility-platform/.env.example (orchestration)"
cat > "$DESKTOP/eligibility-platform/.env.example" <<'EOF'
# ----- Orchestration environment -------------------------------------
# Used by docker-compose.yml. Copy to .env if you want to override.

# Postgres (all 4 databases share this password locally)
POSTGRES_PASSWORD=dev_pw

# Pub/Sub emulator project (any string; not real GCP)
PUBSUB_PROJECT_ID=local-eligibility

# Object storage (MinIO — local S3-compatible)
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio12345
MINIO_BUCKET=eligibility-files

# Logging / observability
LOG_LEVEL=INFO

# Default tenant for seed + demo (multi-tenancy is by tenant_id everywhere)
TENANT_DEFAULT=11111111-1111-1111-1111-111111111111
EOF

# Note: the meta repo README is more comprehensive and lives in its own update step.

echo ""
echo "✅ READMEs + .env.example written for all 8 repos."
ls -1 "$DESKTOP" | grep eligibility-
