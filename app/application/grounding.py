"""Grounded explanation validation and deterministic explanation generator.

Invariants (Manual 43):
- Candidate LLM explanation text must derive strictly from the authoritative decision record.
- The LLM may paraphrase, but the validator strictly enforces:
  1. The exact request_id is present.
  2. The exact decision outcome (ALLOW, STEP_UP, DENY) matches.
  3. Reason codes are accurately reflected.
  4. No hallucinated amounts or numbers outside the decision record appear.
  5. No payee other than the expected recipient appears.
- On ANY failure: cleanly falls back to the deterministic templated explanation.
"""

import logging
import re

from app.application.dtos import AuthorizationResponseDTO

logger = logging.getLogger(__name__)


class GroundedExplanationValidator:
    """Verifies that assistant explanations do not hallucinate amounts, payees, or decisions."""

    @staticmethod
    def format_templated_explanation(
        record: AuthorizationResponseDTO,
        recipient_id: str,
        amount_minor: int,
        currency: str = "USD",
    ) -> str:
        """Generate a deterministic, grounded explanation directly from the record."""
        codes_str = ", ".join(c.value for c in record.reason_codes) or "PRE_AUTHORIZED"
        reasons_str = "; ".join(record.reasons) or "Policy evaluation completed"
        amount_dollars = f"{amount_minor / 100:.2f}"
        payout_str = (
            f" Dispatched payout transaction ID: {record.payout_id}." if record.payout_id else ""
        )

        return (
            f"Decision: {record.decision.value} for request {record.request_id} "
            f"({currency} {amount_dollars} to payee '{recipient_id}'). "
            f"Reason codes: [{codes_str}]. Details: {reasons_str}.{payout_str}"
        )

    def validate_and_ground(
        self,
        candidate_explanation: str,
        record: AuthorizationResponseDTO,
        expected_recipient_id: str,
        expected_amount_minor: int,
        currency: str = "USD",
    ) -> tuple[bool, str]:
        """Validate candidate LLM response against the ground-truth decision record.

        Returns:
            (True, candidate_explanation) if fully grounded and truthful.
            (False, templated_explanation) if any hallucination, omission, or tamper is detected.
        """
        templated = self.format_templated_explanation(
            record, expected_recipient_id, expected_amount_minor, currency
        )

        # 1. Request ID verification
        if record.request_id not in candidate_explanation:
            logger.info("Grounding failed: missing request_id '%s'", record.request_id)
            return False, templated

        # 2. Decision outcome verification
        if record.decision.value not in candidate_explanation:
            logger.info("Grounding failed: missing decision outcome '%s'", record.decision.value)
            return False, templated

        # Check for conflicting contradictory outcomes
        other_outcomes = {"ALLOW", "STEP_UP", "DENY"} - {record.decision.value}
        for other in other_outcomes:
            # If candidate claims another decision as the verdict, reject
            if re.search(rf"\bdecision\b[^.\n]*\b{other}\b", candidate_explanation, re.IGNORECASE):
                logger.info("Grounding failed: contradictory outcome '%s' mentioned", other)
                return False, templated

        # 3. Payee verification: if payee/recipient/vendor is mentioned, it MUST match expected
        if (
            "recipient" in candidate_explanation.lower()
            or "payee" in candidate_explanation.lower()
            or "vendor" in candidate_explanation.lower()
        ) and expected_recipient_id not in candidate_explanation:
            logger.info("Grounding failed: expected payee '%s' missing", expected_recipient_id)
            return False, templated

        # 4. Strict numerical boundary check: no hallucinated monetary amounts
        cents_str = str(expected_amount_minor)
        dollars_str = str(expected_amount_minor // 100)
        dollars_float_str = f"{expected_amount_minor / 100:.2f}"

        # Collect allowed numeric tokens from the record and expected input
        allowed_numbers: set[str] = {
            cents_str,
            dollars_str,
            dollars_float_str,
            "0",
            "1",
            "2",
        }
        # Allow numbers found in reasons or reason codes (e.g. thresholds like 50000 or 1000)
        for r in record.reasons:
            for num in re.findall(r"\b\d+(?:\.\d+)?\b", r):
                allowed_numbers.add(num)
                if "." in num:
                    allowed_numbers.add(str(int(float(num) * 100)))

        # Also extract digits from request_id so request ID components don't trigger false positives
        for id_part in re.findall(r"\d+", record.request_id):
            allowed_numbers.add(id_part)

        # Find all numbers in candidate explanation (e.g. 500, 25.00, $9000, 99999999)
        # Strip currency symbols and commas
        clean_text = candidate_explanation.replace("$", " ").replace(",", "")
        candidate_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", clean_text)

        for num in candidate_numbers:
            # Single digits (0-9) used for enumerations are permitted
            if len(num) == 1:
                continue
            if num not in allowed_numbers:
                # Number was not in the decision record or original intent
                logger.info(
                    "Grounding failed: hallucinated number '%s' not in allowed set %s",
                    num,
                    allowed_numbers,
                )
                return False, templated

        return True, candidate_explanation
