"""add daily quotas table

Revision ID: 004_daily_quotas
Revises: 003_unique_event_seq
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_daily_quotas"
down_revision: str | None = "003_unique_event_seq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_quotas",
        sa.Column("quota_key", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_quotas")
