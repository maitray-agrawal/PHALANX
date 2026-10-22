"""Initial schema creation for PHALANX.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-22 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_budgets
    op.create_table(
        "agent_budgets",
        sa.Column("agent_id", sa.String(128), primary_key=True),
        sa.Column("mandate_id", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("allocated_minor", sa.BigInteger(), nullable=False),
        sa.Column("spent_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "spent_minor + reserved_minor <= allocated_minor",
            name="chk_budget_spent_plus_reserved_within_allocated",
        ),
        sa.CheckConstraint("spent_minor >= 0", name="chk_spent_non_negative"),
        sa.CheckConstraint("reserved_minor >= 0", name="chk_reserved_non_negative"),
        sa.CheckConstraint("allocated_minor >= 0", name="chk_allocated_non_negative"),
    )

    # 2. budget_reservations
    op.create_table(
        "budget_reservations",
        sa.Column("reservation_id", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), unique=True, nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="chk_reservation_positive"),
    )
    op.create_index("ix_budget_reservations_agent_id", "budget_reservations", ["agent_id"])

    # 3. idempotency_records
    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("intent_digest", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("response_payload", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_idempotency_records_agent_id", "idempotency_records", ["agent_id"])

    # 4. step_up_approvals
    op.create_table(
        "step_up_approvals",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("expected_digest", sa.String(64), nullable=False),
        sa.Column("intent_payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("approver_id", sa.String(128), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_step_up_approvals_idempotency_key", "step_up_approvals", ["idempotency_key"])

    # 5. ledger_events
    op.create_table(
        "ledger_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("event_seq", sa.BigInteger(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("recipient_id", sa.String(128), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_ledger_events_seq", "ledger_events", ["event_seq"])
    op.create_index("ix_ledger_events_agent_id", "ledger_events", ["agent_id"])


def downgrade() -> None:
    op.drop_table("ledger_events")
    op.drop_table("step_up_approvals")
    op.drop_table("idempotency_records")
    op.drop_table("budget_reservations")
    op.drop_table("agent_budgets")
