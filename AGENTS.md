# Agent instructions for xprlens

## Workflow

- When a task is finished, commit and push straight to `main`. Don't leave
  finished work uncommitted or sitting on a branch waiting for review.
- Keep this file (`AGENTS.md`) updated and useful as the project evolves —
  update it whenever conventions, structure, or decisions change, without
  asking for permission first.

## Project overview

A Python package that takes a live `xpress.problem` and writes one
self-contained HTML page describing it.

- `src/xprlens/report.py` — the public `report()` entry point and section wiring.
- `src/xprlens/facts.py` — reads the problem. **Every trap below lives here.**
- `src/xprlens/classify.py` — MIPLIB-style constraint shape classification.
- `src/xprlens/slice2d.py` — 2D slice geometry (half-plane clipping).
- `src/xprlens/render.py` — HTML and Plotly assembly.
- `src/xprlens/_xp.py` — lazy `xpress` import and the two sentinel tests.

Tooling: `uv`, `hatchling` + `hatch-vcs` (version comes from git tags, so a
checkout without `.git` cannot build), `ruff` via pre-commit, pytest.

### Two absolute rules

1. **Never mutate the caller's problem.** No setting controls, no changing
   bounds, no triggering a solve. `test_report_does_not_modify_the_problem`
   guards this; keep it passing.
2. **Never display a number the problem cannot support.** Xpress returns
   sentinels rather than raising, so silence is the correct output far more
   often than it looks. When in doubt, omit the figure and say why.

---

## What the numbers mean, and how they mislead

Every item below was reproduced against a live Xpress (library 45.01.01, via
`xpress==9.6.0`). These are not hypotheticals. If you change `facts.py`,
re-run these snippets first.

### Trap A — `getObjVal()` returns garbage on an unsolved problem, silently

```python
p = xp.problem()
x = p.addVariable(lb=0, ub=10)
p.addConstraint(x <= 8)
p.setObjective(x, sense=xp.maximize)
p.getObjVal()  # -> 0.0     for an LP.  No exception.
# same on a MIP    -> 1e+40
# infeasible MIP   -> 1e+40
```

`objval` and `lpobjval` behave the same way. Gate every result figure on
`Status.started` / `Status.has_solution` before showing it.

### Trap B — only `solvestatus` can tell you whether anything ran

```python
p = xp.problem()
p.addVariable(vartype=xp.binary)
p.attributes.mipstatus  # -> MIPStatus.LP_NOT_OPTIMAL   (not NOT_LOADED)
p.getProbStatusString()  # -> 'mip_lp_not_optimal'
p.attributes.solvestatus  # -> SolveStatus.UNSTARTED      <- the truth
```

`mipstatus` and the status string read like findings about the relaxation
while nothing has run. Use `solvestatus` for freshness and `solstatus` for
what kind of solution exists. `read_status` does this; don't "simplify" it.

### Trap C — `SolStatus.OPTIMAL` does not mean proven optimal

```python
p.controls.miprelstop = 0.35
p.optimize()
p.attributes.solstatus  # -> OPTIMAL
p.attributes.mipstatus  # -> OPTIMAL
p.attributes.mipobjval  # -> 813.0
p.attributes.bestbound  # -> 818.0      <- a real gap of 5
p.attributes.stopstatus  # -> 5  == StopType.MIPGAP
```

Xpress reports OPTIMAL for a solution that merely met the stopping tolerance.
Honest status is the **triple** `(solvestatus, solstatus, stopstatus)`, shown
with the gap and with `miprelstop` / `mipabsstop` / `timelimit`.

### Trap D — there is no gap attribute, and the formula is specific

Searching all 285 attributes for "gap" finds only `barcgap`, which is the
*barrier complementarity gap* and unrelated. The gap must be computed, and it
must match the rule Xpress itself stops on:

```
|MIPOBJVAL - BESTBOUND|  <=  MIPRELSTOP * max(|BESTBOUND|, |MIPOBJVAL|)
```

