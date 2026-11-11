"""Reset PHALANX demo state to canonical defaults.

Restores:
1. Agent budget: allocated $25,000.00 (2,500,000 minor), spent $0.00, reserved $0.00.
2. Demo mandate: mandate_default_sandbox ($25k lifetime, $500 instant, $5k single).
3. Supervisor approvals: exactly one clean PENDING step-up request (req_stepup_1001, $1,200.00).
4. Clears active reservations and idempotency records for clean demo execution.

Database URL is resolved strictly from the environment; no hardcoded credentials or passwords.
"""

import json
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.services import compute_intent_digest
from app.domain.canonical_json import canonical_json_bytes
from app.infrastructure.config import settings
from app.infrastructure.crypto import load_or_generate_keypair, sign_bytes
from app.infrastructure.database import get_engine
from app.infrastructure.models import (
    AgentBudgetModel,
    ApprovalStatus,
    BudgetReservationModel,
    IdempotencyModel,
    MandateModel,
    StepUpApprovalModel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phalanx.reset_demo")


def reset_demo_state() -> bool:
    """Restore clean demo state in the configured database."""
    logger.info("Resetting PHALANX demo state to canonical configuration...")
    engine = get_engine()

    fixed_valid_from = datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)
    fixed_valid_until = datetime(2027, 3, 31, 23, 59, 59, tzinfo=UTC)
    now_utc = datetime.now(UTC)

    # 1. Ed25519 Authority Keypair
    priv_key, pub_key, key_id = load_or_generate_keypair(
        key_hex=settings.mandate_signing_key_hex,
        key_file_path=settings.mandate_signing_key_file,
    )

    with Session(engine) as session, session.begin():
        # 2. Reset Budget Reservations & Idempotency Cache for demo agent
        session.execute(
            delete(BudgetReservationModel).where(BudgetReservationModel.agent_id == "agent-auto-1")
        )
        session.execute(delete(IdempotencyModel).where(IdempotencyModel.agent_id == "agent-auto-1"))

        # 3. Reset Agent Budget ($25,000.00 allocated, 0 spent, 0 reserved)
        budget = session.scalar(
            select(AgentBudgetModel).where(AgentBudgetModel.agent_id == "agent-auto-1")
        )
        if not budget:
            budget = AgentBudgetModel(
                agent_id="agent-auto-1",
                mandate_id="mandate_default_sandbox",
                currency="USD",
                allocated_minor=2_500_000,
                spent_minor=0,
                reserved_minor=0,
                created_at_utc=now_utc,
                updated_at_utc=now_utc,
            )
            session.add(budget)
        else:
            budget.allocated_minor = 2_500_000
            budget.spent_minor = 0
            budget.reserved_minor = 0
            budget.mandate_id = "mandate_default_sandbox"
            budget.currency = "USD"
            budget.updated_at_utc = now_utc

        # 4. Reset Demo Mandate
        session.execute(
            delete(MandateModel).where(MandateModel.mandate_id == "mandate_default_sandbox")
        )
        mandate_payload = {
            "mandate_id": "mandate_default_sandbox",
            "version": 1,
            "principal_id": "principal_treasury",
            "agent_id": "agent-auto-1",
            "single_limit_minor": 500_000,
            "instant_threshold_minor": 50_000,
            "lifetime_budget_minor": 2_500_000,
            "currency": "USD",
            "allowed_payees": [],
            "allow_unregistered_payees": True,
            "allowed_purposes": [],
            "valid_from_utc": fixed_valid_from.isoformat(),
            "valid_until_utc": fixed_valid_until.isoformat(),
            "status": "ACTIVE",
            "key_id": key_id,
        }
        signed_bytes = canonical_json_bytes(mandate_payload)
        sig = sign_bytes(priv_key, signed_bytes)
        mandate_row = MandateModel(
            mandate_id="mandate_default_sandbox",
            version=1,
            principal_id="principal_treasury",
            agent_id="agent-auto-1",
            single_limit_minor=500_000,
            instant_threshold_minor=50_000,
            lifetime_budget_minor=2_500_000,
            currency="USD",
            allowed_payees_json="[]",
            allowed_purposes_json="[]",
            allow_unregistered_payees=True,
            require_invoice_reference=False,
            valid_from_utc=fixed_valid_from,
            valid_until_utc=fixed_valid_until,
            status="ACTIVE",
            key_id=key_id,
            signature=sig,
            signed_payload=signed_bytes.decode("utf-8"),
            created_at_utc=fixed_valid_from,
            updated_at_utc=fixed_valid_from,
        )
        session.add(mandate_row)

        # 5. Reset Step-Up Approvals: remove all and seed canonical req_stepup_1001
        session.execute(delete(StepUpApprovalModel))
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
            expires_at_utc=now_utc + timedelta(hours=24),
            decision=None,
            approver_id=None,
            created_at_utc=now_utc,
            updated_at_utc=now_utc,
        )
        session.add(stepup)

    logger.info("Demo state successfully reset to canonical defaults.")
    return True


if __name__ == "__main__":
    success = reset_demo_state()
    sys.exit(0 if success else 1)
