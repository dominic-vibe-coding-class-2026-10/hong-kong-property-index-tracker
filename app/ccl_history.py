"""Load the full Centa-City Leading Index history from the Centanet chart API."""

from __future__ import annotations

import logging
from datetime import date

import requests

from app.config import CCL_HISTORY_API, USER_AGENT, setup_logging
from app.db import init_db, log_path, upsert_observations, write_evidence
from app.quality import QualityGateError, check_value, parse_iso_date, require

logger = logging.getLogger(__name__)


def fetch_chart() -> dict:
    response = requests.get(
        CCL_HISTORY_API,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def rows_from_chart(payload: dict) -> list[dict]:
    raw = payload.get("rawData") or {}
    values = raw.get("ccl")
    starts = raw.get("realContractStartDate")
    ends = raw.get("realContractEndDate")
    require(isinstance(values, list) and values, "CCL history payload has no ccl series")
    require(
        isinstance(starts, list) and isinstance(ends, list) and len(values) == len(starts) == len(ends),
        "CCL history date arrays do not match the value array",
    )
    rows: list[dict] = []
    for value, start, end in zip(values, starts, ends):
        if value is None:
            continue
        number = float(value)
        check_value("ccl", number)
        period = parse_iso_date(str(end))
        rows.append(
            {
                "period_date": period.isoformat(),
                "period_label": f"{start} – {end}",
                "value": number,
                "source_path": "history_api",
                "raw_note": None,
            }
        )
    return rows


def gate_history(rows: list[dict], today: date | None = None) -> None:
    today = today or date.today()
    require(len(rows) >= 1400, f"CCL history has {len(rows)} points; expected at least 1400")
    dates = [parse_iso_date(row["period_date"]) for row in rows]
    require(dates == sorted(dates), "CCL history dates are not sorted")
    require(len(dates) == len(set(dates)), "CCL history has duplicate dates")
    require(dates[0] <= date(1995, 1, 1), f"CCL history starts too late: {dates[0].isoformat()}")
    age = (today - dates[-1]).days
    require(0 <= age <= 21, f"CCL history latest date {dates[-1].isoformat()} is not a current week")
    for earlier, later in zip(dates, dates[1:]):
        gap = (later - earlier).days
        require(gap == 7, f"CCL weekly gap {gap} days between {earlier} and {later}")


def load_history(today: date | None = None) -> int:
    init_db()
    logger.info("Fetching Centa-City Leading Index history from %s", CCL_HISTORY_API)
    payload = fetch_chart()
    rows = rows_from_chart(payload)
    gate_history(rows, today=today)
    written = upsert_observations("ccl", rows)
    detail = (
        f"Stored {written} weekly points from {rows[0]['period_date']} "
        f"to {rows[-1]['period_date']} (latest {rows[-1]['value']})"
    )
    log_path("ccl", "history_api", "ok", detail)
    write_evidence(
        "ccl_history",
        {
            "path": "history_api",
            "url": CCL_HISTORY_API,
            "count": written,
            "first": rows[0],
            "last": rows[-1],
        },
    )
    logger.info(detail)
    return written


def main() -> None:
    setup_logging()
    try:
        load_history()
    except (QualityGateError, requests.RequestException) as exc:
        init_db()
        log_path("ccl", "history_api", "fail", str(exc))
        logger.error("CCL history load failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
