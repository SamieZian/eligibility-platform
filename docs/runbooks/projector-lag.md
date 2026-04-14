# Runbook: Projector lag

## Trigger

SLO alert: `CDC/event → eligibility_view freshness` p95 > 60s.

## Triage

1. `make logs S=projector | tail -200` — any errors, OS timeouts, pg deadlocks?
2. Check Pub/Sub subscription backlog via emulator UI or prod console.
3. Check OpenSearch health: `curl localhost:9200/_cluster/health`.

## Resolution

- If OpenSearch is down: projector continues upserting pg view (graceful degradation); reconciliation fills OS once it's back.
- If subscription backlog is climbing and OS/pg are healthy: bump projector replica count.
- If projector is crashing: check the latest deploy, roll back if needed.

## Reconciliation

Nightly reconciliation job compares `(tenant_id, employer_id)` checksums. Drift > 0.01% rebuilds the affected tenants from CDC history.
