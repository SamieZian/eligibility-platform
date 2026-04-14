"""Pure-domain Plan aggregate."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Plan:
    id: UUID
    plan_code: str
    name: str
    type: str
    metal_level: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    version: int = 1


@dataclass
class UpsertPlanCommand:
    plan_code: str
    name: str
    type: str
    metal_level: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


def new_id() -> UUID:
    return uuid4()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
