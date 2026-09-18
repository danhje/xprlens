"""The public entry point."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from . import _compat
from ._xp import is_inf, xpress
from .classify import classify_rows
from .facts import (
    read_classification,
    read_effort,
    read_matrix,
    read_numerics,
    read_objective,
    read_shape,
    read_status,
    read_variables,
)
from .render import build_page
from .slice2d import build_slice, pick_pair

#: Every section, in page order. ``report(..., sections=...)`` takes any subset.
ALL_SECTIONS: tuple[str, ...] = (
    "status",
    "classification",
    "variables",
    "constraints",
    "objective",
    "effort",
    "numerics",
    "sparsity",
    "slice",
)

#: Sections that walk the whole constraint matrix. Drop these first if a very
#: large model makes report() slow.
MATRIX_SECTIONS: frozenset[str] = frozenset({"constraints", "numerics", "sparsity", "slice"})


def _package_version() -> str:
    try:
        from ._version import __version__

        return __version__
    except Exception:
        return "0+unknown"


def _reference_point(prob: Any, status, variables) -> tuple[list[float], str]:
    """A point to slice through, and an honest description of where it came from."""
    if status.has_solution:
        try:
            sol = [float(v) for v in prob.getSolution()]
            if len(sol) == variables.n:
                return sol, "the solution Xpress returned"
        except Exception:
            pass
    ref: list[float] = []
    for lo, hi in zip(variables.lb, variables.ub, strict=False):
        lo_inf, hi_inf = is_inf(lo), is_inf(hi)
        if lo_inf and hi_inf:
            ref.append(0.0)
        elif lo_inf:
            ref.append(hi)
        elif hi_inf:
            ref.append(lo)
        else:
            ref.append((lo + hi) / 2.0)
    return ref, "the midpoint of the variable bounds, which need not be feasible"


def report(
    prob: Any,
    *,
    sections: list[str] | tuple[str, ...] | None = None,
    path: str | Path | None = None,
    title: str | None = None,
    slice_vars: tuple[int, int] | tuple[str, str] | None = None,
    sparsity_cap: int = 60_000,
    open_browser: bool = False,
) -> Path:
    """Write a one-page HTML report for an Xpress problem.

    The problem is only read, never modified: no controls are set, no bounds
    changed, and no solve is triggered. A problem that has not been optimized is
    reported as such rather than having result figures invented for it.

    Args:
        prob: an ``xpress.problem``.
        sections: subset of :data:`ALL_SECTIONS`; ``None`` means all of them.
            The members of :data:`MATRIX_SECTIONS` are the expensive ones.
        path: output file. Defaults to ``<problem name>-xprlens.html`` in the
            working directory.
        title: page heading. Defaults to the problem's name.
        slice_vars: the two variables to slice through, as indices or names.
            Defaults to the two appearing in the most constraints.
        sparsity_cap: maximum non-zeros plotted before downsampling.
        open_browser: open the file when done.

    Returns:
        The path written.
    """
    xp = xpress()
    if not isinstance(prob, xp.problem):
        raise TypeError(f"expected an xpress.problem, got {type(prob).__name__}")

    wanted = list(ALL_SECTIONS if sections is None else sections)
    unknown = [s for s in wanted if s not in ALL_SECTIONS]
    if unknown:
        raise ValueError(f"unknown section(s) {unknown}; valid: {list(ALL_SECTIONS)}")

    status = read_status(prob)
    shape = read_shape(prob)
    cls = read_classification(prob)
    objective = read_objective(prob, status, cls)
    effort = read_effort(prob, status, cls)

    # On a presolved problem the accessors describe the presolved matrix and
    # there is no attribute that recovers the original entity count, so the
    # structural sections are withheld rather than reported wrongly.
    variables = matrix = numerics = shapes = slice_obj = None
    if not shape.presolved:
        if {"variables", "constraints", "numerics", "sparsity", "slice"} & set(wanted):
            variables = read_variables(prob, solved=status.started)
        if MATRIX_SECTIONS & set(wanted):
            matrix = read_matrix(prob, rows=shape.rows, cols=shape.cols)
        if matrix is not None and variables is not None:
            if "constraints" in wanted:
                shapes = classify_rows(matrix.rows, variables)
            if "numerics" in wanted:
                numerics = read_numerics(prob, matrix, variables)
            if "slice" in wanted and variables.n >= 2:
                pair = _resolve_pair(slice_vars, variables) or pick_pair(matrix, variables)
                if pair is not None:
                    x_ref, origin = _reference_point(prob, status, variables)
                    slice_obj = build_slice(matrix, variables, x_ref, origin, pair[0], pair[1])
    else:
        wanted = [s for s in wanted if s in {"status", "classification", "objective", "effort"}]

    # `prob.name` is a bound method in this API, not a string; the name lives
    # in the matrixname attribute (and is "noname" when unset).
    name = str(prob.attributes.matrixname or "problem")
    if name == "noname":
        name = "problem"
    page = build_page(
        title=title or f"{name} — xprlens",
        lib_version=_compat.library_version(xp),
        pkg_version=_package_version(),
        status=status,
        shape=shape,
        cls=cls,
        variables=variables,
        matrix=matrix,
        shapes=shapes,
        objective=objective,
        effort=effort,
        numerics=numerics,
        slice_=slice_obj,
        sections=wanted,
        sparsity_cap=sparsity_cap,
    )

    out = Path(path) if path is not None else Path(f"{name}-xprlens.html")
    out.write_text(page, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out


def _resolve_pair(spec, variables) -> tuple[int, int] | None:
    if spec is None:
        return None
    a, b = spec
    idx = []
    for item in (a, b):
        if isinstance(item, str):
            if item not in variables.names:
                raise ValueError(f"no variable named {item!r}")
            idx.append(variables.names.index(item))
        else:
            idx.append(int(item))
    if idx[0] == idx[1]:
        raise ValueError("slice_vars must name two different variables")
    return (idx[0], idx[1])
