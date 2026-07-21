# Foundation Phase Implementation Plan (cityops-agent-harness)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared foundation for the cityops-agent-harness notebook series: repo scaffold, `cityops_harness` Python package (DB/LLM/tracing/checks/state), student-notebook build tool, Langfuse compose stack, Codespaces devcontainer, and the `00_setup.ipynb` verification notebook.

**Architecture:** All notebook plumbing lives in `src/cityops_harness/` as small pure-logic modules (config resolution separated from side effects so everything is unit-testable without a database or network). Notebooks import from the package. Secrets flow only through `.env` (local) / Codespaces secrets (remote); the wallet directory is git-ignored.

**Tech Stack:** Python 3.12, python-oracledb (thin), Oracle Autonomous DB 23ai, LiteLLM + LangChain (Ollama/Anthropic/OpenAI), oracleagentmemory SDK, Langfuse v3, pytest, nbformat.

## Global Constraints

- Repo name `cityops-agent-harness`; Python package `cityops_harness` under `src/`. Working directory is `/Users/anantsr/Documents/Projects/total_recall` (already a git repo on `main`).
- **Never touch** `notebook_complete_ollama.ipynb` or `total_recall_complete (1).ipynb`.
- **Never commit secrets**: `wallet/`, `.env` are git-ignored (already in `.gitignore`); check `git status` before every commit.
- All three LLM providers first-class, selected by `LLM_PROVIDER` env var: `ollama` | `anthropic` | `openai`.
- Default models: Anthropic `claude-opus-4-8`; OpenAI `gpt-4o`; Ollama `qwen3` (tool-capable).
- Langfuse modes: `LANGFUSE_MODE` = `cloud` | `local` | `off` (default `off`).
- DB defaults: DSN `anant_low`, wallet dir `wallet` (repo-relative), in-DB embed model `ALL_MINILM_L12_V2`.
- All pytest tests must run **without** a database, Ollama, API keys, or network.
- Every command below runs from the repo root; use `.venv/bin/python` / `.venv/bin/pytest` explicitly.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Repo scaffold and package skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/cityops_harness/__init__.py`
- Create: `tests/__init__.py`
- Create: `.env.example`

**Interfaces:**
- Produces: installable editable package `cityops_harness`; `.venv/` with dev deps; env-var contract documented in `.env.example` that Tasks 2–11 code against.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "cityops-harness"
version = "0.1.0"
description = "CityOps Agent Harness - agent memory + harness engineering workshop series"
requires-python = ">=3.12"
dependencies = [
    "oracledb>=2.0",
    "python-dotenv>=1.0",
    "litellm>=1.40",
    "langfuse>=3.0",
    "langchain-core>=0.3",
    "langchain-ollama>=0.2",
    "langchain-anthropic>=0.3",
    "langchain-openai>=0.3",
    "oracleagentmemory",
    "pydantic>=2",
    "pandas",
    "matplotlib",
    "jupyter",
    "ipykernel",
    "ipywidgets",
]

[project.optional-dependencies]
dev = ["pytest>=8", "nbformat>=5"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the package and test skeletons**

`src/cityops_harness/__init__.py`:

```python
"""Shared plumbing for the cityops-agent-harness notebook series."""

__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [ ] **Step 3: Write `.env.example`**

```bash
# ---- Oracle Autonomous DB 23ai ----
DB_USER=ADMIN
DB_PASSWORD=change_me
DB_DSN=anant_low
# Repo-relative directory holding tnsnames.ora + ewallet.pem (mTLS wallet).
WALLET_LOCATION=wallet
# Password chosen when the wallet was downloaded from OCI (required for thin-mode mTLS).
WALLET_PASSWORD=change_me
# In-database ONNX embedding model name (loaded by 00_setup.ipynb).
EMBED_MODEL=ALL_MINILM_L12_V2

# ---- LLM provider: ollama | anthropic | openai ----
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-opus-4-8
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3

# ---- Langfuse: cloud | local | off ----
LANGFUSE_MODE=off
# cloud mode: paste keys from langfuse.com; local mode: leave blank (deterministic
# local keys are baked into docker-compose.langfuse.override.yml).
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
```

- [ ] **Step 4: Create venv and install**

Run: `python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"`
Expected: exits 0. (If `oracleagentmemory` fails to resolve on this machine, re-run once; it is on PyPI — the CityOps lab installs it with plain pip.)

- [ ] **Step 5: Smoke-run pytest**

Run: `.venv/bin/pytest -q`
Expected: `no tests ran` (exit code 5 is fine at this point).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ tests/ .env.example
git commit -m "feat: scaffold cityops_harness package and env contract

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(`.venv/` must not be staged — add `.venv/` to `.gitignore` if `git status` shows it.)

---

### Task 2: Settings loader (`config.py`)

