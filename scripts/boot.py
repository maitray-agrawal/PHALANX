"""Idempotent boot script for PHALANX.

Actions:
1. Verifies/creates database tables and append-only ledger triggers.
2. Seeds demo mandate (mandate_default_sandbox) with validity no earlier than 31 Mar 2027.
3. Seeds initial budget allocation, payees, and pending supervisor approval.
4. Fully idempotent: safe to run multiple times during startup or reboots.
"""

import json
import logging
import os
import re
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
    MandateModel,
    StepUpApprovalModel,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phalanx.boot")


class BootError(RuntimeError):
    """Raised when any step of the boot sequence fails."""


def redact_message(text: str) -> str:
    """Redact passwords, secrets, tokens, and sensitive strings from logs and tracebacks."""
    if not text:
        return ""
    s = str(text)
    # Redact URI passwords, e.g. postgresql://user:pass@host:port/db
    s = re.sub(r"(://[^:@\s]+):[^@\s]+@", r"\1:[REDACTED]@", s)
    # Redact key/secret/password/token assignments
    s = re.sub(
        r"(?i)\b(password|secret|token|api_key|client_secret|signing_key|private_key)\b\s*[:=]\s*['\"]?[^'\"\s,;&]+['\"]?",
        r"\1=[REDACTED]",
        s,
    )
    # Redact actual known secret values from environment if populated
    sensitive_keys = (
        "SECRET_KEY",
        "ADMIN_TOKEN",
        "PAYPAL_CLIENT_SECRET",
        "MANDATE_SIGNING_KEY_HEX",
        "GEMINI_API_KEY",
        "RECONCILE_SECRET",
        "POSTGRES_PASSWORD",
        "PHALANX_APP_DB_PASSWORD",
    )
    for env_var in sensitive_keys:
        val = os.getenv(env_var)
        if val and len(val) >= 8:
            s = s.replace(val, "[REDACTED]")
    return s


