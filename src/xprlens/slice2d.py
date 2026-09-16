"""Two-dimensional slices through the feasible set.

What this is, precisely: pick two variables (p, q), hold every other variable
at a reference point x-bar, and draw the set

    { (u, v) : A (x-bar with x_p = u, x_q = v) within its row bounds,
               lb_p <= u <= ub_p, lb_q <= v <= ub_q }

**This is a slice, not a projection.** It is not the shadow of the feasible
region on those two axes. A point can be feasible in the full space and absent
here, and the slice can be empty for a perfectly feasible problem. Nothing in
this module may describe its output as "the feasible region".

For a discrete problem the polygon is the **LP relaxation** restricted to the
slice. The integer-feasible set restricted to the same slice is a set of
isolated lattice points (both slice variables discrete) or segments (one of
them). They are different objects and are drawn differently.

Rows with no coefficient on either slice variable do not draw a line: under the
slice they are constants, either satisfied by x-bar or not. If any is violated,
the whole slice is empty -- which is reported in words rather than as a blank
chart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._xp import is_inf
from .facts import MatrixFacts, Row, VariableFacts

# A finite window is needed for unbounded slice variables. Edges produced by
# this clip are flagged so they are not drawn as if they were real constraints.
_FALLBACK_SPAN = 10.0


@dataclass
class SliceHalfplane:
    """a*u + b*v <= c, already reduced by the fixed variables."""

    a: float
    b: float
    c: float
    row: int
    label: str


@dataclass
class Slice2D:
    px: int
    qx: int
    px_name: str
    qx_name: str
    x_ref: list[float]
    ref_origin: str
    window: tuple[float, float, float, float]
    window_clipped: tuple[bool, bool, bool, bool]
    halfplanes: list[SliceHalfplane]
    polygon: list[tuple[float, float]]
    lattice: list[tuple[float, float]]
    lattice_kind: str
    constant_rows_violated: list[str]
    slider_vars: list[int]
    empty_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def _finite_window(lo: float, hi: float, ref: float) -> tuple[float, float, bool, bool]:
    lo_clip = is_inf(lo)
    hi_clip = is_inf(hi)
    if lo_clip and hi_clip:
        return (ref - _FALLBACK_SPAN, ref + _FALLBACK_SPAN, True, True)
    if lo_clip:
        return (hi - _FALLBACK_SPAN, hi, True, False)
    if hi_clip:
        return (lo, lo + _FALLBACK_SPAN, False, True)
    if hi - lo <= 0:
        return (lo - 0.5, hi + 0.5, False, False)
    return (lo, hi, False, False)


def _row_halfplanes(row: Row, px: int, qx: int, x_ref: list[float]) -> list[SliceHalfplane]:
    a = b = 0.0
    fixed = 0.0
    for c, v in zip(row.cols, row.coefs, strict=False):
        if c == px:
            a += v
        elif c == qx:
            b += v
        else:
            fixed += v * x_ref[c]
    lo, hi = row.interval()
    out: list[SliceHalfplane] = []
    if hi != float("inf"):
        out.append(SliceHalfplane(a, b, hi - fixed, row.index, f"{row.name} <= {hi:g}"))
    if lo != float("-inf"):
        out.append(SliceHalfplane(-a, -b, -(lo - fixed), row.index, f"{row.name} >= {lo:g}"))
    return out


def _clip(poly: list[tuple[float, float]], hp: SliceHalfplane) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a convex polygon by a*u + b*v <= c."""
    if not poly:
        return poly
    inside = lambda pt: hp.a * pt[0] + hp.b * pt[1] <= hp.c + 1e-9  # noqa: E731
    out: list[tuple[float, float]] = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        cur_in, prev_in = inside(cur), inside(prev)
        if cur_in != prev_in:
            dx, dy = cur[0] - prev[0], cur[1] - prev[1]
            denom = hp.a * dx + hp.b * dy
            if abs(denom) > 1e-15:
                t = (hp.c - hp.a * prev[0] - hp.b * prev[1]) / denom
                out.append((prev[0] + t * dx, prev[1] + t * dy))
        if cur_in:
            out.append(cur)
    return out


