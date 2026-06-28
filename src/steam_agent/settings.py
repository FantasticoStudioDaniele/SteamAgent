"""Configurazione centrale (12-factor): legge da .env / variabili d'ambiente."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Account Steam dedicato al bot
    steam_username: str = ""
    steam_password: str = ""
    steam_shared_secret: str = ""

    # Steamworks publisher Web API key (opzionale)
    steam_publisher_api_key: str = ""

    # ID partner/publisher sul portale (report vendite). 0 = non impostato:
    # `setup` lo rileva automaticamente dal portale dopo il login.
    steam_partner_id: int = 0

    # Nome studio mostrato in dashboard (opzionale, rilevato da `setup`).
    studio_name: str = ""

    # Claude API (fase LLM)
    anthropic_api_key: str = ""

    # Storage
    database_url: str = f"sqlite:///{(DATA_DIR / 'steam_agent.db').as_posix()}"

    # Smoke-test su un appid pubblico qualsiasi
    smoke_test_appid: int = 440

    @property
    def storage_state_path(self) -> Path:
        return DATA_DIR / "storage_state.json"


settings = Settings()
