"""Application configuration loading and validation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.models.company import WatchlistConfig

LLMProvider = Literal["anthropic", "openai", "azure", "local"]
NotificationMethod = Literal["slack", "email", "none"]
WebSearchProvider = Literal["brave", "tavily", "none"]


class Settings(BaseSettings):
    """Strongly typed settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TUJ_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Data stores
    mongodb_uri: str
    mongodb_database: str
    chromadb_persist_dir: Path = Path("data/chromadb")
    embedding_model: str = "all-MiniLM-L6-v2"

    # LLM configuration (provider-agnostic)
    llm_provider: LLMProvider = "anthropic"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gate_model: str
    analysis_model: str
    decision_model: str

    # Web search enrichment (Layer 3)
    web_search_provider: WebSearchProvider = "none"
    brave_api_key: str | None = None
    tavily_api_key: str | None = None
    web_search_timeout_seconds: int = 15
    web_search_max_results: int = 5

    # Trigger ingestion
    nse_rss_url: str
    bse_rss_url: str
    polling_interval_seconds: int = 300
    polling_enabled: bool = True

    # Processing controls
    max_document_size_mb: int = 50
    text_extraction_timeout_seconds: int = 60

    # Notification controls
    notification_method: NotificationMethod = "none"
    slack_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    notification_email: str | None = None

    # File-based configs
    watchlist_config_path: Path = Path("config/watchlist.yaml")
    settings_config_path: Path = Path("config/settings.yaml")

    @property
    def resolved_llm_api_key(self) -> str | None:
        """Return the effective API key for the selected provider."""
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider == "anthropic":
            return self.anthropic_api_key
        if self.llm_provider in {"openai", "azure"}:
            return self.openai_api_key
        return None

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> "Settings":
        """Validate cross-field configuration constraints."""
        if self.polling_interval_seconds <= 0:
            raise ValueError("TUJ_POLLING_INTERVAL_SECONDS must be > 0")

        if self.max_document_size_mb <= 0:
            raise ValueError("TUJ_MAX_DOCUMENT_SIZE_MB must be > 0")

        if self.text_extraction_timeout_seconds <= 0:
            raise ValueError("TUJ_TEXT_EXTRACTION_TIMEOUT_SECONDS must be > 0")

        if self.web_search_timeout_seconds <= 0:
            raise ValueError("TUJ_WEB_SEARCH_TIMEOUT_SECONDS must be > 0")

        if self.web_search_max_results <= 0:
            raise ValueError("TUJ_WEB_SEARCH_MAX_RESULTS must be > 0")

        if self.llm_provider in {"anthropic", "openai", "azure"} and not self.resolved_llm_api_key:
            raise ValueError(
                "Missing API key for selected LLM provider. Set TUJ_LLM_API_KEY or provider-specific key."
            )

        if self.notification_method == "slack" and not self.slack_webhook_url:
            raise ValueError("TUJ_SLACK_WEBHOOK_URL is required when TUJ_NOTIFICATION_METHOD=slack")

        if self.notification_method == "email" and (not self.smtp_host or not self.notification_email):
            raise ValueError("TUJ_SMTP_HOST and TUJ_NOTIFICATION_EMAIL are required when TUJ_NOTIFICATION_METHOD=email")

        if self.web_search_provider == "brave" and not self.brave_api_key:
            raise ValueError("TUJ_BRAVE_API_KEY is required when TUJ_WEB_SEARCH_PROVIDER=brave")

        if self.web_search_provider == "tavily" and not self.tavily_api_key:
            raise ValueError("TUJ_TAVILY_API_KEY is required when TUJ_WEB_SEARCH_PROVIDER=tavily")

        return self


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)

    if parsed is None:
        return {}

    if not isinstance(parsed, dict):
        raise ValueError(f"YAML config must be a mapping: {path}")

    return parsed


def load_watchlist_config(path: str | Path = "config/watchlist.yaml") -> WatchlistConfig:
    """Load and validate watchlist YAML config."""
    config_path = Path(path)
    payload = _load_yaml(config_path)

    try:
        return WatchlistConfig.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid watchlist config at {config_path}: {exc}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
