"""Lazy access to the `xpress` module, and the sentinel arithmetic around it.

Two different sentinels matter and they are not interchangeable:

* **Bounds** use ``xpress.infinity``, which is ``1e+20``. The Xpress docs say a
  bound *greater than or equal to* that counts as infinite, so the test is
  ``>=``, never ``==``.
* **"no incumbent"** in ``mipobjval`` / ``mipbestobjval`` / ``bestbound`` is
  ``1e+40``, whose **sign follows the objective sense** (``+1e40`` when
  minimising, ``-1e40`` when maximising). ``1e40 == xpress.infinity`` is
  ``False``, so a bounds-style test silently fails to catch it.

Everything here is read-only. Nothing in xprlens may mutate the caller's
problem -- not its controls, not its bounds, not its solution state.
"""

from __future__ import annotations

from typing import Any

#: Bound sentinel. Equal to ``xpress.infinity``; hard-coded so that bound
#: classification does not require importing xpress.
BOUND_INF = 1e20

#: Anything at least this large in magnitude is an Xpress "unset" marker rather
#: than a number the caller would recognise. Sits between the two sentinels so
#: it catches 1e40 without catching a legitimate large bound at 1e20.
UNSET_MAGNITUDE = 1e30


def xpress() -> Any:
    """Import and return the ``xpress`` module, with a useful error if absent."""
    try:
        import xpress
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "xprlens needs the `xpress` package to read a problem. "
            "Install it with `pip install xpress` (FICO ships a size-limited "
            "community licence with it)."
        ) from exc
    return xpress


def is_inf(value: float) -> bool:
    """True if ``value`` is an infinite *bound*."""
    return abs(value) >= BOUND_INF


def is_unset(value: float) -> bool:
    """True if ``value`` is an Xpress "not available" marker (the 1e40 family)."""
    return abs(value) >= UNSET_MAGNITUDE


def enum_name(value: Any) -> str:
    """Name of an Xpress enum member, or ``str(value)`` for a plain int."""
    return getattr(value, "name", None) or str(value)


def enum_value(value: Any) -> int:
    """Integer value of an Xpress enum member, or the int itself."""
    return int(getattr(value, "value", value))
