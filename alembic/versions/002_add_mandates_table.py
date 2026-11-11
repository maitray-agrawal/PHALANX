"""Add mandates table and unique event_seq index for PHALANX.

Revision ID: 002_add_mandates_table
Revises: 001_initial_schema
Create Date: 2026-11-07 07:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_mandates_table"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. mandates table
    op.create_table(
        "mandates",
        sa.Column("mandate_id", sa.String(64), primary_key=True),
        sa.Column("version", sa.BigInteger(), primary_key=True, server_default="1"),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("single_limit_minor", sa.BigInteger(), nullable=False),
        sa.Column("instant_threshold_minor", sa.BigInteger(), nullable=False),
        sa.Column("lifetime_budget_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("allowed_payees_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allowed_purposes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "allow_unregistered_payees", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "require_invoice_reference", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signed_payload", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mandates_agent_id", "mandates", ["agent_id"])

    # 2. ensure event_seq in ledger_events is unique across instances
    op.drop_index("idx_ledger_events_seq", table_name="ledger_events")
    op.create_index("idx_ledger_events_seq", "ledger_events", ["event_seq"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_ledger_events_seq", table_name="ledger_events")
    op.create_index("idx_ledger_events_seq", "ledger_events", ["event_seq"], unique=False)
    op.drop_index("ix_mandates_agent_id", table_name="mandates")
    op.drop_table("mandates")
