"""Extraction against a live solver. Skips when no licence is available."""

from __future__ import annotations

from xprlens.facts import (
    read_classification,
    read_effort,
    read_matrix,
    read_objective,
    read_shape,
    read_status,
    read_variables,
)


def test_unsolved_problem_is_reported_as_unsolved(mip):
    # Trap A/B: getObjVal() would return 1e+40 here without raising, and
    # mipstatus reads LP_NOT_OPTIMAL, which sounds like a result.
    st = read_status(mip)
    assert st.solve == "UNSTARTED"
    assert st.started is False
    assert st.has_solution is False
    assert st.mip == "LP_NOT_OPTIMAL"  # the misleading one
    assert "Not solved" in st.headline


def test_unsolved_problem_reports_no_objective(mip):
    st = read_status(mip)
    cls = read_classification(mip)
    obj = read_objective(mip, st, cls)
    assert obj.value is None
    assert obj.abs_gap is None
    assert obj.gap_applies is False


def test_solved_lp_has_value_but_no_gap(lp):
    lp.optimize()
    st = read_status(lp)
    cls = read_classification(lp)
    obj = read_objective(lp, st, cls)
    assert st.sol == "OPTIMAL"
    assert st.proven_optimal is True
    assert obj.value is not None
    # Trap H: bestbound is populated for an LP, but a MIP gap does not apply.
    assert cls.discrete is False
    assert obj.gap_applies is False


def test_solved_mip_has_gap(mip):
    mip.optimize()
    st = read_status(mip)
    cls = read_classification(mip)
    obj = read_objective(mip, st, cls)
    assert cls.discrete is True
    assert cls.label == "MILP"
    assert obj.gap_applies is True
    assert obj.abs_gap is not None and obj.abs_gap >= 0.0


def test_infeasible_is_distinguishable_from_unsolved(xp):
    p = xp.problem(name="infeasible")
    p.setOutputEnabled(False)
    a = p.addVariable(name="a", vartype=xp.binary)
    b = p.addVariable(name="b", vartype=xp.binary)
    p.addConstraint(a + b >= 2)
    p.addConstraint(a + b <= 1)
    p.setObjective(a + b)
    p.optimize()
    st = read_status(p)
    assert st.started is True
    assert st.sol == "INFEASIBLE"
    assert st.has_solution is False
    obj = read_objective(p, st, read_classification(p))
    assert obj.value is None  # 1e+40 must not be shown as an objective


def test_variable_type_and_bound_classification(mip):
    v = read_variables(mip)
    assert v.n == 6
    assert v.binary_declared == 2
    assert v.integer_unit_range == 1  # i01, declared integer with ub 1
    assert v.integer_general == 1  # g1, ub 7
    assert v.bounds["free"] == 1
    assert v.bounds["boxed"] >= 1


def test_shape_reports_not_presolved_for_a_normal_problem(mip):
    shape = read_shape(mip)
    assert shape.presolved is False
    assert shape.rows == shape.input_rows
    assert shape.cols == shape.input_cols


def test_presolved_problem_is_detected_and_flagged(xp):
    # Trap F: after an explicit presolve the accessors describe the presolved
    # matrix, and originalrows/originalcols follow it down. postsolve() does
    # not restore them.
    p = xp.problem(name="presolved")
    p.setOutputEnabled(False)
    xs = [p.addVariable(name=f"v{i}", vartype=xp.binary) for i in range(8)]
    p.addConstraint(xs[0] + xs[1] <= 1)
    p.addConstraint(xs[0] + xs[1] <= 2)
    p.addConstraint(xs[2] == 1)
    p.setObjective(sum(xs), sense=xp.maximize)
    before = read_shape(p)
    assert before.presolved is False
    p.presolve()
    after = read_shape(p)
    assert after.presolved is True
    assert after.input_rows == before.rows
    assert after.input_cols == before.cols
    assert after.note is not None


def test_effort_separates_nodes_from_simplex_iterations(mip):
    mip.optimize()
    st = read_status(mip)
    eff = read_effort(mip, st, read_classification(mip))
    labels = [name for name, _, _ in eff.entries]
    # Trap G: these must never be collapsed into one "iterations" figure.
    assert "Simplex iterations" in labels
    assert "Branch-and-bound nodes" in labels
    assert not any(label.strip().lower() == "iterations" for label in labels)


def test_matrix_row_intervals(mip):
    mat = read_matrix(mip)
    assert len(mat.rows) == 4
    assert mat.nnz > 0
    for row in mat.rows:
        lo, hi = row.interval()
        assert lo <= hi


def test_solving_rewrites_column_types_and_the_report_says_so(xp):
    # Trap I: an integer variable bounded to [0,1] is coltype 'I' before the
    # solve and 'B' after. The declared-vs-effective split the user asked for
    # therefore depends on when the report is taken, so it must be flagged.
    p = xp.problem(name="retype")
    p.setOutputEnabled(False)
    a = p.addVariable(name="a", vartype=xp.integer, lb=0, ub=1)
    b = p.addVariable(name="b", vartype=xp.integer, lb=0, ub=7)
    p.addConstraint(a + b <= 5)
    p.setObjective(a + b, sense=xp.maximize)

    before = read_variables(p, solved=False)
    assert before.integer_unit_range == 1
    assert before.binary_declared == 0
    assert not any("rewrites column types" in n for n in before.notes)

    p.optimize()
    after = read_variables(p, solved=True)
    assert after.binary_declared == 1  # Xpress folded it into B
    assert after.integer_unit_range == 0
    assert any("rewrites column types" in n for n in after.notes)
