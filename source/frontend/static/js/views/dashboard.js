/* ---------- Dashboard (US-9) ---------- */
let dashDays = '30';
let dashRange = null;   // {from, to} when "Custom" is applied

/* Charts are plain SVG/CSS (no library): ring gauge, donut, horizontal bars. */
const DX_ICON = {
  cal:   '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4M9.5 15l2 2 3.5-4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  wrench:'<path d="M14.7 6.3a4 4 0 0 0-5 5L4 17l3 3 5.7-5.7a4 4 0 0 0 5-5l-2.5 2.5-2.2-.5-.5-2.2z"/>',
  gauge: '<path d="M4 18a8 8 0 1 1 16 0"/><path d="m12 18 4-5"/>',
  info:  '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.5"/>'
};
const dxIcon = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true">${DX_ICON[k]}</svg>`;
const DX_GO = '<svg class="dx-go" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
const DX_BUSY = 85;   // utilization at or above this is flagged as near capacity

function dxPct(v){
  const n = Math.round((Number(v) || 0) * 10) / 10;
  return (Number.isInteger(n) ? n : n.toFixed(1)) + '%';
}
function dxDate(iso){
  return new Date(iso).toLocaleDateString([], {day:'numeric', month:'short', year:'numeric'});
}
function dxRing(pct){
  const R = 26, C = 2 * Math.PI * R, len = Math.max(0, Math.min(100, pct)) / 100 * C;
  const fg = len > 0.5 ? `<circle class="dx-ring-fg" cx="32" cy="32" r="${R}" stroke-dasharray="${len.toFixed(1)} ${(C - len).toFixed(1)}" transform="rotate(-90 32 32)"/>` : '';
  return `<svg class="dx-ring" viewBox="0 0 64 64" aria-hidden="true"><circle class="dx-ring-bg" cx="32" cy="32" r="${R}"/>${fg}</svg>`;
}
function dxDonut(segs, total){
  const R = 54, C = 2 * Math.PI * R;
  const live = segs.filter(s => s.v > 0);
  const gap = live.length > 1 ? 3 : 0;
  let off = 0;
  const arcs = total ? live.map(s => {
    const len = s.v / total * C, dash = Math.max(len - gap, 0.5);
    const el = `<circle class="dx-arc" data-k="${s.key}" cx="70" cy="70" r="${R}" style="stroke:${s.color}" stroke-dasharray="${dash.toFixed(2)} ${(C - dash).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}"><title>${escapeHtml(s.label)}: ${s.v}</title></circle>`;
    off += len;
    return el;
  }).join('') : '';
  return `<svg class="dx-donut" viewBox="0 0 140 140" role="img" aria-label="Resources by status, ${total} in total">
    <circle class="dx-donut-bg" cx="70" cy="70" r="${R}"/>
    <g transform="rotate(-90 70 70)">${arcs}</g>
    <text class="dx-donut-num" x="70" y="70" text-anchor="middle">${total}</text>
    <text class="dx-donut-cap" x="70" y="88" text-anchor="middle">resources</text>
  </svg>`;
}
function dxKpi({tone, icon, label, num, sub, hot, goto}){
  const head = `<div class="dx-kpi-top"><span class="dx-ico">${dxIcon(icon)}</span><span>${escapeHtml(label)}</span>${goto ? DX_GO : ''}</div>
    <div class="dx-num">${num}</div><div class="dx-sub">${escapeHtml(sub)}</div>`;
  const cls = `dx-kpi dx-t-${tone}${hot ? ' dx-hot' : ''}`;
  return goto
    ? `<button type="button" class="${cls}" data-goto="${goto}">${head}</button>`
    : `<div class="${cls}">${head}</div>`;
}

