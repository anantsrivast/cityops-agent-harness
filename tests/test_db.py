from pathlib import Path

import pytest

from cityops_harness.config import load_settings
from cityops_harness import db as db_mod
from cityops_harness.db import (
    POOL_MAX,
    REPO_ROOT,
    _is_session_exhaustion,
    connect_kwargs,
    get_connection,
)


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


def test_pool_stays_small_enough_for_a_30_session_database():
    # Several kernels share one ADB; a runaway per-process cap defeats pooling.
    assert POOL_MAX <= 3


@pytest.mark.parametrize("code", ["DPY-6000", "DPY-4011", "ORA-12506",
                                  "ORA-12516", "ORA-12520"])
def test_listener_refusals_are_recognised_as_session_exhaustion(code):
    assert _is_session_exhaustion(Exception(f"{code}: listener refused connection"))


def test_unrelated_errors_are_not_mistaken_for_exhaustion():
    assert not _is_session_exhaustion(Exception("ORA-01017: invalid credential"))


def _fail_with(monkeypatch, message):
    class _Pool:
        def acquire(self):
            raise RuntimeError(message)

    monkeypatch.setattr(db_mod, "get_pool", lambda settings=None: _Pool())


def test_local_pool_timeout_explains_how_to_free_a_connection(monkeypatch):
    _fail_with(monkeypatch, "DPY-4005: timed out waiting for the connection pool")
    with pytest.raises(ConnectionError, match="conn.close()"):
        get_connection()


def test_server_refusal_explains_the_30_session_cap(monkeypatch):
    _fail_with(monkeypatch, "DPY-6000: Listener refused connection")
    with pytest.raises(ConnectionError, match="30 concurrent sessions"):
        get_connection()


def test_other_errors_propagate_unchanged(monkeypatch):
    _fail_with(monkeypatch, "ORA-01017: invalid username/password")
    with pytest.raises(RuntimeError, match="ORA-01017"):
        get_connection()
