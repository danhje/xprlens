"""The sentinel arithmetic, which needs no solver."""

from __future__ import annotations

from xprlens._xp import BOUND_INF, UNSET_MAGNITUDE, is_inf, is_unset


def test_bound_infinity_is_1e20_and_test_is_inclusive():
    assert BOUND_INF == 1e20
    assert is_inf(1e20)
    assert is_inf(-1e20)
    assert is_inf(1e25)
    assert not is_inf(9.9e19)


def test_unset_marker_is_distinct_from_bound_infinity():
    # Trap E: these are two different sentinels. A bound of 1e20 is a real
    # (infinite) bound; 1e40 in mipobjval means "no incumbent".
    assert is_unset(1e40)
    assert is_unset(-1e40)
    assert not is_unset(1e20)
    assert UNSET_MAGNITUDE > BOUND_INF


def test_unset_catches_both_signs():
    # the sentinel's sign follows the objective sense
    assert is_unset(1e40) and is_unset(-1e40)
