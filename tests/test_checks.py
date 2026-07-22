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
