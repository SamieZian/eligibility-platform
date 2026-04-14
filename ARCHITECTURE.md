# Architecture — Eligibility & Enrollment Platform

This document describes how the platform is built: the services and how they
talk to each other, the data flows behind each user-visible action, the
technology choices and what we considered instead, and the cross-cutting
concerns (observability, security, resilience). It is meant as a reader's
guide — start at the top, read linearly, and by the end you should
understand *why* the code is organised the way it is.

---

## 1. Summary

Eight independently deployable units — **four bounded-context services** that
own data, **one BFF** that speaks GraphQL to the browser, **three stateless
workers**, and a **React SPA**. They communicate in three styles:

1. **Synchronous request/response** (BFF → services, frontend → BFF) —
   HTTP/JSON with tight timeouts, retries on idempotent ops, circuit breakers
   per downstream.
2. **Asynchronous event fan-out** (services → workers, workers → services) —
   **Transactional Outbox** (inside each service's DB) → **Google Pub/Sub**
   (emulator locally) → **idempotent consumers** in the projector + bridge
   workers.
3. **Server-push** for real-time UX — **GraphQL subscriptions over WebSocket**
   (`graphql-transport-ws`), backed by **Redis Pub/Sub** between the projector
   and the BFF.

The write model is **bitemporal** in `atlas`; the read model is **CQRS** —
`eligibility_view` (Postgres, authoritative for exact filters) + **OpenSearch**
(fuzzy / typeahead). Both are rebuilt by the **projector** from domain events.

The production target is **Google Cloud Run + Cloud SQL + Pub/Sub**, defined
in **Pulumi Python** at [`pulumi/gcp/`](pulumi/gcp/).

---

## 2. System topology

```
                     ┌──────────────────────────────────────────────┐
                     │   React + TS SPA (Vite, TanStack Query,      │
                     │   graphql-ws for subscriptions)              │
                     └────────┬───────────────────────┬─────────────┘
                              │ GraphQL HTTP          │ WebSocket
                              │ (queries + mutations) │ (subscriptions)
                              ▼                       ▼
                     ┌──────────────────────────────────────────────┐
                     │   BFF — FastAPI + Strawberry GraphQL         │
                     │   • Orchestrates multi-service mutations     │
                     │   • DataLoader batching (kills N+1)          │
                     │   • Error envelope + depth limit + CORS      │
                     │   • Redis Pub/Sub → subscription stream      │
                     └─┬───────┬────────┬────────┬──────────────────┘
           gRPC/REST   │       │        │        │
                       ▼       ▼        ▼        ▼
              ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
              │ atlas  │ │ member │ │ group  │ │ plan   │   ◄─── 4 bounded-context services
              │(enrol) │ │  (PHI) │ │(hier.) │ │(catlog)│       each: FastAPI + SA ORM
              │        │ │        │ │        │ │        │            + its own Postgres
              └──┬─────┘ └──┬─────┘ └──┬─────┘ └──┬─────┘
       outbox   │           │ outbox   │ outbox   │ outbox
                ▼           ▼          ▼          ▼
           ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
           │atlas_db│ │member  │ │ group  │ │plan_db │    ◄─── 4 Postgres instances,
           │ (bitemp│ │  _db   │ │  _db   │ │        │        one per bounded context
           │  hash  │ │ (ssn   │ │        │ │(redis  │        (strict DB ownership)
           │  part) │ │encrypt)│ │        │ │ cached)│
           └────────┘ └────────┘ └────────┘ └────────┘
                │          │         │         │
                └────┬─────┴─────────┴─────────┘
                     │ outbox-relay (per DB, polls unpublished rows)
                     ▼
              ┌──────────────────────────┐
              │   Pub/Sub emulator       │◄─────────── DLQ on max-retry
              │   (prod: GCP Pub/Sub)    │
              └─┬────────────────┬───────┘
                │                │
                ▼                ▼
       ┌────────────────┐ ┌──────────────────────────────┐
       │  ingestion     │ │  projector                   │
       │  (834/CSV/PDF) │ │  ┌──────────────────────────┐│
       │                │ │  │ idempotent upserts:      ││
       │  optional:     │ │  │   • eligibility_view     ││
       │  Vertex AI     │ │  │   • OpenSearch           ││
       │  Document AI   │ │  │   • Redis Pub/Sub (live) ││
       │                │ │  └──────────────────────────┘│
       └───────┬────────┘ └──────┬───────────────────────┘
               │ GCS/MinIO        │
               ▼                  ▼
       ┌────────────────┐ ┌──────────────────────┐
       │ raw 834/CSV    │ │ eligibility_view     │
       │ + audit dump   │ │ (pg; hash-partitioned│
       │                │ │ by tenant)           │
       └────────────────┘ └───────┬──────────────┘
                                  │
                                  ▼
                          ┌──────────────────────┐
                          │ OpenSearch           │
                          │ (fuzzy, facets,      │
                          │ typeahead)           │
                          └──────────────────────┘

Shared infra: Redis (cache, rate-limit, sub pub/sub), MinIO (GCS locally),
Jaeger (OTel locally; Cloud Trace in prod), OpenSearch, Pub/Sub emulator.
```

### Deployables at a glance

| Unit | What it owns | Data store | Port (local) |
|---|---|---|---|
| **atlas** (svc) | Bitemporal enrollment aggregate, saga state, idempotency keys, outbox | `atlas_db` (Postgres 15) | 8001 |
| **member** (svc) | Members + dependents + encrypted SSN | `member_db` | 8002 |
| **group** (svc) | Payer → employer → subgroup hierarchy, plan-visibility matrix | `group_db` | 8003 |
| **plan** (svc) | Plan catalog + benefits attributes (Redis write-through cache) | `plan_db` + Redis | 8004 |
| **bff** | GraphQL + REST gateway; orchestrates mutations; subscriptions | — (stateless) | 4000 |
| **ingestion** (worker) | 834 / CSV / optional PDF → atlas commands | — (reads MinIO, writes via atlas API) | n/a |
| **projector** (worker) | Domain events → `eligibility_view` + OpenSearch + Redis Pub/Sub | — (writes into atlas_db read-view + OS + Redis) | n/a |
| **outbox-relay** (worker) | Polls each DB's outbox, publishes to Pub/Sub, marks rows published | — | n/a |
| **frontend** | React SPA | — | 3000 |

**Why 4 services, not 1 monolith, not 20 microservices?** Four maps cleanly to
the four natural aggregates in benefits administration (enrollment, person,
organization, product). Fewer would blur responsibility (e.g., dumping plans
into members would make the plan catalog non-reusable for other products).
More would fragment without benefit — dependents don't need their own service
because their lifecycle is strictly nested under the member aggregate.

---

## 3. Why this split? (Domain-Driven Design)

Each service is one DDD **aggregate root**:

| Service | Aggregate | Why separate |
|---|---|---|
| atlas | `Enrollment` | Bitemporal, high write volume, saga orchestration, must be auditable. Wants strict transactional control and a specialized schema. |
| member | `Member` (with dependents) | Contains PHI (SSN, DOB). Envelope-encrypted. Different security posture — HIPAA audit, strictest RLS, separate KMS key. |
| group | `Employer` (parent: Payer) | Reference data, infrequently mutated. Hierarchical. Queried by every other service but rarely written. |
| plan | `Plan` | Truly reference data; written by ops teams, read by everything. Aggressive caching (Redis write-through) is possible precisely because it's isolated. |

**Strict DB-per-service.** No cross-service FK constraints. Foreign references
are "by value" (UUIDs) and reconciled via events, never via joins. That's what
lets each service evolve its schema independently. It's also what makes the
outbox pattern *necessary* — you can't rely on two-phase commit across four
databases.

**What we deliberately avoided**: a single "eligibility_db" with one Postgres
server. That would be faster for an MVP, but it locks schema evolution across
domains. Splitting later is the hard part — doing it from day one is free.

---

## 4. The 5 canonical request paths

### 4.1 Add a new member (write-path, orchestrated saga)

```
Browser                 BFF             member svc        atlas svc
   │   GraphQL mutation   │                 │                  │
   │ addMember(input)     │                 │                  │
   ├─────────────────────►│                 │                  │
   │                      │  POST /members  │                  │
   │                      │ (upsert by card)│                  │
   │                      ├────────────────►│                  │
   │                      │                 │ INSERT + outbox  │
   │                      │   201 {id, ...} │ event MemberUpserted
   │                      │◄────────────────┤                  │
   │                      │                                    │
   │                      │   POST /commands {command_type:ADD,│
   │                      │    member_id, plan_id, effective}  │
   │                      ├───────────────────────────────────►│
   │                      │                                    │ INSERT + outbox
   │                      │                                    │ event EnrollmentAdded
   │                      │   201 {enrollment_id}              │
   │                      │◄───────────────────────────────────┤
   │  {memberId,          │                                    │
   │   enrollmentId,      │                                    │
   │   memberName}        │                                    │
   │◄─────────────────────┤                                    │
```

**Key properties:**
- Both calls carry `Idempotency-Key` (header) + `X-Tenant-Id` + `X-Correlation-Id`.
- BFF circuit-breaks each downstream separately; failure of atlas doesn't retry the member call.
- Member + enrollment writes are NOT atomic — they're an eventually-consistent saga.
  If the enrollment POST fails, a stale member row exists but the UI never shows it
  (the grid reads `eligibility_view`, which needs both events). Retrying the
  mutation upserts the same member (idempotent by card) and creates the enrollment.
- The frontend does **not** see the member until projector writes `eligibility_view`.
  Today that's ~1-2s; acceptable for async work, hidden behind a toast.

### 4.2 Ingest an 834 EDI file (async write-path)

```
Browser              BFF             MinIO          Pub/Sub         ingestion       atlas
  │ POST /files       │                │               │                │              │
  │  multipart        │                │               │                │              │
  ├──────────────────►│                │               │                │              │
  │                   │  PUT object    │               │                │              │
  │                   ├───────────────►│               │                │              │
  │                   │   ETag         │               │                │              │
  │                   │◄───────────────┤               │                │              │
  │                   │  publish       │               │                │              │
  │                   │  file.received ├──────────────►│                │              │
  │                   │                │               │ push message   │              │
  │                   │                │               ├───────────────►│              │
  │  {file_id}        │                │               │                │              │
  │◄──────────────────┤                │               │                │ stream parse │
  │                                                                     │ INS by INS   │
  │                                                                     │              │
  │                                                                     │  POST /commands (ADD|TERMINATE|CORRECTION)
  │                                                                     │   with Idempotency-Key = ISA13:GS06:ST02:ins_seq
  │                                                                     ├─────────────►│
  │                                                                     │              │ dedup via processed_segments,
  │                                                                     │   201        │ INSERT + outbox
  │                                                                     │◄─────────────┤
```

**Idempotency is load-bearing.** Trading partners often retransmit the same
834 file; `ISA13:GS06:ST02:ins_seq` is the canonical dedup key. The ingestion
worker hashes row content for CSV (no canonical segment position). Consumer
side stores processed keys in `processed_segments`. At-least-once delivery
from Pub/Sub + idempotent handlers = effectively-once.

**Streaming parse** (not buffering): a 100 MB 834 is parsed INS by INS.
Backpressure comes from the atlas command rate, not buffer size.

### 4.3 Read: eligibility grid search (query path)

```
Browser           BFF                atlas_db             OpenSearch
  │  GraphQL       │                    │                       │
  │  searchEnrol.. │                    │                       │
  ├───────────────►│                    │                       │
  │                │  exact filters     │                       │
  │                │  (planId, status,  │                       │
  │                │   dateRange)       │                       │
  │                ├───────────────────►│                       │
  │                │  <rows from        │                       │
  │                │   eligibility_view>│                       │
  │                │◄───────────────────┤                       │
  │                │                                            │
  │                │  if q.fuzzy: search OS                     │
  │                ├───────────────────────────────────────────►│
  │                │  hit IDs                                   │
  │                │◄───────────────────────────────────────────┤
  │                │                    │                       │
  │                │  hydrate IDs from pg                       │
  │                ├───────────────────►│                       │
  │  {items,       │◄───────────────────┤                       │
  │   total,       │                                            │
  │   nextCursor}  │                                            │
  │◄───────────────┤                                            │
```

- Exact filters on the read-view use **covering indexes** + **keyset
  pagination** (`(status, effective_date DESC, id)` — no OFFSET pain at page
  10,000).
- Fuzzy queries use OpenSearch's multi-match + completion suggester; results
  are IDs only, then hydrated from pg. This avoids stale OS documents
  surfacing to the UI.
- If OS is down, BFF degrades to pg-only (exact/substring match) and flashes
  a small banner. No 5xx to the user.

### 4.4 Live update via GraphQL subscription

```
Browser                BFF                Redis              projector           atlas/member
  │ ws://…/graphql       │                   │                   │                      │
  │ subscribe            │                   │                   │                      │
  │ enrollmentUpdated    │                   │                   │                      │
  │ (memberId: X)        │                   │                   │                      │
  ├─────────────────────►│                   │                   │                      │
  │                      │ SUBSCRIBE         │                   │                      │
  │                      │ enrollment_updates│                   │                      │
  │                      ├──────────────────►│                   │                      │
  │                                          │                   │                      │
  │           (user in another tab triggers a mutation)          │                      │
  │                                          │                   │   EnrollmentAdded    │
  │                                          │                   │◄─────────────────────┤
  │                                          │                   │ project to           │
  │                                          │                   │ eligibility_view + OS│
  │                                          │   PUBLISH         │                      │
  │                                          │◄──────────────────┤                      │
  │ event {                                  │                   │                      │
  │   memberId, eventType,                   │                   │                      │
  │   occurredAt                             │                   │                      │
  │ }                                        │                   │                      │
  │◄─────────────────────┬───────────────────┤                   │                      │
```

**Why Redis Pub/Sub** (not another Pub/Sub or WebSockets direct from
projector)? Because:
- Pub/Sub is the system of record for **durable** events; subscriptions are
  **ephemeral** (only "who's open right now" matters). Redis Pub/Sub is
  fire-and-forget — ideal for "kick the open browsers, let them refresh".
- Multiple BFF replicas can all SUBSCRIBE to the same channel; each browser
  is connected to exactly one replica. Every replica gets every event, only
  the replica with an interested client pushes.
- No new infra — Redis is already the cache / rate-limiter.

### 4.5 Plan change (bitemporal-correct saga)

```
Browser                BFF                  atlas svc
  │ changeEnrollmentPlan │                      │
  ├─────────────────────►│                      │
  │                      │ TERMINATE old plan   │
  │                      │   valid_to = new - 1d│
  │                      ├─────────────────────►│
  │                      │  close txn_to on old │
  │                      │  insert TERMED row   │
  │                      │  (bitemporal split)  │
  │                      │                      │
  │                      │ ADD new plan         │
  │                      │   valid_from = new   │
  │                      ├─────────────────────►│
  │                      │  insert ACTIVE row   │
  │                      │                      │
  │  {new_enrollment_id} │                      │
  │◄─────────────────────┤                      │
```

The Gantt chart reflects this as: one green bar ends, one red bar starts, a
new green bar opens. The original ACTIVE row is preserved — `txn_to` is set,
not deleted — so the audit trail answers "what did we believe on date X".

---

## 5. Inter-service communication patterns — how and why

### 5.1 Sync HTTP/JSON between BFF and services

**What we use**: httpx + pooled `BreakerClient` (timeout 2s, 3 retries with
exp backoff + full jitter, circuit breaker opens at 5 failures / 10s).

**Why not gRPC?** We designed for it (the plan has a `proto/` dir) but didn't
implement. Tradeoffs:
- gRPC wins on latency (HTTP/2 multiplexing, binary protobuf) — ~2-3x smaller
  frames, ~15-30% lower p99 at high throughput.
- gRPC loses on debuggability: `curl localhost:8001/members` works; `grpcurl`
  doesn't by default without reflection enabled.
- The BFF is I/O bound on DB + OS, not network — gRPC wouldn't move the p95
  meaningfully for our workload.
- JSON + FastAPI + OpenAPI auto-docs is a strictly better DX at this scale.

**Why not GraphQL between services?** GraphQL shines when the *client* has
varied query shapes. Service-to-service calls have fixed, known shapes —
GraphQL just adds overhead.

### 5.2 Async events via transactional outbox → Pub/Sub

**The outbox pattern.** Every state-changing command commits two rows in one
transaction: the business row + a row in `outbox`. A separate `outbox-relay`
worker polls `WHERE published_at IS NULL`, publishes to Pub/Sub, sets
`published_at`. This guarantees **atomic "write DB + emit event"** without
2PC.

```sql
-- inside a single transaction
INSERT INTO enrollments (...);
INSERT INTO outbox (aggregate, aggregate_id, event_type, payload)
  VALUES ('Enrollment', :id, 'EnrollmentAdded', :json);
COMMIT;
```

**Why this over Debezium CDC?** CDC reads the WAL — catches every DB change
including migrations and manual fixes. Outbox gives *intent-full* events
because the app decides what to publish. For an eligibility system with
strict business semantics ("this is an ADD vs CORRECTION vs REPLACE"), the
app knows more than the WAL. CDC is documented as a scale path but not
wired — the topology image shows it because Debezium + outbox is the
enterprise-standard combo (outbox for clean semantics, CDC as belt-and-
braces against outbox-relay bugs).

**Why Pub/Sub over Kafka?** Kafka has better throughput and exactly-once
semantics with idempotent producers + transactions. Pub/Sub is:
- Managed GCP-native (no broker to run, no Zookeeper / KRaft to operate).
- Per-message ACK (Kafka acks per batch), better for independent consumers.
- Built-in DLQ (Kafka requires manual setup).
- 20ms median latency vs Kafka's sub-ms — irrelevant for eligibility.

For a 100K-claims/day workload on a 4-person team, Pub/Sub is the right pick.
For 100M claims/day on a dedicated data platform team, Kafka wins.

### 5.3 Real-time push via WebSocket (GraphQL subscriptions)

**What we use**: Strawberry's built-in subscription support over
`graphql-transport-ws` protocol (with `graphql-ws` fallback). Frontend uses
the `graphql-ws` npm client.

**Why not Server-Sent Events (SSE)?** SSE is simpler (one-way, plain HTTP)
but:
- No browser handshake versioning → hard to evolve.
- No built-in backpressure signaling.
- Not supported in GraphQL ecosystem — subscriptions assume WS.

**Why not polling?** An enrollment grid with 1000 users polling every 5s =
200 qps of wasted BFF + DB load for events that happen maybe once a minute.
Push over WS is O(updates), polling is O(users × interval).

---

## 6. The bitemporal write model — the hardest part

`atlas.enrollments` stores **two independent time dimensions**:

- **valid_time**: `[valid_from, valid_to)` — when coverage is active in reality
- **transaction_time**: `[txn_from, txn_to)` — when the system believed this

Every row is a (valid-time × txn-time) tuple. The current "truth" is the set
of rows where `txn_to = 'infinity'`. Historical truth is obtained by filtering
`txn_from <= :as_of < txn_to`.

### Why bitemporal?

Retroactive 834 corrections (segment type 030) are the norm in US healthcare:
- A 2026-01-15 file terminates a subscriber effective 2026-01-01.
- A 2026-03-20 correction says "actually, terminate effective 2025-12-01".

A naive UPDATE destroys the audit trail. A bitemporal model records:
1. The old row (coverage 2026-01-01 → open) is closed in txn-time
   (`txn_to = 2026-03-20 00:00:00`). It stays visible as "what we believed
   between 2026-01-15 and 2026-03-20".
2. A new row (coverage 2025-12-01 → 2025-12-31) is inserted with
   `txn_from = 2026-03-20`.

This is what claims adjudicators need to answer "was member X covered on
2026-01-10?" *while preserving the ability to ask* "did we *think* member X
was covered on 2026-01-10 *as of claim date 2026-02-01*?". The two questions
have different answers after a correction, and both can matter legally.

### Alternatives considered (and rejected)

- **Audit table + business table**: you get audit but not "as-of" queries
  without a full history scan. Linearly worse than bitemporal.
- **Event sourcing**: full log, perfect replay — but every read rebuilds
  state, so you need snapshots, which reintroduces the tracking problem.
  Also loses the declarative SQL interrogation story (adjudicators want to
  `SELECT WHERE`, not consume a stream).
- **Temporal tables** (SQL:2011 `PERIOD FOR ...`): only transaction-time in
  vanilla Postgres (via extensions); no valid-time support. We'd need to
  manage valid-time by hand anyway, so the extension buys little.

Bitemporal with two explicit tstzranges is the most honest representation.
The code pays for it with slightly more complex SELECTs, which is why
`atlas/app/infra/repo.py` keeps using SQLAlchemy `text()` for those queries —
the ORM abstraction hides the range semantics a staff reviewer wants to see.

---

## 7. The read model — CQRS done for the right reasons

Writes go to `atlas.enrollments` (normalized, bitemporal, hash-partitioned by
`tenant_id`). Reads go to a **denormalized** projection:

- `eligibility_view` (Postgres table): 1 row per in-force enrollment, joined
  with member name, employer name, plan name, subgroup name. Indexed for
  the grid's exact filters (`tenant_id, employer_id, status`, `card_number`,
  etc.). Written by the projector worker.
