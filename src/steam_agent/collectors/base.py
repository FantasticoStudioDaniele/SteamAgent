"""Common collector interface + raw record."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RawRecord:
    """A raw payload collected from a source, before normalization."""

    source: str  # e.g. "store_appdetails"
    key: str  # logical identifier, e.g. "appid:440"
    payload: dict[str, Any]
    app_id: int | None = None
    collected_at: datetime = field(default_factory=utcnow)


class Collector(ABC):
    """Each collector collects from a source and returns raw records."""

    name: str

    @abstractmethod
    def collect(self) -> list[RawRecord]:
        ...
