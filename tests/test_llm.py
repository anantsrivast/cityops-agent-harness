import pytest

from cityops_harness.config import load_settings
from cityops_harness.llm import chat_model, litellm_spec


def test_litellm_spec_ollama():
    s = load_settings(env={"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "qwen3",
                           "OLLAMA_BASE_URL": "http://box:11434"})
    assert litellm_spec(s) == {
        "model": "openai/qwen3",
        "api_base": "http://box:11434/v1",
        "api_key": "ollama",
    }


def test_litellm_spec_anthropic():
    s = load_settings(env={"LLM_PROVIDER": "anthropic"})
    assert litellm_spec(s) == {"model": "anthropic/claude-opus-4-8"}


def test_litellm_spec_openai():
    s = load_settings(env={"LLM_PROVIDER": "openai", "OPENAI_MODEL": "gpt-4o"})
    assert litellm_spec(s) == {"model": "openai/gpt-4o"}


def test_chat_model_ollama():
    from langchain_ollama import ChatOllama
    s = load_settings(env={"LLM_PROVIDER": "ollama"})
    m = chat_model(s)
    assert isinstance(m, ChatOllama)
    assert m.model == "qwen3"


def test_chat_model_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from langchain_anthropic import ChatAnthropic
    s = load_settings(env={"LLM_PROVIDER": "anthropic"})
    assert isinstance(chat_model(s), ChatAnthropic)


def test_chat_model_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from langchain_openai import ChatOpenAI
    s = load_settings(env={"LLM_PROVIDER": "openai"})
    assert isinstance(chat_model(s), ChatOpenAI)