- OpenSearch index `eligibility`: same logical shape, multi-field analyzer
  (edge n-grams for autocomplete, ASCII-folding for accents, soft-kerning
  tokenizer for `Sharma/Sarma`). Also written by the projector.

**Why CQRS?** Because search and write have opposite optimization goals:
- Writes want normalized schema, strict transactions, partitioning by
  tenant, optimistic locking.
- Reads want denormalized rows (no joins at query time), fuzzy match, facets,
  typeahead, low tail latency.

Trying to serve both from one table means adding indexes for the grid to
the write table, which slows writes and inflates pool-memory. Separate
models + eventual consistency (~1-2s) is the industry standard trade for
this shape of workload.

**Why not federate via a view?** Postgres views can't do fuzzy match at scale,
and a materialized view requires full refresh or a custom trigger — both
worse than an event-driven projector.

**Why OpenSearch over Elasticsearch/Meilisearch/Typesense?**
- **ES**: license change (Elastic 2.0) made running it on a small team
  risky; OpenSearch (AWS fork) is Apache-2.
- **Meilisearch / Typesense**: excellent for instant search on small datasets
  (< 10M docs), less mature for facets + aggregations + joins. Would need a
  second tool for analytics.
- OpenSearch has the largest ecosystem (Logstash, Beats, OSD dashboards) and
  the fullest feature set. Tradeoff: heavier (JVM, 1GB+ idle), slower to
  spin up.