Denominator is `max(|bound|, |incumbent|)` — **not** `/|bound|` and **not**
Gurobi's `/|incumbent|`. On one measured solve the three conventions gave
0.00611247 / 0.00615006 / 0.00611247. Using another convention prints a gap
that disagrees with the solver's own stopping decision.

**Do not compute a gap without an incumbent.** A timed-out run gives:

```
mipobjval = -1e+40,  bestbound = 158842.15
naive rel gap -> exactly 1.0, i.e. a fabricated "100%"
```

### Trap E — there are two different infinity sentinels

| meaning | value | test |
| --- | --- | --- |
| infinite **bound** | `xpress.infinity` == `1e+20` | `abs(v) >= 1e20` (docs say *greater than or equal*) |
| **no incumbent** | `1e+40`, sign follows objective sense | `abs(v) >= 1e30` |

`1e40 == xpress.infinity` is `False`. A bounds-style equality test silently
fails to catch the no-incumbent marker. `_xp.is_inf` and `_xp.is_unset` exist
so this is decided in one place.

### Trap F — presolve destroys the counts, and `originalrows` does not save you

```python
# 4 rows, 9 cols, 8 binaries
p.presolve()
p.attributes.rows, p.attributes.cols, p.attributes.mipents  # -> 0, 1, 0
p.attributes.originalrows, p.attributes.originalcols  # -> 0, 1   (!)
p.attributes.inputrows, p.attributes.inputcols  # -> 4, 9   <- survives
p.postsolve()  # does NOT restore
```

`originalrows`/`originalcols`/`originalmipents` mean "original at this level"
and follow the presolve down. A naive tool reports *"an empty LP with one
continuous variable"* for a 9-variable MIP. There is **no** `inputmipents`, so
after presolve no safe entity count exists at all — which is why `report()`
withholds the structural sections entirely rather than guessing.

Detection is `rows != inputrows or cols != inputcols`. Do **not** use
`presolvestate`: its documented bits 1 and 2 (LP/MIP presolved) did not set in
testing, and the bits that did (5, 6, 18–22) are undocumented. Bit 7
("solution in memory is valid") does behave as documented.

On some unsolved model-building paths the aggregate shape attributes can still
read zero while `getVariable()` / `getConstraint()` expose the model entities.
When the problem is not presolved, use those object accessors for the report's
row and column counts, and derive MIP entities from `getColType()` rather than
trusting `mipents` alone.

In the ordinary `p.optimize()` flow the counts come back correct; the trap
only bites on an explicitly presolved problem.

### Trap G — "iterations" is at least two different numbers

Time-limited 42-binary market-split model:

```
nodes       =   391,541      # branch-and-bound nodes
simplexiter = 1,167,684      # simplex iterations across all node LPs
                             # -> ~3 iterations per node
```

And on easy models `nodes == 0` while `simplexiter == 5`, because the search
finished at the root. Report these as **separately named** quantities.
`test_effort_separates_nodes_from_simplex_iterations` asserts no field is
called plain "iterations".

### Trap H — LP and MIP fields are not interchangeable

- `bestbound` is populated for a **pure LP** (it equals the LP objective).
  Showing a "gap" there invents a MIP concept. Gate on `Classification.discrete`.
- `mipobjval` on a solved LP reads `-1e+40`.
- There are **six** column types, not three: `C`, `I`, `B`, `S` (semi-continuous),
  `R` (semi-continuous integer), `P` (partial integer).
- Range rows are type `R`, with the interval `[rhs - |rhsrange|, rhs]`.

### Trap I — solving rewrites column types

```python
a = p.addVariable(vartype=xp.integer, lb=0, ub=1)
p.getcoltype(...)  # before optimize -> 'I'
p.optimize()
p.getcoltype(...)  # after  optimize -> 'B'
```

Xpress folds integer variables bounded to `[0,1]` into binaries during the
solve. The "declared binary vs integer restricted to {0,1}" split therefore
means different things before and after a solve, and the post-solve figure
cannot be un-mixed. `read_variables(solved=True)` adds a note saying so.

