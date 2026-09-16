"""Pull facts out of an Xpress problem, refusing to report anything that would
be untrue.

Read AGENTS.md before changing this file. Most of what looks like defensive
paranoia here is guarding against a specific, reproduced way that Xpress
reports something misleading on an unsolved, truncated or presolved problem.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from ._xp import enum_name, is_inf, is_unset, xpress

# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

#: StopType values that mean the search was cut short rather than finishing.
_TRUNCATING_STOPS = {
    "TIMELIMIT",
    "CTRLC",
    "NODELIMIT",
    "ITERLIMIT",
    "SOLLIMIT",
    "MEMORYERROR",
    "USER",
    "WORKLIMIT",
    "LICENSELOST",
    "NUMERICALERROR",
    "GENERICERROR",
}


@dataclass
class Status:
    solve: str
    sol: str
    stop: str
    lp: str
    mip: str
    started: bool
    has_solution: bool
    proven_optimal: bool
    headline: str
    caveats: list[str] = field(default_factory=list)


def read_status(prob: Any) -> Status:
    """The (solvestatus, solstatus, stopstatus) triple, in plain English.

    ``mipstatus`` and ``getProbStatusString()`` are deliberately *not* used to
    decide whether the problem has been solved: on a never-solved MIP they read
    ``LP_NOT_OPTIMAL`` / ``'mip_lp_not_optimal'``, which sounds like a finding
    about the relaxation but means nothing has run. See AGENTS.md Trap B.
    """
    a = prob.attributes
    solve = enum_name(a.solvestatus)
    sol = enum_name(a.solstatus)
    lp = enum_name(a.lpstatus)
    mip = enum_name(a.mipstatus)

    xp = xpress()
    try:
        stop = enum_name(xp.StopType(int(a.stopstatus)))
    except Exception:  # pragma: no cover - unknown future code
        stop = str(a.stopstatus)

    started = solve != "UNSTARTED"
    has_solution = sol in {"OPTIMAL", "FEASIBLE"}

    caveats: list[str] = []
    if not started:
        headline = "Not solved — this problem has never been optimized"
        caveats.append(
            "No objective value, solution, bound or iteration count is available. "
            "Xpress returns 0.0 (LP) or 1e+40 (MIP) from getObjVal() here rather "
            "than raising, so any such figure would be fabricated."
        )
    elif solve == "FAILED":
        headline = "Solve failed"
    elif sol == "INFEASIBLE":
        headline = "Solved — proven infeasible"
    elif sol == "UNBOUNDED":
        headline = "Solved — unbounded"
    elif sol == "NOTFOUND":
        headline = f"Stopped ({stop}) — no feasible solution found"
    elif sol == "OPTIMAL":
        headline = "Solved — optimal"
    else:
        headline = f"Stopped ({stop}) — feasible solution found, not proven optimal"

    truncated = stop in _TRUNCATING_STOPS
    if truncated:
        caveats.append(
            f"The search was cut short (stopstatus = {stop}); it did not run to completion."
        )

    # Trap C: Xpress reports solstatus OPTIMAL for a solution that merely met
    # the relative/absolute stopping tolerance. "Optimal" is only honest when
    # the remaining gap is zero.
    proven_optimal = sol == "OPTIMAL" and not truncated
    if sol == "OPTIMAL" and stop == "MIPGAP":
        caveats.append(
            "Xpress reports OPTIMAL, but the search stopped on the MIP gap tolerance "
            "(stopstatus = MIPGAP). Check the gap below before calling this optimal."
        )

    return Status(
        solve=solve,
        sol=sol,
        stop=stop,
        lp=lp,
        mip=mip,
        started=started,
        has_solution=has_solution,
        proven_optimal=proven_optimal,
        headline=headline,
        caveats=caveats,
    )


# --------------------------------------------------------------------------
# presolve guard
# --------------------------------------------------------------------------


@dataclass
class ModelShape:
    rows: int
    cols: int
    mipents: int
    input_rows: int
    input_cols: int
    presolved: bool
    note: str | None


def read_shape(prob: Any) -> ModelShape:
    """Detect whether the accessors still describe the caller's model.

    After an explicit ``presolve()`` the matrix accessors describe the
    *presolved* problem, and ``originalrows`` / ``originalcols`` /
    ``originalmipents`` follow it down -- they do not mean "the user's model".
    ``postsolve()`` does not restore them. Only ``inputrows`` / ``inputcols``
    survive. See AGENTS.md Trap F.
    """
    a = prob.attributes
    rows, cols = int(a.rows), int(a.cols)
    in_rows, in_cols = int(a.inputrows), int(a.inputcols)
    presolved = (rows, cols) != (in_rows, in_cols)
    note = None
    if presolved:
        note = (
            f"This problem is in a presolved state: the matrix now has {rows} rows and "
            f"{cols} columns, while the model you built had {in_rows} rows and {in_cols} "
            "columns. Structural sections are withheld, because the accessors would "
            "describe the presolved matrix rather than your model, and Xpress offers no "
            "attribute that recovers the original MIP entity count."
        )
    return ModelShape(rows, cols, int(a.mipents), in_rows, in_cols, presolved, note)


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------


@dataclass
class Classification:
    label: str
    discrete: bool
    quadratic_objective: bool
    quadratic_constraints: bool
    features: dict[str, int]


def read_classification(prob: Any) -> Classification:
    a = prob.attributes
    mipents = int(a.mipents)
    qobj = int(a.qelems) > 0
    qcon = int(a.qconstraints) > 0
    nonlinear = int(getattr(a, "nonlinearconstraints", 0) or 0) > 0

    discrete = mipents > 0 or int(a.sets) > 0

    if nonlinear:
        label = "MINLP" if discrete else "NLP"
    elif qcon:
        label = "MIQCQP" if discrete else "QCQP"
    elif qobj:
        label = "MIQP" if discrete else "QP"
    else:
        label = "MILP" if discrete else "LP"

    features = {
        "MIP entities": mipents,
        "SOS sets": int(a.sets),
        "Indicator constraints": int(a.indicators),
        "Piecewise-linear constraints": int(a.pwlcons),
        "General constraints": int(a.gencons),
        "Quadratic objective terms": int(a.qelems),
        "Quadratic constraints": int(a.qconstraints),
        "Objectives": int(a.objectives),
    }
    return Classification(label, discrete, qobj, qcon, features)


# --------------------------------------------------------------------------
# variables
# --------------------------------------------------------------------------

COLTYPE_NAMES = {
    "C": "continuous",
    "I": "integer",
    "B": "binary",
    "S": "semi-continuous",
    "R": "semi-continuous integer",
    "P": "partial integer",
}


@dataclass
class VariableFacts:
    n: int
    declared: dict[str, int]
    binary_declared: int
    integer_unit_range: int
    integer_general: int
    bounds: dict[str, int]
    names: list[str]
    coltype: list[str]
    lb: list[float]
    ub: list[float]
    notes: list[str] = field(default_factory=list)


def read_variables(prob: Any, *, solved: bool = False) -> VariableFacts:
    a = prob.attributes
    n = int(a.cols)
    coltype: list[str] = []
    lb: list[float] = []
    ub: list[float] = []
    if n:
        prob.getcoltype(coltype, 0, n - 1)
        prob.getlb(lb, 0, n - 1)
        prob.getub(ub, 0, n - 1)
    names = prob.getnamelist(xpress().Namespaces.COLUMN, 0, n - 1) if n else []

    declared = dict.fromkeys(COLTYPE_NAMES, 0)
    for t in coltype:
        declared[t] = declared.get(t, 0) + 1

    # Trap H: a variable declared xp.integer with bounds [0, 1] keeps type 'I';
    # Xpress does not reclassify it. It is binary in effect, and the user asked
    # to be able to tell those apart from genuinely general integers.
    binary_declared = declared.get("B", 0)
    integer_unit_range = 0
    integer_general = 0
    for t, lo, hi in zip(coltype, lb, ub, strict=False):
        if t != "I":
            continue
        if not is_inf(lo) and not is_inf(hi) and lo >= 0.0 and hi <= 1.0:
            integer_unit_range += 1
        else:
            integer_general += 1

    buckets = dict.fromkeys(["free", "lower bound only", "upper bound only", "boxed", "fixed"], 0)
    for lo, hi in zip(lb, ub, strict=False):
        lo_inf, hi_inf = is_inf(lo), is_inf(hi)
        if lo_inf and hi_inf:
            buckets["free"] += 1
        elif hi_inf:
            buckets["lower bound only"] += 1
        elif lo_inf:
            buckets["upper bound only"] += 1
        elif lo == hi:
            buckets["fixed"] += 1
        else:
            buckets["boxed"] += 1

    notes = []
    if solved:
        # Trap I: optimize() rewrites coltype. An integer variable bounded to
        # [0, 1] is 'I' before the solve and 'B' after, so on a solved problem
        # the B/I split reflects what Xpress did, not what you declared, and the
        # "bounds within [0,1]" row will usually read 0.
        notes.append(
            "This problem has been solved, and solving rewrites column types: an integer "
            "variable bounded to [0,1] is reported as binary afterwards. The split below "
            "therefore reflects how Xpress types the columns now, not how they were "
            "declared. Run report() before optimize() to see the declared split."
        )
    notes += [
        "'Continuous' counts declarations. A continuous variable may still be forced "
        "integral once the integer variables are fixed (MIPLIB calls these implicit "
        "integers); xprlens does not detect that.",
        f"A bound counts as infinite when |value| >= {1e20:g} (xpress.infinity), which is "
        "how Xpress encodes 'no bound' -- there is no separate unset flag.",
    ]

    return VariableFacts(
        n=n,
        declared=declared,
        binary_declared=binary_declared,
        integer_unit_range=integer_unit_range,
        integer_general=integer_general,
        bounds=buckets,
        names=names,
        coltype=coltype,
        lb=lb,
        ub=ub,
        notes=notes,
    )


# --------------------------------------------------------------------------
# objective, bound and gap
# --------------------------------------------------------------------------


@dataclass
class ObjectiveFacts:
    sense: str
    value: float | None
    bound: float | None
    abs_gap: float | None
    rel_gap: float | None
    gap_applies: bool
    gap_formula: str
    tolerances: dict[str, float]
    notes: list[str] = field(default_factory=list)


#: Xpress stops when |MIPOBJVAL - BESTBOUND| <= MIPRELSTOP * max(|BESTBOUND|, |MIPOBJVAL|).
#: The denominator is max(|bound|, |incumbent|) -- not |bound| and not |incumbent|.
#: Using another convention would print a gap that disagrees with the solver's
#: own stopping decision. See AGENTS.md Trap D.
GAP_FORMULA = "|incumbent - bound| / max(|bound|, |incumbent|)   (the MIPRELSTOP definition)"


def read_objective(prob: Any, status: Status, cls: Classification) -> ObjectiveFacts:
    a = prob.attributes
    sense = "maximize" if float(a.objsense) < 0 else "minimize"

    tolerances = {}
    for ctl in ("miprelstop", "mipabsstop", "timelimit"):
        with contextlib.suppress(Exception):  # pragma: no cover
            tolerances[ctl] = float(getattr(prob.controls, ctl))

    notes: list[str] = []
    value: float | None = None
    bound: float | None = None

    if not status.started:
        notes.append(
            "Not solved, so no objective value is shown. getObjVal() would return 0.0 for "
            "an LP and 1e+40 for a MIP here, without raising."
        )
        return ObjectiveFacts(sense, None, None, None, None, False, GAP_FORMULA, tolerances, notes)

    if status.has_solution:
        raw = float(a.mipobjval) if cls.discrete else float(a.objval)
        value = None if is_unset(raw) else raw
        if value is None:
            notes.append("Xpress reports a solution status but no finite objective value.")
    else:
        notes.append(
            f"No solution to report (solstatus = {status.sol}); the objective is omitted "
            "rather than shown as a sentinel."
        )

    raw_bound = float(a.bestbound)
    if not is_unset(raw_bound):
        bound = raw_bound

    # A pure LP also populates bestbound (it equals the LP objective). Showing a
    # "gap" there would invent a MIP concept that does not apply. See Trap H.
    gap_applies = cls.discrete and value is not None and bound is not None
    abs_gap = rel_gap = None
    if gap_applies:
        abs_gap = abs(value - bound)
        denom = max(abs(bound), abs(value))
        rel_gap = abs_gap / denom if denom > 0 else 0.0
    elif cls.discrete and value is None:
        notes.append(
            "No incumbent, so no gap is shown. Computing one from the sentinel would give a "
            "meaningless figure -- on a timed-out run it comes out as exactly 100%."
        )
    elif not cls.discrete:
        notes.append(
            "This is a continuous problem. bestbound is populated (it equals the LP "
            "objective), but a MIP optimality gap does not apply and is not shown."
        )

    return ObjectiveFacts(
        sense, value, bound, abs_gap, rel_gap, gap_applies, GAP_FORMULA, tolerances, notes
    )


# --------------------------------------------------------------------------
# solver effort
# --------------------------------------------------------------------------


@dataclass
class EffortFacts:
    entries: list[tuple[str, int | float, str]]
    notes: list[str] = field(default_factory=list)


def read_effort(prob: Any, status: Status, cls: Classification) -> EffortFacts:
    a = prob.attributes
    if not status.started:
        return EffortFacts([], ["Not solved — no iteration or node counts exist yet."])

    entries: list[tuple[str, int | float, str]] = [
        (
            "Simplex iterations",
            int(a.simplexiter),
            "summed over every LP solved, including every node relaxation",
        ),
        (
            "Barrier iterations",
            int(a.bariter),
            "interior-point iterations; 0 when the barrier was not used",
        ),
        (
            "Crossover iterations",
            int(getattr(a, "crossoveriter", 0) or 0),
            "simplex clean-up after the barrier",
        ),
    ]
    if cls.discrete:
        entries += [
            ("Branch-and-bound nodes", int(a.nodes), "0 means the search finished at the root"),
            ("Nodes left", int(a.activenodes), "unexplored nodes remaining when the solve ended"),
            ("Integer solutions found", int(a.mipsols), ""),
        ]
    entries.append(("Solve time (s)", round(float(a.time), 3), "wall clock as reported by Xpress"))

    notes = [
        "These are separate quantities, not one 'iterations' number. On a timed-out "
        "42-binary model measured during development, nodes was 391,541 while "
        "simplexiter was 1,167,684 — about 3 simplex iterations per node. Reporting "
        "either alone as 'iterations used' would be wrong.",
        "Iteration counts depend on presolve, cuts and heuristics, so they are not a "
        "stable measure of problem difficulty between runs.",
    ]
    return EffortFacts(entries, notes)


# --------------------------------------------------------------------------
# constraints and the matrix
# --------------------------------------------------------------------------

ROWTYPE_NAMES = {
    "N": "free (non-binding)",
    "L": "<=",
    "E": "=",
    "G": ">=",
    "R": "range",
}


@dataclass
class Row:
    index: int
    name: str
    kind: str
    rhs: float
    rng: float
    cols: list[int]
    coefs: list[float]

    def interval(self) -> tuple[float, float]:
        """(lower, upper) implied by the row type. Range rows are [rhs-|range|, rhs]."""
        if self.kind == "L":
            return (-float("inf"), self.rhs)
        if self.kind == "G":
            return (self.rhs, float("inf"))
        if self.kind == "E":
            return (self.rhs, self.rhs)
        if self.kind == "R":
            return (self.rhs - abs(self.rng), self.rhs)
        return (-float("inf"), float("inf"))


@dataclass
class MatrixFacts:
    rows: list[Row]
    nnz: int
    density: float
    rowtypes: dict[str, int]


def read_matrix(prob: Any) -> MatrixFacts:
    """Read the full constraint matrix, row-wise.

    ``getrows`` hands back *variable objects* in the index array in this API,
    not integers, so they are mapped through ``getIndex``.
    """
    a = prob.attributes
    m, n = int(a.rows), int(a.cols)
    if m == 0:
        return MatrixFacts([], 0, 0.0, {})

    rowtype: list[str] = []
    rhs: list[float] = []
    rng: list[float] = []
    prob.getrowtype(rowtype, 0, m - 1)
    prob.getrhs(rhs, 0, m - 1)
    prob.getrhsrange(rng, 0, m - 1)
    names = prob.getnamelist(xpress().Namespaces.ROW, 0, m - 1)

    start: list[int] = []
    colind: list[Any] = []
    coefs: list[float] = []
    prob.getrows(start, colind, coefs, int(a.elems) + m + 1, 0, m - 1)

    indices: list[int] = []
    for c in colind:
        indices.append(c if isinstance(c, int) else prob.getIndex(c))

    rows: list[Row] = []
    for i in range(m):
        lo, hi = start[i], start[i + 1]
        rows.append(
            Row(
                index=i,
                name=names[i],
                kind=rowtype[i],
                rhs=float(rhs[i]),
                rng=float(rng[i]),
                cols=indices[lo:hi],
                coefs=[float(v) for v in coefs[lo:hi]],
            )
        )

    counts: dict[str, int] = {}
    for t in rowtype:
        counts[t] = counts.get(t, 0) + 1
    nnz = len(indices)
    density = nnz / (m * n) if m and n else 0.0
    return MatrixFacts(rows, nnz, density, counts)


# --------------------------------------------------------------------------
# numerics
# --------------------------------------------------------------------------


@dataclass
class NumericsFacts:
    ranges: list[tuple[str, float | None, float | None, float | None]]
    notes: list[str] = field(default_factory=list)


def _range_of(
    values: list[float], *, drop_inf: bool = False
) -> tuple[float | None, float | None, float | None]:
    vals = [abs(v) for v in values if v != 0.0]
    if drop_inf:
        vals = [v for v in vals if v < 1e20]
    if not vals:
        return (None, None, None)
    lo, hi = min(vals), max(vals)
    return (lo, hi, (hi / lo) if lo > 0 else None)


def read_numerics(prob: Any, mat: MatrixFacts, var: VariableFacts) -> NumericsFacts:
    matrix_vals = [c for r in mat.rows for c in r.coefs]
    obj: list[float] = []
    if var.n:
        prob.getobj(obj, 0, var.n - 1)
    rhs_vals = [r.rhs for r in mat.rows]
    bnd_vals = list(var.lb) + list(var.ub)

    ranges = [
        ("Matrix coefficients", *_range_of(matrix_vals)),
        ("Objective coefficients", *_range_of(obj)),
        ("Right-hand sides", *_range_of(rhs_vals, drop_inf=True)),
        ("Finite bounds", *_range_of(bnd_vals, drop_inf=True)),
    ]
    notes = [
        "Magnitudes of non-zero entries. Infinite bounds and RHS sentinels are excluded "
        "so the ratio reflects the model rather than 1e+20.",
        "A wide ratio (say beyond 1e9) is a common source of numerical trouble, but it is "
        "a hint, not a diagnosis — Xpress scales internally.",
    ]
    return NumericsFacts(ranges, notes)
