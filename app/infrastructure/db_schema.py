"""Database schema setup and trigger immutability enforcement."""

from sqlalchemy import Engine, text

from app.infrastructure.models import Base


def create_schema(engine: Engine) -> None:
    """Create all relational tables and immutability triggers."""
    Base.metadata.create_all(engine)
    install_ledger_triggers(engine)


def install_ledger_triggers(engine: Engine) -> None:
    """Install database-level triggers strictly preventing UPDATE and DELETE on ledger_events."""
    dialect_name = engine.dialect.name

    with engine.begin() as conn:
        if dialect_name == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_no_update_ledger
                    BEFORE UPDATE ON ledger_events
                    BEGIN
                        SELECT RAISE(ABORT, 'ledger_events is append-only: updates are strictly prohibited');
                    END;
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_no_delete_ledger
                    BEFORE DELETE ON ledger_events
                    BEGIN
                        SELECT RAISE(ABORT, 'ledger_events is append-only: deletes are strictly prohibited');
                    END;
                    """
                )
            )
        elif dialect_name in ("postgresql", "postgres"):
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION deny_ledger_mutation()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        RAISE EXCEPTION 'ledger_events is append-only: updates and deletes are strictly prohibited';
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DROP TRIGGER IF EXISTS trg_deny_ledger_mutation ON ledger_events;
                    CREATE TRIGGER trg_deny_ledger_mutation
                    BEFORE UPDATE OR DELETE ON ledger_events
                    FOR EACH ROW EXECUTE FUNCTION deny_ledger_mutation();
                    """
                )
            )
