"""Steam Guard TOTP: generates the 2FA code from the shared_secret.

Steam uses an HMAC-SHA1 TOTP with a 30s window, but with a custom alphabet
of 5 characters instead of the classic 6 digits. Algorithm identical to the
one used by Steam Desktop Authenticator / ValvePython.
"""
from __future__ import annotations

import base64
import hmac
import struct
import time
from hashlib import sha1

_ALPHABET = "23456789BCDFGHJKMNPQRTVWXY"


def generate_twofactor_code(shared_secret: str, timestamp: float | None = None) -> str:
    """Returns the 5-character Steam Guard code for the given instant."""
    if not shared_secret:
        raise ValueError("shared_secret missing")
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
