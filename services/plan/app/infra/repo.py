"""Repository — the only place that touches the DB for the Plan aggregate."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.plan import Plan, new_id


class PlanRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def find_by_id(self, plan_id: UUID) -> Plan | None:
        r = (
            await self.s.execute(
                text(
                    """
                    SELECT id, plan_code, name, type, metal_level, attributes, version
                    FROM plans WHERE id = :id
                    """
                ),
                {"id": str(plan_id)},
            )
        ).first()
        return _row_to_plan(r) if r else None

    async def find_by_code(self, plan_code: str) -> Plan | None:
        r = (
            await self.s.execute(
                text(
                    """
                    SELECT id, plan_code, name, type, metal_level, attributes, version
                    FROM plans WHERE plan_code = :c
                    """
                ),
                {"c": plan_code},
            )
        ).first()
        return _row_to_plan(r) if r else None

    async def upsert(self, p: Plan) -> Plan:
        existing = await self.find_by_code(p.plan_code)
        if existing is None:
            plan_id = p.id or new_id()
            await self.s.execute(
                text(
                    """
                    INSERT INTO plans (id, plan_code, name, type, metal_level, attributes, version)
                    VALUES (:id, :c, :n, :t, :ml, CAST(:a AS JSONB), 1)
                    """
                ),
                {
                    "id": str(plan_id),
                    "c": p.plan_code,
                    "n": p.name,
                    "t": p.type,
                    "ml": p.metal_level,
                    "a": json.dumps(p.attributes or {}),
                },
            )
            p.id = plan_id
            p.version = 1
            return p
        await self.s.execute(
            text(
                """
                UPDATE plans
                SET name = :n, type = :t, metal_level = :ml,
                    attributes = CAST(:a AS JSONB), version = version + 1
                WHERE id = :id
                """
            ),
            {
                "id": str(existing.id),
                "n": p.name,
                "t": p.type,
                "ml": p.metal_level,
                "a": json.dumps(p.attributes or {}),
            },
        )
        existing.name = p.name
        existing.type = p.type
        existing.metal_level = p.metal_level
        existing.attributes = p.attributes or {}
        existing.version += 1
        return existing


def _row_to_plan(r: Any) -> Plan:
    return Plan(
        id=r.id,
        plan_code=r.plan_code,
        name=r.name,
        type=r.type,
        metal_level=r.metal_level,
        attributes=dict(r.attributes) if r.attributes else {},
        version=r.version,
    )