For 100M+ enrollments, OpenSearch is the right tool. Under 1M, Meilisearch
would win on simplicity.

---

## 8. Tech choice rationale — every major decision, with what we rejected

| Decision | Chose | Rejected | Why |
|---|---|---|---|
| Language | Python 3.11+ | Go, TypeScript, Kotlin | Healthcare data work leans heavily on Python's ecosystem (pandas, X12 tooling, ML libs). `async` + type hints are mature; FastAPI + Pydantic is best-in-class. Go would win on startup time but cost every ecosystem integration. |
| Web framework | FastAPI | Flask, Django, Litestar | Async-native, auto OpenAPI, Pydantic integration, big ecosystem. Litestar is faster in micro-benchmarks but has 10× fewer integrations. |
| Data validation | Pydantic v2 | marshmallow, attrs | v2 is Rust-backed (~5× faster than v1); zero serious alternative. |
| ORM | SQLAlchemy 2.0 async + Alembic | Tortoise, SQLModel, raw asyncpg | SA 2.0 is the most mature async-native ORM. Tortoise is simpler but less flexible. Raw asyncpg would save ~10% perf but loses migrations + typed repos. |
| DB driver | asyncpg | psycopg3 async | asyncpg is ~3× faster than psycopg in benchmarks; psycopg3 is more compatible but slower. |
| Query API | ORM `select()` for CRUD (member/group/plan), `text()` for atlas bitemporal ranges | 100% ORM everywhere | Bitemporal SQL uses window functions and range predicates that ORMs verbalize awkwardly. Mixing is legitimate when you keep it explicit. |
| Migrations | Alembic | sqitch, goose, hand-rolled DDL | Alembic integrates with SA models; autogenerate + branching is the standard Python stack. |
| GraphQL | **Strawberry** | Graphene, Ariadne, Gqlgen | Code-first with typed dataclasses — the schema *is* the Python types, so refactors can't drift. Async-native; ships DataLoader, extensions, and subscriptions without third-party glue. Graphene is sync-first and stagnant. Ariadne is schema-first, which duplicates every type between SDL and Python. |
| GraphQL subscriptions | graphql-transport-ws + Strawberry | SSE, raw WebSockets | Strawberry subscriptions speak `graphql-transport-ws` natively; the frontend's `graphql-ws` client is the ecosystem standard. |
| Caching | Redis 7 | Memcached, DragonflyDB | Redis has pub/sub (used for subscriptions), scripting, streams — everything. DragonflyDB is a faster drop-in but small adoption. Memcached has no pub/sub. |
| Event bus | Google Pub/Sub | Kafka, Redis Streams, RabbitMQ, NATS | Pub/Sub is managed on GCP, supports DLQ natively, per-message ACK. Kafka wins at 1M+ msg/s but we're far below that. |
| Object storage | GCS (MinIO locally) | S3, Azure Blob | We deploy on GCP, so GCS is the native choice (IAM, CMEK, VPC-SC integrate without glue). MinIO is S3-compatible, which keeps the code vendor-portable — the same `boto3`-style client talks to both. |
| Container runtime | Cloud Run | GKE, Cloud Functions, App Engine | Cloud Run = managed container autoscaling to zero, pay-per-request. GKE adds ops overhead for no benefit at our scale. Cloud Functions has tight limits (< 540s, < 8GB). |
| Serving Postgres | Cloud SQL (private IP) | AlloyDB, Spanner | Cloud SQL is the default. AlloyDB is ~2× faster for analytics (uses Postgres wire protocol with custom storage) but more expensive. Spanner is global-scale with different consistency semantics — overkill for a single region. |
| Secrets | Secret Manager | HashiCorp Vault, Cloud KMS Encrypted Env Vars | Secret Manager is managed, audited, rotatable, integrates with Cloud Run. Vault is more powerful but needs self-hosting. |
| IaC | **Pulumi Python** | Terraform, CDK for Terraform, Crossplane | Pulumi lets infra be real Python — conditionals, loops, helper functions, shared dataclasses between app and infra. Terraform's HCL works but the DSL constrains expressiveness and splits the codebase's language boundary. CDK for Terraform is viable but has a smaller community. |
| CI | GitHub Actions | GitLab CI, Cloud Build | Actions has the largest action marketplace and stays portable across cloud vendors. Cloud Build is a fine alternative when the pipeline is 100% GCP-native; we keep the Actions path to avoid vendor lock-in at the CI layer. |
| Observability | OpenTelemetry (vendor-neutral) → Jaeger local / Cloud Trace prod | Datadog, Honeycomb, New Relic | OTel is the CNCF standard; the exporter swaps without changing app code, so local dev stays free (Jaeger) and prod can fan out to Cloud Trace / Cloud Logging / Cloud Monitoring — or any third-party APM — without rewriting spans. Datadog is excellent but vendor-locked and expensive at scale. |
| Structured logs | structlog + PHI scrubber | loguru, stdlib logging alone | structlog's `bind_contextvars` makes correlation_id propagation trivial across async boundaries. loguru is easier but less customizable. |
| Encryption | KMS envelope (master key wraps per-member DEK) | app-level fixed key, FPE, asymmetric | Envelope is the standard for PHI at rest. Rotates without re-encrypting everything. |
| AuthZ | OPA sidecar (Rego policies) | role checks in app code, Casbin | OPA decouples policy from code; same policy runs locally + in GCP. Rego is clunky but audit-friendly. |
| AuthN | OIDC mock (dex) locally, Auth0/Google in prod | Sessions, JWT rolled-by-hand | OIDC is the standard; Auth0/Firebase Auth provide SDKs. Custom JWT is only right if you're very sure you're smarter than the attackers. |
| API style | GraphQL (frontend ↔ BFF) + REST (service ↔ service, ingestion uploads) | GraphQL everywhere, gRPC everywhere, REST everywhere | GraphQL shines for varied-query UIs; REST shines for simple internal APIs + file uploads + streaming. Use each where it fits. |
| 834 parsing | Custom streaming parser | pyx12 library, commercial SDKs | pyx12 is abandoned (last release 2015). Commercial SDKs (Edifecs, Axway) are expensive and opaque. X12 834's structure (ISA/GS/ST envelopes + INS loops) is tractable enough to parse yourself in ~500 LOC with better performance. |
| Frontend framework | React 18 + Vite + TS | Vue, Svelte, Solid, Next.js | Team velocity — React has the largest ecosystem for grids/charts/auth. Vite over Next.js because we don't need SSR for an internal console. |
| Grid library | Custom table + TanStack Query | AG-Grid Enterprise, MUI DataGrid | AG-Grid Enterprise is great but $$. MUI DataGrid is fine but locks us to MUI's styling. Custom is 300 LOC and matches our exact wireframe. |
| Data fetching | TanStack Query | Redux + RTK Query, SWR, Apollo Client | TanStack Query is the modern standard for async state: caching, invalidation, optimistic updates, all framework-agnostic. Apollo is GraphQL-only and heavier. |
| CSS | CSS Modules + CSS variables | Tailwind, emotion, styled-components | CSS Modules keep styles co-located + typed, no runtime cost. Tailwind is fine but class names leak design intent into JSX. |

