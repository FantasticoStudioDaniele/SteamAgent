"""Per-run tally of schema-drift events, surfaced by the CLI.

This is module-level state for a single CLI invocation (the tool runs one
collection at a time): the CLI calls `reset()` before a run and reads `had_drift()`
/ `drift_events()` after. Drift is the human-attention outcome — a run with any
drift should exit non-zero so an unattended scheduler notices a layout change
(retrying won't help, unlike a transient failure).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_drift: list[str] = []


def reset() -> None:
    _drift.clear()


def record_drift(source: str, detail: str, artifact: str | None = None) -> None:
    """Log a loud, unmistakable drift line and remember it for the run summary."""
    suffix = f" — artifact: {artifact}" if artifact else ""
    log.error("SCHEMA DRIFT [%s]: %s%s", source, detail, suffix)
    _drift.append(f"{source}: {detail}")


def drift_events() -> list[str]:
    return list(_drift)


def had_drift() -> bool:
    return bool(_drift)
