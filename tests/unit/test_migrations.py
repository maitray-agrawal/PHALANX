"""Unit test for Alembic migrations forward and rollback on a clean database (Manual 56.12)."""

from pathlib import Path

from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config


def test_alembic_migrations_forward_and_rollback() -> None:
    """Verify that Alembic migrations upgrade to head and downgrade to base cleanly."""
    test_db_path = Path("test_migrations_temp.db")
    if test_db_path.exists():
        test_db_path.unlink()

    db_url = f"sqlite:///{test_db_path.resolve()}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    engine = create_engine(db_url)

    try:
        # 1. Initially empty database
        inspector = inspect(engine)
        initial_tables = set(inspector.get_table_names())
        assert "agent_budgets" not in initial_tables
        assert "ledger_events" not in initial_tables

        # 2. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(engine)
        tables_after_upgrade = set(inspector.get_table_names())
        expected_tables = {
            "agent_budgets",
            "budget_reservations",
            "idempotency_records",
            "step_up_approvals",
            "ledger_events",
            "alembic_version",
        }
        for table in expected_tables:
            assert table in tables_after_upgrade, f"Expected table '{table}' missing after upgrade"

        # 3. Downgrade back to base
        command.downgrade(alembic_cfg, "base")

        inspector = inspect(engine)
        tables_after_downgrade = set(inspector.get_table_names())
        for table in expected_tables - {"alembic_version"}:
            assert table not in tables_after_downgrade, (
                f"Table '{table}' not dropped after downgrade"
            )

    finally:
        engine.dispose()
        if test_db_path.exists():
            test_db_path.unlink()
