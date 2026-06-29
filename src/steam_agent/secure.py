"""Restrict filesystem permissions on files that hold secrets or session state.

On POSIX these files must not be readable by other users on the machine —
especially on the always-on server deploy target:

- ``.env`` holds the bot password and the TOTP ``shared_secret`` in plaintext.
- ``storage_state.json`` is a *live* authenticated Steam session (cookies for
  both partner portals) — reusable without password or 2FA, so leaking it is
  equivalent to leaking the account.

On Windows these calls are a no-op: NTFS permissions are inherited from the
parent directory and ``chmod`` cannot express the same model.
"""
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

log = logging.getLogger(__name__)

_POSIX = os.name == "posix"


def secure_file(path: str | os.PathLike[str]) -> None:
    """Best-effort ``chmod 0600`` (owner read/write only). No-op off POSIX."""
    if not _POSIX:
        return
    p = Path(path)
    try:
        if p.exists():
            p.chmod(0o600)
    except OSError as exc:
        log.warning("Could not restrict permissions on %s: %s", p, exc)


def secure_dir(path: str | os.PathLike[str]) -> None:
    """Best-effort ``chmod 0700`` (owner only). No-op off POSIX."""
    if not _POSIX:
        return
    p = Path(path)
    try:
        if p.exists():
            p.chmod(0o700)
    except OSError as exc:
        log.warning("Could not restrict permissions on %s: %s", p, exc)


def is_exposed(path: str | os.PathLike[str]) -> bool | None:
    """Whether ``path`` is group/other-accessible.

    Returns ``True``/``False`` on POSIX, or ``None`` when the answer is not
    meaningful (non-POSIX platform, or the file does not exist).
    """
    if not _POSIX:
        return None
    p = Path(path)
    if not p.exists():
        return None
    mode = p.stat().st_mode
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))
