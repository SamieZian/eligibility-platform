# Eligibility & Enrollment Platform

Distributed microservices system for healthcare eligibility. Ingests ANSI X12 **834** enrollment files (CSV/XLSX too), maintains a **bitemporal coverage timeline**, and powers a React search console.

**This is the orchestration / demo repo.** The actual services each live in their own repo:

| Repo | Purpose | Stack |
|---|---|---|
| [`eligibility-atlas`](https://github.com/SamieZian/eligibility-atlas) | Enrollment — bitemporal core | Python + FastAPI + Postgres |
| [`eligibility-member`](https://github.com/SamieZian/eligibility-member) | Members + dependents | Python + FastAPI + Postgres + KMS |
| [`eligibility-group`](https://github.com/SamieZian/eligibility-group) | Payer / employer / subgroup / plan visibility | Python + FastAPI + Postgres |
| [`eligibility-plan`](https://github.com/SamieZian/eligibility-plan) | Plan catalog | Python + FastAPI + Postgres + Redis |
| [`eligibility-bff`](https://github.com/SamieZian/eligibility-bff) | GraphQL gateway + file upload | FastAPI + Strawberry GraphQL |
| [`eligibility-workers`](https://github.com/SamieZian/eligibility-workers) | Ingestion / projector / outbox-relay | Python async |
| [`eligibility-frontend`](https://github.com/SamieZian/eligibility-frontend) | React UI | Vite + React + TS + TanStack |

Each service is **independently deployable** — its own Dockerfile, its own CI, its own database. They only communicate via the network (REST/GraphQL + Pub/Sub events).

## Architecture

```
 ┌───────────────┐       ┌──────────────────────────────┐
 │ React + TS UI │──────▶│ BFF (FastAPI + GraphQL)      │
 └───────────────┘       │ OIDC • circuit breakers      │
                         │ rate-limit • DataLoaders     │
                         └──┬──────┬─────┬──────┬───────┘
                            ▼      ▼     ▼      ▼
                      ┌────────┐┌────────┐┌──────┐┌──────┐
                      │ atlas  ││ member ││group ││ plan │   ◄── 4 services
                      │(enrol- ││        ││      ││      │
                      │lment,  ││        ││      ││      │
                      │bitempo-││        ││      ││      │
                      │ ral)   ││        ││      ││      │
                      └───┬────┘└───┬────┘└──┬───┘└──┬───┘
                          ▼         ▼        ▼       ▼
                      ┌────────┐┌────────┐┌──────┐┌──────┐
                      │atlas_db││member_ ││group_││plan_ │   ◄── 4 databases
                      │        ││  db    ││  db  ││  db  │
                      └───┬────┘└───┬────┘└──┬───┘└──┬───┘
                          └──── outbox ──────┴───────┘
                                │
                                ▼
                      Pub/Sub emulator (retries + DLQ)
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
             ingestion      projector    outbox-
             worker         worker       relay
                                │
                                ▼
                      ┌─────────────────────┐
                      │ eligibility_view +  │
                      │ OpenSearch          │
                      └─────────────────────┘
```

## Quickstart — 3 commands

Prerequisites: **Docker** (or [colima](https://github.com/abiosoft/colima)), **git**, **gh** CLI (optional — only needed if cloning via SSH).

```bash
# 1. Clone this repo
git clone https://github.com/SamieZian/eligibility-platform.git
cd eligibility-platform

# 2. Clone all 7 sibling service repos into the parent dir
./bootstrap.sh

# 3. Bring everything up
make up
```

That's it. `make up` builds **8 Docker images** (4 services + bff + 3 workers + frontend) and spins them up with their 4 dedicated Postgres instances + Redis + Pub/Sub emulator + MinIO + OpenSearch + Jaeger.

Layout after `bootstrap.sh`:

```
Desktop/
├── eligibility-platform/     # ← you are here (orchestration + demo)
│   ├── docker-compose.yml    # builds images from sibling repos
│   ├── Makefile              # make up / seed / ingest / search / verify
│   ├── samples/              # ← 834 files to upload
│   ├── bootstrap.sh
│   └── README.md             # this file
├── eligibility-atlas/        # cloned by bootstrap.sh
├── eligibility-member/
├── eligibility-group/
├── eligibility-plan/
├── eligibility-bff/
├── eligibility-workers/
└── eligibility-frontend/
```

## Demo flow

```bash
make up                  # boot the full stack (~2-3 min first time, builds 8 images)
make seed                # seed ICICI + Aetna payers, Swiggy + Zomato employers, 3 plans
make ingest              # upload samples/834_sample.x12 via BFF
make verify              # asserts bitemporal rows + OS projection

open http://localhost:5173    # UI
```

In the UI:
- **Grid**: 5 enrollments (Sharma, Patel, Kaur, Nair + Rohit the dependent).
- **Quick search**: type `sharma` → filters to Priya + Rohit.
- **Advanced Search**: click the button → modal with all 15 filter fields (Member ID, SSN last 4, employer, plan, DOB, date ranges, status, etc.).
- **Member detail**: click a row → drawer with bitemporal timeline. For Simran Kaur (who had a CORRECTION in the 834) you'll see both the original in-force row and the corrected one.
- **Upload**: nav → Upload → drag in `samples/834_sample.x12` → watch job status poll.

## Feature checklist

| Feature | Where | How to test |
|---|---|---|
| 4 independently-deployable services | Each has its own repo + Dockerfile | `docker ps` shows 4 distinct service containers |
| 4 private databases | docker-compose.yml | `docker ps` shows 4 pg containers on ports 5441-5444 |
| Bitemporal enrollment | `eligibility-atlas/app/domain/enrollment.py` | Ingest 834_sample.x12 → open Simran Kaur → timeline shows 2 rows (corrected + historical) |
| Transactional outbox | `eligibility-common/outbox.py` + `eligibility-workers/outbox-relay/` | `select count(*) from outbox` after any write |
| CQRS projector | `eligibility-workers/projector/` | `eligibility_view` table and OpenSearch `eligibility` index both populated |
| Ingestion pipeline | `eligibility-workers/ingestion/` | `make ingest` → all INS loops mapped to atlas commands |
| Idempotency | atlas `processed_segments` table | Re-ingest same file → no new enrollments (dedup by ISA13:GS06:ST02:INS_pos) |
| GraphQL search | `eligibility-bff/app/schema.py` | `make search Q=sharma` |
| Fuzzy search via OpenSearch | `eligibility-bff/app/search.py` | UI quick search box (250ms debounce) |
| Advanced search modal | `eligibility-frontend/src/features/eligibility/AdvancedSearchModal.tsx` | Click "Advanced Search" in UI |
| Bitemporal timeline UI | `eligibility-frontend/src/features/member/Detail.tsx` | Click any row → drawer with timeline |
| File upload | `eligibility-bff/app/upload.py` + `.../frontend/.../FileUpload.tsx` | Upload page → pick file → watch status |
| Saved views | `eligibility-frontend/src/features/eligibility/SavedViews.tsx` | "Saved Views" dropdown in toolbar |
| Column config | Grid | "Columns" details in toolbar |
| Density toggle | Grid | "Comfortable/Compact" dropdown |
| Correlation IDs end-to-end | `eligibility-common/http_middleware.py` | `X-Correlation-Id` on every response + footer of UI |
| Circuit breakers | `eligibility-common/circuit.py` | BFF → svc calls use CircuitBreaker |
| Retry w/ jitter | `eligibility-common/retry.py` | Ingestion resolver wraps httpx calls |
| KMS envelope encryption | `eligibility-common/kms.py` + member svc | `select ssn_ciphertext from members_lookup` |
| HIPAA log scrubbing | `eligibility-common/logging.py` | Any "ssn" key in log output is `***` |

## Sample 834 files

Under `samples/` — see [`samples/README.md`](samples/README.md) for the full walkthrough of what's in each file. **Drag `samples/834_sample.x12` into the Upload page** or run `make ingest`.

## All `make` targets

```bash
make up                              # docker compose up -d (builds from sibling repos)
make down                            # stop
make clean                           # stop + wipe volumes
make logs [S=atlas]                  # tail logs (optionally single service)
make seed                            # seed synthetic payers/employers/plans via BFF CLI
make ingest [F=samples/834_sample.x12]   # upload 834 via BFF
make search Q=sharma                 # fuzzy search via GraphQL
make verify                          # assert DB + OS state
make test                            # run all unit + integration tests
make load                            # k6 small load run
make chaos-kill-projector            # kill projector, write, restart, verify catch-up
make replay-dlq TOPIC=xyz.dlq        # re-drive DLQ messages
make psql D=atlas_db                 # psql into any service's DB
make demo                            # automated tour
```

## Useful URLs once up

| URL | What |
|---|---|
| http://localhost:5173 | Frontend |
| http://localhost:4000/graphql | BFF GraphQL playground |
| http://localhost:4000/files/eligibility | BFF file upload (POST) |
| http://localhost:16686 | Jaeger (distributed traces) |
| http://localhost:9001 | MinIO console (user: `minio` / `minio12345`) |
| http://localhost:9200 | OpenSearch |

## Design highlights

| Concern | Pattern used | Where |
|---|---|---|
| Retro-active 834 corrections | **Bitemporal** (valid_time + transaction_time) | `eligibility-atlas/app/domain/enrollment.py` |
| Atomic "write DB + emit event" | **Transactional outbox** | every service's `outbox` table + `eligibility-workers/outbox-relay/` |
| Read-model sync | **CQRS** via Pub/Sub events → projector | `eligibility-workers/projector/` |
| Search at scale | Postgres `eligibility_view` (exact) + OpenSearch (fuzzy) | `eligibility-bff/app/search.py` |
| Multi-step workflows | **Saga orchestration** (FSM + compensations) | `eligibility-atlas/app/domain/saga.py` |
| 834 retry dedup | `(trading_partner, ISA13, GS06, ST02, ins_pos)` key | `processed_segments` table |
| Cascading failure prevention | **Circuit breaker + timeout + retry w/ jitter** | `eligibility-common/circuit.py`, `retry.py` |
| Tenant isolation | Postgres `set_config('app.tenant_id', ...)` per request | `eligibility-common/db.py` |
| PHI at rest | Envelope-encrypted SSN via KMS | `eligibility-common/kms.py` |
| Observability | OpenTelemetry → Jaeger + structured JSON logs + correlation IDs | `eligibility-common/tracing.py` |

## Fault-tolerance budget

| Edge | Timeout | Retries | Backoff | Circuit breaker |
|---|---|---|---|---|
| Browser → BFF | 15s client / 5s srv | 1 on 503 | — | — |
| BFF → svc | 2s | 3 | exp 50/150/450ms + jitter | 5 fails / 10s window |
| Service → Pub/Sub (relay) | 5s | 5 | exp 0.1s → 5s | open on > 5% err |
| Pub/Sub → consumer | ack 60s | 7 | exp 10s → 600s | DLQ after 7 |
| Projector → OS | 3s | 5 | exp 0.1s → 5s | graceful fallback to pg |

## Repos and commits

This repo (eligibility-platform) contains:
- `docker-compose.yml` — multi-repo build
- `Makefile` — common commands
- `bootstrap.sh` — clones all 7 sibling repos
- `samples/` — 834 EDI files
- `tests/e2e/` — end-to-end verifier
- `tests/golden/` — 834 fixture generator
- `docs/adr/` — architecture decision records
- `docs/runbooks/` — on-call runbooks

All 7 service repos have their own README explaining what they do, how to run standalone, and how to test. CI is configured in each.

## License

MIT.
