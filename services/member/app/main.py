from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from eligibility_common.app_factory import create_app
from eligibility_common.db import engine, session_scope
from eligibility_common.idempotency import IDEMPOTENCY_DDL
from eligibility_common.outbox import OUTBOX_DDL
from fastapi import FastAPI
from sqlalchemy import text

from app.interfaces.api import router
from app.settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    # ensure schema exists (migrations run separately via alembic in prod)
    async with engine().begin() as conn:
        await conn.execute(text(OUTBOX_DDL))
        await conn.execute(text(IDEMPOTENCY_DDL))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS members (
                  id UUID PRIMARY KEY,
                  tenant_id UUID NOT NULL,
                  employer_id UUID NOT NULL,
                  payer_member_id TEXT,
                  card_number TEXT UNIQUE,
                  first_name TEXT,
                  last_name TEXT,
                  dob DATE,
                  gender TEXT,
                  ssn_last4 TEXT,
                  ssn_sha256 BYTEA,
                  ssn_ciphertext TEXT,
                  address JSONB,
                  version BIGINT NOT NULL DEFAULT 1,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS members_tenant_card ON members (tenant_id, card_number);
                CREATE INDEX IF NOT EXISTS members_employer ON members (tenant_id, employer_id);

                CREATE TABLE IF NOT EXISTS dependents (
                  id UUID PRIMARY KEY,
                  member_id UUID NOT NULL REFERENCES members(id),
                  relationship TEXT NOT NULL,
                  first_name TEXT,
                  last_name TEXT,
                  dob DATE,
                  gender TEXT
                );
                CREATE INDEX IF NOT EXISTS dep_member ON dependents (member_id);
                """
            )
        )
    yield


async def _ping_db() -> None:
    async with session_scope() as s:
        await s.execute(text("SELECT 1"))


app = create_app(
    service_name=settings.service_name,
    lifespan=lifespan,
    readiness={"db": _ping_db},
)
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
