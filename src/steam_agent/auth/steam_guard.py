"""Steam Guard TOTP: genera il codice 2FA dallo shared_secret.

Steam usa un TOTP HMAC-SHA1 con finestra di 30s, ma con un alfabeto custom
di 5 caratteri invece delle classiche 6 cifre. Algoritmo identico a quello
usato da Steam Desktop Authenticator / ValvePython.
"""
from __future__ import annotations

import base64
import hmac
import struct
import time
from hashlib import sha1

_ALPHABET = "23456789BCDFGHJKMNPQRTVWXY"


def generate_twofactor_code(shared_secret: str, timestamp: float | None = None) -> str:
    """Restituisce il codice Steam Guard a 5 caratteri per l'istante dato."""
    if not shared_secret:
        raise ValueError("shared_secret mancante")
    if timestamp is None:
        timestamp = time.time()

    secret = base64.b64decode(shared_secret)
    counter = int(timestamp) // 30
    digest = hmac.new(secret, struct.pack(">Q", counter), sha1).digest()
    start = digest[19] & 0x0F
    code_int = struct.unpack(">I", digest[start : start + 4])[0] & 0x7FFFFFFF

    chars = []
    for _ in range(5):
        code_int, idx = divmod(code_int, len(_ALPHABET))
        chars.append(_ALPHABET[idx])
    return "".join(chars)
