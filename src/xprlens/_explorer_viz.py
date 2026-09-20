"""Vanilla SVG explorer for interactive two-dimensional model slices."""

from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import _compat
from ._xp import is_inf, xpress
from .facts import (
    MatrixFacts,
    VariableFacts,
    read_classification,
    read_matrix,
    read_shape,
    read_status,
    read_variables,
)
from .report import _reference_point, _resolve_pair
from .slice2d import pick_pair


def _mps_facts(
    prob: Any, variables: VariableFacts, output_dir: Path
) -> tuple[list[float | None], float]:
    export = output_dir / f".xprlens-{uuid4().hex}.mps"
    try:
        writer = getattr(prob, "writeProb", None) or prob.write
        writer(str(export))
        section = ""
        column_names: list[str] = []
        lower_bounds: dict[str, float] = {}
        objective_row: str | None = None
        objective_rhs = 0.0
        for line in export.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped in {"ROWS", "COLUMNS", "BOUNDS", "RHS", "ENDATA"}:
                section = stripped
                continue
            fields = stripped.split()
            if section == "ROWS" and len(fields) >= 2 and fields[0] == "N":
                objective_row = fields[1]
            elif section == "COLUMNS" and fields and "'MARKER'" not in fields:
                if fields[0] not in column_names:
                    column_names.append(fields[0])
            elif section == "RHS" and objective_row is not None:
                for row, value in zip(fields[1::2], fields[2::2], strict=False):
                    if row == objective_row:
                        objective_rhs = float(value)
            elif section == "BOUNDS" and len(fields) >= 4 and fields[0] == "LO":
                lower_bounds[fields[2]] = float(fields[3])
    finally:
        export.unlink(missing_ok=True)

    if len(column_names) != variables.n:
        raise ValueError("cannot match semi-variable thresholds to the model columns")
    thresholds = [
        lower_bounds.get(column_names[index], 0.0) if coltype in {"S", "R"} else None
        for index, coltype in enumerate(variables.coltype)
    ]
    return thresholds, -objective_rhs


def _model_data(
    prob: Any,
    matrix: MatrixFacts,
    variables: VariableFacts,
    reference: list[float],
    reference_origin: str,
    reference_optimal: bool,
    pair: tuple[int, int],
    output_dir: Path,
) -> dict[str, Any]:
    thresholds, objective_offset = _mps_facts(prob, variables, output_dir)
    model_variables = [
        {
            "name": name,
            "type": variables.coltype[index],
            "lo": None if is_inf(variables.lb[index]) else variables.lb[index],
            "hi": None if is_inf(variables.ub[index]) else variables.ub[index],
            "threshold": thresholds[index],
        }
        for index, name in enumerate(variables.names)
    ]
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

    coefficients = _compat.obj_coefficients(prob, variables.n)
    sense = "minimize" if float(prob.attributes.objsense) > 0 else "maximize"
    return {
        "vars": model_variables,
        "c": coefficients,
        "offset": objective_offset,
        "sense": sense,
        "reference": reference,
        "referenceValue": objective_offset
        + sum(c * value for c, value in zip(coefficients, reference, strict=False)),
        "referenceOrigin": reference_origin,
        "referenceOptimal": reference_optimal,
        "rows": rows,
        "initialPair": pair,
    }


