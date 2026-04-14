# Runbook: Saga stuck

## Trigger

`sagas.status = 'RUNNING'` for > 10 minutes.

## Triage

```sql
SELECT id, kind, state, updated_at FROM sagas WHERE status='RUNNING' AND updated_at < now() - interval '10 minutes';
```

The `state` JSON shows the current step and retry count.

## Resolution

- **Transient downstream issue**: let retry continue; often resolves on its own.
- **Permanent failure**: invoke compensation:
  ```bash
  docker compose exec atlas python -m app.cli compensate --saga-id <id>
  ```
  Atlas runs each completed step's `compensate` in reverse, then sets `status='COMPENSATED'`.
- **Data bug**: fix the underlying row, then mark `status='COMPLETED'` manually after verifying.

## Prevention

- Add idempotent step implementations so retries don't double-write.
- Set sensible per-step deadlines; the orchestrator times out and compensates.