def run_boot(raise_on_error: bool = False) -> bool:
    """Run idempotent migrations and seed data.

    Args:
        raise_on_error: If True, raise BootError on failure. If False, log error and return False.
    """
    logger.info("Starting PHALANX idempotent boot sequence...")

    # Step 1: Key validation
    print("[boot] step: key validation", flush=True)
    sys.stdout.flush()
    from app.infrastructure.tokens import validate_secret_key

    is_key_valid, key_error = validate_secret_key()
    if not is_key_valid:
        msg = f"Key validation failed: {key_error}"
        sys.stderr.write(f"Boot aborted: {msg}\n")
        sys.stderr.flush()
        logger.error("Boot aborted: %s", key_error)
        if raise_on_error:
            raise BootError(msg)
        return False

    engine = get_engine()

    # Step 2: Migrations
    print("[boot] step: migrations", flush=True)
    sys.stdout.flush()
    import time

    from sqlalchemy import text

    connected = False
    for attempt in range(1, 6):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            connected = True
            break
        except Exception as db_err:
            redacted_err = redact_message(str(db_err))
            logger.warning("Database connection attempt %d/5 failed: %s", attempt, redacted_err)
            if attempt < 5:
                time.sleep(2)

    if not connected:
        msg = "Database connection failure (retry limit exceeded)"
        sys.stderr.write(f"Boot aborted: {msg}\n")
        sys.stderr.flush()
        logger.error("Boot aborted: %s", msg)
        if raise_on_error:
            raise BootError(msg)
        return False

    try:
        from pathlib import Path

        from alembic import command
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory

        ini_candidates = [
            Path("alembic.ini"),
            Path(__file__).resolve().parent.parent / "alembic.ini",
            Path("/app/alembic.ini"),
        ]
        ini_path = next((p for p in ini_candidates if p.exists()), None)
        if not ini_path:
            msg = "alembic.ini configuration file not found"
            sys.stderr.write(f"Boot aborted: {msg}\n")
            sys.stderr.flush()
            logger.error("Boot aborted: %s", msg)
            if raise_on_error:
                raise BootError(msg)
            return False

        logger.info("Applying database migrations via Alembic (%s)...", ini_path)
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
        alembic_cfg.attributes["connection"] = engine
        command.upgrade(alembic_cfg, "head")
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True
        )
        logger.info("Alembic migrations successfully applied to head.")

        # Verify the migration revision matches the declarative models
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()
        with engine.connect() as conn:
            m_context = MigrationContext.configure(conn)
            current_rev = m_context.get_current_revision()

        if current_rev != head_rev:
            msg = f"Alembic revision mismatch (current db: {current_rev}, head: {head_rev})"
            sys.stderr.write(f"Boot aborted: {msg}\n")
            sys.stderr.flush()
            logger.error(msg)
            if raise_on_error:
                raise BootError(msg)
            return False
        logger.info("Verified database revision '%s' matches migration head.", current_rev)

        # Verify physical schema: tables and required constraints must exist
        from sqlalchemy import inspect

        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        required_tables = {
            "agent_budgets",
            "budget_reservations",
            "idempotency_records",
            "step_up_approvals",
            "ledger_events",
            "mandates",
        }
        missing_tables = required_tables - existing_tables
        if missing_tables:
            msg = f"missing required database tables: {missing_tables}"
            sys.stderr.write(f"Boot aborted: {msg}\n")
            sys.stderr.flush()
            logger.error(msg)
            if raise_on_error:
                raise BootError(msg)
            return False

        ledger_constraints = inspector.get_unique_constraints("ledger_events")
        u_names = {c.get("name") for c in ledger_constraints}
        u_cols = [set(c.get("column_names") or []) for c in ledger_constraints]
        if "uq_ledger_events_event_seq" not in u_names and {"event_seq"} not in u_cols:
            msg = "constraint 'uq_ledger_events_event_seq' missing on ledger_events"
            sys.stderr.write(f"Boot aborted: {msg}\n")
            sys.stderr.flush()
            logger.error(msg)
            if raise_on_error:
                raise BootError(msg)
            return False
        logger.info("Verified schema tables and unique constraints exist.")
    except Exception as exc:
        if raise_on_error and isinstance(exc, BootError):
            raise
        import traceback

        tb = redact_message(traceback.format_exc())
        redacted_exc = redact_message(str(exc))
        sys.stderr.write(f"Boot migration/schema error: {redacted_exc}\n{tb}\n")
        sys.stderr.flush()
        logger.error("Boot aborted: migration or schema initialization failure: %s", redacted_exc)
        if raise_on_error:
            raise BootError(f"Migration error: {redacted_exc}") from exc
        return False

    # Step 3: Trigger install
    print("[boot] step: trigger install", flush=True)
    sys.stdout.flush()
    try:
        from app.infrastructure.db_schema import install_ledger_triggers

        install_ledger_triggers(engine)
        logger.info("Database schema and append-only triggers successfully verified/created.")
    except Exception as exc:
        import traceback

        tb = redact_message(traceback.format_exc())
        redacted_exc = redact_message(str(exc))
        sys.stderr.write(f"Boot trigger install error: {redacted_exc}\n{tb}\n")
        sys.stderr.flush()
        logger.error("Boot aborted: trigger installation failure: %s", redacted_exc)
        if raise_on_error:
            raise BootError(f"Trigger install error: {redacted_exc}") from exc
        return False

    # Step 4: Seeding
    print("[boot] step: seeding", flush=True)
    sys.stdout.flush()
    fixed_valid_from = datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)
    fixed_valid_until = datetime(2027, 3, 31, 23, 59, 59, tzinfo=UTC)
    try:
        from app.infrastructure.config import settings
        from app.infrastructure.crypto import load_or_generate_keypair, sign_bytes

        priv_key, pub_key, key_id = load_or_generate_keypair(
            key_hex=settings.mandate_signing_key_hex,
            key_file_path=settings.mandate_signing_key_file,
        )
        with Session(engine) as session:
            existing_mandate = session.scalar(
                select(MandateModel).where(MandateModel.mandate_id == "mandate_default_sandbox")
            )
            if not existing_mandate or existing_mandate.key_id != key_id:
                if existing_mandate:
                    logger.info(
                        "Updating demo mandate key binding to match deployment authority..."
                    )
                    session.delete(existing_mandate)
                    session.flush()
                logger.info("Seeding demo mandate (mandate_default_sandbox)...")
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
                session.commit()
                logger.info("Demo mandate seeded with fixed temporal window.")
            else:
                logger.info("Demo mandate already seeded (idempotent skip).")
    except Exception as exc:
        import traceback

        tb = redact_message(traceback.format_exc())
        redacted_exc = redact_message(str(exc))
        sys.stderr.write(f"Boot mandate seeding error: {redacted_exc}\n{tb}\n")
        sys.stderr.flush()
        logger.error("Boot aborted: error during mandate seeding: %s", redacted_exc)
        if raise_on_error:
            raise BootError(f"Mandate seeding error: {redacted_exc}") from exc
        return False

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
                logger.info("Seeding initial demo budget for agent-auto-1 ($25,000 USD)...")
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
                session.commit()
                logger.info("Initial demo budget created.")
            elif existing_budget.allocated_minor != 2_500_000:
                logger.info("Aligning existing budget allocated_minor to $25,000 USD...")
                existing_budget.allocated_minor = 2_500_000
                session.commit()
            else:
                logger.info("Demo budget for agent-auto-1 already exists (idempotent skip).")

            # Seed Genesis ledger block if missing
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

            # Seed pending step-up request for Scene 2 demo if DEMO_SEED=true
            demo_seed_enabled = os.getenv("DEMO_SEED", "").strip().lower() in ("true", "1")
            if demo_seed_enabled:
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
            else:
                logger.info("DEMO_SEED not enabled; skipping demo step-up request seeding.")

    except Exception as exc:
        import traceback

        tb = redact_message(traceback.format_exc())
        redacted_exc = redact_message(str(exc))
        sys.stderr.write(f"Boot seeding error: {redacted_exc}\n{tb}\n")
        sys.stderr.flush()
        logger.error("Boot aborted: error during data seeding: %s", redacted_exc)
        if raise_on_error:
            raise BootError(f"Data seeding error: {redacted_exc}") from exc
        return False

    logger.info("PHALANX boot sequence complete. Ready to serve traffic.")
    sys.stdout.flush()
    return True


def main() -> None:
    """Main entrypoint for boot script with transparent error reporting."""
    try:
        run_boot(raise_on_error=True)
        sys.stdout.flush()
    except Exception as exc:
        import traceback

        exc_type = type(exc).__name__
        redacted_msg = redact_message(str(exc))
        raw_tb = traceback.format_exc()
        redacted_tb = redact_message(raw_tb)
        sys.stderr.write(f"[boot] ERROR: {exc_type}: {redacted_msg}\n")
        sys.stderr.write(f"[boot] Traceback:\n{redacted_tb}\n")
        sys.stderr.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
