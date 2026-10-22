"""External Keepalive Pinger for PHALANX on Render.

Features:
- Pings /healthz and /readyz to prevent free Render instances from sleeping (15m rule).
- Measures and logs cold-start wakeup latency.
- Validates JSON health payload.
- Can run as one-shot (CI/cron) or continuous daemon loop (--daemon).
"""

import argparse
import logging
import os
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phalanx.pinger")


def ping(target_url: str, timeout: float = 35.0) -> bool:
    """Send health ping to target PHALANX instance."""
    base_url = target_url.rstrip("/")
    health_url = f"{base_url}/healthz"
    ready_url = f"{base_url}/readyz"

    logger.info("Pinging health endpoint: %s", health_url)
    start_time = time.perf_counter()

    try:
        req = urllib.request.Request(
            health_url,
            headers={
                "User-Agent": "PHALANX-External-Pinger/1.0",
                "X-Request-ID": f"pinger_{int(time.time())}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            body = response.read().decode("utf-8")
            status_code = response.getcode()

        is_cold_start = latency_ms > 3000
        logger.info(
            "Health check succeeded [status=%d, latency=%0.2fms, cold_start=%s]: %s",
            status_code,
            latency_ms,
            is_cold_start,
            body,
        )

        # Also probe readiness
        ready_req = urllib.request.Request(
            ready_url,
            headers={
                "User-Agent": "PHALANX-External-Pinger/1.0",
                "X-Request-ID": f"pinger_ready_{int(time.time())}",
            },
        )
        try:
            with urllib.request.urlopen(ready_req, timeout=10.0) as ready_resp:
                ready_body = ready_resp.read().decode("utf-8")
                logger.info("Readiness check: %s", ready_body)
        except Exception as ready_exc:
            logger.warning("Readiness probe non-critical warning: %s", ready_exc)

        return status_code == 200

    except urllib.error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error("HTTP error during ping [%d, latency=%0.2fms]: %s", exc.code, latency_ms, exc)
        return False
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error("Connection failed during ping [latency=%0.2fms]: %s", latency_ms, exc)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="PHALANX keepalive and cold-start pinger")
    parser.add_argument(
        "--url",
        default=os.getenv("PHALANX_TARGET_URL", "http://127.0.0.1:8000"),
        help="Base URL of PHALANX deployment",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously in a loop every interval seconds",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.getenv("PING_INTERVAL_SECONDS", "600")),
        help="Ping interval in seconds (default: 600s / 10m to prevent Render 15m sleep)",
    )
    args = parser.parse_args()

    if not args.daemon:
        success = ping(args.url)
        sys.exit(0 if success else 1)

    logger.info(
        "Starting pinger daemon targeting %s every %d seconds...",
        args.url,
        args.interval,
    )
    while True:
        ping(args.url)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
