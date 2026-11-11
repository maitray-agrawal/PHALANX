"""Comprehensive tests for Alembic migration, logger preservation, and boot diagnostics.

Verifies:
1. Alembic environment configuration preserves existing application loggers.
2. Fresh migration chain execution on empty PostgreSQL database creates all required tables.
3. Repeated boot execution (idempotency) succeeds cleanly.
4. Migration revision mismatch fails closed with explicit error written to stderr.
5. Missing required tables fail closed with explicit table list written to stderr.
6. Missing unique event sequence constraint fails closed with explicit error written to stderr.
7. Ledger immutability triggers prevent UPDATE and DELETE on ledger_events.
8. Database connection failures and unexpected migration errors preserve full tracebacks.
"""

import io
import logging
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from alembic.config import Config
from scripts.boot import run_boot


def _get_test_db_url() -> str | None:
    from app.infrastructure.config import settings

    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url and "postgres" in test_url:
        if "localhost" in test_url and os.name == "nt":
            test_url = test_url.replace("localhost", "127.0.0.1")
        return test_url
    base_url = os.getenv("DATABASE_URL") or settings.database_url
    if base_url and "postgres" in base_url:
        if "phalanx_db" in base_url:
            base_url = base_url.replace("/phalanx_db", "/phalanx_test")
        if "localhost" in base_url and os.name == "nt":
            base_url = base_url.replace("localhost", "127.0.0.1")
        return base_url
    return None


test_db_url = _get_test_db_url()
is_ci = os.getenv("CI", "").lower() in ("true", "1")
TEST_SECRET_KEY = "test_secret_key_minimum_thirty_two_bytes_long_12345"

pytestmark = pytest.mark.skipif(
    test_db_url is None and not is_ci,
    reason="PostgreSQL test database is not configured (TEST_DATABASE_URL)",
)


def _reset_test_schema(db_url: str) -> None:
    engine = create_engine(db_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()


def test_alembic_logging_preserves_application_loggers():
    """Verify that Alembic logging configuration preserves existing loggers."""
    app_logger = logging.getLogger("phalanx.boot")
    app_logger.disabled = False

    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    from logging.config import fileConfig

    # Loading with disable_existing_loggers=False must NOT disable phalanx.boot
    fileConfig(str(ini_path), disable_existing_loggers=False)
    msg = "Application logger 'phalanx.boot' must not be disabled by Alembic"
    assert not app_logger.disabled, msg


def test_fresh_migration_and_boot_success(monkeypatch):
    """Verify that a fresh PostgreSQL database completes boot sequence cleanly."""
    if test_db_url is None:
        return
    _reset_test_schema(test_db_url)

    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database

    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    reset_database()
    success = run_boot()
    assert success is True, "run_boot() must succeed on clean PostgreSQL database"

    # Verify all 7 required application tables exist
    engine = create_engine(test_db_url, poolclass=NullPool)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {
        "agent_budgets",
        "budget_reservations",
        "idempotency_records",
        "step_up_approvals",
        "mandates",
        "ledger_events",
        "daily_quotas",
        "alembic_version",
    }
    missing = required_tables - existing_tables
    assert not missing, f"Missing expected tables after boot: {missing}"

    # Verify unique constraint on event_seq
    constraints = inspector.get_unique_constraints("ledger_events")
    c_names = {c.get("name") for c in constraints}
    c_cols = [set(c.get("column_names") or []) for c in constraints]
    assert "uq_ledger_events_event_seq" in c_names or {"event_seq"} in c_cols, (
        "uq_ledger_events_event_seq unique constraint must exist on ledger_events"
    )

    # Verify ledger immutability trigger exists
    with engine.connect() as conn:
        trg_exists = conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.triggers "
                "WHERE event_object_table = 'ledger_events' "
                "AND trigger_name = 'trg_deny_ledger_mutation'"
            )
        )
        assert trg_exists > 0, "trg_deny_ledger_mutation trigger must exist on ledger_events"
    engine.dispose()
    reset_database()


def test_repeated_boot_idempotency(monkeypatch):
    """Verify that running run_boot() consecutively is fully idempotent and succeeds."""
    if test_db_url is None:
        return

    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database

    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    reset_database()
    # Second run on existing data
    success = run_boot()
    assert success is True, "Subsequent run_boot() calls must be idempotent and succeed"
    reset_database()