### Not a trap in Xpress, but worth knowing

`p.addConstraint(3 <= expr <= 7)` silently keeps only `expr <= 7`. That is
Python chained comparison, not Xpress. Once the row is built the lower bound
is gone and xprlens cannot detect that it was ever intended.

---

## Deliberate limitations, stated on the page

- **Constraint classification is MIPLIB-*style*, not MIPLIB.** Binary negation
  is not attempted when matching, so counts skew towards the general classes;
  and MIPLIB's `binpacking` is folded into `knapsack`. Both differences are
  printed under the table so nobody reads it as a reproduction.
- **Implicit integers are not detected.** A continuous variable may be forced
  integral once the integer variables are fixed; "continuous" counts
  declarations only.
- **The 2D slice is a slice, not a projection.** See the module docstring in
  `slice2d.py`. For a discrete problem the shaded polygon is the LP relaxation
  restricted to the slice; the integer-feasible set is drawn separately because
  it is a different object. Nothing in the codebase may call the shaded region
  "the feasible region".
- **Quadratic constraints are not sliced.** A quadratic row is not a half-plane
  and clipping would silently produce the wrong shape.

## Testing

`tests/conftest.py` provides an `xp` fixture that **skips** when the `xpress`
package is missing or its licence will not initialise. This is deliberate: FICO
ships a community licence with a hard expiry date inside the wheel (the one
bundled with 9.6.0 expired 30 April 2026), so a green CI run must not depend on
that licence still being valid on the day it runs. Point `XPRESS_LICENCE` at a
valid `.xpr` file to exercise the solver-backed tests.

Roughly half the suite is solver-free by design — sentinel arithmetic, the
constraint classifier and the slice geometry all run on hand-built inputs, so
CI keeps real coverage even when no licence is available.

## Versions, accessor renames, and the CI guard

Xpress 9.8 renamed every problem accessor xprlens uses, from the C-style
`getlb(out_list, first, last)` to `getLB(first, last) -> list`; 9.9 renamed
`xpress.getversion` to `xpress.getVersion`; and `var.index` replaces
`problem.getIndex`. The old spellings still work and emit
`DeprecationWarning`, so they are on their way out.

`_compat.py` supports both: each helper tries the modern call and falls back
to the legacy one. Note that on 9.8+ some of the new names **also accept the
legacy signature** and merely warn — `getRows` does — so a `TypeError`-based
fallback is not enough on its own; try the returning form first.

**The guard that this is working is a CI step, not a pytest setting.** A
`filterwarnings = ["error:Deprecated in Xpress:..."]` entry in pyproject was
tried and did *not* error on these warnings; CI passed with eight of them in
the log. It looked like a guard and was not. The working version greps the
pytest output for `Deprecated in Xpress` lines originating in `src/xprlens/`
and fails the job. It is scoped to package source deliberately: a test may call
a deprecated API on purpose, as the presolve test does.

## Platform note

The macOS wheels for `xpress` 9.9.x are arm64 only, and `xpresslibs` from 9.6.1
onward tags its Intel-mac wheel `macosx_14_0`. Development on an Intel Mac
below macOS 14 is therefore pinned to `xpress==9.6.0`, which has only the
legacy accessor names — so local runs exercise the fallback path and CI
exercises the modern one. Between them both branches of `_compat.py` are
covered.

CI installs the newest `xpress` (9.9.1 at the time of writing) on Linux, and
the full suite passes there with the solver actually running: the community
licence bundled with 9.9.1 is currently valid. That is not something to rely
on — it has an expiry date — which is why the skip path exists.

## Conventions

- `uv` for environments, `ruff` for lint and format, pre-commit to run both.
- Publishing is by git tag via GitHub Actions using **PyPI trusted publishing
  (OIDC)**. There is no API token and no repository secret; do not add one.
- Not affiliated with FICO. Keep that line in the README, the package metadata
  and the report footer.
