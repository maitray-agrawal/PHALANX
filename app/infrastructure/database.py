"""Database connection management and health checks."""

from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.config import settings

_engine: Engine | None = None
_session_factory: Any | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        connect_args = (
            {"connect_timeout": 3} if "sqlite" not in settings.database_url else {"timeout": 3}
        )
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> Any:
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.orm import sessionmaker

        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


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
