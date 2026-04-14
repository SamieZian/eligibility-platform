# Sample 834 EDI files

Ready-to-upload ANSI X12 834 (Benefit Enrollment and Maintenance) files for
testing the platform. Upload them from the UI at http://localhost:5173 → Upload,
or via `make ingest F=samples/834_sample.x12`.

| File | Scenarios |
|---|---|
| `834_sample.x12` | **Default demo**. 5 ADDs (subscribers + dependents across Swiggy/Zomato), 1 TERMINATE, 1 CORRECTION. Deterministic IDs so assertions are stable. Use this one. |
| `834_replace.x12` | Full-file-replace (`BGN08=22`). Demonstrates the saga that terminates all active enrollments not present in the new file. |
| `834_large.x12` | 1000 synthetic ADDs. For load testing the ingestion pipeline. |

## What's in `834_sample.x12`

**Envelope:** ISA `SENDER` → `RECEIVER`, control `000000001`. GS `005010X220A1`. ST `0001`. BGN original (not replace).

**Sponsor:** ICICI (via `REF*38`).

**Members (5 INS loops):**

| # | Relationship | Name | Card | DOB | Employer | Plan | Action |
|---|---|---|---|---|---|---|---|
| 1 | Subscriber | PRIYA SHARMA | 123456789 | 1990-02-15 F | Swiggy | PLAN-GOLD (FAM) | ADD 021 |
| 2 | Spouse | ROHIT SHARMA | 123456790 | 1988-07-12 M | Swiggy | PLAN-GOLD (FAM) | ADD 021 |
| 3 | Subscriber | AMIT PATEL | 234567891 | 1985-11-20 M | Zomato | PLAN-SILVER (IND) | ADD 021 |
| 4 | Subscriber | SIMRAN KAUR | 345678912 | 1992-08-04 F | Swiggy | PLAN-GOLD (IND) | ADD 021 |
| 5 | Subscriber | ARJUN NAIR | 456789123 | 1981-03-08 M | Zomato | PLAN-SILVER (IND) | ADD 021 |

**Then:**
- **TERMINATE 024** — Amit Patel's Silver plan ends 2026-03-31.
- **CORRECTION 030** — Simran Kaur's effective date moves from 2026-01-01 → 2026-01-15 (retroactive; creates a bitemporal history row — you can see both the old and new rows in the member detail drawer).

## What happens after upload

1. BFF receives the multipart file → streams to MinIO → emits `FileReceived` to Pub/Sub.
2. `ingestion` worker consumes → streaming-parses the 834 → resolves employer/member/plan IDs against the group/member/plan services → POSTs commands to `atlas`.
3. `atlas` applies bitemporal writes in a single DB transaction + inserts outbox rows.
4. `outbox-relay` publishes the outbox rows to Pub/Sub (`EnrollmentAdded`, `MemberUpserted`, etc.).
5. `projector` consumes those → upserts the denormalized `eligibility_view` + OpenSearch index.
6. The UI shows 5 enrollments; search "sharma" returns Priya and Rohit; Simran's timeline shows both the corrected and the historical row.

## Regenerate

```bash
python3 tests/golden/generate_834.py
```
