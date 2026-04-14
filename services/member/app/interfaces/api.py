from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from eligibility_common.db import session_scope
from eligibility_common.errors import Codes, NotFoundError
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.application.commands import add_dependent, upsert_member
from app.domain.member import (
    AddDependentCommand,
    Relationship,
    UpsertMemberCommand,
)
from app.infra.repo import MemberRepo

router = APIRouter(prefix="", tags=["member"])


class MemberIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: UUID
    employer_id: UUID
    first_name: str
    last_name: str
    dob: date
    payer_member_id: str | None = None
    card_number: str | None = None
    gender: str | None = None
    ssn: str | None = Field(None, description="Full SSN; encrypted at rest via KMS")
    address: dict[str, Any] | None = None


class MemberOut(BaseModel):
    id: UUID
    tenant_id: UUID
    employer_id: UUID
    first_name: str | None
    last_name: str | None
    dob: date | None
    payer_member_id: str | None
    card_number: str | None
    gender: str | None
    ssn_last4: str | None
    address: dict[str, Any] | None
    version: int


class DependentIn(BaseModel):
    relationship: Relationship = Relationship.CHILD
    first_name: str
    last_name: str
    dob: date
    gender: str | None = None


class DependentOut(BaseModel):
    id: UUID
    member_id: UUID
    relationship: Relationship
    first_name: str | None
    last_name: str | None
    dob: date | None
    gender: str | None


def _to_out(m: Any) -> MemberOut:
    return MemberOut(
        id=m.id,
        tenant_id=m.tenant_id,
        employer_id=m.employer_id,
        first_name=m.first_name,
        last_name=m.last_name,
        dob=m.dob,
        payer_member_id=m.payer_member_id,
        card_number=m.card_number,
        gender=m.gender,
        ssn_last4=m.ssn_last4,
        address=m.address,
        version=m.version,
    )


@router.post("/members", response_model=MemberOut, status_code=200)
async def post_member(body: MemberIn) -> MemberOut:
    async with session_scope(tenant_id=str(body.tenant_id)) as s:
        repo = MemberRepo(s)
        m = await upsert_member(
            s,
            repo,
            UpsertMemberCommand(
                tenant_id=body.tenant_id,
                employer_id=body.employer_id,
                first_name=body.first_name,
                last_name=body.last_name,
                dob=body.dob,
                payer_member_id=body.payer_member_id,
                card_number=body.card_number,
                gender=body.gender,
                ssn=body.ssn,
                address=body.address,
            ),
        )
        return _to_out(m)


@router.get("/members/{member_id}", response_model=MemberOut)
async def get_member(member_id: UUID) -> MemberOut:
    async with session_scope() as s:
        repo = MemberRepo(s)
        m = await repo.find_by_id(member_id)
        if m is None:
            raise NotFoundError(Codes.MEMBER_NOT_FOUND, f"Member {member_id} not found")
        return _to_out(m)


@router.get("/members", response_model=MemberOut)
async def get_member_by_card(
    cardNumber: str = Query(..., alias="cardNumber"),
    tenantId: UUID = Query(..., alias="tenantId"),
) -> MemberOut:
    async with session_scope(tenant_id=str(tenantId)) as s:
        repo = MemberRepo(s)
        m = await repo.find_by_card(tenantId, cardNumber)
        if m is None:
            raise NotFoundError(
                Codes.MEMBER_NOT_FOUND, f"No member for card {cardNumber}"
            )
        return _to_out(m)


@router.post(
    "/members/{member_id}/dependents",
    response_model=DependentOut,
    status_code=201,
)
async def post_dependent(member_id: UUID, body: DependentIn) -> DependentOut:
    async with session_scope() as s:
        repo = MemberRepo(s)
        dep = await add_dependent(
            repo,
            AddDependentCommand(
                member_id=member_id,
                relationship=body.relationship,
                first_name=body.first_name,
                last_name=body.last_name,
                dob=body.dob,
                gender=body.gender,
            ),
        )
        return DependentOut(
            id=dep.id,
            member_id=dep.member_id,
            relationship=dep.relationship,
            first_name=dep.first_name,
            last_name=dep.last_name,
            dob=dep.dob,
            gender=dep.gender,
        )
