"""Use-cases for the Plan aggregate."""
from __future__ import annotations

from eligibility_common.events import Topics
from eligibility_common.outbox import emit
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.plan import Plan, UpsertPlanCommand, new_id
from app.infra import cache
from app.infra.repo import PlanRepo
from app.settings import settings


async def upsert_plan(
    s: AsyncSession, repo: PlanRepo, cmd: UpsertPlanCommand, *, tenant_id: str
) -> Plan:
    p = Plan(
        id=new_id(),
        plan_code=cmd.plan_code,
        name=cmd.name,
        type=cmd.type,
        metal_level=cmd.metal_level,
        attributes=cmd.attributes or {},
    )
    saved = await repo.upsert(p)

    # write-through invalidate so the next GET re-populates cache
    try:
        await cache.invalidate(settings.redis_url, saved)
    except Exception:  # cache unavailable — never fail the write
        pass

    await emit(
        s,
        aggregate="plan",
        aggregate_id=saved.id,
        event_type="PlanUpserted",
        payload={
            "plan_id": str(saved.id),
            "plan_code": saved.plan_code,
            "name": saved.name,
            "type": saved.type,
            "metal_level": saved.metal_level,
            "version": saved.version,
        },
        headers={"topic": Topics.PLAN, "tenant_id": tenant_id},
    )
    return saved
