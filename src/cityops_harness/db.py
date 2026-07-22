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
