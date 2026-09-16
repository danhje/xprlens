"""Slice geometry. Pure arithmetic, so no solver is needed."""

from __future__ import annotations

from xprlens.facts import MatrixFacts, Row, VariableFacts
from xprlens.slice2d import build_slice


def _setup(kinds="CC", lbs=(0.0, 0.0), ubs=(10.0, 10.0)):
    var = VariableFacts(
        n=2,
        declared={},
        binary_declared=0,
        integer_unit_range=0,
        integer_general=0,
        bounds={},
        names=["x", "y"],
        coltype=list(kinds),
        lb=list(lbs),
        ub=list(ubs),
    )
    rows = [Row(0, "r0", "L", 8.0, 0.0, [0, 1], [1.0, 1.0])]
    return MatrixFacts(rows, 2, 0.5, {"L": 1}), var


def test_polygon_is_clipped_by_the_constraint():
    mat, var = _setup()
    sl = build_slice(mat, var, [0.0, 0.0], "test", 0, 1)
    assert sl.polygon
    for u, v in sl.polygon:
        assert u + v <= 8.0 + 1e-6


def test_lattice_only_when_both_slice_vars_are_discrete():
    mat, var = _setup(kinds="CC")
    assert build_slice(mat, var, [0.0, 0.0], "t", 0, 1).lattice_kind == "none"
    mat, var = _setup(kinds="II")
    sl = build_slice(mat, var, [0.0, 0.0], "t", 0, 1)
    assert sl.lattice_kind == "points"
    assert sl.lattice
    for u, v in sl.lattice:
        assert u + v <= 8.0 + 1e-9
    mat, var = _setup(kinds="IC")
    assert build_slice(mat, var, [0.0, 0.0], "t", 0, 1).lattice_kind == "segments"


def test_constraint_not_involving_the_pair_can_empty_the_slice():
    mat, var = _setup()
    var.n = 3
    var.names.append("z")
    var.coltype.append("C")
    var.lb.append(0.0)
    var.ub.append(10.0)
    # z <= 1 is a constant under the slice, and the reference point sets z = 5
    mat.rows.append(Row(1, "r1", "L", 1.0, 0.0, [2], [1.0]))
    sl = build_slice(mat, var, [0.0, 0.0, 5.0], "t", 0, 1)
    assert sl.empty_reason is not None
    assert "not involving them" in sl.empty_reason


def test_fractional_reference_point_suppresses_the_lattice():
    mat, var = _setup(kinds="II")
    var.n = 3
    var.names.append("z")
    var.coltype.append("I")
    var.lb.append(0.0)
    var.ub.append(10.0)
    mat.rows.append(Row(1, "r1", "L", 20.0, 0.0, [0, 2], [1.0, 1.0]))
    sl = build_slice(mat, var, [0.0, 0.0, 2.5], "t", 0, 1)
    assert sl.lattice == []
    assert any("fractional" in n for n in sl.notes)


def test_unbounded_slice_variable_gets_a_flagged_window():
    mat, var = _setup(ubs=(1e20, 10.0))
    sl = build_slice(mat, var, [0.0, 0.0], "t", 0, 1)
    assert any(sl.window_clipped)
    assert any("artificial" in n for n in sl.notes)
