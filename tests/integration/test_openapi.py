"""Tests for OpenAPI schema generation and specification completeness."""

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_schema_generated_and_valid() -> None:
    """Ensure OpenAPI JSON schema is generated, valid, and contains all required v1 endpoints."""
    openapi = app.openapi()
    assert openapi["openapi"].startswith("3.")
    assert openapi["info"]["title"] == "PHALANX"
    assert openapi["info"]["version"] == "0.1.0"

    paths = openapi["paths"]

    # Verify all expected endpoints exist in the schema
    expected_endpoints = [
        "/v1/payment-requests",
        "/v1/payment-requests/{request_id}",
        "/v1/mandates",
        "/v1/mandates/{mandate_id}",
        "/v1/decisions/{decision_id}",
        "/v1/approvals/{request_id}",
        "/v1/ledger",
        "/v1/ledger/verify",
        "/v1/webhooks/paypal",
        "/v1/admin/reset",
        "/v1/auth/demo-token",
        "/healthz",
        "/readyz",
    ]

    for endpoint in expected_endpoints:
        assert endpoint in paths, f"Endpoint {endpoint} missing from generated OpenAPI schema"


def test_openapi_docs_accessible(client: TestClient) -> None:
    """Ensure /docs (Swagger UI) and /openapi.json are accessible."""
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200

    schema_resp = client.get("/openapi.json")
    assert schema_resp.status_code == 200
    assert schema_resp.json()["info"]["title"] == "PHALANX"
