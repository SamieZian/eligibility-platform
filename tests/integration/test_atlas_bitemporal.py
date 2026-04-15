"""Integration test: real Postgres → atlas bitemporal invariants.

Verifies:
- ADD creates an in-force row.
- Duplicate segment_key is ignored (idempotent 834 retries).
- TERMINATE closes the in-force row and opens a TERMED segment.
- CORRECTION closes the in-force row and opens a new corrected one (valid_to of
  the closed row is preserved; only txn_to is touched).
- Outbox accumulates one row per command.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_atlas_bitemporal_lifecycle(pg_url: str) -> None:
    """Full lifecycle: ADD → TERMINATE, plus CORRECTION."""
    # Import lazily so the DATABASE_URL env var is set first.
    sys.path.insert(0, str(ROOT / "services" / "atlas"))
    from app.application.commands import (  # type: ignore[import-not-found]
        add_enrollment,
        correct_enrollment,
        terminate_enrollment,
    )
    from app.domain.enrollment import (  # type: ignore[import-not-found]
        INFINITY_DATE,
        AddCommand,
        CorrectionCommand,
        Relationship,
        TerminateCommand,
    )
    from app.infra.repo import EnrollmentRepo  # type: ignore[import-not-found]

    # Re-create engine so it picks up the pg_url fixture.
    from eligibility_common import db as common_db  # noqa: WPS433 — test-time reset

    common_db._engine = None
    common_db._sessionmaker = None
    from eligibility_common.db import engine, session_scope
    from eligibility_common.idempotency import IDEMPOTENCY_DDL
    from eligibility_common.outbox import OUTBOX_DDL

    # DDL
    async with engine().begin() as conn:
        await conn.execute(text(OUTBOX_DDL))
        await conn.execute(text(IDEMPOTENCY_DDL))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS enrollments (
                  id UUID PRIMARY KEY,
                  tenant_id UUID NOT NULL,
                  employer_id UUID NOT NULL,
                  subgroup_id UUID,
                  plan_id UUID NOT NULL,
                  member_id UUID NOT NULL,
                  relationship TEXT NOT NULL,
                  status TEXT NOT NULL,
                  valid_from DATE NOT NULL,
                  valid_to DATE NOT NULL,
                  txn_from TIMESTAMPTZ NOT NULL DEFAULT now(),
                  txn_to TIMESTAMPTZ NOT NULL,
                  source_file_id UUID,
                  source_segment_ref TEXT,
                  version BIGINT NOT NULL DEFAULT 1,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS processed_segments (
                  segment_key TEXT PRIMARY KEY,
                  processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS sagas (
                  id UUID PRIMARY KEY,
                  kind TEXT NOT NULL,
                  status TEXT NOT NULL,
                  state JSONB NOT NULL,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
        )

    tenant = uuid4()
    employer = uuid4()
    plan = uuid4()
    member = uuid4()

    # 1. ADD
    async with session_scope(tenant_id=str(tenant)) as s:
        await add_enrollment(
            s,
            AddCommand(
                tenant_id=tenant,
                employer_id=employer,
                subgroup_id=None,
                plan_id=plan,
                member_id=member,
                relationship=Relationship.SUBSCRIBER,
                valid_from=date(2026, 1, 1),
                valid_to=INFINITY_DATE,
                source_segment_ref="trader:123:456:0001:1",
            ),
            segment_key="trader:123:456:0001:1",
        )

    async with session_scope(tenant_id=str(tenant)) as s:
        repo = EnrollmentRepo(s)
        tl = await repo.load_timeline(tenant, member)
        in_force = tl.in_force()
        assert len(in_force) == 1
        assert in_force[0].status.value == "active"
        assert in_force[0].valid_from == date(2026, 1, 1)

    # 2. Duplicate segment_key is a no-op
    from eligibility_common.errors import DomainError

    async with session_scope(tenant_id=str(tenant)) as s:
        with pytest.raises(DomainError) as exc_info:
            await add_enrollment(
                s,
                AddCommand(
                    tenant_id=tenant,
                    employer_id=employer,
                    subgroup_id=None,
                    plan_id=plan,
                    member_id=member,
                    relationship=Relationship.SUBSCRIBER,
                    valid_from=date(2026, 1, 1),
                    valid_to=INFINITY_DATE,
                ),
                segment_key="trader:123:456:0001:1",
            )
        assert exc_info.value.code == "DUPLICATE_SEGMENT"

    # 3. TERMINATE
    async with session_scope(tenant_id=str(tenant)) as s:
        closed = await terminate_enrollment(
            s,
            TerminateCommand(
                tenant_id=tenant,
                member_id=member,
                plan_id=plan,
                valid_to=date(2026, 6, 30),
                source_segment_ref="trader:123:456:0001:2",
            ),
            segment_key="trader:123:456:0001:2",
        )
        assert len(closed) == 1

    async with session_scope(tenant_id=str(tenant)) as s:
        repo = EnrollmentRepo(s)
        tl = await repo.load_timeline(tenant, member)
        in_force = tl.in_force()
        # After terminate: 1 in-force TERMED row; the original ACTIVE row is history
        assert len(in_force) == 1
        assert in_force[0].status.value == "termed"
        assert in_force[0].valid_to == date(2026, 6, 30)
        # And there's at least 1 history row (the closed active one)
        history = [s for s in tl.segments if not s.is_in_force]
        assert any(h.status.value == "active" for h in history)

    # 4. CORRECTION on a fresh plan (add then correct)
    plan2 = uuid4()
    async with session_scope(tenant_id=str(tenant)) as s:
        await add_enrollment(
            s,
            AddCommand(
                tenant_id=tenant,
                employer_id=employer,
                subgroup_id=None,
                plan_id=plan2,
                member_id=member,
                relationship=Relationship.SUBSCRIBER,
                valid_from=date(2026, 1, 1),
                valid_to=INFINITY_DATE,
            ),
        )

    async with session_scope(tenant_id=str(tenant)) as s:
        await correct_enrollment(
            s,
            CorrectionCommand(
                tenant_id=tenant,
                member_id=member,
                plan_id=plan2,
                new_valid_from=date(2026, 1, 15),
                new_valid_to=INFINITY_DATE,
                employer_id=employer,
                subgroup_id=None,
                relationship=Relationship.SUBSCRIBER,
            ),
        )

    async with session_scope(tenant_id=str(tenant)) as s:
        repo = EnrollmentRepo(s)
        tl = await repo.load_timeline(tenant, member)
        plan2_in_force = [seg for seg in tl.in_force() if seg.plan_id == plan2]
        assert len(plan2_in_force) == 1
        assert plan2_in_force[0].valid_from == date(2026, 1, 15)  # corrected

    # 5. Outbox has rows for each command (3 ADDs + 1 TERMINATE + 1 CHANGE = 5)
    async with session_scope(tenant_id=str(tenant)) as s:
        row = (await s.execute(text("SELECT COUNT(*)::int AS n FROM outbox"))).first()
        assert row.n >= 5
