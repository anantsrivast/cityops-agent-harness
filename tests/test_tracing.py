import pytest

from cityops_harness.config import load_settings
from cityops_harness.tracing import (
    LOCAL_PUBLIC_KEY,
    LOCAL_SECRET_KEY,
    init_tracing,
    langfuse_env,
)


def test_off_mode_returns_none():
    s = load_settings(env={"LANGFUSE_MODE": "off"})
    assert langfuse_env(s) is None
    assert init_tracing(s) is None


def test_cloud_mode_requires_keys():
    s = load_settings(env={"LANGFUSE_MODE": "cloud"})
    with pytest.raises(ValueError, match="LANGFUSE_PUBLIC_KEY"):
        langfuse_env(s)


def test_cloud_mode_env():
    s = load_settings(env={
        "LANGFUSE_MODE": "cloud",
        "LANGFUSE_PUBLIC_KEY": "pk-lf-abc",
        "LANGFUSE_SECRET_KEY": "sk-lf-abc",
    })
    assert langfuse_env(s) == {
        "LANGFUSE_PUBLIC_KEY": "pk-lf-abc",
        "LANGFUSE_SECRET_KEY": "sk-lf-abc",
        "LANGFUSE_HOST": "https://cloud.langfuse.com",
    }


def test_local_mode_defaults_to_deterministic_keys():
    s = load_settings(env={"LANGFUSE_MODE": "local"})
    assert langfuse_env(s) == {
        "LANGFUSE_PUBLIC_KEY": LOCAL_PUBLIC_KEY,
        "LANGFUSE_SECRET_KEY": LOCAL_SECRET_KEY,
        "LANGFUSE_HOST": "http://localhost:3000",
    }


def test_explicit_host_wins():
    s = load_settings(env={
        "LANGFUSE_MODE": "cloud",
        "LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk",
        "LANGFUSE_HOST": "https://eu.cloud.langfuse.com",
    })
    assert langfuse_env(s)["LANGFUSE_HOST"] == "https://eu.cloud.langfuse.com"
