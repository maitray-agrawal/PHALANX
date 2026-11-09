"""Test Alembic migration progression from 001 and 002 to head on an empty PostgreSQL database."""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from alembic import command
from alembic.config import Config


def _get_test_db_url() -> str | None:
    from app.infrastructure.config import settings

    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url and "postgres" in test_url:
        return test_url
    base_url = os.getenv("DATABASE_URL") or settings.database_url
    if base_url and "postgres" in base_url:
        if "phalanx_db" in base_url:
            return base_url.replace("/phalanx_db", "/phalanx_test")
        return base_url
    return None


test_db_url = _get_test_db_url()
is_ci = os.getenv("CI", "").lower() in ("true", "1")

pytestmark = pytest.mark.skipif(
    test_db_url is None and not is_ci,
    reason="PostgreSQL test database is not configured (TEST_DATABASE_URL)",
)


def test_upgrade_from_001_and_002_to_head_on_empty_postgres():
    """Verify upgrade progression from 001 and 002 to head on empty PostgreSQL."""
    if test_db_url is None:
        if is_ci:
            pytest.fail("TEST_DATABASE_URL must be provided in CI environment")
        return

    engine = create_engine(test_db_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")

    try:
        # 1. Clean out the test database completely
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))

        ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", test_db_url.replace("%", "%%"))

        # 2. Upgrade to 001_initial_schema
        command.upgrade(alembic_cfg, "001_initial_schema")
        inspector = inspect(engine)
        tables_001 = set(inspector.get_table_names())
        assert "ledger_events" in tables_001
        assert "agent_budgets" in tables_001
        assert "mandates" not in tables_001

        # 3. Upgrade to 002_add_mandates_table
        command.upgrade(alembic_cfg, "002_add_mandates_table")
        inspector = inspect(engine)
        tables_002 = set(inspector.get_table_names())
        assert "mandates" in tables_002

        # 4. Upgrade to head (003_unique_event_seq)
        command.upgrade(alembic_cfg, "head")
        inspector = inspect(engine)
        tables_head = set(inspector.get_table_names())
        assert "mandates" in tables_head
        assert "ledger_events" in tables_head

        # Verify unique constraint uq_ledger_events_event_seq exists
        constraints = inspector.get_unique_constraints("ledger_events")
        constraint_names = {c.get("name") for c in constraints}
        constraint_cols = [set(c.get("column_names") or []) for c in constraints]
        has_constraint = (
            "uq_ledger_events_event_seq" in constraint_names or {"event_seq"} in constraint_cols
        )
        assert has_constraint, f"Expected unique constraint on event_seq, found: {constraints}"
    finally:
        engine.dispose()
