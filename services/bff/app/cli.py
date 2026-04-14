"""Operational CLI for the BFF container.

Usage (inside the bff container):
    python -m app.cli seed
    python -m app.cli replay --file-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.settings import settings

# ───────────── Seed data ─────────────
PAYER_ICICI = "11111111-0000-0000-0000-000000000001"
PAYER_AETNA = "11111111-0000-0000-0000-000000000002"

EMPLOYER_SWIGGY = "22222222-0000-0000-0000-000000000001"
EMPLOYER_ZOMATO = "22222222-0000-0000-0000-000000000002"

PLANS = [
    {
        "id": "33333333-0000-0000-0000-000000000001",
        "plan_code": "PLAN-GOLD",
        "name": "Gold Health",
        "type": "HLT",
        "metal_level": "GOLD",
    },
    {
        "id": "33333333-0000-0000-0000-000000000002",
        "plan_code": "PLAN-SILVER",
        "name": "Silver Health",
        "type": "HLT",
        "metal_level": "SILVER",
    },
    {
        "id": "33333333-0000-0000-0000-000000000003",
        "plan_code": "PLAN-BRONZE",
        "name": "Bronze Health",
        "type": "HLT",
        "metal_level": "BRONZE",
    },
]


async def _post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(5):
        try:
            r = await client.post(path, json=body, timeout=10.0)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            if attempt == 4:
                raise
            await asyncio.sleep(0.5 * (2**attempt))
    raise RuntimeError("unreachable")


async def seed() -> None:
    async with (
        httpx.AsyncClient(base_url=settings.group_url) as group,
        httpx.AsyncClient(base_url=settings.plan_url) as plan,
    ):
        # Payers
        for pid, name in ((PAYER_ICICI, "ICICI"), (PAYER_AETNA, "Aetna")):
            await _post(group, "/payers", {"id": pid, "name": name})
        # Employers
        await _post(
            group,
            "/employers",
            {"id": EMPLOYER_SWIGGY, "payer_id": PAYER_ICICI, "name": "Swiggy", "external_id": "SWIGGY"},
        )
        await _post(
            group,
            "/employers",
            {"id": EMPLOYER_ZOMATO, "payer_id": PAYER_ICICI, "name": "Zomato", "external_id": "ZOMATO"},
        )
        # Subgroups
        for emp, sg in (
            (EMPLOYER_SWIGGY, "SWIGGY_GROUP_A"),
            (EMPLOYER_SWIGGY, "SWIGGY_GROUP_B"),
            (EMPLOYER_ZOMATO, "ZOMATO_GROUP_A"),
            (EMPLOYER_ZOMATO, "ZOMATO_GROUP_B"),
        ):
            await _post(group, "/subgroups", {"employer_id": emp, "name": sg})
        # Plans
        for p in PLANS:
            await _post(plan, "/plans", p)
        # Plan visibility — every plan visible to both employers
        for emp in (EMPLOYER_SWIGGY, EMPLOYER_ZOMATO):
            for p in PLANS:
                await _post(group, "/visibility", {"employer_id": emp, "plan_id": p["id"]})
    print("seed complete")


async def replay(file_id: str) -> None:
    from eligibility_common.events import Topics
    from eligibility_common.pubsub import publish

    publish(
        Topics.FILE_RECEIVED,
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "FileReceived",
            "tenant_id": settings.tenant_default,
            "emitted_at": datetime.now(timezone.utc).isoformat(),
            "file_id": file_id,
            "format": "X12_834",
            "object_key": f"{settings.tenant_default}/{file_id}.x12",
        },
    )
    print(f"replay published for {file_id}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    rp = sub.add_parser("replay")
    rp.add_argument("--file-id", required=True)
    ns = p.parse_args()
    if ns.cmd == "seed":
        asyncio.run(seed())
    elif ns.cmd == "replay":
        asyncio.run(replay(ns.file_id))
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