**Files:**
- Create: `src/cityops_harness/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` frozen dataclass with fields `db_user, db_password, db_dsn, wallet_location, wallet_password, embed_model, llm_provider, ollama_base_url, ollama_model, anthropic_model, openai_model, langfuse_mode, langfuse_public_key, langfuse_secret_key, langfuse_host`; `load_settings(env: Mapping[str, str] | None = None) -> Settings`. When `env is None` it calls `load_dotenv()` and reads `os.environ`; passing a mapping makes it pure for tests. Raises `ValueError` on invalid `LLM_PROVIDER` / `LANGFUSE_MODE`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cityops_harness.config'`

- [ ] **Step 3: Implement `src/cityops_harness/config.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/cityops_harness/config.py tests/test_config.py
git commit -m "feat: env-driven Settings loader

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: ADB connection helper (`db.py`)

**Files:**
- Create: `src/cityops_harness/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Settings`, `load_settings` from Task 2.
- Produces: `connect_kwargs(settings: Settings) -> dict` (pure — resolves wallet path against the repo root and builds `oracledb.connect` kwargs); `get_connection(settings: Settings | None = None)` (side-effecting — calls `oracledb.connect(**connect_kwargs(...))`); `REPO_ROOT: pathlib.Path` module constant.

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:

```python
from pathlib import Path

from cityops_harness.config import load_settings
from cityops_harness.db import REPO_ROOT, connect_kwargs


def test_wallet_kwargs_for_mtls():
    s = load_settings(env={
        "DB_USER": "admin",
        "DB_PASSWORD": "pw",
        "DB_DSN": "anant_low",
        "WALLET_LOCATION": "wallet",
        "WALLET_PASSWORD": "wpw",
    })
    kw = connect_kwargs(s)
    assert kw["user"] == "admin"
    assert kw["password"] == "pw"
    assert kw["dsn"] == "anant_low"
    wallet = str(REPO_ROOT / "wallet")
    assert kw["config_dir"] == wallet
    assert kw["wallet_location"] == wallet
    assert kw["wallet_password"] == "wpw"


def test_absolute_wallet_path_used_verbatim():
    s = load_settings(env={"WALLET_LOCATION": "/opt/wallet", "WALLET_PASSWORD": "x"})
    kw = connect_kwargs(s)
    assert kw["wallet_location"] == "/opt/wallet"


def test_walletless_tls_when_wallet_location_blank():
    # ADB "TLS" (walletless) connections use a long connect descriptor and no wallet.
    s = load_settings(env={"WALLET_LOCATION": "", "DB_DSN": "tcps://host:1522/svc"})
    kw = connect_kwargs(s)
    assert "wallet_location" not in kw
    assert "config_dir" not in kw
    assert kw["dsn"] == "tcps://host:1522/svc"


def test_repo_root_points_at_project():
    assert (Path(REPO_ROOT) / "pyproject.toml").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cityops_harness.db'`

- [ ] **Step 3: Implement `src/cityops_harness/db.py`**

```python
"""Oracle Autonomous DB connectivity (python-oracledb thin mode)."""

from __future__ import annotations

from pathlib import Path

import oracledb

from .config import Settings, load_settings

# src/cityops_harness/db.py -> src/cityops_harness -> src -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


def connect_kwargs(settings: Settings) -> dict:
    kw: dict = {
        "user": settings.db_user,
        "password": settings.db_password,
        "dsn": settings.db_dsn,
    }
    if settings.wallet_location:
        wallet = Path(settings.wallet_location)
        if not wallet.is_absolute():
            wallet = REPO_ROOT / wallet
        kw["config_dir"] = str(wallet)
        kw["wallet_location"] = str(wallet)
        if settings.wallet_password:
            kw["wallet_password"] = settings.wallet_password
    return kw


def get_connection(settings: Settings | None = None) -> oracledb.Connection:
    settings = settings or load_settings()
    return oracledb.connect(**connect_kwargs(settings))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_db.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/cityops_harness/db.py tests/test_db.py
git commit -m "feat: ADB connection helper with wallet and walletless-TLS paths

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: LLM factory (`llm.py`)

**Files:**
- Create: `src/cityops_harness/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: `Settings` from Task 2.
- Produces: `litellm_spec(settings) -> dict` (pure; keys `model` always, `api_base`/`api_key` for ollama only); `sdk_llm(settings)` returning an `oracleagentmemory` `Llm` built from that spec (for the Agent Memory SDK); `chat_model(settings)` returning a LangChain chat model (`ChatOllama` | `ChatAnthropic` | `ChatOpenAI`). Later notebooks call exactly these three functions.

- [ ] **Step 1: Write the failing tests**

`tests/test_llm.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_llm.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cityops_harness.llm'`

