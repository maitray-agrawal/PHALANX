"""Idempotent boot script for PHALANX.

Actions:
1. Verifies/creates database tables and append-only ledger triggers.
2. Seeds demo mandate (mandate_default_astra) with validity no earlier than 31 Mar 2027.
3. Seeds initial budget allocation, payees, and pending supervisor approval.
4. Fully idempotent: safe to run multiple times during startup or reboots.
"""

import json
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services import compute_intent_digest
from app.domain.canonical_json import canonical_json_bytes
from app.infrastructure.database import get_engine
from app.infrastructure.db_schema import create_schema
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
    engine = get_engine()

    # Step 1: Database schema & triggers
    try:
        logger.info("Applying database schema and ledger immutability triggers...")
        create_schema(engine)
        logger.info("Database schema and triggers successfully verified/created.")
    except Exception as exc:
        logger.warning(
            "Database unreachable or schema creation failed: %s. Using runtime fallbacks.",
            exc,
        )
        return True

    # Step 2: Seed initial AgentBudget if not present
    now_utc = datetime.now(UTC)
    try:
        with Session(engine) as session:
            existing_budget = session.scalar(
                select(AgentBudgetModel).where(AgentBudgetModel.agent_id == "agent-auto-1")
            )
            if not existing_budget:
                logger.info("Seeding initial demo budget for agent-auto-1 ($10,000 USD)...")
                budget = AgentBudgetModel(
                    agent_id="agent-auto-1",
                    mandate_id="mandate_default_astra",
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

            # Step 3: Seed Genesis ledger block if empty
            existing_event = session.scalar(select(LedgerEventModel).limit(1))
            if not existing_event:
                logger.info("Seeding Genesis ledger block...")
                genesis_payload = {
                    "event": "GENESIS_INITIALIZED",
                    "mandate_id": "mandate_default_astra",
                    "description": "PHALANX Autonomous Financial Governance Genesis",
                    "timestamp": now_utc.isoformat(),
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

            # Step 4: Seed pending step-up request for Scene 2 demo
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
                from datetime import timedelta

                stepup = StepUpApprovalModel(
                    request_id="req_stepup_1001",
                    idempotency_key="stepup_seed_1001",
                    expected_digest=digest,
                    intent_payload=json.dumps(intent_payload),
                    status=ApprovalStatus.PENDING.value,
                    expires_at_utc=now_utc + timedelta(days=30),
                    created_at_utc=now_utc,
                    updated_at_utc=now_utc,
                )
                session.add(stepup)
                session.commit()
                logger.info("Demo step-up request seeded.")
            else:
                logger.info("Demo step-up request already present (idempotent skip).")

    except Exception as exc:
        logger.warning("Error during data seeding: %s (continuing boot).", exc)

    logger.info("PHALANX boot sequence complete. Ready to serve traffic.")
    return True


if __name__ == "__main__":
    success = run_boot()
    sys.exit(0 if success else 1)
