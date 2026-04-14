# Sample 834 EDI files

Ready-to-upload ANSI X12 834 (Benefit Enrollment and Maintenance) files for testing the platform.

**From the UI:** http://localhost:3000 → Upload tab → drag any of these in.
**From the CLI:** `make ingest F=samples/834_demo.x12` (or use the default `make ingest`).

## Files

| File | Use case | Members | Size |
|---|---|---|---|
| **`834_demo.x12`** ⭐ | **Default demo** — 18 members across Swiggy + Zomato + 4 subgroups + all 3 plans. Subscribers + dependents (Reddy family with child, Iyer family with spouse). Best for showing the platform's range. | 18 | ~3.6 KB |
| `834_sample.x12` | The original test fixture — 5 ADDs (subscriber Sharma Priya + spouse Rohit, 3 more subscribers) + 1 TERMINATE (Patel Amit ends 2026-03-31) + 1 CORRECTION (Kaur Simran's effective date moves 2026-01-01 → 2026-01-15). Best for exercising the bitemporal timeline. | 5 + edits | ~3 KB |
| `834_replace.x12` | Full-file-replace (`BGN08=22`). Demonstrates the saga that terminates all active enrollments not present in the new file. | 2 | small |
| **`members_demo.csv`** | **Alternative ingestion path** — proves the platform handles CSV in addition to 834. 8 members (Sharma, Gupta, Rao, Iyengar, Kumar, Kapoor, Verma, Mehta). Same downstream pipeline (parser → atlas → events → projector). | 8 | ~1 KB |
| `834_large.x12` | 1000 synthetic ADDs. For load-testing the ingestion pipeline. | 1000 | ~200 KB |

## What's in `834_demo.x12` (the recommended demo file)

Envelope: ISA `SENDER → RECEIVER` control `000000200`. Sponsor `ICICI_DEMO_POLICY`. Effective date `2026-01-01`.

### Swiggy members (9)
| # | Name | Card | DOB | Subgroup | Plan | Type |
|---|---|---|---|---|---|---|
| 1 | PRIYA SHARMA | 111000001 | 1990-02-15 F | SWIGGY-A | PLAN-GOLD (FAM) | Subscriber |
| 2 | ROHIT SHARMA | 111000002 | 1988-07-12 M | SWIGGY-A | PLAN-GOLD (FAM) | Spouse of Priya |
| 3 | SIMRAN KAUR | 111000003 | 1992-08-04 F | SWIGGY-A | PLAN-GOLD (IND) | Subscriber |
| 4 | VIKRAM REDDY | 111000004 | 1987-05-18 M | SWIGGY-B | PLAN-SILVER (IND) | Subscriber |
| 5 | ANANYA REDDY | 111000005 | 1989-03-22 F | SWIGGY-B | PLAN-SILVER (FAM) | Spouse of Vikram |
| 6 | AARAV REDDY | 111000006 | 2015-06-10 M | SWIGGY-B | PLAN-SILVER (FAM) | Child of Vikram |
| 7 | MEERA DESAI | 111000007 | 1995-12-25 F | SWIGGY-A | PLAN-BRONZE (IND) | Subscriber |
| 8 | RAVI JOSHI | 111000008 | 1983-04-09 M | SWIGGY-B | PLAN-GOLD (IND) | Subscriber |
| 9 | DEEPA MENON | 111000009 | 1991-11-28 F | SWIGGY-A | PLAN-SILVER (IND) | Subscriber |

### Zomato members (9)
| # | Name | Card | DOB | Subgroup | Plan | Type |
|---|---|---|---|---|---|---|
| 10 | AMIT PATEL | 222000001 | 1985-11-20 M | ZOMATO-A | PLAN-SILVER (IND) | Subscriber |
| 11 | ARJUN NAIR | 222000002 | 1981-03-08 M | ZOMATO-A | PLAN-SILVER (IND) | Subscriber |
| 12 | KAVYA IYER | 222000003 | 1993-08-12 F | ZOMATO-B | PLAN-GOLD (FAM) | Subscriber |
| 13 | RAHUL IYER | 222000004 | 1992-02-15 M | ZOMATO-B | PLAN-GOLD (FAM) | Spouse of Kavya |
| 14 | ROHAN GUPTA | 222000005 | 1990-07-15 M | ZOMATO-A | PLAN-BRONZE (IND) | Subscriber |
| 15 | POOJA SINGH | 222000006 | 1984-09-03 F | ZOMATO-B | PLAN-GOLD (IND) | Subscriber |
| 16 | FARHAN KHAN | 222000007 | 1996-10-14 M | ZOMATO-A | PLAN-SILVER (IND) | Subscriber |
| 17 | LATHA RAO | 222000008 | 1979-05-27 F | ZOMATO-A | PLAN-BRONZE (IND) | Subscriber |
| 18 | NIKHIL VERMA | 222000009 | 1998-12-01 M | ZOMATO-B | PLAN-SILVER (IND) | Subscriber |

## What `834_sample.x12` adds

The original 5-member fixture also includes:

- **TERMINATE (024)** — Amit Patel's Silver plan ends 2026-03-31.
- **CORRECTION (030)** — Simran Kaur's effective date moves from 2026-01-01 → 2026-01-15 (retroactive; creates a bitemporal history row visible in the member detail drawer).

Use this one if you want to exercise the bitemporal timeline UI.

## What happens after upload

1. BFF receives the multipart file → streams to MinIO → publishes `FileReceived` to Pub/Sub.
2. `ingestion` worker consumes → streaming-parses the 834 → resolves employer / member / plan IDs against the group / member / plan services → POSTs commands to `atlas`.
3. `atlas` applies bitemporal writes in a single DB transaction + inserts outbox rows.
4. `outbox-relay` publishes the outbox rows to Pub/Sub (`EnrollmentAdded`, `MemberUpserted`, etc.).
5. `projector` consumes those → upserts the denormalized `eligibility_view` + OpenSearch index.
6. The UI shows the new rows; search "sharma" returns Priya + Rohit; click any row for the bitemporal timeline.

End-to-end latency: typically 5–10 seconds for 18 rows.

## Regenerate

```bash
python3 samples/generate_834_demo.py     # the 18-member demo
python3 tests/golden/generate_834.py     # the 5-member fixture + replace + large
```
