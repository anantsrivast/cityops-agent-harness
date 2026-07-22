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