- [ ] **Step 3: Implement `src/cityops_harness/llm.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_llm.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/cityops_harness/llm.py tests/test_llm.py
git commit -m "feat: three-provider LLM factory (LiteLLM spec + LangChain chat model)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Langfuse wiring (`tracing.py`)

**Files:**
- Create: `src/cityops_harness/tracing.py`
- Test: `tests/test_tracing.py`

**Interfaces:**
- Consumes: `Settings` from Task 2.
- Produces: `LOCAL_PUBLIC_KEY = "pk-lf-local-0000"`, `LOCAL_SECRET_KEY = "sk-lf-local-0000"` constants (must match `docker-compose.langfuse.override.yml` in Task 9); `langfuse_env(settings) -> dict | None` (pure — the `LANGFUSE_*` env vars to export, `None` when mode is `off`; raises `ValueError` if cloud mode lacks keys); `init_tracing(settings) -> CallbackHandler | None` (side-effecting — exports the vars and returns a LangChain callback handler, or `None` when off).

- [ ] **Step 1: Write the failing tests**

`tests/test_tracing.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tracing.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cityops_harness.tracing'`

- [ ] **Step 3: Implement `src/cityops_harness/tracing.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_tracing.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/cityops_harness/tracing.py tests/test_tracing.py
git commit -m "feat: Langfuse cloud/local/off tracing wiring

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Notebook check helpers (`checks.py`)

**Files:**
- Create: `src/cityops_harness/checks.py`
- Test: `tests/test_checks.py`

**Interfaces:**
- Produces: `ok(msg) -> str` (renders + returns green-check HTML), `fail(msg)` (renders red HTML, raises `AssertionError(msg)`), `check(condition, msg) -> str` (dispatches to `ok`/`fail`). Displays via IPython when available; safe to call from plain pytest. Every `✅ check` cell in later notebooks uses these.

- [ ] **Step 1: Write the failing tests**

`tests/test_checks.py`:

```python
import pytest

from cityops_harness.checks import check, fail, ok


def test_ok_returns_green_html():
    out = ok("all good")
    assert "all good" in out and "✓" in out


def test_ok_escapes_html():
    assert "<script>" not in ok("<script>x</script>")


def test_fail_raises():
    with pytest.raises(AssertionError, match="broken"):
        fail("broken")


def test_check_dispatch():
    assert "✓" in check(True, "fine")
    with pytest.raises(AssertionError):
        check(False, "not fine")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_checks.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/cityops_harness/checks.py`**

```python
"""Green-check / red-cross cell helpers, in the style of the CityOps lab."""

from __future__ import annotations

import html

_GREEN = "#1a7f37"
_RED = "#cf222e"


def _render(symbol: str, color: str, msg: str) -> str:
    return (
        f'<div style="color:{color};font-weight:600;font-family:monospace">'
        f"{symbol} {html.escape(msg)}</div>"
    )


def _display(html_str: str) -> None:
    try:
        from IPython.display import HTML, display

        display(HTML(html_str))
    except Exception:
        pass


def ok(msg: str) -> str:
    out = _render("✓", _GREEN, msg)
    _display(out)
    return out


def fail(msg: str) -> str:
    _display(_render("✗", _RED, msg))
    raise AssertionError(msg)


def check(condition: bool, msg: str) -> str:
    return ok(msg) if condition else fail(msg)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_checks.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/cityops_harness/checks.py tests/test_checks.py
git commit -m "feat: notebook ok/fail/check helpers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Cross-notebook state verification (`state.py`)

**Files:**
- Create: `src/cityops_harness/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: a live DB connection (any object with `.cursor()`).
- Produces: `ArtifactCheck(description, sql)` frozen dataclass (scalar SELECT; truthy first column = pass); `REGISTRY: dict[str, list[ArtifactCheck]]` keyed by notebook id (`"00_setup"` seeded now; notebooks 01–04 append entries in later phases); `verify(conn, notebook) -> list[tuple[str, bool]]`; `require(conn, notebook)` which raises `RuntimeError` listing every failed check with the instruction to run the earlier notebook or its backfill cell.

- [ ] **Step 1: Write the failing tests**

`tests/test_state.py`:

```python
import pytest

from cityops_harness.state import REGISTRY, ArtifactCheck, require, verify


class StubCursor:
    def __init__(self, results):
        self._results = results

    def execute(self, sql):
        if isinstance(self._results.get(sql), Exception):
            raise self._results[sql]
        self._row = (self._results.get(sql, 0),)

    def fetchone(self):
        return self._row

    def close(self):
        pass


class StubConn:
    def __init__(self, results):
        self._results = results

    def cursor(self):
        return StubCursor(self._results)


def test_registry_seeds_setup_notebook():
    assert "00_setup" in REGISTRY
    assert all(isinstance(c, ArtifactCheck) for c in REGISTRY["00_setup"])


