"""Interactive, self-contained explorer for two-dimensional model slices."""

from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path
from typing import Any

from plotly.offline import get_plotlyjs

from ._xp import is_inf, xpress
from .facts import MatrixFacts, VariableFacts, read_matrix, read_shape, read_status, read_variables
from .report import _reference_point, _resolve_pair
from .slice2d import pick_pair


def _model_data(
    matrix: MatrixFacts,
    variables: VariableFacts,
    reference: list[float],
    reference_origin: str,
    pair: tuple[int, int],
) -> dict[str, Any]:
    rows = []
    for row in matrix.rows:
        lo, hi = row.interval()
        rows.append(
            {
                "name": row.name,
                "lo": None if lo == float("-inf") else lo,
                "hi": None if hi == float("inf") else hi,
                "cols": row.cols,
                "coefs": row.coefs,
            }
        )
    return {
        "names": variables.names,
        "types": variables.coltype,
        "lb": [None if is_inf(value) else value for value in variables.lb],
        "ub": [None if is_inf(value) else value for value in variables.ub],
        "reference": reference,
        "referenceOrigin": reference_origin,
        "rows": rows,
        "initialPair": pair,
    }


_CSS = """
:root{--ink:#12203a;--muted:#5b6b86;--line:#d8e0eb;--accent:#2f6fd0;--warn:#8a5300;
  --bad:#b4231c;--good:#16794a;--panel:#fff}
*{box-sizing:border-box}
body{margin:0;background:#eef2f8;color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.5}
header{background:#fff;border-bottom:1px solid var(--line);padding:1.1rem 1.6rem}
h1{margin:0;font-size:1.35rem;letter-spacing:0}
.sub{margin:.2rem 0 0;color:var(--muted);font-size:.85rem}
main{max-width:1180px;margin:0 auto;padding:1.2rem 1.2rem 3rem}
.toolbar{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;gap:1rem;
  align-items:end;background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:1rem 1.2rem;margin-bottom:1rem}
label{display:grid;gap:.35rem;color:var(--muted);font-size:.78rem;font-weight:650;
  text-transform:uppercase;letter-spacing:.05em}
select{width:100%;min-width:0;border:1px solid #aebbd0;border-radius:6px;background:#fff;
  color:var(--ink);font:inherit;padding:.55rem .7rem}
.pair-meta{min-width:8rem;color:var(--muted);font-size:.85rem;padding-bottom:.55rem;text-align:right}
.plot-panel{min-width:0;overflow:hidden;background:var(--panel);border:1px solid var(--line);
  border-radius:8px;padding:.35rem}
#slice-plot{width:100%;max-width:100%;height:min(68vh,680px);min-height:460px}
.banner{border-radius:6px;padding:.75rem 1rem;margin:1rem 0 0;font-size:.9rem}
.banner[hidden]{display:none}
.warn{background:#fff6e6;border:1px solid #f0d49a;color:var(--warn)}
.notes{margin:1rem 0 0;padding-left:1.2rem;color:var(--muted);font-size:.86rem}
.notes li{margin:.25rem 0}
footer{max-width:1180px;margin:0 auto;padding:0 1.2rem 2.5rem;color:var(--muted);font-size:.78rem}
@media(max-width:700px){.toolbar{grid-template-columns:1fr}.pair-meta{text-align:left;padding:0}
  #slice-plot{height:62vh;min-height:390px}}
"""


