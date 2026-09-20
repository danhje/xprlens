"""End-to-end contract for the interactive slice explorer."""

from __future__ import annotations

import pytest

from xprlens import slice_explorer


def test_slice_explorer_has_variable_controls_and_does_not_modify_problem(mip, tmp_path):
    before = (
        mip.attributes.rows,
        mip.attributes.cols,
        mip.attributes.mipents,
        int(mip.attributes.solvestatus),
    )

    out = slice_explorer(mip, path=tmp_path / "slice.html")
    page = out.read_text(encoding="utf-8")

    assert "id='h-variable'" in page
    assert "id='v-variable'" in page
    assert "id='fixed-variable'" in page
    assert "id='fixed-value'" in page
    assert "calculateSlice" in page
    assert "Plotly" not in page
    assert '"vars":[{"name":"b1","type":"B"' in page
    assert '"c":[5.0,4.0,3.0,1.0,1.0,0.0]' in page
    assert "<script src=" not in page
    assert before == (
        mip.attributes.rows,
        mip.attributes.cols,
        mip.attributes.mipents,
        int(mip.attributes.solvestatus),
    )


def test_slice_explorer_serializes_semicontinuous_threshold(xp, tmp_path):
    problem = xp.problem()
    problem.setOutputEnabled(False)
    semi = problem.addVariable(name="semi", lb=0, ub=6, vartype=xp.semicontinuous, threshold=2.0)
    other = problem.addVariable(name="other", lb=0, ub=4)
    problem.addConstraint(semi + other <= 7)
    problem.setObjective(3 * semi + other + 7, sense=xp.maximize)

    page = slice_explorer(problem, path=tmp_path / "slice.html").read_text(encoding="utf-8")

    assert '"name":"semi","type":"S","lo":0.0,"hi":6.0,"threshold":2.0' in page
    assert '"offset":7.0' in page
    assert "Semi-variable gap" in page


def test_slice_explorer_accepts_an_initial_pair_by_name(mip, tmp_path):
    page = slice_explorer(
        mip,
        path=tmp_path / "slice.html",
        slice_vars=("g1", "c1"),
    ).read_text(encoding="utf-8")

    assert '"initialPair":[2,4]' in page


def test_slice_explorer_rejects_out_of_range_indices(mip, tmp_path):
    with pytest.raises(ValueError, match="indices must be between 0 and 5"):
        slice_explorer(mip, path=tmp_path / "slice.html", slice_vars=(0, 6))


def test_slice_explorer_rejects_non_problem(xp, tmp_path):
    with pytest.raises(TypeError, match=r"expected an xpress\.problem"):
        slice_explorer(object(), path=tmp_path / "slice.html")


def test_slice_explorer_requires_two_variables(xp, tmp_path):
    problem = xp.problem()
    problem.setOutputEnabled(False)
    problem.addVariable(name="only")

    with pytest.raises(ValueError, match="at least two variables"):
        slice_explorer(problem, path=tmp_path / "slice.html")
