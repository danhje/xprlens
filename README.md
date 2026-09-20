# xprlens

Plotly reports and interactive 2D slices for
[FICO Xpress](https://www.fico.com/en/products/fico-xpress-optimization) problems.

```sh
pip install xprlens
```

`xpress` itself is not installed for you — bring your own, licensed copy:

```sh
pip install "xprlens[xpress]"
```

## Usage

```python
import xpress as xp
import xprlens

p = xp.problem()
x = p.addVariable(name="x", vartype=xp.binary)
y = p.addVariable(name="y", lb=0, ub=10)
p.addConstraint(3 * x + y <= 8)
p.setObjective(5 * x + y, sense=xp.maximize)
p.optimize()

xprlens.report(p, path="report.html", open_browser=True)
```

That writes one self-contained HTML file: status, problem type, variable and
constraint breakdowns, objective and MIP gap, solver effort, coefficient
ranges, the sparsity pattern, and a 2D slice through the feasible set.

The problem is only read. `report()` sets no controls, changes no bounds and
never triggers a solve. A problem you have not optimized is reported as
unsolved rather than having numbers invented for it.

### Choosing sections

All sections are included by default. On a very large model, drop the ones that
walk the whole matrix:

```python
xprlens.report(p, sections=["status", "classification", "objective", "effort"])
```

`xprlens.ALL_SECTIONS` lists every name; `xprlens.MATRIX_SECTIONS` lists the
expensive ones (`constraints`, `numerics`, `sparsity`, `slice`).

### Interactive 2D slices

Use the separate slice explorer to choose either axis interactively:

```python
xprlens.slice_explorer(p, path="slice.html", open_browser=True)
```

This writes a self-contained HTML and SVG page with selectors for both axes and
a slider for every other variable. Fixed variables default to the solution
returned by Xpress, or to the midpoint of their bounds when no solution exists.
The page draws exact continuous, integer, semi-continuous and semi-integer domain
pieces, the sliced continuous relaxation, the best point in the slice and its
objective iso-line. All geometry is recomputed in the browser, so the page needs
no Python server and does not touch the Xpress problem again. Set the initial
pair by name or index with `slice_vars=("x", "y")`.

The one-page report still includes a static 2D slice. By default it is taken
through the two variables appearing in the most constraints, at the returned
solution if there is one. Choose its pair with:

```python
xprlens.report(p, slice_vars=("x", "y"))
```

A slice holds every other variable fixed. It is **not** a projection: a point
can be feasible in the full model and absent from the slice, and the slice can
be empty for a feasible problem. For a discrete problem the shaded polygon is
the LP relaxation restricted to the slice; integer-feasible points are drawn
separately, because they are a different set.

### Options

| argument | meaning |
| --- | --- |
| `sections` | subset of `ALL_SECTIONS`; `None` (default) means all |
| `path` | output file; defaults to `<problem name>-xprlens.html` |
| `title` | page heading; defaults to the problem's name |
| `slice_vars` | the two variables to slice through, as indices or names |
| `sparsity_cap` | non-zeros plotted before downsampling (default 60,000) |
| `open_browser` | open the file when written |

## Licence note

Xpress ships a size-limited community licence with a fixed expiry date. If
`report()` raises a licensing error, that is Xpress talking, not xprlens.

---

xprlens is not affiliated with, endorsed by, or supported by FICO. "FICO" and
"Xpress" are trademarks of Fair Isaac Corporation. This package reads problems
built with the separately licensed `xpress` package; it neither bundles nor
redistributes any part of it.
