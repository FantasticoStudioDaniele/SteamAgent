"""Collector for the PUBLIC Steam sources (no authentication required).

- store appdetails: metadata, price, tags, release date
- appreviews (summary): positive/negative review count + rating
- GetNumberOfCurrentPlayers: real-time concurrent players
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from steam_agent.collectors.base import Collector, RawRecord

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(20.0)
_HEADERS = {"User-Agent": "steam-agent/0.1 (+local research tool)"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _get_json(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> Any:
    resp = client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


class PublicApiCollector(Collector):
    name = "public_api"

    def __init__(self, app_id: int):
        self.app_id = app_id

    def collect(self) -> list[RawRecord]:
        records: list[RawRecord] = []
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS) as client:
            self._collect_appdetails(client, records)
            self._collect_reviews(client, records)
            self._collect_players(client, records)
        return records

    def _collect_appdetails(self, client: httpx.Client, out: list[RawRecord]) -> None:
        try:
            data = _get_json(
                client,
                "https://store.steampowered.com/api/appdetails",
                {"appids": self.app_id, "l": "english"},
            )
            entry = data.get(str(self.app_id), {})
            if entry.get("success"):
                out.append(RawRecord("store_appdetails", f"appid:{self.app_id}",
                                     entry["data"], self.app_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("appdetails failed for %s: %s", self.app_id, exc)

    def _collect_reviews(self, client: httpx.Client, out: list[RawRecord]) -> None:
        try:
            data = _get_json(
                client,
                f"https://store.steampowered.com/appreviews/{self.app_id}",
                {"json": 1, "num_per_page": 0, "language": "all",
                 "purchase_type": "all", "filter": "summary"},
            )
            if data.get("success") == 1:
                out.append(RawRecord("appreviews_summary", f"appid:{self.app_id}",
                                     data.get("query_summary", {}), self.app_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("appreviews failed for %s: %s", self.app_id, exc)

    def _collect_players(self, client: httpx.Client, out: list[RawRecord]) -> None:
        try:
            data = _get_json(
                client,
                "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
                {"appid": self.app_id},
            )
            resp = data.get("response", {})
            if resp.get("result") == 1:
                out.append(RawRecord("current_players", f"appid:{self.app_id}",
                                     {"player_count": resp.get("player_count")}, self.app_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("current_players failed for %s: %s", self.app_id, exc)