def test_verify_pass_and_fail(monkeypatch):
    checks = [
        ArtifactCheck("thing exists", "SELECT 1 FROM a"),
        ArtifactCheck("missing thing", "SELECT 0 FROM b"),
    ]
    monkeypatch.setitem(REGISTRY, "nb_test", checks)
    conn = StubConn({"SELECT 1 FROM a": 1, "SELECT 0 FROM b": 0})
    assert verify(conn, "nb_test") == [("thing exists", True), ("missing thing", False)]


def test_verify_treats_sql_error_as_failure(monkeypatch):
    monkeypatch.setitem(REGISTRY, "nb_err", [ArtifactCheck("errors", "SELECT boom")])
    conn = StubConn({"SELECT boom": RuntimeError("ORA-00942")})
    assert verify(conn, "nb_err") == [("errors", False)]


def test_require_raises_with_failed_descriptions(monkeypatch):
    monkeypatch.setitem(REGISTRY, "nb_req", [ArtifactCheck("the widget", "SELECT 0")])
    conn = StubConn({"SELECT 0": 0})
    with pytest.raises(RuntimeError, match="the widget"):
        require(conn, "nb_req")


def test_require_passes_silently(monkeypatch):
    monkeypatch.setitem(REGISTRY, "nb_ok", [ArtifactCheck("fine", "SELECT 1")])
    require(StubConn({"SELECT 1": 1}), "nb_ok")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_state.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/cityops_harness/state.py`**

```python
"""Did the previous notebook leave its artifacts in the database?

Each notebook opens with require(conn, "<previous notebook id>") so the series
is independently runnable: a clear error names what is missing and where to
backfill it, instead of an ORA-00942 five cells later.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactCheck:
    description: str
    sql: str  # scalar SELECT; truthy first column of first row = pass


REGISTRY: dict[str, list[ArtifactCheck]] = {
    "00_setup": [
        ArtifactCheck(
            description="in-database ONNX embedding model ALL_MINILM_L12_V2",
            sql=(
                "SELECT COUNT(*) FROM user_mining_models "
                "WHERE model_name = 'ALL_MINILM_L12_V2'"
            ),
        ),
    ],
    # Notebooks 01-04 register their artifacts here in later phases.
}


def verify(conn, notebook: str) -> list[tuple[str, bool]]:
    results: list[tuple[str, bool]] = []
    for chk in REGISTRY.get(notebook, []):
        cur = conn.cursor()
        try:
            cur.execute(chk.sql)
            row = cur.fetchone()
            passed = bool(row and row[0])
        except Exception:
            passed = False
        finally:
            cur.close()
        results.append((chk.description, passed))
    return results


def require(conn, notebook: str) -> None:
    failed = [desc for desc, passed in verify(conn, notebook) if not passed]
    if failed:
        missing = "\n  - ".join(failed)
        raise RuntimeError(
            f"Missing artifacts from notebook {notebook!r}:\n  - {missing}\n"
            f"Run that notebook (or its backfill cell) first."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_state.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/cityops_harness/state.py tests/test_state.py
git commit -m "feat: cross-notebook artifact verification registry

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Student-notebook build tool (`tools/make_student.py`)

**Files:**
- Create: `tools/make_student.py`
- Test: `tests/test_make_student.py`

**Interfaces:**
- Produces: `strip_solutions(source: str) -> str` (pure); `to_student(nb: dict) -> dict` (pure — strips marked solution blocks, clears outputs/execution counts); CLI `python tools/make_student.py [notebooks_dir]` converting every `*_complete.ipynb` into a `*_todo.ipynb` sibling. Authoring convention for notebooks 01–04: solution lines wrapped in `# TODO-SOLUTION-START` / `# TODO-SOLUTION-END` comment markers, preceded by a `# ✏️ TODO(n): <instruction>` comment that survives stripping.

- [ ] **Step 1: Write the failing tests**

`tests/test_make_student.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from make_student import strip_solutions, to_student

SRC = """def harvest(rows):
    # ✏️ TODO(1): return rows with occurrences >= 3
    # TODO-SOLUTION-START
    keep = [r for r in rows if r.occurrences >= 3]
    return keep
    # TODO-SOLUTION-END