_CSS = """
:root{--ink:#17211d;--muted:#66716b;--faint:#8a948e;--paper:#fbfcf8;--band:#eef2eb;
  --line:#ccd5cd;--control:#fff;--feas:#235c45;--feas-fill:#63a478;--relax:#2878a0;
  --objective:#bd641c;--bad:#a5372f;--good:#287345;--focus:#176f8c}
@media(prefers-color-scheme:dark){:root{--ink:#eef3ed;--muted:#b4beb6;--faint:#8f9991;
  --paper:#171c19;--band:#222a25;--line:#465149;--control:#1c231f;--feas:#75c49a;
  --feas-fill:#3d8f61;--relax:#70b8dc;--objective:#ef9a4e;--bad:#f18b83;--good:#81cb99;
  --focus:#70b8dc}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:Verdana,sans-serif;
  font-size:14px;line-height:1.45}
header{border-bottom:1px solid var(--line);padding:1.15rem clamp(1rem,4vw,2.4rem)}
h1{margin:0;font-family:Georgia,serif;font-size:clamp(1.35rem,3vw,2rem);font-weight:500;letter-spacing:0}
.sub{margin:.25rem 0 0;color:var(--muted);font-size:.82rem}
main{max-width:1240px;margin:0 auto;padding:1.2rem clamp(.75rem,3vw,2rem) 2.5rem}
.toolbar{display:grid;grid-template-columns:repeat(3,minmax(130px,1fr)) auto;gap:.85rem;
  align-items:end;background:var(--band);border-block:1px solid var(--line);padding:1rem}
label{display:grid;gap:.3rem;color:var(--muted);font-size:.74rem;font-weight:700;text-transform:uppercase}
select,button,input{font:inherit;color:inherit}
select,button{width:100%;min-width:0;background:var(--control);border:1px solid var(--line);
  border-radius:6px;padding:.55rem .65rem}
select:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
button{cursor:pointer;white-space:nowrap}
.slider-row{display:grid;grid-template-columns:auto minmax(100px,1fr) auto;gap:.8rem;align-items:center;
  min-height:3.15rem;padding:.55rem 1rem;background:var(--band);border-bottom:1px solid var(--line)}
.slider-row[hidden]{display:none}.slider-row output{min-width:4.5rem;text-align:right;font-weight:700}
.visual{margin-top:1rem}svg{display:block;width:100%;height:auto;min-height:420px;max-height:72vh;
  background:var(--control);border:1px solid var(--line)}
svg text{font-family:Verdana,sans-serif;font-size:11px;fill:var(--muted)}
svg text.strong{font-size:13px;font-weight:700;fill:var(--ink)}
.status{min-height:1.5rem;margin:.8rem 0;font-size:.88rem}.status.bad{color:var(--bad)}
.status.good{color:var(--good)}
.chips{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1px;background:var(--line);
  border:1px solid var(--line)}
.chip{min-width:0;background:var(--band);padding:.65rem .75rem}.chip-name{font-weight:700;overflow-wrap:anywhere}
.chip-type{color:var(--faint);font-weight:400}.chip-state{color:var(--muted);font-size:.78rem;margin-top:.12rem}
.chip-state.set{color:var(--focus)}
.notes{margin:.8rem 0 0;padding-left:1.2rem;color:var(--muted);font-size:.78rem}.notes li{margin:.2rem 0}
footer{max-width:1240px;margin:0 auto;padding:0 2rem 2rem;color:var(--muted);font-size:.72rem}
@media(max-width:760px){.toolbar{grid-template-columns:1fr 1fr}.toolbar .fixed{grid-column:1/-1}
  .toolbar button{grid-column:1/-1}svg{min-height:330px}.chips{grid-template-columns:1fr 1fr}}
@media(max-width:450px){.toolbar{grid-template-columns:1fr}.toolbar .fixed,.toolbar button{grid-column:auto}
  .chips{grid-template-columns:1fr}}
"""


