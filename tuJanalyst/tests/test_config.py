"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings, load_watchlist_config


def _set_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUJ_MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("TUJ_MONGODB_DATABASE", "test_db")
    monkeypatch.setenv("TUJ_CHROMADB_PERSIST_DIR", "./data/chromadb")
    monkeypatch.setenv("TUJ_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setenv("TUJ_GATE_MODEL", "haiku")
    monkeypatch.setenv("TUJ_ANALYSIS_MODEL", "sonnet")
    monkeypatch.setenv("TUJ_DECISION_MODEL", "sonnet")
    monkeypatch.setenv("TUJ_NSE_RSS_URL", "https://example.com/nse")
    monkeypatch.setenv("TUJ_BSE_RSS_URL", "https://example.com/bse")
    monkeypatch.setenv("TUJ_POLLING_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("TUJ_POLLING_ENABLED", "true")
    monkeypatch.setenv("TUJ_MAX_DOCUMENT_SIZE_MB", "50")
    monkeypatch.setenv("TUJ_TEXT_EXTRACTION_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("TUJ_NOTIFICATION_METHOD", "none")


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TUJ_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TUJ_ANTHROPIC_API_KEY", "test-anthropic-key")

    settings = Settings(_env_file=None)

    assert settings.mongodb_uri == "mongodb://localhost:27017"
    assert settings.mongodb_database == "test_db"
    assert settings.llm_provider == "anthropic"
    assert settings.resolved_llm_api_key == "test-anthropic-key"


def test_settings_fail_when_provider_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TUJ_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("TUJ_LLM_API_KEY", raising=False)
    monkeypatch.delenv("TUJ_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TUJ_OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_provider_switch_works(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TUJ_LLM_PROVIDER", "openai")
    monkeypatch.setenv("TUJ_OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("TUJ_ANTHROPIC_API_KEY", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai"
    assert settings.resolved_llm_api_key == "test-openai-key"


def test_settings_require_web_search_key_for_brave_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TUJ_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TUJ_ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("TUJ_WEB_SEARCH_PROVIDER", "brave")
    monkeypatch.delenv("TUJ_BRAVE_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_allow_tavily_provider_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TUJ_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TUJ_ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("TUJ_WEB_SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TUJ_TAVILY_API_KEY", "tavily-test-key")

    settings = Settings(_env_file=None)

    assert settings.web_search_provider == "tavily"
    assert settings.tavily_api_key == "tavily-test-key"


def test_load_watchlist_config_parses_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "watchlist.yaml"
    config_path.write_text(
        """
sectors:
  - name: "Capital Goods"
    keywords: ["results", "order book"]
companies:
  - symbol: "INOXWIND"
    name: "Inox Wind Limited"
    priority: "high"
    aliases: ["Inox Wind"]
global_keywords:
  - "fraud"
""".strip(),
        encoding="utf-8",
    )

    watchlist = load_watchlist_config(config_path)

    assert len(watchlist.sectors) == 1
    assert len(watchlist.companies) == 1
    assert watchlist.companies[0].symbol == "INOXWIND"
    assert watchlist.global_keywords == ["fraud"]


def test_settings_validate_layer_dependency_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TUJ_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("TUJ_ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("TUJ_ENABLE_LAYER3_ANALYSIS", "false")
    monkeypatch.setenv("TUJ_ENABLE_LAYER4_DECISION", "true")
    monkeypatch.setenv("TUJ_ENABLE_LAYER5_REPORTING", "true")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
