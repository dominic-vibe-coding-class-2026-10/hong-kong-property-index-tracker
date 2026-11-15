"""Run history load, weekly update, adaptive extraction, and the insight."""

from __future__ import annotations

import logging

from app.adaptive import extract_midland, extract_rvd
from app.ccl_history import load_history
from app.ccl_weekly import update_weekly
from app.config import setup_logging
from app.db import log_path
from app.insight import generate_insight
from app.quality import QualityGateError

logger = logging.getLogger(__name__)

STEPS = (
    ("Centa-City Leading Index history", load_history),
    ("Centa-City Leading Index weekly update", update_weekly),
    ("Rating and Valuation Department extraction", extract_rvd),
    ("Midland Realty extraction", extract_midland),
    ("Ollama Cloud insight", generate_insight),
)


def main() -> None:
    setup_logging()
    failed = False
    for label, step in STEPS:
        logger.info("Starting %s", label)
        try:
            step()
        except (QualityGateError, Exception) as exc:
            failed = True
            log_path(None, label, "fail", str(exc))
            logger.error("%s failed: %s", label, exc)
            if label == "Centa-City Leading Index history":
                logger.error("Stopping because the historical series is required")
                raise SystemExit(1) from exc
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
