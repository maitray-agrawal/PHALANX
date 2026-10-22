"""Post-deploy smoke test verifying the three core demo scenes against live deployment.

Scenes:
1. Scene 1 - Request Console: Agent autonomous request within limits -> ALLOW.
2. Scene 2 - Approval Queue: Step-up transaction -> supervisor approval with digest -> ALLOW.
3. Scene 3 - Audit Ledger: Chain integrity verification -> tamper detection -> chain restoration.
4. Admin Reset: Clean state reset with X-Admin-Token.

Exit code 0 on all scenes verified.
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phalanx.smoke")


class SmokeTestRunner:
    def __init__(self, base_url: str, admin_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}{path}"
        req_headers = {
            "User-Agent": "PHALANX-SmokeTestRunner/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            req_headers.update(headers)

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                status_code = resp.getcode()
                raw = resp.read().decode("utf-8")
                return status_code, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw}
            return exc.code, parsed

    def run_all(self) -> bool:
        logger.info("=== STARTING PHALANX POST-DEPLOY SMOKE TEST ===")
        logger.info("Target URL: %s", self.base_url)

        # 0. Health & Readiness Probe
        logger.info("[PROBE] Testing /healthz and /readyz...")
        code, data = self._request("GET", "/healthz")
        assert code == 200, f"Healthz failed: {code} {data}"
        code, _ = self._request("GET", "/readyz")
        logger.info("[PROBE] Health checks OK.")

        # 1. Reset state to clean baseline
        logger.info("[SCENE 0] Verifying Admin State Reset with X-Admin-Token...")
        code, data = self._request(
            "POST",
            "/v1/admin/reset",
            headers={"X-Admin-Token": self.admin_token},
        )
        assert code == 200, f"Admin reset failed: {code} {data}"
        assert data.get("status") == "reset_completed"
        logger.info("Scene 0 (Admin Reset) passed.")

        # 2. Scene 1 - Request Console (Pre-authorized autonomous agent payment)
        logger.info("[SCENE 1] Testing Request Console: Autonomous Agent Payment (ALLOW)...")
        tx_key = f"smoke_tx_{int(time.time())}"
        payload = {
            "agent_id": "agent-auto-1",
            "recipient_id": "vendor-paypal-sandbox-1",
            "amount_minor": 1500,  # $15.00
            "currency": "USD",
            "purpose": "Monthly cloud server hosting",
            "idempotency_key": tx_key,
        }
        code, data = self._request(
            "POST",
            "/api/v1/authorize",
            body=payload,
            headers={"x-phalanx-role": "agent"},
        )
        assert code == 200, f"Scene 1 authorization failed: {code} {data}"
        assert data["decision"] == "ALLOW", f"Expected ALLOW, got {data['decision']}"
        assert data["event_id"].startswith("evt_")
        assert data["intent_digest"]
        logger.info("Scene 1 (Request Console ALLOW) passed: Event %s", data["event_id"])

        # 3. Scene 2 - Approval Queue (Human Supervisor Step-Up & Approval)
        logger.info("[SCENE 2] Testing Approval Queue: Human Supervisor Step-Up...")
        # Step 2a: Query pending step-up requests
        code, stepups = self._request(
            "GET",
            "/v1/approvals",
            headers={"x-phalanx-role": "approver"},
        )
        assert code == 200, f"Failed to fetch pending approvals: {code} {stepups}"
        assert len(stepups) > 0, "Expected at least 1 pending step-up request in demo queue!"
        pending_item = stepups[0]
        req_id = pending_item["request_id"]
        expected_digest = pending_item["intent_digest"]
        logger.info("Found pending step-up request: %s (digest: %s)", req_id, expected_digest[:16])

        # Step 2b: Approve bound to exact digest
        approval_body = {
            "expected_digest": expected_digest,
            "decision": "ALLOW",
            "reason": "Verified purchase order by CFO supervisor.",
        }
        code, approval_res = self._request(
            "POST",
            f"/v1/approvals/{req_id}",
            body=approval_body,
            headers={"x-phalanx-role": "approver"},
        )
        assert code == 200, f"Scene 2 supervisor approval failed: {code} {approval_res}"
        assert approval_res["decision"] == "ALLOW", f"Approval failed: {approval_res}"
        logger.info("Scene 2 (Approval Queue ALLOW) passed: Resolved %s", req_id)

        # 4. Scene 3 - Audit Ledger & Chain Integrity
        logger.info("[SCENE 3] Testing Audit Ledger: Cryptographic Chain Verification...")
        # Step 3a: Verify pristine chain
        code, verify_res = self._request(
            "GET",
            "/v1/ledger/verify",
            headers={"x-phalanx-role": "auditor"},
        )
        assert code == 200, f"Ledger verification failed: {code} {verify_res}"
        assert verify_res["is_valid"] is True, f"Pristine ledger chain invalid: {verify_res}"
        logger.info(
            "Pristine ledger verified OK: %d events, hash chain intact.",
            verify_res["total_events"],
        )

        # Step 3b: Simulate tampering and confirm detection
        logger.info("Testing Auditor Tamper Detection...")
        code, _ = self._request(
            "POST",
            "/v1/ledger/tamper",
            body={"index": 1, "new_amount": 99999999},
            headers={"x-phalanx-role": "auditor"},
        )
        assert code == 200, "Tamper endpoint failed"
        code, tampered_verify = self._request(
            "GET",
            "/v1/ledger/verify",
            headers={"x-phalanx-role": "auditor"},
        )
        assert code == 200
        assert tampered_verify["is_valid"] is False, "Tampering was NOT detected by verify_chain!"
        logger.info(
            "Tamper detection passed: Broken index %s detected as expected.",
            tampered_verify.get("broken_index"),
        )

        # Step 3c: Restore pristine chain
        code, _ = self._request(
            "POST",
            "/v1/ledger/restore",
            headers={"x-phalanx-role": "auditor"},
        )
        assert code == 200
        code, restored_verify = self._request(
            "GET",
            "/v1/ledger/verify",
            headers={"x-phalanx-role": "auditor"},
        )
        assert code == 200 and restored_verify["is_valid"] is True
        logger.info("Scene 3 (Audit Ledger Verification & Tamper Detection) passed.")

        logger.info("=== ALL THREE DEMO SCENES & ADMIN RESET VERIFIED ON LIVE HOST! ===")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="PHALANX live post-deploy smoke test")
    parser.add_argument(
        "--url",
        default=os.getenv("PHALANX_TARGET_URL", "http://127.0.0.1:8000"),
        help="Base URL of PHALANX deployment",
    )
    parser.add_argument(
        "--admin-token",
        default=os.getenv("PHALANX_ADMIN_TOKEN", "phalanx-admin-demo-key"),
        help="Admin token for reset verification",
    )
    args = parser.parse_args()

    runner = SmokeTestRunner(args.url, args.admin_token)
    try:
        success = runner.run_all()
        sys.exit(0 if success else 1)
    except AssertionError as exc:
        logger.error("SMOKE TEST ASSERTION FAILURE: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("UNEXPECTED SMOKE TEST FAILURE: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
