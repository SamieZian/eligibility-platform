from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.application.commands import add_dependent, upsert_member
from app.domain.member import (
    AddDependentCommand,
    Dependent,
    Member,
    Relationship,
    UpsertMemberCommand,
)


class FakeRepo:
    def __init__(self) -> None:
        self.by_id: dict[UUID, Member] = {}
        self.by_card: dict[tuple[UUID, str], Member] = {}
        self.dependents: list[Dependent] = []
        self.insert_calls = 0
        self.update_calls = 0

    async def find_by_card(self, tenant_id: UUID, card_number: str) -> Member | None:
        return self.by_card.get((tenant_id, card_number))

    async def find_by_id(self, member_id: UUID) -> Member | None:
        return self.by_id.get(member_id)

    async def insert(self, m: Member) -> None:
        self.insert_calls += 1
        self.by_id[m.id] = m
        if m.card_number:
            self.by_card[(m.tenant_id, m.card_number)] = m

    async def update(self, m: Member) -> None:
        self.update_calls += 1
        self.by_id[m.id] = m
        if m.card_number:
            self.by_card[(m.tenant_id, m.card_number)] = m

    async def insert_dependent(self, d: Dependent) -> None:
        self.dependents.append(d)


def _cmd(**kw):
    base = dict(
        tenant_id=uuid4(),
        employer_id=uuid4(),
        first_name="Jane",
        last_name="Doe",
        dob=date(1990, 5, 3),
        card_number="CARD-123",
        ssn="123-45-6789",
    )
    base.update(kw)
    return UpsertMemberCommand(**base)


@pytest.mark.asyncio
async def test_upsert_creates_new_when_not_found() -> None:
    repo = FakeRepo()
    cmd = _cmd()
    m = await upsert_member(None, repo, cmd)
    assert repo.insert_calls == 1
    assert repo.update_calls == 0
    assert m.version == 1
    assert m.ssn_last4 == "6789"
    assert m.ssn_ciphertext is not None
    assert m.ssn_sha256 is not None
    # Ensure full SSN is NOT stored verbatim in ciphertext
    assert "123456789" not in (m.ssn_ciphertext or "")


@pytest.mark.asyncio
async def test_upsert_updates_when_card_matches() -> None:
    repo = FakeRepo()
    tenant = uuid4()
    employer = uuid4()
    first = await upsert_member(
        None,
        repo,
        UpsertMemberCommand(
            tenant_id=tenant,
            employer_id=employer,
            first_name="Jane",
            last_name="Doe",
            dob=date(1990, 5, 3),
            card_number="CARD-XYZ",
        ),
    )
    second = await upsert_member(
        None,
        repo,
        UpsertMemberCommand(
            tenant_id=tenant,
            employer_id=employer,
            first_name="Jane",
            last_name="Smith",  # last name changed (married)
            dob=date(1990, 5, 3),
            card_number="CARD-XYZ",
        ),
    )
    assert first.id == second.id
    assert repo.insert_calls == 1
    assert repo.update_calls == 1
    assert second.last_name == "Smith"
    assert second.version == 2


@pytest.mark.asyncio
async def test_upsert_encrypts_ssn_with_kms_stub() -> None:
    # Sanity: ssn_ciphertext is present and base64-ish dotted triple
    repo = FakeRepo()
    m = await upsert_member(None, repo, _cmd(ssn="987654321"))
    assert m.ssn_last4 == "4321"
    assert m.ssn_ciphertext and m.ssn_ciphertext.count(".") == 2


@pytest.mark.asyncio
async def test_add_dependent_links_to_parent() -> None:
    repo = FakeRepo()
    parent = await upsert_member(None, repo, _cmd())
    dep = await add_dependent(
        repo,
        AddDependentCommand(
            member_id=parent.id,
            relationship=Relationship.CHILD,
            first_name="Kid",
            last_name="Doe",
            dob=date(2020, 1, 1),
        ),
    )
    assert dep.member_id == parent.id
    assert len(repo.dependents) == 1
    assert repo.dependents[0].first_name == "Kid"


@pytest.mark.asyncio
async def test_add_dependent_raises_when_parent_missing() -> None:
    from eligibility_common.errors import NotFoundError

    repo = FakeRepo()
    with pytest.raises(NotFoundError):
        await add_dependent(
            repo,
            AddDependentCommand(
                member_id=uuid4(),
                relationship=Relationship.SPOUSE,
                first_name="X",
                last_name="Y",
                dob=date(1985, 1, 1),
            ),
        )
