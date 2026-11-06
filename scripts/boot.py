"""Idempotent boot script for PHALANX.

Actions:
1. Verifies/creates database tables and append-only ledger triggers.
2. Seeds demo mandate (mandate_default_sandbox) with validity no earlier than 31 Mar 2027.
3. Seeds initial budget allocation, payees, and pending supervisor approval.
4. Fully idempotent: safe to run multiple times during startup or reboots.
"""

import json
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services import compute_intent_digest
from app.domain.canonical_json import canonical_json_bytes
from app.infrastructure.database import get_engine
from app.infrastructure.models import (
    AgentBudgetModel,
    ApprovalStatus,
    LedgerEventModel,
    StepUpApprovalModel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phalanx.boot")


def run_boot() -> bool:
    """Run idempotent migrations and seed data."""
    logger.info("Starting PHALANX idempotent boot sequence...")

    # Step 0: Validate runtime secret configuration outside test environment
    from app.infrastructure.tokens import validate_secret_key

    is_key_valid, key_error = validate_secret_key()
    if not is_key_valid:
        logger.error("Boot aborted: %s", key_error)
        return False

    engine = get_engine()

    # Step 1: Database connectivity verification & schema migrations via Alembic
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as db_err:
        logger.error("Boot aborted: database connection failure: %s", db_err)
        return False

    try:
        from pathlib import Path

        from alembic import command
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from app.infrastructure.db_schema import install_ledger_triggers

        ini_candidates = [
            Path("alembic.ini"),
            Path(__file__).resolve().parent.parent / "alembic.ini",
            Path("/app/alembic.ini"),
        ]
        ini_path = next((p for p in ini_candidates if p.exists()), None)
        if not ini_path:
            logger.error("Boot aborted: alembic.ini configuration file not found")
            return False

        logger.info("Applying database migrations via Alembic (%s)...", ini_path)
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
        alembic_cfg.attributes["connection"] = engine
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations successfully applied to head.")

        # Verify the migration revision matches the declarative models
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()
        with engine.connect() as conn:
            m_context = MigrationContext.configure(conn)
            current_rev = m_context.get_current_revision()

        if current_rev != head_rev:
            logger.error(
                "Boot aborted: Alembic revision mismatch (current db: %s, head: %s)",
                current_rev,
                head_rev,
            )
            return False
        logger.info("Verified database revision '%s' matches migration head.", current_rev)

        install_ledger_triggers(engine)
        logger.info("Database schema and append-only triggers successfully verified/created.")
    except Exception as exc:
        logger.error("Boot aborted: migration or schema initialization failure: %s", exc)
        return False

    # Step 2: Seed initial AgentBudget if missing
    now_utc = datetime.now(UTC)
    valid_until_mar_2027 = max(
        now_utc + timedelta(days=365),
        datetime(2027, 3, 31, 23, 59, 59, tzinfo=UTC),
    )
    try:
        with Session(engine) as session:
            existing_budget = session.scalar(
                select(AgentBudgetModel).where(AgentBudgetModel.agent_id == "agent-auto-1")
            )
            if not existing_budget:
                logger.info("Seeding initial demo budget for agent-auto-1 ($10,000 USD)...")
                budget = AgentBudgetModel(
                    agent_id="agent-auto-1",
                    mandate_id="mandate_default_sandbox",
                    currency="USD",
                    allocated_minor=1_000_000,
                    spent_minor=0,
                    reserved_minor=0,
                    created_at_utc=now_utc,
                    updated_at_utc=now_utc,
                )
                session.add(budget)
                session.commit()
                logger.info("Initial demo budget created.")
            else:
                logger.info("Demo budget for agent-auto-1 already exists (idempotent skip).")

            # Step 3: Seed Genesis ledger block if missing
            existing_event = session.scalar(select(LedgerEventModel).limit(1))
            if not existing_event:
                logger.info("Seeding Genesis ledger block...")
                genesis_payload = {
                    "event": "GENESIS_INITIALIZED",
                    "mandate_id": "mandate_default_sandbox",
                    "description": "PHALANX Autonomous Financial Governance Genesis",
                    "timestamp": now_utc.isoformat(),
                    "valid_until": valid_until_mar_2027.isoformat(),
                }
                genesis_bytes = canonical_json_bytes(genesis_payload)
                import hashlib

                genesis_hash = hashlib.sha256(b"0" * 64 + genesis_bytes).hexdigest()

                genesis_event = LedgerEventModel(
                    event_id="evt_0000000000000000",
                    event_seq=0,
                    prev_hash="0" * 64,
                    event_hash=genesis_hash,
                    event_type="SYSTEM_GENESIS",
                    agent_id="system-root",
                    recipient_id="system-root",
                    amount_minor=0,
                    currency="USD",
                    payload_json=json.dumps(genesis_payload),
                    recorded_at_utc=now_utc,
                )
                session.add(genesis_event)
                session.commit()
                logger.info("Genesis ledger block established.")
            else:
                logger.info("Ledger already initialized (idempotent skip).")

            # Step 4: Seed pending step-up request for Scene 2 demo if missing
            existing_stepup = session.scalar(
                select(StepUpApprovalModel).where(
                    StepUpApprovalModel.request_id == "req_stepup_1001"
                )
            )
            if not existing_stepup:
                logger.info("Seeding human supervisor step-up approval for Scene 2 demo...")
                intent_payload = {
                    "agent_id": "agent-auto-1",
                    "recipient_id": "vendor-paypal-sandbox-1",
                    "amount_minor": 120000,
                    "currency": "USD",
                    "purpose": "Equipment invoice review",
                    "idempotency_key": "stepup_seed_1001",
                }
                digest = compute_intent_digest(
                    agent_id="agent-auto-1",
                    recipient_id="vendor-paypal-sandbox-1",
                    amount_minor=120000,
                    currency="USD",
                    purpose="Equipment invoice review",
                    idempotency_key="stepup_seed_1001",
                )

                stepup = StepUpApprovalModel(
                    request_id="req_stepup_1001",
                    idempotency_key="stepup_seed_1001",
                    expected_digest=digest,
                    intent_payload=json.dumps(intent_payload),
                    status=ApprovalStatus.PENDING.value,
                    expires_at_utc=valid_until_mar_2027,
                    created_at_utc=now_utc,
                    updated_at_utc=now_utc,
                )
                session.add(stepup)
                session.commit()
                logger.info("Demo step-up request seeded.")
            else:
                logger.info("Demo step-up request already present (idempotent skip).")

    except Exception as exc:
        logger.error("Boot aborted: error during data seeding: %s", exc)
        return False

    logger.info("PHALANX boot sequence complete. Ready to serve traffic.")
    return True


if __name__ == "__main__":
    success = run_boot()
    sys.exit(0 if success else 1)