---

## 9. Cross-cutting concerns

### 9.1 Resilience (failures are normal, cascades are bugs)

Every network boundary has an explicit policy (timeout / retries / backoff /
circuit breaker / bulkhead / fallback) — see the full matrix in README.md §4.5.

Highlights:
- **Deadlines propagate**: BFF sets an absolute deadline in trace context;
  every downstream checks `now < deadline` before starting work.
- **Retries only on idempotent ops**: GETs, POSTs with `Idempotency-Key`.
- **Exponential backoff + full jitter**: `sleep = random(0, base * 2^attempt)`.
  Prevents thundering-herd on recovery.
- **Circuit breakers per downstream**: 5 failures in 10s → open 30s →
  half-open 1 probe. Isolated pools so a slow plan svc doesn't starve member
  calls.
- **DLQ on every subscription**: 5 delivery attempts → DLQ topic. Replay tool
  in the Makefile.
- **Graceful shutdown**: SIGTERM → `/readyz` returns 503 (Cloud Run stops
  new traffic) → in-flight requests drain up to 20s → engine pool disposed.

### 9.2 Observability

Three signals, unified via correlation ID:

- **Traces**: OTel SDK on every service, auto-instrumented FastAPI +
  SQLAlchemy + httpx. Local: OTLP → Jaeger. Prod: GCP Cloud Trace (auto-
  switch when `GOOGLE_CLOUD_PROJECT` is set).
