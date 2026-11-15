"""SQLite access for series, observations, insights, and path logs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.config import DATA_DIR, DB_PATH, EVIDENCE_DIR, SCHEMA_PATH, SERIES


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema)
        for series_id, meta in SERIES.items():
            conn.execute(
                """
                INSERT INTO series (id, name_en, name_zh, frequency, source_url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name_en = excluded.name_en,
                    name_zh = excluded.name_zh,
                    frequency = excluded.frequency,
                    source_url = excluded.source_url
                """,
                (
                    series_id,
                    meta["name_en"],
                    meta["name_zh"],
                    meta["frequency"],
                    meta["source_url"],
                ),
            )


def log_path(series_id: str | None, step: str, status: str, detail: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO path_logs (created_at, series_id, step, status, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (utc_now(), series_id, step, status, detail),
        )


def write_evidence(name: str, payload: dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_observations(series_id: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = utc_now()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO observations (
                series_id, period_date, period_label, value, source_path, raw_note, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id, period_date) DO UPDATE SET
                period_label = excluded.period_label,
                value = excluded.value,
                source_path = excluded.source_path,
                raw_note = excluded.raw_note,
                updated_at = excluded.updated_at
            """,
            [
                (
                    series_id,
                    row["period_date"],
                    row.get("period_label"),
                    float(row["value"]),
                    row["source_path"],
                    row.get("raw_note"),
                    now,
                )
                for row in rows
            ],
        )
    return len(rows)


def latest_observations(series_id: str, limit: int = 2) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                """
                SELECT period_date, period_label, value, source_path, raw_note
                FROM observations
                WHERE series_id = ?
                ORDER BY period_date DESC
                LIMIT ?
                """,
                (series_id, limit),
            )
        )


def observation_count(series_id: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM observations WHERE series_id = ?",
            (series_id,),
        ).fetchone()
    return int(row["n"])


def series_rows(series_id: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                """
                SELECT period_date, period_label, value, source_path, raw_note, updated_at
                FROM observations
                WHERE series_id = ?
                ORDER BY period_date
                """,
                (series_id,),
            )
        )


def save_insight(language: str, text: str, model: str, payload: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO insights (created_at, language, text, model, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (utc_now(), language, text, model, json.dumps(payload, ensure_ascii=False)),
        )


def latest_insights() -> dict[str, sqlite3.Row]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT language, text, model, created_at
            FROM insights
            WHERE id IN (SELECT MAX(id) FROM insights GROUP BY language)
            """
        ).fetchall()
    return {row["language"]: row for row in rows}


def recent_logs(limit: int = 12) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(
            conn.execute(
                """
                SELECT created_at, series_id, step, status, detail
                FROM path_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
        )
