# Golden X12 834 fixtures

Deterministic ANSI X12 834 (5010X220A1) files produced by `generate_834.py`.
Regenerate with:

```
python3 tests/golden/generate_834.py
```

All three files share the same envelope delimiters — element `*`, composite `:`,
segment terminator `~` — and the same sender/receiver pair so assertions can
focus on body content.

## `834_sample.x12`

Small demo transmission exercising the primary maintenance codes in one file:

| # | Maintenance | Subscriber        | Plan         | Level | Note                                                |
|---|-------------|-------------------|--------------|-------|------------------------------------------------------|
| 1 | ADD (021)   | SHARMA PRIYA      | PLAN-GOLD    | FAM   | Swiggy, subgroup A, effective 2026-01-01             |
| 2 | ADD (021)   | SHARMA ROHIT      | PLAN-GOLD    | FAM   | Spouse dep of Priya (relationship 01)                |
| 3 | ADD (021)   | PATEL AMIT        | PLAN-SILVER  | IND   | Zomato, effective 2026-01-01                         |
| 4 | ADD (021)   | KAUR SIMRAN       | PLAN-GOLD    | IND   | Swiggy, effective 2026-01-01                         |
| 5 | ADD (021)   | NAIR ARJUN        | PLAN-SILVER  | IND   | Zomato, effective 2026-01-01                         |
| 6 | CANCEL (024)| PATEL AMIT        | PLAN-SILVER  | IND   | Termination 2026-03-31                               |
| 7 | CORRECTION  | KAUR SIMRAN       | PLAN-GOLD    | IND   | Effective date corrected to 2026-01-15               |

BGN08 = `2` (Original).

## `834_replace.x12`

Same envelope pattern but `BGN08 = 22` (Full Replace). Contains only the two
Swiggy members who remain after the correction window — used to exercise
reconciliation/replace semantics in the enrollment workers.

## `834_large.x12`

1000 ADD (`021`) instructions generated from a `random.Random(42)` seed so the
file is byte-stable across runs. Alternates sponsor (Swiggy/Zomato) and plan
(Gold/Silver) on odd/even sequence. Used for load and memory-stability tests.
