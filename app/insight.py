"""Comparison insight from Ollama Cloud, in English and Traditional Chinese."""

from __future__ import annotations

import json
import logging
import re

import requests

from app.config import OLLAMA_URL, OUTPUT_MD, SERIES, env, setup_logging
from app.db import init_db, latest_observations, log_path, save_insight, utc_now, write_evidence
from app.quality import QualityGateError, require

logger = logging.getLogger(__name__)


def _payload() -> dict:
    snapshot = []
    for series_id, meta in SERIES.items():
        rows = latest_observations(series_id, limit=2)
        require(rows, f"no stored readings for {meta['name_en']}")
        latest = rows[0]
        previous = rows[1] if len(rows) > 1 else None
        item = {
            "name_en": meta["name_en"],
            "name_zh": meta["name_zh"],
            "base_en": meta["base_en"],
            "frequency": meta["frequency"],
            "latest_value": latest["value"],
            "latest_period": latest["period_label"] or latest["period_date"],
            "previous_value": None if previous is None else previous["value"],
            "previous_period": None if previous is None else (previous["period_label"] or previous["period_date"]),
        }
        snapshot.append(item)
    return {"indices": snapshot}


def _messages(language: str, payload: dict) -> list[dict[str, str]]:
    if language == "zh-Hant":
        instruction = (
            "用香港繁體中文寫一段80到120字的比較。使用這些全名："
            "中原城市領先指數、差餉物業估價署私人住宅售價指數、美聯物業樓價指數。"
            "不要用簡稱。說明三個指數基期不同，點數不能直接比較。"
            "只根據提供的數字描述最新水平與上一期變化。不要給投資建議。"
        )
    else:
        instruction = (
            "Write 80 to 120 words in English. Use these full names: "
            "Centa-City Leading Index, Rating and Valuation Department Private Domestic "
            "Price Index, and Midland Realty Property Price Index. Do not abbreviate them. "
            "Say that the indices use different base periods, so the levels are not directly "
            "comparable. Describe the latest level and the change from the previous reading "
            "using only the numbers provided. Do not give investment advice."
        )
    return [
        {
            "role": "system",
            "content": "You write a short factual note for a Hong Kong property analyst.",
        },
        {
            "role": "user",
            "content": instruction + "\n\nData:\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def _call_ollama(language: str, payload: dict) -> str:
    key = env("OLLAMA_API_KEY")
    model = env("OLLAMA_MODEL") or "kimi-k3.1-pro"
    require(bool(key), "OLLAMA_API_KEY is missing")
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "temperature": 0.2,
            "messages": _messages(language, payload),
        },
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    message = (body.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    text = _strip_thinking(str(content))
    require(len(text) >= 40, f"Ollama returned too little text for {language}")
    return text


def _write_markdown(payload: dict, texts: dict[str, str], model: str) -> None:
    lines = [
        "# Index comparison insight",
        "",
        f"Generated: {utc_now()}",
        f"Model: {model}",
        "",
        "## English",
        "",
        texts["en"],
        "",
        "## 繁體中文",
        "",
        texts["zh-Hant"],
        "",
        "## Latest values",
        "",
        "| Index | Period | Value | Previous |",
        "| --- | --- | --- | --- |",
    ]
    for item in payload["indices"]:
        lines.append(
            f"| {item['name_en']} | {item['latest_period']} | {item['latest_value']} | {item['previous_value']} |"
        )
    lines.append("")
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def generate_insight() -> dict[str, str]:
    init_db()
    payload = _payload()
    model = env("OLLAMA_MODEL") or "kimi-k3.1-pro"
    texts = {}
    for language in ("en", "zh-Hant"):
        logger.info("Requesting %s insight from Ollama Cloud (%s)", language, model)
        texts[language] = _call_ollama(language, payload)
        save_insight(language, texts[language], model, payload)
    _write_markdown(payload, texts, model)
    log_path("ccl", "ollama", "ok", f"Saved English and Traditional Chinese insights with {model}")
    write_evidence(
        "insight",
        {"path": "ollama", "model": model, "url": OLLAMA_URL, "texts": texts, "payload": payload},
    )
    logger.info("Wrote %s", OUTPUT_MD)
    return texts


def main() -> None:
    setup_logging()
    try:
        generate_insight()
    except (QualityGateError, requests.RequestException) as exc:
        init_db()
        log_path(None, "ollama", "fail", str(exc))
        logger.error("Insight generation failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
