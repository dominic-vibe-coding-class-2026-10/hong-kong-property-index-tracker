"""Territory-wide Midland Property Price Index.

The market-insight page publishes one weekly series for all of Hong Kong
(`mrIndexWeekly[].mr_index`, the "All" / 全港 figure, 美聯樓價指數). District
indices, the confidence index, and other charts on the same page are different
series. A scrape that lands on one of those must not be written beside the
territory-wide index.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from app.quality import QualityGateError, as_float, check_value, parse_period, require, require_recent

# Largest week-to-week move in the published weekly series from 2016 through
# November 2026 is 2.7 points. The mixed chart was two levels about 38 points
# apart, so 8 points still accepts a real move and rejects a second series.
MIDLAND_LEVEL_GAP = 8.0
# Firecrawl often rounds the headline. District indices sit well outside this.
MIDLAND_OFFICIAL_TOLERANCE = 1.5
MIDLAND_MIN_POINTS = 30

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

WRONG_NAME_MARKERS = (
    "island",
    "kowloon",
    "new territories",
    "港島",
    "九龍",
    "新界",
    "confidence",
    "信心",
    "dollar",
    "美匯",
    "hang seng",
    "恒生",
    "恆生",
    "affordability",
    "負擔",
    "sqft",
    "sq ft",
    "square foot",
    "呎價",
)


def level_clusters(values: list[float], max_gap: float = MIDLAND_LEVEL_GAP) -> list[list[float]]:
    """Split readings into levels. A gap wider than max_gap starts a new level."""
    if not values:
        return []
    ordered = sorted(float(value) for value in values)
    groups: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - groups[-1][-1] > max_gap:
            groups.append([value])
        else:
            groups[-1].append(value)
    return groups


def assert_same_level(values: list[float], max_gap: float = MIDLAND_LEVEL_GAP) -> None:
    require(bool(values), "Midland extraction has no readings")
    groups = level_clusters(values, max_gap)
    if len(groups) > 1:
        raise QualityGateError(
            f"Midland readings mix incompatible levels ({groups[0][-1]:.1f} and {groups[1][0]:.1f})"
        )


def stored_is_mixed(values: list[float], max_gap: float = MIDLAND_LEVEL_GAP) -> bool:
    """True when two substantial clusters are already stored together."""
    groups = level_clusters(values, max_gap)
    if len(groups) < 2:
        return False
    groups.sort(key=len, reverse=True)
    return len(groups[1]) >= 3 and len(groups[1]) * 2 >= len(groups[0])


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def assert_compatible_with_stored(
    new_values: list[float],
    stored_values: list[float],
    max_gap: float = MIDLAND_LEVEL_GAP,
) -> None:
    """Refuse an unverified reading that would sit beside a different level.

    A verified official series is stored with a replace, not this check.
    """
    assert_same_level(new_values, max_gap)
    if not stored_values:
        return
    if stored_is_mixed(stored_values, max_gap):
        raise QualityGateError(
            "Stored Midland readings already mix two levels; refusing an unverified extract"
        )
    groups = level_clusters(stored_values, max_gap)
    reference = _median(max(groups, key=len))
    incoming = _median(new_values)
    if abs(incoming - reference) > max_gap:
        raise QualityGateError(
            f"Midland value {incoming:.1f} is incompatible with the stored series level {reference:.1f}"
        )


def disagreement_count(
    stored: list[Any],
    new_rows: list[dict[str, Any]],
    tolerance: float = 0.05,
) -> int:
    """How many stored points are missing from the new series or disagree with it."""
    new_by_date = {row["period_date"]: float(row["value"]) for row in new_rows}
    count = 0
    for row in stored:
        updated = new_by_date.get(row["period_date"])
        if updated is None or abs(float(row["value"]) - updated) > tolerance:
            count += 1
    return count


def parse_weekly_index(html: str) -> list[dict[str, Any]]:
    """Read the territory-wide weekly index from the market-insight page.

    Only `mr_index` is kept. `mr_index_hk`, `mr_index_kln`, and `mr_index_nt`
    are district sub-indices and are ignored.
    """
    match = _NEXT_DATA.search(html)
    require(match is not None, "Midland page has no published index payload")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise QualityGateError("Midland page index payload is not valid JSON") from exc
    weekly = payload.get("props", {}).get("pageProps", {}).get("mrIndexWeekly")
    require(isinstance(weekly, list) and weekly, "Midland page has no weekly property price index")
    points: list[dict[str, Any]] = []
    for item in weekly:
        if not isinstance(item, dict) or item.get("mr_index") is None:
            continue
        period = parse_period(str(item.get("date") or "")[:10])
        if period is None:
            continue
        points.append({"period_date": period.isoformat(), "value": as_float(item["mr_index"])})
    require(points, "Midland weekly index payload had no territory-wide readings")
    deduped: dict[str, dict[str, Any]] = {}
    for point in points:
        deduped[point["period_date"]] = point
    return [deduped[key] for key in sorted(deduped)]


def validate_weekly(points: list[dict[str, Any]], today: date) -> None:
    require(
        len(points) >= MIDLAND_MIN_POINTS,
        f"Midland weekly series has only {len(points)} points",
    )
    previous: date | None = None
    values: list[float] = []
    for point in points:
        value = as_float(point["value"])
        check_value("midland", value)
        period = date.fromisoformat(point["period_date"])
        if previous is not None:
            gap_days = (period - previous).days
            require(
                5 <= gap_days <= 21,
                f"Midland weekly dates {previous.isoformat()} and {period.isoformat()} are {gap_days} days apart",
            )
        previous = period
        values.append(value)
    assert_same_level(values)
    require_recent(date.fromisoformat(points[-1]["period_date"]), today, max_age_days=21)


def observations_from_points(points: list[dict[str, Any]], source_path: str) -> list[dict[str, Any]]:
    return [
        {
            "period_date": point["period_date"],
            "period_label": point["period_date"],
            "value": float(point["value"]),
            "source_path": source_path,
            "raw_note": None,
        }
        for point in points
    ]


def reject_wrong_midland_extract(extracted: dict[str, Any]) -> None:
    if extracted.get("is_price_per_sqft") is True:
        raise QualityGateError("midland extraction is a price per square foot")
    scope = str(extracted.get("series_scope") or "").lower()
    name = str(extracted.get("index_name") or "").lower()
    if scope == "district" or any(marker in name for marker in WRONG_NAME_MARKERS):
        raise QualityGateError(f"midland extraction is a different series: {name or scope}")


def _row(period: date, value: float, source_path: str) -> dict[str, Any]:
    return {
        "period_date": period.isoformat(),
        "period_label": period.isoformat(),
        "value": value,
        "source_path": source_path,
        "raw_note": None,
    }


def _latest_official(points: list[dict[str, Any]]) -> dict[str, Any]:
    return points[-1]


def select_midland_rows(
    extracted: dict[str, Any],
    official_points: list[dict[str, Any]] | None,
    stored_values: list[float],
    today: date,
    source_path: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Choose what to store.

    Returns rows and whether they are the verified territory-wide weekly series.
    A verified series replaces stored Midland rows. An unverified extract is
    only the headline (plus recent points of that same level) and is refused
    when it does not match the series already stored.
    """
    reject_wrong_midland_extract(extracted)
    if official_points:
        validate_weekly(official_points, today)
        latest = _latest_official(official_points)
        value = as_float(extracted.get("latest_value"))
        check_value("midland", value)
        period = parse_period(extracted.get("period_end"))
        require(period is not None, "Midland extraction has no readable date")
        require_recent(period, today, max_age_days=21)
        official_date = date.fromisoformat(latest["period_date"])
        matches_value = abs(value - float(latest["value"])) <= MIDLAND_OFFICIAL_TOLERANCE
        matches_date = abs((period - official_date).days) <= 14
        require(
            matches_value and matches_date,
            (
                f"Midland extraction {value} on {period.isoformat()} does not match the "
                f"territory-wide Midland Property Price Index {latest['value']} "
                f"on {latest['period_date']}"
            ),
        )
        rows = observations_from_points(official_points, source_path)
        assert_same_level([row["value"] for row in rows])
        return rows, True

    value = as_float(extracted.get("latest_value"))
    check_value("midland", value)
    period = parse_period(extracted.get("period_end"))
    require(period is not None, "Midland extraction has no readable date")
    require_recent(period, today, max_age_days=21)
    rows = [_row(period, value, source_path)]
    for point in extracted.get("recent_points") or []:
        if not isinstance(point, dict):
            continue
        try:
            point_value = as_float(point.get("value"))
            check_value("midland", point_value)
            point_date = parse_period(point.get("period_end"))
            if point_date is None:
                continue
            require_recent(point_date, today, max_age_days=120)
        except (QualityGateError, TypeError, ValueError):
            continue
        if abs(point_value - value) > MIDLAND_LEVEL_GAP:
            continue
        rows.append(_row(point_date, point_value, source_path))
    deduped = {row["period_date"]: row for row in rows}
    chosen = [deduped[key] for key in sorted(deduped)]
    if stored_is_mixed(stored_values):
        raise QualityGateError(
            "Stored Midland readings already mix two levels; refusing an unverified extract"
        )
    # Compare with the latest stored readings. The index's level years ago is a
    # different point on the same series, not a reason to reject this week's figure.
    recent = stored_values[-8:] if stored_values else []
    assert_compatible_with_stored([row["value"] for row in chosen], recent)
    return chosen, False
