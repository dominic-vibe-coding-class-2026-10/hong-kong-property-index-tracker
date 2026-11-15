"""Paths, series names, and environment."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
EVIDENCE_DIR = ROOT / "evidence"
DB_PATH = DATA_DIR / "indices.sqlite"
OUTPUT_MD = ROOT / "output.md"
SCHEMA_PATH = ROOT / "schema.sql"

load_dotenv(ROOT / ".env")

CCL_PAGE = "https://hk.centanet.com/CCI/index"
CCL_HISTORY_API = "https://hk.centanet.com/CCI/api/Index/CCLChart"

RVD_SEED_PAGE = "https://www.rvd.gov.hk/en/publications/property_market_statistics.html"
RVD_SEED_CSV = "https://www.rvd.gov.hk/datagovhk/1.4M.csv"
MIDLAND_SEED = "https://www.midland.com.hk/en/market-insight/"

OLLAMA_URL = "https://ollama.com/v1/chat/completions"
TAVILY_URL = "https://api.tavily.com/search"
FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SERIES = {
    "ccl": {
        "name_en": "Centa-City Leading Index",
        "name_zh": "中原城市領先指數",
        "frequency": "weekly",
        "source_url": CCL_PAGE,
        "base_en": "July 1997 = 100",
        "base_zh": "1997年7月 = 100",
    },
    "rvd": {
        "name_en": "Rating and Valuation Department Private Domestic Price Index",
        "name_zh": "差餉物業估價署私人住宅售價指數",
        "frequency": "monthly",
        "source_url": RVD_SEED_PAGE,
        "base_en": "1999 = 100",
        "base_zh": "1999年 = 100",
    },
    "midland": {
        "name_en": "Midland Realty Property Price Index",
        "name_zh": "美聯物業樓價指數",
        "frequency": "weekly",
        "source_url": MIDLAND_SEED,
        "base_en": "Published index points",
        "base_zh": "公布指數點",
    },
}

VALUE_RANGES = {
    "ccl": (20.0, 250.0),
    "rvd": (40.0, 500.0),
    "midland": (60.0, 220.0),
}


def env(name: str) -> str:
    return os.getenv(name, "").strip()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