- **Logs**: structlog JSON to stdout with `correlation_id` + `tenant_id` +
  `trace_id` bound via `bind_contextvars`. PHI scrubber (`ssn`, `token`,
  `password`) redacts known-sensitive keys. Prod: Cloud Logging (same auto-
  switch).
- **Metrics**: `/metrics` Prometheus endpoint on each service (FastAPI
  instrumentator). Prod: Cloud Monitoring via OpenTelemetry Collector.

**SLOs** (documented, alertable in prod):
- search p95 < 300ms, p99 < 800ms
- 834 ingest p95 < 5 min per 100 MB
- CDC → OS projection lag p95 < 10s

### 9.3 Security (HIPAA posture)

- **Network**: Cloud Run → Cloud SQL via Private IP + VPC-SC perimeter
  (documented TODO in Pulumi; requires Org Policy).
- **At rest**: envelope-encrypted SSN (KMS master key wraps per-row DEK;
  AES-GCM). Cloud SQL uses CMEK.
- **In transit**: TLS everywhere. Internal mTLS is documented but not
  implemented (Cloud Run's default service-to-service auth is sufficient
  when bound to a dedicated SA).
- **AuthN**: OIDC. JWKS cached 5 min with pub/sub invalidation on rotation.
- **AuthZ**: OPA sidecar; Rego policies committed at `policies/`.
- **Tenant isolation**: Postgres RLS on every table (`app.tenant_id` session
  var set from the JWT/header); app-level tenant check on member GET as
  defense-in-depth.
