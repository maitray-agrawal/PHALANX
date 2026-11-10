"""Unit tests for configuration validation and environment models."""

import pytest

from app.infrastructure.config import Settings


def test_neon_database_url_requires_sslmode() -> None:
    """Settings validator raises ValueError when neon.tech URL omits sslmode."""
    with pytest.raises(
        ValueError, match=r"DATABASE_URL targets Neon but is missing '\?sslmode=require'"
    ):
        Settings(
            database_url="postgresql+psycopg://user:pass@ep-cool-db.us-east-2.aws.neon.tech/neondb"
        )


def test_neon_database_url_accepts_sslmode_require() -> None:
    """Settings validator accepts neon.tech URL with sslmode=require."""
    url = "postgresql+psycopg://user:pass@ep-cool-db.us-east-2.aws.neon.tech/neondb?sslmode=require"
    s = Settings(database_url=url)
    assert "sslmode=require" in s.database_url


def test_non_neon_database_url_allowed_without_sslmode() -> None:
    """Settings validator does not require sslmode for local/internal databases."""
    url = "postgresql+psycopg://phalanx_app:localpass@localhost:5433/phalanx_db"
    s = Settings(database_url=url)
    assert s.database_url == url


def test_database_url_normalization() -> None:
    """Settings normalizes postgres:// and postgresql:// to postgresql+psycopg://."""
    s1 = Settings(database_url="postgres://user:pass@localhost:5432/db")
    assert s1.database_url.startswith("postgresql+psycopg://")

    s2 = Settings(database_url="postgresql://user:pass@localhost:5432/db")
    assert s2.database_url.startswith("postgresql+psycopg://")
