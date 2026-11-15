"""Bilingual dashboard for the three property indices."""

from __future__ import annotations

import csv
import io

from flask import Flask, Response, jsonify, render_template

from app.config import ROOT, SERIES
from app.db import (
    init_db,
    latest_insights,
    latest_observations,
    observation_count,
    recent_logs,
    series_rows,
)

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)

DOWNLOAD_NAMES = {
    "ccl": "centa-city-leading-index.csv",
    "rvd": "rating-and-valuation-department-private-domestic-price-index.csv",
    "midland": "midland-realty-property-price-index.csv",
}


def _change(latest: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return (latest - previous) / previous * 100


@app.route("/")
def index():
    init_db()
    return render_template("index.html")


@app.route("/api/dashboard")
def dashboard_data():
    init_db()
    insights = latest_insights()
    cards = []
    for series_id, meta in SERIES.items():
        rows = latest_observations(series_id, limit=2)
        latest = rows[0] if rows else None
        previous = rows[1] if len(rows) > 1 else None
        cards.append(
            {
                "id": series_id,
                "name_en": meta["name_en"],
                "name_zh": meta["name_zh"],
                "base_en": meta["base_en"],
                "base_zh": meta["base_zh"],
                "frequency": meta["frequency"],
                "source_url": meta["source_url"],
                "latest_value": None if latest is None else latest["value"],
                "latest_date": None if latest is None else latest["period_date"],
                "period_label": None if latest is None else (latest["period_label"] or latest["period_date"]),
                "source_path": None if latest is None else latest["source_path"],
                "note": None if latest is None else latest["raw_note"],
                "change_pct": None
                if latest is None
                else _change(latest["value"], None if previous is None else previous["value"]),
                "count": observation_count(series_id),
                "download": f"/download/{series_id}.csv",
            }
        )
    history = [
        {"date": row["period_date"], "value": row["value"]}
        for row in series_rows("ccl")
    ]
    return jsonify(
        {
            "series": cards,
            "ccl_history": history,
            "insights": {language: row["text"] for language, row in insights.items()},
            "insight_at": None if not insights else max(row["created_at"] for row in insights.values()),
            "evidence": [dict(row) for row in recent_logs(12)],
        }
    )


@app.route("/download/<series_id>.csv")
def download(series_id: str):
    init_db()
    meta = SERIES.get(series_id)
    if meta is None:
        return Response("Unknown series", status=404)
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        ["series_name_en", "series_name_zh", "period_date", "period_label", "value", "source_path", "note", "updated_at"]
    )
    for row in series_rows(series_id):
        writer.writerow(
            [
                meta["name_en"],
                meta["name_zh"],
                row["period_date"],
                row["period_label"] or "",
                row["value"],
                row["source_path"],
                row["raw_note"] or "",
                row["updated_at"],
            ]
        )
    filename = DOWNLOAD_NAMES[series_id]
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def main() -> None:
    init_db()
    app.run(host="127.0.0.1", port=5050, debug=False)


if __name__ == "__main__":
    main()
