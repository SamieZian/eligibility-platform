# Eligibility & Enrollment Platform

Distributed microservices system for healthcare eligibility. Ingests ANSI X12 **834** enrollment files (CSV/XLSX too), maintains a **bitemporal coverage timeline**, and powers a React console with full search, file upload, member management, and group/subgroup admin.

**This is the orchestration / demo repo.** The 7 actual services each live in their own repo:

| Repo | Purpose | Stack |
|---|---|---|
| [`eligibility-atlas`](https://github.com/SamieZian/eligibility-atlas) | Bitemporal enrollment | Python · FastAPI · Postgres |
| [`eligibility-member`](https://github.com/SamieZian/eligibility-member) | Members + dependents | Python · FastAPI · Postgres · KMS |
| [`eligibility-group`](https://github.com/SamieZian/eligibility-group) | Payers / employers / subgroups / plan visibility | Python · FastAPI · Postgres |
| [`eligibility-plan`](https://github.com/SamieZian/eligibility-plan) | Plan catalog | Python · FastAPI · Postgres · Redis |
| [`eligibility-bff`](https://github.com/SamieZian/eligibility-bff) | GraphQL gateway + file upload | FastAPI · Strawberry GraphQL |
| [`eligibility-workers`](https://github.com/SamieZian/eligibility-workers) | Ingestion · projector · outbox-relay | Python async |
| [`eligibility-frontend`](https://github.com/SamieZian/eligibility-frontend) | React UI | Vite · React · TypeScript · TanStack |

Each service is **independently deployable** — own repo, own Dockerfile, own database, own CI. They communicate only via the network (REST/GraphQL + Pub/Sub events).

**📐 [ARCHITECTURE.md](ARCHITECTURE.md)** — Reader's guide to the whole system: topology, request-path walkthroughs, tech choices with rationale + rejected alternatives, bitemporal deep-dive, CQRS reasoning, production GCP deployment, and what we consciously did NOT build.

---

## Prerequisites

### Required

| Tool | Version | How to install |
|---|---|---|
| **Docker Engine** | 24+ | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (macOS/Windows) · `apt install docker.io` / `dnf install docker` (Linux) · [OrbStack](https://orbstack.dev/) + [Colima](https://github.com/abiosoft/colima) also work |
| **Docker Compose** | v2 — the `docker compose` plugin (NOT legacy `docker-compose`) | Ships with Docker Desktop · `apt install docker-compose-plugin` on Debian/Ubuntu |
| **Git** | 2.30+ | `brew install git` · `apt install git` · [git-scm.com](https://git-scm.com/downloads) |
| **GNU Make** | any recent | Pre-installed on macOS (via Xcode CLT) and Linux · Windows: use WSL2 |

### Optional (only for running services outside Docker)

| Tool | Version | When you need it |
|---|---|---|
| **Python** | 3.11–3.12 | Running a single service from its repo (`poetry run uvicorn …`) |
| **Poetry** | 1.8+ | Installing per-service Python deps — `pipx install poetry==1.8.3` |
| **Node.js** | 20+ | Running the frontend dev server outside Docker (`npm run dev`) |
| **k6** | latest | Running the load tests in `tests/load/` |

### System resources

- **RAM**: ~6 GB free while `make up` is running (18 containers)
- **Disk**: ~10 GB free — first-time image build downloads ~2 GB
- **Ports used on localhost**: 3000 (frontend), 4000 (BFF), 5441–5444 (Postgres), 6379 (Redis), 8001–8004 (services), 8083 (Debezium), 8085 (Pub/Sub), 9000–9001 (MinIO), 9200 (OpenSearch), 16686 (Jaeger). If any of these are in use on your machine, stop the conflicting process before `make up`.

### Verify your prerequisites

```bash
docker version                  # expect "Server: Docker Engine ... Version: 24+"
docker compose version          # expect "Docker Compose version v2.x"
git --version                   # any 2.30+
make --version                  # any GNU Make
```

If all four print a version, you're ready.

## Architecture

```
 ┌───────────────────┐       ┌──────────────────────────────┐
 │  React + TS UI    │──────▶│ BFF (FastAPI + Strawberry)   │
 │  Vite + TanStack  │       │ OIDC mock · circuit breakers │
 └───────────────────┘       │ rate-limit · DataLoaders     │
                             └──┬──────┬─────┬──────┬───────┘
                                ▼      ▼     ▼      ▼
                          ┌────────┐┌────────┐┌──────┐┌──────┐
                          │ atlas  ││ member ││group ││ plan │   ◄── 4 services
                          │(enrol- ││        ││      ││      │
                          │ ment,  ││        ││      ││      │
                          │bitemp.)││        ││      ││      │
                          └───┬────┘└───┬────┘└──┬───┘└──┬───┘
                              ▼         ▼        ▼       ▼
                          ┌────────┐┌────────┐┌──────┐┌──────┐
                          │atlas_db││member_ ││group_││plan_ │   ◄── 4 databases
                          │        ││  db    ││  db  ││  db  │       (one per svc)
                          └───┬────┘└───┬────┘└──┬───┘└──┬───┘
                              └──── outbox ──────┴───────┘
                                    │ (per-svc)
                                    ▼
                          Pub/Sub emulator (retries + DLQ)
                                    │
                      ┌─────────────┼─────────────┐
                      ▼             ▼             ▼
              ingestion       projector       outbox-
              worker          worker          relay
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │ eligibility_view (pg)   │
                       │  +  OpenSearch index    │
                       └─────────────────────────┘
```

Supporting infra (all in compose): **Redis** (cache + saga state), **MinIO** (S3-compatible for raw 834 files), **OpenSearch** (fuzzy search), **Pub/Sub emulator**, **Jaeger** (OTel UI).

---

## Quickstart — from zero to a running stack

The platform is split across **8 repos** (one orchestration repo + 7 services).
`bootstrap.sh` clones the 7 siblings next to the orchestration repo, so the
very first step is to create a **dedicated workspace directory** that will
hold all 8 side-by-side.

```bash
# 1. Create a dedicated workspace (keeps the 8 repos together)
mkdir -p ~/Desktop/eligibility-workspace && cd ~/Desktop/eligibility-workspace

# 2. Clone the orchestration repo
git clone https://github.com/SamieZian/eligibility-platform.git
cd eligibility-platform

# 3. Clone the 7 sibling service repos next to this one
./bootstrap.sh

# 4. Copy the env template (defaults work for local dev; no edits needed)
cp .env.example .env

# 5. Boot the whole stack — builds 9 Docker images, starts 18 containers (~3 min first time)
make up
```

When `make up` finishes, the console prints `All services healthy.` and the
console UI is at http://localhost:3000.

**Layout after these steps:**

```
~/Desktop/eligibility-workspace/         ← the workspace dir you created in step 1
├── eligibility-platform/                ← orchestration (this repo); where you run make
│   ├── docker-compose.yml
│   ├── Makefile
│   ├── samples/                         ← sample 834 EDI files for `make ingest`
│   ├── bootstrap.sh
│   ├── ARCHITECTURE.md                  ← full design doc
│   ├── .env.example  →  .env
│   └── README.md                        ← this file
├── eligibility-atlas/                   ← cloned by bootstrap.sh
├── eligibility-member/
├── eligibility-group/
├── eligibility-plan/
├── eligibility-bff/
├── eligibility-workers/
└── eligibility-frontend/
```

> **Windows users**: run all commands inside **WSL2 Ubuntu** (Docker Desktop's
> WSL2 backend mounts the filesystem there). PowerShell / cmd will not work
> — Makefile + bash heredocs are POSIX-only.

### If something goes wrong during `make up`

```bash
make down                               # stop + remove containers
docker compose logs --tail 100 atlas    # inspect one service's logs
make clean                              # stop + delete volumes (nuclear — wipes seeded data)
make up                                 # try again
```

Port conflicts are the most common issue — see the [prerequisite port list](#system-resources) above.

## Demo flow

```bash
make up                  # boot everything (~3 min first time, builds 9 images)
make seed-demo           # rich dataset: seed + ingest + varied statuses (active/pending/terminated/corrected)
make verify              # asserts bitemporal rows + projector caught up

open http://localhost:3000    # the React UI
```

Or, for the minimal flow (just the raw 834 ingest, no post-ingest mutations):

```bash
make seed                # payers + employers + plans
make ingest              # 18 members from samples/834_demo.x12 (all active)
```

`make seed-demo` builds on `make seed` + `make ingest` and adds:
- **4 pending members** with future effective dates (2026-08-01)
- **3 terminations** closing existing active coverage on 2026-06-30
- **1 plan change saga** — one member switches Silver → Bronze on 2026-07-01 (shows as two bitemporal segments in the timeline drawer)

In the UI:
- **Eligibility** tab — 24+ enrollments, search "sharma", advanced filters, click any row for the bitemporal timeline drawer
- **Groups** tab (bonus task) — payer / employer / subgroup / plan-visibility CRUD
- **Upload** tab — drag in any 834/CSV file from `samples/`, watch it process
- **+ Add New Member** button — full form, orchestrates create-member + create-enrollment in one round-trip via BFF GraphQL `addMember` mutation. Auto-generates Member ID Card if blank.
- **Row Actions menu** (☰ on each row):
  - *View timeline* — opens the member drawer with a **visual Gantt chart** of coverage segments (green = active, red = termed, grey = historical), today marker, plan-grouped rows. Toggle to tabular view for raw bitemporal columns.
  - *Terminate* — closes the in-force segment on a chosen date (bitemporally correct: opens a TERMED row, preserves the original ACTIVE row's history).
  - *Change plan* — saga: TERMINATE old (day before new effective) + ADD new. Produces two new timeline segments.
  - *Edit details* — correct member name / DOB / gender. Upserts via member svc, emits `MemberUpserted`, projector fans the new name into `eligibility_view`.

## Useful URLs

| URL | What |
|---|---|
| http://localhost:3000 | React frontend |
| http://localhost:4000/graphql | BFF GraphQL playground |
| http://localhost:4000/files/eligibility | BFF file upload (POST multipart) |
| http://localhost:16686 | Jaeger (distributed traces) |
| http://localhost:9001 | MinIO console — user: `minio` / `minio12345` |
| http://localhost:9200 | OpenSearch |
| postgres://localhost:5441 / 5442 / 5443 / 5444 | atlas / member / group / plan DBs |

## Deploy to GCP

Production IaC lives in [`pulumi/gcp/`](pulumi/gcp/) — a Pulumi Python
program that deploys all services to **Cloud Run**, **Cloud SQL**
(one Postgres per bounded context), **Pub/Sub** (topics + subs + DLQ),
**Cloud Storage**, **Secret Manager**, and **Artifact Registry** on a
private VPC. See [`pulumi/gcp/README.md`](pulumi/gcp/README.md) for
install / `pulumi up` / teardown.

## Feature checklist (as built)

| Feature | Status |
|---|---|
| 4 microservices, each with own DB & Dockerfile | ✓ |
| ANSI X12 834 ingestion (streaming parser) | ✓ |
| CSV ingestion | ✓ |
| Bitemporal enrollment model (handles 030 corrections) | ✓ |
| Transactional outbox + Pub/Sub at-least-once | ✓ |
| CQRS read model — Postgres view + OpenSearch | ✓ |
| Saga orchestration (REPLACE_FILE, plan changes) | ✓ |
| GraphQL + REST BFF | ✓ |
| Eligibility grid (sort, filter, pagination, column config, density) | ✓ |
| Advanced search modal (15 fields) | ✓ |
| Quick search (debounced, fuzzy via OS) | ✓ |
| Member detail drawer with bitemporal **Gantt chart** (+ tabular toggle) | ✓ |
| **Add Member** form wired end-to-end | ✓ |
| **Groups admin** — payer / employer / subgroup / plan visibility CRUD (bonus) | ✓ |
| **Row actions** — View timeline / Terminate / Change plan / Edit details | ✓ |
| File upload page with job status polling | ✓ |
| Saved views (per-user filter presets) | ✓ |
| Light + dark theme | ✓ |
| Click-outside + Escape closes all popovers | ✓ |
| Status filter chips + active filter chips | ✓ |
| Auto-generated Member ID Card on new member | ✓ |
| KMS-encrypted SSN at rest | ✓ |
| Circuit breakers + retry w/ jitter + timeouts | ✓ |
| OpenTelemetry tracing → Jaeger | ✓ |
| Per-row idempotency on 834 retries | ✓ |
| Health endpoints (`/livez`, `/readyz`) on every service | ✓ |
| `.env.example` in every repo | ✓ |
| Per-repo README with prereqs + setup + test | ✓ |
| **Idempotency middleware** (HTTP `Idempotency-Key` → dedup, replay on retry) | ✓ |
| **Optimistic locking** (`version` column enforced on UPDATEs → 412 on conflict) | ✓ |
| **Tenant isolation** on member lookup (`X-Tenant-Id` required + matched) | ✓ |
| **Postgres `statement_timeout` / `lock_timeout`** per connection (pool safety) | ✓ |
| **SIGTERM graceful drain** (`/readyz` → 503, in-flight drains, pool disposed) | ✓ |
| **GraphQL error envelope** (`extensions.code` + `retryable` + `correlation_id`) | ✓ |
| **GraphQL DataLoader** batching (kills N+1 on `groupAdmin`) | ✓ |
| **GraphQL query depth limit** (max 8, rejects AST-expanded attacks) | ✓ |
| **GCP-native observability** (Cloud Logging + Cloud Trace exporters, opt-in) | ✓ |
| **Pulumi Python IaC** for GCP (Cloud Run, Cloud SQL, Pub/Sub, GCS, SM) | ✓ |
| **Vertex AI Document AI** hook (scanned-PDF 834 extraction, opt-in) | ✓ |

## Sample 834 files

Under [`samples/`](samples/) — see [`samples/README.md`](samples/README.md) for a walkthrough.

| File | What it does |
|---|---|
| `834_sample.x12` | 5 ADDs + 1 TERMINATE + 1 CORRECTION (~3 KB) — the demo file. Ingest with `make ingest`. |
| `834_demo.x12` | 18 members across Swiggy/Zomato + 4 subgroups + 3 plans (~3.6 KB) |
| `834_replace.x12` | Full-file REPLACE scenario for the saga |
| `834_large.x12` | 1000 members for load testing |

Drag any of these into the Upload page in the UI to exercise the full pipeline.

## All `make` targets

```bash
make help                                    # list everything
make up                                      # docker compose up -d (builds from sibling repos)
make down                                    # stop
make clean                                   # stop + delete volumes
make logs [S=atlas]                          # tail logs (optionally one service)
make seed                                    # seed payers/employers/plans via BFF CLI
make ingest [F=samples/834_demo.x12]         # upload an 834 file
make search Q=sharma                         # fuzzy search via GraphQL
make verify                                  # assert DB + OS state after ingest
make test                                    # run unit + integration tests across all repos
make load                                    # k6 small load run
make chaos-kill-projector                    # kill projector, write, restart, verify catch-up
make replay-dlq TOPIC=enrollment.events.dlq  # re-drive a DLQ topic
make psql D=atlas_db                         # psql into a service's DB
make demo                                    # automated tour
```

## Environment variables

See [`.env.example`](.env.example). All values have safe defaults for local dev — `cp .env.example .env` and you're done.

For per-service env vars, see each repo's `.env.example`.

## Patterns shipped (where to find them)

| Pattern | Code |
|---|---|
| Bitemporal model | `eligibility-atlas/app/domain/enrollment.py` |
| Transactional outbox | `eligibility-atlas/app/application/commands.py` (write); `eligibility-workers/outbox-relay/` (publish) |
| CQRS projection | `eligibility-workers/projector/app/handlers.py` |
| Saga orchestration (FSM) | `eligibility-atlas/app/domain/saga.py` |
| Circuit breaker | `libs/python-common/.../circuit.py` (vendored in each Python repo) |
| Retry w/ jitter | `libs/python-common/.../retry.py` |
| Streaming X12 834 parser | `libs/x12-834/src/x12_834/parser.py` (vendored in workers + ingestion uses) |
| KMS envelope encryption | `libs/python-common/.../kms.py`; member svc encrypts SSN |
| Hexagonal layout | every Python service: `app/{domain,application,infra,interfaces}` |
| Click-outside hook | `eligibility-frontend/src/lib/useClickOutside.ts` |

## Load test results (k6, 50 VUs, 50 sec)

```
http_req_duration p95 = 390ms   (target < 300ms — local single-instance)
http_req_duration p99 = 429ms   ✓ (target < 800ms)
http_req_failed       = 0%      ✓ (target < 1%)
total requests        = 3,155   (63 req/s sustained)
```

`make load` to re-run. p95 misses the 300ms target on a single-instance dev box; in production with Cloud Run autoscaling + read replicas + warm OpenSearch indices, it stays inside budget.

## Fault-tolerance budget (real numbers)

| Edge | Timeout | Retries | Backoff | Circuit breaker |
|---|---|---|---|---|
| Browser → BFF | 15s / 5s srv | 1 on 503 | — | — |
| BFF → svc | 2s | 3 | exp 50/150/450ms + jitter | 5 fails / 10s window → open 30s |
| Service → Pub/Sub (relay) | 5s | 5 | exp 0.1s → 5s | open on > 5% err |
| Pub/Sub → consumer | ack 60s | 7 | exp 10s → 600s | DLQ after 7 |
| Projector → OpenSearch | 3s | 5 | exp 0.1s → 5s | graceful fallback to pg |

## Verifying everything works

```bash
# After make up succeeds:
make verify             # asserts pg + OS state matches expectations

# Or manually:
docker compose ps       # all 18 containers should show "healthy"
curl http://localhost:4000/livez   # → 200
curl http://localhost:3000          # → React HTML
```

## License

MIT.