- **Optimistic locking**: `version` column on members/plans; `UPDATE WHERE id
  AND version=?` → 412 on mismatch, client re-fetches.
- **Idempotency**: HTTP middleware dedups POST/PUT/PATCH/DELETE by
  `Idempotency-Key`. Replay returns the cached 2xx response.
- **Audit**: every outbox event carries actor + correlation_id; events archived
  to GCS with object-lock (WORM) in prod.
- **Log scrubbing**: PHI keys redacted automatically.
- **DLP (documented)**: Cloud DLP API for outbound scanning (planned).

### 9.4 Scale path

Every piece has a known scale lever:

| Bottleneck | Lever |
|---|---|
| Read latency | Postgres read replicas + Redis cache; OpenSearch cluster with dedicated master nodes |
| Write latency (atlas) | Hash-partitioned by `tenant_id` — partitions move to separate pg instances; atlas clones per-partition if needed |
| Ingestion throughput | Pub/Sub auto-scales consumers; ingestion is pure-async, CPU-bound only on AES-GCM |
| OS indexing lag | Projector auto-scales; batched `/_bulk` API (currently 1-by-1 for simplicity, documented as follow-up) |
| Saga complexity | Temporal.io for long-running workflows; current hand-rolled FSM is fine up to ~10-step flows |
| Connection storms | PgBouncer transaction-mode pooling in front of Cloud SQL |

