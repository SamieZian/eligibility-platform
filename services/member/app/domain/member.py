"""Pure-domain Member aggregate. No I/O — repository handles persistence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class Relationship(str, Enum):
    SUBSCRIBER = "subscriber"
    SPOUSE = "spouse"
    CHILD = "child"
    DEPENDENT = "dependent"


@dataclass
class Member:
    id: UUID
    tenant_id: UUID
    employer_id: UUID
    first_name: str
    last_name: str
    dob: date
    payer_member_id: str | None = None
    card_number: str | None = None
    gender: str | None = None
    ssn_last4: str | None = None
    ssn_sha256: bytes | None = None
    ssn_ciphertext: str | None = None
    address: dict[str, Any] | None = None
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Dependent:
    id: UUID
    member_id: UUID
    relationship: Relationship
    first_name: str
    last_name: str
    dob: date
    gender: str | None = None


@dataclass
class UpsertMemberCommand:
    tenant_id: UUID
    employer_id: UUID
    first_name: str
    last_name: str
    dob: date
    payer_member_id: str | None = None
    card_number: str | None = None
    gender: str | None = None
    ssn: str | None = None  # full SSN; encrypted at rest
    address: dict[str, Any] | None = None


@dataclass
class AddDependentCommand:
    member_id: UUID
    relationship: Relationship
    first_name: str
    last_name: str
    dob: date
    gender: str | None = None


def new_id() -> UUID:
    return uuid4()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
