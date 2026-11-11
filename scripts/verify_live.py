"""Live Deployment Verification Script for PHALANX.

Probes core API endpoints and prints a PASS/FAIL/UNVERIFIED table with response latencies.
Usage:
    python scripts/verify_live.py <base-url> [--admin-token <token>] [--agent-token <token>]
Example:
    python scripts/verify_live.py http://127.0.0.1:8000
"""

import argparse
import sys
import time
from typing import Any
import httpx


def probe_endpoint(
    client: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    expected_status: set[int] | None = None,
) -> dict[str, Any]:
    expected = expected_status or {200}
    start = time.perf_counter()
    try:
        resp = client.request(method, url, headers=headers or {}, timeout=15.0)
        latency_ms = (time.perf_counter() - start) * 1000.0
        status_code = resp.status_code
        passed = status_code in expected
        result_label = "PASS" if passed else "FAIL"
        details = f"HTTP {status_code}"
    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start) * 1000.0
        result_label = "FAIL"
        status_code = 0
        details = "Request Timed Out (>15s)"
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        result_label = "FAIL"
        status_code = 0
        details = f"Error: {exc}"

    return {
        "method": method,
        "url": url,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "result": result_label,
        "details": details,
    }


def run_verification(
    base_url: str,
    admin_token: str | None = None,
    agent_token: str | None = None,
) -> int:
    base = base_url.rstrip("/")
    print("=" * 78)
    print(f"  PHALANX LIVE DEPLOYMENT VERIFICATION: {base}")
    print("=" * 78)

    endpoints_to_probe = [
        # (Path, Method, Headers, Expected Statuses, Description)
        (
            "/healthz",
            "GET",
            {},
            {200},
            "Liveness Probe (non-DB)",
        ),
        (
            "/readyz",
            "GET",
            {},
            {200},
            "Readiness Probe (DB connectivity)",
        ),
        (
            "/v1/mandates/mandate_default_sandbox",
            "GET",
            {"Authorization": f"Bearer {agent_token}"} if agent_token else {},
            {200, 404},
            "Mandate Specification Endpoint",
        ),
        (
            "/v1/approvals",
            "GET",
            {"Authorization": f"Bearer {agent_token}"} if agent_token else {},
            {200},
            "Step-Up Approvals Queue",
        ),
        (
            "/v1/ledger",
            "GET",
            {"Authorization": f"Bearer {agent_token}"} if agent_token else {},
            {200},
            "Audit Ledger Query",
        ),
        (
            "/v1/admin/client-ip",
            "GET",
            {"X-Admin-Token": admin_token} if admin_token else {},
            {200} if admin_token else {401, 403},
            "Client IP Proxy Diagnostic",
        ),
        (
            "/v1/invoice-agent/samples",
            "GET",
            {},
            {200},
            "Invoice Agent Built-In Samples",
        ),
    ]

    results = []
    failures = 0

    with httpx.Client() as client:
        for path, method, headers, expected_statuses, desc in endpoints_to_probe:
            url = f"{base}{path}"
            res = probe_endpoint(client, method, url, headers=headers, expected_status=expected_statuses)
            res["path"] = path
            res["description"] = desc
            results.append(res)
            if res["result"] == "FAIL":
                failures += 1

    # Print Table
    print(f"\n| {'Path':<30} | {'Method':<6} | {'Status':<8} | {'Latency':<10} | {'Result':<6} | {'Description':<22} |")
    print(f"|{'-'*32}|{'-'*8}|{'-'*10}|{'-'*12}|{'-'*8}|{'-'*24}|")
    for r in results:
        lat = f"{r['latency_ms']:.1f} ms"
        status_disp = str(r['status_code']) if r['status_code'] > 0 else "ERR"
        print(f"| {r['path']:<30} | {r['method']:<6} | {status_disp:<8} | {lat:<10} | {r['result']:<6} | {r['description']:<22} |")
    print(f"|{'-'*32}|{'-'*8}|{'-'*10}|{'-'*12}|{'-'*8}|{'-'*24}|\n")

    print(f"Verification Summary: {len(results) - failures}/{len(results)} Passed ({failures} Failures)")
    if failures == 0:
        print("[SUCCESS] All surveyed endpoints verified operational.\n")
        return 0
    else:
        print(f"[FAIL] {failures} endpoint(s) failed verification check.\n")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify PHALANX Live Deployment Endpoints")
    parser.add_argument("base_url", help="Base URL of deployed service (e.g. https://phalanx.onrender.com)")
    parser.add_argument("--admin-token", default=None, help="X-Admin-Token secret for diagnostic endpoint")
    parser.add_argument("--agent-token", default=None, help="Bearer token for protected endpoints")
    args = parser.parse_args()

    exit_code = run_verification(args.base_url, admin_token=args.admin_token, agent_token=args.agent_token)
    sys.exit(exit_code)
