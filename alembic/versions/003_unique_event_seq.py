"""Add unique event_seq constraint for ledger_events.

Revision ID: 003_unique_event_seq
Revises: 002_add_mandates_table
Create Date: 2026-11-07 10:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_unique_event_seq"
down_revision: str | None = "002_add_mandates_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table("ledger_events", schema=None) as batch_op:
        batch_op.drop_index("idx_ledger_events_seq")
        batch_op.create_unique_constraint("uq_ledger_events_event_seq", ["event_seq"])


def downgrade() -> None:
    with op.batch_alter_table("ledger_events", schema=None) as batch_op:
        batch_op.drop_constraint("uq_ledger_events_event_seq", type_="unique")
        batch_op.create_index("idx_ledger_events_seq", ["event_seq"], unique=True)