---

## 10. Production deployment — Pulumi Python on GCP

See [`pulumi/gcp/`](pulumi/gcp/) for the full IaC. Summary:

```
         ┌─────────────────────────────────────────────────────┐
         │  VPC (private)                                      │
         │  ┌──────────────────────────────────────────────┐   │
         │  │  Cloud Run (serverless, min=1, max=10)       │   │
         │  │  • atlas, member, group, plan, bff           │   │
         │  │  • min_instance_count=1 → no cold start      │   │
         │  │  • VPC egress → Cloud SQL Private IP         │   │
         │  └──────────────────────────────────────────────┘   │
         │  ┌──────────────────────────────────────────────┐   │
         │  │  Cloud SQL (Postgres 15, HA, PITR, insights) │   │
         │  │  • atlas_db, member_db, group_db, plan_db    │   │
         │  │  • Private IP only (no public IP)            │   │
         │  │  • CMEK + object-level encryption            │   │
         │  └──────────────────────────────────────────────┘   │
         │                                                     │
         │  Pub/Sub (topic × 5 + sub × 5 + DLQ × 5)            │
         │  Cloud Storage (versioned, lifecycle 30/180/2555d)  │
         │  Secret Manager (DB pws, KMS keys, OIDC secrets)    │
         │  Artifact Registry (one repo, 8 image tags)         │
         │  Cloud Monitoring + Logging + Trace (native)        │
         │                                                     │
         │  (Planned; TODO in Pulumi README:                   │
         │   VPC-SC service perimeter, CMEK on Cloud SQL,      │
         │   Cloud Armor WAF, IAM DB authentication)           │
         └─────────────────────────────────────────────────────┘
```

