# Runbook: DLQ non-empty

## Trigger

Alert: any `*.dlq` topic has depth > 0 for more than 5 minutes.

## Triage

1. Which topic? Common culprits:
   - `file.received.dlq` — ingestion parse errors.
   - `enrollment.events.dlq` — projector couldn't apply.
2. Pull sample payloads:
   ```bash
   python scripts/replay_dlq.py --topic <topic>  # first peek a single message via a debug mode; see tool
   ```
3. Inspect the message attributes for `tenant_id` and `correlation_id`. Search logs:
   ```bash
   make logs S=ingestion | grep "<correlation_id>"
   ```
4. Pattern-match: is one tenant failing, one file, one segment type?

## Resolution

- **Data fix possible** (e.g., missing employer record): add the missing row, then `make replay-dlq TOPIC=<topic>` to re-drive.
- **Bug**: patch, deploy, then replay.
- **Poison message**: drop with `--drop` flag on replay_dlq (not implemented yet — use gcloud pubsub to ack manually).

## Prevention

- Canary a small sample of new 834 schemas through a staging tenant first.
- Add a contract test for the affected event shape.
