"""Database connection management and health checks."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.config import settings

_engine: Engine | None = None
_session_factory: Any | None = None


def get_connection_args(db_url: str) -> dict[str, Any]:
    """Return dialect-specific connection arguments for PostgreSQL/Neon or SQLite."""
    if "sqlite" in db_url:
        return {"timeout": 15, "check_same_thread": False}
    connect_args: dict[str, Any] = {"connect_timeout": 10}
    if "-pooler" in db_url or "pooler" in db_url:
        connect_args["prepare_threshold"] = None
    return connect_args


def get_engine() -> Engine:
    """Return single managed SQLAlchemy engine with dialect-specific connection arguments."""
    global _engine
    if _engine is None:
        import os

        db_url = settings.database_url
        if os.name == "nt" and "localhost" in db_url:
            db_url = db_url.replace("localhost", "127.0.0.1")

        connect_args = get_connection_args(db_url)
        if "sqlite" in db_url:
            _engine = create_engine(
                db_url,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
        else:
            # PostgreSQL / psycopg dialect args
            _engine = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                pool_recycle=240,
                connect_args=connect_args,
            )
    return _engine


def get_session_factory() -> Any:
    """Return managed sessionmaker bound to the singleton engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


def get_db_session() -> Generator[Session, None, None]:
    """Provide a request-scoped database session with automatic cleanup and rollback on error."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_database() -> None:
    """Dispose the active engine and clear session factory singletons."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _session_factory = None


def check_database_readiness() -> tuple[bool, str]:
    """Execute 'SELECT 1' to verify database connectivity.

    Returns:
        tuple[bool, str]: (is_ready, details_message)
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "connected"
    except SQLAlchemyError as exc:
        return False, f"database unreachable: {exc.__class__.__name__}"
    except Exception as exc:
        return False, f"connection failed: {str(exc)}"
