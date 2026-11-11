"""Tests for deployment configuration, URL normalization, and clean database initialization."""

import os
import tempfile

from sqlalchemy import text

import app.infrastructure.database as db_mod
from app.infrastructure.config import Settings
from app.infrastructure.database import check_database_readiness, get_engine, get_session_factory
from scripts.boot import run_boot


def test_database_url_normalization_postgres() -> None:
    """Verify legacy postgres:// and generic postgresql:// are normalized to postgresql+psycopg://."""
    s1 = Settings(database_url="postgres://user:pass@render-db.internal:5432/phalanx_db")
    assert s1.database_url.startswith("postgresql+psycopg://")
    assert "user:pass@render-db.internal:5432/phalanx_db" in s1.database_url

    s2 = Settings(database_url="postgresql://user:pass@neon.tech:5432/phalanx_db?sslmode=require")
    assert s2.database_url.startswith("postgresql+psycopg://")
    assert "user:pass@neon.tech:5432/phalanx_db?sslmode=require" in s2.database_url

    s3 = Settings(database_url="sqlite:///./test.db")
    assert s3.database_url == "sqlite:///./test.db"


def test_sqlite_engine_connect_args_compatible() -> None:
    """Verify SQLite database engine creates connections without connect_timeout TypeErrors."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"

    try:
        # Temporarily set settings database_url
        orig_engine = db_mod._engine
        orig_session_factory = db_mod._session_factory
        db_mod._engine = None
        db_mod._session_factory = None
        orig_url = db_mod.settings.database_url
        db_mod.settings.database_url = db_url

        try:
            engine = get_engine()
            with engine.connect() as conn:
                res = conn.execute(text("SELECT 1")).scalar()
                assert res == 1

            is_ready, msg = check_database_readiness()
            assert is_ready is True
            assert msg == "connected"

            sf = get_session_factory()
            assert sf is not None
            with sf() as session:
                val = session.execute(text("SELECT 42")).scalar()
                assert val == 42
        finally:
            db_mod.settings.database_url = orig_url
            db_mod._engine = orig_engine
            db_mod._session_factory = orig_session_factory
            engine.dispose()
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_clean_database_boot_script() -> None:
    """Verify idempotent boot script completes successfully on a clean database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_url = f"sqlite:///{path}"

    try:
        orig_engine = db_mod._engine
        orig_session_factory = db_mod._session_factory
        db_mod._engine = None
        db_mod._session_factory = None
        orig_url = db_mod.settings.database_url
        db_mod.settings.database_url = db_url

        try:
            # First run: applies schema and seeds data
            boot_ok = run_boot()
            assert boot_ok is True

            # Verify schema was actually installed
            engine = db_mod.get_engine()
            with engine.connect() as conn:
                tables = (
                    conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                    .scalars()
                    .all()
                )
                assert "agent_budgets" in tables
                assert "ledger_events" in tables
                assert "step_up_approvals" in tables

            # Second run: idempotent skip
            boot_ok_repeat = run_boot()
            assert boot_ok_repeat is True
            test_engine = db_mod.get_engine()
        finally:
            if "test_engine" in locals() and test_engine is not None:
                test_engine.dispose()
            db_mod.settings.database_url = orig_url
            db_mod._engine = orig_engine
            db_mod._session_factory = orig_session_factory
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except PermissionError:
            pass


def test_postgres_engine_neon_tuning_and_pooler() -> None:
    """Verify engine applies pool_pre_ping=True, pool_recycle<=240, connect_timeout 10-15s."""
    orig_engine = db_mod._engine
    orig_session_factory = db_mod._session_factory
    orig_url = db_mod.settings.database_url

    try:
        # 1. Standard / Direct PostgreSQL connection
        db_mod._engine = None
        direct_url = "postgresql+psycopg://user:pass@ep-direct-12345.us-east-2.aws.neon.tech/phalanx_db?sslmode=require"
        db_mod.settings.database_url = direct_url
        engine_direct = db_mod.get_engine()
        assert engine_direct.pool._pre_ping is True
        assert engine_direct.pool._recycle <= 240
        connect_args_direct = db_mod.get_connection_args(direct_url)
        assert connect_args_direct.get("connect_timeout") in (10, 11, 12, 13, 14, 15)
        assert "prepare_threshold" not in connect_args_direct

        # 2. Pooled connection string (PgBouncer / -pooler)
        db_mod._engine = None
        pooled_url = "postgresql+psycopg://user:pass@ep-direct-12345-pooler.us-east-2.aws.neon.tech/phalanx_db?sslmode=require"
        db_mod.settings.database_url = pooled_url
        engine_pooled = db_mod.get_engine()
        assert engine_pooled.pool._pre_ping is True
        assert engine_pooled.pool._recycle <= 240
        connect_args_pooled = db_mod.get_connection_args(pooled_url)
        assert connect_args_pooled.get("connect_timeout") in (10, 11, 12, 13, 14, 15)
        assert connect_args_pooled.get("prepare_threshold") is None
    finally:
        db_mod._engine = orig_engine
        db_mod._session_factory = orig_session_factory
        db_mod.settings.database_url = orig_url
