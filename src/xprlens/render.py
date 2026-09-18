"""Assemble the facts into one self-contained HTML page."""

from __future__ import annotations

import html
from typing import Any

import plotly.graph_objects as go
from plotly.io import to_html

from .classify import CAVEATS as CLASS_CAVEATS
from .facts import (
    COLTYPE_NAMES,
    ROWTYPE_NAMES,
    Classification,
    EffortFacts,
    MatrixFacts,
    ModelShape,
    NumericsFacts,
    ObjectiveFacts,
    Status,
    VariableFacts,
)
from .slice2d import Slice2D

_PALETTE = {
    "ink": "#12203a",
    "muted": "#5b6b86",
    "line": "#dde4ee",
    "accent": "#2f6fd0",
    "warn": "#9a5b00",
    "bad": "#b4231c",
    "good": "#16794a",
}


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _fig_html(fig: go.Figure, first: bool) -> str:
    fig.update_layout(
        margin=dict(l=60, r=24, t=34, b=48),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#fbfcfe",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12),
        height=380,
    )
    return to_html(
        fig,
        include_plotlyjs=bool(first),
        full_html=False,
        config={"displaylogo": False, "displayModeBar": False},
    )


def _kv_table(pairs: list[tuple[str, Any]]) -> str:
    rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in pairs if v is not None
    )
    return f"<table class='kv'>{rows}</table>"


def _count_table(counts: dict[str, Any], head: tuple[str, str]) -> str:
    rows = "".join(
        f"<tr><td>{_esc(k)}</td><td class='num'>{_esc(v)}</td></tr>" for k, v in counts.items()
    )
    return (
        f"<table class='counts'><thead><tr><th>{_esc(head[0])}</th>"
        f"<th class='num'>{_esc(head[1])}</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _notes(items: list[str], kind: str = "note") -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(t)}</li>" for t in items)
    return f"<ul class='{kind}'>{lis}</ul>"


def _section(title: str, body: str, *, anchor: str) -> str:
    return f"<section id='{anchor}'><h2>{_esc(title)}</h2>{body}</section>"


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------


def _bar(counts: dict[str, int], title: str, color: str) -> go.Figure:
    keys = list(counts)
    fig = go.Figure(
        go.Bar(x=[counts[k] for k in keys], y=keys, orientation="h", marker_color=color)
    )
    fig.update_layout(title=title, xaxis_title="count", yaxis=dict(autorange="reversed"))
    return fig


