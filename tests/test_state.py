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


def test_registry_seeds_notebook_01():
    checks = REGISTRY["01_self_improving_copilot"]
    descs = " ".join(c.description for c in checks)
    sqls = " ".join(c.sql for c in checks)
    assert len(checks) == 4
    assert "CITY_INSPECTION_FINDING" in sqls
    assert "HARNESS_TOOLS" in sqls
    assert "HARNESS_WORKFLOW" in sqls
    assert "HARNESS_SKILLS" in sqls
    assert "domain data" in descs


def test_registry_seeds_notebook_02():
    checks = REGISTRY["02_scheduled_briefings"]
    sqls = " ".join(c.sql for c in checks)
    assert len(checks) == 6
    for t in ("HARNESS_SCRATCH", "HARNESS_PROMOTION_QUEUE", "HARNESS_MEMORY_META",
              "HARNESS_BRIEFING", "CITY_MEMORY"):
        assert t in sqls
    assert "user_scheduler_jobs" in sqls


def test_registry_seeds_notebook_03():
    checks = REGISTRY["03_context_engineering"]
    sqls = " ".join(c.sql for c in checks)
    assert len(checks) == 3
    for t in ("HARNESS_TRANSCRIPT", "HARNESS_CARD", "HARNESS_BLOB"):
        assert t in sqls


def test_registry_seeds_notebook_04():
    checks = REGISTRY["04_evals"]
    sqls = " ".join(c.sql for c in checks)
    assert len(checks) == 2
    assert "HARNESS_EVAL" in sqls
    assert "5" in sqls  # the >=5 distinct-evals gate
