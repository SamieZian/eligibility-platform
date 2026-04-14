# Runbook: Anomaly Detection & AI-assisted Extraction

Owners: platform-eng  
Severity: P3 (degraded extraction) · P2 (sustained anomaly with pending commands)  
Last reviewed: 2026-04-14

## Scope

Covers two related AI hooks in the ingestion path:

1. **Rules-based anomaly detection** on command volume per trading partner.
2. **Vertex AI Document AI** opt-in branch for scanned 834 PDF / image faxes.
3. **Vertex AI Forecasting** (planned) for expected daily enrollment volume.

## Detection rules

Rules run inside the `projector` worker after each batch commit:

| Signal | Threshold | Action |
|---|---|---|
| `enrollment_adds` for a `trading_partner_id` < 0.3× 7-day median | sustained 30 min | page on-call |
| `ingestion.instruction.failed` rate > 5% over 15 min | per worker | warn in #eligibility-alerts |
| `ingestion.pdf_scanned_without_docai` observed in prod | any occurrence | warn — payer is sending scans but feature flag is off |
| Forecast delta > ±3σ vs. Vertex AI Forecasting baseline | daily rollup at 02:00 UTC | ticket, not page |

The forecasting hook is a stub today (see `projector/app/anomaly.py::forecast_hook`); Vertex AI Forecasting is wired when `VERTEX_AI_FORECAST_MODEL_ID` is set. Until then, the rules-based thresholds are authoritative.

## How to enable Document AI

The ingestion worker treats Document AI as strictly opt-in — see `ingestion/app/document_ai.py::is_enabled`.

```bash
# 1. Install the extra on the worker image
poetry install --extras ai

# 2. Set env vars on the ingestion deployment
export GOOGLE_CLOUD_PROJECT=eligibility-prod
export VERTEX_AI_LOCATION=us
export VERTEX_AI_DOCUMENT_PROCESSOR_ID=projects/.../processors/abc123

# 3. Ensure the workload identity / service account has
#    roles/documentai.apiUser on the processor.
```

Validate:

```bash
docker compose exec ingestion \
  python -c "from app import document_ai; print(document_ai.is_enabled())"
# expect: True
```

When disabled, scanned PDFs surface as `ingestion.pdf_scanned_without_docai` warnings and the file is skipped — they do **not** dead-letter, because the payload itself is valid; we just lack extraction capability.

## Expected lag + alerts

| Stage | p50 lag | p95 lag | Alert after |
|---|---|---|---|
| `file.received` → first atlas command (CSV/X12) | 1.2s | 4s | 30s |
| `file.received` → first atlas command (Document AI) | 5s | 25s | 90s |
| Command → projection visible in `/search` | 400ms | 1.5s | 10s |

Pager signals:

- `ingestion.document_ai.call` with no matching `ingestion.document_ai.extracted` inside 120s → Document AI stuck; check quota.
- `document_ai.process_document` retry exhaustion (3 attempts) → surfaces as `ingestion.file.failed` and nacks to DLQ after `max_delivery`.

## Rollback

Unset `VERTEX_AI_DOCUMENT_PROCESSOR_ID` and redeploy — the worker reverts to refusing scanned PDFs with the warning log. No data migration required.
