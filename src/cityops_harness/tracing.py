"""Langfuse wiring: cloud (langfuse.com), local (docker compose), or off."""

from __future__ import annotations

import os

from .config import Settings

CLOUD_HOST = "https://cloud.langfuse.com"
LOCAL_HOST = "http://localhost:3000"
# Deterministic keys seeded into the local stack by docker-compose.langfuse.override.yml.
LOCAL_PUBLIC_KEY = "pk-lf-local-0000"
LOCAL_SECRET_KEY = "sk-lf-local-0000"


def langfuse_env(settings: Settings) -> dict | None:
    if settings.langfuse_mode == "off":
        return None
    if settings.langfuse_mode == "cloud":
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            raise ValueError(
                "LANGFUSE_MODE=cloud requires LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"
            )
        return {
            "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key,
            "LANGFUSE_HOST": settings.langfuse_host or CLOUD_HOST,
        }
    return {
        "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key or LOCAL_PUBLIC_KEY,
        "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key or LOCAL_SECRET_KEY,
        "LANGFUSE_HOST": settings.langfuse_host or LOCAL_HOST,
    }


def init_tracing(settings: Settings):
    env = langfuse_env(settings)
    if env is None:
        return None
    os.environ.update(env)
    from langfuse.langchain import CallbackHandler

    return CallbackHandler()