"""


def test_strip_solutions_replaces_block_keeping_indent():
    out = strip_solutions(SRC)
    assert "keep = [" not in out
    assert "TODO-SOLUTION" not in out
    assert "# ✏️ TODO(1)" in out                    # instruction survives
    assert "    #   ... your code here ..." in out  # placeholder at marker indent


def test_strip_solutions_noop_without_markers():
    assert strip_solutions("x = 1\n") == "x = 1\n"


def _nb(cells):
    return {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def test_to_student_strips_code_and_outputs():
    nb = _nb([
        {"cell_type": "markdown", "source": ["# Title"], "metadata": {}},
        {"cell_type": "code", "source": SRC.splitlines(keepends=True),
         "metadata": {}, "outputs": [{"output_type": "stream"}], "execution_count": 7},
    ])
    out = to_student(nb)
    code = out["cells"][1]
    assert "keep = [" not in "".join(code["source"])
    assert code["outputs"] == []
    assert code["execution_count"] is None
    assert out["cells"][0]["source"] == ["# Title"]  # markdown untouched


def test_cli_converts_complete_to_todo(tmp_path):
    nb = _nb([{"cell_type": "code", "source": SRC.splitlines(keepends=True),
               "metadata": {}, "outputs": [], "execution_count": 1}])
    (tmp_path / "01_demo_complete.ipynb").write_text(json.dumps(nb))
    repo = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(repo / "tools" / "make_student.py"), str(tmp_path)],
        check=True,
    )
    student = json.loads((tmp_path / "01_demo_todo.ipynb").read_text())
    assert "keep = [" not in "".join(student["cells"][0]["source"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_make_student.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'make_student'`

- [ ] **Step 3: Implement `tools/make_student.py`**

```python
"""Generate learner (*_todo.ipynb) notebooks from authored *_complete.ipynb files.

The complete notebook is the single source of truth; solution code is wrapped in
comment markers and replaced by a placeholder here, so the two can never drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER_START = "# TODO-SOLUTION-START"
MARKER_END = "# TODO-SOLUTION-END"
PLACEHOLDER = "#   ... your code here ..."


def strip_solutions(source: str) -> str:
    out: list[str] = []
    in_block = False
    for line in source.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == MARKER_START:
            in_block = True
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}{PLACEHOLDER}\n")
        elif stripped == MARKER_END:
            in_block = False
        elif not in_block:
            out.append(line)
    return "".join(out)


def to_student(nb: dict) -> dict:
    student = json.loads(json.dumps(nb))  # deep copy
    for cell in student["cells"]:
        if cell.get("cell_type") != "code":
            continue
        cell["source"] = strip_solutions("".join(cell["source"])).splitlines(keepends=True)
        cell["outputs"] = []
        cell["execution_count"] = None
    return student


