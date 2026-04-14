# Eligibility & Enrollment Platform

Take-home distributed system for health/dental eligibility (ICICI → Swiggy/Zomato → members + dependents). Ingests ANSI X12 **834** enrollment files (CSV/XLSX too), maintains a **bitemporal coverage timeline**, and powers a React search console.

**One command to run everything locally:** `make up`

---

## The diagram — 4 services, 4 databases

```
 ┌───────────────┐       ┌──────────────────────────────┐
 │ React + TS UI │──────▶│ BFF (FastAPI + GraphQL)      │
 │ (Vite, tan-   │       │ OIDC • circuit breakers      │
 │  stack-table) │       │ rate-limit • DataLoaders     │
 └───────────────┘       └───┬────┬─────┬─────┬─────────┘
                             ▼    ▼     ▼     ▼
               ┌──────────┐ ┌────────┐ ┌──────┐ ┌──────┐
               │  atlas   │ │ member │ │group │ │ plan │   ◄── 4 services
               │(enroll- │ │        │ │      │ │      │
               │ ment,   │ │        │ │      │ │      │
               │bitempo- │ │        │ │      │ │      │
               │  ral)   │ │        │ │      │ │      │
               └────┬─────┘ └───┬────┘ └──┬───┘ └──┬───┘
                    ▼           ▼         ▼        ▼
               ┌──────────┐ ┌────────┐ ┌──────┐ ┌──────┐
               │ atlas_db │ │member_ │ │group_│ │plan_ │   ◄── 4 databases
               │   (pg)   │ │  db    │ │  db  │ │  db  │
               └────┬─────┘ └───┬────┘ └──┬───┘ └──┬───┘
                    └───── outbox ────────┴────────┘
                          │ (Debezium CDC + outbox relay)
                          ▼
                    Pub/Sub emulator (retries + DLQ)
                          │
                ┌─────────┴──────────┐
                ▼                     ▼
         ingestion worker       projector worker
         (834/CSV → atlas)      (events + CDC → pg
                                view + OpenSearch)
                                     │
                                     ▼
                       ┌─────────────────────────┐
                       │ eligibility_view (pg) + │
                       │ OpenSearch              │
                       └─────────────────────────┘
```

Supporting infra (all in docker-compose): **Redis** (cache + rate-limit), **MinIO** (S3-compatible object store for raw files), **Pub/Sub emulator**, **OpenSearch**, **Jaeger** (OpenTelemetry UI).

## Quickstart

```bash
git clone https://github.com/SamieZian/eligibility-platform.git
cd eligibility-platform
make up            # all 4 dbs, 4 services, bff, workers, OS, frontend — up
make seed          # synthetic payers, employers, plans
make ingest        # submits tests/golden/834_sample.x12 via BFF upload
make verify        # asserts bitemporal invariants + OS projection
open http://localhost:5173
```

Useful URLs:
- Frontend: http://localhost:5173
- BFF GraphQL playground: http://localhost:4000/graphql
- Jaeger: http://localhost:16686
- MinIO: http://localhost:9001 (user: `minio` / `minio12345`)
- OpenSearch: http://localhost:9200

## Design highlights

| Concern | Pattern used | Where |
|---|---|---|
| Retro-active 834 corrections | **Bitemporal** (valid_time + transaction_time) | `services/atlas/app/domain/enrollment.py` |
| Atomic "write DB + emit event" | **Transactional outbox** | `libs/python-common/.../outbox.py` + `workers/outbox-relay/` |
| Read-model sync | **CQRS** with projector consuming events (CDC-ready) | `workers/projector/` |
| Search at scale | Postgres `eligibility_view` + OpenSearch (fuzzy) | `workers/projector/` + `services/bff/app/search.py` |
| Multi-step workflows | **Saga orchestration** (FSM, compensations) | `services/atlas/app/domain/saga.py` |
| Idempotency under 834 retries | `(trading_partner, ISA13, GS06, ST02, ins_pos)` dedup key | `services/atlas` + `workers/ingestion` |
| Cascading failure prevention | **Circuit breakers + bulkheads + timeouts + retry w/ jitter** | `libs/python-common/.../circuit.py`, `retry.py` |
| Tenant isolation | Postgres RLS + `app.tenant_id` session var | `libs/python-common/.../db.py` |
| PHI | Envelope-encrypted SSN via KMS, PHI-scrubbing logger | `libs/python-common/.../kms.py`, `logging.py` |
| Observability | OpenTelemetry → Jaeger, structured JSON logs, correlation IDs | `libs/python-common/.../tracing.py`, `http_middleware.py` |
| Scalability | Partitioned `enrollments` by tenant hash; cursor pagination | atlas DDL; `services/bff/app/search.py` |

## Fault-tolerance budget (actual values in code)

