"""Persist a debugging artifact when a scrape fails, so a "broke for me" report
becomes inspectable. Two modes:

- page-navigation failures (DOM/JS scrape): a screenshot + page HTML + manifest.
- CSV-over-request failures: the response status/headers/body — a screenshot would
  show an unrelated warmed page here, so it is useless.

Everything is best-effort and wrapped so an artifact failure never masks the
original error. Files land under data/raw/_failures/<kind>/<key>/ with a `.FAILED.`
infix so they never collide with the happy-path raw dumps. (data/ is gitignored.)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from steam_agent.settings import DATA_DIR

log = logging.getLogger(__name__)

FAILURES_ROOT = DATA_DIR / "raw" / "_failures"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def failure_path(kind: str, key: object, label: str, ext: str, *, root: Path | None = None) -> Path:
    """Pure builder for a failure-artifact path (no IO unless the caller mkdirs)."""
    base = root if root is not None else FAILURES_ROOT
    safe_key = str(key).replace("/", "_").replace("\\", "_").strip() or "_"
    return base / kind / safe_key / f"{label}.FAILED.{ext}"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def dump_page_artifact(page, kind: str, key: object, *, label: str, error: object = None) -> dict:
    """Screenshot + HTML + manifest for a failed DOM/JS scrape. Returns the manifest."""
    manifest = {
        "mode": "page", "kind": kind, "key": str(key), "label": label,
        "url": None, "error": str(error) if error else None, "captured_at": _now_iso(),
    }
    try:
        manifest["url"] = page.url
        png = failure_path(kind, key, label, "png")
        png.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(png), full_page=True)
        _write(failure_path(kind, key, label, "html"), await page.content())
        _write(failure_path(kind, key, label, "json"), json.dumps(manifest, ensure_ascii=False, indent=2))
        log.error("Scrape-failure artifact saved: %s", png.parent)
    except Exception as exc:  # noqa: BLE001 — never mask the original failure
        log.warning("Could not save page failure artifact (%s/%s): %s", kind, label, exc)
    return manifest


async def dump_response_artifact(
    resp, request_url: str, kind: str, key: object, *, label: str, error: object = None
) -> dict:
    """Status + headers + body for a failed CSV-over-request fetch. Returns the manifest."""
    manifest = {
        "mode": "response", "kind": kind, "key": str(key), "label": label,
        "request_url": request_url, "status": None,
        "error": str(error) if error else None, "captured_at": _now_iso(),
    }
    try:
        if resp is not None:
            manifest["status"] = resp.status
            try:
                manifest["headers"] = dict(resp.headers)
            except Exception:  # noqa: BLE001
                pass
            _write(failure_path(kind, key, label, "txt"), (await resp.text())[:8192])
        json_path = failure_path(kind, key, label, "json")
        _write(json_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        log.error("Scrape-failure artifact saved: %s", json_path.parent)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not save response failure artifact (%s/%s): %s", kind, label, exc)
    return manifest
