"""Constraint shape classification, driven by hand-built rows (no solver)."""

from __future__ import annotations

from xprlens.classify import classify_row
from xprlens.facts import Row, VariableFacts


def _vars(types, lbs=None, ubs=None):
    n = len(types)
    lbs = lbs or [0.0] * n
    ubs = ubs or [1.0] * n
    return VariableFacts(
        n=n,
        declared={},
        binary_declared=0,
        integer_unit_range=0,
        integer_general=0,
        bounds={},
        names=[f"x{i}" for i in range(n)],
        coltype=list(types),
        lb=lbs,
        ub=ubs,
    )


def _row(kind, rhs, cols, coefs, rng=0.0):
    return Row(index=0, name="r", kind=kind, rhs=rhs, rng=rng, cols=cols, coefs=coefs)


def test_set_partitioning_packing_covering():
    v = _vars("BBB")
    assert classify_row(_row("E", 1.0, [0, 1, 2], [1, 1, 1]), v) == "set partitioning"
    assert classify_row(_row("L", 1.0, [0, 1, 2], [1, 1, 1]), v) == "set packing"
    assert classify_row(_row("G", 1.0, [0, 1, 2], [1, 1, 1]), v) == "set covering"


def test_cardinality_and_invariant_knapsack():
    v = _vars("BBBB")
    assert classify_row(_row("E", 3.0, [0, 1, 2, 3], [1, 1, 1, 1]), v) == "cardinality"
    assert classify_row(_row("L", 3.0, [0, 1, 2, 3], [1, 1, 1, 1]), v) == "invariant knapsack"


def test_knapsack_and_equation_knapsack():
    v = _vars("BBB")
    assert classify_row(_row("L", 9.0, [0, 1, 2], [3, 4, 5]), v) == "knapsack"
    assert classify_row(_row("E", 9.0, [0, 1, 2], [3, 4, 5]), v) == "equation knapsack"


def test_empty_free_and_singleton():
    v = _vars("BB")
    assert classify_row(_row("L", 1.0, [], []), v) == "empty"
    assert classify_row(_row("N", 0.0, [0, 1], [1, 1]), v) == "free"
    assert classify_row(_row("L", 1.0, [0], [1]), v) == "singleton"


def test_integer_variable_bounded_to_unit_range_counts_as_binary():
    # Trap H: Xpress keeps vartype 'I' for a variable bounded to [0, 1]; the
    # classifier must treat it as binary anyway.
    v = _vars("II", lbs=[0.0, 0.0], ubs=[1.0, 1.0])
    assert classify_row(_row("L", 1.0, [0, 1], [1, 1]), v) == "set packing"


def test_general_integer_is_not_treated_as_binary():
    v = _vars("II", lbs=[0.0, 0.0], ubs=[7.0, 7.0])
    assert classify_row(_row("L", 5.0, [0, 1], [1, 1]), v) == "integer knapsack"


def test_mixed_binary_and_general_linear():
    mixed = _vars("BCC", lbs=[0, 0, 0], ubs=[1, 10, 10])
    assert classify_row(_row("L", 5.0, [0, 1, 2], [1, 2.5, 3.5]), mixed) == "mixed binary"
    cont = _vars("CCC", lbs=[0, 0, 0], ubs=[10, 10, 10])
    assert classify_row(_row("L", 5.0, [0, 1, 2], [1, 2.5, 3.5]), cont) == "general linear"