_SCRIPT = r"""
const model = __MODEL__;
const plot = document.getElementById('slice-plot');
const xSelect = document.getElementById('x-variable');
const ySelect = document.getElementById('y-variable');
const banner = document.getElementById('slice-warning');
const notes = document.getElementById('slice-notes');
const pairMeta = document.getElementById('pair-meta');
const EPS = 1e-9;
const FALLBACK_SPAN = 10;

function formatNumber(value) {
  return Number(value.toPrecision(6)).toString();
}

function finiteWindow(lo, hi, reference) {
  if (lo === null && hi === null) return [reference - FALLBACK_SPAN, reference + FALLBACK_SPAN, true];
  if (lo === null) return [hi - FALLBACK_SPAN, hi, true];
  if (hi === null) return [lo, lo + FALLBACK_SPAN, true];
  if (hi - lo <= 0) return [lo - 0.5, hi + 0.5, false];
  return [lo, hi, false];
}

function clipPolygon(polygon, halfplane) {
  if (!polygon.length) return polygon;
  const output = [];
  const inside = point => halfplane.a * point[0] + halfplane.b * point[1] <= halfplane.c + EPS;
  for (let index = 0; index < polygon.length; index += 1) {
    const current = polygon[index];
    const previous = polygon[(index + polygon.length - 1) % polygon.length];
    const currentInside = inside(current);
    const previousInside = inside(previous);
    if (currentInside !== previousInside) {
      const dx = current[0] - previous[0];
      const dy = current[1] - previous[1];
      const denominator = halfplane.a * dx + halfplane.b * dy;
      if (Math.abs(denominator) > 1e-15) {
        const amount = (halfplane.c - halfplane.a * previous[0] - halfplane.b * previous[1]) / denominator;
        output.push([previous[0] + amount * dx, previous[1] + amount * dy]);
      }
    }
    if (currentInside) output.push(current);
  }
  return output;
}

function calculateSlice(px, qx) {
  const xWindow = finiteWindow(model.lb[px], model.ub[px], model.reference[px]);
  const yWindow = finiteWindow(model.lb[qx], model.ub[qx], model.reference[qx]);
  const halfplanes = [];
  const constantViolations = [];

  for (const row of model.rows) {
    let a = 0;
    let b = 0;
    let fixed = 0;
    let involvesPair = false;
    for (let index = 0; index < row.cols.length; index += 1) {
      const column = row.cols[index];
      const coefficient = row.coefs[index];
      if (column === px) {
        a += coefficient;
        involvesPair = true;
      } else if (column === qx) {
        b += coefficient;
        involvesPair = true;
      } else {
        fixed += coefficient * model.reference[column];
      }
    }
    const rowPlanes = [];
    if (row.hi !== null) {
      rowPlanes.push({a, b, c: row.hi - fixed, label: `${row.name} <= ${formatNumber(row.hi)}`});
    }
    if (row.lo !== null) {
      rowPlanes.push({a: -a, b: -b, c: -(row.lo - fixed), label: `${row.name} >= ${formatNumber(row.lo)}`});
    }
    if (involvesPair) {
      halfplanes.push(...rowPlanes);
    } else {
      for (const plane of rowPlanes) {
        if (plane.c < -1e-7) constantViolations.push(plane.label);
      }
    }
  }

  let polygon = [
    [xWindow[0], yWindow[0]], [xWindow[1], yWindow[0]],
    [xWindow[1], yWindow[1]], [xWindow[0], yWindow[1]],
  ];
  for (const plane of halfplanes) {
    polygon = clipPolygon(polygon, plane);
    if (!polygon.length) break;
  }

  const xDiscrete = ['B', 'I'].includes(model.types[px]);
  const yDiscrete = ['B', 'I'].includes(model.types[qx]);
  const fixedDiscreteIntegral = model.types.every((type, index) =>
    index === px || index === qx || !['B', 'I'].includes(type)
      || Math.abs(model.reference[index] - Math.round(model.reference[index])) <= 1e-6);
  const latticeKind = xDiscrete && yDiscrete ? 'points' : (xDiscrete || yDiscrete ? 'segments' : 'none');
  const lattice = [];
  let latticeCapped = false;
  if (polygon.length && latticeKind === 'points' && fixedDiscreteIntegral) {
    const xs = polygon.map(point => point[0]);
    const ys = polygon.map(point => point[1]);
    const x0 = Math.ceil(Math.min(...xs) - EPS);
    const x1 = Math.floor(Math.max(...xs) + EPS);
    const y0 = Math.ceil(Math.min(...ys) - EPS);
    const y1 = Math.floor(Math.max(...ys) + EPS);
    latticeCapped = (x1 - x0 + 1) * (y1 - y0 + 1) > 4000;
    if (!latticeCapped) {
      for (let x = x0; x <= x1; x += 1) {
        for (let y = y0; y <= y1; y += 1) {
          if (halfplanes.every(plane => plane.a * x + plane.b * y <= plane.c + 1e-7)) {
            lattice.push([x, y]);
          }
        }
      }
    }
  }
  return {xWindow, yWindow, halfplanes, constantViolations, polygon, lattice,
    latticeKind, fixedDiscreteIntegral, latticeCapped};
}

function tracesFor(slice, px, qx) {
  const traces = [];
  for (const plane of slice.halfplanes) {
    if (Math.abs(plane.a) < 1e-12 && Math.abs(plane.b) < 1e-12) continue;
    let points;
    if (Math.abs(plane.b) > 1e-12) {
      points = [slice.xWindow[0], slice.xWindow[1]].map(x => [x, (plane.c - plane.a * x) / plane.b]);
    } else {
      const x = plane.c / plane.a;
      points = [[x, slice.yWindow[0]], [x, slice.yWindow[1]]];
    }
    traces.push({type: 'scatter', mode: 'lines', x: points.map(point => point[0]),
      y: points.map(point => point[1]), line: {color: '#5b6b86', width: 1, dash: 'dot'},
      name: plane.label, hoverinfo: 'name', showlegend: false});
  }
  if (slice.polygon.length) {
    const closed = [...slice.polygon, slice.polygon[0]];
    traces.push({type: 'scatter', mode: 'lines', x: closed.map(point => point[0]),
      y: closed.map(point => point[1]), fill: 'toself', fillcolor: 'rgba(47,111,208,0.12)',
      line: {color: '#2f6fd0', width: 1.6}, name: 'LP relaxation, sliced',
      hovertemplate: '%{x:.4g}, %{y:.4g}<extra></extra>'});
  }
  if (slice.lattice.length) {
    traces.push({type: 'scatter', mode: 'markers', x: slice.lattice.map(point => point[0]),
      y: slice.lattice.map(point => point[1]), marker: {size: 7, color: '#16794a'},
      name: 'integer-feasible in this slice', hovertemplate: '%{x:g}, %{y:g}<extra></extra>'});
  }
  traces.push({type: 'scatter', mode: 'markers', x: [model.reference[px]], y: [model.reference[qx]],
    marker: {size: 11, color: '#b4231c', symbol: 'x'},
    name: `reference point (${model.referenceOrigin})`});
  return traces;
}

function render() {
  const px = Number(xSelect.value);
  const qx = Number(ySelect.value);
  const slice = calculateSlice(px, qx);
  const xName = model.names[px];
  const yName = model.names[qx];
  const layout = {
    title: {text: `Slice through ${xName} and ${yName}`, font: {size: 17}},
    xaxis: {title: xName, range: slice.xWindow.slice(0, 2), zerolinecolor: '#d8e0eb'},
    yaxis: {title: yName, range: slice.yWindow.slice(0, 2), zerolinecolor: '#d8e0eb'},
    margin: {l: 64, r: 28, t: 54, b: 76}, paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: '#fbfcfe', font: {family: 'system-ui, -apple-system, Segoe UI, sans-serif', size: 12},
    legend: {orientation: 'h', y: -0.18}, hovermode: 'closest',
  };
  Plotly.react(plot, tracesFor(slice, px, qx), layout,
    {responsive: true, displaylogo: false, scrollZoom: true});

  let warning = '';
  if (slice.constantViolations.length) {
    warning = `The slice is empty before either selected variable is considered: ${slice.constantViolations.length} constraint(s) not involving them are violated by the reference point (first: ${slice.constantViolations[0]}).`;
  } else if (!slice.polygon.length) {
    warning = 'No point in this slice satisfies every constraint.';
  } else if (slice.latticeKind === 'segments') {
    warning = 'One selected variable is discrete and the other continuous. The shaded area is only the sliced LP relaxation; the integer-feasible part consists of line segments.';
  }
  banner.textContent = warning;
  banner.hidden = !warning;

  const messages = [
    `Every variable other than ${xName} and ${yName} is held at ${model.referenceOrigin}.`,
    'This is a slice, not a projection: points feasible in the full model need not appear here.',
  ];
  if ((slice.xWindow[2] || slice.yWindow[2])) {
    messages.push('A selected variable is unbounded, so its displayed window is artificial.');
  }
  if (slice.latticeKind !== 'none' && !slice.fixedDiscreteIntegral) {
    messages.push('A fixed discrete variable is fractional at the reference point, so the integer-feasible overlay is suppressed.');
  }
  if (slice.latticeCapped) {
    messages.push('The integer lattice would exceed 4,000 points, so its overlay is suppressed.');
  }
  notes.replaceChildren(...messages.map(message => {
    const item = document.createElement('li');
    item.textContent = message;
    return item;
  }));
  pairMeta.textContent = `${slice.halfplanes.length} boundaries`;
}

model.names.forEach((name, index) => {
  const text = `${index}: ${name} (${model.types[index]})`;
  xSelect.add(new Option(text, index));
  ySelect.add(new Option(text, index));
});
xSelect.value = model.initialPair[0];
ySelect.value = model.initialPair[1];
let previousX = xSelect.value;
let previousY = ySelect.value;
function selectPair(changed) {
  if (xSelect.value === ySelect.value) {
    if (changed === 'x') ySelect.value = previousX;
    else xSelect.value = previousY;
  }
  previousX = xSelect.value;
  previousY = ySelect.value;
  render();
}
xSelect.addEventListener('change', () => selectPair('x'));
ySelect.addEventListener('change', () => selectPair('y'));
render();
"""


