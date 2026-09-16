"""End-to-end: the report must build for every problem state."""

from __future__ import annotations

import pytest

from xprlens import ALL_SECTIONS, report


def test_report_on_unsolved_problem(mip, tmp_path):
    out = report(mip, path=tmp_path / "r.html")
    page = out.read_text(encoding="utf-8")
    assert out.exists() and len(page) > 10_000
    assert "Not solved" in page
    assert "not affiliated with" in page.lower()


def test_report_on_solved_mip_mentions_the_gap_formula(mip, tmp_path):
    mip.optimize()
    page = report(mip, path=tmp_path / "r.html").read_text(encoding="utf-8")
    assert "MIPRELSTOP" in page
    assert "miprelstop" in page


def test_report_on_solved_lp(lp, tmp_path):
    lp.optimize()
    page = report(lp, path=tmp_path / "r.html").read_text(encoding="utf-8")
    assert "LP" in page


def test_report_does_not_modify_the_problem(mip, tmp_path):
    before = (
        mip.attributes.rows,
        mip.attributes.cols,
        mip.attributes.mipents,
        int(mip.attributes.solvestatus),
        float(mip.controls.miprelstop),
    )
    report(mip, path=tmp_path / "r.html")
    after = (
        mip.attributes.rows,
        mip.attributes.cols,
        mip.attributes.mipents,
        int(mip.attributes.solvestatus),
        float(mip.controls.miprelstop),
    )
    assert before == after


def test_sections_can_be_subset(mip, tmp_path):
    out = report(mip, sections=["status", "objective"], path=tmp_path / "r.html")
    page = out.read_text(encoding="utf-8")
    assert "id='status'" in page
    assert "id='spy'" not in page


def test_unknown_section_is_rejected(mip, tmp_path):
    with pytest.raises(ValueError, match="unknown section"):
        report(mip, sections=["nope"], path=tmp_path / "r.html")


def test_every_declared_section_is_accepted(mip, tmp_path):
    mip.optimize()
    for name in ALL_SECTIONS:
        report(mip, sections=[name], path=tmp_path / f"{name}.html")


def test_non_problem_argument_is_rejected(xp, tmp_path):
    with pytest.raises(TypeError):
        report(object(), path=tmp_path / "r.html")


def test_problem_name_is_read_from_the_attribute_not_the_method(xp, tmp_path):
    # prob.name is a bound method here; reading it as a string leaked a repr
    # like "<built-in method name of xpress.problem ...>" into the page title.
    p = xp.problem(name="named_problem")
    p.setOutputEnabled(False)
    p.addVariable(name="a", lb=0, ub=1)
    page = report(p, path=tmp_path / "r.html").read_text(encoding="utf-8")
    assert "named_problem" in page
    assert "built-in method" not in page


def test_unnamed_problem_does_not_render_noname(xp, tmp_path):
    p = xp.problem()
    p.setOutputEnabled(False)
    p.addVariable(name="a", lb=0, ub=1)
    page = report(p, path=tmp_path / "r.html").read_text(encoding="utf-8")
    assert "noname" not in page
