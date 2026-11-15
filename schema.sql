PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS series (
    id TEXT PRIMARY KEY,
    name_en TEXT NOT NULL,
    name_zh TEXT NOT NULL,
    frequency TEXT NOT NULL,
    source_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    series_id TEXT NOT NULL REFERENCES series(id),
    period_date TEXT NOT NULL,
    period_label TEXT,
    value REAL NOT NULL,
    source_path TEXT NOT NULL,
    raw_note TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (series_id, period_date)
);

CREATE INDEX IF NOT EXISTS idx_observations_series_date
    ON observations (series_id, period_date);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    model TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS path_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    series_id TEXT,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT
);
