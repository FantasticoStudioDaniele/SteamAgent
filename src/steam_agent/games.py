"""Helper to read the portfolio game list from config/games.yaml."""
from __future__ import annotations

import yaml

from steam_agent.settings import settings


def load_games() -> list[dict]:
    """Returns the list [{appid, name}, ...] from the games catalog (empty if absent)."""
    path = settings.games_catalog_path
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("games") or []
