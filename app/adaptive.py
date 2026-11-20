"""Latest Rating and Valuation Department and Midland readings.

Tavily finds the current official page. Firecrawl extracts the latest value.
If Tavily is missing or fails, the known seed URL is used and that fallback
is logged. Playwright runs only after Firecrawl fails the quality gate.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date
from typing import Any

import requests

from app.config import (
    FIRECRAWL_URL,
    MIDLAND_SEED,
    RVD_SEED_CSV,
    RVD_SEED_PAGE,
    TAVILY_URL,
    USER_AGENT,
    env,
    setup_logging,
)
from app.db import (
    init_db,
    log_path,
    replace_observations,
    series_rows,
    upsert_observations,
    write_evidence,
)
from app.midland import (
    MIDLAND_MIN_POINTS,
    disagreement_count,
    observations_from_points,
    parse_weekly_index,
    select_midland_rows,
    validate_weekly,
)
from app.quality import (
    QualityGateError,
    as_float,
    check_value,
    parse_period,
    require,
    require_recent,
    same_month,
)

logger = logging.getLogger(__name__)

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "index_name": {"type": "string"},
        "series_scope": {"type": "string"},
        "latest_value": {"type": "number"},
        "period_end": {"type": "string"},
        "provisional": {"type": "boolean"},
        "is_price_per_sqft": {"type": "boolean"},
        "recent_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "period_end": {"type": "string"},
                    "value": {"type": "number"},
                },
            },
        },
    },
    "required": ["latest_value", "period_end"],
}

PROMPTS = {
    "rvd": (
        "Extract the latest territory-wide Private Domestic Price Index for All Classes "
        "published by the Hong Kong Rating and Valuation Department. "
        "Use the All Classes column, not Class A, B, C, D, or E. "
        "Return the index level (1999 = 100), not a rent and not a price in dollars. "
        "period_end must be the month of that reading as YYYY-MM. "
        "Set series_scope to territory. Set provisional to true when the cell is marked P."
    ),
    "midland": (
        "Extract the latest territory-wide Midland Property Price Index "
        "(美聯樓價指數), the headline All / 全港 index on the market-insight page. "
        "It is published every Monday. Return that index in points. "
        "Never return a price per square foot (dollar amounts, usually above 1000). "
        "Never return the Hong Kong Island, Kowloon, or New Territories sub-index. "
        "Never return the Midland Confidence Index (美聯信心指數), the US Dollar Index, "
        "the Hang Seng Index, an affordability ratio, or any other chart on the page. "
        "Set series_scope to territory and is_price_per_sqft to false. "
        "period_end is the Monday as-of date as YYYY-MM-DD. "
        "If you include recent_points, every point must be this same All / 全港 weekly index."
    ),
}

DISTRICT_MARKERS = (
    "island",
    "kowloon",
    "new territories",
    "港島",
    "九龍",
    "新界",
    "confidence",
    "信心",
)


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def tavily_urls(query: str, domains: list[str], series_id: str) -> list[str]:
    key = env("TAVILY_API_KEY")
    if not key:
        log_path(series_id, "tavily", "fallback", "TAVILY_API_KEY is missing; using the seed URL")
        logger.info("%s: Tavily key missing, seed URL fallback", series_id)
        return []
    body = {
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_domains": domains,
        "include_answer": False,
    }
    try:
        response = requests.post(
            TAVILY_URL,
            json=body,
            headers={**_headers(), "Authorization": f"Bearer {key}"},
            timeout=45,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except requests.RequestException as exc:
        log_path(series_id, "tavily", "fallback", f"Tavily failed ({exc}); using the seed URL")
        logger.info("%s: Tavily failed, seed URL fallback: %s", series_id, exc)
        return []

    urls: list[str] = []
    for item in results:
        url = str(item.get("url") or "").strip()
        host_ok = any(domain in url for domain in domains)
        if url and host_ok and url not in urls:
            urls.append(url)
    urls.sort(key=lambda item: (
        0 if item.lower().endswith(".csv") else 1,
        1 if item.lower().endswith(".pdf") else 0,
        item,
    ))
    if not urls:
        log_path(
            series_id,
            "tavily",
            "fallback",
            "Tavily returned no official URL; using the seed URL",
        )
        logger.info("%s: Tavily returned no official URL, seed URL fallback", series_id)
        return []
    log_path(series_id, "tavily", "ok", "Discovered " + " | ".join(urls[:3]))
    return urls[:3]


def _firecrawl_post(url: str, payload: dict[str, Any], key: str) -> dict[str, Any]:
    response = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    data = body.get("data") or {}
    extracted = data.get("json") or data.get("llm_extraction") or data.get("extract") or {}
    require(isinstance(extracted, dict) and extracted, f"Firecrawl returned no JSON for {payload.get('url')}")
    extracted["_markdown_excerpt"] = str(data.get("markdown") or "")[:800]
    extracted["_links"] = list(data.get("links") or [])[:20]
    extracted["_url"] = payload.get("url")
    return extracted


def firecrawl_extract(url: str, series_id: str) -> dict[str, Any]:
    key = env("FIRECRAWL_API_KEY")
    require(bool(key), "FIRECRAWL_API_KEY is missing")
    is_csv = url.lower().endswith(".csv")
    v1_payload = {
        "url": url,
        "formats": ["markdown", "json", "links"],
        "onlyMainContent": not is_csv,
        "timeout": 90000,
        "waitFor": 0 if is_csv else 3000,
        "jsonOptions": {"prompt": PROMPTS[series_id], "schema": EXTRACT_SCHEMA},
    }
    try:
        return _firecrawl_post(FIRECRAWL_URL, v1_payload, key)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status not in {404, 410}:
            raise
    v2_payload = {
        "url": url,
        "formats": [
            {"type": "json", "prompt": PROMPTS[series_id], "schema": EXTRACT_SCHEMA},
            "markdown",
            "links",
        ],
        "onlyMainContent": not is_csv,
        "timeout": 90000,
        "waitFor": 0 if is_csv else 3000,
    }
    return _firecrawl_post("https://api.firecrawl.dev/v2/scrape", v2_payload, key)


def _reject_wrong_series(extracted: dict[str, Any], series_id: str) -> None:
    if extracted.get("is_price_per_sqft") is True:
        raise QualityGateError(f"{series_id} extraction is a price per square foot")
    scope = str(extracted.get("series_scope") or "").lower()
    name = str(extracted.get("index_name") or "").lower()
    if scope == "district" or any(marker in name for marker in DISTRICT_MARKERS):
        raise QualityGateError(f"{series_id} extraction is a sub-index: {name or scope}")


def parse_rvd_csv(text: str) -> list[dict[str, Any]]:
    sample = text.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(sample))
    rows = list(reader)
    header_index = next((i for i, row in enumerate(rows) if row and row[0].strip().lower() == "month"), None)
    require(header_index is not None, "RVD file has no Month header")
    header = [cell.strip() for cell in rows[header_index]]
    try:
        value_at = header.index("All Classes")
    except ValueError as exc:
        raise QualityGateError("RVD file has no All Classes column") from exc
    parsed: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        if not row or not row[0].strip():
            continue
        period = parse_period(row[0].strip())
        if period is None or value_at >= len(row):
            continue
        raw_value = row[value_at].strip()
        if raw_value in {"", "-", "—", "N/A"}:
            continue
        number = as_float(raw_value)
        check_value("rvd", number)
        remark = row[value_at + 1].strip() if value_at + 1 < len(row) else ""
        parsed.append(
            {
                "period_date": period.isoformat(),
                "period_label": f"{period.year:04d}-{period.month:02d}",
                "value": number,
                "source_path": "official_csv",
                "raw_note": "provisional" if remark.upper() == "P" else None,
            }
        )
    require(parsed, "RVD file contained no All Classes readings")
    return parsed


def download_rvd_csv() -> list[dict[str, Any]]:
    response = requests.get(
        RVD_SEED_CSV,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return parse_rvd_csv(response.text)


def _accept_rvd(extracted: dict[str, Any], today: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _reject_wrong_series(extracted, "rvd")
    value = as_float(extracted.get("latest_value"))
    check_value("rvd", value)
    stated = parse_period(extracted.get("period_end"))
    official = download_rvd_csv()
    latest = official[-1]
    official_date = date.fromisoformat(latest["period_date"])
    require(
        abs(value - latest["value"]) <= 0.5,
        f"Firecrawl value {value} does not match official All Classes {latest['value']}",
    )
    if stated is not None:
        require(
            same_month(stated, official_date),
            f"Firecrawl month {stated.isoformat()} does not match official {official_date.isoformat()}",
        )
    require_recent(official_date, today, max_age_days=120)
    confirmed = {
        "period_date": latest["period_date"],
        "period_label": latest["period_label"],
        "value": latest["value"],
        "source_path": "tavily_firecrawl",
        "raw_note": latest.get("raw_note"),
    }
    return confirmed, official


def fetch_midland_html() -> str:
    response = requests.get(
        MIDLAND_SEED,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "en-HK,en;q=0.9",
        },
        timeout=60,
    )
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def load_official_midland(today: date) -> list[dict[str, Any]] | None:
    """Territory-wide weekly index from the market-insight page, or None if unavailable."""
    try:
        points = parse_weekly_index(fetch_midland_html())
        validate_weekly(points, today)
    except (QualityGateError, requests.RequestException, ValueError, TypeError) as exc:
        logger.info("Midland official weekly series unavailable: %s", exc)
        return None
    return points


def _stored_midland_values() -> list[float]:
    return [float(row["value"]) for row in series_rows("midland")]


def _commit_midland(
    rows: list[dict[str, Any]],
    *,
    verified: bool,
    source_path: str,
    url: str,
    extracted: dict[str, Any] | None,
) -> None:
    require(bool(rows), "Midland extraction produced no rows")
    stored = series_rows("midland")
    if verified:
        require(
            len(rows) >= MIDLAND_MIN_POINTS,
            f"Refusing to replace the Midland series with only {len(rows)} points",
        )
        removed = disagreement_count(stored, rows)
        replace_observations("midland", rows)
    else:
        upsert_observations("midland", rows)
        removed = 0
    latest = rows[-1]
    detail = (
        f"Latest {latest['value']} on {latest['period_date']} "
        f"via {source_path} ({len(rows)} territory-wide weekly points)"
    )
    if removed:
        detail += f"; replaced {removed} stored points that were not this series or disagreed with it"
    log_path("midland", source_path, "ok", detail)
    write_evidence(
        "midland",
        {
            "path": source_path,
            "url": url,
            "series": "territory-wide Midland Property Price Index",
            "extracted": None
            if extracted is None
            else {
                "index_name": extracted.get("index_name"),
                "latest_value": extracted.get("latest_value"),
                "period_end": extracted.get("period_end"),
                "series_scope": extracted.get("series_scope"),
            },
            "stored_count": len(rows),
            "stored_latest": latest,
            "recent": rows[-8:],
            "replaced_count": removed,
        },
    )
    logger.info(detail)


def _store_rvd(confirmed: dict[str, Any], official: list[dict[str, Any]], evidence_name: str, extracted: dict) -> None:
    upsert_observations("rvd", official)
    upsert_observations("rvd", [confirmed])
    detail = (
        f"Latest All Classes {confirmed['value']} for {confirmed['period_label']} "
        f"via {confirmed['source_path']}; stored {len(official)} monthly points"
    )
    log_path("rvd", confirmed["source_path"], "ok", detail)
    write_evidence(
        evidence_name,
        {
            "path": confirmed["source_path"],
            "url": extracted.get("_url") or RVD_SEED_PAGE,
            "extracted_value": extracted.get("latest_value"),
            "extracted_period": extracted.get("period_end"),
            "stored": confirmed,
            "history_count": len(official),
        },
    )
    logger.info(detail)


def _candidate_urls(series_id: str) -> list[str]:
    if series_id == "rvd":
        discovered = tavily_urls(
            "Hong Kong Rating and Valuation Department private domestic price index "
            "All Classes territory-wide latest official statistics",
            ["rvd.gov.hk", "data.gov.hk"],
            "rvd",
        )
        seeds = [RVD_SEED_PAGE, RVD_SEED_CSV]
    else:
        discovered = tavily_urls(
            "Midland Realty Property Price Index Hong Kong latest official market insight",
            ["midland.com.hk"],
            "midland",
        )
        seeds = [MIDLAND_SEED]
    urls: list[str] = []
    # Midland always starts from the market-insight page. A Tavily hit such as
    # the homepage must not replace that page, because other charts there are
    # a different series.
    ordered = (seeds[:1] + discovered) if series_id == "midland" else (discovered or seeds[:1])
    for url in ordered:
        if url not in urls:
            urls.append(url)
    if series_id == "rvd" and RVD_SEED_CSV not in urls:
        urls.append(RVD_SEED_CSV)
    if not discovered:
        logger.info("%s: continuing with seed URL %s", series_id, urls[0])
    return urls


def _playwright_text_and_json(url: str) -> tuple[str, list[Any], list[str], str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise QualityGateError(
            "Playwright is not installed. Run: python -m playwright install chromium"
        ) from exc

    blobs: list[Any] = []

    def capture(response) -> None:
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            return
        lowered = response.url.lower()
        if any(token in lowered for token in ("index", "insight", "price", "chart", "stat")):
            try:
                blobs.append(response.json())
            except Exception:
                return

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT, locale="en-HK")
            page.on("response", capture)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            text = page.locator("body").inner_text(timeout=15000)
            hrefs = page.eval_on_selector_all("a", "els => els.map((el) => el.href).filter(Boolean)")
            html = page.content()
        finally:
            browser.close()
    return text, blobs, hrefs, html


def playwright_rvd(today: date) -> tuple[dict[str, Any], list[dict[str, Any]], dict]:
    text, _blobs, hrefs, _html = _playwright_text_and_json(RVD_SEED_PAGE)
    require(
        "price indices" in text.lower() or "private domestic" in text.lower(),
        "RVD statistics page did not render",
    )
    linked = next((href for href in hrefs if "1.4M.csv" in href or href.lower().endswith("his_data_4.xls")), "")
    if linked.lower().endswith(".csv"):
        response = requests.get(linked, headers={"User-Agent": USER_AGENT}, timeout=60)
        response.raise_for_status()
        response.encoding = "utf-8"
        official = parse_rvd_csv(response.text)
    else:
        official = download_rvd_csv()
    latest = official[-1]
    official_date = date.fromisoformat(latest["period_date"])
    require_recent(official_date, today, max_age_days=120)
    confirmed = dict(latest)
    confirmed["source_path"] = "playwright_fallback"
    extracted = {"_url": RVD_SEED_PAGE, "latest_value": latest["value"], "period_end": latest["period_label"]}
    return confirmed, official, extracted


def _walk_numbers(node: Any, found: list[tuple[str, float]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                found.append((str(key).lower(), float(value)))
            else:
                _walk_numbers(value, found)
    elif isinstance(node, list):
        for item in node[:80]:
            _walk_numbers(item, found)


def playwright_midland(today: date) -> tuple[list[dict[str, Any]], bool]:
    text, blobs, _hrefs, html = _playwright_text_and_json(MIDLAND_SEED)
    try:
        points = parse_weekly_index(html)
        validate_weekly(points, today)
        return observations_from_points(points, "playwright_fallback"), True
    except QualityGateError as exc:
        logger.info("Midland Playwright page had no usable weekly series: %s", exc)
    flat = re.sub(r"\s+", " ", text)
    patterns = [
        r"All Index\s+(\d{2,3}\.\d{1,2})",
        r"全港.{0,40}?(\d{2,3}\.\d{1,2})",
        r"Midland Property Price Index.{0,80}?(\d{2,3}\.\d{1,2})",
        r"美聯樓價指數.{0,40}?(\d{2,3}\.\d{1,2})",
        r"(\d{2,3}\.\d{1,2}).{0,40}?Midland Property Price Index",
    ]
    value = None
    for pattern in patterns:
        match = re.search(pattern, flat, flags=re.IGNORECASE)
        if match:
            candidate = float(match.group(1))
            if 60 <= candidate <= 220:
                value = candidate
                break
    if value is None:
        found: list[tuple[str, float]] = []
        for blob in blobs:
            _walk_numbers(blob, found)
        for key, candidate in found:
            if any(token in key for token in ("priceindex", "propertyindex", "indexvalue", "mpi")):
                if 60 <= candidate <= 220:
                    value = candidate
                    break
    require(value is not None, "Playwright could not find the Midland Property Price Index")
    check_value("midland", value)
    update = re.search(r"(\d{1,2}/\d{1,2}/20\d{2})\s*Update", flat, flags=re.IGNORECASE)
    require(update is not None, "Midland page is missing the update date")
    period = parse_period(update.group(1))
    require(period is not None, "Midland update date could not be parsed")
    require_recent(period, today, max_age_days=21)
    rows, verified = select_midland_rows(
        {
            "index_name": "Midland Property Price Index",
            "series_scope": "territory",
            "latest_value": value,
            "period_end": period.isoformat(),
            "is_price_per_sqft": False,
        },
        None,
        _stored_midland_values(),
        today,
        "playwright_fallback",
    )
    return rows, verified


def extract_rvd(today: date | None = None) -> dict[str, Any]:
    init_db()
    today = today or date.today()
    errors: list[str] = []
    for url in _candidate_urls("rvd"):
        try:
            extracted = firecrawl_extract(url, "rvd")
            confirmed, official = _accept_rvd(extracted, today)
            confirmed["source_path"] = "tavily_firecrawl"
            _store_rvd(confirmed, official, "rvd", extracted)
            return confirmed
        except (QualityGateError, requests.RequestException, ValueError) as exc:
            errors.append(f"{url}: {exc}")
            log_path("rvd", "firecrawl", "fail", f"{url} failed the quality gate: {exc}")
            logger.info("RVD Firecrawl attempt failed for %s: %s", url, exc)
    logger.info("RVD: Firecrawl failed, Playwright fallback")
    log_path("rvd", "playwright_fallback", "fallback", "Firecrawl failed; opening the official statistics page")
    try:
        confirmed, official, extracted = playwright_rvd(today)
        _store_rvd(confirmed, official, "rvd", extracted)
        return confirmed
    except (QualityGateError, requests.RequestException, Exception) as exc:
        detail = "; ".join(errors[-3:]) + f" | playwright: {exc}"
        log_path("rvd", "playwright_fallback", "fail", detail)
        raise QualityGateError(detail) from exc


def extract_midland(today: date | None = None) -> list[dict[str, Any]]:
    init_db()
    today = today or date.today()
    official_points = load_official_midland(today)
    stored_values = _stored_midland_values()
    errors: list[str] = []
    for url in _candidate_urls("midland"):
        try:
            extracted = firecrawl_extract(url, "midland")
            rows, verified = select_midland_rows(
                extracted,
                official_points,
                stored_values,
                today,
                "tavily_firecrawl",
            )
            _commit_midland(
                rows,
                verified=verified,
                source_path="tavily_firecrawl",
                url=str(extracted.get("_url") or url),
                extracted=extracted,
            )
            return rows
        except (QualityGateError, requests.RequestException, ValueError) as exc:
            errors.append(f"{url}: {exc}")
            log_path("midland", "firecrawl", "fail", f"{url} failed the quality gate: {exc}")
            logger.info("Midland Firecrawl attempt failed for %s: %s", url, exc)
    if official_points is not None:
        logger.info("Midland: Firecrawl did not match the territory-wide index; storing the published weekly series")
        log_path(
            "midland",
            "official_page",
            "fallback",
            "Firecrawl did not match the territory-wide Midland Property Price Index; storing that published series",
        )
        rows = observations_from_points(official_points, "official_page")
        _commit_midland(
            rows,
            verified=True,
            source_path="official_page",
            url=MIDLAND_SEED,
            extracted=None,
        )
        return rows
    logger.info("Midland: Firecrawl failed, Playwright fallback")
    log_path(
        "midland",
        "playwright_fallback",
        "fallback",
        "Firecrawl failed; opening the official market insight page",
    )
    try:
        rows, verified = playwright_midland(today)
        _commit_midland(
            rows,
            verified=verified,
            source_path="playwright_fallback",
            url=MIDLAND_SEED,
            extracted=None,
        )
        return rows
    except (QualityGateError, Exception) as exc:
        detail = "; ".join(errors[-3:]) + f" | playwright: {exc}"
        log_path("midland", "playwright_fallback", "fail", detail)
        raise QualityGateError(detail) from exc


def main() -> None:
    setup_logging()
    failed = False
    for label, runner in (("rvd", extract_rvd), ("midland", extract_midland)):
        try:
            runner()
        except QualityGateError as exc:
            failed = True
            logger.error("%s extraction failed: %s", label, exc)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