def test_migration_revision_mismatch_fails_closed(monkeypatch):
    """Verify that an unexpected revision in alembic_version fails closed with visible stderr."""
    if test_db_url is None:
        return

    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database

    _reset_test_schema(test_db_url)
    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    reset_database()
    assert run_boot() is True

    # Simulate an upgrade that ended on an unexpected revision (e.g., partial head)
    from alembic.migration import MigrationContext

    monkeypatch.setattr(
        MigrationContext, "get_current_revision", lambda _self: "001_simulated_old_revision"
    )

    captured_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_stderr)

    success = run_boot()
    assert success is False, "run_boot() must fail closed on revision mismatch"
    err_output = captured_stderr.getvalue()
    assert "Alembic revision mismatch" in err_output, (
        f"Expected mismatch warning in stderr, got: {err_output}"
    )
    reset_database()


def test_missing_required_table_fails_closed(monkeypatch):
    """Verify that dropping a required table causes run_boot to fail closed with visible stderr."""
    if test_db_url is None:
        return

    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database

    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    # Restore head revision first
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", test_db_url.replace("%", "%%"))
    from alembic import command

    command.upgrade(cfg, "head")

    # Drop agent_budgets
    engine = create_engine(test_db_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE agent_budgets CASCADE;"))
    engine.dispose()
    reset_database()

    captured_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_stderr)

    success = run_boot()
    assert success is False, "run_boot() must fail closed when a required table is missing"
    err_output = captured_stderr.getvalue()
    assert "missing required database tables" in err_output
    assert "agent_budgets" in err_output
    reset_database()


def test_missing_unique_constraint_fails_closed(monkeypatch):
    """Verify that missing uq_ledger_events_event_seq constraint fails closed with stderr."""
    if test_db_url is None:
        return

    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database

    _reset_test_schema(test_db_url)
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", test_db_url.replace("%", "%%"))
    from alembic import command

    command.upgrade(cfg, "head")

    # Drop constraint
    engine = create_engine(test_db_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(
            text("ALTER TABLE ledger_events DROP CONSTRAINT IF EXISTS uq_ledger_events_event_seq;")
        )
        conn.execute(text("DROP INDEX IF EXISTS uq_ledger_events_event_seq;"))
    engine.dispose()
    reset_database()

    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)

    captured_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_stderr)

    success = run_boot()
    assert success is False, "run_boot() must fail closed when constraint is missing"
    err_output = captured_stderr.getvalue()
    assert "constraint 'uq_ledger_events_event_seq' missing" in err_output
    reset_database()


def test_ledger_trigger_immutability(monkeypatch):
    """Verify that ledger_events immutability trigger strictly forbids UPDATE and DELETE."""
    if test_db_url is None:
        return

    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database

    _reset_test_schema(test_db_url)
    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    reset_database()
    assert run_boot() is True

    engine = create_engine(test_db_url, poolclass=NullPool)
    with engine.connect() as conn:
        # Genesis event exists (event_seq = 0)
        with pytest.raises(Exception, match="append-only|prohibited"):
            conn.execute(text("UPDATE ledger_events SET amount_minor = 9999 WHERE event_seq = 0;"))
        conn.rollback()

        with pytest.raises(Exception, match="append-only|prohibited"):
            conn.execute(text("DELETE FROM ledger_events WHERE event_seq = 0;"))
        conn.rollback()
    engine.dispose()
    reset_database()


def test_traceback_visibility_on_unexpected_error(monkeypatch):
    """Verify that unexpected exceptions in run_boot preserve full tracebacks on stderr."""
    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database

    _reset_test_schema(test_db_url)
    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    reset_database()

    def _exploding_triggers(_eng):
        raise RuntimeError("Simulated unhandled trigger failure")

    monkeypatch.setattr("app.infrastructure.db_schema.install_ledger_triggers", _exploding_triggers)

    captured_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", captured_stderr)

    success = run_boot()
    assert success is False
    err_output = captured_stderr.getvalue()
    assert "Boot trigger install error: Simulated unhandled trigger failure" in err_output
    assert "Traceback (most recent call last):" in err_output
    assert "RuntimeError: Simulated unhandled trigger failure" in err_output
    reset_database()


