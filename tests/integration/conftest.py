"""Integration test fixtures — spin a real Postgres via testcontainers.

Skips cleanly if Docker or testcontainers isn't available (so CI can still run
the unit suite without docker).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "libs" / "python-common" / "src"))
sys.path.insert(0, str(ROOT / "libs" / "x12-834" / "src"))
sys.path.insert(0, str(ROOT / "services" / "atlas"))


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Postgres URL for tests — spins a real container."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    pg = PostgresContainer("postgres:15-alpine")
    pg.start()
    try:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")
        os.environ["DATABASE_URL"] = url
        yield url
    finally:
        pg.stop()
