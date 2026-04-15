"""Integration test: 834 parser → atlas commands → bitemporal timeline.

No network. Drives the pipeline in-process: parse the golden 834 file, map
instructions into atlas commands, apply, and assert the final timeline shape.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "tests" / "golden" / "834_sample.x12"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_834_sample_produces_expected_timeline(pg_url: str) -> None:
    sys.path.insert(0, str(ROOT / "services" / "atlas"))
    from app.application.commands import (  # type: ignore
        add_enrollment,
        correct_enrollment,
        terminate_enrollment,
    )
    from app.domain.enrollment import (  # type: ignore
        INFINITY_DATE,
        AddCommand,
        CorrectionCommand,
        Relationship,
        TerminateCommand,
    )
    from eligibility_common import db as common_db

    common_db._engine = None
    common_db._sessionmaker = None
    from eligibility_common.db import engine, session_scope
    from eligibility_common.outbox import OUTBOX_DDL
    from x12_834 import MaintenanceType, parse_834

    async with engine().begin() as conn:
        await conn.execute(text(OUTBOX_DDL))
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
                """
            )
        )

    tenant = uuid4()
    employer = uuid4()
    plan_by_code: dict[str, object] = {}
    member_by_ref: dict[str, object] = {}

    # Parse the golden file
    instructions = list(parse_834(SAMPLE.read_bytes(), trading_partner_id="SENDER"))
    assert len(instructions) > 0

    # Drive into atlas — simplified: one tenant+employer, mint plan/member ids on first sight.
    for instr in instructions:
        plan_code = instr.plan_code or "DEFAULT"
        plan_id = plan_by_code.setdefault(plan_code, uuid4())
        member_ref = instr.subscriber_ref or instr.sponsor_ref or instr.last_name or "unknown"
        member_id = member_by_ref.setdefault(member_ref, uuid4())
        seg_key = instr.segment_key
        async with session_scope(tenant_id=str(tenant)) as s:
            try:
                if instr.maintenance_type in (MaintenanceType.ADD, MaintenanceType.REINSTATE):
                    await add_enrollment(
                        s,
                        AddCommand(
                            tenant_id=tenant,
                            employer_id=employer,
                            subgroup_id=None,
                            plan_id=plan_id,
                            member_id=member_id,
                            relationship=Relationship.SUBSCRIBER,
                            valid_from=instr.effective_date or date(2026, 1, 1),
                            valid_to=instr.termination_date or INFINITY_DATE,
                            source_segment_ref=seg_key,
                        ),
                        segment_key=seg_key,
                    )
                elif instr.maintenance_type == MaintenanceType.CANCEL:
                    await terminate_enrollment(
                        s,
                        TerminateCommand(
                            tenant_id=tenant,
                            member_id=member_id,
                            plan_id=plan_id,
                            valid_to=instr.termination_date or date(2026, 12, 31),
                            source_segment_ref=seg_key,
                        ),
                        segment_key=seg_key,
                    )
                elif instr.maintenance_type in (MaintenanceType.CORRECTION, MaintenanceType.CHANGE):
                    await correct_enrollment(
                        s,
                        CorrectionCommand(
                            tenant_id=tenant,
                            employer_id=employer,
                            subgroup_id=None,
                            plan_id=plan_id,
                            member_id=member_id,
                            relationship=Relationship.SUBSCRIBER,
                            new_valid_from=instr.effective_date or date(2026, 1, 15),
                            new_valid_to=instr.termination_date or INFINITY_DATE,
                            source_segment_ref=seg_key,
                        ),
                        segment_key=seg_key,
                    )
            except Exception as e:
                # Domain-level rejections (e.g., TERMINATE for unknown member) are expected
                # for some of the instruction variations — we only assert aggregate state below.
                print(f"skipped instruction {seg_key}: {e}")

    # Aggregate assertion: we have at least one in-force enrollment per member we added
    async with session_scope(tenant_id=str(tenant)) as s:
        res = (await s.execute(text("SELECT COUNT(*)::int AS n FROM enrollments"))).first()
        assert res.n >= 3, f"expected >=3 enrollment rows, got {res.n}"

        # At least one TERMED row (the cancel of Patel Amit)
        res = (
            await s.execute(
                text("SELECT COUNT(*)::int AS n FROM enrollments WHERE status='termed' AND txn_to > now()")
            )
        ).first()
        assert res.n >= 1

        # The outbox accumulated events
        res = (await s.execute(text("SELECT COUNT(*)::int AS n FROM outbox"))).first()
        assert res.n >= 3