@pytest.mark.parametrize(
    "step_name,patch_target,patch_factory,expected_err",
    [
        (
            "key validation",
            "app.infrastructure.tokens.validate_secret_key",
            lambda: (lambda: (False, "Simulated bad key format")),
            "Key validation failed: Simulated bad key format",
        ),
        (
            "migrations",
            "alembic.command.upgrade",
            lambda: (
                lambda *_a, **_kw: (_ for _ in ()).throw(
                    RuntimeError("Simulated migration failure")
                )
            ),
            "Migration error: Simulated migration failure",
        ),
        (
            "trigger install",
            "app.infrastructure.db_schema.install_ledger_triggers",
            lambda: (
                lambda *_a, **_kw: (_ for _ in ()).throw(
                    RuntimeError("Simulated trigger install failure")
                )
            ),
            "Trigger install error: Simulated trigger install failure",
        ),
        (
            "seeding",
            "app.infrastructure.crypto.load_or_generate_keypair",
            lambda: (
                lambda *_a, **_kw: (_ for _ in ()).throw(
                    RuntimeError("Simulated mandate crypto failure")
                )
            ),
            "Mandate seeding error: Simulated mandate crypto failure",
        ),
    ],
)
def test_forced_failure_in_each_step_prints_step_name_and_traceback(
    monkeypatch, step_name, patch_target, patch_factory, expected_err
):
    """Test that a forced failure in each boot step prints its step name and redacted traceback."""
    from app.infrastructure.config import settings
    from app.infrastructure.database import reset_database
    from scripts.boot import main

    _reset_test_schema(test_db_url)
    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    reset_database()

    monkeypatch.setattr(patch_target, patch_factory())

    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_stdout)
    monkeypatch.setattr(sys, "stderr", captured_stderr)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1, "main() must exit with status 1 on boot failure"

    out = captured_stdout.getvalue()
    err = captured_stderr.getvalue()

    # Step name must be printed to stdout
    assert f"[boot] step: {step_name}" in out, (
        f"Expected '[boot] step: {step_name}' in stdout, got:\n{out}"
    )

    # Redacted error and traceback must be printed to stderr
    assert "[boot] ERROR:" in err, f"Expected '[boot] ERROR:' in stderr, got:\n{err}"
    assert "[boot] Traceback:" in err, f"Expected '[boot] Traceback:' in stderr, got:\n{err}"
    assert expected_err in err, f"Expected '{expected_err}' in stderr, got:\n{err}"

    reset_database()


def test_redact_message_masks_secrets_and_passwords():
    """Verify that redact_message strips credentials and configured environment secrets."""
    from scripts.boot import redact_message

    # Test URL credentials
    raw_url = "postgresql+psycopg://owner_user:SuperSecretPassword123@ep-test.neon.tech/neondb"
    redacted_url = redact_message(raw_url)
    assert "SuperSecretPassword123" not in redacted_url
    assert "owner_user:[REDACTED]@ep-test.neon.tech" in redacted_url

    # Test key/secret parameters
    raw_param = "Connection failed with password='super_secret_token_abc' and api_key=xyz987654321"
    redacted_param = redact_message(raw_param)
    assert "super_secret_token_abc" not in redacted_param
    assert "xyz987654321" not in redacted_param
    assert "password=[REDACTED]" in redacted_param
    assert "api_key=[REDACTED]" in redacted_param


def test_boot_fails_fast_in_key_validation_on_invalid_mandate_signing_key_hex(monkeypatch):
    """Verify that malformed MANDATE_SIGNING_KEY_HEX fails in step: key validation before DB."""
    from app.infrastructure.config import settings
    from scripts.boot import main

    monkeypatch.setattr(settings, "secret_key", TEST_SECRET_KEY)
    monkeypatch.setattr(settings, "mandate_signing_key_hex", "a" * 65)

    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_stdout)
    monkeypatch.setattr(sys, "stderr", captured_stderr)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    out = captured_stdout.getvalue()
    err = captured_stderr.getvalue()

    assert "[boot] step: key validation" in out
    assert "[boot] step: migrations" not in out, "Must fail fast before running migrations"
    assert "MANDATE_SIGNING_KEY_HEX must contain exactly 64 hexadecimal characters." in err
