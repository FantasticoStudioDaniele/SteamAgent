"""Interfaccia comune dei collector + record grezzo."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RawRecord:
    """Un payload grezzo raccolto da una fonte, prima della normalizzazione."""

    source: str  # es. "store_appdetails"
    key: str  # identificatore logico, es. "appid:440"
    payload: dict[str, Any]
    app_id: int | None = None
    collected_at: datetime = field(default_factory=utcnow)


class Collector(ABC):
    """Ogni collector raccoglie da una fonte e restituisce record grezzi."""

    name: str

    @abstractmethod
    def collect(self) -> list[RawRecord]:
        ...
