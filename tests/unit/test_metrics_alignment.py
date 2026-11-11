"""Test scripts/generate_test_report.py as single source of truth for test metrics."""

from scripts.generate_test_report import (
    CANONICAL_METRICS,
    get_canonical_metrics,
    verify_documentation_alignment,
)


def test_canonical_metrics_exist() -> None:
    """Verify that canonical metrics are defined with correct types and keys."""
    metrics = get_canonical_metrics()
    assert isinstance(metrics["total_backend_tests"], int) and metrics["total_backend_tests"] > 0
    assert isinstance(metrics["redteam_tests"], int) and metrics["redteam_tests"] > 0
    assert metrics["frontend_tests"] == 11
    assert metrics["prompt_injections"] == 30
    assert (
        isinstance(metrics["policy_eval_median_us"], float) and metrics["policy_eval_median_us"] > 0
    )
    assert metrics["http_request_max_target_ms"] == 200.0


def test_documentation_quotes_canonical_metrics() -> None:
    """Verify that docs/testing.md quotes canonical metrics."""
    assert verify_documentation_alignment(CANONICAL_METRICS) is True
