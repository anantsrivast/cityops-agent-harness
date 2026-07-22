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
