"""Oracle Autonomous DB connectivity (python-oracledb thin mode).

Connections come from a small per-process pool. The workshop ADB is capped at
30 concurrent sessions, and a notebook that calls ``get_connection`` on every
re-run would otherwise leak a session per run until the listener starts
refusing new ones with ORA-12506.
"""

from __future__ import annotations

import atexit
from pathlib import Path

import oracledb

from .config import Settings, load_settings

# src/cityops_harness/db.py -> src/cityops_harness -> src -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# One kernel should never hold more than a couple of the ADB's 30 sessions.
POOL_MIN = 1
POOL_MAX = 2
POOL_WAIT_SECONDS = 10

_pool: oracledb.ConnectionPool | None = None
_pool_key: tuple | None = None

_SERVER_HINT = (
    "the database refused the connection because its session pool is full "
    "(this ADB allows 30 concurrent sessions). Shut down idle notebook kernels "
    "and re-run. To see who is holding them: "
    "SELECT program, module, status FROM v$session WHERE username IS NOT NULL"
)

_LOCAL_HINT = (
    f"this process already holds all {POOL_MAX} of its pooled connections. "
    "Close one with conn.close() (that returns it to the pool), or restart the "
    "kernel. The cap is deliberate - the ADB only allows 30 sessions in total."
)


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


def _is_session_exhaustion(exc: Exception) -> bool:
    # ORA-12506/12516/12520 all reach the client as a listener refusal once
    # every session handler is busy; DPY-4011 is the mid-handshake variant.
    text = str(exc)
    return any(code in text for code in
               ("DPY-6000", "DPY-4011", "ORA-12506", "ORA-12516", "ORA-12520"))


def get_pool(settings: Settings | None = None) -> oracledb.ConnectionPool:
    """Return the process-wide pool, creating it on first use."""
    global _pool, _pool_key
    settings = settings or load_settings()
    kw = connect_kwargs(settings)
    key = tuple(sorted(kw.items()))
    if _pool is not None and _pool_key == key:
        return _pool
    close_pool()  # settings changed - drop the old pool first
    _pool = oracledb.create_pool(
        min=POOL_MIN,
        max=POOL_MAX,
        increment=1,
        # TIMEDWAIT, not WAIT: plain WAIT ignores wait_timeout and blocks forever
        # when every pooled connection is checked out.
        getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
        wait_timeout=POOL_WAIT_SECONDS * 1000,  # milliseconds
        **kw,
    )
    _pool_key = key
    return _pool


def get_connection(settings: Settings | None = None) -> oracledb.Connection:
    """Check out a connection from the pool.

    The result behaves like a normal ``oracledb.Connection``; calling
    ``close()`` hands the session back to the pool instead of dropping it.
    """
    try:
        return get_pool(settings).acquire()
    except Exception as exc:
        if "DPY-4005" in str(exc):  # pool timed out handing back a connection
            raise ConnectionError(f"{exc}\n\nLikely cause: {_LOCAL_HINT}") from exc
        if _is_session_exhaustion(exc):
            raise ConnectionError(f"{exc}\n\nLikely cause: {_SERVER_HINT}") from exc
        raise


def close_pool() -> None:
    """Close the pool and release every session it holds."""
    global _pool, _pool_key
    if _pool is None:
        return
    try:
        _pool.close(force=True)
    except oracledb.Error:
        pass
    _pool = None
    _pool_key = None


atexit.register(close_pool)