def build_slice(
    mat: MatrixFacts,
    var: VariableFacts,
    x_ref: list[float],
    ref_origin: str,
    px: int,
    qx: int,
    *,
    max_sliders: int = 12,
    max_lattice: int = 4000,
) -> Slice2D:
    u_lo, u_hi, u_lc, u_hc = _finite_window(var.lb[px], var.ub[px], x_ref[px])
    v_lo, v_hi, v_lc, v_hc = _finite_window(var.lb[qx], var.ub[qx], x_ref[qx])

    halfplanes: list[SliceHalfplane] = []
    constant_violated: list[str] = []
    touching_rows: list[Row] = []
    for row in mat.rows:
        involves = px in row.cols or qx in row.cols
        hps = _row_halfplanes(row, px, qx, x_ref)
        if involves:
            touching_rows.append(row)
            halfplanes.extend(hps)
        else:
            for hp in hps:
                if hp.c < -1e-7:  # 0 <= c with c < 0 -> unsatisfiable
                    constant_violated.append(hp.label)

    poly: list[tuple[float, float]] = [(u_lo, v_lo), (u_hi, v_lo), (u_hi, v_hi), (u_lo, v_hi)]
    for hp in halfplanes:
        poly = _clip(poly, hp)
        if not poly:
            break

    empty_reason = None
    if constant_violated:
        empty_reason = (
            "The slice is empty before any of the two chosen variables is considered: "
            f"{len(constant_violated)} constraint(s) not involving them are already violated "
            f"by the reference point (first: {constant_violated[0]})."
        )
    elif not poly:
        empty_reason = "No point in this slice satisfies every constraint."

    # lattice overlay -- only meaningful when the reference point is itself
    # integral on the discrete variables it holds fixed
    lattice: list[tuple[float, float]] = []
    p_disc = var.coltype[px] in {"B", "I"}
    q_disc = var.coltype[qx] in {"B", "I"}
    ref_integral = all(
        abs(x_ref[i] - round(x_ref[i])) <= 1e-6
        for i in range(var.n)
        if i not in (px, qx) and var.coltype[i] in {"B", "I"}
    )
    if p_disc and q_disc:
        lattice_kind = "points"
    elif p_disc or q_disc:
        lattice_kind = "segments"
    else:
        lattice_kind = "none"

    if poly and lattice_kind == "points" and ref_integral:
        xs = [pt[0] for pt in poly]
        ys = [pt[1] for pt in poly]
        import math

        u0, u1 = math.ceil(min(xs) - 1e-9), math.floor(max(xs) + 1e-9)
        v0, v1 = math.ceil(min(ys) - 1e-9), math.floor(max(ys) + 1e-9)
        if (u1 - u0 + 1) * (v1 - v0 + 1) <= max_lattice:
            for iu in range(u0, u1 + 1):
                for iv in range(v0, v1 + 1):
                    if all(hp.a * iu + hp.b * iv <= hp.c + 1e-7 for hp in halfplanes):
                        lattice.append((float(iu), float(iv)))

    # Only variables sharing a row with the pair can move a line. Everything
    # else can at most flip the slice between empty and non-empty.
    sharing: list[int] = []
    for row in touching_rows:
        for c in row.cols:
            if c not in (px, qx) and c not in sharing:
                sharing.append(c)
    sharing.sort()
    slider_vars = sharing[:max_sliders]

    notes: list[str] = [
        f"Slice through the reference point ({ref_origin}); every variable other than "
        f"{var.names[px]} and {var.names[qx]} is held fixed.",
        "This is a slice, not a projection: points feasible in the full space need not "
        "appear here, and the slice can be empty for a feasible problem.",
    ]
    if lattice_kind != "none" and not ref_integral:
        notes.append(
            "The reference point holds at least one discrete variable at a fractional "
            "value, so no point in this slice is integer-feasible. The lattice overlay "
            "is suppressed rather than drawn empty."
        )
    if len(sharing) > max_sliders:
        notes.append(
            f"{len(sharing)} variables share a row with this pair; sliders are shown for "
            f"the first {max_sliders}."
        )
    if any((u_lc, u_hc, v_lc, v_hc)):
        notes.append(
            "A slice variable is unbounded, so the plot window is artificial. Edges drawn "
            "as dashed grey are the window, not constraints."
        )

    return Slice2D(
        px=px,
        qx=qx,
        px_name=var.names[px],
        qx_name=var.names[qx],
        x_ref=x_ref,
        ref_origin=ref_origin,
        window=(u_lo, u_hi, v_lo, v_hi),
        window_clipped=(u_lc, u_hc, v_lc, v_hc),
        halfplanes=halfplanes,
        polygon=poly,
        lattice=lattice,
        lattice_kind=lattice_kind,
        constant_rows_violated=constant_violated,
        slider_vars=slider_vars,
        empty_reason=empty_reason,
        notes=notes,
    )


def pick_pair(mat: MatrixFacts, var: VariableFacts) -> tuple[int, int] | None:
    """The two variables appearing in the most rows -- they shape the picture most."""
    if var.n < 2:
        return None
    degree = [0] * var.n
    for row in mat.rows:
        for c in row.cols:
            degree[c] += 1
    order = sorted(range(var.n), key=lambda i: (-degree[i], i))
    return (order[0], order[1])
