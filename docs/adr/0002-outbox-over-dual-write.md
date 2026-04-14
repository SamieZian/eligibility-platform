# ADR-0002: Transactional outbox for event publication

**Status:** accepted. **Date:** 2026-04-14.

## Context

We need "write DB + emit event" atomicity without 2PC. Dual-writes (DB then Pub/Sub) lose events on crash between the two writes.

## Decision

Every service has an `outbox` table. Domain writes and outbox inserts happen in the **same local transaction**. A separate `outbox-relay` worker drains rows to Pub/Sub with retry+backoff and marks rows `published_at` on success.

## Consequences

- Guaranteed *at-least-once* delivery of integration events.
- Consumers must be idempotent (they already are, via `processed_segments` and ON CONFLICT).
- Outbox grows unboundedly unless reaped — a future cron trims rows older than N days after confirming downstream reception.

## Alternative considered

Debezium CDC on the business tables directly. Kept as a future upgrade for richer event shapes; the outbox is simpler, decoupled from table schema, and testable without Debezium infrastructure.