def main(notebooks_dir: str) -> None:
    directory = Path(notebooks_dir)
    for complete in sorted(directory.glob("*_complete.ipynb")):
        student_path = complete.with_name(
            complete.name.replace("_complete.ipynb", "_todo.ipynb")
        )
        nb = json.loads(complete.read_text())
        student_path.write_text(json.dumps(to_student(nb), indent=1))
        print(f"{complete.name} -> {student_path.name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "notebooks")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_make_student.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tools/make_student.py tests/test_make_student.py
git commit -m "feat: student-notebook generator (strip TODO solution blocks)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Local Langfuse stack

**Files:**
- Create: `docker-compose.langfuse.yml` (vendored from the official Langfuse repo)
- Create: `docker-compose.langfuse.override.yml`

**Interfaces:**
- Consumes: `LOCAL_PUBLIC_KEY` / `LOCAL_SECRET_KEY` values from Task 5 — the override file must seed exactly `pk-lf-local-0000` / `sk-lf-local-0000`.
- Produces: `docker compose -f docker-compose.langfuse.yml -f docker-compose.langfuse.override.yml up -d` brings up Langfuse at `http://localhost:3000` with a pre-provisioned org/project/user and those API keys — `LANGFUSE_MODE=local` works with zero manual setup.

- [ ] **Step 1: Vendor the official compose file**

Run:
```bash
curl -fsSL https://raw.githubusercontent.com/langfuse/langfuse/main/docker-compose.yml -o docker-compose.langfuse.yml
```
Expected: file exists, contains services including `langfuse-web` and `langfuse-worker` (verify with `grep -c "langfuse" docker-compose.langfuse.yml` > 0). Then pin: edit any `langfuse/langfuse:latest` / `langfuse/langfuse-worker:latest` image tags to the newest concrete version shown at https://github.com/langfuse/langfuse/releases (WebFetch that page for the current tag; use e.g. `langfuse/langfuse:3` if only a major tag is documented).

- [ ] **Step 2: Write the override with deterministic init**

`docker-compose.langfuse.override.yml`:

```yaml
# Seeds a deterministic org/project/user + API keys into the local stack so
# LANGFUSE_MODE=local works with zero clicks. Values must match
# cityops_harness.tracing.LOCAL_PUBLIC_KEY / LOCAL_SECRET_KEY.
services:
  langfuse-web:
    environment:
      LANGFUSE_INIT_ORG_ID: cityops
      LANGFUSE_INIT_ORG_NAME: CityOps
      LANGFUSE_INIT_PROJECT_ID: cityops-harness
      LANGFUSE_INIT_PROJECT_NAME: cityops-agent-harness
      LANGFUSE_INIT_PROJECT_PUBLIC_KEY: pk-lf-local-0000
      LANGFUSE_INIT_PROJECT_SECRET_KEY: sk-lf-local-0000
      LANGFUSE_INIT_USER_EMAIL: workshop@example.com
      LANGFUSE_INIT_USER_NAME: Workshop
      LANGFUSE_INIT_USER_PASSWORD: workshop123
```

- [ ] **Step 3: Validate compose syntax**

Run: `docker compose -f docker-compose.langfuse.yml -f docker-compose.langfuse.override.yml config -q`
Expected: exits 0 (syntax + merge valid). If Docker is not running locally, note it and rely on the Codespaces verification in Task 11.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.langfuse.yml docker-compose.langfuse.override.yml
git commit -m "feat: local Langfuse stack with deterministic seeded keys

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Codespaces devcontainer

**Files:**
- Create: `.devcontainer/devcontainer.json`
- Create: `.devcontainer/post-create.sh`

**Interfaces:**
- Consumes: Codespaces secrets `WALLET_B64` (base64 of a zip of the wallet directory), plus optional `DB_PASSWORD`, `WALLET_PASSWORD`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (Codespaces injects secrets as env vars automatically).
- Produces: a Codespace with the package installed, Jupyter kernel registered, wallet unpacked to `wallet/`, Ollama installed (model pull left to the user — it is multi-GB), and Docker available for the local Langfuse stack.

- [ ] **Step 1: Write `.devcontainer/devcontainer.json`**

```json
{
  "name": "cityops-agent-harness",
  "image": "mcr.microsoft.com/devcontainers/python:3.12",
  "hostRequirements": { "cpus": 4 },
  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "ghcr.io/prulloac/devcontainer-features/ollama:1": {}
  },
  "forwardPorts": [3000, 11434],
  "portsAttributes": {
    "3000": { "label": "Langfuse", "onAutoForward": "silent" },
    "11434": { "label": "Ollama", "onAutoForward": "silent" }
  },
  "postCreateCommand": "bash .devcontainer/post-create.sh",
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-toolsai.jupyter",
        "ms-toolsai.jupyter-renderers"
      ],
      "settings": {
        "jupyter.notebookFileRoot": "${containerWorkspaceFolder}/notebooks"
      }
    }
  }
}
```

- [ ] **Step 2: Write `.devcontainer/post-create.sh`**

```bash
#!/bin/bash
set -e

echo "[1/3] Installing cityops_harness + dev deps..."
pip install -q --no-cache-dir -e ".[dev]"
python -m ipykernel install --user --name harness --display-name "CityOps Harness"

echo "[2/3] Unpacking Oracle wallet from WALLET_B64 secret (if set)..."
if [ -n "${WALLET_B64:-}" ] && [ ! -f wallet/tnsnames.ora ]; then
  mkdir -p wallet
  echo "$WALLET_B64" | base64 -d > /tmp/wallet.zip
  unzip -o -q /tmp/wallet.zip -d wallet
  rm /tmp/wallet.zip
  echo "  wallet/ unpacked."
elif [ -f wallet/tnsnames.ora ]; then
  echo "  wallet/ already present."
else
  echo "  WALLET_B64 not set - add it as a Codespaces secret, or copy wallet/ manually."
fi

echo "[3/3] Seeding .env from .env.example (if absent)..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  .env created - fill in DB_PASSWORD / WALLET_PASSWORD / API keys."
fi

echo "Done. Open notebooks/00_setup.ipynb to verify the environment."
```

- [ ] **Step 3: Syntax-check the script and run the test suite**

Run: `bash -n .devcontainer/post-create.sh && .venv/bin/pytest -q`
Expected: no bash syntax errors; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add .devcontainer/
git commit -m "feat: Codespaces devcontainer (python 3.12, ollama, docker-in-docker)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: `00_setup.ipynb` and README

**Files:**
- Create: `tools/make_00_setup.py` (generator script, kept so the notebook can be regenerated)
- Create: `notebooks/00_setup.ipynb` (generated)
- Create: `README.md`

**Interfaces:**
- Consumes: everything from Tasks 2–7 (`load_settings`, `get_connection`, `litellm_spec`, `sdk_llm`, `chat_model`, `init_tracing`, `ok`/`check`, `state.verify`).
- Produces: a runnable setup notebook that (1) connects to ADB, (2) idempotently loads the ONNX embedding model via `DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD` from Oracle's public model bucket, (3) smoke-tests the configured LLM provider through both the LangChain and Agent Memory SDK paths, and (4) smoke-tests Langfuse when enabled.

- [ ] **Step 1: Write `tools/make_00_setup.py`**

```python
"""Regenerate notebooks/00_setup.ipynb. Run: .venv/bin/python tools/make_00_setup.py"""

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []

cells.append(nbf.v4.new_markdown_cell(
    "# 00 - Setup: verify your environment\n\n"
    "Run every cell top to bottom. Each section ends with a green check.\n\n"
    "Prerequisites: `.env` filled in (copy `.env.example`), the ADB wallet in "
    "`wallet/`, and - depending on `LLM_PROVIDER` - an API key or a running "
    "Ollama with the configured model pulled (`ollama pull qwen3`)."
))

cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.checks import ok, check\n"
    "from cityops_harness.config import load_settings\n"
    "\n"
    "settings = load_settings()\n"
    "ok(f\"settings loaded - provider={settings.llm_provider}, \"\n"
    "   f\"langfuse={settings.langfuse_mode}, dsn={settings.db_dsn}\")"
))

cells.append(nbf.v4.new_markdown_cell("## 1 · Autonomous Database"))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.db import get_connection\n"
    "\n"
    "conn = get_connection(settings)\n"
    "with conn.cursor() as cur:\n"
    "    cur.execute(\"SELECT banner_full FROM v$version\")\n"
    "    banner = cur.fetchone()[0]\n"
    "ok(banner.splitlines()[0])"
))

cells.append(nbf.v4.new_markdown_cell(
    "## 2 · In-database embeddings (ONNX)\n\n"
    "Embeddings run **inside** the database - no API key, no text egress. The\n"
    "cell below loads Oracle's `ALL_MINILM_L12_V2` model from the public\n"
    "OML-Resources object-storage bucket if it is not already present."
))
cells.append(nbf.v4.new_code_cell(
    "ONNX_URI = (\"https://objectstorage.us-ashburn-1.oraclecloud.com\"\n"
    "            \"/n/adwc4pm/b/OML-Resources/o/all_MiniLM_L12_v2.onnx\")\n"
    "\n"
    "with conn.cursor() as cur:\n"
    "    cur.execute(\n"
    "        \"SELECT COUNT(*) FROM user_mining_models WHERE model_name = :m\",\n"
    "        m=settings.embed_model,\n"
    "    )\n"
    "    present = cur.fetchone()[0] > 0\n"
    "\n"
    "if not present:\n"
    "    with conn.cursor() as cur:\n"
    "        cur.execute(\"\"\"\n"
    "            BEGIN\n"
    "              DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD(\n"
    "                model_name => :m,\n"
    "                credential => NULL,\n"
    "                uri        => :u,\n"
    "                metadata   => JSON('{\"function\":\"embedding\",'\n"
    "                                   || '\"embeddingOutput\":\"embedding\",'\n"
    "                                   || '\"input\":{\"input\":[\"DATA\"]}}')\n"
    "              );\n"
    "            END;\"\"\", m=settings.embed_model, u=ONNX_URI)\n"
    "    conn.commit()\n"
    "\n"
    "with conn.cursor() as cur:\n"
    "    cur.execute(\n"
    "        f\"SELECT VECTOR_EMBEDDING({settings.embed_model} USING 'hello' AS DATA)\"\n"
    "        \" FROM dual\"\n"
    "    )\n"
    "    vec = cur.fetchone()[0]\n"
    "check(vec is not None, f\"{settings.embed_model} embeds in-database\")"
))

cells.append(nbf.v4.new_markdown_cell(
    "## 3 · LLM provider\n\n"
    "One env var (`LLM_PROVIDER`) drives both LLM consumers: LangChain chat\n"
    "calls and the Oracle Agent Memory SDK (which speaks LiteLLM)."
))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.llm import chat_model, litellm_spec, sdk_llm\n"
    "\n"
    "print(\"LiteLLM spec:\", litellm_spec(settings))\n"
    "_ = sdk_llm(settings)  # constructs the Agent Memory SDK adapter\n"
    "\n"
    "model = chat_model(settings)\n"
    "reply = model.invoke(\"Reply with exactly: pong\")\n"
    "check(\"pong\" in reply.content.lower(),\n"
    "      f\"{settings.llm_provider} responded: {reply.content[:60]!r}\")"
))

cells.append(nbf.v4.new_markdown_cell(
    "## 4 · Langfuse (optional)\n\n"
    "`LANGFUSE_MODE=cloud` needs keys in `.env`; `local` needs the compose\n"
    "stack up (`docker compose -f docker-compose.langfuse.yml -f "
    "docker-compose.langfuse.override.yml up -d`); `off` skips this section."
))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.tracing import init_tracing\n"
    "\n"
    "handler = init_tracing(settings)\n"
    "if handler is None:\n"
    "    ok(\"Langfuse off - skipping\")\n"
    "else:\n"
    "    traced = chat_model(settings).invoke(\n"
    "        \"Say: traced\", config={\"callbacks\": [handler]}\n"
    "    )\n"
    "    handler.client.flush()\n"
    "    ok(f\"trace sent to Langfuse ({settings.langfuse_mode}) - \"\n"
    "       \"check the UI for a '00_setup' trace\")"
))

