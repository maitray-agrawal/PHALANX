"""Test asserting alignment of the demo dataset across API endpoints and UI figures.

Invariants:
- UI remaining authority, stored mandate budget, and boot seed come from same dataset:
  * Lifetime budget: $25,000.00 (2,500,000 minor units)
  * Instant threshold: $500.00 (50,000 minor units)
  * Single limit cap: $5,000.00 (500,000 minor units)
- Overview remaining_authority matches mandate remaining_budget_minor.
"""

from fastapi.testclient import TestClient

from app.infrastructure.tokens import Role, create_role_token
from app.main import app


def test_demo_dataset_figures_alignment() -> None:
    """Assert /v1/overview remaining authority equals /v1/mandates figures."""
    client = TestClient(app)

    token = create_role_token(
        role=Role.PRINCIPAL,
        principal_id="principal_treasury",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fetch overview
    ov_resp = client.get("/v1/overview", headers=headers)
    assert ov_resp.status_code == 200, f"Overview fetch failed: {ov_resp.text}"
    overview_data = ov_resp.json()

    # 2. Fetch stored demo mandate
    man_resp = client.get("/v1/mandates/mandate_default_sandbox", headers=headers)
    assert man_resp.status_code == 200, f"Mandate fetch failed: {man_resp.text}"
    mandate_data = man_resp.json()

    # 3. Assert exact alignment across dataset
    assert mandate_data["lifetime_budget_minor"] == 2_500_000
    assert mandate_data["instant_threshold_minor"] == 50_000
    assert mandate_data["single_limit_minor"] == 500_000

    # Remaining authority in overview must equal remaining budget in mandate
    assert overview_data["remaining_authority"] == mandate_data["remaining_budget_minor"]
    assert overview_data["remaining_authority"] == 2_500_000
