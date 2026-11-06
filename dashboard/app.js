/* Group 15 Research Atlas: interactive dashboard over data.js (built by build_dashboard.py). */
(() => {
const D = window.DATA;
const I = D.insts, SHORT = ['MANIT', 'NITJ', 'NITS'];
const P = D.papers, F = D.fac;
// paper tuple fields
const T = { title: 0, year: 1, type: 2, venue: 3, cites: 4, doi: 5, q: 6, field: 7, mask: 8, pr: 9, indeg: 10, outdeg: 11, iff: 12, multi: 13, inh: 14, ci: 15, cbi: 16, fwci: 17, vkind: 18, conf: 19, core: 20, subfield: 21, topic: 22, inSelf: 23, inSame: 24, inCross: 25, prYear: 26, wid: 27, review: 28, qsrc: 29, nref: 30, nauth: 31, ninst: 32, ncty: 33, ifS: 34, ifO: 35 };
const YEARS = d3.range(2016, 2027);

const state = { inst: -1, tab: 'overview', dirty: new Set(), history: [] };
const $ = s => document.querySelector(s);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = d3.format(','), fmt1 = d3.format(',.1f'), fmt2 = d3.format('.2f'), fmt3 = d3.format('.3f');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const instColor = i => css(`--i${i}`);
const CAT = () => [1, 2, 3, 4, 5, 6, 7, 8].map(k => css(`--c${k}`));
const instsShown = () => state.inst < 0 ? [0, 1, 2] : [state.inst];
const inInst = mask => state.inst < 0 || (mask & (1 << state.inst));
const instNames = mask => [0, 1, 2].filter(i => mask & (1 << i));
const qChip = q => /^Q[1-4]$/.test(q) ? `<span class="q ${q}">${q}</span>` : `<span class="q other">${esc(q || '—')}</span>`;
const instChip = i => `<span class="chip"><span class="dot" style="background:${instColor(i)}"></span>${SHORT[i]}</span>`;
const doiLink = d => d ? `<a href="${esc(d)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">DOI ↗</a>` : '';

// ---------------------------------------------------------------- indexes
const facPapers = F.map(() => []);
D.pfac.forEach((fs, p) => fs.forEach(f => facPapers[f].push(p)));
const adj = F.map(() => []);
D.fedges.forEach(([a, b, w]) => { adj[a].push([b, w]); adj[b].push([a, w]); });
adj.forEach(l => l.sort((x, y) => y[1] - x[1]));
const citesOut = P.map(() => []), citesIn = P.map(() => []);
D.cedges.forEach(([s, t]) => { citesOut[s].push(t); citesIn[t].push(s); });
const prOrder = d3.range(P.length).sort((a, b) => P[b][T.pr] - P[a][T.pr]);
const prRank = new Int32Array(P.length); prOrder.forEach((p, r) => prRank[p] = r + 1);
const fieldCount = d3.rollups(P, v => v.length, p => p[T.field]).sort((a, b) => b[1] - a[1]);
const TOP_FIELDS = fieldCount.slice(0, 7).map(d => d[0]);
// Louvain communities: fixed colour per community by global size (colour follows the entity)
const commSize = d3.rollups(F.filter((f, i) => adj[i].length), v => v.length, f => f.lv).sort((a, b) => b[1] - a[1] || a[0] - b[0]);
const TOP_COMMS = commSize.slice(0, 8).map(d => d[0]);
const deptCount = d3.rollups(F, v => v.length, f => f.d).sort((a, b) => b[1] - a[1]).filter(d => d[0] !== 'Unknown department');
const TOP_DEPTS = deptCount.slice(0, 8).map(d => d[0]);

// ---------------------------------------------------------------- plotly helpers
function baseLayout(extra = {}) {
  const ink2 = css('--ink2'), grid = css('--grid'), axis = css('--axis');
  const ax = { gridcolor: grid, linecolor: axis, zerolinecolor: axis, tickfont: { color: css('--muted'), size: 11 }, title: { font: { color: ink2, size: 12 } }, automargin: true };
  return Object.assign({
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Geist, Inter, system-ui, sans-serif', color: ink2, size: 12 },
    margin: { l: 44, r: 12, t: 10, b: 36 }, barcornerradius: 4,
    hoverlabel: { bgcolor: css('--surface'), bordercolor: css('--axis'), font: { color: css('--ink'), family: 'Geist, Inter, system-ui, sans-serif' } },
    legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 12 } },
    xaxis: { ...ax }, yaxis: { ...ax },
  }, extra, {
    xaxis: Object.assign({ ...ax }, extra.xaxis || {}),
    yaxis: Object.assign({ ...ax }, extra.yaxis || {}),
  });
}
const lm = labels => Math.min(300, 16 + 6.4 * (d3.max(labels, l => String(l).length) || 0));
const isDark = () => css('--page').toLowerCase() === '#09090c';
function fitView(o, nodes, maxK = 2.5) {
  nodes = nodes.filter(n => n && n.x != null); if (!nodes.length) return;
  const [x0, x1] = d3.extent(nodes, n => n.x), [y0, y1] = d3.extent(nodes, n => n.y);
  const k = Math.min(maxK, .92 / Math.max((x1 - x0 + 40) / o.W, (y1 - y0 + 40) / o.H));
  o.svg.call(o.zoom.transform, d3.zoomIdentity.translate(o.W / 2, o.H / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
}
function plot(id, traces, layout = {}, onClick) {
  const el = document.getElementById(id);
  Plotly.react(el, traces, baseLayout(layout), { displayModeBar: false, responsive: true });
  if (onClick) { el.removeAllListeners?.('plotly_click'); el.on('plotly_click', onClick); }
}

// ---------------------------------------------------------------- generic table
function makeTable(host, opt) {
  const st = { sort: opt.sort || null, dir: opt.dir || -1, page: 0, q: '', filters: {} };
  host.innerHTML = '';
  const tools = document.createElement('div'); tools.className = 'tbl-tools';
  const wrap = document.createElement('div'); wrap.className = 'tbl-wrap';
  const pager = document.createElement('div'); pager.className = 'pager';
  host.append(tools, wrap, pager);
  if (opt.search) {
    const s = document.createElement('input'); s.type = 'search'; s.placeholder = opt.search;
    s.oninput = () => { st.q = s.value.toLowerCase(); st.page = 0; draw(); };
    tools.append(s); st.searchEl = s;
  }
  (opt.selects || []).forEach(sel => {
    const s = document.createElement('select');
    s.innerHTML = `<option value="">${esc(sel.label)}</option>` + sel.options.map(o => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
    s.onchange = () => { st.filters[sel.key] = s.value; st.page = 0; draw(); };
    tools.append(s); sel.el = s;
  });
  if (opt.extraTools) opt.extraTools(tools, st, () => draw());
  const ex = document.createElement('button'); ex.className = 'btn'; ex.type = 'button';
  ex.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg> CSV';
  ex.title = 'Download the filtered rows as CSV';
  ex.onclick = () => {
    const strip = s => String(s ?? '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    const cols = opt.columns.filter(c => c.label);
    const lines = [cols.map(c => '"' + strip(c.label).replace(/"/g, '""') + '"').join(',')]
      .concat(rowsNow().map(r => cols.map(c => '"' + strip(c.v(r)).replace(/"/g, '""') + '"').join(',')));
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv' }));
    a.download = (host.closest('.card')?.querySelector('h2')?.textContent || 'table').replace(/[^\w]+/g, '_').toLowerCase() + '.csv'; a.click();
    document.dispatchEvent(new CustomEvent('atlas:toast', { detail: `Downloaded ${fmt(rowsNow().length)} rows` }));
  };
  tools.append(ex);
  if (!tools.children.length) tools.remove();
  function rowsNow() {
    let r = opt.rows();
    if (st.q) r = r.filter(x => opt.text(x).toLowerCase().includes(st.q));
    (opt.selects || []).forEach(sel => { const v = st.filters[sel.key]; if (v) r = r.filter(x => sel.get(x) === v); });
    if (opt.filter) r = r.filter(x => opt.filter(x, st));
    if (st.sort) { const c = opt.columns.find(c => c.key === st.sort); r = r.slice().sort((a, b) => d3.ascending(c.v(a) ?? -Infinity, c.v(b) ?? -Infinity) * st.dir); }
    return r;
  }
  function draw() {
    const r = rowsNow(), ps = opt.pageSize || 10, pages = Math.max(1, Math.ceil(r.length / ps));
    st.page = Math.min(st.page, pages - 1);
    const slice = r.slice(st.page * ps, st.page * ps + ps);
    wrap.innerHTML = `<table><thead><tr>${opt.columns.map(c => `<th data-k="${c.key}" class="${c.num ? 'r' : ''}">${c.label}${st.sort === c.key ? ` <span class="arr">${st.dir > 0 ? '▲' : '▼'}</span>` : ''}</th>`).join('')}</tr></thead><tbody>${
      slice.map((x, i) => `<tr class="${opt.onRow ? 'row' : ''}" data-i="${i}">${opt.columns.map(c => `<td class="${c.num ? 'r num' : ''}">${c.html ? c.html(x) : esc(c.v(x))}</td>`).join('')}</tr>`).join('') ||
      `<tr><td colspan="${opt.columns.length}" class="note" style="padding:18px">No rows match.</td></tr>`}</tbody></table>`;
    wrap.querySelectorAll('th').forEach(th => th.onclick = () => { const k = th.dataset.k; if (st.sort === k) st.dir *= -1; else { st.sort = k; st.dir = opt.columns.find(c => c.key === k).num ? -1 : 1; } draw(); });
    if (opt.onRow) wrap.querySelectorAll('tr.row').forEach(tr => tr.onclick = () => opt.onRow(slice[+tr.dataset.i]));
    pager.innerHTML = r.length > ps ? `<span>${fmt(st.page * ps + 1)}–${fmt(Math.min(r.length, st.page * ps + ps))} of ${fmt(r.length)}</span><button ${st.page ? '' : 'disabled'} data-d="-1">‹ Prev</button><button ${st.page < pages - 1 ? '' : 'disabled'} data-d="1">Next ›</button>` : r.length ? `<span>${fmt(r.length)} rows</span>` : '';
    pager.querySelectorAll('button').forEach(b => b.onclick = () => { st.page += +b.dataset.d; draw(); });
  }
  draw();
  return { draw, st, opt };
}

// ---------------------------------------------------------------- header: institute switch, theme, search
function buildInstSeg() {
  const seg = $('#instSeg');
  seg.innerHTML = `<button data-i="-1" class="${state.inst < 0 ? 'on' : ''}">All three</button>` +
    I.map((n, i) => `<button data-i="${i}" title="${n}" class="${state.inst === i ? 'on' : ''}"><span class="dot" style="background:${instColor(i)}"></span>${SHORT[i]}</button>`).join('');
  seg.querySelectorAll('button').forEach(b => b.onclick = () => setInst(+b.dataset.i));
}
function setInst(i) {
  state.inst = i; buildInstSeg();
  document.dispatchEvent(new CustomEvent('atlas:inst', { detail: i }));
  ['overview', 'pubs', 'faculty', 'papers', 'citnet', 'collab', 'reach', 'flows'].forEach(t => state.dirty.add(t));
  renderTab(state.tab, true);
}
$('#themeBtn').onclick = () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('atlas-theme', root.dataset.theme); } catch (e) {}
  buildInstSeg(); Object.keys(RENDER).forEach(t => state.dirty.add(t)); renderTab(state.tab, true);
};
try { const t = localStorage.getItem('atlas-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) {}

const searchIdx = { fac: F.map((f, i) => [f.n.toLowerCase(), i]), pap: P.map((p, i) => [p[T.title].toLowerCase(), i]) };
let resSel = 0, resItems = [];
$('#q').addEventListener('input', e => {
  const q = e.target.value.trim().toLowerCase(), box = $('#results');
  if (q.length < 2) { box.classList.remove('show'); return; }
  const fs = searchIdx.fac.filter(([n]) => n.includes(q)).slice(0, 7).map(([, i]) => i);
  const ps = searchIdx.pap.filter(([n]) => n.includes(q)).map(([, i]) => i).sort((a, b) => P[b][T.cites] - P[a][T.cites]).slice(0, 8);
  resItems = [...fs.map(i => ['f', i]), ...ps.map(i => ['p', i])]; resSel = 0;
  box.innerHTML = (fs.length ? `<div class="grp">Faculty</div>` + fs.map((i, k) => `<div class="it" data-k="${k}"><span class="dot" style="background:${instColor(F[i].i)}"></span><span>${esc(F[i].n)}</span><small>${esc(F[i].d)} · h ${F[i].h}</small></div>`).join('') : '') +
    (ps.length ? `<div class="grp">Papers</div>` + ps.map((i, k) => `<div class="it" data-k="${fs.length + k}"><span>${esc(P[i][T.title])}</span><small>${P[i][T.year]} · ${fmt(P[i][T.cites])} cites</small></div>`).join('') : '') ||
    `<div class="note" style="padding:10px">No matches.</div>`;
  box.classList.add('show'); markSel();
  box.querySelectorAll('.it').forEach(it => it.onmousedown = () => pickRes(+it.dataset.k));
});
function markSel() { $('#results').querySelectorAll('.it').forEach(it => it.classList.toggle('act', +it.dataset.k === resSel)); }
function pickRes(k) { const [t, i] = resItems[k] || []; if (t === 'f') openFaculty(i); else if (t === 'p') openPaper(i); $('#results').classList.remove('show'); $('#q').blur(); }
$('#q').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown') { resSel = Math.min(resItems.length - 1, resSel + 1); markSel(); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { resSel = Math.max(0, resSel - 1); markSel(); e.preventDefault(); }
  else if (e.key === 'Enter') pickRes(resSel);
  else if (e.key === 'Escape') { $('#results').classList.remove('show'); e.target.blur(); }
});
$('#q').addEventListener('blur', () => setTimeout(() => $('#results').classList.remove('show'), 150));
document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); $('#q').focus(); }
  if (e.key === 'Escape' && $('#drawer').classList.contains('on')) closeDrawer();
});

// ---------------------------------------------------------------- navigation
document.querySelectorAll('#nav button').forEach(b => b.onclick = () => go(b.dataset.tab));
function go(tab) {
  state.tab = tab;
  document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  document.querySelectorAll('section.tab').forEach(s => s.classList.toggle('on', s.id === 'tab-' + tab));
  window.scrollTo({ top: 0 });
  renderTab(tab);
  try { history.replaceState(null, '', '#' + tab); } catch (e) {}
  document.dispatchEvent(new CustomEvent('atlas:tab', { detail: tab }));
}
const rendered = new Set();
function renderTab(tab, force) {
  if (!rendered.has(tab) || state.dirty.has(tab) || force && state.dirty.has(tab)) {
    rendered.add(tab); state.dirty.delete(tab); RENDER[tab]();
  }
  // plotly charts inside hidden tabs need a resize when shown
  requestAnimationFrame(() => document.querySelectorAll(`#tab-${tab} .js-plotly-plot`).forEach(el => Plotly.Plots.resize(el)));
}

// ---------------------------------------------------------------- drawer
function showDrawer(html, crumb, entry) {
  $('#drBody').innerHTML = html; $('#drCrumb').textContent = crumb;
  $('#drawer').classList.add('on'); $('#scrim').classList.add('on');
  $('#drBody').scrollTop = 0;
  if (entry) { state.history.push(entry); }
  $('#drBack').style.visibility = state.history.length > 1 ? 'visible' : 'hidden';
  $('#drBody').querySelectorAll('[data-f]').forEach(e => e.onclick = ev => { ev.stopPropagation(); openFaculty(+e.dataset.f); });
  $('#drBody').querySelectorAll('[data-p]').forEach(e => e.onclick = ev => { if (ev.target.tagName === 'A') return; openPaper(+e.dataset.p); });
  $('#drBody').querySelectorAll('[data-i]').forEach(e => e.onclick = ev => { ev.stopPropagation(); openPartner(e.dataset.i); });
}
function closeDrawer() { $('#drawer').classList.remove('on'); $('#scrim').classList.remove('on'); state.history = []; }
$('#drClose').onclick = closeDrawer; $('#scrim').onclick = closeDrawer;
$('#drBack').onclick = () => { state.history.pop(); const e = state.history.pop(); if (e) ({ f: openFaculty, p: openPaper, i: openPartner, x: openForeign, t: openTypeDrawer, s: openSharedDrawer })[e[0]](e[1]); };

function paperRow(p, extra = '') {
  const x = P[p];
  return `<div class="pi" data-p="${p}"><div class="pt">${esc(x[T.title])}</div><div class="pm">${qChip(x[T.q])}<span>${esc(x[T.venue] || '—')}</span><span>· ${x[T.year]}</span><span>· <b class="num">${fmt(x[T.cites])}</b> cites</span>${extra}${doiLink(x[T.doi])}</div></div>`;
}

function openFaculty(fi) {
  const f = F[fi], ps = facPapers[fi].slice().sort((a, b) => P[b][T.cites] - P[a][T.cites]);
  const initials = f.n.split(/\s+/).filter(w => /^[A-Za-z]/.test(w)).slice(0, 2).map(w => w[0].toUpperCase()).join('');
  const peers = F.filter(g => g.i === f.i).length;
  const qc = d3.rollup(ps.filter(p => P[p][T.type] === 0), v => v.length, p => P[p][T.q]);
  const collab = adj[fi];
  const html = `
    <div style="display:flex;gap:14px;align-items:center">
      <div class="avatar" style="background:linear-gradient(135deg, ${instColor(f.i)}, var(--brand1))">${esc(initials)}</div>
      <div><h3 style="margin:0">${esc(f.n)}</h3><div class="note">${esc(f.des || 'Faculty')} · ${esc(f.d)}</div></div>
    </div>
    <div class="chips" style="margin-top:12px">${instChip(f.i)}<span class="chip">${f.s === 'former' ? 'Former faculty' : 'Current faculty'}</span>${f.fy ? `<span class="chip">Active ${f.fy}–${f.ly}</span>` : ''}${f.lv >= 0 && collab.length ? `<span class="chip click" id="drComm">Louvain community ${f.lv}</span>` : ''}</div>
    <h4>Performance (2016–2026 papers)</h4>
    <div class="stats">
      <div class="stat"><div class="v num">${f.h}</div><div class="l">h-index · #${f.rh} of ${peers}</div></div>
      <div class="stat"><div class="v num">${fmt(f.p)}</div><div class="l">papers · #${f.rp}</div></div>
      <div class="stat"><div class="v num">${fmt(f.c)}</div><div class="l">citations · #${f.rc}</div></div>
      <div class="stat"><div class="v num">${f.q1 ?? '—'}%</div><div class="l">journal papers in Q1</div></div>
      <div class="stat"><div class="v num">${f.cpp ?? '—'}</div><div class="l">citations / paper</div></div>
      <div class="stat"><div class="v num">${f.jp} / ${f.cp}</div><div class="l">journal / conference</div></div>
    </div>
    <div class="chips" style="margin-top:10px">${['Q1', 'Q2', 'Q3', 'Q4'].map(q => `<span class="chip">${qChip(q)} ${qc.get(q) || 0}</span>`).join('')}<span class="chip">Q1 &amp; IF&gt;5: ${f.q5}</span></div>
    <div class="note" style="margin-top:8px">Most frequent journal: <b style="color:var(--ink)">${esc(f.tj || '—')}</b>${f.tjp ? ` (${f.tjp} papers)` : ''}</div>
    <h4>Papers per year</h4><div id="drYear" style="height:150px"></div>
    <h4>Position in the collaboration network</h4>
    <div class="stats">
      <div class="stat"><div class="v num">${f.deg}</div><div class="l">faculty collaborators</div></div>
      <div class="stat"><div class="v num">${f.str}</div><div class="l">joint papers (strength)</div></div>
      <div class="stat"><div class="v num">${fmt3(f.btw)}</div><div class="l">betweenness</div></div>
      <div class="stat"><div class="v num">${fmt3(f.clo)}</div><div class="l">closeness</div></div>
      <div class="stat"><div class="v num">${fmt3(f.eig)}</div><div class="l">eigenvector</div></div>
      <div class="stat"><div class="v num">${f.kc}</div><div class="l">k-core</div></div>
    </div>
    <div class="note" style="margin-top:8px">${f.xd} collaborators in other departments · ${f.xi} at the other two institutes · clustering ${fmt2(f.clu)} · ${f.ext ?? '—'}% of papers have a co-author outside the three institutes</div>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">${collab.length ? `<button class="btn primary" id="drLocate">Show in collaboration network →</button>` : `<span class="note">No co-authored papers with other faculty in the data.</span>`}</div>
    ${L && L.facWO[fi] ? `<h4>Within vs outside the institute</h4><div class="stats">
      <div class="stat"><div class="v num">${L.facWO[fi][0]}</div><div class="l">co-authors, same institute</div></div>
      <div class="stat"><div class="v num">${L.facWO[fi][2]}</div><div class="l">co-authors elsewhere in India</div></div>
      <div class="stat"><div class="v num">${L.facWO[fi][3]}</div><div class="l">co-authors abroad</div></div></div>
      <div class="note" style="margin-top:6px">${L.facWO[fi][1]} co-authors at the other two institutes institutes · betweenness in the full author network ${L.facWO[fi][6].toFixed(4)}</div>` : ''}
    ${L && L.facPartners[fi] ? `<h4>Top partner institutes</h4><div class="chips">${L.facPartners[fi].map(([p, c, cl]) => `<span class="chip click" data-i="${esc(p)}"><span class="dot" style="background:${clColor(cl)}"></span>${esc(p)} · ${c}</span>`).join('')}</div>` : ''}
    ${collab.length ? `<h4>Faculty collaborators (${collab.length})</h4><div class="chips">${collab.map(([g, w]) => `<span class="chip click" data-f="${g}"><span class="dot" style="background:${instColor(F[g].i)}"></span>${esc(F[g].n)} · ${w}</span>`).join('')}</div>` : ''}
    <h4>Papers (${ps.length}) · most cited first</h4>
    <div class="plist" id="drPapers">${ps.slice(0, 12).map(p => paperRow(p)).join('')}</div>
    ${ps.length > 12 ? `<button class="btn" id="drMore" style="margin-top:10px">Show all ${ps.length} papers</button>` : ''}`;
  showDrawer(html, `${I[f.i]} · Faculty`, ['f', fi]);
  const yc = d3.rollup(ps, v => v.length, p => P[p][T.year]);
  Plotly.react('drYear', [{ type: 'bar', x: YEARS, y: YEARS.map(y => yc.get(y) || 0), marker: { color: instColor(f.i) }, hovertemplate: '%{x}: %{y} papers<extra></extra>' }],
    baseLayout({ margin: { l: 30, r: 6, t: 4, b: 24 }, xaxis: { dtick: 2 }, bargap: .25 }), { displayModeBar: false, responsive: true });
  $('#drMore') && ($('#drMore').onclick = () => { $('#drPapers').innerHTML = ps.map(p => paperRow(p)).join(''); $('#drMore').remove(); $('#drPapers').querySelectorAll('[data-p]').forEach(e => e.onclick = ev => { if (ev.target.tagName !== 'A') openPaper(+e.dataset.p); }); });
  $('#drLocate') && ($('#drLocate').onclick = () => { closeDrawer(); focusFaculty(fi); });
  $('#drComm') && ($('#drComm').onclick = () => { closeDrawer(); focusCommunity(f.lv); });
}

// Journal impact: SCImago citations/doc vs OpenAlex 2-year mean citedness. The IF flag uses the lower one.
function ifNote(x) {
  const s = x[T.ifS], o = x[T.ifO];
  if (x[T.type] || (s == null && o == null)) return '';
  const f = v => v == null ? 'n/a' : (+v).toFixed(2);
  const off = s != null && o != null && [5, 10].some(t => (s > t) !== (o > t));
  return `<div class="note">Journal impact: SCImago cites/doc ${f(s)} · OpenAlex 2-year citedness ${f(o)}${off ? ' · <b>sources disagree, the lower value is used for the IF flag</b>' : ''}</div>`;
}

function openPaper(pi) {
  const x = P[pi], fs = D.pfac[pi], out = citesOut[pi], inn = citesIn[pi];
  const sortC = a => a.slice().sort((p, q) => P[q][T.cites] - P[p][T.cites]);
  const html = `
    <div class="chips">${instNames(x[T.mask]).map(instChip).join('')}<span class="chip">${x[T.type] ? 'Conference' : 'Journal'}</span>${qChip(x[T.q])}${x[T.iff] ? `<span class="chip">Q1 · IF &gt; ${x[T.iff] === 2 ? 10 : 5}</span>` : ''}${x[T.multi] ? '<span class="chip">&gt;10 authors</span>' : ''}</div>
    <h3>${esc(x[T.title])}</h3>
    <div class="note">${esc(x[T.venue] || '—')} · ${x[T.year]} · ${esc(x[T.field])}</div>
    ${ifNote(x)}
    ${x[T.nauth] ? `<div class="note">${x[T.nauth]} author${x[T.nauth] > 1 ? 's' : ''} · ${x[T.ninst]} institution${x[T.ninst] === 1 ? '' : 's'} · ${x[T.ncty]} countr${x[T.ncty] === 1 ? 'y' : 'ies'}${x[T.fwci] != null ? ` · FWCI ${(+x[T.fwci]).toFixed(2)}` : ''}</div>` : ''}
    <div style="margin-top:10px">${x[T.doi] ? `<a class="btn" href="${esc(x[T.doi])}" target="_blank" rel="noopener">Open DOI ↗</a>` : '<span class="note">No DOI</span>'}</div>
    <h4>Impact</h4>
    <div class="stats">
      <div class="stat"><div class="v num">${fmt(x[T.cites])}</div><div class="l">citations (OpenAlex)</div></div>
      <div class="stat"><div class="v num">${x[T.indeg]}</div><div class="l">cited by the institutes’ papers${x[T.inSelf] ? ` (${x[T.inSelf]} self)` : ''}</div></div>
      <div class="stat"><div class="v num">${fmt(x[T.nref] || 0)}</div><div class="l">references (all, OpenAlex)</div></div>
      <div class="stat"><div class="v num">${x[T.outdeg]}</div><div class="l">of them in our corpus</div></div>
      <div class="stat"><div class="v num">#${fmt(prRank[pi])}</div><div class="l">within-corpus PageRank of ${fmt(P.length)}</div></div>
      ${x[T.prYear] != null ? `<div class="stat"><div class="v num">#${fmt(x[T.prYear])}</div><div class="l">PageRank among ${x[T.year]} papers</div></div>` : ''}
      <div class="stat"><div class="v num">${x[T.pr] ? fmt2(x[T.pr]) : '—'}</div><div class="l">PageRank ×10⁶</div></div>
      <div class="stat"><div class="v num">${x[T.inh]}</div><div class="l">in-degree h-index</div></div>
    </div>
    <h4>Faculty authors (${fs.length})</h4>
    <div class="chips">${fs.map(f => `<span class="chip click" data-f="${f}"><span class="dot" style="background:${instColor(F[f].i)}"></span>${esc(F[f].n)} · h ${F[f].h}</span>`).join('') || '<span class="note">—</span>'}</div>
    ${(inn.length || out.length) ? `<div style="margin-top:14px"><button class="btn primary" id="drCit">Show its citation network →</button></div>` : ''}
    ${inn.length ? `<h4>Cited by (in corpus, ${inn.length})</h4><div class="plist">${sortC(inn).slice(0, 15).map(p => paperRow(p)).join('')}</div>` : ''}
    ${out.length ? `<h4>Cites (in corpus, ${out.length})</h4><div class="plist">${sortC(out).slice(0, 15).map(p => paperRow(p)).join('')}</div>` : ''}`;
  showDrawer(html, 'Paper', ['p', pi]);
  $('#drCit') && ($('#drCit').onclick = () => { closeDrawer(); focusPaper(pi); });
}

// ================================================================ YEAR RANGE + PER-RANGE STATS
const S = Object.fromEntries(D.summary.map(r => [r.institution, r]));
const yr = { from: 2016, to: 2026 };
const fullYears = () => yr.from === 2016 && yr.to === 2026;
const inYears = x => x[T.year] >= yr.from && x[T.year] <= yr.to;
const pIn = x => inInst(x[T.mask]) && inYears(x);
const RY = () => d3.range(yr.from, yr.to + 1);
const yrLabel = () => yr.from === yr.to ? String(yr.from) : `${yr.from}–${yr.to}`;
const sumYears = arr => RY().reduce((a, y) => a + (arr[y - 2016] || 0), 0);
const facCache = new Map(), instCache = new Map();
function setYears(a, b) {
  yr.from = Math.min(a, b); yr.to = Math.max(a, b); facCache.clear(); instCache.clear();
  buildYearCtl(); markAllYears();
  Object.keys(RENDER).forEach(t => state.dirty.add(t)); renderTab(state.tab, true);
  document.dispatchEvent(new CustomEvent('atlas:toast', { detail: fullYears() ? 'Showing all years, 2016–2026' : `Showing papers from ${yrLabel()}` }));
}
function buildYearCtl() {
  const host = $('#yearCtl'); if (!host) return;
  const opts = sel => YEARS.map(y => `<option value="${y}"${y === sel ? ' selected' : ''}>${y}</option>`).join('');
  host.innerHTML = `<select id="yrFrom" aria-label="From year">${opts(yr.from)}</select><span class="yr-dash">to</span><select id="yrTo" aria-label="To year">${opts(yr.to)}</select>${fullYears() ? '' : '<button class="yr-x" id="yrAll" title="Back to all years">✕</button>'}`;
  $('#yrFrom').onchange = e => setYears(+e.target.value, yr.to);
  $('#yrTo').onchange = e => setYears(yr.from, +e.target.value);
  $('#yrAll') && ($('#yrAll').onclick = () => setYears(2016, 2026));
}
// panels whose numbers are pre-computed for the whole period do not follow the year range: say so
const ALLYEAR_PANELS = ['pp-t30chart', 'pp-t30', 'pp-hyper', 'fc-dept', 'cn-top', 'cn-flow', 'cn-macro', 'fn-wrap', 'fn-comms', 'fn-brokers', 'fn-bridges', 'fn-metrics',
  'rc-scatter', 'rc-topfac', 'rc-ext', 'rc-inst', 'rc-cit', 'rc-citpapers', 'fl-ratio', 'fl-vel', 'fl-cluster', 'fl-in', 'fl-out', 'fl-partners', 'fl-types', 'fl-jac', 'md-funnel', 'md-qsrc'];
function markAllYears() {
  ALLYEAR_PANELS.forEach(id => {
    const head = document.getElementById(id)?.closest('.card')?.querySelector('.card-h > div'); if (!head) return;
    let b = head.querySelector('.allyears');
    if (fullYears()) { b?.remove(); return; }
    if (!b) { b = document.createElement('span'); b.className = 'allyears'; head.querySelector('h2')?.after(b); }
    b.textContent = 'All years · not filtered';
  });
}
const hIdx = cs => { cs = cs.slice().sort((a, b) => b - a); let h = 0; while (h < cs.length && cs[h] >= h + 1) h++; return h; };
// faculty numbers for the current year range (the pre-computed values when the range is 2016-2026)
function fs(fi) {
  const f = F[fi]; if (fullYears()) return f;
  if (facCache.has(fi)) return facCache.get(fi);
  const ps = facPapers[fi].filter(p => inYears(P[p])), js = ps.filter(p => P[p][T.type] === 0), cs = ps.map(p => P[p][T.cites]);
  const q1p = js.filter(p => P[p][T.q] === 'Q1').length, c = d3.sum(cs);
  const tj = d3.rollups(js, v => v.length, p => P[p][T.venue]).sort((a, b) => b[1] - a[1])[0];
  const o = { ...f, p: ps.length, jp: js.length, cp: ps.length - js.length, c, h: hIdx(cs), q1p, q1: js.length ? +(100 * q1p / js.length).toFixed(1) : null,
    cpp: ps.length ? +(c / ps.length).toFixed(1) : null, q5: js.filter(p => P[p][T.iff] >= 1).length, tj: tj ? tj[0] : '', tjp: tj ? tj[1] : 0 };
  facCache.set(fi, o); return o;
}
// institute numbers for the current year range (the official summary table when the range is 2016-2026)
function iStat(i) {
  if (instCache.has(i)) return instCache.get(i);
  const s = S[I[i]];
  let o;
  if (fullYears()) o = { papers: +s.papers, jp: +s.journal_papers, cp: +s.conference_papers, cites: +s.total_citations, fac: F.filter(f => f.i === i && f.p > 0).length,
    h: +s.institute_h_index, q1: +s['journal_Q1_%'], if5: +s.Q1_and_IF_gt5, if10: +s.Q1_and_IF_gt10 };
  else {
    const ps = P.filter(x => (x[T.mask] & (1 << i)) && inYears(x)), js = ps.filter(x => x[T.type] === 0), jq = js.filter(x => /^Q[1-4]$/.test(x[T.q]));
    o = { papers: ps.length, jp: js.length, cp: ps.length - js.length, cites: d3.sum(ps, x => x[T.cites]), fac: F.filter((f, k) => f.i === i && fs(k).p > 0).length,
      h: hIdx(ps.map(x => x[T.cites])), q1: jq.length ? +(100 * jq.filter(x => x[T.q] === 'Q1').length / jq.length).toFixed(1) : 0,
      if5: js.filter(x => x[T.iff] >= 1).length, if10: js.filter(x => x[T.iff] === 2).length };
  }
  o.cpp = o.papers ? +(o.cites / o.papers).toFixed(2) : 0;
  instCache.set(i, o); return o;
}
// papers per institute per year (a paper counts for each of our institutes on it)
const PPY = [0, 1, 2].map(i => { const m = {}; P.forEach(x => { if (x[T.mask] & (1 << i)) m[x[T.year]] = (m[x[T.year]] || 0) + 1; }); return m; });

// ================================================================ OVERVIEW
function renderOverview() {
  const sh = instsShown(), st = sh.map(iStat), all = [0, 1, 2].map(iStat);
  const uniq = P.filter(pIn).length;
  $('#heroLede').innerHTML = state.inst < 0
    ? `MANIT Bhopal, NIT Jamshedpur and NIT Silchar together: <b>${fmt(uniq)}</b> distinct papers${fullYears() ? '' : ` from ${yrLabel()}`} by <b>${fmt(F.length)}</b> verified faculty, <b>${fmt(D.cedges.length)}</b> citation links and <b>${fmt(D.fedges.length)}</b> co-authorship ties.`
    : `${I[state.inst]}: <b>${fmt(uniq)}</b> papers${fullYears() ? '' : ` from ${yrLabel()}`} by <b>${fmt(st[0].fac)}</b> faculty, institute h-index <b>${st[0].h}</b>.`;
  const silo = D.citNet.per_institute_outgoing_share;
  const top = (f) => I.map((n, k) => [k, +f(n)]).filter(x => !isNaN(x[1])).sort((a, b) => b[1] - a[1])[0][0];
  const kPub = top(n => S[n].papers), kImp = top(n => S[n].citations_per_paper), kGro = top(n => D.pub['growth_2016_to_2025_cagr_%'][n]);
  const sameShare = I.map(n => +silo[n]['to_same_inst_%']), selfLink = e => F[e[0]].n === F[e[1]].n;
  const crossN = D.fedges.filter(e => F[e[0]].i !== F[e[1]].i && !selfLink(e)).length;
  const ins = [
    ['pubs', `${I[kPub]} publishes the most`, `${fmt(+S[I[kPub]].papers)} papers; Q1 share of its ranked journal papers ${S[I[kPub]]['journal_Q1_%']}%.`],
    ['papers', `${I[kImp]} has the most impact per paper`, `${S[I[kImp]].citations_per_paper} citations per paper; institute h-index ${S[I[kImp]].institute_h_index}.`],
    ['pubs', `${I[kGro]} grows fastest`, `${D.pub['growth_2016_to_2025_cagr_%'][I[kGro]]}% a year in papers (CAGR 2016→2025).`],
    ['citnet', 'Citations stay at home', `${fmt1(Math.min(...sameShare))}–${fmt1(Math.max(...sameShare))}% of in-corpus citations point to the same institute.`],
    ['reach', 'Three islands', `Only ${crossN} of ${fmt(D.fedges.filter(e => !selfLink(e)).length)} faculty links cross the three institutes; each works mostly with other NITs, IITs and universities.`],
    ['flows', 'Net importers of citations', `In/out ratio with other Indian institutes: ${I.map((n, k) => `${SHORT[k]} ${S[n].in_over_out_ratio}`).join(' · ')}. ${I.every(i => +S[i].in_over_out_ratio < 1) ? 'All below 1.' : ''}`],
  ];
  $('#insights').innerHTML = ins.map(([t, b, s]) => `<div class="ins" data-t="${t}"><span class="go">→</span><b>${b}</b>${s}</div>`).join('');
  $('#insights').querySelectorAll('.ins').forEach(e => e.onclick = () => go(e.dataset.t));

  const bars = (vals, f = fmt) => { const mx = d3.max(vals) || 1; return `<div class="bars">${[0, 1, 2].map(i => `<div class="bar" style="opacity:${sh.includes(i) ? 1 : .35}"><span>${SHORT[i]}</span><i style="width:${(vals[i] / mx * 100).toFixed(1)}%;background:${instColor(i)}"></i><span class="num">${f(vals[i])}</span></div>`).join('')}</div>`; };
  const tot = k => d3.sum(st, s => s[k]);
  const q1 = d3.sum(st, s => s.q1 * s.jp) / (tot('jp') || 1);
  const k = [
    ['Papers', fmt(uniq), state.inst < 0 ? `distinct papers, ${yrLabel()}` : `${fmt(st[0].jp)} journal · ${fmt(st[0].cp)} conference`, bars(all.map(s => s.papers))],
    ['Citations', fmt(state.inst < 0 ? d3.sum(P.filter(pIn), x => x[T.cites]) : tot('cites')), `${fmt1((state.inst < 0 ? d3.sum(P.filter(pIn), x => x[T.cites]) : tot('cites')) / ((state.inst < 0 ? uniq : tot('papers')) || 1))} per paper`, bars(all.map(s => s.cites), d3.format('.3s'))],
    ['Faculty with papers', fmt(tot('fac')), 'current + former, verified', bars(all.map(s => s.fac))],
    ['Institute h-index', state.inst < 0 ? d3.max(st, s => s.h) : st[0].h, state.inst < 0 ? 'highest of the three' : 'from all its papers', bars(all.map(s => s.h))],
    ['Journal Q1 share', fmt1(q1) + '%', `${fmt(tot('if5'))} Q1 papers with IF > 5`, bars(all.map(s => s.q1), d => d + '%')],
  ];
  $('#kpis').innerHTML = k.map(([l, v, s, b]) => `<div class="card kpi"><div class="lab">${l}</div><div class="val num">${v}</div><div class="sub">${s}</div>${b}</div>`).join('');

  trendChart('ov-trend', 'line');
  quartileChart('ov-q', 'bar');

  const rows = [0, 1, 2].map(i => ({ institution: I[i], ...iStat(i), ratio: +S[I[i]].in_over_out_ratio }));
  const cols = [['papers', 'Papers', fmt], ['cites', 'Citations', fmt], ['cpp', 'Cites/paper', fmt2], ['h', 'Inst. h', String], ['fac', 'Faculty', String],
    ['q1', 'Q1 %', String], ['if5', 'Q1·IF>5', fmt], ['if10', 'Q1·IF>10', fmt], ['ratio', 'In/out (all years)', String]];
  makeTable($('#ov-table'), {
    rows: () => rows, pageSize: 5,
    columns: [{ key: 'institution', label: 'Institute', v: r => r.institution, html: r => `<span class="dot" style="background:${instColor(I.indexOf(r.institution))}"></span> <b>${esc(r.institution)}</b>` },
      ...cols.map(([k, l, f]) => ({ key: k, label: l, num: 1, v: r => r[k], html: r => f(r[k]) }))],
    onRow: r => setInst(I.indexOf(r.institution)),
  });
}

function trendChart(id, mode) {
  const sh = instsShown(), ys = RY(), traces = [];
  const ax = { xaxis: { dtick: 1, title: { text: 'Year' } }, yaxis: { rangemode: 'tozero', title: { text: 'Papers' } } };
  if (mode === 'stack') {
    const by = d3.rollup(P.filter(pIn), v => v.length, x => x[T.type], x => x[T.year]);
    [['Journal', 0, '--c1'], ['Conference', 1, '--c4']].forEach(([n, t, c]) => traces.push({ type: 'bar', name: n, x: ys, y: ys.map(y => by.get(t)?.get(y) || 0), marker: { color: css(c), line: { color: css('--surface'), width: 1 } }, hovertemplate: `%{x}: %{y:,} ${n.toLowerCase()} papers<extra></extra>`, meta: t }));
    plot(id, traces, { barmode: 'stack', bargap: .3, ...ax }, ev => explorer({ year: ev.points[0].x, type: ev.points[0].data.meta }));
    return;
  }
  sh.forEach(i => {
    const c = instColor(i), full = ys.filter(y => y <= 2025), part = yr.to === 2026 ? ys.filter(y => y >= Math.max(2025, yr.from)) : [];
    if (full.length) traces.push({ type: 'scatter', mode: 'lines+markers', name: I[i], x: full, y: full.map(y => PPY[i][y] || 0), line: { color: c, width: 2.5, shape: 'spline', smoothing: .4 }, marker: { size: 8, color: c, line: { color: css('--surface'), width: 2 } }, hovertemplate: `${SHORT[i]} %{x}: %{y:,} papers<extra></extra>`, meta: i });
    if (part.length) traces.push({ type: 'scatter', mode: 'lines+markers', name: full.length ? I[i] + ' (2026, partial)' : I[i], showlegend: !full.length, x: part, y: part.map(y => PPY[i][y] || 0), line: { color: c, width: 2, dash: 'dot' }, marker: { size: 8, color: c, symbol: 'circle-open' }, hovertemplate: `${SHORT[i]} %{x}: %{y:,} papers (2026 is partial)<extra></extra>`, meta: i });
  });
  plot(id, traces, { hovermode: 'closest', ...ax }, ev => explorer({ year: ev.points[0].x, inst: ev.points[0].data.meta }));
}

const QS = ['Q1', 'Q2', 'Q3', 'Q4'];
function qCounts(i, type) { const c = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 }; P.forEach(x => { if ((x[T.mask] & (1 << i)) && x[T.type] === type && inYears(x) && c[x[T.q]] != null) c[x[T.q]]++; }); return c; }
function quartileChart(id, mode) {
  const sh = instsShown(), cnt = sh.map(i => qCounts(i, 0)), tot = cnt.map(c => d3.sum(QS, q => c[q]) || 1);
  if (mode === 'pie') {
    const traces = sh.map((i, k) => ({
      type: 'pie', hole: .6, sort: false, direction: 'clockwise', labels: QS, values: QS.map(q => cnt[k][q]),
      marker: { colors: QS.map(q => css('--' + q.toLowerCase())), line: { color: css('--surface'), width: 2 } },
      domain: { column: k }, title: { text: SHORT[i], font: { size: 13, color: css('--ink') } }, textinfo: 'percent', textfont: { size: 11 },
      hovertemplate: `${SHORT[i]} %{label}: %{value:,} journal papers (%{percent})<extra></extra>`, name: I[i], meta: i,
    }));
    plot(id, traces, { grid: { rows: 1, columns: sh.length }, showlegend: true, margin: { l: 10, r: 10, t: 30, b: 10 } }, ev => explorer({ q: ev.points[0].label, inst: ev.points[0].data.meta, type: 0 }));
    return;
  }
  const traces = QS.map(q => ({
    type: 'bar', orientation: 'h', name: q, y: sh.map(i => SHORT[i]), x: sh.map((i, k) => +(100 * cnt[k][q] / tot[k]).toFixed(1)), customdata: sh.map((i, k) => cnt[k][q]),
    marker: { color: css('--' + q.toLowerCase()), line: { color: css('--surface'), width: 2 } },
    text: sh.map((i, k) => 100 * cnt[k][q] / tot[k] >= 8 ? (100 * cnt[k][q] / tot[k]).toFixed(1) + '%' : ''), textposition: 'inside', insidetextanchor: 'middle',
    textfont: { color: q === 'Q4' || q === 'Q3' ? css('--ink') : css('--surface'), size: 11 },
    hovertemplate: `%{y} ${q}: %{x}% (%{customdata:,} journal papers)<extra></extra>`,
  }));
  plot(id, traces, { barmode: 'stack', bargap: .35, legend: { orientation: 'h', y: 1.14, x: 0, traceorder: 'normal' }, xaxis: { ticksuffix: '%', range: [0, 100], title: { text: '% of journal papers with a quartile' } }, yaxis: { autorange: 'reversed' }, margin: { l: 52, r: 10, b: 40 } },
    ev => explorer({ q: ev.points[0].data.name, inst: SHORT.indexOf(ev.points[0].y), type: 0 }));
}

// ================================================================ PUBLICATIONS
function segBind(id, cb) { document.querySelectorAll(`#${id} button`).forEach(b => b.onclick = () => { document.querySelectorAll(`#${id} button`).forEach(x => x.classList.toggle('on', x === b)); cb(b.dataset.v); }); }
const segVal = id => document.querySelector(`#${id} button.on`).dataset.v;
// book series / proceedings volumes that collect many conferences (not a single conference)
const SERIES = /^(lecture notes|materials today|aip conference|advances in |communications in computer|smart innovation|procedia|iop conference|journal of physics|springer|learning and analytics|algorithms for intelligent|sae technical|structural integrity|proceedings of the institution|proceedings of the national academy|studies in |unknown venue)/i;
const confName = v => String(v || '').replace(/^(19|20)\d{2}\s+/, '').replace(/^\d+(st|nd|rd|th)\s+/i, '').replace(/\s+(19|20)\d{2}$/, '').trim();
const CR = [['CORE A*', q => q === 'A*', '--c8'], ['CORE A', q => q === 'A', '--c2'], ['CORE B', q => q === 'B', '--c4'], ['CORE C', q => q === 'C', '--c5'],
  ['Scopus Q1', q => q === 'Q1', '--q1'], ['Scopus Q2', q => q === 'Q2', '--q2'], ['Scopus Q3', q => q === 'Q3', '--q3'], ['Scopus Q4', q => q === 'Q4', '--q4'],
  ['Not ranked', q => !/^(Q[1-4]|A\*|A|B|C)$/.test(q), '--qu']];
function renderPubs() {
  const sh = instsShown();
  trendChart('pb-trend', segVal('trendMode'));
  segBind('trendMode', v => trendChart('pb-trend', v));
  quartileChart('pb-q', segVal('qMode'));
  segBind('qMode', v => quartileChart('pb-q', v));

  const q1y = sh.map(i => { const m = {}; P.forEach(x => { if ((x[T.mask] & (1 << i)) && x[T.type] === 0 && /^Q[1-4]$/.test(x[T.q]) && inYears(x)) { const o = m[x[T.year]] || (m[x[T.year]] = [0, 0]); o[1]++; if (x[T.q] === 'Q1') o[0]++; } }); return m; });
  plot('pb-q1y', sh.map((i, k) => ({ type: 'scatter', mode: 'lines+markers', name: I[i], x: RY(), y: RY().map(y => q1y[k][y] ? +(100 * q1y[k][y][0] / q1y[k][y][1]).toFixed(1) : null),
    customdata: RY().map(y => q1y[k][y] ? q1y[k][y] : [0, 0]),
    line: { color: instColor(i), width: 2.5 }, marker: { size: 8, color: instColor(i), line: { color: css('--surface'), width: 2 } }, hovertemplate: `${SHORT[i]} %{x}: %{y}% Q1 (%{customdata[0]} of %{customdata[1]} journal papers)<extra></extra>`, meta: i })),
    { yaxis: { ticksuffix: '%', rangemode: 'tozero', title: { text: 'Q1 share of journal papers' } }, xaxis: { dtick: 1, title: { text: 'Year' } } }, ev => explorer({ year: ev.points[0].x, inst: ev.points[0].data.meta, q: 'Q1', type: 0 }));

  // conference papers by venue rank: CORE rank where the venue is CORE-listed, otherwise the Scopus quartile of the proceedings
  const confs = sh.map(i => P.filter(x => (x[T.mask] & (1 << i)) && x[T.type] === 1 && inYears(x)));
  const crc = confs.map(ps => CR.map(([, f]) => ps.filter(x => f(x[T.q])).length));
  plot('pb-conf', CR.map(([n, , c], k) => ({ type: 'bar', orientation: 'h', name: n, y: sh.map(i => SHORT[i]), x: sh.map((i, j) => confs[j].length ? +(100 * crc[j][k] / confs[j].length).toFixed(2) : 0),
    customdata: sh.map((i, j) => crc[j][k]), marker: { color: css(c), line: { color: css('--surface'), width: 1.5 } }, hovertemplate: `%{y} · ${n}: %{customdata:,} conference papers (%{x}%)<extra></extra>`, meta: n }))
    .filter(t => d3.sum(t.customdata) > 0),
    { barmode: 'stack', bargap: .35, xaxis: { ticksuffix: '%', range: [0, 100], title: { text: 'Share of conference papers (%)' } }, yaxis: { autorange: 'reversed' }, legend: { orientation: 'h', y: 1.3, x: 0, traceorder: 'normal' }, margin: { l: 52, r: 10, t: 56, b: 44 } },
    ev => { const n = ev.points[0].data.meta, q = n.startsWith('Scopus') ? n.slice(7) : n.startsWith('CORE') ? n.slice(5) : 'Unranked'; explorer({ type: 1, q, inst: SHORT.indexOf(ev.points[0].y) }); });
  $('#pb-core').innerHTML = `<div class="tbl-wrap" style="margin-top:8px"><table><thead><tr><th>Conference papers</th>${sh.map(i => `<th class="r">${SHORT[i]}</th>`).join('')}</tr></thead><tbody>${
    CR.map(([n], k) => `<tr><td>${n}</td>${sh.map((i, j) => `<td class="r num">${fmt(crc[j][k])}</td>`).join('')}</tr>`).join('')}
    <tr><td><b>Total</b></td>${sh.map((i, j) => `<td class="r num"><b>${fmt(confs[j].length)}</b></td>`).join('')}</tr></tbody></table></div>`;

  // fields
  const ps = P.filter(pIn);
  const fr = d3.rollups(ps, v => ({ n: v.length, c: d3.sum(v, x => x[T.cites]) }), x => x[T.field]).sort((a, b) => b[1].n - a[1].n);
  const top = fr.slice(0, 12).reverse();
  plot('pb-fields', [{ type: 'bar', orientation: 'h', y: top.map(d => d[0]), x: top.map(d => d[1].n), marker: { color: state.inst < 0 ? css('--c7') : instColor(state.inst) },
    text: top.map(d => fmt1(d[1].n / (ps.length || 1) * 100) + '%'), textposition: 'outside', cliponaxis: false, textfont: { color: css('--ink2'), size: 11 },
    hovertemplate: '%{y}: %{x:,} papers<extra></extra>' }], { margin: { l: lm(top.map(d => d[0])), r: 50, t: 4, b: 40 }, bargap: .3, xaxis: { title: { text: 'Papers' } } }, ev => explorer({ field: ev.points[0].y }));
  const fi = fr.filter(d => d[1].n >= 30);
  plot('pb-fieldimpact', [{ type: 'scatter', mode: 'markers+text', x: fi.map(d => d[1].n), y: fi.map(d => d[1].c / d[1].n), text: fi.map(d => d[1].n > ps.length * .03 || d[1].c / d[1].n > 25 ? d[0] : ''),
    textposition: fi.map((d, k) => k % 2 ? 'bottom center' : 'top center'), textfont: { size: 10.5, color: css('--ink2') }, customdata: fi.map(d => d[0]),
    marker: { size: fi.map(d => Math.sqrt(d[1].c) / 6 + 6), color: state.inst < 0 ? css('--c7') : instColor(state.inst), opacity: .7, line: { color: css('--surface'), width: 2 } },
    hovertemplate: '%{customdata}<br>%{x:,} papers · %{y:.1f} citations per paper<extra></extra>' }],
    { xaxis: { type: 'log', title: { text: 'Papers in the field (log scale)' } }, yaxis: { title: { text: 'Mean citations per paper' } } }, ev => explorer({ field: ev.points[0].customdata }));

  // field filter shared by the journal and conference lists
  const fsels = [...document.querySelectorAll('.pbField')], fsel = { get value() { return fsels[0].value; } };
  if (!fsels[0].options.length) fsels.forEach(el => { el.innerHTML = '<option value="">All fields</option>' + fieldCount.map(d => `<option value="${esc(d[0])}">${esc(d[0])} (${fmt(d[1])})</option>`).join(''); el.onchange = () => { fsels.forEach(o => o.value = el.value); drawJournals(); ven(); }; });
  const fieldOK = x => !fsel.value || x[T.field] === fsel.value;
  // journals (top 5 bold, 6-10 faded)
  const jtop = i => { const m = new Map(); P.forEach(x => { if ((x[T.mask] & (1 << i)) && x[T.type] === 0 && inYears(x) && x[T.venue] && fieldOK(x)) { const o = m.get(x[T.venue]) || { n: 0, c: 0, q: {} }; o.n++; o.c += x[T.cites]; o.q[x[T.q]] = (o.q[x[T.q]] || 0) + 1; m.set(x[T.venue], o); } });
    return [...m].sort((a, b) => b[1].n - a[1].n).slice(0, +($('#pbTop')?.value || 10)).map(([name, o]) => ({ name, papers: o.n, citations: o.c, quartile: Object.entries(o.q).sort((a, b) => b[1] - a[1])[0][0] })); };
  const venueCol = (i, list, key) => { const mx = d3.max(list, j => j.papers) || 1; return `<div><div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span class="dot" style="background:${instColor(i)}"></span><b>${I[i]}</b></div>${list.map((j, k) => `
      <div class="jr" data-j="${esc(j.name)}" data-i="${i}" style="cursor:pointer;padding:6px 0;border-bottom:1px solid var(--border);opacity:${k < 5 ? 1 : .55}">
        <div style="display:flex;gap:8px;align-items:baseline"><span class="num note">${k + 1}</span><span style="flex:1">${esc(j.name)}</span>${j.quartile ? qChip(j.quartile) : ''}</div>
        <div style="display:flex;align-items:center;gap:6px;margin-top:3px"><i class="minibar" style="width:${(j.papers / mx * 70).toFixed(0)}%;background:${instColor(i)}"></i><span class="note num">${j.papers} papers · ${fmt(j.citations)} cites</span></div></div>`).join('') || '<p class="note">No papers in this range.</p>'}</div>`; };
  const gridCols = el => { el.style.gridTemplateColumns = sh.length === 1 ? '1fr' : ''; };
  const drawJournals = () => { $('#pb-journals').innerHTML = sh.map(i => venueCol(i, jtop(i))).join(''); gridCols($('#pb-journals'));
    $('#pb-journals').querySelectorAll('.jr').forEach(e => e.onclick = () => explorer({ venue: e.dataset.j, inst: +e.dataset.i, type: 0 })); };
  if ($('#pbTop')) $('#pbTop').onchange = drawJournals;
  drawJournals();

  // conference venues: named conferences vs proceedings series
  const ven = () => {
    const series = segVal('venMode') === 'series';
    $('#pb-vennote').innerHTML = series
      ? 'These are <b>book series and proceedings volumes</b>, such as Springer\'s Lecture Notes or Materials Today: Proceedings. Each volume collects the papers of a different conference, so a series is not a single conference. Most are Scopus-indexed and rank Q3–Q4.'
      : 'These are <b>individual conferences</b>, such as IEEE TENCON or SILCON. Editions from different years are grouped together. Papers that appear only in a proceedings series are under "Proceedings series".';
    const vtop = i => { const m = new Map(); P.forEach(x => { if ((x[T.mask] & (1 << i)) && x[T.type] === 1 && inYears(x) && x[T.venue] && fieldOK(x) && SERIES.test(x[T.venue]) === series) {
      const key = series ? x[T.venue] : confName(x[T.venue]); const o = m.get(key) || { n: 0, c: 0, q: {} }; o.n++; o.c += x[T.cites]; o.q[x[T.q]] = (o.q[x[T.q]] || 0) + 1; m.set(key, o); } });
      return [...m].sort((a, b) => b[1].n - a[1].n).slice(0, 8).map(([name, o]) => ({ name, papers: o.n, citations: o.c, quartile: Object.entries(o.q).sort((a, b) => b[1] - a[1])[0][0] })); };
    $('#pb-venues').innerHTML = sh.map(i => venueCol(i, vtop(i))).join(''); gridCols($('#pb-venues'));
    $('#pb-venues').querySelectorAll('.jr').forEach(e => e.onclick = () => explorer({ venue: e.dataset.j, inst: +e.dataset.i, type: 1 }));
  };
  ven(); segBind('venMode', ven);
}

// ================================================================ FACULTY
let facTable;
const H_BANDS = ['0', '1-4', '5-9', '10-14', '15-19', '20-29', '30+'];
const hBand = h => h === 0 ? '0' : h < 5 ? '1-4' : h < 10 ? '5-9' : h < 15 ? '10-14' : h < 20 ? '15-19' : h < 30 ? '20-29' : '30+';
function renderFaculty() {
  const sh = instsShown();
  const hd = sh.map(i => { const c = Object.fromEntries(H_BANDS.map(b => [b, 0])); F.forEach((f, k) => { if (f.i === i) { const s = fs(k); if (s.p > 0) c[hBand(s.h)]++; } }); return c; });
  plot('fc-h', sh.map((i, k) => ({ type: 'bar', name: I[i], x: H_BANDS, y: H_BANDS.map(b => hd[k][b]),
    marker: { color: instColor(i), line: { color: css('--surface'), width: 1 } }, hovertemplate: `${SHORT[i]} h-index %{x}: %{y} faculty<extra></extra>` })),
    { barmode: 'group', bargap: .25, bargroupgap: .08, margin: { l: 50, r: 12, t: 46, b: 44 }, legend: { orientation: 'h', y: 1.25, x: 0 }, xaxis: { title: { text: 'h-index band' }, type: 'category' }, yaxis: { title: { text: 'Faculty' } } },
    ev => { facTable.st.hband = ev.points[0].x; facTable.st.page = 0; facTable.draw(); $('#fc-table').scrollIntoView({ behavior: 'smooth', block: 'start' }); });

  const lb = () => {
    const m = segVal('lbMetric'), lab = { h: 'h-index', c: 'Citations', p: 'Papers', btw: 'Betweenness (all years)' }[m];
    const top = F.map((f, i) => [fs(i), i]).filter(([f]) => sh.includes(f.i) && f.p > 0).sort((a, b) => b[0][m] - a[0][m]).slice(0, 10).reverse();
    plot('fc-lb', [{ type: 'bar', orientation: 'h', y: top.map(([f]) => f.n), x: top.map(([f]) => f[m]), customdata: top.map(([, i]) => i),
      marker: { color: top.map(([f]) => instColor(f.i)) }, text: top.map(([f]) => m === 'btw' ? fmt3(f[m]) : fmt(f[m])), textposition: 'outside', cliponaxis: false, textfont: { color: css('--ink2'), size: 11 },
      hovertext: top.map(([f]) => `${esc(f.n)}<br>${SHORT[f.i]} · ${esc(f.d)}<br>h ${f.h} · ${fmt(f.p)} papers · ${fmt(f.c)} cites`), hovertemplate: '%{hovertext}<extra></extra>' }],
      { margin: { l: lm(top.map(([f]) => f.n)), r: 50, t: 4, b: 44 }, bargap: .28, xaxis: { title: { text: lab } } }, ev => openFaculty(ev.points[0].customdata));
  };
  lb(); segBind('lbMetric', lb);

  const depts = [...new Set(F.filter(f => sh.includes(f.i)).map(f => f.d))].sort();
  facTable = makeTable($('#fc-table'), {
    rows: () => F.map((f, i) => ({ ...fs(i), idx: i })).filter(f => sh.includes(f.i) && f.p > 0),
    search: 'Search name, department or journal…', text: f => f.n + ' ' + f.d + ' ' + f.tj,
    selects: [{ key: 'd', label: 'All departments', options: depts, get: f => f.d }, { key: 's', label: 'Current + former', options: ['current', 'former'], get: f => f.s }],
    filter: (f, st) => !st.hband || hBand(f.h) === st.hband,
    extraTools: (tools, st) => { const b = document.createElement('span'); b.className = 'chip'; b.style.display = 'none'; tools.append(b); st.badge = b; },
    sort: 'h', dir: -1, pageSize: 12,
    columns: [
      { key: 'n', label: 'Name', v: f => f.n, html: f => `<div class="namecell"><span class="av" style="background:linear-gradient(135deg, ${instColor(f.i)}, var(--brand1))">${esc(f.n.split(/\s+/).filter(w => /^[A-Za-z]/.test(w)).slice(0, 2).map(w => w[0].toUpperCase()).join(''))}</span><div><div class="t">${esc(f.n)}</div><div class="s">${esc(f.des || '')}${f.s === 'former' ? ' · former' : ''}</div></div></div>` },
      { key: 'i', label: 'Inst.', v: f => f.i, html: f => instChip(f.i) },
      { key: 'd', label: 'Department', v: f => f.d },
      { key: 'h', label: 'h-index 2016–26', num: 1, v: f => f.h },
      { key: 'i10', label: 'i10', num: 1, v: f => f.i10 },
      { key: 'citp', label: 'Cited %', num: 1, v: f => f.p ? Math.round(100 * f.cit / f.p) : null, html: f => f.p ? Math.round(100 * f.cit / f.p) + '%' : '—' },
      { key: 'ya', label: 'Active yrs', num: 1, v: f => f.ya },
      { key: 'p', label: 'Papers', num: 1, v: f => f.p, html: f => fmt(f.p) },
      { key: 'c', label: 'Citations', num: 1, v: f => f.c, html: f => fmt(f.c) },
      { key: 'q1', label: 'Q1 %', num: 1, v: f => f.q1, html: f => f.q1 == null ? '—' : f.q1 },
      { key: 'q1p', label: 'Q1 papers', num: 1, v: f => f.q1p },
      { key: 'tjp', label: 'Top-journal papers', num: 1, v: f => f.tjp, html: f => `<span title="${esc(f.tj)}">${f.tjp}</span>` },
      { key: 'deg', label: 'Collab.', num: 1, v: f => f.deg },
    ],
    onRow: f => openFaculty(f.idx),
  });
  const origDraw = facTable.draw;
  facTable.draw = () => { origDraw(); const b = facTable.st.badge; if (facTable.st.hband) { b.style.display = ''; b.innerHTML = `h-index ${facTable.st.hband} <a href="#" style="margin-left:4px">✕</a>`; b.querySelector('a').onclick = e => { e.preventDefault(); facTable.st.hband = null; facTable.draw(); }; } else b.style.display = 'none'; };
  facTable.draw();

  const dr = D.dept.filter(r => sh.includes(I.indexOf(r.institution)) && r.department !== 'Unknown department' && +r.papers >= 20);
  plot('fc-dept', sh.map(i => { const rs = dr.filter(r => r.institution === I[i]); return {
    type: 'scatter', mode: 'markers', name: I[i], x: rs.map(r => +r.papers_per_faculty), y: rs.map(r => +r['q1_share_%']), customdata: rs.map(r => r.department),
    marker: { size: rs.map(r => Math.sqrt(+r.papers) / 1.6 + 5), color: instColor(i), opacity: .75, line: { color: css('--surface'), width: 2 } },
    hovertext: rs.map(r => `<b>${esc(r.department)}</b> (${SHORT[i]})<br>${r.faculty_matched} faculty · ${fmt(+r.papers)} papers · ${fmt(+r.citations)} cites<br>median h ${r.median_h_index} · max h ${r.max_h_index}`), hovertemplate: '%{hovertext}<br>%{x} papers per faculty · %{y}% Q1<extra></extra>' }; }),
    { xaxis: { title: { text: 'Papers per faculty member' } }, yaxis: { title: { text: 'Journal Q1 share' }, ticksuffix: '%' } },
    ev => { const sel = facTable.opt.selects[0]; sel.el.value = ev.points[0].customdata; facTable.st.filters.d = sel.el.value; facTable.draw(); $('#fc-table').scrollIntoView({ behavior: 'smooth' }); });
}

// ================================================================ PAPERS
let exTable, exFilter = {};
const EX_SELECTS = [
  ['type', 'Any type', [['0', 'Journal papers'], ['1', 'Conference papers']]],
  ['q', 'Any rank', [['Q1', 'Q1'], ['Q2', 'Q2'], ['Q3', 'Q3'], ['Q4', 'Q4'], ['A*', 'CORE A*'], ['A', 'CORE A'], ['B', 'CORE B'], ['C', 'CORE C'], ['Unranked', 'Unranked']]],
  ['field', 'All fields', fieldCount.map(([f]) => [f, f])],
  ['iff', 'Any impact', [['1', 'Q1 & IF > 5'], ['2', 'Q1 & IF > 10']]],
  ['multi', 'Any team size', [['0', '10 or fewer authors'], ['1', 'More than 10 authors']]],
  ['flow', 'Any Indian links', [['out', 'Cites another Indian institute'], ['in', 'Cited by another Indian institute']]],
];
function explorer(f) {
  exFilter = { ...f };
  go('papers');
  drawExplorer();
  setTimeout(() => $('#explorerCard').scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
}
function exMatch(k) {
  const p = P[k], f = exFilter;
  if (!pIn(p)) return false;
  if (f.inst != null && f.inst >= 0 && !(p[T.mask] & (1 << f.inst))) return false;
  if (f.year && p[T.year] !== +f.year) return false;
  if (f.type != null && f.type !== '' && p[T.type] !== +f.type) return false;
  if (f.q) { if (f.q === 'Unranked' ? /^(Q[1-4]|A\*|A|B|C)$/.test(p[T.q]) : p[T.q] !== f.q || (/^Q[1-4]$/.test(f.q) && p[T.type] !== 0)) return false; }   // journal quartiles apply to journal papers only
  if (f.field && p[T.field] !== f.field) return false;
  if (f.venue && p[T.venue] !== f.venue && confName(p[T.venue]) !== f.venue) return false;
  if (f.iff && !(p[T.iff] >= +f.iff)) return false;
  if (f.multi != null && f.multi !== '' && p[T.multi] !== +f.multi) return false;
  if (f.flow === 'out' && !p[T.ci]) return false;
  if (f.flow === 'in' && !p[T.cbi]) return false;
  return true;
}
function drawExplorer() {
  const f = exFilter, chips = [];
  if (f.inst != null && f.inst >= 0) chips.push(['inst', I[f.inst]]);
  if (f.year) chips.push(['year', 'Year ' + f.year]);
  if (f.venue) chips.push(['venue', f.venue]);
  EX_SELECTS.forEach(([key, , opts]) => { if (f[key] != null && f[key] !== '') chips.push([key, (opts.find(o => o[0] === String(f[key])) || [, f[key]])[1]]); });
  const n = d3.range(P.length).filter(exMatch);
  const cites = d3.sum(n, k => P[k][T.cites]);
  $('#pp-exnote').innerHTML = `<b class="num">${fmt(n.length)}</b> papers · ${fmt(cites)} citations${fullYears() ? '' : ` · ${yrLabel()}`}` +
    (chips.length ? ` <span class="ex-chips">${chips.map(([k, l]) => `<span class="chip">${esc(l)} <a href="#" data-k="${k}" title="Remove">✕</a></span>`).join('')}<a href="#" id="exClear">Clear all</a></span>` : '');
  $('#pp-exnote').querySelectorAll('[data-k]').forEach(a => a.onclick = e => { e.preventDefault(); delete exFilter[a.dataset.k]; drawExplorer(); });
  $('#exClear') && ($('#exClear').onclick = e => { e.preventDefault(); exFilter = {}; drawExplorer(); });
  document.querySelectorAll('#pp-ex select[data-ex]').forEach(s => { s.value = exFilter[s.dataset.ex] != null ? String(exFilter[s.dataset.ex]) : ''; });
  if (exTable) { exTable.st.page = 0; exTable.draw(); }
}
function renderPapers() {
  const sh = instsShown();
  const t10 = d3.range(P.length).filter(k => pIn(P[k])).sort((a, b) => P[b][T.cites] - P[a][T.cites]).slice(0, 10);
  const doiMap = new Map(P.map((p, k) => [p[T.doi].toLowerCase(), k]));
  makeTable($('#pp-top10'), {
    rows: () => t10, pageSize: 10,
    columns: [
      { key: 'title', label: 'Paper', v: k => P[k][T.title], html: k => `<div class="t">${esc(P[k][T.title])}</div><div class="s">${esc(P[k][T.venue])} · ${P[k][T.year]}</div>` },
      { key: 'i', label: 'Inst.', v: k => P[k][T.mask], html: k => instNames(P[k][T.mask]).map(instChip).join(' ') },
      { key: 'citations', label: 'Cites', num: 1, v: k => P[k][T.cites], html: k => fmt(P[k][T.cites]) },
      { key: 'doi', label: 'DOI', v: k => P[k][T.doi], html: k => doiLink(P[k][T.doi]) },
    ],
    onRow: k => openPaper(k),
  });

  const s30 = D.top30sum.filter(r => sh.includes(I.indexOf(r.institution)));
  const metrics = [['Q1_share_%', 'Q1 share %'], ['Q1_and_IF_gt5', 'Q1 · IF > 5'], ['Q1_and_IF_gt10', 'Q1 · IF > 10'], ['papers_with_faculty_h_20_plus', 'Faculty h ≥ 20']];
  plot('pp-t30chart', s30.map(r => { const i = I.indexOf(r.institution); return { type: 'bar', name: I[i], x: metrics.map(m => m[1]), y: metrics.map(m => +r[m[0]]), marker: { color: instColor(i) }, hovertemplate: `${SHORT[i]} %{x}: %{y}<extra></extra>` }; }),
    { barmode: 'group', bargap: .3, margin: { l: 44, r: 8, t: 4, b: 30 }, yaxis: { title: { text: 'Count (or %)' } } });
  $('#pp-t30sum').innerHTML = `<div class="tbl-wrap" style="margin-top:8px"><table><thead><tr><th></th>${s30.map(r => `<th class="r">${SHORT[I.indexOf(r.institution)]}</th>`).join('')}</tr></thead><tbody>${
    [['citations_total', 'Total citations'], ['citations_median', 'Median citations'], ['citations_min', 'Citations of #30'], ['journal_papers', 'Journal papers'], ['Q1', 'Q1 papers'], ['median_venue_h_index', 'Median venue h-index'], ['median_max_faculty_h', 'Median best-author h']]
      .map(([k, l]) => `<tr><td>${l}</td>${s30.map(r => `<td class="r num">${fmt(+r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;

  const t30 = sh.flatMap(i => D.top30[I[i]].map(r => ({ ...r, i })));
  makeTable($('#pp-t30'), {
    rows: () => t30, pageSize: 10, sort: 'citations', dir: -1, search: 'Search title, journal or author…', text: r => r.title + r.journal_name + r.faculty_authors,
    selects: [{ key: 'q', label: 'Any quartile', options: ['Q1', 'Q2', 'Q3', 'Q4'], get: r => r.quartile }],
    columns: [
      { key: 'rank', label: 'Rank in inst.', num: 1, v: r => +r.rank },
      { key: 'title', label: 'Paper', v: r => r.title, html: r => `<div class="t">${esc(r.title)}</div><div class="s">${esc(r.journal_name)} · ${r.year} · ${esc(r.faculty_authors)}</div>` },
      { key: 'i', label: 'Inst.', v: r => r.i, html: r => instChip(r.i) },
      { key: 'quartile', label: 'Q', v: r => r.quartile, html: r => qChip(r.quartile) },
      { key: 'citations', label: 'Cites', num: 1, v: r => +r.citations, html: r => fmt(+r.citations) },
      { key: 'jcd', label: 'IF estimate', num: 1, v: r => +r.impact_estimate || null, html: r => r.impact_estimate ? `<span title="SCImago cites/doc ${esc(r.journal_cites_per_doc || 'n/a')} · OpenAlex 2-year citedness ${esc(r.journal_2yr_citedness_openalex || 'n/a')}">${esc(r.impact_estimate)}${(r.impact_check || '').startsWith('sources disagree') ? ' <span class="note">*</span>' : ''}</span>` : '—' },
      { key: 'if', label: 'IF flag', v: r => r.q1_impact_gt10 === 'TRUE' ? 2 : r.q1_impact_gt5 === 'TRUE' ? 1 : 0, html: r => r.q1_impact_gt10 === 'TRUE' ? '<span class="chip">&gt;10</span>' : r.q1_impact_gt5 === 'TRUE' ? '<span class="chip">&gt;5</span>' : '' },
      { key: 'mh', label: 'Best author h', num: 1, v: r => +r.max_faculty_h_index },
      { key: 'doi', label: '', v: r => r.doi, html: r => doiLink(r.doi) },
    ],
    onRow: r => { const k = doiMap.get((r.doi || '').toLowerCase()); if (k != null) openPaper(k); },
  });

  exTable = makeTable($('#pp-ex'), {
    rows: () => d3.range(P.length),
    search: 'Search titles…', text: k => P[k][T.title],
    filter: k => exMatch(k),
    extraTools: tools => EX_SELECTS.forEach(([key, label, opts]) => {
      const s = document.createElement('select'); s.dataset.ex = key;
      s.innerHTML = `<option value="">${esc(label)}</option>` + opts.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
      s.onchange = () => { if (s.value === '') delete exFilter[key]; else exFilter[key] = s.value; drawExplorer(); };
      tools.append(s);
    }),
    sort: 'cites', dir: -1, pageSize: 12,
    columns: [
      { key: 'title', label: 'Paper', v: k => P[k][T.title], html: k => `<div class="t">${esc(P[k][T.title])}</div><div class="s">${esc(P[k][T.venue] || '—')} · ${esc(P[k][T.field])}${P[k][T.type] ? ' · conference' : ''}</div>` },
      { key: 'inst', label: 'Inst.', v: k => P[k][T.mask], html: k => instNames(P[k][T.mask]).map(instChip).join(' ') },
      { key: 'year', label: 'Year', num: 1, v: k => P[k][T.year] },
      { key: 'q', label: 'Rank', v: k => P[k][T.q], html: k => qChip(P[k][T.q]) + (P[k][T.iff] ? ` <span class="chip">IF&gt;${P[k][T.iff] === 2 ? 10 : 5}</span>` : '') },
      { key: 'cites', label: 'Cites', num: 1, v: k => P[k][T.cites], html: k => fmt(P[k][T.cites]) },
      { key: 'pr', label: 'PageRank ×10⁶ (within corpus)', num: 1, v: k => P[k][T.pr], html: k => P[k][T.pr] ? fmt2(P[k][T.pr]) : '—' },
      { key: 'indeg', label: 'In-degree: papers that cite it (self)', num: 1, v: k => P[k][T.indeg], html: k => `${fmt(P[k][T.indeg])}${P[k][T.inSelf] ? ` <span class="note">(${P[k][T.inSelf]} self)</span>` : ''}` },
      { key: 'doi', label: '', v: k => P[k][T.doi], html: k => doiLink(P[k][T.doi]) },
    ],
    onRow: k => openPaper(k),
  });
  drawExplorer();

  const hy = D.hyper.filter(r => sh.includes(I.indexOf(r.institution)));
  $('#pp-hyper').innerHTML = `<div class="tbl-wrap"><table><thead><tr><th>Institute</th><th>Group</th><th class="r">Papers</th><th class="r">Share</th><th class="r">Mean cites</th><th class="r">Median cites</th><th class="r">Share of cites</th><th class="r">Q1 %</th></tr></thead><tbody>${
    hy.map(r => `<tr><td>${instChip(I.indexOf(r.institution))}</td><td>${esc(r.group)}</td><td class="r num">${fmt(+r.papers)}</td><td class="r num">${r['share_of_papers_%']}%</td><td class="r num">${r.mean_citations}</td><td class="r num">${r.median_citations}</td><td class="r num">${r['share_of_citations_%']}%</td><td class="r num">${r['journal_Q1_%']}</td></tr>`).join('')}</tbody></table></div>`;
}

// ================================================================ CITATION GRAPH
const cn = { sel: null, sim: null };
const CORE_R = new Set(['A*', 'A', 'B', 'C']);
const yearColor = y => d3.interpolateRgb(css('--seq0'), css('--seq1'))((y - 2016) / 10);
function cnColor(p, mode) {
  const x = P[p];
  if (mode === 'inst') { const n = instNames(x[T.mask]); return n.length > 1 ? css('--multi') : instColor(n[0]); }
  if (mode === 'field') { const k = TOP_FIELDS.indexOf(x[T.field]); return k >= 0 ? CAT()[k] : css('--other'); }
  if (mode === 'year') return yearColor(x[T.year]);
  return /^Q[1-4]$/.test(x[T.q]) ? css('--' + x[T.q].toLowerCase()) : css('--other');
}
const CN_SIZE = { pr: 'PageRank (influence)', in: 'in-degree (how many papers in the set cite it)', c: 'total citations', btw: 'betweenness (bridge papers, in this view)' };
const CN_COLOR = { inst: 'institute', field: 'research field', q: 'venue quartile', year: 'publication year' };
function cnLegend(o) {
  let items;
  if (o.color === 'inst') items = [...[0, 1, 2].map(i => [instColor(i), I[i]]), [css('--multi'), 'Shared by 2+ institutes']];
  else if (o.color === 'field') items = [...TOP_FIELDS.map((f, k) => [CAT()[k], f]), [css('--other'), 'Other fields']];
  else if (o.color === 'q') items = [...QS.map(q => [css('--' + q.toLowerCase()), q]), [css('--other'), 'CORE-ranked or unranked']];
  else items = [2016, 2018, 2020, 2022, 2024, 2026].map(y => [yearColor(y), String(y)]);
  $('#cn-legend').innerHTML = `<div class="lg-t">Colour = ${CN_COLOR[o.color]}</div>` + items.map(([c, l]) => `<div><span class="dot" style="background:${c}"></span>${esc(l)}</div>`).join('') +
    `<div class="lg-s">Size = ${CN_SIZE[o.size]}<br>Arrow points to the cited paper${$('#cnStar')?.checked ? '<br><span style="color:var(--brand3)">Orange line = citation between two institutes</span><br>Ring = standout paper' : ''}</div>`;
}
$('#cnField').innerHTML = '<option value="">All fields</option>' + fieldCount.map(([f, n]) => `<option value="${esc(f)}">${esc(f)} (${fmt(n)})</option>`).join('');
function cnOpts() {
  return { N: +$('#cnN').value, min: +$('#cnMin').value, view: $('#cnView').value, links: $('#cnLinks').value, type: $('#cnType').value,
    qs: new Set([...document.querySelectorAll('#cnQ input:checked')].map(e => e.value)), iff: +$('#cnIF').value || 0, core: $('#cnCore').value,
    field: $('#cnField').value, flow: $('#cnFlow').value, multi: $('#cnMulti').checked, size: $('#cnSize').value, color: $('#cnColor').value };
}
function cnPass(p, o, lens = true) {
  const x = P[p];
  if (!inYears(x)) return false;
  if (lens && !inInst(x[T.mask])) return false;
  if (o.type !== '' && x[T.type] !== +o.type) return false;
  if (o.core) { if (o.core === 'any' ? !CORE_R.has(x[T.q]) : x[T.q] !== o.core) return false; }
  else if (!o.qs.has(/^Q[1-4]$/.test(x[T.q]) ? x[T.q] : 'other')) return false;
  if (o.iff && !(x[T.iff] >= o.iff)) return false;
  if (o.field && x[T.field] !== o.field) return false;
  if (o.flow === 'out' && !x[T.ci]) return false;
  if (o.flow === 'in' && !x[T.cbi]) return false;
  if (o.multi && x[T.multi]) return false;
  if (x[T.indeg] < o.min) return false;
  return true;
}
function components(ids, links) {
  const par = new Map(ids.map(p => [p, p]));
  const find = p => { while (par.get(p) !== p) { par.set(p, par.get(par.get(p))); p = par.get(p); } return p; };
  links.forEach(([s, t]) => { const a = find(s), b = find(t); if (a !== b) par.set(a, b); });
  return d3.groups(ids, find).map(g => g[1]);
}
function cnBuild(o) {
  const share = (s, t) => (P[s][T.mask] & P[t][T.mask]) !== 0;
  const selfL = (s, t) => (D.pfac[s] || []).some(f => (D.pfac[t] || []).includes(f));
  const keep = (s, t) => o.links === 'all' || (o.links === 'self' ? selfL(s, t) : o.links === 'noself' ? !selfL(s, t) : o.links === 'within' ? share(s, t) : !share(s, t));
  let ids, links;
  if (o.view === 'ego1' || o.view === 'ego2') {
    if (cn.sel == null) return { need: 'ego' };
    const seen = new Set([cn.sel]); let front = [cn.sel];
    for (let h = 0; h < (o.view === 'ego1' ? 1 : 2); h++) {
      const nx = [];
      front.forEach(p => [...citesOut[p], ...citesIn[p]].forEach(q => { if (!seen.has(q) && seen.size < 900 && cnPass(q, o, false)) { seen.add(q); nx.push(q); } }));
      front = nx;
    }
    ids = [...seen];
    const S0 = new Set(ids); links = D.cedges.filter(([s, t]) => S0.has(s) && S0.has(t) && keep(s, t));
    return { ids, links };
  }
  cn.matched = 0;
  if (o.links === 'between') {
    // citations between our institutes: keep both ends, even when the other end is outside the lens
    links = D.cedges.filter(([s, t]) => !share(s, t) && cnPass(s, o, false) && cnPass(t, o, false) && (inInst(P[s][T.mask]) || inInst(P[t][T.mask])));
    const top = new Set([...new Set(links.flat())].sort((a, b) => prRank[a] - prRank[b]).slice(0, o.N));
    links = links.filter(([s, t]) => top.has(s) && top.has(t));
    ids = [...new Set(links.flat())];
  } else {
    ids = prOrder.filter(p => cnPass(p, o)).slice(0, o.N); cn.matched = ids.length;
    const S0 = new Set(ids); links = D.cedges.filter(([s, t]) => S0.has(s) && S0.has(t) && keep(s, t));
  }
  if (o.view === 'linked') { const d = new Set(links.flat()); ids = ids.filter(p => d.has(p) || p === cn.sel); }
  else if (o.view === 'lcc' || o.view === 'small') {
    const comps = components(ids, links).sort((a, b) => b.length - a.length);
    const keepIds = new Set(o.view === 'lcc' ? (comps[0] || []) : comps.filter(c => c.length >= 2 && c.length <= 15).flat());
    ids = ids.filter(p => keepIds.has(p)); links = links.filter(([s, t]) => keepIds.has(s) && keepIds.has(t));
  }
  return { ids, links };
}
// Brandes betweenness on the papers in view (undirected; sampled sources for large views)
function viewBetweenness(ids, links) {
  const idx = new Map(ids.map((p, k) => [p, k])), n = ids.length, A = ids.map(() => []), cb = new Float64Array(n);
  links.forEach(([s, t]) => { const a = idx.get(s), b = idx.get(t); A[a].push(b); A[b].push(a); });
  const step = Math.max(1, Math.ceil(n / 400));
  for (let s = 0; s < n; s += step) {
    const St = [], Pr = new Map(), sig = new Float64Array(n), dist = new Int32Array(n).fill(-1), Q = [s]; sig[s] = 1; dist[s] = 0;
    for (let qi = 0; qi < Q.length; qi++) { const v = Q[qi]; St.push(v); for (const w of A[v]) { if (dist[w] < 0) { dist[w] = dist[v] + 1; Q.push(w); } if (dist[w] === dist[v] + 1) { sig[w] += sig[v]; (Pr.get(w) || Pr.set(w, []).get(w)).push(v); } } }
    const de = new Float64Array(n);
    while (St.length) { const w = St.pop(); for (const v of Pr.get(w) || []) de[v] += sig[v] / sig[w] * (1 + de[w]); if (w !== s) cb[w] += de[w]; }
  }
  return new Map(ids.map((p, k) => [p, cb[k] * step]));
}
function cnActive(o) {
  const parts = [];
  if (!fullYears()) parts.push(`Years ${yrLabel()}`);
  if (state.inst >= 0) parts.push(I[state.inst]);
  if (o.type !== '') parts.push(o.type === '0' ? 'Journal papers' : 'Conference papers');
  if (o.core) parts.push(o.core === 'any' ? 'Any CORE rank' : 'CORE ' + o.core);
  else if (o.qs.size < 5) parts.push('Rank: ' + [...o.qs].map(q => q === 'other' ? 'other' : q).join(', '));
  if (o.iff) parts.push(`Q1 & IF > ${o.iff === 2 ? 10 : 5}`);
  if (o.field) parts.push(o.field);
  if (o.flow) parts.push(o.flow === 'out' ? 'Cites another Indian institute' : 'Cited by another Indian institute');
  if (o.multi) parts.push('≤ 10 authors');
  if (o.min) parts.push(`Cited ≥ ${o.min}× in corpus`);
  if (o.links !== 'all') parts.push({ within: 'Links within one institute', between: 'Links between the three institutes', self: 'Self-citations only', noself: 'Without self-citations' }[o.links]);
  $('#cnActive').innerHTML = parts.length ? `<span class="note">Active:</span> ${parts.map(p => `<span class="chip">${esc(p)}</span>`).join(' ')}` : '<span class="note">No filters: showing the most influential papers by PageRank.</span>';
}
function cnResetAll() {
  $('#cnN').value = 500; $('#cnMin').value = 0; $('#cnView').value = 'linked'; $('#cnLinks').value = 'all'; $('#cnType').value = ''; $('#cnIF').value = '';
  $('#cnCore').value = ''; $('#cnField').value = ''; $('#cnFlow').value = ''; $('#cnMulti').checked = false;
  document.querySelectorAll('#cnQ input').forEach(e => e.checked = true);
  cn.sel = null; drawCitGraph();
}
function drawCitGraph() {
  const o = cnOpts();
  $('#cnNv').textContent = o.N; $('#cnMinv').textContent = o.min;
  $('#cnN').disabled = o.view.startsWith('ego');
  document.querySelectorAll('#cnQ input').forEach(e => { e.disabled = !!o.core; });
  cnActive(o); cnLegend(o);
  const wrap = $('#cn-wrap'); wrap.querySelector('.cn-empty')?.remove();
  const svg = d3.select('#cn-svg'); svg.selectAll('*').remove();
  if (cn.sim) cn.sim.stop();
  const b = cnBuild(o);
  if (b.need === 'ego' || !b.ids.length) {
    $('#cn-stats').innerHTML = '<b class="num">0</b> papers shown';
    wrap.insertAdjacentHTML('beforeend', b.need === 'ego'
      ? '<div class="cn-empty"><b>Pick a paper first</b><p>Click a paper in the graph or in the PageRank table below, or find one with Ctrl K, then choose this view again.</p><button class="btn" data-a="back">Back to linked papers</button></div>'
      : cn.matched ? `<div class="cn-empty"><b>${fmt(cn.matched)} papers match, but none cite each other</b><p>Set <b>View</b> to "All, including unlinked papers" to see them, or widen the filters.</p><button class="btn" data-a="all">Show unlinked papers</button></div>`
      : '<div class="cn-empty"><b>No papers match these filters</b><p>Try a wider year range, tick more ranks, lower "Cited at least", or switch "Links" back to all citations.</p><button class="btn" data-a="reset">Reset filters</button></div>');
    wrap.querySelector('.cn-empty .btn').onclick = e => { const a = e.target.dataset.a; if (a === 'back') { $('#cnView').value = 'linked'; drawCitGraph(); } else if (a === 'all') { $('#cnView').value = 'all'; drawCitGraph(); } else cnResetAll(); };
    cn.node = null; return;
  }
  const btw = o.size === 'btw' ? viewBetweenness(b.ids, b.links) : null;
  const val = p => o.size === 'pr' ? P[p][T.pr] : o.size === 'in' ? P[p][T.indeg] : o.size === 'c' ? P[p][T.cites] : btw.get(p);
  const nodes = b.ids.map(p => ({ id: p })), byId = new Map(nodes.map(n => [n.id, n]));
  const links = b.links.map(([s, t]) => ({ source: byId.get(s), target: byId.get(t) })).filter(l => l.source && l.target);
  const r = d3.scaleSqrt().domain([0, d3.max(nodes, n => val(n.id)) || 1]).range([2.5, 17]);
  $('#cn-stats').innerHTML = `<b class="num">${fmt(nodes.length)}</b> papers · <b class="num">${fmt(links.length)}</b> citations shown<br><span class="note">${o.view.startsWith('ego') ? 'around the selected paper' : `of ${fmt(P.filter(pIn).length)} papers in scope`}</span>`;
  const { width: W, height: H } = wrap.getBoundingClientRect();
  const defs = svg.append('defs');
  [['arr', css('--muted')], ['arrH', css('--brand1')]].forEach(([id, c]) => defs.append('marker').attr('id', id).attr('viewBox', '0 -4 8 8').attr('refX', 8).attr('markerWidth', 6).attr('markerHeight', 6).attr('orient', 'auto').append('path').attr('d', 'M0,-4L8,0L0,4').attr('fill', c));
  const g = svg.append('g');
  const zoom = d3.zoom().scaleExtent([.15, 8]).on('zoom', e => { g.attr('transform', e.transform); g.selectAll('.stars text').attr('font-size', 11.5 / e.transform.k).attr('stroke-width', 4 / e.transform.k); g.selectAll('.stars circle').attr('stroke-width', 3 / e.transform.k); });
  svg.call(zoom).on('dblclick.zoom', null);
  Object.assign(cn, { zoom, svg, W, H, byId });
  const starOn = !!$('#cnStar')?.checked, cross = l => !(P[l.source.id][T.mask] & P[l.target.id][T.mask]);
  cn.cross = cross;
  const link = g.append('g').selectAll('line').data(links).join('line').attr('stroke', l => starOn && cross(l) ? css('--brand3') : css('--muted')).attr('stroke-opacity', l => starOn && cross(l) ? 1 : .7).attr('stroke-width', l => starOn && cross(l) ? 2.4 : 1.2).attr('marker-end', 'url(#arr)');
  const node = g.append('g').selectAll('circle').data(nodes).join('circle')
    .attr('r', d => r(val(d.id))).attr('fill', d => cnColor(d.id, o.color)).attr('stroke', d => d.id === cn.sel ? css('--ink') : css('--surface')).attr('stroke-width', d => d.id === cn.sel ? 2.5 : 1.5).style('cursor', 'pointer')
    .on('mouseenter', (e, d) => tip(e, `<b>${esc(P[d.id][T.title])}</b><div class="m">${instNames(P[d.id][T.mask]).map(i => SHORT[i]).join(', ')} · ${P[d.id][T.year]} · ${esc(P[d.id][T.venue] || '')} · ${esc(P[d.id][T.q])}</div><div class="m">PageRank #${fmt(prRank[d.id])} · cited ${P[d.id][T.indeg]}× in corpus · ${fmt(P[d.id][T.cites])} citations${btw ? ` · betweenness ${fmt1(btw.get(d.id))}` : ''}</div>`))
    .on('mousemove', moveTip).on('mouseleave', hideTip)
    .on('click', (e, d) => { e.stopPropagation(); if (o.view.startsWith('ego') && d.id !== cn.sel) { cn.sel = d.id; drawCitGraph(); } else cnSelect(d.id); openPaper(d.id); })
    .call(d3.drag().on('start', (e, d) => { if (!e.active) sim.alphaTarget(.2).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; }).on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
  svg.on('click', () => cnSelect(null));
  cn.node = node; cn.link = link;
  const cMax = f => nodes.reduce((m, n) => (!m || f(n) > f(m) ? n : m), null), cS = (node, tag) => node && ({ node, tag: `${tag}: ${P[node.id][T.title].slice(0, 42)}${P[node.id][T.title].length > 42 ? '…' : ''}`, r: r(val(node.id)) });
  const starUp = addStars(g, mergeStars([cS(cMax(n => P[n.id][T.cites]), 'Most cited in view'), cS(cMax(n => P[n.id][T.pr]), 'Top PageRank in view'), cS(cMax(n => P[n.id][T.indeg]), 'Most cited inside the set, in view')].filter(Boolean)), starOn);
  const sim = cn.sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).distance(28).strength(.5))
    .force('charge', d3.forceManyBody().strength(-34).distanceMax(320))
    .force('x', d3.forceX(W / 2).strength(.06)).force('y', d3.forceY(H / 2).strength(.06))
    .force('collide', d3.forceCollide(d => r(val(d.id)) + 1.5))
    .on('tick', () => {
      link.each(function (l) { const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y, len = Math.hypot(dx, dy) || 1, rr = r(val(l.target.id)) + 2;
        this.setAttribute('x1', l.source.x); this.setAttribute('y1', l.source.y); this.setAttribute('x2', l.target.x - dx / len * rr); this.setAttribute('y2', l.target.y - dy / len * rr); });
      node.attr('cx', d => d.x).attr('cy', d => d.y); starUp();
    });
  sim.stop().tick(220); sim.on('tick')(); fitView(cn, nodes);
  if (cn.sel != null && byId.has(cn.sel)) cnSelect(cn.sel, o.view.startsWith('ego') ? false : !!cn.zoomSel);
  cn.zoomSel = false;
}
function renderCitnet() {
  drawCitGraph();
  makeTable($('#cn-top'), {
    rows: () => D.top10pr, pageSize: 10,
    columns: [
      { key: 'title', label: 'Paper', v: r => r.title, html: r => `<div class="t">${esc(r.title)}</div><div class="s">${esc(r.journal)} · ${r.year}</div>` },
      { key: 'inst', label: 'Inst.', v: r => r.inst, html: r => instChip(I.indexOf(r.inst)) },
      { key: 'pagerank', label: 'PageRank', num: 1, v: r => r.pagerank, html: r => r.pagerank.toFixed(4) },
      { key: 'in', label: 'In-deg.', num: 1, v: r => r.in_degree_in_corpus },
      { key: 'c', label: 'Cites', num: 1, v: r => r.citations_openalex },
    ],
    onRow: r => { const k = P.findIndex(p => p[T.title] === r.title && p[T.year] === r.year); if (k >= 0) focusPaper(k); },
  });
  const ind = d3.rollups(P.filter(p => p[T.indeg] > 0 && pIn(p)), v => v.length, p => p[T.indeg]).sort((a, b) => a[0] - b[0]);
  plot('cn-indeg', [{ type: 'scatter', mode: 'markers', x: ind.map(d => d[0]), y: ind.map(d => d[1]), marker: { size: 8, color: state.inst < 0 ? css('--c7') : instColor(state.inst), line: { color: css('--surface'), width: 1.5 } }, hovertemplate: 'Cited %{x}× in corpus: %{y} papers<extra></extra>' }],
    { xaxis: { type: 'log', title: { text: 'In-degree: number of papers in the set that cite this paper (log)' } }, yaxis: { type: 'log', title: { text: 'Number of papers (log)' } } });
  const flowDraw = () => {
    const cross = segVal('flowMode') === 'cross', pct = segVal('flowUnit') === 'pct';
    const M = pct ? D.citNet.flow_matrix_row_pct : D.citNet.flow_matrix_source_rows_target_cols;   // row = citing institute, column = cited institute
    const z = I.map(a => I.map(b => cross && a === b ? null : M[a][b]));
    const lab = v => v == null ? '—' : pct ? fmt1(v) + '%' : fmt(v);
    plot('cn-flow', [{ type: 'heatmap', x: SHORT.map(s => '→ ' + s), y: SHORT, z, colorscale: [[0, css('--seq0')], [1, css('--seq1')]], showscale: false, xgap: 3, ygap: 3,
      hovertemplate: pct ? '%{y} citing links that go to %{x}: %{z:.1f}% of its outgoing links<extra></extra>' : '%{y} papers cite %{x} papers: %{z:,} links<extra></extra>' }],
      { yaxis: { autorange: 'reversed', title: { text: 'Citing institute (row)' } }, xaxis: { title: { text: 'Cited institute (column)' } }, margin: { l: 70, r: 10, t: 4, b: 44 },
        annotations: I.flatMap((a, r) => I.map((b, c) => ({ x: '→ ' + SHORT[c], y: SHORT[r], text: lab(z[r][c]), showarrow: false, font: { color: z[r][c] / d3.max(z.flat()) > .5 ? (isDark() ? '#0b0b0b' : '#ffffff') : css('--ink'), size: 13 } }))) });
  };
  flowDraw(); segBind('flowMode', flowDraw); segBind('flowUnit', flowDraw);
  const mac = D.citMacro, rows = [['papers', 'Papers'], ['citation_links', 'Citation links'], ['density', 'Density'], ['avg_clustering_undirected', 'Avg clustering (undirected)'], ['reciprocity', 'Reciprocity'], ['weak_components', 'Weak components'], ['largest_component_share_%', 'Largest component %'], ['papers_never_cited_in_corpus_%', 'Never cited in corpus %']];
  const scopes = ['whole corpus', ...instsShown().map(i => I[i])];
  $('#cn-macro').innerHTML = `<div class="tbl-wrap"><table><thead><tr><th></th>${scopes.map(s => `<th class="r">${s === 'whole corpus' ? 'All' : SHORT[I.indexOf(s)]}</th>`).join('')}</tr></thead><tbody>${rows.map(([k, l]) => `<tr><td>${l}</td>${scopes.map(s => `<td class="r num">${typeof mac[s][k] === 'number' && mac[s][k] >= 1000 ? fmt(mac[s][k]) : mac[s][k]}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function cnSelect(p, zoomTo) {
  cn.sel = p; if (!cn.node) return;
  if (p == null) { cn.node.attr('opacity', 1); const sx = $('#cnStar')?.checked; cn.link.attr('stroke-opacity', l => sx && cn.cross(l) ? 1 : .7).attr('stroke', l => sx && cn.cross(l) ? css('--brand3') : css('--muted')).attr('marker-end', 'url(#arr)'); return; }
  const nb = new Set([p, ...citesOut[p], ...citesIn[p]]);
  cn.node.attr('opacity', d => nb.has(d.id) ? 1 : .12);
  cn.link.attr('stroke-opacity', l => l.source.id === p || l.target.id === p ? .95 : .04).attr('stroke', l => l.source.id === p || l.target.id === p ? css('--brand1') : css('--axis'))
    .attr('marker-end', l => l.source.id === p || l.target.id === p ? 'url(#arrH)' : 'url(#arr)');
  const n = cn.byId.get(p);
  if (zoomTo && n && n.x != null) cn.svg.transition().duration(700).call(cn.zoom.transform, d3.zoomIdentity.translate(cn.W * ($('#drawer').classList.contains('on') ? .3 : .5), cn.H / 2).scale(2.2).translate(-n.x, -n.y));
}
function focusPaper(p) {
  cn.sel = p; $('#cnView').value = 'ego1';
  state.dirty.add('citnet'); go('citnet');
  setTimeout(() => openPaper(p), 400);
}
['cnN', 'cnMin', 'cnView', 'cnLinks', 'cnType', 'cnIF', 'cnCore', 'cnField', 'cnFlow', 'cnMulti', 'cnSize', 'cnColor', 'cnStar'].forEach(id => $('#' + id).addEventListener('input', () => {
  if (id === 'cnN') $('#cnNv').textContent = $('#cnN').value; if (id === 'cnMin') $('#cnMinv').textContent = $('#cnMin').value;
  clearTimeout(cn.t); cn.t = setTimeout(drawCitGraph, id === 'cnN' || id === 'cnMin' ? 250 : 0); }));
document.querySelectorAll('#cnQ input').forEach(e => e.addEventListener('change', () => { clearTimeout(cn.t); cn.t = setTimeout(drawCitGraph, 0); }));
$('#cnReset').onclick = cnResetAll;

// tooltip
function tip(e, html) { const t = $('#tip'); t.innerHTML = html; t.style.display = 'block'; moveTip(e); }
function moveTip(e) { const t = $('#tip'), w = t.offsetWidth; t.style.left = Math.min(innerWidth - w - 10, e.clientX + 14) + 'px'; t.style.top = (e.clientY + 14) + 'px'; }
function hideTip() { $('#tip').style.display = 'none'; }

// ================================================================ COLLABORATION GRAPH
const fn = { sel: null, comm: null };
function fnColor(i, mode) {
  const f = F[i];
  if (mode === 'inst') return instColor(f.i);
  if (mode === 'lv') { const k = TOP_COMMS.indexOf(f.lv); return k >= 0 ? CAT()[k] : css('--other'); }
  if (mode === 'dept') { const k = TOP_DEPTS.indexOf(f.d); return k >= 0 ? CAT()[k] : css('--other'); }
  return d3.interpolateRgb(css('--seq0'), css('--seq1'))(f.kc / 5);
}
function commLabel(c) {
  const mem = F.map((f, i) => [f, i]).filter(([f, i]) => f.lv === c && adj[i].length);
  const inst = d3.rollups(mem, v => v.length, ([f]) => f.i).sort((a, b) => b[1] - a[1])[0];
  const dept = d3.rollups(mem, v => v.length, ([f]) => f.d).sort((a, b) => b[1] - a[1])[0];
  return { mem, inst: inst?.[0], dept: dept?.[0], deptShare: dept ? dept[1] / mem.length : 0, lead: mem.sort((a, b) => b[0].deg - a[0].deg).slice(0, 3) };
}
function fnLegend(mode) {
  let items;
  if (mode === 'inst') items = instsShown().map(i => [instColor(i), I[i]]);
  else if (mode === 'lv') items = [...TOP_COMMS.map((c, k) => { const L = commLabel(c); return [CAT()[k], `C${c} · ${SHORT[L.inst]} ${L.dept?.replace(' Engineering', ' Eng.')} (${L.mem.length})`, c]; }), [css('--other'), `${commSize.length - 8} smaller communities`]];
  else if (mode === 'dept') items = [...TOP_DEPTS.map((d, k) => [CAT()[k], d]), [css('--other'), 'Other departments']];
  else items = [1, 2, 3, 4, 5].map(k => [d3.interpolateRgb(css('--seq0'), css('--seq1'))(k / 5), `k-core ${k}`]);
  const what = { lv: 'research community (Louvain): faculty who publish together', inst: 'institute', dept: 'department', kc: 'k-core: depth inside the network' }[mode];
  const size = { deg: 'number of faculty collaborators', h: 'h-index', btw: 'betweenness (bridging role)', p: 'papers', eig: 'eigenvector centrality' }[$('#fnSize').value];
  $('#fn-legend').innerHTML = `<div class="lg-t">Colour = ${what}</div>` + items.map(([c, l, id]) => `<div ${id != null ? `data-c="${id}"` : ''}><span class="dot" style="background:${c}"></span>${esc(l)}</div>`).join('') +
    `<div class="lg-s">Size = ${size}<br>Ring = standout: top broker, most co-authors, strongest cross-institute pair<br>Line = joint papers (thicker = more)${$('#fnCross')?.checked ? `<br><span style="color:var(--brand3)">Orange line = link between two institutes </span>` : ''}${mode === 'lv' ? '<br>Click a community to highlight it' : ''}</div>`;
  $('#fn-legend').querySelectorAll('[data-c]').forEach(e => e.onclick = () => focusCommunity(+e.dataset.c, true));
}
function renderCollab() {
  const mode = $('#fnColor').value, sizeBy = $('#fnSize').value, minW = +$('#fnW').value;
  $('#fnWv').textContent = minW;
  const sh = instsShown();
  let ids = d3.range(F.length).filter(i => sh.includes(F[i].i));
  const ok = new Set(ids);
  const lk = $('#fnLinks')?.value || 'all';
  let E = D.fedges.filter(([a, b, w]) => ok.has(a) && ok.has(b) && w >= minW && (lk === 'all' || (lk === 'between') === (F[a].i !== F[b].i)));
  if ($('#fnIso').checked) { const d = new Set(E.flatMap(e => [e[0], e[1]])); ids = ids.filter(i => d.has(i)); }
  const topN = +($('#fnTop')?.value || 0);
  if (topN > 0 && ids.length > topN) { ids = ids.slice().sort((a, b) => F[b][sizeBy] - F[a][sizeBy]).slice(0, topN); const keep = new Set(ids); E = E.filter(([a, b]) => keep.has(a) && keep.has(b)); }
  const nodes = ids.map(i => ({ id: i })), byId = new Map(nodes.map(n => [n.id, n]));
  const links = E.map(([a, b, w]) => ({ source: byId.get(a), target: byId.get(b), w })).filter(l => l.source && l.target);
  const r = d3.scaleSqrt().domain([0, d3.max(nodes, n => F[n.id][sizeBy]) || 1]).range([3, 18]);
  fnLegend(mode);
  const ws = D.facNet[state.inst < 0 ? 'whole_network' : I[state.inst]];
  $('#fn-stats').innerHTML = `<b class="num">${fmt(nodes.length)}</b> faculty${topN ? ` (top ${topN} by ${$('#fnSize').selectedOptions[0].text.toLowerCase()})` : ''} · <b class="num">${fmt(links.length)}</b> links${$('#fnCross')?.checked ? ` (<b class="num" style="color:var(--brand3)">${fmt(links.filter(fnX).length)}</b> between institutes)` : ''}<br><span class="note">Louvain ${ws.louvain.communities} communities · Q = ${ws.louvain.modularity}</span>`;

  const svg = d3.select('#fn-svg'); svg.selectAll('*').remove();
  const { width: W, height: H } = $('#fn-wrap').getBoundingClientRect();
  const g = svg.append('g');
  const zoom = d3.zoom().scaleExtent([.15, 8]).on('zoom', e => { g.attr('transform', e.transform); g.selectAll('.stars text').attr('font-size', 11.5 / e.transform.k).attr('stroke-width', 4 / e.transform.k); g.selectAll('.stars circle').attr('stroke-width', 3 / e.transform.k); label.attr('font-size', 10.5 / e.transform.k).attr('stroke-width', 3 / e.transform.k).style('display', d => showLab(d, e.transform.k) ? null : 'none'); });
  svg.call(zoom).on('dblclick.zoom', null);
  Object.assign(fn, { zoom, svg, W, H, byId });
  const link = g.append('g').selectAll('line').data(links).join('line').attr('stroke', css('--axis')).attr('stroke-opacity', .6).attr('stroke-width', l => Math.min(6, .6 + Math.sqrt(l.w) * .7));
  Object.assign(fn, { link }); fnLinkBase();
  const node = g.append('g').selectAll('circle').data(nodes).join('circle')
    .attr('r', d => r(F[d.id][sizeBy])).attr('fill', d => fnColor(d.id, mode)).attr('stroke', css('--surface')).attr('stroke-width', 1.5).style('cursor', 'pointer')
    .on('mouseenter', (e, d) => { const f = F[d.id]; tip(e, `<b>${esc(f.n)}</b><div class="m">${SHORT[f.i]} · ${esc(f.d)}</div><div class="m">h ${f.h} · ${fmt(f.p)} papers · ${f.deg} collaborators · betweenness ${fmt3(f.btw)} · community ${f.lv}</div>`); })
    .on('mousemove', moveTip).on('mouseleave', hideTip)
    .on('click', (e, d) => { e.stopPropagation(); fnSelect(d.id); openFaculty(d.id); })
    .call(d3.drag().on('start', (e, d) => { if (!e.active) sim.alphaTarget(.2).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; }).on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
  const labTop = new Set(nodes.slice().sort((a, b) => F[b.id].deg - F[a.id].deg).slice(0, 22).map(n => n.id));
  const showLab = (d, k) => $('#fnLab').checked && (labTop.has(d.id) || k > 2.2 || fn.sel === d.id);
  const label = g.append('g').selectAll('text').data(nodes).join('text').text(d => F[d.id].n).attr('font-size', 10.5).attr('fill', css('--ink')).attr('paint-order', 'stroke').attr('stroke', css('--raise')).attr('stroke-width', 3)
    .attr('pointer-events', 'none').attr('dx', d => r(F[d.id][sizeBy]) + 3).attr('dy', 3.5).style('display', d => showLab(d, 1) ? null : 'none');
  svg.on('click', () => { fnSelect(null); });
  Object.assign(fn, { node, link, label });
  if (fn.sim) fn.sim.stop();
  const starOn = !!$('#fnStar')?.checked;
  const pickMax = f => nodes.reduce((m, n) => (!m || f(n) > f(m) ? n : m), null), xl = links.filter(fnX).sort((p, q) => q.w - p.w)[0];
  const sNode = (node, tag) => node && ({ node, tag: `${tag}: ${F[node.id].n}`, r: r(F[node.id][sizeBy]) });
  const starUp = addStars(g, mergeStars([sNode(pickMax(n => F[n.id].btw), 'Top broker'), sNode(pickMax(n => F[n.id].deg), 'Most co-authors'), xl && sNode(xl.source, 'Strongest cross-institute pair'), xl && sNode(xl.target, 'Strongest cross-institute pair')].filter(Boolean)), starOn);
  fn.starLink = xl; fnLinkBase();
  const sim = fn.sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).distance(l => 34 / Math.sqrt(l.w)).strength(.6))
    .force('charge', d3.forceManyBody().strength(-42).distanceMax(380))
    .force('x', d3.forceX(W / 2).strength(.05)).force('y', d3.forceY(H / 2).strength(.05))
    .force('collide', d3.forceCollide(d => r(F[d.id][sizeBy]) + 2))
    .on('tick', () => {
      link.attr('x1', l => l.source.x).attr('y1', l => l.source.y).attr('x2', l => l.target.x).attr('y2', l => l.target.y);
      node.attr('cx', d => d.x).attr('cy', d => d.y); label.attr('x', d => d.x).attr('y', d => d.y); starUp();
    });
  sim.stop().tick(260); sim.on('tick')(); fitView(fn, nodes);
  if (fn.pending) { const p = fn.pending; fn.pending = null; p(); }
  else if (fn.sel != null && byId.has(fn.sel)) fnSelect(fn.sel); else if (fn.comm != null) highlightComm(fn.comm);

  // side panels
  const comms = commSize.filter(([c]) => { const L = commLabel(c); return sh.includes(L.inst); }).slice(0, 12);
  $('#fn-comms').innerHTML = `<div class="tbl-wrap"><table><thead><tr><th>Community</th><th class="r">Size</th><th>Main department</th><th>Most connected</th></tr></thead><tbody>${comms.map(([c, n]) => {
    const L = commLabel(c), k = TOP_COMMS.indexOf(c);
    return `<tr class="row" data-c="${c}"><td><span class="dot" style="background:${k >= 0 ? CAT()[k] : css('--other')}"></span> C${c} ${instChip(L.inst)}</td><td class="r num">${n}</td><td>${esc(L.dept)} <span class="s">${Math.round(L.deptShare * 100)}%</span></td><td>${L.lead.map(([f, i]) => `<a href="#" data-f="${i}">${esc(f.n)}</a>`).join(', ')}</td></tr>`; }).join('')}</tbody></table></div>`;
  $('#fn-comms').querySelectorAll('tr.row').forEach(tr => tr.onclick = e => { if (e.target.dataset.f) { e.preventDefault(); openFaculty(+e.target.dataset.f); return; } focusCommunity(+tr.dataset.c, true); });

  const br = F.map((f, i) => [f, i]).filter(([f]) => sh.includes(f.i)).sort((a, b) => b[0].btw - a[0].btw).slice(0, 10);
  makeTable($('#fn-brokers'), {
    rows: () => br, pageSize: 10,
    columns: [
      { key: 'n', label: 'Faculty', v: ([f]) => f.n, html: ([f]) => `<div class="t">${esc(f.n)}</div><div class="s">${esc(f.d)}</div>` },
      { key: 'i', label: 'Inst.', v: ([f]) => f.i, html: ([f]) => instChip(f.i) },
      { key: 'btw', label: 'Betweenness', num: 1, v: ([f]) => f.btw, html: ([f]) => `<i class="minibar" style="width:${(f.btw / br[0][0].btw * 50).toFixed(0)}px"></i>${fmt3(f.btw)}` },
      { key: 'deg', label: 'Collab.', num: 1, v: ([f]) => f.deg },
      { key: 'xd', label: 'Other dept', num: 1, v: ([f]) => f.xd },
    ],
    onRow: ([, i]) => { focusFaculty(i); },
  });

  const bd = D.bridges.filter(r => sh.includes(I.indexOf(r.institution))).sort((a, b) => b.cross_institute_edges - a.cross_institute_edges).slice(0, 15).reverse();
  const fkey = new Map(F.map((f, i) => [f.i + '|' + f.n, i]));
  plot('fn-bridges', [{ type: 'bar', orientation: 'h', y: bd.map(r => r.faculty_name + ' '), x: bd.map(r => +r.cross_institute_edges), customdata: bd.map(r => fkey.get(I.indexOf(r.institution) + '|' + r.faculty_name)),
    marker: { color: bd.map(r => instColor(I.indexOf(r.institution))) }, hovertext: bd.map(r => `${r.faculty_name} (${SHORT[I.indexOf(r.institution)]})<br>${r.distinct_indian_partner_institutes} partner institutes · ${r.joint_papers} joint papers`),
    hovertemplate: '%{hovertext}<br>%{x} cross-institute edges<extra></extra>' }], { margin: { l: lm(bd.map(r => r.faculty_name)), r: 14, t: 4, b: 30 }, bargap: .28, xaxis: { title: { text: 'co-authorship edges to other Indian institutes' } } },
    ev => ev.points[0].customdata != null && openFaculty(ev.points[0].customdata));

  const X = D.facNetExtra.filter(x => x.scope === 'all three institutes' || sh.map(i => I[i]).includes(x.scope));
  const mrow = [['faculty', 'Faculty'], ['links', 'Links'], ['largest_component_faculty', 'Largest component'], ['diameter_largest_component', 'Diameter'], ['avg_shortest_path_largest_component', 'Avg shortest path'], ['degree_assortativity', 'Degree assortativity'], ['h_index_assortativity', 'h-index assortativity'], ['max_k_core', 'Max k-core'], ['faculty_in_max_core', 'Faculty in max core']];
  const mod = s => s === 'all three institutes' ? D.facNet.whole_network : D.facNet[s];
  $('#fn-metrics').innerHTML = `<div class="tbl-wrap"><table><thead><tr><th></th>${X.map(x => `<th class="r">${x.scope === 'all three institutes' ? 'All' : SHORT[I.indexOf(x.scope)]}</th>`).join('')}</tr></thead><tbody>${
    mrow.map(([k, l]) => `<tr><td>${l}</td>${X.map(x => `<td class="r num">${x[k]}</td>`).join('')}</tr>`).join('')}
    <tr><td>Avg clustering</td>${X.map(x => `<td class="r num">${mod(x.scope).avg_clustering}</td>`).join('')}</tr>
    <tr><td>Louvain communities (Q)</td>${X.map(x => `<td class="r num">${mod(x.scope).louvain.communities} (${mod(x.scope).louvain.modularity})</td>`).join('')}</tr>
    <tr><td>Leiden communities (Q)</td>${X.map(x => `<td class="r num">${mod(x.scope).leiden.communities} (${mod(x.scope).leiden.modularity})</td>`).join('')}</tr>
    <tr><td>Cross-department links</td>${X.map(x => `<td class="r num">${mod(x.scope)['cross_department_edges_%']}%</td>`).join('')}</tr>
    </tbody></table></div>`;
}
// rings and short tags around chosen nodes; returns a function that keeps them on the nodes while the layout moves
function addStars(g, items, on) {
  const grp = g.append('g').attr('class', 'stars').attr('pointer-events', 'none').style('display', on ? null : 'none');
  const ring = grp.selectAll('circle').data(items).join('circle').attr('fill', 'none').attr('stroke', css('--brand3')).attr('stroke-width', 3).attr('r', d => d.r + 5);
  const tag = grp.selectAll('text').data(items).join('text').text(d => d.tag).attr('font-size', 11.5).attr('font-weight', 700).attr('text-anchor', 'middle').attr('fill', css('--brandInk')).attr('paint-order', 'stroke').attr('stroke', css('--raise')).attr('stroke-width', 4);
  return () => { ring.attr('cx', d => d.node.x).attr('cy', d => d.node.y); tag.attr('x', d => d.node.x).attr('y', d => d.node.y - d.r - 9); };
}
const mergeStars = list => { const m = new Map(); list.forEach(s => { if (!s.node) return; const e = m.get(s.node.id); e ? e.tag += ' · ' + s.tag : m.set(s.node.id, { ...s }); }); return [...m.values()]; };
const fnX = l => F[l.source.id].i !== F[l.target.id].i;
function fnLinkBase() {
  const on = $('#fnCross')?.checked;
  fn.link.attr('stroke', l => on && fnX(l) ? css('--brand3') : css('--axis')).attr('stroke-opacity', l => on ? (fnX(l) ? 1 : .28) : .6)
    .attr('stroke-width', l => Math.min(6, .6 + Math.sqrt(l.w) * .7) + (on && fnX(l) ? 1.6 : 0) + (l === fn.starLink && $('#fnStar')?.checked ? 2.5 : 0));
}
function fnSelect(i) {
  fn.sel = i; fn.comm = null; if (!fn.node) return;
  if (i == null) { fn.node.attr('opacity', 1); fnLinkBase(); fn.label.attr('opacity', 1); return; }
  const nb = new Set([i, ...adj[i].map(a => a[0])]);
  fn.node.attr('opacity', d => nb.has(d.id) ? 1 : .1);
  fn.label.attr('opacity', d => nb.has(d.id) ? 1 : .08).style('display', d => nb.has(d.id) && $('#fnLab').checked ? null : 'none');
  fn.link.attr('stroke-opacity', l => l.source.id === i || l.target.id === i ? .95 : .04).attr('stroke', l => l.source.id === i || l.target.id === i ? css('--brand1') : css('--axis'));
}
function highlightComm(c) {
  fn.comm = c; if (!fn.node) return;
  fn.node.attr('opacity', d => F[d.id].lv === c ? 1 : .08);
  fn.label.attr('opacity', d => F[d.id].lv === c ? 1 : .05).style('display', d => F[d.id].lv === c && $('#fnLab').checked ? null : 'none');
  fn.link.attr('stroke-opacity', l => F[l.source.id].lv === c && F[l.target.id].lv === c ? .9 : .03).attr('stroke', css('--axis'));
}
function zoomToNodes(ns) {
  ns = ns.filter(n => n && n.x != null); if (!ns.length) return;
  const [x0, x1] = d3.extent(ns, n => n.x), [y0, y1] = d3.extent(ns, n => n.y);
  const k = Math.min(3, .8 / Math.max((x1 - x0 + 60) / fn.W, (y1 - y0 + 60) / fn.H));
  fn.svg.transition().duration(750).call(fn.zoom.transform, d3.zoomIdentity.translate(fn.W * (state.history.length ? .3 : .5), fn.H / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2));
}
function focusFaculty(i) {
  if (!adj[i].length) { openFaculty(i); return; }
  if (state.inst >= 0 && F[i].i !== state.inst) { state.inst = -1; buildInstSeg(); Object.keys(RENDER).forEach(t => state.dirty.add(t)); }
  if (!fn.byId?.has(i)) { $('#fnW').value = 1; state.dirty.add('collab'); }
  const needRender = !rendered.has('collab') || state.dirty.has('collab');
  fn.sel = i;
  const act = () => { fnSelect(i); zoomToNodes([i, ...adj[i].map(a => a[0])].map(k => fn.byId.get(k))); };
  if (needRender) fn.pending = act;
  go('collab');
  if (!needRender) act();
}
function focusCommunity(c, inPlace) {
  if (state.tab !== 'collab') { go('collab'); }
  fn.sel = null; highlightComm(c);
  const zoom = () => zoomToNodes(F.map((f, i) => i).filter(i => F[i].lv === c).map(i => fn.byId.get(i)));
  zoom();
  $('#fn-wrap').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
['fnColor', 'fnSize', 'fnW', 'fnIso', 'fnTop', 'fnCross', 'fnStar', 'fnLinks'].forEach(id => $('#' + id).addEventListener('input', () => { if (id === 'fnW') $('#fnWv').textContent = $('#fnW').value; clearTimeout(fn.t); fn.t = setTimeout(renderCollab, id === 'fnW' ? 200 : 0); }));
$('#fnLab').onchange = () => { if (fn.label) fn.label.style('display', d => $('#fnLab').checked ? null : 'none'); if (fn.sel != null) fnSelect(fn.sel); };
$('#fnReset').onclick = () => { if ($('#fnTop').value !== '0' || $('#fnLinks').value !== 'all') { $('#fnTop').value = '0'; $('#fnLinks').value = 'all'; renderCollab(); } fn.sel = null; fn.comm = null; fnSelect(null); fitView(fn, [...fn.byId.values()]); };
$('#facList').innerHTML = F.map(f => `<option value="${esc(f.n)} (${SHORT[f.i]})">`).join('');
$('#fnFind').addEventListener('change', e => { const v = e.target.value; const i = F.findIndex(f => `${f.n} (${SHORT[f.i]})` === v); if (i >= 0) { focusFaculty(i); openFaculty(i); e.target.value = ''; } });

// ================================================================ FLOWS
function renderFlows() {
  const sh = instsShown();
  plot('fl-ratio', sh.map(i => { const rs = D.ratio.filter(r => r.your_inst === I[i]); return { type: 'scatter', mode: 'lines+markers', name: I[i], x: rs.map(r => +r.year), y: rs.map(r => +r.in_over_out),
    line: { color: instColor(i), width: 2.5 }, marker: { size: 8, color: instColor(i), line: { color: css('--surface'), width: 2 } }, customdata: rs.map(r => [+r.in_cites, +r.out_cites]),
    hovertemplate: `${SHORT[i]} %{x}: ratio %{y:.2f}<br>in %{customdata[0]:,} · out %{customdata[1]:,}<extra></extra>` }; }),
    { xaxis: { dtick: 1, title: { text: 'Year' } }, yaxis: { rangemode: 'tozero', title: { text: 'Citations received ÷ citations given' } }, shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 1, y1: 1, line: { color: css('--muted'), width: 1, dash: 'dot' } }],
      annotations: [{ xref: 'paper', x: 0, y: 1, text: 'parity (in = out)', showarrow: false, yanchor: 'bottom', xanchor: 'left', font: { size: 11, color: css('--muted') } }] });

  plot('fl-vel', sh.map(i => { const rs = D.velocity.filter(r => r.institution === I[i] && r.table.startsWith('publication-year')); return { type: 'bar', name: I[i], x: rs.map(r => +r.year), y: rs.map(r => +r.value),
    marker: { color: instColor(i) }, hovertemplate: `${SHORT[i]} papers of %{x}: %{y:.2f} cites/paper/year<extra></extra>` }; }), { barmode: 'group', bargap: .25, xaxis: { dtick: 1, title: { text: 'Publication year of the papers' } }, yaxis: { title: { text: 'Citations per paper per year' } } });

  const clusters = [...new Set(D.flowCluster.map(r => r.cluster))];
  const traces = [];
  sh.forEach(i => ['incoming', 'outgoing'].forEach(dir => {
    const rs = D.flowCluster.filter(r => r.your_inst === I[i] && r.direction === dir), m = new Map(rs.map(r => [r.cluster, r]));
    traces.push({ type: 'bar', name: `${SHORT[i]} ${dir === 'incoming' ? 'cited by' : 'cites'}`, x: clusters, y: clusters.map(c => +(m.get(c)?.['share_%'] || 0)), customdata: clusters.map(c => +(m.get(c)?.citations || 0)),
      marker: { color: instColor(i), opacity: dir === 'incoming' ? 1 : .45, line: { color: instColor(i), width: dir === 'incoming' ? 0 : 1.5 } }, hovertemplate: `${SHORT[i]} ${dir}: %{x} %{y}% (%{customdata:,})<extra></extra>` });
  }));
  plot('fl-cluster', traces, { barmode: 'group', bargap: .2, yaxis: { ticksuffix: '%', type: 'log', title: { text: 'Share of citations (log scale)' } } });

  const lst = (id, src, key) => {
    const rows = sh.flatMap(i => src[I[i]].slice(0, sh.length === 1 ? 12 : 6).map(r => ({ ...r, i })));
    const agg = d3.rollups(rows, v => v, r => r[key]).map(([n, v]) => ({ n, v })).sort((a, b) => d3.sum(b.v, r => +r.citations) - d3.sum(a.v, r => +r.citations)).slice(0, 14).reverse();
    plot(id, sh.map(i => ({ type: 'bar', orientation: 'h', name: I[i], y: agg.map(a => a.n.replace('Indian Institute of Technology', 'IIT').replace(' University', ' Univ.') + ' '), x: agg.map(a => +(a.v.find(r => r.i === i)?.citations || 0)),
      marker: { color: instColor(i), line: { color: css('--surface'), width: 1 } }, hovertemplate: `${SHORT[i]}: %{x:,} citations<extra>%{y}</extra>` })), { barmode: 'stack', bargap: .3, legend: { orientation: 'h', x: 1, xanchor: 'right', y: 1.02, yanchor: 'bottom', traceorder: 'normal' }, margin: { t: 34, l: lm(agg.map(a => a.n.replace('Indian Institute of Technology', 'IIT').replace(' University', ' Univ.'))), r: 10, t: 10, b: 30 } });
  };
  lst('fl-in', D.incoming, 'citing_inst'); lst('fl-out', D.outgoing, 'cited_inst');

  const pr = sh.flatMap(i => D.partners[I[i]].slice(0, sh.length === 1 ? 15 : 8).map(r => ({ ...r, i }))).sort((a, b) => a.shared_papers - b.shared_papers);
  $('#fl-partners').style.height = Math.max(380, pr.length * 21 + 70) + 'px';
  plot('fl-partners', [{ type: 'bar', orientation: 'h', y: pr.map(r => `${r.partner_inst.replace('Indian Institute of Technology', 'IIT').replace('National Institute of Technology', 'NIT')} · ${SHORT[r.i]}`), x: pr.map(r => +r.shared_papers),
    marker: { color: pr.map(r => instColor(r.i)) }, customdata: pr.map(r => +r.total_citations), hovertemplate: '%{y}<br>%{x} shared papers · %{customdata:,} citations<extra></extra>' }],
    { margin: { l: lm(pr.map(r => r.partner_inst.replace('Indian Institute of Technology', 'IIT').replace('National Institute of Technology', 'NIT') + ' · NITS')), r: 14, t: 4, b: 30 }, bargap: .25, xaxis: { title: { text: 'Co-authored papers' } } },
    ev => { const n = ev.points[0].y.split(' · ')[0]; const full = L && L.partners.find(r => abbr(r[PT.name]) === n || r[PT.name] === n); if (full) openPartner(full[PT.name]); });
  renderFlowsExtra();
}
function renderFlowsExtra() {
  if (!L || !L.partnerRes) return;
  const sh = instsShown(), PR = L.partnerRes;
  const agg = new Map();
  sh.forEach(i => (PR[I[i]]?.cross_cluster || []).forEach(r => { const o = agg.get(r.partner_cluster) || { sp: 0, cf: 0, ct: 0, n: 0 }; o.sp += r.shared_papers; o.cf += r.cites_from_partner; o.ct += r.cites_to_partner; o.n += r.partners; agg.set(r.partner_cluster, o); }));
  const cls = [...agg].sort((a, b) => b[1].sp - a[1].sp).map(d => d[0]).reverse();
  plot('fl-types', [['Joint papers', 'sp', '--c1'], ['Other institutes cite the institutes’ papers', 'cf', '--c3'], ['The institutes’ papers cite other institutes', 'ct', '--c2']].map(([n, k, c]) => ({
    type: 'bar', orientation: 'h', name: n, y: cls, x: cls.map(cl => agg.get(cl)[k]), customdata: cls.map(cl => agg.get(cl).n), marker: { color: css(c) },
    hovertemplate: `%{y} (%{customdata} institutes) · ${n}: %{x:,}<extra></extra>` })),
    { barmode: 'group', bargap: .25, bargroupgap: .05, margin: { l: lm(cls), r: 14, t: 56, b: 44 }, xaxis: { type: 'log', title: { text: 'Count (log scale)' } }, legend: { orientation: 'h', y: 1.02, yanchor: 'bottom', x: 0 } },
    ev => openTypeDrawer(`${ev.points[0].y}|`));
  const pts = L.partners.filter(r => sh.includes(r[PT.i]) && r[PT.wj] != null);
  const rho = sh.map(i => { const s = PR[I[i]]?.similarity_vs_shared_papers_spearman; return s ? `${SHORT[i]} ρ = ${s.rho} (p = ${s.p})` : ''; }).filter(Boolean).join(' · ');
  $('#fl-jacnote').textContent = rho ? `Rank correlation between similarity and joint papers: ${rho}` : '';
  plot('fl-jac', sh.map(i => { const rs = pts.filter(r => r[PT.i] === i); return { type: 'scatter', mode: 'markers', name: I[i], x: rs.map(r => r[PT.wj]), y: rs.map(r => r[PT.papers]), customdata: rs.map(r => r[PT.name]),
    marker: { size: 10, color: instColor(i), opacity: .8, line: { color: css('--surface'), width: 1.5 } }, hovertemplate: `%{customdata}<br>${SHORT[i]} · similarity %{x:.2f} · %{y} joint papers<extra></extra>` }; }),
    { xaxis: { title: { text: 'Research-topic similarity (weighted Jaccard of subfields, 0–1)' } }, yaxis: { type: 'log', title: { text: 'Joint papers (log scale)' } } },
    ev => openPartner(ev.points[0].customdata));
}


// ================================================================ METHOD
function renderMethod() {
  const steps = [
    ['Collect', 'Every 2016–2026 paper with at least one author from MANIT Bhopal, NIT Jamshedpur or NIT Silchar, taken from OpenAlex.'],
    ['Clean', 'Errata, retractions and duplicate records removed. Only journal articles and conference papers kept.'],
    ['Verify faculty', 'Authors matched to the official faculty lists, including former faculty found on archived department pages. Students, staff and visitors removed. Matches checked by hand.'],
    ['Rank venues', 'Journals ranked Q1–Q4 with SCImago. Conference proceedings ranked by their Scopus CiteScore quartile, and by CORE 2023 where listed.'],
    ['Build networks', 'A citation network between the institutes’ papers, a co-authorship network between faculty, and links with other Indian institutes.'],
  ];
  $('#pipe').innerHTML = steps.map(([b, p], k) => `<div class="step"><div class="n">${k + 1}</div><b>${b}</b><p>${p}</p></div>`).join('');
  const fun = D.funnel;
  Plotly.react('md-funnel', [{ type: 'funnel', y: fun.map(f => f[0]), x: fun.map(f => f[1]), textinfo: 'value+percent initial', texttemplate: '%{value:,} (%{percentInitial:.0%})',
    marker: { color: [css('--c7'), css('--c1'), css('--c3'), css('--c4'), css('--c5')] }, connector: { line: { color: css('--axis'), width: 1 } }, textfont: { color: '#fff', size: 12 },
    hovertemplate: '%{y}: %{x:,} records (%{percentInitial:.1%} of the download)<extra></extra>' }],
    baseLayout({ margin: { l: lm(fun.map(f => f[0])), r: 20, t: 4, b: 44 }, xaxis: { title: { text: 'Number of records' } }, yaxis: { title: { text: '' } } }), { displayModeBar: false, responsive: true });
  const src = D.qsrc;
  plot('md-qsrc', [{ type: 'bar', orientation: 'h', y: src.map(s => s[0]).reverse(), x: src.map(s => s[1]).reverse(), marker: { color: css('--c1') }, text: src.map(s => fmt(s[1])).reverse(), textposition: 'outside', cliponaxis: false, textfont: { color: css('--ink2') }, hovertemplate: '%{y}: %{x:,} paper rows<extra></extra>' }],
    { margin: { l: lm(src.map(s => s[0])), r: 50, t: 4, b: 44 }, bargap: .3, xaxis: { type: 'log', title: { text: 'Paper rows ranked this way (log scale)' } } });
  $('#limits').innerHTML = `<ul style="margin:0;padding-left:18px;color:var(--ink2)">
    <li>Quartiles marked "estimated" are not official ranks (tested: 58% exact, 96% within one quartile). IF &gt; 5 / &gt; 10 are not the Clarivate impact factor (not free). They use the lower of SCImago citations per document and OpenAlex 2-year mean citedness: SCImago alone runs well above the real IF for new or fast-growing journals, so a paper is flagged only when both sources clear the threshold. A * in the top-30 table marks journals where the two sources disagree.</li>
    <li>2026 is a partial year. Recent papers have had less time to collect citations, so compare yearly ratios with care.</li>
    <li>Affiliation-based counting: a paper counts for an institute when a verified faculty member lists it. Faculty who publish under another affiliation are partly missed.</li>
    <li>Most conference papers appear in book series (for example Springer Lecture Notes). Few of these venues are in the CORE list, so CORE ranks are rare.</li>
    <li>Topic similarity (Jaccard) is computed for each institute's top 25 partners.</li></ul>`;
}

// ================================================================ REACH & LOCALITY
const L = D.loc || null;
const LOCS = ['Same state', 'Same region', 'Other region', 'National body', 'Unknown'];
const locColor = l => css({ 'Same state': '--q1', 'Same region': '--q2', 'Other region': '--q3', 'National body': '--c7', 'Unknown': '--qu' }[l]);
const CL_ORDER = ['IIT', 'NIT', 'IIIT', 'Central university', 'Other university/college', 'CSIR', 'DAE', 'Industry'];
const clColor = c => { const k = CL_ORDER.indexOf(c); return k >= 0 ? CAT()[k] : css('--other'); };
const clFold = c => CL_ORDER.includes(c) ? c : 'Other types';
const PEER = ['NIT', 'IIT', 'IIIT', 'IISER', 'IISc'];
const LABS = ['CSIR', 'DAE', 'DRDO', 'ISRO', 'ICAR', 'ICMR', 'Premier science inst.'];
const facByName = new Map(F.map((f, i) => [f.i + '|' + f.n, i]));
const PT = { i: 0, name: 1, papers: 2, cites: 3, cl: 4, state: 5, region: 6, loc: 7, fy: 8, ly: 9, nfac: 10, topfac: 11, jac: 12, wj: 13, years: 14, cf: 15, ct: 16 };
const pl = r => fullYears() ? r[PT.papers] : sumYears(r[PT.years]);   // joint papers in the year range
const partnerRows = () => L ? L.partners.filter(r => instsShown().includes(r[PT.i]) && pl(r) > 0) : [];
const clMatch = (r, cl) => !cl || (cl === 'Other types' ? clFold(r[PT.cl]) === 'Other types' : cl === 'University/college' ? /university/i.test(r[PT.cl]) : r[PT.cl] === cl || (cl === 'Premier science inst.' && r[PT.cl] === 'IISc'));
let rcTable, rcFilter = {};
const sameIn = new Int32Array(P.length);
D.cedges.forEach(([s, t]) => { if (P[s][T.mask] & P[t][T.mask]) sameIn[t]++; });
const abbr = s => s.replace('Indian Institute of Technology', 'IIT').replace('National Institute of Technology', 'NIT').replace('Indian Institute of Information Technology', 'IIIT').replace(' University', ' Univ.');

function openPartner(name) {
  const rows = L.partners.filter(r => r[PT.name] === name);
  if (!rows.length) return;
  const r0 = rows[0], ps = (L.partnerPapers[name] || []).slice().sort((a, b) => P[b][T.cites] - P[a][T.cites]);
  const yrs = YEARS.map((y, k) => d3.sum(rows, r => r[PT.years][k]));
  const fc = new Map();
  ps.forEach(p => D.pfac[p].forEach(f => fc.set(f, (fc.get(f) || 0) + 1)));
  const fl = [...fc].sort((a, b) => b[1] - a[1]);
  const cf = d3.sum(rows, r => r[PT.cf] || 0), ct = d3.sum(rows, r => r[PT.ct] || 0);
  const html = `
    <div class="chips"><span class="chip"><span class="dot" style="background:${clColor(r0[PT.cl])}"></span>${esc(r0[PT.cl])}</span><span class="chip">${esc(r0[PT.state])}${r0[PT.region] !== r0[PT.state] ? ' · ' + esc(r0[PT.region]) : ''}</span></div>
    <h3>${esc(name)}</h3>
    <div class="note">Indian partner institute · co-authorship with our faculty, ${d3.min(rows, r => r[PT.fy])}–${d3.max(rows, r => r[PT.ly])}</div>
    <h4>Links with our institutes</h4>
    <div class="stats">${rows.map(r => `<div class="stat"><div class="v num">${r[PT.papers]}</div><div class="l">${SHORT[r[PT.i]]} joint papers · ${esc(r[PT.loc].toLowerCase())}</div></div>`).join('')}
      <div class="stat"><div class="v num">${fmt(d3.sum(rows, r => r[PT.cites]))}</div><div class="l">citations of joint papers</div></div>
      <div class="stat"><div class="v num">${fmt(cf)}</div><div class="l">times they cite our papers</div></div>
      <div class="stat"><div class="v num">${fmt(ct)}</div><div class="l">times our papers cite them</div></div>
      ${rows.some(r => r[PT.wj] != null) ? `<div class="stat"><div class="v num">${rows.filter(r => r[PT.wj] != null).map(r => fmt2(r[PT.wj])).join(' / ')}</div><div class="l">topic similarity (weighted Jaccard, 0–1)</div></div>` : ''}</div>
    <h4>Joint papers per year</h4><div id="drPY" style="height:140px"></div>
    <h4>Faculty of the three institutes on these papers (${fl.length})</h4>
    <div class="chips">${fl.map(([f, c]) => `<span class="chip click" data-f="${f}"><span class="dot" style="background:${instColor(F[f].i)}"></span>${esc(F[f].n)} · ${c}</span>`).join('')}</div>
    <h4>Joint papers (${ps.length}) · most cited first</h4>
    <div class="plist">${ps.slice(0, 25).map(p => paperRow(p)).join('')}</div>`;
  showDrawer(html, 'Partner institute', ['i', name]);
  Plotly.react('drPY', [{ type: 'bar', x: YEARS, y: yrs, marker: { color: clColor(r0[PT.cl]) }, hovertemplate: '%{x}: %{y} papers<extra></extra>' }],
    baseLayout({ margin: { l: 28, r: 6, t: 4, b: 24 }, xaxis: { dtick: 2 }, bargap: .25 }), { displayModeBar: false, responsive: true });
}
// a partner institute abroad: joint papers and our faculty on them
function openForeign(name) {
  const rows = (L.foreign || []).filter(r => r[1] === name);
  if (!rows.length) return;
  const ps = (L.foreignPapers[name] || []).slice().sort((a, b) => P[b][T.cites] - P[a][T.cites]);
  const fc = new Map(); ps.forEach(p => D.pfac[p].forEach(f => fc.set(f, (fc.get(f) || 0) + 1)));
  const fl = [...fc].sort((a, b) => b[1] - a[1]);
  const yrs = YEARS.map(y => ps.filter(p => P[p][T.year] === y).length);
  const html = `
    <div class="chips"><span class="chip">Abroad${rows[0][2] ? ' · ' + esc(rows[0][2]) : ''}</span></div>
    <h3>${esc(name)}</h3>
    <div class="note">Partner institute abroad · joint papers with our faculty</div>
    <h4>Links with our institutes</h4>
    <div class="stats">${rows.map(r => `<div class="stat"><div class="v num">${r[3]}</div><div class="l">${SHORT[r[0]]} joint papers</div></div>`).join('')}
      <div class="stat"><div class="v num">${fmt(d3.sum(rows, r => r[4]))}</div><div class="l">citations of joint papers</div></div></div>
    <h4>Joint papers per year</h4><div id="drPY" style="height:140px"></div>
    <h4>Faculty of the three institutes on these papers (${fl.length})</h4>
    <div class="chips">${fl.map(([f, c]) => `<span class="chip click" data-f="${f}"><span class="dot" style="background:${instColor(F[f].i)}"></span>${esc(F[f].n)} · ${c}</span>`).join('') || '<span class="note">—</span>'}</div>
    <h4>Joint papers (${ps.length}) · most cited first</h4>
    <div class="plist">${ps.slice(0, 25).map(p => paperRow(p)).join('')}</div>`;
  showDrawer(html, 'Partner abroad', ['x', name]);
  Plotly.react('drPY', [{ type: 'bar', x: YEARS, y: yrs, marker: { color: css('--c5') }, hovertemplate: '%{x}: %{y} papers<extra></extra>' }],
    baseLayout({ margin: { l: 28, r: 6, t: 4, b: 24 }, xaxis: { dtick: 2 }, bargap: .25 }), { displayModeBar: false, responsive: true });
}
// all partner institutes of one type (from the Sankey, the flows chart or a legend)
function openTypeDrawer(key) {
  const [cl, inst] = key.split('|'), ii = inst === '' || inst == null ? -1 : +inst;
  const rows = L.partners.filter(r => clMatch(r, cl) && pl(r) > 0 && (ii < 0 ? instsShown().includes(r[PT.i]) : r[PT.i] === ii));
  const by = d3.rollups(rows, v => v, r => r[PT.name]).map(([n, v]) => ({ n, v, tot: d3.sum(v, pl) })).sort((a, b) => b.tot - a.tot);
  const title = (cl || 'All partner types') + (ii >= 0 ? ` · ${I[ii]}` : '');
  const shown = by.slice(0, 40).reverse();
  showDrawer(`<div class="chips"><span class="chip"><span class="dot" style="background:${clColor(cl)}"></span>${esc(cl || 'All types')}</span>${ii >= 0 ? instChip(ii) : ''}${fullYears() ? '' : `<span class="chip">${yrLabel()}</span>`}</div>
    <h3>${esc(title)}</h3>
    <div class="stats" style="margin-top:12px"><div class="stat"><div class="v num">${fmt(by.length)}</div><div class="l">institutes</div></div>
      <div class="stat"><div class="v num">${fmt(d3.sum(by, b => b.tot))}</div><div class="l">joint-paper links</div></div>
      <div class="stat"><div class="v num">${fmt(by.filter(b => new Set(b.v.map(r => r[PT.i])).size > 1).length)}</div><div class="l">shared by 2+ of our institutes</div></div></div>
    <h4>Institutes by joint papers${by.length > 40 ? ' (top 40)' : ''} · click a bar for details</h4><div id="drType" style="height:${Math.max(220, shown.length * 22 + 60)}px"></div>
    ${by.length > 40 ? `<h4>All ${by.length} institutes</h4><div class="chips">${by.slice(40).map(b => `<span class="chip click" data-i="${esc(b.n)}">${esc(b.n)} · ${b.tot}</span>`).join('')}</div>` : ''}`,
    'Partner type', ['t', key]);
  Plotly.react('drType', [0, 1, 2].filter(i => ii < 0 ? instsShown().includes(i) : i === ii).map(i => ({ type: 'bar', orientation: 'h', name: SHORT[i], y: shown.map(b => abbr(b.n) + ' '), customdata: shown.map(b => b.n),
    x: shown.map(b => d3.sum(b.v.filter(r => r[PT.i] === i), pl)), marker: { color: instColor(i) }, hovertemplate: `%{customdata} · ${SHORT[i]}: %{x} joint papers<extra></extra>` })),
    baseLayout({ barmode: 'stack', bargap: .25, margin: { l: lm(shown.map(b => abbr(b.n))), r: 10, t: 24, b: 40 }, xaxis: { title: { text: 'Joint papers' } }, legend: { orientation: 'h', y: 1.06, x: 0 } }), { displayModeBar: false, responsive: true });
  $('#drType').on('plotly_click', ev => openPartner(ev.points[0].customdata));
}
// partners shared by a given combination of our institutes (bitmask)
function openSharedDrawer(key) {
  const mask = +key, members = [0, 1, 2].filter(i => mask & (1 << i));
  const sets = sharedSets(), names = sets.byMask.get(mask) || [];
  const rows = names.map(n => ({ n, v: L.partners.filter(r => r[PT.name] === n && pl(r) > 0) })).sort((a, b) => d3.sum(b.v, pl) - d3.sum(a.v, pl));
  showDrawer(`<div class="chips">${members.map(instChip).join('')}${fullYears() ? '' : `<span class="chip">${yrLabel()}</span>`}</div>
    <h3>${members.length > 1 ? 'Partners shared by ' + members.map(i => SHORT[i]).join(' + ') : 'Partners of ' + SHORT[members[0]] + ' only'}</h3>
    <p class="note">${fmt(rows.length)} Indian institutes. Click one for its joint papers and faculty.</p>
    <div class="tbl-wrap"><table><thead><tr><th>Institute</th><th>Type</th>${members.map(i => `<th class="r">${SHORT[i]}</th>`).join('')}</tr></thead><tbody>${
      rows.slice(0, 150).map(r => `<tr class="row" data-i="${esc(r.n)}"><td>${esc(r.n)}</td><td class="s">${esc(r.v[0][PT.cl])}</td>${members.map(i => `<td class="r num">${d3.sum(r.v.filter(x => x[PT.i] === i), pl)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`,
    'Shared partners', ['s', key]);
}
function sharedSets() {
  const m = new Map();
  L.partners.forEach(r => { if (pl(r) > 0) m.set(r[PT.name], (m.get(r[PT.name]) || 0) | (1 << r[PT.i])); });
  const byMask = new Map(); m.forEach((mask, n) => { if (!byMask.has(mask)) byMask.set(mask, []); byMask.get(mask).push(n); });
  return { m, byMask };
}
function openExternal(r) {
  const names = r.faculty.split('; ');
  const ids = names.map(n => F.findIndex(f => f.n === n && r.our_institutes.includes(I[f.i]))).filter(i => i >= 0);
  showDrawer(`<div class="chips"><span class="chip">${esc(r.country || 'country unknown')}</span><span class="chip">outside author</span></div>
    <h3>${esc(r.author)}</h3><div class="note">${esc(r.institution)}</div>
    <div class="stats" style="margin-top:12px"><div class="stat"><div class="v num">${r.faculty_connected}</div><div class="l">of our faculty co-author with them</div></div>
    <div class="stat"><div class="v num">${r.coauthors_total}</div><div class="l">co-authors on our papers</div></div><div class="stat"><div class="v num">${(+r.betweenness_full_network).toFixed(4)}</div><div class="l">betweenness (full network)</div></div></div>
    <h4>Our faculty connected</h4><div class="chips">${ids.map(f => `<span class="chip click" data-f="${f}"><span class="dot" style="background:${instColor(F[f].i)}"></span>${esc(F[f].n)}</span>`).join('')}</div>
    ${r.faculty_connected > names.length ? `<p class="note">and ${r.faculty_connected - names.length} more</p>` : ''}`, 'Outside author', null);
}

// ---------------------------------------------------------------- institute network: the three institutes + their partners
const inet = { focus: -1 };
function drawInstNet() {
  if (!L) return;
  const mode = $('#inPart').value, min = +$('#inMin').value, colorBy = $('#inColor').value;
  $('#inMinv').textContent = min;
  const sh = instsShown();
  const agg = new Map();
  L.partners.forEach(r => {
    const w = pl(r); if (!w) return;
    const ok = mode === 'peer' ? PEER.includes(r[PT.cl]) : mode === 'labs' ? PEER.includes(r[PT.cl]) || LABS.includes(r[PT.cl]) : true;
    if (!ok) return;
    const a = agg.get(r[PT.name]) || { name: r[PT.name], cl: r[PT.cl], w: [0, 0, 0], loc: {}, foreign: false }; a.w[r[PT.i]] += w; a.loc[r[PT.i]] = r[PT.loc]; agg.set(r[PT.name], a);
  });
  if (mode === 'world' && fullYears()) (L.foreign || []).forEach(([i, n, cc, w]) => { const a = agg.get(n) || { name: n, cl: 'Abroad', country: cc, w: [0, 0, 0], loc: {}, foreign: true }; a.w[i] += w; agg.set(n, a); });
  let parts = [...agg.values()].filter(a => sh.some(i => a.w[i] > 0)).map(a => ({ ...a, tot: d3.sum(sh, i => a.w[i]), k: [0, 1, 2].filter(i => a.w[i] > 0).length }))
    .filter(a => a.tot >= min).sort((a, b) => b.tot - a.tot).slice(0, 260);
  const svg = d3.select('#in-svg'); svg.selectAll('*').remove();
  const wrap = $('#in-wrap'); wrap.querySelector('.cn-empty')?.remove();
  const { width: W, height: H } = wrap.getBoundingClientRect();
  const cx = W / 2, cy = H / 2 + 10, R0 = Math.min(W, H) * .3;
  const ours = [0, 1, 2].map(i => ({ id: 'I' + i, our: i, fx: cx + R0 * Math.cos(-Math.PI / 2 + i * 2 * Math.PI / 3), fy: cy + R0 * Math.sin(-Math.PI / 2 + i * 2 * Math.PI / 3) }));
  const pnodes = parts.map(a => ({ id: 'P' + a.name, a }));
  const nodes = [...ours, ...pnodes], byId = new Map(nodes.map(n => [n.id, n]));
  const links = [];
  pnodes.forEach(n => [0, 1, 2].forEach(i => { if (n.a.w[i] > 0) links.push({ source: 'I' + i, target: n.id, w: n.a.w[i], i }); }));
  const J = L.between.joint_papers, jp = (a, b) => J[`${I[Math.min(a, b)]} & ${I[Math.max(a, b)]}`] || 0;
  const ourLinks = [[0, 1], [0, 2], [1, 2]].map(([a, b]) => ({ source: 'I' + a, target: 'I' + b, w: jp(a, b), our: true }));
  const rP = d3.scaleSqrt().domain([0, d3.max(pnodes, n => n.a.tot) || 1]).range([3.5, 18]);
  const shareCol = k => [css('--other'), css('--c2'), css('--c8')][k - 1];
  const colorOf = a => colorBy === 'type' ? (a.foreign ? css('--c5') : clColor(a.cl)) : colorBy === 'loc' ? (a.foreign ? css('--c5') : locColor(a.loc[[0, 1, 2].sort((x, y) => a.w[y] - a.w[x])[0]] || 'Unknown')) : shareCol(a.k);
  const shared2 = parts.filter(a => a.k >= 2).length, shared3 = parts.filter(a => a.k === 3).length;
  $('#in-stats').innerHTML = `<b class="num">${fmt(parts.length)}</b> partner institutes shown<br><span class="note">${fmt(shared2)} shared by 2+ institutes · ${fmt(shared3)} by all three</span>${mode === 'world' && !fullYears() ? '<br><span class="note">Partners abroad shown for all years only</span>' : ''}`;
  const legend = colorBy === 'type' ? [...CL_ORDER.map(c => [clColor(c), c]), [css('--other'), 'Other types'], ...(mode === 'world' ? [[css('--c5'), 'Abroad']] : [])]
    : colorBy === 'loc' ? LOCS.map(l => [locColor(l), l]).concat(mode === 'world' ? [[css('--c5'), 'Abroad']] : [])
    : [[shareCol(1), 'Works with one institute'], [shareCol(2), 'Shared by two institutes'], [shareCol(3), 'Shared by all three']];
  $('#in-legend').innerHTML = `<div class="lg-t">Colour = ${{ type: 'partner type', loc: 'distance from home state', shared: 'how many of the three institutes it works with' }[colorBy]}</div>` +
    legend.map(([c, l]) => `<div><span class="dot" style="background:${c}"></span>${esc(l)}</div>`).join('') + `<div class="lg-s">${$('#inStar')?.checked ? 'Ring = standout: the top partner and the three biggest partners that work with all three institutes<br>' : ''}Big circles = the three institutes · node size = joint papers · line width = joint papers with that institute · dashed = joint papers between the three institutes</div>`;
  if (!parts.length) { wrap.insertAdjacentHTML('beforeend', '<div class="cn-empty"><b>No partners above this threshold</b><p>Lower "Min joint papers" or widen the year range.</p></div>'); }
  const g = svg.append('g');
  const zoom = d3.zoom().scaleExtent([.3, 6]).on('zoom', e => { g.attr('transform', e.transform); g.selectAll('.stars text').attr('font-size', 11.5 / e.transform.k).attr('stroke-width', 4 / e.transform.k); g.selectAll('.stars circle').attr('stroke-width', 3 / e.transform.k); lab.style('display', d => showLab(d, e.transform.k) ? null : 'none'); });
  svg.call(zoom).on('dblclick.zoom', null);
  inet.zoom = zoom; inet.svg = svg;
  const link = g.append('g').selectAll('line').data(links).join('line').attr('stroke', d => instColor(d.i)).attr('stroke-opacity', .28).attr('stroke-width', d => Math.min(7, .5 + Math.sqrt(d.w) * .45));
  const ol = g.append('g').selectAll('line').data(ourLinks).join('line').attr('stroke', css('--brandInk')).attr('stroke-width', d => 1.5 + Math.sqrt(d.w) * .6).attr('stroke-dasharray', '6 4').attr('stroke-opacity', .9);
  const olt = g.append('g').selectAll('text').data(ourLinks).join('text').text(d => `${d.w} joint papers`).attr('font-size', 11).attr('text-anchor', 'middle').attr('fill', css('--brandInk')).attr('paint-order', 'stroke').attr('stroke', css('--raise')).attr('stroke-width', 3);
  const topLab = new Set(pnodes.slice().sort((a, b) => b.a.tot - a.a.tot).slice(0, 26).map(n => n.id));
  const showLab = (d, k) => d.our != null || ($('#inLab').checked && (topLab.has(d.id) || k > 1.8));
  const node = g.append('g').selectAll('circle').data(nodes).join('circle')
    .attr('r', d => d.our != null ? 26 : rP(d.a.tot)).attr('fill', d => d.our != null ? instColor(d.our) : colorOf(d.a)).attr('stroke', css('--surface')).attr('stroke-width', d => d.our != null ? 3 : 1.2).style('cursor', 'pointer')
    .on('mouseenter', (e, d) => tip(e, d.our != null ? `<b>${I[d.our]}</b><div class="m">${fmt(parts.filter(a => a.w[d.our] > 0).length)} partners in view · click to highlight them</div>`
      : `<b>${esc(d.a.name)}</b><div class="m">${d.a.foreign ? 'Abroad' + (d.a.country ? ' · ' + d.a.country : '') : esc(d.a.cl)}</div><div class="m">${[0, 1, 2].filter(i => d.a.w[i]).map(i => `${SHORT[i]} ${d.a.w[i]}`).join(' · ')} joint papers</div>`))
    .on('mousemove', moveTip).on('mouseleave', hideTip)
    .on('click', (e, d) => { e.stopPropagation(); if (d.our != null) { inet.focus = inet.focus === d.our ? -1 : d.our; focusInst(); } else if (!d.a.foreign) openPartner(d.a.name); else openForeign(d.a.name); })
    .call(d3.drag().on('start', (e, d) => { if (d.our != null) return; if (!e.active) sim.alphaTarget(.2).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { if (d.our != null) return; d.fx = e.x; d.fy = e.y; }).on('end', (e, d) => { if (d.our != null) return; if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
  const inStarOn = !!$('#inStar')?.checked, topP = pnodes.slice().sort((p, q) => q.a.tot - p.a.tot)[0], all3 = pnodes.filter(n => n.a.k === 3).sort((p, q) => q.a.tot - p.a.tot).slice(0, 3);
  const iS = (node, tag) => node && ({ node, tag: tag === 'Top partner' ? `Top partner: ${abbr(node.a.name)}` : abbr(node.a.name), r: rP(node.a.tot) });
  const inStarUp = addStars(g, mergeStars([iS(topP, 'Top partner'), ...all3.map(n => iS(n, 'Works with all three'))].filter(Boolean)), inStarOn);
  const lab = g.append('g').selectAll('text').data(nodes).join('text').text(d => d.our != null ? SHORT[d.our] : abbr(d.a.name))
    .attr('font-size', d => d.our != null ? 13 : 10).attr('font-weight', d => d.our != null ? 700 : 400).attr('text-anchor', d => d.our != null ? 'middle' : 'start')
    .attr('fill', d => d.our != null ? '#fff' : css('--ink')).attr('paint-order', 'stroke').attr('stroke', d => d.our != null ? 'none' : css('--raise')).attr('stroke-width', 3)
    .attr('dx', d => d.our != null ? 0 : rP(d.a.tot) + 3).attr('dy', d => d.our != null ? 4.5 : 3.5).attr('pointer-events', 'none').style('display', d => showLab(d, 1) ? null : 'none');
  svg.on('click', () => { inet.focus = -1; focusInst(); });
  function focusInst() {
    const f = inet.focus;
    node.attr('opacity', d => f < 0 || d.our != null || d.a.w[f] > 0 ? 1 : .12);
    link.attr('stroke-opacity', d => f < 0 ? .28 : d.i === f ? .6 : .03);
    lab.attr('opacity', d => f < 0 || d.our != null || d.a.w[f] > 0 ? 1 : .1);
  }
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink([...links]).id(d => d.id).distance(d => 60 + 180 / Math.sqrt(d.w)).strength(d => .2 + Math.min(.6, d.w / 60)))
    .force('charge', d3.forceManyBody().strength(-26))
    .force('collide', d3.forceCollide(d => d.our != null ? 34 : rP(d.a.tot) + 2))
    .on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      ol.attr('x1', d => byId.get(d.source).fx).attr('y1', d => byId.get(d.source).fy).attr('x2', d => byId.get(d.target).fx).attr('y2', d => byId.get(d.target).fy);
      olt.attr('x', d => (byId.get(d.source).fx + byId.get(d.target).fx) / 2).attr('y', d => (byId.get(d.source).fy + byId.get(d.target).fy) / 2 - 6);
      node.attr('cx', d => d.x).attr('cy', d => d.y); lab.attr('x', d => d.x).attr('y', d => d.y); inStarUp();
    });
  sim.stop().tick(260); sim.on('tick')();
  inet.sim = sim; focusInst();
}
['inPart', 'inMin', 'inColor', 'inStar'].forEach(id => $('#' + id)?.addEventListener('input', () => { clearTimeout(inet.t); inet.t = setTimeout(drawInstNet, id === 'inMin' ? 200 : 0); }));
$('#inLab') && ($('#inLab').onchange = drawInstNet);
$('#inReset') && ($('#inReset').onclick = () => { inet.focus = -1; inet.svg?.transition().duration(500).call(inet.zoom.transform, d3.zoomIdentity); drawInstNet(); });

// ---------------------------------------------------------------- how connected are the three?
function drawConnected() {
  const pairs = [[0, 1], [0, 2], [1, 2]];
  const J = L.between.joint_papers, jp = (a, b) => J[`${I[Math.min(a, b)]} & ${I[Math.max(a, b)]}`] || 0;
  const flinks = (a, b) => D.fedges.filter(([x, y]) => (F[x].i === a && F[y].i === b) || (F[x].i === b && F[y].i === a)).length;
  const M = D.citNet.flow_matrix_source_rows_target_cols;
  const { m } = sharedSets(), set = i => new Set([...m].filter(([, mask]) => mask & (1 << i)).map(([n]) => n));
  const sets = [0, 1, 2].map(set);
  const inter = (a, b) => [...sets[a]].filter(n => sets[b].has(n)).length, uni = (a, b) => new Set([...sets[a], ...sets[b]]).size;
  const jac = (a, b) => { const o = L.jacOurs[`${I[a]} vs ${I[b]}`] || L.jacOurs[`${I[b]} vs ${I[a]}`]; return o ? fmt2(o.weighted_jaccard) : '—'; };
  const rows = [
    ['Joint papers', (a, b) => fmt(jp(a, b))],
    ['Faculty co-authorship links', (a, b) => fmt(flinks(a, b))],
    ['Citations (first cites second / second cites first)', (a, b) => `${fmt(M[I[a]][I[b]])} / ${fmt(M[I[b]][I[a]])}`],
    ['Shared Indian partner institutes', (a, b) => fmt(inter(a, b))],
    ['Partner overlap (shared ÷ all partners of the two)', (a, b) => fmt1(100 * inter(a, b) / (uni(a, b) || 1)) + '%'],
    ['Research-topic similarity (weighted Jaccard, 0–1)', jac],
  ];
  $('#rc-pairs').innerHTML = `<div class="tbl-wrap"><table><thead><tr><th></th>${pairs.map(([a, b]) => `<th class="r">${SHORT[a]} – ${SHORT[b]}</th>`).join('')}</tr></thead><tbody>${
    rows.map(([l, f]) => `<tr><td>${l}</td>${pairs.map(([a, b]) => `<td class="r num">${f(a, b)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const combos = [[1], [2], [4], [3], [5], [6], [7]].map(([mk]) => mk);
  const name = mk => [0, 1, 2].filter(i => mk & (1 << i)).map(i => SHORT[i]).join(' + ') + ([1, 2, 4].includes(mk) ? ' only' : '');
  const cnt = mk => [...m.values()].filter(v => v === mk).length;
  plot('rc-upset', [{ type: 'bar', x: combos.map(name), y: combos.map(cnt), customdata: combos, marker: { color: combos.map(mk => [1, 2, 4].includes(mk) ? instColor([1, 2, 4].indexOf(mk)) : mk === 7 ? css('--c8') : css('--c7')) },
    text: combos.map(cnt), textposition: 'outside', cliponaxis: false, textfont: { color: css('--ink2') }, hovertemplate: '%{x}: %{y} partner institutes<extra></extra>' }],
    { bargap: .3, margin: { l: 50, r: 10, t: 14, b: 70 }, xaxis: { tickangle: -20, title: { text: 'Which of the three institutes work with the partner' } }, yaxis: { title: { text: 'Indian partner institutes' } } },
    ev => openSharedDrawer(String(ev.points[0].customdata)));
  const B = L.between;
  $('#rc-betweenlist').innerHTML = `<div class="sublabel">Strongest faculty pairs across the three institutes</div><div class="chips">${B.faculty_pairs.slice(0, 10).map(p => {
    const a = facByName.get(I.indexOf(p.inst_a) + '|' + p.a), b = facByName.get(I.indexOf(p.inst_b) + '|' + p.b);
    return `<span class="chip">${a != null ? `<a href="#" data-f="${a}">${esc(p.a)}</a>` : esc(p.a)} (${SHORT[I.indexOf(p.inst_a)]}) ↔ ${b != null ? `<a href="#" data-f="${b}">${esc(p.b)}</a>` : esc(p.b)} (${SHORT[I.indexOf(p.inst_b)]}) · ${p.joint_papers}</span>`; }).join('')}</div>`;
  $('#rc-betweenlist').querySelectorAll('[data-f]').forEach(e => e.onclick = ev => { ev.preventDefault(); openFaculty(+e.dataset.f); });
}

function renderReach() {
  if (!L) { $('#tab-reach').insertAdjacentHTML('beforeend', '<p class="note">Run locality_reach.py and build_dashboard.py to fill this tab.</p>'); return; }
  const sh = instsShown(), pr = partnerRows();
  const R = Object.fromEntries(L.reach.map(r => [r.institution, r]));
  const linksOf = i => L.partners.filter(r => r[PT.i] === i);
  const bars = (vals, f) => { const mx = d3.max(vals) || 1; return `<div class="bars">${[0, 1, 2].map(i => `<div class="bar" style="opacity:${sh.includes(i) ? 1 : .35}"><span>${SHORT[i]}</span><i style="width:${(vals[i] / mx * 100).toFixed(1)}%;background:${instColor(i)}"></i><span class="num">${f(vals[i])}</span></div>`).join('')}</div>`; };
  const pc = v => fmt1(v) + '%';
  const wavg = (vals, w) => d3.sum(sh, i => vals[i] * w[i]) / (d3.sum(sh, i => w[i]) || 1);
  const papersN = I.map(i => +R[i].papers);
  const peer = [0, 1, 2].map(i => d3.sum(linksOf(i).filter(r => PEER.includes(r[PT.cl])), pl));
  const linkTot = [0, 1, 2].map(i => d3.sum(linksOf(i), pl));
  const localN = [0, 1, 2].map(i => d3.sum(linksOf(i).filter(r => r[PT.loc] === 'Same state' || r[PT.loc] === 'Same region'), pl));
  const local = localN.map((v, i) => linkTot[i] ? 100 * v / linkTot[i] : 0);
  const ind = I.map(i => +R[i]['with_other_indian_inst_%']), abr = I.map(i => +R[i]['with_foreign_inst_%']);
  const scope = state.inst < 0 ? 'all three combined' : I[state.inst];
  $('#rc-kpis').innerHTML = [
    ['Papers with another Indian institute', pc(state.inst < 0 ? wavg(ind, papersN) : ind[state.inst]), `${scope} · all years`, bars(ind, pc)],
    ['Papers with a partner abroad', pc(state.inst < 0 ? wavg(abr, papersN) : abr[state.inst]), `${fmt(d3.sum(sh, i => R[I[i]].distinct_foreign_partners))} foreign institutes · all years`, bars(abr, pc)],
    ['Partner links that stay local', pc(100 * d3.sum(sh, i => localN[i]) / (d3.sum(sh, i => linkTot[i]) || 1)), `same state or same region · ${scope}`, bars(local, pc)],
    ['Links with peer institutes', fmt(d3.sum(sh, i => peer[i])), `joint-paper links with other NITs, IITs, IIITs, IISERs, IISc · ${state.inst < 0 ? 'total of the three' : I[state.inst]}`, bars(peer, fmt)],
  ].map(([l, v, s, b]) => `<div class="card kpi"><div class="lab">${l}</div><div class="val num">${v}</div><div class="sub">${s}</div>${b}</div>`).join('');

  drawInstNet();
  drawConnected();

  plot('rc-loc', LOCS.map(l => ({ type: 'bar', orientation: 'h', name: l, y: sh.map(i => SHORT[i]), meta: l,
    x: sh.map(i => linkTot[i] ? +(100 * d3.sum(linksOf(i).filter(r => r[PT.loc] === l), pl) / linkTot[i]).toFixed(1) : 0),
    customdata: sh.map(i => d3.sum(linksOf(i).filter(r => r[PT.loc] === l), pl)),
    marker: { color: locColor(l), line: { color: css('--surface'), width: 2 } }, hovertemplate: `%{y} · ${l}: %{x}% of partner links (%{customdata:,})<extra></extra>` })),
    { barmode: 'stack', bargap: .35, xaxis: { ticksuffix: '%', range: [0, 100], title: { text: 'Share of joint-paper links with Indian partners' } }, yaxis: { autorange: 'reversed' }, legend: { orientation: 'h', y: 1.2, x: 0, traceorder: 'normal' }, margin: { l: 52, r: 10, t: 40, b: 44 } },
    ev => { rcFilter = { loc: ev.points[0].data.meta, inst: SHORT.indexOf(ev.points[0].y) }; drawRcAll(true); });

  // Sankey: institute -> partner type (click a type or a band to list the institutes)
  const types = [...CL_ORDER, 'Other types'];
  const src = [], tgt = [], val = [], col = [];
  sh.forEach((i, si) => types.forEach((c, ci) => {
    const v = d3.sum(linksOf(i).filter(r => clFold(r[PT.cl]) === c), pl);
    if (v) { src.push(si); tgt.push(sh.length + ci); val.push(v); const cc = d3.color(clColor(c === 'Other types' ? '' : c)); cc.opacity = .45; col.push(cc.formatRgb()); }
  }));
  const sk = document.getElementById('rc-sankey');
  Plotly.react(sk, [{ type: 'sankey', arrangement: 'fixed', node: { label: [...sh.map(i => SHORT[i]), ...types], customdata: [...sh.map(i => 'I' + i), ...types], pad: 12, thickness: 16,
    color: [...sh.map(i => instColor(i)), ...types.map(c => clColor(c === 'Other types' ? '' : c))], line: { width: 0 }, hovertemplate: '%{label}: %{value:,} joint-paper links · click for the list<extra></extra>' },
    link: { source: src, target: tgt, value: val, color: col, hovertemplate: '%{source.label} → %{target.label}: %{value:,} joint-paper links · click for the list<extra></extra>' } }],
    baseLayout({ margin: { l: 6, r: 6, t: 6, b: 6 }, font: { size: 11.5, color: css('--ink') } }), { displayModeBar: false, responsive: true });
  sk.removeAllListeners?.('plotly_click');
  sk.on('plotly_click', ev => {
    const p = ev.points[0];
    if (p.target && p.source) { const t = types[p.target.pointNumber - sh.length], s = sh[p.source.pointNumber]; if (t) openTypeDrawer(`${t}|${s}`); return; }
    const k = p.pointNumber; if (k == null) return;
    if (k < sh.length) openTypeDrawer(`|${sh[k]}`); else openTypeDrawer(`${types[k - sh.length]}|`);
  });

  const geo = () => {
    const key = segVal('rcGeo') === 'region' ? PT.region : PT.state;
    const cats = [...new Set(pr.map(r => r[key]))].map(c => [c, d3.sum(pr.filter(r => r[key] === c), pl)]).sort((a, b) => b[1] - a[1]).slice(0, key === PT.state ? 22 : 12).map(c => c[0]);
    plot('rc-region', sh.map(i => ({ type: 'bar', name: I[i], x: cats, y: cats.map(c => d3.sum(linksOf(i).filter(r => r[key] === c), pl)), meta: i,
      marker: { color: instColor(i) }, hovertemplate: `${SHORT[i]} · %{x}: %{y} joint-paper links<extra></extra>` })),
      { barmode: 'group', bargap: .25, xaxis: { tickangle: key === PT.state ? -35 : 0, title: { text: key === PT.region ? 'Region of the partner institute' : 'State of the partner institute' } }, yaxis: { title: { text: 'Joint-paper links' } } },
      ev => { rcFilter = { [key === PT.region ? 'region' : 'state']: ev.points[0].x, inst: ev.points[0].data.meta }; drawRcAll(true); });
  };
  geo(); segBind('rcGeo', geo);

  const peerCol = c => CL_ORDER.includes(c) ? clColor(c) : CAT()[c === 'IISER' ? 6 : 4];
  plot('rc-trend', PEER.map(c => ({ type: 'scatter', mode: 'lines+markers', name: c, x: RY(), y: RY().map(y => d3.sum(pr.filter(r => r[PT.cl] === c), r => r[PT.years][y - 2016])),
    line: { color: peerCol(c), width: 2.5 }, marker: { size: 7, color: peerCol(c), line: { color: css('--surface'), width: 1.5 } }, hovertemplate: `${c} %{x}: %{y} joint papers<extra></extra>` })),
    { xaxis: { dtick: 1, title: { text: 'Year' } }, yaxis: { rangemode: 'tozero', title: { text: 'Joint papers' } } });

  makeTable($('#rc-peers'), {
    rows: () => pr.filter(r => PEER.includes(r[PT.cl])), pageSize: 12, sort: 'papers', dir: -1, search: 'Search institutes or faculty…', text: r => r[PT.name] + ' ' + r[PT.topfac],
    selects: [{ key: 'cl', label: 'All peer types', options: PEER, get: r => r[PT.cl] }, { key: 'loc', label: 'Any locality', options: LOCS, get: r => r[PT.loc] }],
    columns: [
      { key: 'name', label: 'Institute', v: r => r[PT.name], html: r => `<div class="t">${esc(r[PT.name])}</div><div class="s">${esc(r[PT.state])} · top faculty: ${esc(r[PT.topfac])}</div>` },
      { key: 'i', label: 'With', v: r => r[PT.i], html: r => instChip(r[PT.i]) },
      { key: 'cl', label: 'Type', v: r => r[PT.cl] },
      { key: 'loc', label: 'Locality', v: r => LOCS.indexOf(r[PT.loc]), html: r => `<span class="chip"><span class="dot" style="background:${locColor(r[PT.loc])}"></span>${esc(r[PT.loc])}</span>` },
      { key: 'papers', label: 'Joint papers', num: 1, v: r => pl(r) },
      { key: 'cf', label: 'Cite the institutes', num: 1, v: r => r[PT.cf], html: r => r[PT.cf] == null ? '—' : fmt(r[PT.cf]) },
      { key: 'ct', label: 'Cited by the institutes', num: 1, v: r => r[PT.ct], html: r => r[PT.ct] == null ? '—' : fmt(r[PT.ct]) },
      { key: 'nfac', label: 'Faculty', num: 1, v: r => r[PT.nfac] },
      { key: 'wj', label: 'Topic sim.', num: 1, v: r => r[PT.wj], html: r => r[PT.wj] == null ? '—' : fmt2(r[PT.wj]) },
    ],
    onRow: r => openPartner(r[PT.name]),
  });

  const WO = L.facWO;
  plot('rc-scatter', sh.map(i => { const fsx = F.map((f, k) => k).filter(k => F[k].i === i && WO[k]); return {
    type: 'scatter', mode: 'markers', name: I[i], x: fsx.map(k => WO[k][0] + 1), y: fsx.map(k => WO[k][1] + WO[k][2] + WO[k][3] + 1), customdata: fsx,
    marker: { size: fsx.map(k => Math.sqrt(F[k].p) * 1.3 + 4), color: instColor(i), opacity: .7, line: { color: css('--surface'), width: 1 } },
    hovertext: fsx.map(k => `<b>${esc(F[k].n)}</b> (${SHORT[i]})<br>${WO[k][0]} co-authors at ${SHORT[i]} · ${WO[k][1]} at the other two institutes · ${WO[k][2]} elsewhere in India · ${WO[k][3]} abroad`), hovertemplate: '%{hovertext}<extra></extra>' }; }),
    { xaxis: { type: 'log', title: { text: '→ Faculty co-authors inside the same institute (log scale)' } }, yaxis: { type: 'log', title: { text: '↑ Co-authors outside the institute (log scale)' } },
      shapes: [{ type: 'line', x0: 1, y0: 1, x1: 40, y1: 40, line: { color: css('--muted'), dash: 'dot', width: 1 } }],
      annotations: [{ x: Math.log10(30), y: Math.log10(30), text: 'equal inside and outside', showarrow: false, font: { size: 10.5, color: css('--muted') }, xanchor: 'left', yanchor: 'top' }] }, ev => openFaculty(ev.points[0].customdata));
  const topFac = () => {
    const m = segVal('rcTop');
    const v = k => m === 'within' ? WO[k][0] : m === 'outside' ? WO[k][1] + WO[k][2] + WO[k][3] : WO[k][6];
    $('#rc-topfac').innerHTML = `<div class="grid" style="grid-template-columns:repeat(${sh.length},minmax(0,1fr));gap:10px">${sh.map(i => {
      const fsx = F.map((f, k) => k).filter(k => F[k].i === i && WO[k]).sort((a, b) => v(b) - v(a)).slice(0, 10), mx = v(fsx[0]) || 1;
      return `<div><div style="margin-bottom:6px">${instChip(i)}</div>${fsx.map((k, r) => `<div data-f="${k}" style="cursor:pointer;padding:5px 0;border-bottom:1px solid var(--border)"><div style="display:flex;gap:6px"><span class="note num">${r + 1}</span><span style="flex:1">${esc(F[k].n)}</span><b class="num">${m === 'btw' ? v(k).toFixed(3) : v(k)}</b></div><i class="minibar" style="width:${(v(k) / mx * 90).toFixed(0)}%;background:${instColor(i)}"></i></div>`).join('')}</div>`; }).join('')}</div>`;
    $('#rc-topfac').querySelectorAll('[data-f]').forEach(e => e.onclick = () => openFaculty(+e.dataset.f));
  };
  topFac(); segBind('rcTop', topFac);

  makeTable($('#rc-ext'), {
    rows: () => L.extAuthors.filter(r => sh.some(i => r.our_institutes.includes(I[i]))), pageSize: 8, sort: 'n', dir: -1,
    columns: [
      { key: 'a', label: 'Author', v: r => r.author, html: r => `<div class="t">${esc(r.author)}</div><div class="s">${esc(r.institution)} ${r.country ? '· ' + esc(r.country) : ''}</div>` },
      { key: 'n', label: 'Our faculty', num: 1, v: r => +r.faculty_connected },
      { key: 'o', label: 'With', v: r => r.our_institutes, html: r => r.our_institutes.split('; ').map(n => instChip(I.indexOf(n))).join(' ') },
      { key: 'b', label: 'Betweenness', num: 1, v: r => +r.betweenness_full_network, html: r => (+r.betweenness_full_network).toFixed(4) },
    ],
    onRow: r => openExternal(r),
  });
  const instChart = () => {
    const m = segVal('rcInst');
    let rs = L.instNodes.filter(r => state.inst < 0 || r.linked_to.includes(I[state.inst]));
    rs = m === 'btw' ? rs.slice().sort((a, b) => b.betweenness - a.betweenness) : rs.filter(r => m === 'IN' ? r.country === 'IN' : r.country !== 'IN').sort((a, b) => b.papers_with_us - a.papers_with_us);
    rs = rs.slice(0, 15).reverse();
    plot('rc-inst', [{ type: 'bar', orientation: 'h', y: rs.map(r => abbr(r.institution) + ' '), x: rs.map(r => m === 'btw' ? +r.betweenness : +r.papers_with_us), customdata: rs.map(r => r.institution),
      marker: { color: rs.map(r => r.country === 'IN' ? clColor(r.cluster) : css('--c5')) }, hovertext: rs.map(r => `${esc(r.institution)} (${r.country === 'IN' ? esc(r.cluster) : 'abroad'})<br>${r.papers_with_us} papers with ${esc(r.linked_to)}`),
      hovertemplate: '%{hovertext}<extra></extra>' }], { margin: { l: lm(rs.map(r => abbr(r.institution))), r: 14, t: 4, b: 44 }, bargap: .25, xaxis: { title: { text: m === 'btw' ? 'Betweenness in the institute network' : 'Papers with the three institutes' } } },
      ev => { const n = ev.points[0].customdata; if (L.partners.some(r => r[PT.name] === n)) openPartner(n); else if ((L.foreign || []).some(r => r[1] === n)) openForeign(n); });
  };
  instChart(); segBind('rcInst', instChart);

  const CO = L.citOrigin;
  plot('rc-cit', [['Same institute', 'from_same_institute_%', '--q1'], ['The other two institutes', 'from_our_other_two_%', '--c4'], ['Outside the corpus', null, '--q3']].map(([n, k, c]) => ({
    type: 'bar', orientation: 'h', name: n, y: sh.map(i => SHORT[i]), x: sh.map(i => k ? CO[I[i]][k] : +(100 - CO[I[i]]['from_same_institute_%'] - CO[I[i]]['from_our_other_two_%']).toFixed(2)),
    marker: { color: css(c), line: { color: css('--surface'), width: 2 } }, hovertemplate: `%{y} · ${n}: %{x}%<extra></extra>` })),
    { barmode: 'stack', xaxis: { ticksuffix: '%', range: [0, 100], title: { text: 'Share of all citations received' } }, yaxis: { autorange: 'reversed' }, legend: { orientation: 'h', y: 1.25, x: 0, traceorder: 'normal' }, margin: { l: 52, r: 10, t: 40, b: 44 } });
  const citTable = () => {
    const m = segVal('rcCit');
    const v = k => m === 'within' ? sameIn[k] : Math.max(0, P[k][T.cites] - P[k][T.indeg]);
    const top = d3.range(P.length).filter(k => pIn(P[k])).sort((a, b) => v(b) - v(a)).slice(0, 10);
    $('#rc-citpapers').innerHTML = `<div class="plist">${top.map(k => paperRow(k, `<span>· <b class="num">${v(k)}</b> ${m === 'within' ? 'from own institute' : 'from outside'}</span>`)).join('')}</div>`;
    $('#rc-citpapers').querySelectorAll('[data-p]').forEach(e => e.onclick = ev => { if (ev.target.tagName !== 'A') openPaper(+e.dataset.p); });
  };
  citTable(); segBind('rcCit', citTable);

  rcTable = makeTable($('#rc-all'), {
    rows: () => partnerRows(), pageSize: 12, sort: 'papers', dir: -1, search: 'Search partner institutes…', text: r => r[PT.name] + ' ' + r[PT.state],
    selects: [{ key: 'cl', label: 'All types', options: [...new Set(L.partners.map(r => r[PT.cl]))].sort(), get: r => r[PT.cl] },
      { key: 'loc', label: 'Any locality', options: LOCS, get: r => r[PT.loc] }],
    filter: r => (!rcFilter.region || r[PT.region] === rcFilter.region) && (!rcFilter.state || r[PT.state] === rcFilter.state) && (rcFilter.inst == null || rcFilter.inst < 0 || r[PT.i] === rcFilter.inst),
    columns: [
      { key: 'name', label: 'Partner', v: r => r[PT.name], html: r => `<div class="t">${esc(r[PT.name])}</div><div class="s">${esc(r[PT.topfac])}</div>` },
      { key: 'i', label: 'With', v: r => r[PT.i], html: r => instChip(r[PT.i]) },
      { key: 'cl', label: 'Type', v: r => r[PT.cl], html: r => `<span class="chip"><span class="dot" style="background:${clColor(r[PT.cl])}"></span>${esc(r[PT.cl])}</span>` },
      { key: 'state', label: 'State', v: r => r[PT.state] },
      { key: 'loc', label: 'Locality', v: r => LOCS.indexOf(r[PT.loc]), html: r => esc(r[PT.loc]) },
      { key: 'papers', label: 'Papers', num: 1, v: r => pl(r) },
      { key: 'cf', label: 'Cite the institutes', num: 1, v: r => r[PT.cf], html: r => r[PT.cf] == null ? '—' : fmt(r[PT.cf]) },
      { key: 'ct', label: 'Cited by the institutes', num: 1, v: r => r[PT.ct], html: r => r[PT.ct] == null ? '—' : fmt(r[PT.ct]) },
      { key: 'nfac', label: 'Faculty', num: 1, v: r => r[PT.nfac] },
      { key: 'nco', label: 'Partner co-authors', num: 1, v: r => NVP.get(r[PT.i] + '|' + r[PT.name])?.[0] ?? null, html: r => { const x = NVP.get(r[PT.i] + '|' + r[PT.name]); return x ? fmt(x[0]) : '—'; } },
      { key: 'nfw', label: 'Mean FWCI', num: 1, v: r => NVP.get(r[PT.i] + '|' + r[PT.name])?.[1] ?? null, html: r => { const x = NVP.get(r[PT.i] + '|' + r[PT.name]); return x && x[1] != null ? x[1].toFixed(2) : '—'; } },
    ],
    onRow: r => openPartner(r[PT.name]),
  });
  drawRcAll(false);
}
const NVP = new Map(((D.insights || {}).new_views?.pairs || []).map(([i, n, c, f]) => [i + '|' + n, [c, f]]));
function drawRcAll(scroll) {
  if (!rcTable) return;
  if (rcFilter.loc) { const s = rcTable.opt.selects[1]; s.el.value = rcFilter.loc; rcTable.st.filters.loc = rcFilter.loc; }
  rcTable.st.page = 0; rcTable.draw();
  const parts = [rcFilter.inst != null && rcFilter.inst >= 0 ? I[rcFilter.inst] : '', rcFilter.region || rcFilter.state || '', rcFilter.loc || ''].filter(Boolean);
  const host = $('#rc-all').previousElementSibling.querySelector('p');
  host.innerHTML = parts.length ? `Filtered: <b>${esc(parts.join(' · '))}</b> · <a href="#" id="rcClear">clear</a>` : 'Every Indian partner institute';
  $('#rcClear') && ($('#rcClear').onclick = e => { e.preventDefault(); rcFilter = {}; rcTable.opt.selects.forEach(s => { s.el.value = ''; }); rcTable.st.filters = {}; drawRcAll(false); });
  if (scroll) $('#rc-all').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ================================================================ CHECKLIST
function renderChecklist() {
  const ok = 'Done', part = 'Partial', pend = 'Pending';
  const items = [
    ['Dataset: group15_data.csv with all 14 required columns, 2016–2026, all 3 institutes', ok, 'method', `${fmt(D.group15Rows)} rows · ${fmt(P.length)} papers`],
    ['Faculty list incl. former faculty (historical affiliation)', ok, 'faculty', `${fmt(F.length)} verified faculty, current + former`],
    ['Journal quartile Q1–Q4 (SCImago) and CORE conference rank', ok, 'pubs', 'SJR, Scopus CiteScore, CORE 2023'],
    ['Papers with >10 authors flagged', ok, 'papers', 'is_multi_author_10plus'],
    ['Deduplication by DOI and by title + year', part, 'method', `${fmt(D.dupMerged)} duplicate records merged; audit in duplicate_audit.csv`],
    ['citation_network.csv · authorship_network.csv · indian_connections.csv', ok, 'citnet', 'required columns present'],
    ['Panel: publication trend 2016–2026', ok, 'overview', ''], ['Panel: faculty list (name, dept, h-index, papers)', ok, 'faculty', ''],
    ['Panel: journal quartile distribution', ok, 'pubs', ''], ['Panel: sortable faculty performance table', ok, 'faculty', ''],
    ['Panel: top 5 journals per institution', ok, 'pubs', ''], ['Panel: h-index distribution histogram', ok, 'faculty', ''],
    ['Panel: research area breakdown', ok, 'pubs', ''], ['Panel: top 10 most-cited papers with DOI', ok, 'papers', ''],
    ['Panel: CORE A*/A/B/C breakdown', ok, 'pubs', ''], ['Panel: interactive citation graph (size = PageRank / in-degree)', ok, 'citnet', ''],
    ['Panel: interactive co-authorship graph (Louvain colours)', ok, 'collab', ''],
    ['Citation network: in-degree, PageRank top 10, cross-institute flow', ok, 'citnet', ''],
    ['Authorship network: degree, betweenness, Louvain / Leiden', ok, 'collab', ''],
    ['Citation flow: in / out / ratio, top 10 citing institutes, year-wise chart', ok, 'flows', ''],
    ['Top 10 most-cited papers citing the three institutes', pend, 'flows', 'needs the citation counts of the citing papers (one more OpenAlex lookup)'],
    ['Connectivity: every Indian partner ranked by joint papers', ok, 'reach', '1,333 institute links'],
    ['Cross-cluster links flagged (IIT, NIT, CSIR, DAE, IISER …)', ok, 'reach', 'name + known-lab rules + exact parent lookup (partners.py)'],
    ['Jaccard topic similarity with partners', part, 'reach', 'top partners only (partners.py)'],
    ['Hub authors bridging institutes', ok, 'collab', 'bridge authors, brokers, outside authors'],
    ['Locality: same state / region, peer NITs & IITs outside the three institutes', ok, 'reach', ''],
    ['Highest nodes within vs outside each institute', ok, 'reach', ''],
    ['Statistics report ≤ 5 pages + detailed report', ok, 'method', 'report/ folder'],
  ];
  const col = { Done: '--good', Partial: '--c4', Pending: '--c8' }, icon = { Done: '✓', Partial: '◐', Pending: '…' };
  $('#checklist').innerHTML = `<div class="tbl-wrap"><table><thead><tr><th>Requirement</th><th>Status</th><th>Where</th><th>Note</th></tr></thead><tbody>${items.map(([r, s, t, n]) =>
    `<tr class="row" data-t="${t}"><td>${esc(r)}</td><td><span class="chip"><b style="color:var(${col[s]})">${icon[s]}</b> ${s}</span></td><td>${esc(document.querySelector(`#nav button[data-tab="${t}"]`).textContent.trim())}</td><td class="s">${esc(n)}</td></tr>`).join('')}</tbody></table></div>`;
  $('#checklist').querySelectorAll('tr.row').forEach(tr => tr.onclick = () => go(tr.dataset.t));
}

const RENDER = { overview: renderOverview, pubs: renderPubs, faculty: renderFaculty, papers: renderPapers, citnet: renderCitnet, collab: renderCollab, reach: renderReach, flows: renderFlows, method: renderMethod };
buildInstSeg(); buildYearCtl();
// deep links: #collab?f=<faculty index>, #citnet?p=<paper index>, #faculty?f=<i> (profile only), #reach?i=<partner institute>, any tab with &inst=<0..2> (institute lens)
const [start, qs] = (window.__startHash || (location.hash || '').slice(1)).split('?');
go(RENDER[start] ? start : 'overview');
const dl = new URLSearchParams(qs || '');
if (dl.has('inst') && +dl.get('inst') >= 0 && +dl.get('inst') < I.length) setInst(+dl.get('inst'));
if (dl.has('f')) { const i = +dl.get('f'); if (start === 'collab') focusFaculty(i); openFaculty(i); }
if (dl.has('i')) openPartner(dl.get('i'));
if (dl.has('p')) { const p = +dl.get('p'); if (start === 'citnet') focusPaper(p); else openPaper(p); }
window.atlas = { instStat: iStat, yrLabel, openForeign, T, RENDER, renderTab, rendered, instsShown, inYears: (...a) => inYears(...a), fmt, fmt1, fmt2, plot, css, isDark: () => isDark(), segBind, openFaculty, openPaper, openPartner, focusFaculty, focusPaper, explorer, setInst, go, state, instColor, SHORT, closeDrawer };
let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => document.querySelectorAll(`#tab-${state.tab} .js-plotly-plot`).forEach(el => Plotly.Plots.resize(el)), 150); });
})();
