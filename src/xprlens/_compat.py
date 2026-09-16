"""Accessor names that changed between Xpress versions.

Xpress 9.8 renamed the problem accessors from the C-style
``getlb(out_list, first, last)`` to ``getLB(first, last) -> list``, and 9.9
renamed ``xpress.getversion`` to ``xpress.getVersion``. The old spellings still
work but emit ``DeprecationWarning``, so they will go away.

xprlens supports both: each helper tries the modern call and falls back to the
legacy one. The test suite turns Xpress deprecation warnings into errors (see
``filterwarnings`` in pyproject.toml), so CI -- which installs the newest
xpress -- fails if a legacy path is ever reached, while local development on an
older pinned version exercises the fallback.
"""

from __future__ import annotations

from typing import Any


def _ranged(prob: Any, new: str, old: str, first: int, last: int) -> list:
    """`getX(first, last) -> list` if available, else `getx(out, first, last)`."""
    fn = getattr(prob, new, None)
    if fn is not None:
        try:
            return list(fn(first, last))
        except TypeError:
            pass
    out: list = []
    getattr(prob, old)(out, first, last)
    return out


def library_version(xp: Any) -> str:
    fn = getattr(xp, "getVersion", None) or xp.getversion
    return str(fn())


def col_types(prob: Any, n: int) -> list[str]:
    return [] if n <= 0 else [str(t) for t in _ranged(prob, "getColType", "getcoltype", 0, n - 1)]


def lower_bounds(prob: Any, n: int) -> list[float]:
    return [] if n <= 0 else [float(v) for v in _ranged(prob, "getLB", "getlb", 0, n - 1)]


def upper_bounds(prob: Any, n: int) -> list[float]:
    return [] if n <= 0 else [float(v) for v in _ranged(prob, "getUB", "getub", 0, n - 1)]


def row_types(prob: Any, m: int) -> list[str]:
    return [] if m <= 0 else [str(t) for t in _ranged(prob, "getRowType", "getrowtype", 0, m - 1)]


def rhs(prob: Any, m: int) -> list[float]:
    return [] if m <= 0 else [float(v) for v in _ranged(prob, "getRHS", "getrhs", 0, m - 1)]


def rhs_range(prob: Any, m: int) -> list[float]:
    return (
        [] if m <= 0 else [float(v) for v in _ranged(prob, "getRHSRange", "getrhsrange", 0, m - 1)]
    )


def obj_coefficients(prob: Any, n: int) -> list[float]:
    return [] if n <= 0 else [float(v) for v in _ranged(prob, "getObj", "getobj", 0, n - 1)]


def name_list(prob: Any, namespace: Any, count: int) -> list[str]:
    if count <= 0:
        return []
    fn = getattr(prob, "getNameList", None)
    if fn is not None:
        try:
            return [str(s) for s in fn(namespace, 0, count - 1)]
        except TypeError:
            pass
    return [str(s) for s in prob.getnamelist(namespace, 0, count - 1)]


def matrix_rows(prob: Any, m: int, maxcoefs: int) -> tuple[list[int], list[Any], list[float]]:
    """Row-wise non-zeros as (start, column handles, coefficients)."""
    if m <= 0:
        return ([], [], [])
    start: list[int] = []
    colind: list[Any] = []
    coefs: list[float] = []
    fn = getattr(prob, "getRows", None)
    if fn is not None:
        try:
            fn(start, colind, coefs, maxcoefs, 0, m - 1)
            return (start, colind, coefs)
        except TypeError:
            start, colind, coefs = [], [], []
    prob.getrows(start, colind, coefs, maxcoefs, 0, m - 1)
    return (start, colind, coefs)


def column_index(prob: Any, handle: Any) -> int:
    """Index of a column, given whatever `getRows` put in its index array."""
    if isinstance(handle, int):
        return handle
    idx = getattr(handle, "index", None)
    if isinstance(idx, int):
        return idx
    return int(prob.getIndex(handle))
