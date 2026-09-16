"""Constraint shape classification, in the style of MIPLIB 2017.

MIPLIB orders its classes from most specific to most general and counts each
constraint once, under the first class it matches. This module follows that
ordering, with two deliberate, documented differences from MIPLIB proper:

* **No binary negation.** MIPLIB allows complementing binary variables when
  testing a match. xprlens does not, so a constraint that only becomes (say)
  set packing after negating some of its variables is reported one class more
  general. Counts are therefore conservative, and are not interchangeable with
  the numbers on miplib.zib.de.
* **Binpacking is folded into knapsack.** Its MIPLIB definition depends on
  linking structure across constraints that xprlens does not attempt to
  recover. Calling it out separately would imply a precision that is not there.

Both differences are stated on the rendered page as well, so nobody reads the
table as a MIPLIB reproduction.
"""

from __future__ import annotations

from .facts import Row, VariableFacts

CLASSES = [
    "empty",
    "free",
    "singleton",
    "aggregation",
    "precedence",
    "variable bound",
    "set partitioning",
    "set packing",
    "set covering",
    "cardinality",
    "invariant knapsack",
    "equation knapsack",
    "knapsack",
    "integer knapsack",
    "mixed binary",
    "general linear",
]

CAVEATS = [
    "Most specific class first; every constraint is counted exactly once.",
    "Unlike MIPLIB, binary variables are not negated when testing a match, so counts "
    "skew towards the more general classes and will not match miplib.zib.de exactly.",
    "MIPLIB's 'binpacking' class is folded into 'knapsack' here.",
]

_TOL = 1e-9


def _is_int(v: float) -> bool:
    return abs(v - round(v)) <= _TOL


def _binary(idx: int, var: VariableFacts) -> bool:
    if var.coltype[idx] == "B":
        return True
    return var.coltype[idx] == "I" and var.lb[idx] >= -_TOL and var.ub[idx] <= 1.0 + _TOL


def _integral(idx: int, var: VariableFacts) -> bool:
    return var.coltype[idx] in {"B", "I"}


def classify_row(row: Row, var: VariableFacts) -> str:
    coefs = row.coefs
    cols = row.cols
    k = len(cols)

    if k == 0:
        return "empty"
    if row.kind == "N":
        return "free"
    if k == 1:
        return "singleton"

    all_bin = all(_binary(c, var) for c in cols)
    all_int = all(_integral(c, var) for c in cols)
    any_bin = any(_binary(c, var) for c in cols)
    unit = all(abs(abs(a) - 1.0) <= _TOL for a in coefs)
    positive_unit = all(abs(a - 1.0) <= _TOL for a in coefs)
    rhs = row.rhs

    if k == 2 and row.kind == "E":
        return "aggregation"
    if k == 2 and unit and coefs[0] * coefs[1] < 0 and abs(rhs) <= _TOL:
        return "precedence"
    if k == 2 and any_bin and not all_bin:
        return "variable bound"

    if all_bin and positive_unit:
        if row.kind == "E" and abs(rhs - 1.0) <= _TOL:
            return "set partitioning"
        if row.kind == "L" and abs(rhs - 1.0) <= _TOL:
            return "set packing"
        if row.kind == "G" and abs(rhs - 1.0) <= _TOL:
            return "set covering"
        if row.kind == "E" and _is_int(rhs) and rhs >= 2 - _TOL:
            return "cardinality"
        if row.kind == "L" and _is_int(rhs) and rhs >= 2 - _TOL:
            return "invariant knapsack"

    if all_bin and all(_is_int(a) for a in coefs):
        if row.kind == "E":
            return "equation knapsack"
        if row.kind in {"L", "G"}:
            return "knapsack"

    if all_int and all(_is_int(a) for a in coefs) and row.kind in {"L", "G"}:
        return "integer knapsack"

    if any_bin:
        return "mixed binary"
    return "general linear"


def classify_rows(rows: list[Row], var: VariableFacts) -> dict[str, int]:
    counts = dict.fromkeys(CLASSES, 0)
    for row in rows:
        counts[classify_row(row, var)] += 1
    return {k: v for k, v in counts.items() if v}
