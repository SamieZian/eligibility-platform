# ADR-0001: Bitemporal model for enrollments, not full event sourcing

**Status:** accepted. **Date:** 2026-04-14.

## Context

Retroactive 834 corrections (maintenance type `030`) and full-file replacements demand that we never destroy prior beliefs. Claims and audit teams need "as-of" queries like *"what did we believe the coverage was on 2026-03-10?"* Both CQRS+ES and bitemporal modeling answer these questions.

## Decision

Use a **bitemporal table** (`valid_from`/`valid_to` + `txn_from`/`txn_to`) on the `enrollments` aggregate. Integration events are still emitted (via outbox) but are **not** the source of truth.

## Consequences

- Much simpler queries than ES — the timeline is a single SELECT.
- Corrections are two-row operations (close + open), always explicit.
- No event-store tooling needed (snapshots, replays, upcasters).
- Trade-off: operational corrections to the DB itself are harder than in an event log. Mitigation: the outbox table + audit log give us a ledger for downstream systems.

## Alternatives considered

1. Full event sourcing — rejected: high incidental complexity, the team has no EventStore experience, and query patterns are point-in-time + range, not replay-based.
2. History table (plain audit trail) — rejected: no valid-vs-transaction-time separation, making retro corrections lossy.
