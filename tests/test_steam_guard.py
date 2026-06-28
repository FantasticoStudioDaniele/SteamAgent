"""Test del generatore TOTP Steam Guard contro un vettore noto."""
from __future__ import annotations

import pytest

from steam_agent.auth.steam_guard import _ALPHABET, generate_twofactor_code

# Vettore golden calcolato con l'algoritmo di riferimento (stdlib).
GOLDEN_SECRET = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM="  # base64 di b"0123456789abcdef0123"
GOLDEN_TS = 1700000000
GOLDEN_CODE = "JTQJ4"


def test_known_vector():
    assert generate_twofactor_code(GOLDEN_SECRET, GOLDEN_TS) == GOLDEN_CODE


def test_format():
    code = generate_twofactor_code(GOLDEN_SECRET, GOLDEN_TS)
    assert len(code) == 5
    assert all(c in _ALPHABET for c in code)


# 1700000010 è un confine di finestra (multiplo di 30): finestra = [1700000010, 1700000040).
WINDOW_START = 1700000010


def test_deterministico_nella_stessa_finestra():
    # Due istanti nella stessa finestra da 30s -> stesso codice.
    assert generate_twofactor_code(GOLDEN_SECRET, WINDOW_START) == generate_twofactor_code(
        GOLDEN_SECRET, WINDOW_START + 29
    )


def test_cambia_tra_finestre():
    # Finestre adiacenti -> codici diversi.
    assert generate_twofactor_code(GOLDEN_SECRET, WINDOW_START) != generate_twofactor_code(
        GOLDEN_SECRET, WINDOW_START + 30
    )


def test_secret_vuoto_errore():
    with pytest.raises(ValueError):
        generate_twofactor_code("")
