"""Environment-driven settings shared by every notebook and module."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv

_PROVIDERS = ("ollama", "anthropic", "openai")
_LANGFUSE_MODES = ("cloud", "local", "off")


@dataclass(frozen=True)
class Settings:
    # Oracle Autonomous DB
    db_user: str
    db_password: str
    db_dsn: str
    wallet_location: str
    wallet_password: str
    embed_model: str
    # LLM provider
    llm_provider: str
    ollama_base_url: str
    ollama_model: str
    anthropic_model: str
    openai_model: str
    # Langfuse
    langfuse_mode: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ

    provider = env.get("LLM_PROVIDER", "anthropic").lower()
    if provider not in _PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {_PROVIDERS}, got {provider!r}")

    mode = env.get("LANGFUSE_MODE", "off").lower()
    if mode not in _LANGFUSE_MODES:
        raise ValueError(f"LANGFUSE_MODE must be one of {_LANGFUSE_MODES}, got {mode!r}")

    return Settings(
        db_user=env.get("DB_USER", "ADMIN"),
        db_password=env.get("DB_PASSWORD", ""),
        db_dsn=env.get("DB_DSN", "anant_low"),
        wallet_location=env.get("WALLET_LOCATION", "wallet"),
        wallet_password=env.get("WALLET_PASSWORD", ""),
        embed_model=env.get("EMBED_MODEL", "ALL_MINILM_L12_V2"),
        llm_provider=provider,
        ollama_base_url=env.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=env.get("OLLAMA_MODEL", "qwen3"),
        anthropic_model=env.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
        openai_model=env.get("OPENAI_MODEL", "gpt-4o"),
        langfuse_mode=mode,
        langfuse_public_key=env.get("LANGFUSE_PUBLIC_KEY", ""),
        langfuse_secret_key=env.get("LANGFUSE_SECRET_KEY", ""),
        langfuse_host=env.get("LANGFUSE_HOST", ""),
    )
