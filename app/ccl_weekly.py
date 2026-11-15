"""Weekly Centa-City Leading Index update via Playwright.

The visible headline is read with stable selectors. The three latest weekly
points come from the chart payload the same page requests, and they are
accepted only when the newest point matches that headline.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from app.config import CCL_PAGE, setup_logging
from app.db import init_db, log_path, upsert_observations, write_evidence
from app.quality import QualityGateError, check_value, parse_iso_date, require

logger = logging.getLogger(__name__)

DATE_RANGE = re.compile(
    r"反映\s*(\d{4})/(\d{2})/(\d{2})\s*至\s*(\d{4})/(\d{2})/(\d{2})"
)


def _headline_and_chart(page_url: str = CCL_PAGE) -> tuple[float, date, list[dict]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise QualityGateError(
            "Playwright is not installed. Run: python -m playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="zh-HK",
            )
            with page.expect_response(
                lambda response: "/api/Index/CCLChart" in response.url and response.status == 200,
                timeout=45000,
            ) as chart_response:
                page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
            page.locator(".plate-info .info-cell").filter(has_text="本週公佈").locator(
                ".cell-count"
            ).wait_for(timeout=20000)
            headline_text = (
                page.locator(".plate-info .info-cell")
                .filter(has_text="本週公佈")
                .locator(".cell-count")
                .inner_text()
                .strip()
            )
            note = page.locator(".plate-content").first.inner_text()
            chart = chart_response.value.json()
        finally:
            browser.close()

    headline = float(headline_text.replace(",", ""))
    check_value("ccl", headline)
    match = DATE_RANGE.search(note.replace("\n", ""))
    require(match is not None, "CCL page is missing the 反映…至… publication range")
    published_end = date(int(match.group(4)), int(match.group(5)), int(match.group(6)))
    rows = _last_three(chart)
    require(
        abs(rows[-1]["value"] - headline) < 0.02,
        f"headline {headline} does not match chart latest {rows[-1]['value']}",
    )
    require(
        rows[-1]["period_date"] == published_end.isoformat(),
        f"chart date {rows[-1]['period_date']} does not match page date {published_end.isoformat()}",
    )
    return headline, published_end, rows


def _last_three(payload: dict) -> list[dict]:
    raw = payload.get("rawData") or {}
    values = raw.get("ccl") or []
    starts = raw.get("realContractStartDate") or []
    ends = raw.get("realContractEndDate") or []
    points = []
    for value, start, end in zip(values, starts, ends):
        if value is None:
            continue
        number = float(value)
        check_value("ccl", number)
        points.append(
            {
                "period_date": parse_iso_date(str(end)).isoformat(),
                "period_label": f"{start} – {end}",
                "value": number,
                "source_path": "playwright_weekly",
                "raw_note": "three latest weekly points",
            }
        )
    require(len(points) >= 3, "CCL chart did not contain three weekly points")
    latest = points[-3:]
    dates = [parse_iso_date(row["period_date"]) for row in latest]
    require(dates[1] - dates[0] == timedelta(days=7), "weekly points are not 7 days apart")
    require(dates[2] - dates[1] == timedelta(days=7), "weekly points are not 7 days apart")
    return latest


def update_weekly(today: date | None = None) -> list[dict]:
    init_db()
    today = today or date.today()
    logger.info("Reading the three latest Centa-City Leading Index points from %s", CCL_PAGE)
    try:
        headline, published_end, rows = _headline_and_chart()
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc).lower():
            raise QualityGateError(
                "Chromium is not installed for Playwright. Run: python -m playwright install chromium"
            ) from exc
        raise
    age = (today - published_end).days
    require(0 <= age <= 14, f"published week {published_end.isoformat()} is not current")
    written = upsert_observations("ccl", rows)
    detail = (
        f"Upserted {written} weekly points ending {rows[-1]['period_date']} "
        f"at {rows[-1]['value']} (page headline {headline})"
    )
    log_path("ccl", "playwright_weekly", "ok", detail)
    write_evidence(
        "ccl_weekly",
        {
            "path": "playwright_weekly",
            "page": CCL_PAGE,
            "headline": headline,
            "points": rows,
        },
    )
    logger.info(detail)
    return rows


def main() -> None:
    setup_logging()
    try:
        update_weekly()
    except (QualityGateError, Exception) as exc:
        init_db()
        log_path("ccl", "playwright_weekly", "fail", str(exc))
        logger.error("CCL weekly update failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
