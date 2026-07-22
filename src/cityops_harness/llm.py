"""One switch (LLM_PROVIDER) drives both LLM consumers:

- the Oracle Agent Memory SDK, which speaks LiteLLM  -> sdk_llm()
- notebook/agent chat calls, which use LangChain     -> chat_model()
"""

from __future__ import annotations

from .config import Settings


def litellm_spec(settings: Settings) -> dict:
    if settings.llm_provider == "ollama":
        # Ollama exposes an OpenAI-compatible API at /v1; LiteLLM routes via the
        # openai/ provider. The api_key is a required placeholder Ollama ignores.
        return {
            "model": f"openai/{settings.ollama_model}",
            "api_base": f"{settings.ollama_base_url}/v1",
            "api_key": "ollama",
        }
    if settings.llm_provider == "anthropic":
        return {"model": f"anthropic/{settings.anthropic_model}"}
    return {"model": f"openai/{settings.openai_model}"}


def sdk_llm(settings: Settings):
    from oracleagentmemory.core.llms.llm import Llm

    return Llm(**litellm_spec(settings))


def chat_model(settings: Settings):
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url)
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=settings.anthropic_model)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.openai_model)
