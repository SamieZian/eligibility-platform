"""Use-cases for Member aggregate."""
from __future__ import annotations

import hashlib
from typing import Protocol
from uuid import UUID

from eligibility_common.errors import Codes, NotFoundError
from eligibility_common.events import Topics
from eligibility_common.kms import LocalKMS
from eligibility_common.outbox import emit
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.member import (
    AddDependentCommand,
    Dependent,
    Member,
    UpsertMemberCommand,
    new_id,
    now_utc,
)
from app.infra.repo import MemberRepo


class _RepoLike(Protocol):
    async def find_by_card(self, tenant_id: UUID, card_number: str) -> Member | None: ...
    async def find_by_id(self, member_id: UUID) -> Member | None: ...
    async def insert(self, m: Member) -> None: ...
    async def update(self, m: Member) -> None: ...
    async def insert_dependent(self, d: Dependent) -> None: ...


async def _emit_member_upserted(s: AsyncSession | None, m: Member) -> None:
    if s is None:
        return
    await emit(
        s,
        aggregate="member",
        aggregate_id=m.id,
        event_type="MemberUpserted",
        payload={
            "member_id": str(m.id),
            "tenant_id": str(m.tenant_id),
            "employer_id": str(m.employer_id),
            "card_number": m.card_number,
            "first_name": m.first_name,
            "last_name": m.last_name,
            "dob": m.dob.isoformat() if m.dob else None,
            "gender": m.gender,
            "ssn_last4": m.ssn_last4,
        },
        headers={"topic": Topics.MEMBER, "tenant_id": str(m.tenant_id)},
    )


async def upsert_member(
    s: AsyncSession | None,
    repo: _RepoLike,
    cmd: UpsertMemberCommand,
    *,
    kms: LocalKMS | None = None,
) -> Member:
    """Upsert by (tenant_id, card_number). Encrypts SSN via LocalKMS.

    The AsyncSession `s` is passed separately so unit tests can inject a fake
    repo without needing a real SQLAlchemy session (emit is skipped when s=None).
    """
    existing: Member | None = None
    if cmd.card_number:
        existing = await repo.find_by_card(cmd.tenant_id, cmd.card_number)

    ssn_last4: str | None = None
    ssn_sha256: bytes | None = None
    ssn_ciphertext: str | None = None
    if cmd.ssn:
        cleaned = cmd.ssn.replace("-", "").replace(" ", "")
        ssn_last4 = cleaned[-4:]
        ssn_sha256 = hashlib.sha256(cleaned.encode()).digest()
        kms_inst = kms or LocalKMS.from_env()
        ssn_ciphertext = kms_inst.encrypt(cleaned.encode())

    if existing is None:
        m = Member(
            id=new_id(),
            tenant_id=cmd.tenant_id,
            employer_id=cmd.employer_id,
            payer_member_id=cmd.payer_member_id,
            card_number=cmd.card_number,
            first_name=cmd.first_name,
            last_name=cmd.last_name,
            dob=cmd.dob,
            gender=cmd.gender,
            ssn_last4=ssn_last4,
            ssn_sha256=ssn_sha256,
            ssn_ciphertext=ssn_ciphertext,
            address=cmd.address,
            version=1,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        await repo.insert(m)
    else:
        existing.employer_id = cmd.employer_id
        existing.payer_member_id = cmd.payer_member_id or existing.payer_member_id
        existing.card_number = cmd.card_number or existing.card_number
        existing.first_name = cmd.first_name
        existing.last_name = cmd.last_name
        existing.dob = cmd.dob
        existing.gender = cmd.gender or existing.gender
        if cmd.ssn:
            existing.ssn_last4 = ssn_last4
            existing.ssn_sha256 = ssn_sha256
            existing.ssn_ciphertext = ssn_ciphertext
        existing.address = cmd.address if cmd.address is not None else existing.address
        existing.version += 1
        existing.updated_at = now_utc()
        await repo.update(existing)
        m = existing

    await _emit_member_upserted(s, m)
    return m


async def add_dependent(
    repo: _RepoLike, cmd: AddDependentCommand
) -> Dependent:
    parent = await repo.find_by_id(cmd.member_id)
    if parent is None:
        raise NotFoundError(Codes.MEMBER_NOT_FOUND, f"Member {cmd.member_id} not found")
    dep = Dependent(
        id=new_id(),
        member_id=cmd.member_id,
        relationship=cmd.relationship,
        first_name=cmd.first_name,
        last_name=cmd.last_name,
        dob=cmd.dob,
        gender=cmd.gender,
    )
    await repo.insert_dependent(dep)
    return dep
