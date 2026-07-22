import pytest

from cityops_harness.config import Settings, load_settings


def test_defaults_from_empty_env():
    s = load_settings(env={})
    assert s.db_dsn == "anant_low"
    assert s.wallet_location == "wallet"
    assert s.embed_model == "ALL_MINILM_L12_V2"
    assert s.llm_provider == "anthropic"
    assert s.anthropic_model == "claude-opus-4-8"
    assert s.openai_model == "gpt-4o"
    assert s.ollama_model == "qwen3"
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.langfuse_mode == "off"


def test_env_overrides():
    s = load_settings(env={
        "DB_USER": "prism",
        "DB_DSN": "anant_tp",
        "LLM_PROVIDER": "Ollama",
        "LANGFUSE_MODE": "LOCAL",
    })
    assert s.db_user == "prism"
    assert s.db_dsn == "anant_tp"
    assert s.llm_provider == "ollama"       # normalised to lowercase
    assert s.langfuse_mode == "local"


def test_invalid_provider_raises():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        load_settings(env={"LLM_PROVIDER": "gemini"})


def test_invalid_langfuse_mode_raises():
    with pytest.raises(ValueError, match="LANGFUSE_MODE"):
        load_settings(env={"LANGFUSE_MODE": "maybe"})


def test_settings_is_frozen():
    s = load_settings(env={})
    with pytest.raises(Exception):
        s.db_user = "x"