let dashReq = 0;   // ignore a slow response if a newer request has started
async function loadDashboard(){
  const box = document.getElementById('dash-content');
  const myReq = ++dashReq;
  if(!box.firstElementChild){
    box.innerHTML = `<div class="dx-kpis">${'<div class="dx-skel" style="height:128px"></div>'.repeat(4)}</div>
      <div class="dx-grid"><div class="dx-skel" style="height:300px"></div><div class="dx-skel" style="height:300px"></div></div>`;
  }
  box.setAttribute('aria-busy', 'true');
  const query = dashRange ? `from=${dashRange.from}&to=${dashRange.to}` : `days=${dashDays}`;
  let res;
  try{ res = await apiAuthGet('/api/dashboard?' + query); }
  catch(err){ res = {ok:false, data:{error:'Could not reach the server.'}}; }
  if(myReq !== dashReq) return;
  box.removeAttribute('aria-busy');
  const {ok, data} = res;
  if(!ok){
    box.innerHTML = `<div class="dx-empty"><b>Couldn’t load the dashboard</b>${escapeHtml((data && data.error) || 'Something went wrong. Please try again.')}<br><button class="btn ok" type="button" data-dx-retry>Try again</button></div>`;
    return false;
  }

  const r = data.resources, b = data.bookings, i = data.issues;
  const cats = [...data.utilization].sort((a, c) => c.utilization_pct - a.utilization_pct);
  const totRes = cats.reduce((s, u) => s + u.resources, 0);
  const overall = totRes ? cats.reduce((s, u) => s + u.utilization_pct * u.resources, 0) / totRes : 0;
  const overallBusy = overall >= DX_BUSY;

  /* KPI row */
  const kpis = `<div class="dx-kpis">
    <div class="dx-kpi dx-kpi-ring dx-t-${overallBusy ? 'amber' : 'green'}">
      <div>
        <div class="dx-kpi-top"><span>Overall utilization</span></div>
        <div class="dx-num">${dxPct(overall)}</div>
        <div class="dx-sub">${totRes ? 'of available hours were booked' : 'no resources yet'}</div>
      </div>${dxRing(overall)}
    </div>
    ${dxKpi({tone:'blue', icon:'cal', label:'Active bookings', num:b.active, sub: b.active ? 'approved and happening now' : 'nothing booked right now'})}
    ${dxKpi({tone:'amber', icon:'clock', label:'Requests waiting', num:b.pending, sub: b.pending ? 'need an administrator’s decision' : 'all caught up', hot: b.pending > 0, goto:'bookings'})}
    ${dxKpi({tone:'rust', icon:'wrench', label:'Open issues', num:i.open, sub: i.pending_review ? `+ ${i.pending_review} waiting for review` : (i.open ? 'confirmed, not yet resolved' : 'no open issues'), hot: i.open > 0 || i.pending_review > 0, goto:'maintenance'})}
  </div>`;

  /* Resource status donut */
  const segs = [
    {key:'Available',   label:'Available',      sub:'ready to book', v:r.available,   color:'var(--green)'},
    {key:'In Use',      label:'In use',         sub:'checked in now',    v:r.in_use,      color:'var(--blue)'},
    {key:'Maintenance', label:'Maintenance',    sub:'not bookable',  v:r.maintenance, color:'var(--brown-soft)'}
  ];
  const legend = segs.map(s => `
    <button type="button" class="dx-leg" data-k="${s.key}" data-goto="resources" data-status="${s.key}">
      <i class="dx-dot" style="background:${s.color}"></i>
      <span class="dx-leg-name">${s.label}<small>${s.sub}</small></span>
      <b>${s.v}</b><span class="dx-leg-pct">${r.total ? Math.round(s.v / r.total * 100) : 0}%</span>
    </button>`).join('');
  const statusPanel = `<section class="dx-panel" aria-labelledby="dx-h-status">
    <div class="dx-panel-head"><h3 id="dx-h-status">Resource status</h3><p>Right now · archived resources aren’t counted</p></div>
    ${r.total
      ? `<div class="dx-donut-wrap">${dxDonut(segs, r.total)}<div class="dx-legend">${legend}</div></div>`
      : `<div class="dx-empty"><b>No resources yet</b>Add your first resource to see its status here.<br><button class="btn ok" type="button" data-goto="resources">Go to resources</button></div>`}
  </section>`;

  /* Utilization bars */
  let insight = '';
  if(cats.length && cats.every(u => !u.booked_hours)){
    insight = 'No bookings were made in this period yet.';
  } else if(cats.length > 1 && cats[0].utilization_pct !== cats[cats.length - 1].utilization_pct){
    const hi = cats[0], lo = cats[cats.length - 1];
    insight = `<b>${escapeHtml(hi.category)}</b> is the busiest at ${dxPct(hi.utilization_pct)}. <b>${escapeHtml(lo.category)}</b> has the most room at ${dxPct(lo.utilization_pct)}.`;
  }
  const bars = cats.map(u => {
    const pct = Number(u.utilization_pct) || 0, busy = pct >= DX_BUSY;
    const w = Math.min(100, pct), shown = pct > 0 ? Math.max(w, 1.5) : 0;
    return `<button type="button" class="dx-bar" data-lvl="${busy ? 'busy' : 'ok'}" data-goto="resources" data-category="${escapeHtml(u.category)}"
        aria-label="${escapeHtml(u.category)}: ${dxPct(pct)} utilization. Open resources.">
      <div class="dx-bar-top"><span class="dx-bar-name">${escapeHtml(u.category)}</span>
        <span class="dx-bar-val">${dxPct(pct)}</span></div>
      <div class="dx-track" aria-hidden="true"><i style="--w:${shown}%"></i></div>
      <div class="dx-bar-sub"><span>${u.resources} resource${u.resources === 1 ? '' : 's'} · ${u.booked_hours} h booked</span>${busy ? '<span class="badge b-amber">Near capacity</span>' : ''}</div>
    </button>`;
  }).join('');
  const utilPanel = `<section class="dx-panel" aria-labelledby="dx-h-util">
    <div class="dx-panel-head"><h3 id="dx-h-util">Utilization by category</h3><p>Booked hours ÷ (resources × hours in the period). Select a category to see its resources.</p></div>
    ${cats.length
      ? `<div class="dx-bars">${bars}</div><div class="dx-axis" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div>
         ${insight ? `<div class="dx-insight">${dxIcon('info')}<span>${insight}</span></div>` : ''}`
      : `<div class="dx-empty"><b>No categories yet</b>Utilization appears once resources are added.</div>`}
  </section>`;

  box.innerHTML = `
    <div class="dx-meta"><span>Showing <b>${dxDate(data.period.from)} – ${dxDate(data.period.to)}</b></span></div>
    ${kpis}
    <div class="dx-grid">${statusPanel}${utilPanel}</div>`;
  return true;
}

