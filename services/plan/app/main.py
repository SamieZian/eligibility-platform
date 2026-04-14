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
    async with engine().begin() as conn:
        await conn.execute(text(OUTBOX_DDL))
        await conn.execute(text(IDEMPOTENCY_DDL))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS plans (
                  id UUID PRIMARY KEY,
                  plan_code TEXT NOT NULL UNIQUE,
                  name TEXT NOT NULL,
                  type TEXT NOT NULL,
                  metal_level TEXT,
                  attributes JSONB,
                  version BIGINT NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS plans_type ON plans (type);
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
