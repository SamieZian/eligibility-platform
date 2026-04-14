from __future__ import annotations

from typing import Any
from uuid import UUID

from eligibility_common.db import session_scope
from eligibility_common.errors import Codes, NotFoundError
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.application.commands import upsert_plan
from app.domain.plan import Plan, UpsertPlanCommand
from app.infra import cache
from app.infra.repo import PlanRepo
from app.settings import settings

router = APIRouter(prefix="", tags=["plan"])


class PlanIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plan_code: str
    name: str
    type: str
    metal_level: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class PlanOut(BaseModel):
    id: UUID
    plan_code: str
    name: str
    type: str
    metal_level: str | None
    attributes: dict[str, Any]
    version: int


def _to_out(p: Plan) -> PlanOut:
    return PlanOut(
        id=p.id,
        plan_code=p.plan_code,
        name=p.name,
        type=p.type,
        metal_level=p.metal_level,
        attributes=p.attributes or {},
        version=p.version,
    )


@router.post("/plans", response_model=PlanOut, status_code=200)
async def post_plan(body: PlanIn) -> PlanOut:
    async with session_scope(tenant_id=settings.tenant_default) as s:
        repo = PlanRepo(s)
        saved = await upsert_plan(
            s,
            repo,
            UpsertPlanCommand(
                plan_code=body.plan_code,
                name=body.name,
                type=body.type,
                metal_level=body.metal_level,
                attributes=body.attributes,
            ),
            tenant_id=settings.tenant_default,
        )
        return _to_out(saved)


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: UUID) -> PlanOut:
    # Cache-aside: Redis first
    try:
        cached = await cache.get_by_id(settings.redis_url, plan_id)
    except Exception:
        cached = None
    if cached is not None:
        return _to_out(cached)
    async with session_scope() as s:
        repo = PlanRepo(s)
        p = await repo.find_by_id(plan_id)
        if p is None:
            raise NotFoundError(Codes.MEMBER_NOT_FOUND, f"Plan {plan_id} not found")
        try:
            await cache.set_plan(settings.redis_url, p, settings.plan_cache_ttl_seconds)
        except Exception:
            pass
        return _to_out(p)


@router.get("/plans", response_model=PlanOut)
async def get_plan_by_code(code: str = Query(...)) -> PlanOut:
    try:
        cached = await cache.get_by_code(settings.redis_url, code)
    except Exception:
        cached = None
    if cached is not None:
        return _to_out(cached)
    async with session_scope() as s:
        repo = PlanRepo(s)
        p = await repo.find_by_code(code)
        if p is None:
            raise NotFoundError(Codes.MEMBER_NOT_FOUND, f"Plan code {code} not found")
        try:
            await cache.set_plan(settings.redis_url, p, settings.plan_cache_ttl_seconds)
        except Exception:
            pass
        return _to_out(p)