_SCRIPT = r"""
const model = __MODEL__;
const EPS = 1e-9;
const FALLBACK_SPAN = 10;
const MAX_PIECES = 3000;
const plot = document.getElementById('plot');
const hSelect = document.getElementById('h-variable');
const vSelect = document.getElementById('v-variable');
const fixedSelect = document.getElementById('fixed-variable');
const sliderRow = document.getElementById('slider-row');
const slider = document.getElementById('fixed-value');
const sliderName = document.getElementById('slider-name');
const sliderOutput = document.getElementById('slider-output');
const status = document.getElementById('slice-status');
const chips = document.getElementById('variable-chips');
const notes = document.getElementById('slice-notes');
let h = model.initialPair[0], v = model.initialPair[1], fixedSelection = null;
let explicitValues = {};

const esc = value => String(value).replace(/[&<>"']/g, character =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const integerType = type => ['B', 'I', 'R'].includes(type);
const valueAt = index => Object.hasOwn(explicitValues, index) ? explicitValues[index] : model.reference[index];
const formatNumber = value => {
  if (value === null || !Number.isFinite(value)) return 'unavailable';
  if (Math.abs(value - Math.round(value)) < 1e-7) return String(Math.round(value));
  return Number(value.toPrecision(6)).toString();
};
const typeLabel = variable => ({C:'continuous',B:'binary',I:'integer',S:'semi-continuous',
  R:'semi-integer'}[variable.type] || variable.type);

function finiteWindow(variable, reference) {
  if (variable.lo === null && variable.hi === null) return [reference-FALLBACK_SPAN, reference+FALLBACK_SPAN, true];
  if (variable.lo === null) return [variable.hi-FALLBACK_SPAN, variable.hi, true];
  if (variable.hi === null) return [variable.lo, variable.lo+FALLBACK_SPAN, true];
  if (variable.hi-variable.lo <= EPS) return [variable.lo-.5, variable.hi+.5, false];
  return [variable.lo, variable.hi, false];
}

function allowed(variable, value) {
  if (integerType(variable.type) && Math.abs(value-Math.round(value)) >= 1e-7) return false;
  if (['C','B','I'].includes(variable.type)) {
    return (variable.lo === null || value >= variable.lo-EPS)
      && (variable.hi === null || value <= variable.hi+EPS);
  }
  return Math.abs(value) < EPS || (value >= variable.threshold-EPS
    && (variable.hi === null || value <= variable.hi+EPS));
}

function domainPieces(variable, window) {
  const points = (lo, hi) => {
    const first = Math.ceil(lo-EPS), last = Math.floor(hi+EPS);
    if (last-first+1 > MAX_PIECES) return null;
    return Array.from({length:Math.max(0,last-first+1)}, (_, index) => ({p:first+index}));
  };
  if (variable.type === 'C') return [{lo:window[0],hi:window[1]}];
  if (['B','I'].includes(variable.type)) return points(window[0],window[1]);
  if (variable.type === 'S') {
    const interval = variable.threshold <= window[1]+EPS
      ? [{lo:Math.max(variable.threshold,window[0]),hi:window[1]}] : [];
    return Math.abs(variable.threshold) < EPS ? interval : [{p:0},...interval];
  }
  const active = points(Math.max(variable.threshold,window[0]),window[1]);
  return active === null ? null : [{p:0},...active.filter(piece => Math.abs(piece.p) >= EPS)];
}

function clipPolygon(polygon, halfplanes) {
  for (const [a,b,r] of halfplanes) {
    const output = [];
    for (let index=0; index<polygon.length; index+=1) {
      const point=polygon[index], next=polygon[(index+1)%polygon.length];
      const fp=a*point[0]+b*point[1]-r, fn=a*next[0]+b*next[1]-r;
      if (fp <= EPS) output.push(point);
      if (fp*fn < -1e-12) {
        const amount=fp/(fp-fn);
        output.push([point[0]+amount*(next[0]-point[0]),point[1]+amount*(next[1]-point[1])]);
      }
    }
    polygon=output;
    if (!polygon.length) break;
  }
  return polygon;
}

function clipSegment(start, end, halfplanes) {
  let first=0,last=1;
  for (const [a,b,r] of halfplanes) {
    const fs=a*start[0]+b*start[1]-r,fe=a*end[0]+b*end[1]-r;
    if (fs > EPS && fe > EPS) return null;
    if (fs > EPS) first=Math.max(first,fs/(fs-fe));
    else if (fe > EPS) last=Math.min(last,fs/(fs-fe));
  }
  if (first > last+1e-12) return null;
  const at=amount => [start[0]+amount*(end[0]-start[0]),start[1]+amount*(end[1]-start[1])];
  return [at(first),at(last)];
}

function calculateSlice(values) {
  const fixed=model.vars.map((_,index)=>index).filter(index=>index!==h&&index!==v);
  const invalid=fixed.find(index=>!allowed(model.vars[index],values[index]));
  const hWindow=finiteWindow(model.vars[h],values[h]),vWindow=finiteWindow(model.vars[v],values[v]);
  const constant=model.offset+fixed.reduce((sum,index)=>sum+model.c[index]*values[index],0);
  const halfplanes=[];
  for (const row of model.rows) {
    let a=0,b=0,fixedValue=0;
    row.cols.forEach((column,index)=>{
      const coefficient=row.coefs[index];
      if(column===h)a+=coefficient;else if(column===v)b+=coefficient;
      else fixedValue+=coefficient*values[column];
    });
    if(row.hi!==null)halfplanes.push([a,b,row.hi-fixedValue]);
    if(row.lo!==null)halfplanes.push([-a,-b,-(row.lo-fixedValue)]);
  }
  const objective=(horizontal,vertical)=>model.c[h]*horizontal+model.c[v]*vertical+constant;
  const better=(candidate,current)=>current===null
    ||(model.sense==='maximize'?candidate>current+EPS:candidate<current-EPS);
  const relaxBounds=(variable,window)=>['S','R'].includes(variable.type)
    ?[Math.min(0,variable.threshold),window[1]]:window.slice(0,2);
  const hb=relaxBounds(model.vars[h],hWindow),vb=relaxBounds(model.vars[v],vWindow);
  const relaxation=invalid===undefined?clipPolygon(
    [[hb[0],vb[0]],[hb[1],vb[0]],[hb[1],vb[1]],[hb[0],vb[1]]],halfplanes):[];
  let relaxationBest=null;
  relaxation.forEach(point=>{const score=objective(point[0],point[1]);
    if(better(score,relaxationBest))relaxationBest=score;});
  const horizontalPieces=domainPieces(model.vars[h],hWindow);
  const verticalPieces=domainPieces(model.vars[v],vWindow);
  const tooMany=horizontalPieces===null||verticalPieces===null
    ||horizontalPieces.length*verticalPieces.length>MAX_PIECES;
  const shapes=[];let best=null,bestPoint=null;
  const candidate=(horizontal,vertical)=>{const score=objective(horizontal,vertical);
    if(better(score,best)){best=score;bestPoint=[horizontal,vertical];}};
  if(invalid===undefined&&!tooMany){
    for(const hp of horizontalPieces)for(const vp of verticalPieces){
      const horizontalPoint=Object.hasOwn(hp,'p'),verticalPoint=Object.hasOwn(vp,'p');
      if(horizontalPoint&&verticalPoint){
        if(halfplanes.every(([a,b,r])=>a*hp.p+b*vp.p<=r+EPS)){
          shapes.push({kind:'point',points:[[hp.p,vp.p]]});candidate(hp.p,vp.p);
        }
      }else if(horizontalPoint||verticalPoint){
        const start=horizontalPoint?[hp.p,vp.lo]:[hp.lo,vp.p];
        const end=horizontalPoint?[hp.p,vp.hi]:[hp.hi,vp.p];
        const clipped=clipSegment(start,end,halfplanes);
        if(clipped){shapes.push({kind:'segment',points:clipped});
          clipped.forEach(point=>candidate(point[0],point[1]));}
      }else{
        const clipped=clipPolygon([[hp.lo,vp.lo],[hp.hi,vp.lo],[hp.hi,vp.hi],[hp.lo,vp.hi]],halfplanes);
        if(clipped.length){shapes.push({kind:'polygon',points:clipped});
          clipped.forEach(point=>candidate(point[0],point[1]));}
      }
    }
  }
  return{invalid,tooMany,hWindow,vWindow,constant,shapes,relaxation,relaxationBest,best,bestPoint};
}

const ticks=(lo,hi,count=6)=>Array.from({length:count+1},(_,index)=>lo+(hi-lo)*index/count);
function draw() {
  const values=model.vars.map((_,index)=>valueAt(index));
  const slice=calculateSlice(values);
  const left=58,right=478,top=42,bottom=404,width=right-left,height=bottom-top;
  const [hLo,hHi]=slice.hWindow,[vLo,vHi]=slice.vWindow;
  const windowed=slice.hWindow[2]||slice.vWindow[2];
  const x=value=>left+(value-hLo)*width/(hHi-hLo),y=value=>bottom-(value-vLo)*height/(vHi-vLo);
  const points=items=>items.map(point=>`${x(point[0])},${y(point[1])}`).join(' ');
  let svg='';
  for(const tick of ticks(hLo,hHi))svg+=`<line x1="${x(tick)}" y1="${top}" x2="${x(tick)}" y2="${bottom}" stroke="var(--line)"/><text x="${x(tick)}" y="${bottom+18}" text-anchor="middle">${esc(formatNumber(tick))}</text>`;
  for(const tick of ticks(vLo,vHi))svg+=`<line x1="${left}" y1="${y(tick)}" x2="${right}" y2="${y(tick)}" stroke="var(--line)"/><text x="${left-8}" y="${y(tick)+4}" text-anchor="end">${esc(formatNumber(tick))}</text>`;
  const horizontalGap=variable=>{
    if(!['S','R'].includes(variable.type)||variable.threshold<=0)return'';
    const lo=Math.max(0,hLo),hi=Math.min(variable.threshold,hHi);
    return hi>lo?`<rect x="${x(lo)}" y="${top}" width="${x(hi)-x(lo)}" height="${height}" fill="url(#hatch)"/>`:'';
  };
  const verticalGap=variable=>{
    if(!['S','R'].includes(variable.type)||variable.threshold<=0)return'';
    const lo=Math.max(0,vLo),hi=Math.min(variable.threshold,vHi);
    return hi>lo?`<rect x="${left}" y="${y(hi)}" width="${width}" height="${y(lo)-y(hi)}" fill="url(#hatch)"/>`:'';
  };
  svg+=horizontalGap(model.vars[h])+verticalGap(model.vars[v]);
  if(slice.relaxation.length>2)svg+=`<polygon points="${points(slice.relaxation)}" fill="var(--relax)" fill-opacity=".12" stroke="var(--relax)" stroke-width="1.5" stroke-dasharray="5 4"/>`;
  for(const shape of slice.shapes){
    if(shape.kind==='point')svg+=`<circle cx="${x(shape.points[0][0])}" cy="${y(shape.points[0][1])}" r="3.8" fill="var(--feas)"/>`;
    else if(shape.kind==='segment')svg+=`<line x1="${x(shape.points[0][0])}" y1="${y(shape.points[0][1])}" x2="${x(shape.points[1][0])}" y2="${y(shape.points[1][1])}" stroke="var(--feas)" stroke-width="4" stroke-linecap="round"/>`;
    else svg+=`<polygon points="${points(shape.points)}" fill="var(--feas-fill)" fill-opacity=".52" stroke="var(--feas)" stroke-width="1.5"/>`;
  }
  if(slice.best!==null){
    const target=slice.best-slice.constant,ch=model.c[h],cv=model.c[v];let line=null;
    if(Math.abs(cv)>EPS)line=[[hLo,(target-ch*hLo)/cv],[hHi,(target-ch*hHi)/cv]];
    else if(Math.abs(ch)>EPS)line=[[target/ch,vLo],[target/ch,vHi]];
    if(line)svg+=`<g clip-path="url(#plot-clip)"><line x1="${x(line[0][0])}" y1="${y(line[0][1])}" x2="${x(line[1][0])}" y2="${y(line[1][1])}" stroke="var(--objective)" stroke-width="2.5"/></g>`;
    svg+=`<circle cx="${x(slice.bestPoint[0])}" cy="${y(slice.bestPoint[1])}" r="6" fill="var(--objective)" stroke="var(--control)" stroke-width="2"/>`;
  }
  svg+=`<rect x="${left}" y="${top}" width="${width}" height="${height}" fill="none" stroke="var(--faint)"/>`;
  svg+=`<text class="strong" x="${right+8}" y="${bottom+4}">${esc(model.vars[h].name)}</text><text class="strong" x="${left}" y="${top-12}">${esc(model.vars[v].name)}</text>`;
  svg+=`<line x1="516" y1="76" x2="546" y2="76" stroke="var(--feas)" stroke-width="4" stroke-linecap="round"/><text x="556" y="80">Feasible pieces</text>`;
  svg+=`<rect x="516" y="98" width="30" height="15" fill="url(#hatch)" stroke="var(--line)"/><text x="556" y="110">Semi-variable gap</text>`;
  svg+=`<rect x="516" y="132" width="30" height="15" fill="var(--relax)" fill-opacity=".12" stroke="var(--relax)" stroke-dasharray="4 3"/><text x="556" y="144">Continuous relaxation</text>`;
  svg+=`<line x1="516" y1="174" x2="546" y2="174" stroke="var(--objective)" stroke-width="2.5"/><text x="556" y="178">Objective at slice best</text>`;
  svg+=`<circle cx="531" cy="202" r="6" fill="var(--objective)"/><text x="556" y="206">Slice best</text>`;
  svg+=`<text class="strong" x="516" y="256">${windowed?'Window best':'Slice best'}: ${esc(formatNumber(slice.best))}</text>`;
  svg+=`<text x="516" y="280">${windowed?'Window relaxation':'Relaxation'}: ${esc(formatNumber(slice.relaxationBest))}</text>`;
  svg+=`<text x="516" y="304">${esc(model.referenceOptimal?'Global optimum':'Reference value')}: ${esc(formatNumber(model.referenceValue))}</text>`;
  plot.innerHTML=svg;
  status.className='status';
  if(slice.invalid!==undefined){
    const variable=model.vars[slice.invalid];
    status.textContent=`${variable.name} = ${formatNumber(values[slice.invalid])} is outside its domain.`;
    status.classList.add('bad');
  }else if(slice.tooMany){
    status.textContent='The selected integer domains create more than 3,000 pieces; the exact feasible overlay and slice best are withheld.';status.classList.add('bad');
  }else if(slice.best===null){
    status.textContent='No feasible points exist in this slice.';status.classList.add('bad');
  }else if(!windowed&&model.referenceOptimal&&Math.abs(slice.best-model.referenceValue)<1e-6){
    status.textContent=`This slice contains the global optimum at ${model.vars[h].name} = ${formatNumber(slice.bestPoint[0])}, ${model.vars[v].name} = ${formatNumber(slice.bestPoint[1])}.`;status.classList.add('good');
  }else{
    status.textContent=`Best in ${windowed?'the displayed window':'this slice'}: ${formatNumber(slice.best)} at ${model.vars[h].name} = ${formatNumber(slice.bestPoint[0])}, ${model.vars[v].name} = ${formatNumber(slice.bestPoint[1])}.`;
  }
  chips.innerHTML=model.vars.map((variable,index)=>{
    const axis=index===h?'horizontal axis':index===v?'vertical axis':null;
    const state=axis||(Object.hasOwn(explicitValues,index)?`set to ${formatNumber(valueAt(index))}`
      :`${model.referenceOptimal?'optimum':'reference'} value ${formatNumber(valueAt(index))}`);
    return `<div class="chip"><div class="chip-name">${esc(variable.name)} <span class="chip-type">${esc(typeLabel(variable))}</span></div><div class="chip-state${Object.hasOwn(explicitValues,index)&&!axis?' set':''}">${esc(state)}</div></div>`;
  }).join('');
  const messages=['This is a slice, not a projection; all non-axis variables are fixed.',
    `Default fixed values come from ${model.referenceOrigin}.`];
  if(slice.hWindow[2]||slice.vWindow[2])messages.push('An axis is unbounded, so its displayed window is finite and artificial.');
  notes.replaceChildren(...messages.map(message=>{const item=document.createElement('li');item.textContent=message;return item;}));
}

function otherVariables(){return model.vars.map((_,index)=>index).filter(index=>index!==h&&index!==v);}
function fillControls(){
  const fill=(select,selected,indices)=>{select.replaceChildren(...indices.map(index=>
    new Option(`${model.vars[index].name} (${model.vars[index].type})`,index,index===selected,index===selected)));};
  const all=model.vars.map((_,index)=>index);fill(hSelect,h,all);fill(vSelect,v,all);
  const others=otherVariables();
  if(!others.length){fixedSelection=null;sliderRow.hidden=true;fixedSelect.disabled=true;return;}
  if(!others.includes(fixedSelection))fixedSelection=others[0];
  fill(fixedSelect,fixedSelection,others);fixedSelect.disabled=false;sliderRow.hidden=false;
  const variable=model.vars[fixedSelection],window=finiteWindow(variable,valueAt(fixedSelection));
  slider.min=window[0];slider.max=window[1];slider.step=integerType(variable.type)?1:Math.max((window[1]-window[0])/200,.001);
  slider.value=Math.min(window[1],Math.max(window[0],valueAt(fixedSelection)));
  sliderName.textContent=variable.name;sliderOutput.textContent=formatNumber(valueAt(fixedSelection));
}

hSelect.addEventListener('change',event=>{const next=Number(event.target.value);if(next===v)v=h;h=next;fillControls();draw();});
vSelect.addEventListener('change',event=>{const next=Number(event.target.value);if(next===h)h=v;v=next;fillControls();draw();});
fixedSelect.addEventListener('change',event=>{fixedSelection=Number(event.target.value);fillControls();});
slider.addEventListener('input',event=>{explicitValues[fixedSelection]=Number(Number(event.target.value).toFixed(9));sliderOutput.textContent=formatNumber(valueAt(fixedSelection));draw();});
document.getElementById('reset-values').addEventListener('click',()=>{explicitValues={};fillControls();draw();});
fillControls();draw();
"""


