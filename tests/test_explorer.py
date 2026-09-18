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

    assert "id='x-variable'" in page
    assert "id='y-variable'" in page
    assert "Plotly.react" in page
    assert '"names":["b1","b2","g1","i01","c1","free"]' in page
    assert "<script src=" not in page
    assert before == (
        mip.attributes.rows,
        mip.attributes.cols,
        mip.attributes.mipents,
        int(mip.attributes.solvestatus),
    )


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
