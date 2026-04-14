"""Repository — the only place that touches the DB for Member + Dependent."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.member import (
    Dependent,
    Member,
    Relationship,
    new_id,
    now_utc,
)


class MemberRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def find_by_card(self, tenant_id: UUID, card_number: str) -> Member | None:
        row = (
            await self.s.execute(
                text(
                    """
                    SELECT id, tenant_id, employer_id, payer_member_id, card_number,
                           first_name, last_name, dob, gender, ssn_last4, ssn_sha256,
                           ssn_ciphertext, address, version, created_at, updated_at
                    FROM members
                    WHERE tenant_id = :t AND card_number = :c
                    LIMIT 1
                    """
                ),
                {"t": str(tenant_id), "c": card_number},
            )
        ).first()
        return _row_to_member(row) if row else None

    async def find_by_id(self, member_id: UUID) -> Member | None:
        row = (
            await self.s.execute(
                text(
                    """
                    SELECT id, tenant_id, employer_id, payer_member_id, card_number,
                           first_name, last_name, dob, gender, ssn_last4, ssn_sha256,
                           ssn_ciphertext, address, version, created_at, updated_at
                    FROM members
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": str(member_id)},
            )
        ).first()
        return _row_to_member(row) if row else None

    async def insert(self, m: Member) -> None:
        await self.s.execute(
            text(
                """
                INSERT INTO members
                  (id, tenant_id, employer_id, payer_member_id, card_number,
                   first_name, last_name, dob, gender, ssn_last4, ssn_sha256,
                   ssn_ciphertext, address, version, created_at, updated_at)
                VALUES
                  (:id, :t, :e, :pmi, :cn, :fn, :ln, :dob, :gn, :s4, :sh,
                   :sc, CAST(:addr AS JSONB), :v, :cr, :up)
                """
            ),
            {
                "id": str(m.id),
                "t": str(m.tenant_id),
                "e": str(m.employer_id),
                "pmi": m.payer_member_id,
                "cn": m.card_number,
                "fn": m.first_name,
                "ln": m.last_name,
                "dob": m.dob,
                "gn": m.gender,
                "s4": m.ssn_last4,
                "sh": m.ssn_sha256,
                "sc": m.ssn_ciphertext,
                "addr": json.dumps(m.address) if m.address is not None else None,
                "v": m.version,
                "cr": m.created_at or now_utc(),
                "up": m.updated_at or now_utc(),
            },
        )

    async def update(self, m: Member) -> None:
        await self.s.execute(
            text(
                """
                UPDATE members SET
                  employer_id = :e,
                  payer_member_id = :pmi,
                  card_number = :cn,
                  first_name = :fn,
                  last_name = :ln,
                  dob = :dob,
                  gender = :gn,
                  ssn_last4 = :s4,
                  ssn_sha256 = :sh,
                  ssn_ciphertext = :sc,
                  address = CAST(:addr AS JSONB),
                  version = version + 1,
                  updated_at = :up
                WHERE id = :id
                """
            ),
            {
                "id": str(m.id),
                "e": str(m.employer_id),
                "pmi": m.payer_member_id,
                "cn": m.card_number,
                "fn": m.first_name,
                "ln": m.last_name,
                "dob": m.dob,
                "gn": m.gender,
                "s4": m.ssn_last4,
                "sh": m.ssn_sha256,
                "sc": m.ssn_ciphertext,
                "addr": json.dumps(m.address) if m.address is not None else None,
                "up": now_utc(),
            },
        )

    async def insert_dependent(self, d: Dependent) -> None:
        await self.s.execute(
            text(
                """
                INSERT INTO dependents
                  (id, member_id, relationship, first_name, last_name, dob, gender)
                VALUES
                  (:id, :m, :rel, :fn, :ln, :dob, :gn)
                """
            ),
            {
                "id": str(d.id),
                "m": str(d.member_id),
                "rel": d.relationship.value,
                "fn": d.first_name,
                "ln": d.last_name,
                "dob": d.dob,
                "gn": d.gender,
            },
        )

    async def list_dependents(self, member_id: UUID) -> list[Dependent]:
        rows = (
            await self.s.execute(
                text(
                    """
                    SELECT id, member_id, relationship, first_name, last_name, dob, gender
                    FROM dependents
                    WHERE member_id = :m
                    ORDER BY dob ASC
                    """
                ),
                {"m": str(member_id)},
            )
        ).all()
        return [
            Dependent(
                id=r.id,
                member_id=r.member_id,
                relationship=Relationship(r.relationship),
                first_name=r.first_name,
                last_name=r.last_name,
                dob=r.dob,
                gender=r.gender,
            )
            for r in rows
        ]


def _row_to_member(r: Any) -> Member:
    return Member(
        id=r.id,
        tenant_id=r.tenant_id,
        employer_id=r.employer_id,
        payer_member_id=r.payer_member_id,
        card_number=r.card_number,
        first_name=r.first_name,
        last_name=r.last_name,
        dob=r.dob,
        gender=r.gender,
        ssn_last4=r.ssn_last4,
        ssn_sha256=bytes(r.ssn_sha256) if r.ssn_sha256 else None,
        ssn_ciphertext=r.ssn_ciphertext,
        address=dict(r.address) if r.address else None,
        version=r.version,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )
