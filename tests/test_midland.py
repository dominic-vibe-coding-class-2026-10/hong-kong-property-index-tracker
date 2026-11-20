"""The Midland series stays on one level: the territory-wide weekly index."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.config import MIDLAND_SEED
from app.midland import (
    assert_compatible_with_stored,
    assert_same_level,
    disagreement_count,
    parse_weekly_index,
    select_midland_rows,
    stored_is_mixed,
    validate_weekly,
)
from app.quality import QualityGateError

TODAY = date(2026, 11, 20)

# Official All / 全港 readings published on the market-insight page.
OFFICIAL_RECENT = [
    ("2026-10-05", 148.7),
    ("2026-10-12", 148.9),
    ("2026-10-19", 149.1),
    ("2026-10-26", 148.8),
    ("2026-11-02", 148.0),
    ("2026-11-09", 148.1),
    ("2026-11-16", 147.9),
]

# The other cluster written on 16 Nov 2026. It is not the territory-wide index.
OTHER_CLUSTER = [
    ("2026-10-09", 110.4),
    ("2026-10-16", 110.7),
    ("2026-10-23", 110.3),
    ("2026-10-30", 110.5),
    ("2026-11-09", 110.9),
]


def _weekly_page(points: list[tuple[str, float]], district: float = 156.2) -> str:
    weekly = []
    for period, value in points:
        weekly.append(
            {
                "date": f"{period}T00:00:00.000Z",
                "mr_index": value,
                "mr_index_hk": district,
                "mr_index_kln": 155.2,
                "mr_index_nt": 133.7,
            }
        )
    payload = {"props": {"pageProps": {"mrIndexWeekly": weekly, "confidenceIndex": [{"confidence_index": 67.0}]}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'


def _mondays(count: int, end: date = date(2026, 11, 16), level: float = 148.0) -> list[tuple[str, float]]:
    points = []
    for offset in range(count - 1, -1, -1):
        period = date.fromordinal(end.toordinal() - 7 * offset)
        # Drift by less than a point so the series stays one level.
        points.append((period.isoformat(), round(level + (offset % 5) * 0.1, 1)))
    return points


class MidlandSeriesTests(unittest.TestCase):
    def test_parser_keeps_territory_index_only(self) -> None:
        points = parse_weekly_index(_weekly_page(OFFICIAL_RECENT))
        self.assertEqual([(point["period_date"], point["value"]) for point in points], OFFICIAL_RECENT)

    def test_same_level_rejects_the_mixed_clusters(self) -> None:
        mixed = [value for _period, value in OFFICIAL_RECENT + OTHER_CLUSTER]
        with self.assertRaises(QualityGateError):
            assert_same_level(mixed)

    def test_same_level_accepts_the_official_band(self) -> None:
        assert_same_level([value for _period, value in OFFICIAL_RECENT])

    def test_stored_mix_matches_the_live_database(self) -> None:
        live = [value for _period, value in OFFICIAL_RECENT[:5] + OTHER_CLUSTER]
        self.assertTrue(stored_is_mixed(live))
        self.assertFalse(stored_is_mixed([value for _period, value in OFFICIAL_RECENT]))

    def test_unverified_reading_uses_the_recent_level_not_the_old_median(self) -> None:
        history = [170.0] * 40 + [148.5] * 8
        current = {
            "index_name": "Midland Property Price Index",
            "series_scope": "territory",
            "latest_value": 147.9,
            "period_end": "2026-11-16",
        }
        rows, verified = select_midland_rows(current, None, history, TODAY, "playwright_fallback")
        self.assertFalse(verified)
        self.assertEqual(rows[-1]["value"], 147.9)
        other = dict(current, latest_value=110.9, period_end="2026-11-09")
        with self.assertRaises(QualityGateError):
            select_midland_rows(other, None, history, TODAY, "playwright_fallback")

    def test_unverified_110_is_not_written_beside_148(self) -> None:
        stored = [value for _period, value in OFFICIAL_RECENT]
        with self.assertRaises(QualityGateError):
            assert_compatible_with_stored([110.9], stored)

    def test_unverified_extract_is_refused_when_storage_is_already_mixed(self) -> None:
        stored = [value for _period, value in OFFICIAL_RECENT[:5] + OTHER_CLUSTER]
        extracted = {
            "index_name": "Midland Property Price Index",
            "series_scope": "territory",
            "latest_value": 110.9,
            "period_end": "2026-11-09",
            "recent_points": [{"period_end": period, "value": value} for period, value in OTHER_CLUSTER],
        }
        with self.assertRaises(QualityGateError):
            select_midland_rows(extracted, None, stored, TODAY, "tavily_firecrawl")

    def test_matching_headline_stores_official_series_not_the_other_cluster(self) -> None:
        official = [{"period_date": period, "value": value} for period, value in _mondays(40)]
        extracted = {
            "index_name": "Midland Property Price Index",
            "series_scope": "territory",
            "latest_value": official[-1]["value"],
            "period_end": official[-1]["period_date"],
            "recent_points": [{"period_end": period, "value": value} for period, value in OTHER_CLUSTER],
        }
        rows, verified = select_midland_rows(extracted, official, [], TODAY, "tavily_firecrawl")
        self.assertTrue(verified)
        self.assertEqual([row["period_date"] for row in rows], [point["period_date"] for point in official])
        self.assertTrue(all(row["value"] >= 140 for row in rows))
        self.assertNotIn("2026-10-09", [row["period_date"] for row in rows])

    def test_110_headline_does_not_match_the_official_index(self) -> None:
        official = [{"period_date": period, "value": value} for period, value in _mondays(40)]
        extracted = {
            "index_name": "Midland Property Price Index",
            "series_scope": "territory",
            "latest_value": 110.9,
            "period_end": "2026-11-09",
            "recent_points": [{"period_end": period, "value": value} for period, value in OTHER_CLUSTER],
        }
        with self.assertRaises(QualityGateError) as caught:
            select_midland_rows(extracted, official, [], TODAY, "tavily_firecrawl")
        self.assertIn("110.9", str(caught.exception))
        self.assertIn(str(official[-1]["value"]), str(caught.exception))

    def test_district_and_confidence_names_are_rejected(self) -> None:
        official = [{"period_date": period, "value": value} for period, value in _mondays(40)]
        for name in ("Midland Hong Kong Island Price Index", "Midland Confidence Index"):
            extracted = {
                "index_name": name,
                "series_scope": "territory",
                "latest_value": official[-1]["value"],
                "period_end": official[-1]["period_date"],
            }
            with self.assertRaises(QualityGateError):
                select_midland_rows(extracted, official, [], TODAY, "tavily_firecrawl")

    def test_weekly_spacing_rejects_an_interleaved_calendar(self) -> None:
        points = []
        start = date(2026, 2, 2)  # Monday
        for week in range(40):
            monday = date.fromordinal(start.toordinal() + 7 * week)
            friday = date.fromordinal(monday.toordinal() + 4)
            points.append({"period_date": monday.isoformat(), "value": 148.0})
            points.append({"period_date": friday.isoformat(), "value": 110.5})
        points.sort(key=lambda point: point["period_date"])
        with self.assertRaises(QualityGateError):
            validate_weekly(points, TODAY)

    def test_disagreement_count_flags_the_110_dates(self) -> None:
        stored = [{"period_date": period, "value": value} for period, value in OFFICIAL_RECENT[:5] + OTHER_CLUSTER]
        new_rows = [{"period_date": period, "value": value} for period, value in OFFICIAL_RECENT]
        # Four Friday points are absent, and 9 Nov disagrees (110.9 vs 148.1).
        self.assertEqual(disagreement_count(stored, new_rows), 5)

    def test_replace_drops_the_other_cluster_and_leaves_other_series(self) -> None:
        from app import db

        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "indices.sqlite"
            with patch.object(db, "DB_PATH", database):
                db.init_db()
                db.upsert_observations(
                    "midland",
                    [
                        {
                            "period_date": period,
                            "period_label": period,
                            "value": value,
                            "source_path": "tavily_firecrawl",
                            "raw_note": None,
                        }
                        for period, value in OFFICIAL_RECENT[:5] + OTHER_CLUSTER
                    ],
                )
                db.upsert_observations(
                    "ccl",
                    [
                        {
                            "period_date": "2026-11-08",
                            "period_label": "2026-11-02 – 2026-11-08",
                            "value": 158.61,
                            "source_path": "playwright_weekly",
                            "raw_note": None,
                        }
                    ],
                )
                replacement = [
                    {
                        "period_date": period,
                        "period_label": period,
                        "value": value,
                        "source_path": "official_page",
                        "raw_note": None,
                    }
                    for period, value in OFFICIAL_RECENT
                ]
                db.replace_observations("midland", replacement)
                stored = [(row["period_date"], row["value"]) for row in db.series_rows("midland")]
                self.assertEqual(stored, OFFICIAL_RECENT)
                self.assertEqual(db.series_rows("ccl")[0]["value"], 158.61)
                self.assertEqual(db.replace_observations("midland", []), 0)
                self.assertEqual(len(db.series_rows("midland")), len(OFFICIAL_RECENT))

    def test_seed_url_stays_ahead_of_a_discovered_homepage(self) -> None:
        from app.adaptive import _candidate_urls

        discovered = ["https://www.midland.com.hk/en"]
        with patch("app.adaptive.tavily_urls", return_value=discovered):
            urls = _candidate_urls("midland")
        self.assertEqual(urls[0], MIDLAND_SEED)
        self.assertIn("https://www.midland.com.hk/en", urls)


if __name__ == "__main__":
    unittest.main()
