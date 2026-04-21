"""
Application configuration via Pydantic Settings.

All values are read from environment variables (or .env file).
Import the singleton `settings` anywhere in the app:

    from backend.core.config import settings
    print(settings.LLM_MODEL)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # --- LLM Providers -------------------------------------------------------

    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: str | None = None

    # --- LLM Configuration ---------------------------------------------------

    LLM_PROVIDER: Literal["openai", "anthropic"] = "openai"
    LLM_MODEL: str = "gpt-5.2"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.1

    # --- Data ----------------------------------------------------------------

    DATA_DIR: Path = Path("data/processed")

    # --- Application ---------------------------------------------------------

    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- Validators ----------------------------------------------------------

    @field_validator("LLM_TEMPERATURE")
    @classmethod
    def temperature_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("LLM_TEMPERATURE must be between 0.0 and 2.0")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def valid_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return v.upper()


# Singleton — import this throughout the app
settings = Settings()
