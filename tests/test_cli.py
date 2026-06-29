"""Tests for CLI startup helpers."""
from __future__ import annotations

import io

from steam_agent import cli


def test_force_utf8_reconfigures_a_cp1252_stream():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    cli._force_utf8_stdio([stream])
    assert stream.encoding.lower() == "utf-8"
    # the glyphs that crashed a redirected run now encode fine
    stream.write("→ Marketing · done — ok •")
    stream.flush()


def test_force_utf8_is_best_effort_on_streams_without_reconfigure():
    class _NoReconfigure:
        pass

    # must not raise even though the stream has no reconfigure()
    cli._force_utf8_stdio([_NoReconfigure()])