def _sparsity_fig(
    mat: MatrixFacts, variables: VariableFacts, cap: int
) -> tuple[go.Figure, str | None]:
    xs: list[int] = []
    ys: list[int] = []
    details: list[tuple[str, str, str, str, float]] = []
    for row in mat.rows:
        for c, coef in zip(row.cols, row.coefs, strict=False):
            xs.append(c)
            ys.append(row.index)
            details.append(
                (
                    variables.names[c],
                    COLTYPE_NAMES.get(variables.coltype[c], variables.coltype[c]),
                    row.name,
                    ROWTYPE_NAMES.get(row.kind, row.kind),
                    coef,
                )
            )
    note = None
    if len(xs) > cap:
        step = len(xs) // cap + 1
        xs, ys, details = xs[::step], ys[::step], details[::step]
        note = (
            f"Showing every {step}th non-zero ({len(xs):,} of {mat.nnz:,} points). The pattern "
            "is indicative; gaps here are sampling, not structure."
        )
    fig = go.Figure(
        go.Scattergl(
            x=xs,
            y=ys,
            customdata=details,
            mode="markers",
            marker=dict(size=3, color=_PALETTE["accent"], opacity=0.6),
            hovertemplate=(
                "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                "constraint: %{customdata[2]} (%{customdata[3]})<br>"
                "coefficient: %{customdata[4]:.6g}<br>"
                "column %{x}, row %{y}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title="Non-zero pattern of the constraint matrix",
        xaxis_title=f"column (0 … {max(variables.n - 1, 0)})",
        yaxis_title=f"row (0 … {max(len(mat.rows) - 1, 0)})",
        yaxis=dict(autorange="reversed"),
        height=460,
    )
    return fig, note


def _slice_fig(sl: Slice2D) -> go.Figure:
    fig = go.Figure()
    u_lo, u_hi, v_lo, v_hi = sl.window

    for hp in sl.halfplanes:
        if abs(hp.a) < 1e-12 and abs(hp.b) < 1e-12:
            continue
        pts = []
        if abs(hp.b) > 1e-12:
            for u in (u_lo, u_hi):
                pts.append((u, (hp.c - hp.a * u) / hp.b))
        else:
            u = hp.c / hp.a
            pts = [(u, v_lo), (u, v_hi)]
        fig.add_trace(
            go.Scatter(
                x=[p[0] for p in pts],
                y=[p[1] for p in pts],
                mode="lines",
                line=dict(color=_PALETTE["muted"], width=1, dash="dot"),
                name=hp.label,
                hoverinfo="name",
                showlegend=False,
            )
        )

    if sl.polygon:
        poly = [*sl.polygon, sl.polygon[0]]
        fig.add_trace(
            go.Scatter(
                x=[p[0] for p in poly],
                y=[p[1] for p in poly],
                fill="toself",
                fillcolor="rgba(47,111,208,0.12)",
                line=dict(color=_PALETTE["accent"], width=1.6),
                name="LP relaxation, sliced",
                hovertemplate="%{x:.4g}, %{y:.4g}<extra></extra>",
            )
        )
    if sl.lattice:
        fig.add_trace(
            go.Scatter(
                x=[p[0] for p in sl.lattice],
                y=[p[1] for p in sl.lattice],
                mode="markers",
                marker=dict(size=7, color=_PALETTE["good"], symbol="circle"),
                name="integer-feasible in this slice",
                hovertemplate="%{x:g}, %{y:g}<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=[sl.x_ref[sl.px]],
            y=[sl.x_ref[sl.qx]],
            mode="markers",
            marker=dict(size=11, color=_PALETTE["bad"], symbol="x"),
            name=f"reference point ({sl.ref_origin})",
        )
    )
    fig.update_layout(
        title=f"Slice through {sl.px_name} and {sl.qx_name}",
        xaxis_title=sl.px_name,
        yaxis_title=sl.qx_name,
        xaxis=dict(range=[u_lo, u_hi]),
        yaxis=dict(range=[v_lo, v_hi]),
        height=520,
        legend=dict(orientation="h", y=-0.18),
    )
    return fig


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

_CSS = """
:root{--ink:#12203a;--muted:#5b6b86;--line:#dde4ee;--accent:#2f6fd0;--warn:#9a5b00;--bad:#b4231c}
*{box-sizing:border-box}
body{margin:0;background:#eef2f8;color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.5}
header{background:#fff;border-bottom:1px solid var(--line);padding:1.1rem 1.6rem}
header h1{margin:0;font-size:1.35rem;letter-spacing:-.01em}
header .sub{margin:.2rem 0 0;color:var(--muted);font-size:.85rem}
main{max-width:1180px;margin:0 auto;padding:1.2rem 1.2rem 4rem;display:grid;gap:1.1rem}
section{background:#fff;border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.3rem}
section h2{margin:0 0 .8rem;font-size:.82rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.headline{font-size:1.15rem;font-weight:650;margin:0 0 .5rem}
table{border-collapse:collapse;width:100%;margin:.2rem 0 .6rem}
.kv th{text-align:left;font-weight:600;color:var(--muted);padding:.3rem .8rem .3rem 0;
  white-space:nowrap;vertical-align:top;width:1%}
.kv td{padding:.3rem 0;font-variant-numeric:tabular-nums}
.counts th{text-align:left;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);border-bottom:1px solid var(--line);padding:.3rem 0}
.counts td{padding:.28rem 0;border-bottom:1px solid #f1f4f9}
.num{text-align:right;font-variant-numeric:tabular-nums}
ul.note,ul.warn{margin:.5rem 0 0;padding-left:1.1rem;font-size:.85rem;color:var(--muted)}
ul.warn{color:var(--warn)}
ul.note li,ul.warn li{margin:.25rem 0}
.banner{border-radius:10px;padding:.8rem 1rem;margin:0 0 1rem;font-size:.9rem}
.banner-warn{background:#fff6e6;border:1px solid #f0d49a;color:var(--warn)}
.banner-bad{background:#fdecea;border:1px solid #f3bdb8;color:var(--bad)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem}
@media(max-width:820px){.grid2{grid-template-columns:1fr}}
.pill{display:inline-block;background:#eaf1fc;color:var(--accent);border-radius:999px;
  padding:.1rem .6rem;font-size:.8rem;font-weight:600;margin-right:.3rem}
footer{max-width:1180px;margin:0 auto;padding:0 1.2rem 3rem;color:var(--muted);font-size:.78rem}
code{background:#f3f6fb;border-radius:4px;padding:.05rem .3rem;font-size:.86em}
"""


def build_page(
    *,
    title: str,
    lib_version: str,
    pkg_version: str,
    status: Status,
    shape: ModelShape,
    cls: Classification,
    variables: VariableFacts | None,
    matrix: MatrixFacts | None,
    shapes: dict[str, int] | None,
    objective: ObjectiveFacts,
    effort: EffortFacts,
    numerics: NumericsFacts | None,
    slice_: Slice2D | None,
    sections: list[str],
    sparsity_cap: int,
) -> str:
    parts: list[str] = []
    first_fig = True

    banner = ""
    if shape.presolved:
        banner = f"<div class='banner banner-bad'><strong>Presolved problem.</strong> {_esc(shape.note)}</div>"
    elif not status.started:
        banner = (
            "<div class='banner banner-warn'><strong>Not solved.</strong> "
            "Everything below describes the model as built. No result figures are shown, "
            "because Xpress would return sentinel values rather than raise.</div>"
        )

    if "status" in sections:
        body = f"<p class='headline'>{_esc(status.headline)}</p>"
        body += _kv_table(
            [
                ("solvestatus", status.solve),
                ("solstatus", status.sol),
                ("stopstatus", status.stop),
                ("lpstatus", status.lp),
                ("mipstatus", status.mip),
                ("proven optimal", "yes" if status.proven_optimal else "no"),
            ]
        )
        body += _notes(status.caveats, "warn")
        body += _notes(
            [
                "Freshness is decided by solvestatus alone. On a never-solved MIP, mipstatus "
                "reads LP_NOT_OPTIMAL and getProbStatusString() reads 'mip_lp_not_optimal', "
                "which sound like findings but mean nothing has run.",
            ]
        )
        parts.append(_section("Status", body, anchor="status"))

    if "classification" in sections:
        feats = {k: v for k, v in cls.features.items() if v}
        body = f"<p class='headline'><span class='pill'>{_esc(cls.label)}</span></p>"
        body += _count_table(feats or {"(no special structures)": 0}, ("feature", "count"))
        parts.append(_section("Problem type", body, anchor="type"))

    if "variables" in sections and variables is not None:
        declared = {COLTYPE_NAMES[k]: v for k, v in variables.declared.items() if v}
        split = {
            "declared binary (type B)": variables.binary_declared,
            "integer, bounds within [0,1]": variables.integer_unit_range,
            "integer, wider range": variables.integer_general,
        }
        fig = _bar(variables.bounds, "Variables by bound status", _PALETTE["accent"])
        body = (
            "<div class='grid2'><div>"
            + _count_table(declared, ("declared type", "count"))
            + _count_table(split, ("discrete detail", "count"))
            + "</div><div>"
            + _fig_html(fig, first_fig)
            + "</div></div>"
        )
        first_fig = False
        body += _notes(variables.notes)
        parts.append(_section(f"Variables ({variables.n:,})", body, anchor="vars"))

    if "constraints" in sections and matrix is not None:
        rt = {ROWTYPE_NAMES.get(k, k): v for k, v in matrix.rowtypes.items()}
        body = "<div class='grid2'><div>" + _count_table(rt, ("row type", "count"))
        body += _kv_table(
            [
                ("non-zeros", f"{matrix.nnz:,}"),
                ("density", f"{matrix.density:.4%}"),
            ]
        )
        body += "</div><div>"
        if shapes:
            body += _count_table(shapes, ("constraint shape", "count"))
        body += "</div></div>"
        body += _notes(CLASS_CAVEATS)
        parts.append(_section(f"Constraints ({len(matrix.rows):,})", body, anchor="cons"))

    if "objective" in sections:
        pairs: list[tuple[str, Any]] = [("sense", objective.sense)]
        pairs.append(
            (
                "objective value",
                f"{objective.value:.10g}" if objective.value is not None else "not available",
            )
        )
        pairs.append(
            (
                "best bound",
                f"{objective.bound:.10g}" if objective.bound is not None else "not available",
            )
        )
        if objective.gap_applies:
            pairs.append(("absolute gap", f"{objective.abs_gap:.10g}"))
            pairs.append(("relative gap", f"{objective.rel_gap:.6%}"))
            pairs.append(("gap formula", objective.gap_formula))
        for k, v in objective.tolerances.items():
            pairs.append((f"control {k}", f"{v:g}"))
        body = _kv_table(pairs) + _notes(objective.notes)
        parts.append(_section("Objective", body, anchor="obj"))

    if "effort" in sections:
        body = ""
        if effort.entries:
            rows = "".join(
                f"<tr><td>{_esc(n)}</td><td class='num'>{v:,}</td><td style='color:#5b6b86;font-size:.84rem'>{_esc(d)}</td></tr>"
                if isinstance(v, int)
                else f"<tr><td>{_esc(n)}</td><td class='num'>{_esc(v)}</td><td style='color:#5b6b86;font-size:.84rem'>{_esc(d)}</td></tr>"
                for n, v, d in effort.entries
            )
            body += f"<table class='counts'><thead><tr><th>measure</th><th class='num'>value</th><th>meaning</th></tr></thead><tbody>{rows}</tbody></table>"
        body += _notes(effort.notes)
        parts.append(_section("Solver effort", body, anchor="effort"))

    if "numerics" in sections and numerics is not None:
        rows = "".join(
            "<tr><td>{}</td><td class='num'>{}</td><td class='num'>{}</td><td class='num'>{}</td></tr>".format(
                _esc(n),
                f"{lo:.3g}" if lo is not None else "—",
                f"{hi:.3g}" if hi is not None else "—",
                f"{r:.3g}" if r is not None else "—",
            )
            for n, lo, hi, r in numerics.ranges
        )
        body = (
            "<table class='counts'><thead><tr><th>quantity</th><th class='num'>min |v|</th>"
            f"<th class='num'>max |v|</th><th class='num'>ratio</th></tr></thead><tbody>{rows}</tbody></table>"
        )
        body += _notes(numerics.notes)
        parts.append(_section("Numerics", body, anchor="num"))

    if "sparsity" in sections and matrix is not None and matrix.nnz and variables is not None:
        fig, note = _sparsity_fig(matrix, variables, sparsity_cap)
        body = _fig_html(fig, first_fig)
        first_fig = False
        body += _notes([note] if note else [])
        parts.append(_section("Sparsity", body, anchor="spy"))

    if "slice" in sections and slice_ is not None:
        body = ""
        if slice_.empty_reason:
            body += f"<div class='banner banner-warn'>{_esc(slice_.empty_reason)}</div>"
        body += _fig_html(_slice_fig(slice_), first_fig)
        first_fig = False
        body += _notes(slice_.notes)
        if slice_.lattice_kind == "segments":
            body += _notes(
                [
                    "One slice variable is discrete and the other continuous, so the "
                    "integer-feasible part of this slice is a set of line segments, not the "
                    "shaded area. Only the LP relaxation is shaded."
                ],
                "warn",
            )
        parts.append(_section("2D slice", body, anchor="slice"))

    head = (
        f"<header><h1>{_esc(title)}</h1><p class='sub'>xprlens {_esc(pkg_version)} · "
        f"Xpress library {_esc(lib_version)} · {_esc(cls.label)} · "
        f"{shape.input_rows:,} rows × {shape.input_cols:,} columns as built</p></header>"
    )
    foot = (
        "<footer>xprlens is not affiliated with, endorsed by, or supported by FICO. "
        "&ldquo;FICO&rdquo; and &ldquo;Xpress&rdquo; are trademarks of Fair Isaac Corporation.</footer>"
    )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{_esc(title)}</title>"
        f"<style>{_CSS}</style></head><body>{head}<main>{banner}{''.join(parts)}</main>{foot}</body></html>"
    )