cells.append(nbf.v4.new_markdown_cell("## 5 · Summary"))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.state import verify\n"
    "\n"
    "for desc, passed in verify(conn, \"00_setup\"):\n"
    "    check(passed, desc)\n"
    "ok(\"environment ready - continue to 01_self_improving_copilot\")"
))

nb["cells"] = cells
nbf.write(nb, "notebooks/00_setup.ipynb")
print("wrote notebooks/00_setup.ipynb")
```

- [ ] **Step 2: Generate the notebook**

Run: `mkdir -p notebooks && .venv/bin/python tools/make_00_setup.py`
Expected: `wrote notebooks/00_setup.ipynb`; `python -c "import json; json.load(open('notebooks/00_setup.ipynb'))"` exits 0.

- [ ] **Step 3: Write `README.md`**

```markdown
# cityops-agent-harness

Agent memory **and harness engineering**, hands-on: the sequel to the CityOps
Copilot workshop. The copilot you built there gets a self-improving harness -
registered tools, harvested skills, scheduled memory promotion, and context
engineering - with every piece of durable state living in Oracle Autonomous
Database 23ai, and an eval suite (Langfuse) measuring whether the learning
actually works.

## The series

| Notebook | What it teaches |
|---|---|
| `notebooks/00_setup.ipynb` | Verify ADB, in-DB embeddings, LLM provider, Langfuse |
| `notebooks/01_self_improving_copilot` | Tool registry, skillbox, verified workflow harvesting |
| `notebooks/02_scheduled_briefings` | Curated memory promotion + DBMS_SCHEDULER automations |
| `notebooks/03_context_engineering` | Compaction and offloading, measured for fidelity |
| `notebooks/04_evals` | Five Langfuse evals across model and memory |

