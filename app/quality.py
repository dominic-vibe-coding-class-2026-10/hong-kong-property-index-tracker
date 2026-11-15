"""Quality gates and date parsing. Failed gates must not be written."""

from __future__ import annotations

import math
import re
from datetime import date, datetime

from app.config import VALUE_RANGES


class QualityGateError(Exception):
    """Raised when a reading is incomplete or implausible."""


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualityGateError(message)


def as_float(value: object) -> float:
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
    number = float(value)  # type: ignore[arg-type]
    require(math.isfinite(number), f"value is not finite: {value!r}")
    return number


def check_value(series_id: str, value: float) -> None:
    low, high = VALUE_RANGES[series_id]
    require(low <= value <= high, f"{series_id} value {value} is outside {low}–{high}")


def parse_period(text: object) -> date | None:
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None

    iso = re.search(r"(19\d{2}|20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", raw)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    dmy = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](19\d{2}|20\d{2})\b", raw)
    if dmy:
        return _safe_date(int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))

    chinese_day = re.search(r"(19\d{2}|20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})", raw)
    if chinese_day:
        return _safe_date(int(chinese_day.group(1)), int(chinese_day.group(2)), int(chinese_day.group(3)))

    year_month = re.search(r"(19\d{2}|20\d{2})\s*[-/年]\s*(\d{1,2})", raw)
    if year_month:
        return _safe_date(int(year_month.group(1)), int(year_month.group(2)), 1)

    month_year = re.search(r"\b(\d{1,2})[-/](19\d{2}|20\d{2})\b", raw)
    if month_year:
        return _safe_date(int(month_year.group(2)), int(month_year.group(1)), 1)

    named = re.search(
        r"\b([A-Za-z]{3,9})\.?\s+(19\d{2}|20\d{2})\b",
        raw,
    )
    if named and named.group(1).lower() in MONTHS:
        return _safe_date(int(named.group(2)), MONTHS[named.group(1).lower()], 1)

    chinese_month = re.search(r"(19\d{2}|20\d{2})\s*年\s*(\d{1,2})\s*月", raw)
    if chinese_month:
        return _safe_date(int(chinese_month.group(1)), int(chinese_month.group(2)), 1)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def require_recent(period: date, today: date, max_age_days: int) -> None:
    age = (today - period).days
    require(age >= -14, f"period {period.isoformat()} is too far in the future")
    require(age <= max_age_days, f"period {period.isoformat()} is older than {max_age_days} days")


def same_month(left: date, right: date) -> bool:
    return left.year == right.year and left.month == right.month


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
