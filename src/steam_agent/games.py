"""Helper per leggere la lista giochi del portfolio da config/games.yaml."""
from __future__ import annotations

import yaml

from steam_agent.settings import CONFIG_DIR


def load_games() -> list[dict]:
    """Ritorna la lista [{appid, name}, ...] da config/games.yaml (vuota se assente)."""
    path = CONFIG_DIR / "games.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("games") or []
