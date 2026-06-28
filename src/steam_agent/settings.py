"""Central configuration (12-factor): reads from .env / environment variables."""
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

    # Steam account dedicated to the bot
    steam_username: str = ""
    steam_password: str = ""
    steam_shared_secret: str = ""

    # Steamworks publisher Web API key (optional)
    steam_publisher_api_key: str = ""

    # Partner/publisher ID on the portal (sales report). 0 = not set:
    # `setup` detects it automatically from the portal after login.
    steam_partner_id: int = 0

    # Studio name shown in the dashboard (optional, detected by `setup`).
    studio_name: str = ""

    # Claude API (LLM phase)
    anthropic_api_key: str = ""

    # Storage
    database_url: str = f"sqlite:///{(DATA_DIR / 'steam_agent.db').as_posix()}"

    # Smoke-test on any public appid
    smoke_test_appid: int = 440

    @property
    def storage_state_path(self) -> Path:
        return DATA_DIR / "storage_state.json"


settings = Settings()
