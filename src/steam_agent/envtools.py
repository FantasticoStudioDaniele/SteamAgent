"""Idempotent update of the `.env` file (preserves comments and other lines)."""
from __future__ import annotations

from pathlib import Path

from steam_agent.secure import secure_file
from steam_agent.settings import PROJECT_ROOT

ENV_PATH = PROJECT_ROOT / ".env"


def update_env(updates: dict[str, str], path: Path = ENV_PATH) -> Path:
    """Creates/updates the given keys in the `.env`, leaving the rest intact."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    secure_file(path)  # .env holds the password + TOTP secret in plaintext
    return path
