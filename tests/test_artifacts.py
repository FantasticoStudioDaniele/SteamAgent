"""Unit tests for the failure-artifact path builder and the dump writers."""
from __future__ import annotations

import asyncio
from pathlib import Path

from steam_agent.scraping import artifacts
from steam_agent.scraping.artifacts import failure_path


class _FakeResp:
    def __init__(self, status, body, headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def text(self):
        return self._body


class _FakePage:
    url = "https://partner.steampowered.com/app/playtime/440/"

    async def screenshot(self, path, full_page=False):
        Path(path).write_bytes(b"\x89PNG\r\n")

    async def content(self):
        return "<html>broken layout</html>"


def test_failure_path_layout_and_infix(tmp_path):
    p = failure_path("players", 440, "2020-01_to_2026-01", "txt", root=tmp_path)
    assert p == tmp_path / "players" / "440" / "2020-01_to_2026-01.FAILED.txt"
    assert ".FAILED." in p.name  # never collides with the happy-path raw dump


def test_failure_path_sanitizes_key_with_separators(tmp_path):
    p = failure_path("sales", "2026/01", "2026-01", "json", root=tmp_path)
    # the key must not introduce extra path segments
    assert p.parent == tmp_path / "sales" / "2026_01"
    assert "/" not in p.parent.name and "\\" not in p.parent.name


def test_failure_path_defaults_under_data_raw_failures():
    p = failure_path("marketing", 1, "lifetime", "png")
    parts = p.parts
    assert "raw" in parts and "_failures" in parts
    assert p.parent == artifacts.FAILURES_ROOT / "marketing" / "1"
    assert isinstance(artifacts.FAILURES_ROOT, Path)


def test_dump_response_artifact_writes_body_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "FAILURES_ROOT", tmp_path)
    resp = _FakeResp(200, "Some,Bad,CSV\n1,2,3\n", {"content-type": "text/csv"})
    manifest = asyncio.run(
        artifacts.dump_response_artifact(resp, "http://x/report.csv", "players", 440, label="run")
    )
    base = tmp_path / "players" / "440"
    assert (base / "run.FAILED.txt").read_text(encoding="utf-8").startswith("Some,Bad,CSV")
    assert (base / "run.FAILED.json").exists()
    assert manifest["status"] == 200 and manifest["mode"] == "response"


def test_dump_page_artifact_writes_screenshot_html_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "FAILURES_ROOT", tmp_path)
    manifest = asyncio.run(
        artifacts.dump_page_artifact(_FakePage(), "playtime", 440, label="snapshot")
    )
    base = tmp_path / "playtime" / "440"
    assert (base / "snapshot.FAILED.png").exists()
    assert "broken layout" in (base / "snapshot.FAILED.html").read_text(encoding="utf-8")
    assert (base / "snapshot.FAILED.json").exists()
    assert manifest["url"].endswith("/app/playtime/440/")