def _build_page(title: str, model: dict[str, Any]) -> str:
    model_json = json.dumps(model, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    script = _SCRIPT.replace("__MODEL__", model_json)
    safe_title = html.escape(title)
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{safe_title}</title><style>{_CSS}</style></head><body>"
        f"<header><h1>{safe_title}</h1><p class='sub'>Interactive 2D model slice</p></header>"
        "<main><div class='toolbar'>"
        "<label>Horizontal axis<select id='h-variable'></select></label>"
        "<label>Vertical axis<select id='v-variable'></select></label>"
        "<label class='fixed'>Fixed variable<select id='fixed-variable'></select></label>"
        "<button id='reset-values' type='button'>Reset values</button></div>"
        "<div id='slider-row' class='slider-row'><span id='slider-name'></span>"
        "<input id='fixed-value' type='range'><output id='slider-output'></output></div>"
        "<div class='visual'><svg viewBox='0 0 760 460' role='img' "
        "aria-label='Interactive two-dimensional model slice'><defs>"
        "<pattern id='hatch' width='8' height='8' patternUnits='userSpaceOnUse' "
        "patternTransform='rotate(45)'><line x1='0' y1='0' x2='0' y2='8' "
        "stroke='var(--faint)' stroke-width='1' opacity='.5'/></pattern>"
        "<clipPath id='plot-clip'><rect x='58' y='42' width='420' height='362'/></clipPath>"
        "</defs><g id='plot'></g></svg></div>"
        "<div id='slice-status' class='status'></div><div id='variable-chips' class='chips'></div>"
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
    """Write a self-contained SVG explorer for interactive two-dimensional slices."""
    xp = xpress()
    if not isinstance(prob, xp.problem):
        raise TypeError(f"expected an xpress.problem, got {type(prob).__name__}")

    shape = read_shape(prob)
    if shape.presolved:
        raise ValueError(
            "cannot explore a presolved problem because its original matrix is unavailable"
        )
    classification = read_classification(prob)
    unsupported_features = [
        name
        for name in (
            "SOS sets",
            "Indicator constraints",
            "Piecewise-linear constraints",
            "General constraints",
            "Quadratic objective terms",
            "Quadratic constraints",
        )
        if classification.features[name]
    ]
    if classification.label in {"NLP", "MINLP"} or unsupported_features:
        details = ", ".join(unsupported_features) or "nonlinear constraints"
        raise ValueError(
            "slice_explorer supports linear objectives and ordinary linear constraints only; "
            f"found {details}"
        )
    status = read_status(prob)
    variables = read_variables(prob, solved=status.started)
    if variables.n < 2:
        raise ValueError("slice_explorer requires at least two variables")
    unsupported = [
        variables.names[index] for index, coltype in enumerate(variables.coltype) if coltype == "P"
    ]
    if unsupported:
        raise ValueError(
            "slice_explorer does not support partial-integer variables: " + ", ".join(unsupported)
        )

    matrix = read_matrix(prob, rows=shape.rows, cols=shape.cols)
    pair = _resolve_pair(slice_vars, variables) or pick_pair(matrix, variables)
    assert pair is not None
    reference, reference_origin = _reference_point(prob, status, variables)

    name = str(prob.attributes.matrixname or "problem")
    if name == "noname":
        name = "problem"
    out = Path(path) if path is not None else Path(f"{name}-xprlens-slice.html")
    page_title = title or f"{name} - interactive 2D slice"
    page = _build_page(
        page_title,
        _model_data(
            prob,
            matrix,
            variables,
            reference,
            reference_origin,
            status.proven_optimal,
            pair,
            out.parent,
        ),
    )
    out.write_text(page, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out
