"""Reviews collector from the PUBLIC appreviews API (no authentication).

For each app it pages through the reviews (filter=recent, 100/page) via cursor and
extracts text + vote + metadata, the basis for sentiment/themes via LLM (Phase 5).
Endpoint: https://store.steampowered.com/appreviews/<appid>?json=1&...
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from steam_agent.collectors.base import utcnow

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0)
_HEADERS = {"User-Agent": "steam-agent/0.1 (+local research tool)"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _get_json(client: httpx.Client, url: str, params: dict[str, Any]) -> Any:
    resp = client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def _parse_review(r: dict, app_id: int) -> dict:
    author = r.get("author") or {}
    ts = r.get("timestamp_created")
    return {
        "recommendation_id": str(r.get("recommendationid")),
        "app_id": app_id,
        "language": r.get("language"),
        "voted_up": bool(r.get("voted_up")),
        "votes_up": int(r.get("votes_up") or 0),
        "votes_funny": int(r.get("votes_funny") or 0),
        "playtime_at_review_min": author.get("playtime_at_review"),
        "created_at": datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
        "review_text": r.get("review"),
        "collected_at": utcnow(),
    }


def fetch_reviews(app_id: int, max_reviews: int = 2000) -> list[dict]:
    """Page through the reviews (chronological) up to `max_reviews` and return them."""
    out: list[dict] = []
    cursor = "*"
    seen: set[str] = set()
    url = f"https://store.steampowered.com/appreviews/{app_id}"
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
        while len(out) < max_reviews:
            params = {
                "json": 1,
                "filter": "recent",
                "language": "all",
                "num_per_page": 100,
                "cursor": cursor,
                "purchase_type": "all",
                "review_type": "all",
            }
            try:
                data = _get_json(client, url, params)
            except Exception as exc:  # noqa: BLE001
                log.warning("appreviews appid %s: %s", app_id, exc)
                break
            reviews = data.get("reviews") or []
            if not reviews:
                break
            out.extend(_parse_review(r, app_id) for r in reviews)
            cursor = data.get("cursor") or ""
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
            time.sleep(0.3)
    return out[:max_reviews]