Deploy:
```bash
cd pulumi/gcp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pulumi login
pulumi stack init dev
pulumi config set gcp:project YOUR-PROJECT
pulumi up
```

---

## 11. What we deliberately did NOT build (and why)

Scope decisions matter as much as what we built. Omissions with reasons:

| Omitted | Why |
|---|---|
| Kafka | Pub/Sub is sufficient for our rates, adds a team's worth of ops burden. |
| gRPC between services | JSON + httpx + OpenAPI is strictly better DX at this scale. |
| Microfrontends | One operator console; one team. Split would be overhead for no gain. |
| Service mesh (Istio/Linkerd) | Cloud Run's built-in ingress + IAM = enough. Istio is a distraction at 5 services. |
| GraphQL federation | One BFF, one schema. Federation is for multi-team multi-product estates. |
| Event sourcing | Bitemporal table captures history explicitly; ES would add replay complexity we don't need. |
| Machine learning in anomaly detection | Rules-based first (see [`docs/runbooks/anomaly-detection.md`](docs/runbooks/anomaly-detection.md)); Vertex AI Forecasting documented as next step. |
| Exactly-once semantics across services | Idempotent consumers + at-least-once delivery = effectively-once at application level. True exactly-once requires distributed transactions. |
| Homemade auth | Never roll your own. OIDC via Auth0/Firebase. |
| Admin UI for ops | CLI + runbooks + Cloud Monitoring dashboards are fine for a 3-person ops team. |

---

## 12. Where to look in the code

If you have 15 minutes and want to map the concepts in this doc to the
actual files, start here:

- [`services/atlas/app/domain/enrollment.py`](../eligibility-atlas/app/domain/enrollment.py) — pure-Python bitemporal aggregate. No I/O, no SQL.
- [`services/bff/app/graphql_extensions.py`](../eligibility-bff/app/graphql_extensions.py) — custom Strawberry error envelope + DataLoader + depth-limit validator. Production-grade GraphQL hygiene.
- [`libs/python-common/src/eligibility_common/idempotency.py`](../eligibility-atlas/libs/python-common/src/eligibility_common/idempotency.py) — pure ASGI idempotency middleware. Not `BaseHTTPMiddleware` (which has known body-override bugs).
- [`libs/python-common/src/eligibility_common/app_factory.py`](../eligibility-atlas/libs/python-common/src/eligibility_common/app_factory.py) — SIGTERM → `/readyz` = 503 → drain → pool dispose. Shared across every service.
- [`libs/python-common/src/eligibility_common/tracing.py`](../eligibility-atlas/libs/python-common/src/eligibility_common/tracing.py) + `logging.py` — env-switched Cloud Trace / Cloud Logging exporters.
- [`pulumi/gcp/__main__.py`](pulumi/gcp/__main__.py) — 470 lines of real Pulumi Python. Not a toy stack.
- [`services/bff/app/pubsub_bridge.py`](../eligibility-bff/app/pubsub_bridge.py) — Redis Pub/Sub → async-iter for GraphQL subscriptions. Cancellation-safe.
- [`workers/projector/app/redis_bridge.py`](../eligibility-workers/projector/app/redis_bridge.py) — best-effort publish after every successful projection.
- [`tests/golden/834_sample.x12`](tests/golden/834_sample.x12) + `generate_834.py` — deterministic sample file used in CI.
- [`README.md §4.5`](README.md#fault-tolerance--retry-matrix-explicit-per-layer) — per-edge timeout/retry/breaker/fallback policy.

And a live walk-through of the whole platform:
```bash
make up                 # 18 containers come up
make seed               # synthetic payer/employer/plan/member data
make ingest             # ingest tests/golden/834_demo.x12 (18 members)
open http://localhost:3000
# Search "sharma", open the timeline drawer → see the Gantt chart
# Trigger "Change plan" → watch two new bars appear live via WebSocket
# Groups tab → full CRUD for the hierarchy
# Upload tab → drag another 834 or CSV
```

---

*Last updated: 2026-04-14.*