Notebooks 01-04 come in two flavors: `*_complete.ipynb` (full solutions) and
generated `*_todo.ipynb` (fill in the marked gaps; regenerate with
`python tools/make_student.py`).

Prerequisite: the CityOps Copilot workshop (`notebook_complete_ollama.ipynb`,
kept in this repo for reference - unmodified).

## Quick start (GitHub Codespaces)

1. Add Codespaces secrets: `WALLET_B64` (base64 of your ADB wallet zip),
   `DB_PASSWORD`, `WALLET_PASSWORD`, and - per provider - `ANTHROPIC_API_KEY`
   or `OPENAI_API_KEY` (none needed for Ollama). Optional: `LANGFUSE_PUBLIC_KEY`
   / `LANGFUSE_SECRET_KEY` for cloud tracing.
2. Create a Codespace. The devcontainer installs everything and unpacks the wallet.
3. Fill any gaps in `.env`, then run `notebooks/00_setup.ipynb`.

## Quick start (local)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env        # fill in DB_PASSWORD, WALLET_PASSWORD, keys
# place your ADB wallet files in wallet/   (git-ignored)
.venv/bin/jupyter lab notebooks/00_setup.ipynb
```

## LLM providers

Set `LLM_PROVIDER` in `.env`:

| Provider | Needs | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | default; model `claude-opus-4-8` |
| `openai` | `OPENAI_API_KEY` | model `gpt-4o` |
| `ollama` | local Ollama + `ollama pull qwen3` | tool-capable model required; CPU Codespaces are slow but correct |

## Langfuse

Set `LANGFUSE_MODE` in `.env`: `cloud` (keys from langfuse.com), `local`
(`docker compose -f docker-compose.langfuse.yml -f
docker-compose.langfuse.override.yml up -d`, UI at http://localhost:3000,
login `workshop@example.com` / `workshop123`), or `off`.

## Development

```bash
.venv/bin/pytest -q          # unit tests (no DB or network needed)
python tools/make_student.py # regenerate *_todo.ipynb learner notebooks
```
```

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass (≈33).

- [ ] **Step 5: Live verification (requires credentials)**

If `.env` contains a real `DB_PASSWORD`/`WALLET_PASSWORD` (ask the user to fill them in if not — do not proceed silently):

Run: `.venv/bin/jupyter nbconvert --to notebook --execute --stdout notebooks/00_setup.ipynb > /dev/null && echo EXECUTED`
Expected: `EXECUTED`. If credentials are unavailable, mark this step as pending user input and report it — do not fake the result.

- [ ] **Step 6: Commit**

```bash
git add tools/make_00_setup.py notebooks/00_setup.ipynb README.md
git commit -m "feat: 00_setup verification notebook and README

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Post-plan checklist

- `git status` shows no untracked secrets (`wallet/`, `.env` ignored).
- `notebook_complete_ollama.ipynb` untouched (`git diff --stat` clean for it).
- Open items carried to the next phase (01 self-improving copilot): register notebook-01 artifacts in `state.REGISTRY`; validate `oracleagentmemory` + `DBMS_SCHEDULER` against the live ADB; confirm the Ollama `qwen3` model tag supports tool calling (swap for `qwen2.5` in `.env.example` if not).