/* highlight the matching donut slice while hovering / focusing a legend row; retry after an error */
(function(){
  const box = document.getElementById('dash-content');
  const hl = (e, on) => {
    const leg = e.target.closest('.dx-leg'); if(!leg) return;
    box.querySelectorAll('.dx-arc').forEach(a => { a.style.opacity = (!on || a.dataset.k === leg.dataset.k) ? '' : '.25'; });
  };
  box.addEventListener('mouseover', e => hl(e, true));
  box.addEventListener('mouseout',  e => hl(e, false));
  box.addEventListener('focusin',   e => hl(e, true));
  box.addEventListener('focusout',  e => hl(e, false));
  box.addEventListener('click', e => { if(e.target.closest('[data-dx-retry]')) loadDashboard(); });
  // "Custom" opens with the last 30 days pre-filled so the person only has to adjust it
  document.getElementById('dash-period').addEventListener('click', e => {
    if(!e.target.closest('button[data-days="custom"]')) return;
    const from = document.getElementById('dash-from'), to = document.getElementById('dash-to');
    if(!to.value) to.value = new Date().toLocaleDateString('en-CA');
    if(!from.value) from.value = new Date(Date.now() - 29 * 864e5).toLocaleDateString('en-CA');
  });
})();

document.getElementById('dash-period').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-days]');
  if(!btn) return;
  document.querySelectorAll('#dash-period .filter-chip').forEach(b => b.classList.toggle('active', b === btn));
  const custom = btn.dataset.days === 'custom';
  document.getElementById('dash-custom').style.display = custom ? 'flex' : 'none';
  if(!custom){ dashDays = btn.dataset.days; dashRange = null; loadDashboard(); }
});
document.getElementById('dash-apply').addEventListener('click', () => {
  const from = document.getElementById('dash-from').value, to = document.getElementById('dash-to').value;
  if(!from || !to){ toast('Choose both dates'); return; }
  dashRange = {from, to};
  loadDashboard();
});
setupRefreshButton('btn-refresh-dash', () => loadDashboard());