def _build_page(title: str, model: dict[str, Any]) -> str:
    model_json = json.dumps(model, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    script = _SCRIPT.replace("__MODEL__", model_json)
    safe_title = html.escape(title)
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{safe_title}</title><style>{_CSS}</style>"
        f"<script>{get_plotlyjs()}</script></head><body><header><h1>{safe_title}</h1>"
        "<p class='sub'>Choose two variables to redraw the slice. Pan, zoom, and hover "
        "directly in the Plotly chart.</p></header><main><div class='toolbar'>"
        "<label>X variable<select id='x-variable'></select></label>"
        "<label>Y variable<select id='y-variable'></select></label>"
        "<div id='pair-meta' class='pair-meta'></div></div>"
        "<div class='plot-panel'><div id='slice-plot'></div></div>"
        "<div id='slice-warning' class='banner warn' hidden></div>"
        "<ul id='slice-notes' class='notes'></ul></main>"
        "<footer>xprlens is not affiliated with, endorsed by, or supported by FICO. "
        "&ldquo;FICO&rdquo; and &ldquo;Xpress&rdquo; are trademarks of Fair Isaac Corporation.</footer>"
        f"<script>{script}</script></body></html>"
    )


def slice_explorer(
    prob: Any,
    *,
    path: str | Path | None = None,
    title: str | None = None,
    slice_vars: tuple[int, int] | tuple[str, str] | None = None,
    open_browser: bool = False,
) -> Path:
    """Write an interactive Plotly page for choosing and viewing 2D slices.

    The problem is read once and never modified. Variable changes happen entirely
    in the generated page, which remains self-contained and needs no Python server.
    """
    xp = xpress()
    if not isinstance(prob, xp.problem):
        raise TypeError(f"expected an xpress.problem, got {type(prob).__name__}")

    shape = read_shape(prob)
    if shape.presolved:
        raise ValueError(
            "cannot explore a presolved problem because its original matrix is unavailable"
        )
    status = read_status(prob)
    variables = read_variables(prob, solved=status.started)
    if variables.n < 2:
        raise ValueError("slice_explorer requires at least two variables")
    matrix = read_matrix(prob, rows=shape.rows, cols=shape.cols)
    pair = _resolve_pair(slice_vars, variables) or pick_pair(matrix, variables)
    assert pair is not None
    reference, reference_origin = _reference_point(prob, status, variables)

    name = str(prob.attributes.matrixname or "problem")
    if name == "noname":
        name = "problem"
    page_title = title or f"{name} - interactive 2D slice"
    page = _build_page(
        page_title,
        _model_data(matrix, variables, reference, reference_origin, pair),
    )
    out = Path(path) if path is not None else Path(f"{name}-xprlens-slice.html")
    out.write_text(page, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out