| Edge | Timeout | Retries | Backoff | Circuit breaker |
|---|---|---|---|---|
| Browser → BFF | 15s / 5s srv | 1 on 503 | — | — |
| BFF → service | 2s | 3 | exp 50/150/450ms + jitter | 5 fails / 10s window |
| Service → Pub/Sub (relay) | 5s | up to 5, exp | 0.1 → 5s | open on > 5% err |
| Pub/Sub → consumer | ack 60s | 7 | exp 10s → 600s | — (DLQ after 7) |
| Projector → OS | 3s | 5, exp | 0.1 → 5s | — (graceful fallback to pg) |
| BFF → OS | 1.5s | 2 | exp | degrade to pg-only search |

## The 834 sample file

`tests/golden/834_sample.x12` is a ~3 KB deterministic file covering:
- **ADD (021)** — subscriber Sharma Priya + spouse Rohit, Swiggy, PLAN-GOLD
- **ADD** — Patel Amit, Zomato, PLAN-SILVER; Kaur Simran, Swiggy, PLAN-GOLD; Nair Arjun, Zomato, PLAN-SILVER
- **TERMINATE (024)** — Patel Amit effective 2026-03-31
- **CORRECTION (030)** — Kaur Simran's effective date moved from 2026-01-01 to 2026-01-15 (creates a bitemporal history row)

After `make ingest`:
- atlas_db holds the bitemporal rows (closed old row + new corrected row for Simran).
- Event feed fires `EnrollmentAdded/Terminated/Changed` to Pub/Sub.
- Projector updates `eligibility_view` and the OpenSearch `eligibility` index.
- `make verify` asserts all of the above.

## Repo layout

```
├── services/                 # 4 domain services (FastAPI) — each with own pg DB
│   ├── atlas/                # enrollment (the core bitemporal aggregate)
│   ├── member/               # members + dependents
│   ├── group/                # payer/employer/subgroup + plan visibility
│   ├── plan/                 # plan catalog (Redis cache-aside)
│   └── bff/                  # GraphQL gateway + REST file upload
├── workers/
│   ├── ingestion/            # 834 / CSV parse → atlas commands
│   ├── projector/            # CQRS read-model projector (pg view + OS)
│   └── outbox-relay/         # outbox → Pub/Sub
├── libs/
│   ├── python-common/        # errors, retry, circuit, outbox, pubsub, logging, tracing, kms
│   └── x12-834/              # streaming 834 parser + golden files
├── frontend/                 # Vite + React + TS + TanStack
├── tests/
│   ├── golden/               # 834_sample.x12, 834_replace.x12, 834_large.x12, generator
│   ├── integration/
│   ├── e2e/                  # verify_after_ingest.py
│   ├── load/                 # k6 scripts
│   └── chaos/                # chaos-kill-projector.sh
├── docs/
│   ├── adr/                  # architecture decision records
│   └── runbooks/             # DLQ-non-empty, projector-lag, saga-stuck
├── pulumi/gcp/               # production IaC for GCP
├── policies/                 # OPA Rego (authz)
├── .github/workflows/        # CI: lint, typecheck, unit, integration, security, build
├── docker-compose.yml        # single-command local stack
└── Makefile                  # up/down/seed/ingest/search/verify/load/chaos/demo
```

## Common commands

```bash
make up                              # bring the stack up
make seed                            # seed payers/employers/plans
make ingest F=tests/golden/834_sample.x12
make search Q=sharma                 # fuzzy search via GraphQL
make verify                          # asserts bitemporal + projection state
make load                            # k6 small run
make chaos-kill-projector            # kill projector, write, restart → catch-up
make test                            # unit + integration
make replay-dlq TOPIC=enrollment.events.dlq
make logs S=atlas                    # tail a single service
make psql D=atlas_db                 # psql into a service's db
make down                            # stop the stack
make clean                           # stop + remove volumes
```

## Extras shipped

- **Saved views** (frontend localStorage) • **column config + density** • **dark mode**.
- **Replay** mutation (`replayFile(fileId)`) for reprocessing a file.
- **Correlation IDs** end-to-end — bottom-right footer in UI shows the last one.
- **Idempotency keys** on mutating endpoints (shared helper).
- **Typed error envelope** (`problem+json`-style) across REST & GraphQL.
- **Hexagonal** layout in every service (`domain` / `application` / `infra` / `interfaces`).

## What's scaffolded but documented-only

| Area | Status |
|---|---|
| Debezium CDC wiring | container defined; using event-based projection primarily — CDC is additive |
| Pulumi GCP IaC | scaffolded under `pulumi/gcp` (not applied) |
| OPA Rego authz | Rego stubs under `policies/` (BFF hooks not yet wired) |
| Temporal.io for sagas | atlas has a hand-rolled FSM; Temporal is the scale path |
| Full chaos suite | `make chaos-kill-projector` works; broader Litmus experiments documented |
| k6 load | `tests/load/search.k6.js` scaffolded |

## Runbooks

See `docs/runbooks/`:
- `dlq-nonempty.md` — how to triage + replay
- `projector-lag.md` — reconciliation procedure
- `saga-stuck.md` — compensation + manual recovery

## ADRs

See `docs/adr/` — key decisions: bitemporal vs event-sourcing, outbox vs CDC as primary, pg+OS read model, hexagonal, saga-orchestration-not-choreography.

## License

MIT.
