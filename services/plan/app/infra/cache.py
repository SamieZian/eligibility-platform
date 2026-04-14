"""Redis cache-aside for the Plan catalog.

Keys:
  plan:id:<uuid>      -> JSON doc
  plan:code:<code>    -> JSON doc
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from redis import asyncio as redis_asyncio

from app.domain.plan import Plan

_client: redis_asyncio.Redis | None = None


def client(redis_url: str) -> redis_asyncio.Redis:
    global _client
    if _client is None:
        _client = redis_asyncio.from_url(redis_url, decode_responses=True)
    return _client


def _k_id(plan_id: UUID) -> str:
    return f"plan:id:{plan_id}"


def _k_code(code: str) -> str:
    return f"plan:code:{code}"


def _to_doc(p: Plan) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "plan_code": p.plan_code,
        "name": p.name,
        "type": p.type,
        "metal_level": p.metal_level,
        "attributes": p.attributes or {},
        "version": p.version,
    }


def _from_doc(d: dict[str, Any]) -> Plan:
    return Plan(
        id=UUID(d["id"]),
        plan_code=d["plan_code"],
        name=d["name"],
        type=d["type"],
        metal_level=d.get("metal_level"),
        attributes=d.get("attributes") or {},
        version=int(d.get("version", 1)),
    )


async def get_by_id(redis_url: str, plan_id: UUID) -> Plan | None:
    raw = await client(redis_url).get(_k_id(plan_id))
    return _from_doc(json.loads(raw)) if raw else None


async def get_by_code(redis_url: str, code: str) -> Plan | None:
    raw = await client(redis_url).get(_k_code(code))
    return _from_doc(json.loads(raw)) if raw else None


async def set_plan(redis_url: str, p: Plan, ttl_seconds: int) -> None:
    c = client(redis_url)
    doc = json.dumps(_to_doc(p))
    await c.set(_k_id(p.id), doc, ex=ttl_seconds)
    await c.set(_k_code(p.plan_code), doc, ex=ttl_seconds)


async def invalidate(redis_url: str, p: Plan) -> None:
    c = client(redis_url)
    await c.delete(_k_id(p.id), _k_code(p.plan_code))
