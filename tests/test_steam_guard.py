"""Test the Steam Guard TOTP generator against a known vector."""
from __future__ import annotations

import pytest

from steam_agent.auth.steam_guard import _ALPHABET, generate_twofactor_code

# Golden vector computed with the reference algorithm (stdlib).
GOLDEN_SECRET = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM="  # base64 of b"0123456789abcdef0123"
GOLDEN_TS = 1700000000
GOLDEN_CODE = "JTQJ4"


def test_known_vector():
    assert generate_twofactor_code(GOLDEN_SECRET, GOLDEN_TS) == GOLDEN_CODE


def test_format():
    code = generate_twofactor_code(GOLDEN_SECRET, GOLDEN_TS)
    assert len(code) == 5
    assert all(c in _ALPHABET for c in code)


# 1700000010 is a window boundary (multiple of 30): window = [1700000010, 1700000040).
WINDOW_START = 1700000010


def test_deterministic_within_same_window():
    # Two instants in the same 30s window -> same code.
    assert generate_twofactor_code(GOLDEN_SECRET, WINDOW_START) == generate_twofactor_code(
        GOLDEN_SECRET, WINDOW_START + 29
    )


def test_changes_between_windows():
    # Adjacent windows -> different codes.
    assert generate_twofactor_code(GOLDEN_SECRET, WINDOW_START) != generate_twofactor_code(
        GOLDEN_SECRET, WINDOW_START + 30
    )


def test_empty_secret_raises():
    with pytest.raises(ValueError):
        generate_twofactor_code("")
