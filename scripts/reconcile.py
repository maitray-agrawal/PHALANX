#!/usr/bin/env python3
"""Scheduled reconciliation job for PHALANX.

Reconciles all requests in RECONCILE or non-terminal provider states.
Settles completed payments, releases confirmed failures, marks timeouts as NEEDS_REVIEW.
Never auto-releases on timeout.
"""

import logging
import sys

from app.api.dependencies import get_reconciler_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phalanx.reconciler")


def main() -> int:
    logger.info("Starting PHALANX scheduled reconciliation job...")
    try:
        reconciler = get_reconciler_service()
        metrics = reconciler.reconcile_all(force=True)
        logger.info("Reconciliation complete: %s", metrics)
        return 0
    except Exception as exc:
        logger.error("Reconciliation job failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
