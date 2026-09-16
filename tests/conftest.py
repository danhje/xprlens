"""Shared fixtures.

Every test that needs a live solver goes through `xp`, which *skips* rather
than fails when Xpress is missing or its licence will not initialise. FICO
ships a community licence with a hard expiry date inside the wheel, so a green
CI run must not depend on that licence still being valid on the day it runs.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def xp():
    xpress = pytest.importorskip("xpress", reason="the xpress package is not installed")
    lic = os.environ.get("XPRESS_LICENCE") or os.environ.get("XPAUTH_PATH")
    try:
        if lic:
            xpress.init(lic)
        xpress.problem()
    except Exception as exc:  # licence expired, missing, or size-limited
        pytest.skip(f"Xpress licence unavailable: {exc}")
    return xpress


@pytest.fixture
def lp(xp):
    p = xp.problem(name="tiny_lp")
    p.setOutputEnabled(False)
    x = p.addVariable(name="x", lb=0, ub=10)
    y = p.addVariable(name="y", lb=0, ub=xp.infinity)
    p.addConstraint(x + y <= 8)
    p.addConstraint(x + 2 * y <= 12)
    p.setObjective(x + 1.5 * y, sense=xp.maximize)
    return p


@pytest.fixture
def mip(xp):
    p = xp.problem(name="tiny_mip")
    p.setOutputEnabled(False)
    b1 = p.addVariable(name="b1", vartype=xp.binary)
    b2 = p.addVariable(name="b2", vartype=xp.binary)
    g1 = p.addVariable(name="g1", vartype=xp.integer, lb=0, ub=7)
    i01 = p.addVariable(name="i01", vartype=xp.integer, lb=0, ub=1)
    c1 = p.addVariable(name="c1", lb=0, ub=20)
    free = p.addVariable(name="free", lb=-xp.infinity, ub=xp.infinity)
    p.addConstraint(3 * b1 + 4 * b2 + 2 * g1 + c1 <= 20)
    p.addConstraint(b1 + b2 + i01 <= 2)
    p.addConstraint(g1 + c1 >= 2)
    p.addConstraint(free <= 5)
    p.setObjective(5 * b1 + 4 * b2 + 3 * g1 + i01 + c1, sense=xp.maximize)
    return p
