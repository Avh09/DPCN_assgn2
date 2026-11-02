/* Research Atlas: more analyses, each placed in the tab it belongs to.
   Publications: metric trends (switchable), more institute metrics, subject radar   Papers: paper scatter
   Faculty: head-to-head comparison                                                   Collaboration: collaboration distance
   Reach: countries, outside institutes in detail, outside co-authors                 Footer: data build date
   Everything is drawn from DATA; needs app.js and extras.js. */
(() => {
const A = window.atlas, D = window.DATA, I = D.insts, SH = A.SHORT, P = D.papers, F = D.fac, T = A.T;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = A.fmt, fmt1 = A.fmt1, fmt2 = A.fmt2, css = A.css;
const NV = (D.insights || {}).new_views || { countries: {}, coauthors: [], partners: [] };
const card = (title, sub, body, cls = '') => `<div class="card ${cls}"><div class="card-h"><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div></div>${body}</div>`;
const table = (heads, rows) => `<div class="tbl-wrap"><table><thead><tr>${heads.map((h, i) => `<th class="${i ? 'r' : ''}">${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((c, i) => `<td class="${i ? 'r' : ''}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const chart = (id, h = 320) => `<div class="chart" id="${id}" style="height:${h}px"></div>`;
const sel = (id, opts, cls = '') => `<select id="${id}" class="${cls}">${opts.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('')}</select>`;
function addSection(tab, id, html) { const sec = $('#tab-' + tab); if (!sec || $('#' + id)) return false; const d = document.createElement('div'); d.id = id; d.className = 'mt'; d.innerHTML = html; sec.insertBefore(d, sec.querySelector('.site-foot')); return true; }
const hook = (tab, fn) => { const base = A.RENDER[tab]; A.RENDER[tab] = () => { base(); try { fn(); } catch (e) { console.error('more.js', tab, e); } }; };
const yin = y => A.inYears(Object.assign([], { [T.year]: y }));          // is this year inside the selected range?
const papersOf = k => P.filter(x => x[T.mask] & (1 << k));
const inRange = x => A.inYears(x);
const facPapers = F.map(() => []);
D.pfac.forEach((fs, p) => fs.forEach(f => facPapers[f].push(p)));
const mean = v => { v = v.filter(x => x != null && !isNaN(x)); return v.length ? d3.mean(v) : null; };

const style = document.createElement('style');
style.textContent = `.cmp-pick{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin:4px 0 14px}.cmp-pick label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted)}
.cmp-pick input,.cmp-pick select{background:var(--surface,transparent);border:1px solid var(--rule,rgba(128,128,128,.3));border-radius:12px;padding:10px 14px;font:inherit;font-size:14px;color:var(--ink);min-width:250px}
.cmp-pick select{min-width:190px}.cmp-msg{font-size:13px;color:var(--muted);margin:0 0 10px}.cmp td.win{font-weight:650;color:var(--brandInk,#7a3fd0)}.cmp td.grp{font:500 11px var(--mono,monospace);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);padding-top:18px}
.cmp td.d{color:var(--muted);font-size:12.5px}.cmp .nm{display:flex;flex-direction:column;gap:2px}.cmp .nm small{color:var(--muted);font-weight:400}.cd-path{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:10px 0}.cd-path span.arrow{color:var(--muted)}
.cd-chip{padding:4px 10px;border-radius:999px;background:var(--surface2,rgba(128,128,128,.14));font-size:12.5px}.mini-controls{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:0 0 10px;font-size:13px;color:var(--muted)}
.mini-controls select{background:var(--surface,transparent);border:1px solid var(--rule,rgba(128,128,128,.3));border-radius:10px;padding:6px 10px;font:inherit;color:var(--ink)}`;
document.head.append(style);

// ================================================================ Publications: metric trends (switchable), more institute metrics, subject radar
const MEASURES = [
  ['papers', 'Papers', ps => ps.length, 0],
  ['cites', 'Citations (by year of publication)', ps => d3.sum(ps, x => x[T.cites]), 0],
  ['cpp', 'Citations per paper', ps => ps.length ? d3.sum(ps, x => x[T.cites]) / ps.length : null, 1],
  ['unc', 'Uncited papers (%)', ps => ps.length ? 100 * ps.filter(x => x[T.cites] === 0).length / ps.length : null, 1],
  ['fwci', 'Mean FWCI (1 = world average)', ps => mean(ps.map(x => x[T.fwci])), 2],
  ['q1', 'Q1 share of ranked journal papers (%)', ps => { const j = ps.filter(x => x[T.type] === 0 && /^Q[1-4]$/.test(x[T.q])); return j.length ? 100 * j.filter(x => x[T.q] === 'Q1').length / j.length : null; }, 1],
  ['na', 'Authors per paper', ps => mean(ps.filter(x => x[T.nauth]).map(x => x[T.nauth])), 1],
  ['sae', 'Single-author equivalent (each paper counts 1 ÷ its authors)', ps => d3.sum(ps.filter(x => x[T.nauth]), x => 1 / x[T.nauth]), 1],
  ['ninst', 'Institutions per paper', ps => mean(ps.filter(x => x[T.nauth]).map(x => x[T.ninst])), 1],
  ['ncty', 'Countries per paper', ps => mean(ps.filter(x => x[T.nauth]).map(x => x[T.ncty])), 2],
];
function trendsInit() {
  const made = addSection('pubs', 'pb-trends', card('How have the numbers changed year by year?', 'Pick a measure. The peak is marked; 2026 is a partial year and drawn dotted.',
    `<div class="mini-controls"><label>Measure ${sel('trMeasure', MEASURES.map(m => [m[0], m[1]]))}</label></div>` + chart('tr-chart', 340)));
  if (made) $('#trMeasure').onchange = trendsDraw;
}
function trendsDraw() {
  if (!$('#tr-chart')) return;
  const m = MEASURES.find(x => x[0] === $('#trMeasure').value), ys = d3.range(2016, 2027).filter(yin), traces = [], notes = [];
  A.instsShown().forEach(k => {
    const by = d3.group(papersOf(k), x => x[T.year]), c = A.instColor(k), val = y => { const v = m[2](by.get(y) || []); return v == null ? null : +v.toFixed(3); };
    const full = ys.filter(y => y <= 2025), part = ys.filter(y => y >= 2025);
    const fmtv = v => v == null ? '—' : (m[3] ? v.toFixed(m[3]) : fmt(v));
    if (full.length) traces.push({ type: 'scatter', mode: 'lines+markers', name: I[k], x: full, y: full.map(val), line: { color: c, width: 2.5, shape: 'spline', smoothing: .4 }, marker: { size: 7, color: c }, hovertemplate: `${SH[k]} %{x}: %{y}<extra></extra>` });
    if (ys.includes(2026) && part.length > 1) traces.push({ type: 'scatter', mode: 'lines+markers', name: I[k] + ' (2026, partial)', showlegend: false, x: part.filter(y => y >= 2025), y: part.filter(y => y >= 2025).map(val), line: { color: c, width: 2, dash: 'dot' }, marker: { size: 6, color: c, symbol: 'circle-open' }, hovertemplate: `${SH[k]} %{x} (partial): %{y}<extra></extra>` });
    const pk = full.map(y => [y, val(y)]).filter(a => a[1] != null).sort((a, b) => b[1] - a[1])[0];
    if (pk) notes.push({ x: pk[0], y: pk[1], text: `peak ${fmtv(pk[1])}`, showarrow: true, arrowhead: 0, arrowcolor: c, ax: 0, ay: -26, font: { size: 10.5, color: c } });
  });
  A.plot('tr-chart', traces, { hovermode: 'closest', annotations: notes, xaxis: { dtick: 1, title: { text: 'Year' } }, yaxis: { title: { text: m[1] }, rangemode: 'tozero' } });
}
function metricsTable() {
  const rows = [
    ['Papers', k => papersOf(k).filter(inRange).length, fmt],
    ['Papers with 10+ citations (i10)', k => papersOf(k).filter(inRange).filter(x => x[T.cites] >= 10).length, fmt],
    ['Cited papers (%)', k => { const p = papersOf(k).filter(inRange); return p.length ? 100 * p.filter(x => x[T.cites] > 0).length / p.length : null; }, v => fmt1(v) + '%'],
    ['Uncited papers (%)', k => { const p = papersOf(k).filter(inRange); return p.length ? 100 * p.filter(x => x[T.cites] === 0).length / p.length : null; }, v => fmt1(v) + '%'],
    ['Median citations per paper', k => d3.median(papersOf(k).filter(inRange), x => x[T.cites]), v => fmt1(v)],
    ['Most-cited paper (citations)', k => d3.max(papersOf(k).filter(inRange), x => x[T.cites]), fmt],
    ['Single-author equivalent', k => d3.sum(papersOf(k).filter(inRange).filter(x => x[T.nauth]), x => 1 / x[T.nauth]), v => fmt(Math.round(v))],
    ['Authors per paper', k => mean(papersOf(k).filter(inRange).filter(x => x[T.nauth]).map(x => x[T.nauth])), v => fmt1(v)],
    ['Institutions per paper', k => mean(papersOf(k).filter(inRange).filter(x => x[T.nauth]).map(x => x[T.ninst])), v => fmt1(v)],
    ['Countries per paper', k => mean(papersOf(k).filter(inRange).filter(x => x[T.nauth]).map(x => x[T.ncty])), v => fmt2(v)],
    ['Papers with a foreign co-author (%)', k => { const p = papersOf(k).filter(inRange).filter(x => x[T.nauth]); return p.length ? 100 * p.filter(x => x[T.ncty] > 1).length / p.length : null; }, v => fmt1(v) + '%'],
  ].map(([l, f, g]) => [l, ...[0, 1, 2].map(k => { const v = f(k); return v == null || isNaN(v) ? '—' : g(v); })]);
  return table(['Measure', ...SH], rows);
}
function radarDraw() {
  if (!$('#rd-chart')) return;
  const all = d3.rollup(P.filter(inRange), v => v.length, x => x[T.field]);
  const axes = [...all].filter(([f]) => f).sort((a, b) => b[1] - a[1]).slice(0, 12).map(a => a[0]), sq = Math.sqrt, ticks = [1, 5, 10, 25, 50];
  const traces = A.instsShown().map(k => {
    const ps = papersOf(k).filter(inRange), n = ps.length || 1, by = d3.rollup(ps, v => v.length, x => x[T.field]), c = A.instColor(k), pct = [...axes, axes[0]].map(f => +(100 * (by.get(f) || 0) / n).toFixed(1));
    return { type: 'scatterpolar', name: I[k], r: pct.map(sq), customdata: pct, theta: [...axes, axes[0]], fill: 'toself', fillcolor: c + '33', line: { color: c, width: 2 }, hovertemplate: '%{theta}: %{customdata}% of papers<extra>' + SH[k] + '</extra>' };
  });
  A.plot('rd-chart', traces, { polar: { bgcolor: 'rgba(0,0,0,0)', radialaxis: { tickvals: ticks.map(sq), ticktext: ticks.map(t => t + '%'), range: [0, sq(60)], gridcolor: css('--grid'), linecolor: css('--axis'), tickfont: { size: 10, color: css('--muted') } }, angularaxis: { gridcolor: css('--grid'), linecolor: css('--axis'), tickfont: { size: 11, color: css('--ink2') } } }, margin: { l: 120, r: 120, t: 24, b: 24 } });
}
function pubsMore() {
  trendsInit(); trendsDraw();
  if (addSection('pubs', 'pb-more', `<div class="grid g2">` + card('Which subject areas does each institute cover?', 'Share of each institute’s papers in the 12 largest fields (square-root scale, so small fields stay visible)', chart('rd-chart', 460)) +
    card('What other numbers describe each institute?', 'Citation profile and collaboration breadth', `<div id="mm-table"></div>`) + `</div>`)) { /* created once */ }
  $('#mm-table').innerHTML = metricsTable();
  radarDraw();
}

// ================================================================ Papers: every paper as a dot
function scatterInit() {
  const made = addSection('papers', 'pp-scatter', card('How does every paper look at a glance?', 'One dot per paper (hover for the title, click to open it). Pick what the vertical axis shows.',
    `<div class="mini-controls"><label>Vertical axis ${sel('scY', [['cites', 'Citations'], ['fwci', 'Field-weighted citation impact'], ['nauth', 'Number of authors'], ['pr', 'PageRank within the corpus'], ['ninst', 'Institutions on the paper']])}</label>
      <label><input type="checkbox" id="scLog" checked> Log scale (papers with a zero value are hidden)</label></div>` + chart('sc-chart', 440)));
  if (made) { $('#scY').onchange = scatterDraw; $('#scLog').onchange = scatterDraw; }
}
function scatterDraw() {
  if (!$('#sc-chart')) return;
  const key = $('#scY').value, idx = { cites: T.cites, fwci: T.fwci, nauth: T.nauth, pr: T.pr, ninst: T.ninst }[key], sh = new Set(A.instsShown());
  const groups = [[0, 'MANIT'], [1, 'NITJ'], [2, 'NITS']].map(([k, n]) => ({ k, n, x: [], y: [], t: [], id: [] })), multi = { n: 'Shared by several', x: [], y: [], t: [], id: [] };
  P.forEach((x, i) => {
    if (!inRange(x) || x[idx] == null) return;
    const ks = [0, 1, 2].filter(k => x[T.mask] & (1 << k)); if (!ks.some(k => sh.has(k))) return;
    const g = ks.length === 1 ? groups[ks[0]] : multi, jit = ((i * 2654435761) % 1000) / 1000 - .5;
    g.x.push(x[T.year] + jit * .7); g.y.push(x[idx]); g.t.push(x[T.title].slice(0, 90)); g.id.push(i);
  });
  const tr = [...groups, multi].filter(g => g.x.length).map(g => ({ type: 'scattergl', mode: 'markers', name: g.n, x: g.x, y: g.y, text: g.t, customdata: g.id, marker: { size: 5, opacity: .55, color: g.k != null ? A.instColor(g.k) : css('--muted') }, hovertemplate: '%{text}<br>%{x:.0f}: %{y}<extra>' + g.n + '</extra>' }));
  const label = { cites: 'Citations', fwci: 'FWCI', nauth: 'Authors', pr: 'PageRank ×10⁶', ninst: 'Institutions' }[key];
  A.plot('sc-chart', tr, { hovermode: 'closest', xaxis: { dtick: 1, title: { text: 'Year' } }, yaxis: { title: { text: label }, type: $('#scLog').checked ? 'log' : 'linear', rangemode: $('#scLog').checked ? undefined : 'tozero' } },
    ev => { const id = ev.points[0].customdata; if (id != null) A.openPaper(id); });
}
function papersMore() { top20Init(); top20Draw(); scatterInit(); scatterDraw(); }

// ---- Papers: the 20 most-cited papers of one institute
function top20Init() {
  const made = addSection('papers', 'pp-top20', card('Which are the 20 most-cited papers of each institute?', 'Pick an institute and what to rank by. Click a paper to open it.',
    `<div class="cmp-pick"><label>Institute ${sel('t20i', I.map((n, k) => [k, n]))}</label><label>Rank by ${sel('t20s', [['c', 'Citations'], ['f', 'Field-weighted impact (FWCI)']])}</label></div><div id="t20-out"></div>`));
  if (made) { $('#t20i').onchange = $('#t20s').onchange = top20Draw; }
}
function top20Draw() {
  if (!$('#t20-out')) return;
  if (A.state.inst >= 0 && $('#t20i').dataset.lens !== String(A.state.inst)) { $('#t20i').value = A.state.inst; $('#t20i').dataset.lens = A.state.inst; }
  const k = +$('#t20i').value, byF = $('#t20s').value === 'f', key = byF ? T.fwci : T.cites;
  const rows = d3.range(P.length).filter(p => (P[p][T.mask] & (1 << k)) && inRange(P[p]) && P[p][key] != null).sort((a, b) => P[b][key] - P[a][key]).slice(0, 20);
  $('#t20-out').innerHTML = `<div class="tbl-wrap"><table><thead><tr><th>#</th><th>Paper</th><th class="r">Year</th><th class="r">Citations</th><th class="r">FWCI</th></tr></thead><tbody>${rows.map((p, n) => `<tr data-p="${p}" style="cursor:pointer"><td class="num">${n + 1}</td>
    <td><div class="t">${esc(P[p][T.title])}</div><div class="s">${esc(P[p][T.venue] || '')}</div></td><td class="r num">${P[p][T.year]}</td><td class="r num">${fmt(P[p][T.cites])}</td><td class="r num">${P[p][T.fwci] == null ? '' : fmt1(P[p][T.fwci])}</td></tr>`).join('')}</tbody></table></div>`;
  $('#t20-out').querySelectorAll('tr[data-p]').forEach(tr => tr.onclick = () => A.openPaper(+tr.dataset.p));
}

// ================================================================ Reach: countries, outside institutes in detail, outside co-authors
const region = (() => { try { const n = new Intl.DisplayNames(['en'], { type: 'region' }); return c => { try { return n.of(c) || c; } catch (e) { return c; } }; } catch (e) { return c => c; } })();
function reachInit() {
  addSection('reach', 'rc-more', `<div class="grid g2">` + card('Which foreign countries do the institutes write papers with?', 'Papers with a co-author based in each country (India excluded)', chart('rm-country', 400)) +
    card('Who are the outside co-authors?', 'Each dot is a person outside the three institutes: papers written with the institutes against citations of those papers', chart('rm-coauth', 400)) + `</div>`);
}
function reachDraw() {
  const k = A.state.inst, key = k < 0 ? 'all' : I[k], col = k < 0 ? css('--c1') : A.instColor(k);
  const cs = (NV.countries[key] || []).slice(0, 12).reverse();
  A.plot('rm-country', [{ type: 'bar', orientation: 'h', x: cs.map(c => c.papers), y: cs.map(c => c.name), marker: { color: col }, hovertemplate: '%{y}: %{x} papers<extra></extra>' }], { margin: { l: 130, r: 12, t: 6, b: 36 }, xaxis: { title: { text: 'Papers' } }, yaxis: { automargin: true } });
  const mine = x => k < 0 || x.ours.includes(SH[k]), co = NV.coauthors.filter(mine);
  const top = co.slice().sort((a, b) => b.citations - a.citations).slice(0, 6);
  A.plot('rm-coauth', [
    { type: 'scattergl', mode: 'markers', x: co.map(c => c.papers), y: co.map(c => c.citations), text: co.map(c => `${c.name} · ${c.institute}`), marker: { size: 7, opacity: .6, color: col }, hovertemplate: '%{text}<br>%{x} papers, %{y} citations<extra></extra>', showlegend: false },
    { type: 'scatter', mode: 'text', x: top.map(c => c.papers), y: top.map(c => c.citations), text: top.map(c => c.name.split(',')[0]), textposition: 'top center', textfont: { size: 10, color: css('--ink2') }, hoverinfo: 'skip', showlegend: false }],
    { hovermode: 'closest', xaxis: { title: { text: 'Papers with the institutes' } }, yaxis: { title: { text: 'Citations of those papers' } } });
}
function reachMore() { reachInit(); reachDraw(); placesInit(); placesDraw(); }

// ================================================================ Collaboration: collaboration distance
const nb = F.map(() => []);
D.fedges.forEach(([a, b]) => { nb[a].push(b); nb[b].push(a); });
function bfs(src) {
  const dist = new Int16Array(F.length).fill(-1), par = new Int32Array(F.length).fill(-1); dist[src] = 0; const q = [src];
  for (let h = 0; h < q.length; h++) { const u = q[h]; nb[u].forEach(v => { if (dist[v] < 0) { dist[v] = dist[u] + 1; par[v] = u; q.push(v); } }); }
  return { dist, par };
}
const facLabel = i => `${F[i].n} — ${SH[F[i].i]}, ${F[i].d}`;
const facIndex = text => { const t = (text || '').trim().toLowerCase(); if (!t) return -1; const ex = F.findIndex((f, i) => facLabel(i).toLowerCase() === t); if (ex >= 0) return ex; const m = F.map((f, i) => i).filter(i => F[i].n.toLowerCase() === t || facLabel(i).toLowerCase().startsWith(t)); return m.length === 1 ? m[0] : m.length ? -2 : -1; };
function distInit() {
  const top = d3.range(F.length).filter(i => nb[i].length).sort((a, b) => F[b].deg - F[a].deg)[0];
  const made = addSection('collab', 'cl-dist', card('How many co-author steps apart are two faculty?', 'How many co-author steps separate two faculty: 1 = they wrote a paper together, 2 = they share a collaborator, and so on.',
    `<div class="cmp-pick"><label>From <input list="cdList" id="cdA" placeholder="Start typing a name…"></label><label>To (optional) <input list="cdList" id="cdB" placeholder="Start typing a name…"></label><button class="btn grad-btn" id="cdGo">Show</button></div>
    <datalist id="cdList">${d3.range(F.length).filter(i => nb[i].length).map(i => `<option value="${esc(facLabel(i))}">`).join('')}</datalist><div id="cd-out"></div>`));
  if (made) { $('#cdA').value = facLabel(top); $('#cdGo').onclick = distDraw; ['cdA', 'cdB'].forEach(id => $('#' + id).addEventListener('keydown', e => { if (e.key === 'Enter') distDraw(); })); distDraw(); }
}
function distDraw() {
  const a = facIndex($('#cdA').value), b = facIndex($('#cdB').value), out = $('#cd-out');
  if (a < 0 || nb[a].length === 0) { out.innerHTML = `<p class="cmp-msg">${a === -2 ? 'Several people match; pick one from the list.' : 'Pick a faculty member who has at least one collaborator.'}</p>`; return; }
  const { dist, par } = bfs(a), reach = d3.range(F.length).filter(i => dist[i] > 0), by = d3.rollup(reach, v => v.length, i => dist[i]), maxd = d3.max(reach, i => dist[i]);
  const within2 = reach.filter(i => dist[i] <= 2).length, far = reach.slice().sort((x, y) => dist[y] - dist[x] || F[y].p - F[x].p).slice(0, 5);
  let pathHtml = '';
  if (b >= 0 && b !== a) {
    if (dist[b] < 0) pathHtml = `<p class="cmp-msg">${esc(F[a].n)} and ${esc(F[b].n)} are not connected through co-authorship.</p>`;
    else { const path = []; for (let v = b; v >= 0; v = par[v]) path.unshift(v); pathHtml = `<p class="cmp-msg"><b>${esc(F[a].n)}</b> to <b>${esc(F[b].n)}</b>: <b>${dist[b]}</b> step${dist[b] > 1 ? 's' : ''}.</p><div class="cd-path">${path.map((v, k) => `${k ? '<span class="arrow">→</span>' : ''}<span class="cd-chip">${esc(F[v].n)} <small>${SH[F[v].i]}</small></span>`).join('')}</div>`; }
  }
  out.innerHTML = pathHtml + `<div class="grid g2"><div>${chart('cd-hist', 260)}</div><div>${table(['', ''], [['Faculty reachable', fmt(reach.length) + ` of ${fmt(F.length - 1)}`], ['Within 2 steps', `${fmt(within2)} (${fmt1(100 * within2 / Math.max(reach.length, 1))}%)`],
    ['Average distance', fmt2(d3.mean(reach, i => dist[i]))], ['Farthest', `${maxd} steps`], ['Furthest people', far.map(i => esc(F[i].n) + ` <small>(${dist[i]})</small>`).join('; ')]])}</div></div>`;
  const hs = d3.range(1, maxd + 1);
  A.plot('cd-hist', [{ type: 'bar', x: hs, y: hs.map(h => by.get(h) || 0), marker: { color: css('--c1') }, hovertemplate: '%{x} step(s): %{y} faculty<extra></extra>' }], { margin: { l: 44, r: 12, t: 6, b: 40 }, bargap: .3, xaxis: { dtick: 1, title: { text: 'Steps from ' + F[a].n } }, yaxis: { title: { text: 'Faculty' } } });
}

// ================================================================ Faculty: head-to-head comparison
const q1n = i => facPapers[i].map(p => P[p]).filter(x => x[T.type] === 0 && /^Q[1-4]$/.test(x[T.q]));
const FM = i => {
  const f = F[i], ps = facPapers[i].map(p => P[p]), recent = ps.filter(x => x[T.year] >= 2022).length;
  return { f, ps, recent, fwci: mean(ps.map(x => x[T.fwci])) };
};
const ROWS = [   // [group, label, value(m), format, higher is better?]
  ['Profile', 'Institute', m => I[m.f.i], null], ['Profile', 'Department', m => m.f.d, null], ['Profile', 'Designation', m => m.f.des || '—', null], ['Profile', 'Status', m => m.f.s || '—', null],
  ['Output', 'Papers (2016–2026)', m => m.f.p, fmt, 1], ['Output', 'Journal papers', m => m.f.jp, fmt, 1], ['Output', 'Conference papers', m => m.f.cp, fmt, 1], ['Output', 'Papers since 2022', m => m.recent, fmt, 1],
  ['Output', 'Active years', m => m.f.ya, v => fmt(v), 1], ['Output', 'Papers per active year', m => m.f.ya ? m.f.p / m.f.ya : null, v => fmt1(v), 1], ['Output', 'First – last paper', m => m.f.fy ? `${m.f.fy} – ${m.f.ly}` : '—', null],
  ['Impact', 'Citations', m => m.f.c, fmt, 1], ['Impact', 'Citations per paper', m => m.f.cpp, v => fmt1(v), 1], ['Impact', 'h-index (2016–2026)', m => m.f.h, fmt, 1], ['Impact', 'i10-index', m => m.f.i10, fmt, 1],
  ['Impact', 'Most-cited paper (citations)', m => m.f.mc, fmt, 1], ['Impact', 'Cited papers (%)', m => m.f.p ? 100 * m.f.cit / m.f.p : null, v => fmt1(v) + '%', 1], ['Impact', 'Mean FWCI', m => m.fwci, v => fmt2(v), 1],
  ['Quality', 'Q1 share of ranked journal papers (%)', m => m.f.q1, v => fmt1(v) + '%', 1], ['Quality', 'Q1 papers', m => m.f.q1p, fmt, 1], ['Quality', 'Q1 papers in journals with IF above 5', m => m.f.q5, fmt, 1], ['Quality', 'Top journal', m => m.f.tj || '—', null],
  ['Collaboration', 'Collaborators in the faculty network', m => m.f.deg, fmt, 1], ['Collaboration', 'Joint papers with those collaborators', m => m.f.str, fmt, 1], ['Collaboration', 'Distinct co-authors (all)', m => m.f.dca, fmt, 1],
  ['Collaboration', 'Authors per paper', m => m.f.na, v => fmt1(v), null], ['Collaboration', 'Single-author equivalent', m => m.f.sae, v => fmt1(v), 1], ['Collaboration', 'Papers with outside co-authors (%)', m => m.f.ext, v => fmt1(v) + '%', null],
  ['Network position', 'Betweenness (bridging role)', m => m.f.btw, v => v.toFixed(4), 1], ['Network position', 'Collaborators in another institute', m => m.f.xi, fmt, 1], ['Network position', 'Collaborators in another department', m => m.f.xd, fmt, 1],
];
function cmpInit() {
  const depts = [...new Set(F.map(f => f.d))].sort();
  const made = addSection('faculty', 'fc-compare', card('How do two faculty compare?', 'Pick two people and press Compare. The higher value in each row is highlighted.',
    `<div class="cmp-pick"><label>Department ${sel('cmpDept', [['', 'All departments'], ...depts.map(d => [d, d])])}</label>
      <label>Faculty A <select id="cmpA"></select></label><label>Faculty B <select id="cmpB"></select></label>
      <button class="btn grad-btn" id="cmpGo">Compare</button><button class="btn" id="cmpSwap" title="Swap A and B">⇄</button></div>
      <div id="cmp-out"></div>`));
  if (!made) return;
  const fill = () => {
    const d = $('#cmpDept').value, keep = [$('#cmpA').value, $('#cmpB').value];
    const opts = '<option value="">Select faculty…</option>' + d3.range(F.length).filter(i => F[i].p > 0 && (!d || F[i].d === d)).sort((x, y) => F[x].n.localeCompare(F[y].n)).map(i => `<option value="${i}">${esc(F[i].n)} — ${SH[F[i].i]}</option>`).join('');
    ['cmpA', 'cmpB'].forEach((id, k) => { const el = $('#' + id); el.innerHTML = opts; if ([...el.options].some(o => o.value === keep[k])) el.value = keep[k]; });
  };
  fill(); $('#cmpDept').onchange = fill;
  const setPick = (id, i) => { $('#cmpDept').value = ''; fill(); $('#' + id).value = String(i); };
  $('#cmpGo').onclick = cmpDraw; $('#cmpSwap').onclick = () => { const a = $('#cmpA').value; $('#cmpA').value = $('#cmpB').value; $('#cmpB').value = a; cmpDraw(); };
  const dl = new URLSearchParams(((window.__startHash || '').split('?')[1]) || ''), da = +dl.get('cmpA'), db = +dl.get('cmpB');
  if ((window.__startHash || '').startsWith('faculty') && dl.has('cmpA') && dl.has('cmpB') && F[da] && F[db]) { setPick('cmpA', da); setPick('cmpB', db); setTimeout(() => { cmpDraw(); $('#fc-compare').scrollIntoView({ block: 'start' }); }, 0); return; }
  const top = d3.range(F.length).sort((a, b) => F[b].c - F[a].c).slice(0, 2);       // an example to start from
  $('#cmp-out').innerHTML = `<p class="cmp-msg">For example <a href="#faculty" id="cmpEx">${esc(F[top[0]].n)} and ${esc(F[top[1]].n)}</a>.</p>`;
  $('#cmpEx').onclick = e => { e.preventDefault(); setPick('cmpA', top[0]); setPick('cmpB', top[1]); cmpDraw(); };
}
function cmpDraw() {
  const pv = v => v === '' ? -1 : +v, a = pv($('#cmpA').value), b = pv($('#cmpB').value), out = $('#cmp-out');
  if (a < 0 || b < 0) { out.innerHTML = '<p class="cmp-msg">Pick two faculty members from the lists.</p>'; return; }
  if (a === b) { out.innerHTML = '<p class="cmp-msg">Pick two different people.</p>'; return; }
  const A_ = FM(a), B_ = FM(b); let grp = '';
  const rows = ROWS.map(([g, l, val, f, better]) => {
    const va = val(A_), vb = val(B_), num = typeof va === 'number' && typeof vb === 'number' && isFinite(va) && isFinite(vb);
    const head = g !== grp ? `<tr><td class="grp" colspan="4">${g}</td></tr>` : ''; grp = g;
    const shown = v => v == null || (typeof v === 'number' && !isFinite(v)) ? '—' : (f && typeof v === 'number' ? f(v) : esc(v));
    const winA = num && better && va > vb, winB = num && better && vb > va;
    const diff = num && f ? (va === vb ? 'equal' : `${va > vb ? 'A' : 'B'} higher by ${f(Math.abs(va - vb))}`) : '';
    return head + `<tr><td>${l}</td><td class="r ${winA ? 'win' : ''}">${shown(va)}</td><td class="r ${winB ? 'win' : ''}">${shown(vb)}</td><td class="r d">${diff}</td></tr>`;
  }).join('');
  const w = (D.fedges.find(e => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a)) || [])[2] || 0, { dist } = bfs(a);
  const common = nb[a].filter(v => nb[b].includes(v)), steps = dist[b];
  const rel = `<div class="cmp-rel"><b>Between them:</b> ${w ? `${w} joint paper${w > 1 ? 's' : ''}` : 'no joint paper'} · collaboration distance ${steps >= 0 ? steps + ' step' + (steps > 1 ? 's' : '') : 'not connected'} · ${common.length} shared collaborator${common.length === 1 ? '' : 's'}${common.length ? ': ' + common.slice(0, 6).map(v => esc(F[v].n)).join(', ') : ''}${F[a].i === F[b].i ? ' · same institute' : ''}${F[a].d === F[b].d ? ' · same department' : ''}.</div>`;
  const nm = i => `<div class="nm"><b>${esc(F[i].n)}</b><small>${SH[F[i].i]} · ${esc(F[i].d)}</small></div>`;
  out.innerHTML = `${rel}<div class="tbl-wrap cmp"><table><thead><tr><th>Measure</th><th class="r">${nm(a)}</th><th class="r">${nm(b)}</th><th class="r">Difference</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="grid g2 mt"><div>${chart('cmp-year', 260)}</div><div>${chart('cmp-q', 260)}</div></div>`;
  const ys = d3.range(2016, 2027), col = [css('--c1'), css('--c3')];
  A.plot('cmp-year', [a, b].map((i, k) => ({ type: 'bar', name: F[i].n, x: ys, y: ys.map(y => facPapers[i].filter(p => P[p][T.year] === y).length), marker: { color: col[k] }, hovertemplate: `${esc(F[i].n)} %{x}: %{y} papers<extra></extra>` })), { barmode: 'group', bargap: .25, margin: { l: 36, r: 8, t: 34, b: 34 }, title: { text: 'Papers per year', font: { size: 13 }, x: 0, y: .97 }, legend: { orientation: 'h', y: 1.2, x: 1, xanchor: 'right', font: { size: 11 } }, xaxis: { dtick: 1 } });
  const qs = ['Q1', 'Q2', 'Q3', 'Q4'];
  A.plot('cmp-q', [a, b].map((i, k) => ({ type: 'bar', name: F[i].n, x: qs, y: qs.map(q => q1n(i).filter(x => x[T.q] === q).length), marker: { color: col[k] }, hovertemplate: `${esc(F[i].n)} %{x}: %{y} journal papers<extra></extra>` })), { barmode: 'group', bargap: .35, margin: { l: 36, r: 8, t: 34, b: 34 }, title: { text: 'Journal papers by quartile', font: { size: 13 }, x: 0, y: .97 }, legend: { orientation: 'h', y: 1.2, x: 1, xanchor: 'right', font: { size: 11 } } });
}
function facultyMore() { cmpInit(); }

// ================================================================ Reach: does a partner's place change impact?
const PLACE = n => n.startsWith('India: ') ? n.slice(7) + ' (India)' : n;
function placesInit() {
  const made = addSection('reach', 'rc-places', card('Do co-authors from some places lift the institutes’ impact?', 'Mean impact of the papers of the selected institute(s) that have a co-author in each place, against that institute\'s own average. FWCI 1.0 is the world average for papers of the same field, year and type. Orange = above the institute average, grey = below.',
    `<div class="cmp-pick"><label>Institute ${sel('plI', [['all', 'All three'], ...I.map(n => [n, n])])}</label><label>Measure ${sel('plM', [['mean', 'Mean FWCI'], ['median', 'Median FWCI']])}</label></div><p class="cmp-msg" id="pl-note"></p>` + chart('pl-chart', 760) +
    `<p class="note">A place is listed only if at least 25 papers of the selected institute(s) have a co-author there. A paper counts for every place it has a co-author in. The mean is pulled up by a few very highly cited papers, so check the median too. This is an association: it does not show that working with that place causes the higher impact.</p>`));
  if (made) { $('#plI').onchange = $('#plM').onchange = placesDraw; }
}
function placesDraw() {
  if (!$('#pl-chart') || !NV.fwci_places) return;
  if (A.state.inst >= 0 && $('#plI').dataset.lens !== String(A.state.inst)) { $('#plI').value = I[A.state.inst]; $('#plI').dataset.lens = A.state.inst; }
  const sc = NV.fwci_places[$('#plI').value] || NV.fwci_places.all, m = $('#plM').value, base = sc.baseline[m], key = m === 'mean' ? 'lift' : 'lift_median';
  const rows = sc.rows.slice().sort((a, b) => a[key] - b[key]);
  const up = rows.filter(r => r[key] > 0);
  const top = rows.slice(-3).reverse().map(r => `${PLACE(r.place)} (${r[m].toFixed(2)})`).join(', ');
  $('#pl-note').innerHTML = `The institute average is <b>${base.toFixed(2)}</b> (${m}). <b>${up.length}</b> of ${rows.length} places are above it; highest: ${top}.`;
  const h = Math.max(420, rows.length * 20 + 60); $('#pl-chart').style.height = h + 'px';
  A.plot('pl-chart', [{ type: 'bar', orientation: 'h', y: rows.map(r => `${PLACE(r.place)} · ${r.n}`), x: rows.map(r => r[key]), marker: { color: rows.map(r => r[key] > 0 ? css('--brand3') : css('--axis')) },
    customdata: rows.map(r => [r.n, r[m], base]), hovertemplate: '%{y}<br>%{customdata[1]:.2f} vs our %{customdata[2]:.2f} (%{x:+.2f})<extra></extra>' }],
    { margin: { l: 190, r: 14, t: 6, b: 40 }, bargap: .25, xaxis: { title: { text: `${m === 'mean' ? 'Mean' : 'Median'} FWCI minus the institute average (label: place · papers)` }, zeroline: true }, yaxis: { automargin: true, tickfont: { size: 11 } } });
}

// ================================================================ Flows: who gives and who takes
const GT = NV.give_take || {};
function gtInit() {
  const made = addSection('flows', 'fl-gt', `<div class="grid g2">` + card('Which institutes cite the selected institute more than it cites those institutes?', 'For the partner institutes that exchange most citations with the selected institute: citations each partner gives the selected institute (right) against citations the selected institute gives that partner (left).',
    `<div class="cmp-pick"><label>Institute ${sel('gtI', I.map((n, k) => [k, n]))}</label></div>` + chart('gt-bars', 560)) +
    card('Do private universities boost the institutes’ citations?', 'Citations received and given, grouped by the kind of institute. Private universities are matched by name from a list, so treat this as approximate.', `<div id="gt-tbl"></div>`) + `</div>` +
    card('Do the three institutes cite each other equally?', 'Papers of one institute citing papers of another, in each direction.', `<div id="gt-pairs"></div>`));
  if (made) $('#gtI').onchange = gtDraw;
}
function gtDraw() {
  if (!$('#gt-bars') || !GT[I[0]]) return;
  if (A.state.inst >= 0 && $('#gtI').dataset.lens !== String(A.state.inst)) { $('#gtI').value = A.state.inst; $('#gtI').dataset.lens = A.state.inst; }
  const k = +$('#gtI').value, g = GT[I[k]], short = n => n.replace('Indian Institute of Technology', 'IIT').replace('National Institute of Technology', 'NIT').replace(' University', ' Univ.');
  const rows = g.rows.slice(0, 20).reverse();
  $('#fl-gt h2').textContent = `Which institutes cite ${SH[k]} more than ${SH[k]} cites those institutes?`;
  const mx = d3.max(rows, r => Math.max(r.we_cite, r.cites_us)), stp = Math.ceil(mx / 3 / 500) * 500, tv = d3.range(-3, 4).map(v => v * stp).filter(v => Math.abs(v) <= mx * 1.05);
  A.plot('gt-bars', [{ type: 'bar', orientation: 'h', name: `${SH[k]} cites partner institutes`, y: rows.map(r => short(r.name)), x: rows.map(r => -r.we_cite), marker: { color: css('--axis') }, customdata: rows.map(r => r.we_cite), hovertemplate: `%{y}: ${SH[k]} cites this institute %{customdata:,}×<extra></extra>` },
    { type: 'bar', orientation: 'h', name: `Partner institutes cite ${SH[k]}`, y: rows.map(r => short(r.name)), x: rows.map(r => r.cites_us), marker: { color: A.instColor(k) }, hovertemplate: `%{y}: this institute cites ${SH[k]} %{x:,}×<extra></extra>` }],
    { barmode: 'relative', bargap: .25, margin: { l: 200, r: 10, t: 6, b: 40 }, xaxis: { title: { text: `Citations (left: ${SH[k]} gives · right: ${SH[k]} receives)` }, tickvals: tv, ticktext: tv.map(v => fmt(Math.abs(v))) }, yaxis: { automargin: true, tickfont: { size: 11 } }, legend: { orientation: 'h', y: 1.06, x: 1, xanchor: 'right' } });
  const B = [['Private universities (named list)', g.private_univ], ['Other universities and colleges', g.other_univ], ['IITs, NITs, IIITs, IISERs, IISc', g.premier], ['Government labs and agencies', g.govt_lab], ['Industry', g.industry]];
  const rat = b => b.we_cite ? (b.cites_us / b.we_cite).toFixed(2) + '×' : '—';
  const pv = g.private_univ;
  $('#gt-tbl').innerHTML = `<p class="cmp-msg"><b>${I[k]}</b> receives <b>${fmt(pv.cites_us)}</b> citations from ${pv.institutes} private universities and gives those universities <b>${fmt(pv.we_cite)}</b>: ${pv.cites_us > pv.we_cite ? `private universities cite ${SH[k]} ${rat(pv)} as often as ${SH[k]} cites private universities` : `${SH[k]} cites private universities more than they cite ${SH[k]}`}. Private universities account for ${(pv.cites_us / g.total_in * 100).toFixed(0)}% of all the citations ${I[k]} receives from Indian institutes.</p>` +
    table(['Kind of institute', `Cite ${SH[k]}`, `${SH[k]} cites`, 'Ratio'], B.map(([n, b]) => [n, fmt(b.cites_us), fmt(b.we_cite), rat(b)])) +
    `<p class="note">A ratio above 1 means more citations come in to ${SH[k]} than go out. Gaps like this are normal: an institute that publishes a lot, or in the same fields as ${SH[k]}, will cite ${SH[k]} more often than the reverse, and papers can only cite older work.</p>`;
  const M = D.citNet.flow_matrix_source_rows_target_cols, pairs = [[0, 1], [0, 2], [1, 2]];
  $('#gt-pairs').innerHTML = table(['Pair', 'First cites second', 'Second cites first', 'Difference'], pairs.map(([a, b]) => { const x = M[I[a]][I[b]], y = M[I[b]][I[a]]; return [`${SH[a]} and ${SH[b]}`, `${SH[a]} → ${SH[b]}: ${fmt(x)}`, `${SH[b]} → ${SH[a]}: ${fmt(y)}`, `${x >= y ? '+' : '−'}${(Math.abs(x - y) / Math.min(x, y) * 100).toFixed(0)}%`]; })) +
    `<p class="note">The two directions are separate counts: how often one institute's papers cite the other's. They need not match, and here the gaps are small.</p>`;
}

// ================================================================ wiring
hook('pubs', pubsMore); hook('papers', papersMore); hook('reach', reachMore); hook('collab', distInit); hook('faculty', facultyMore); hook('flows', () => { gtInit(); gtDraw(); });
const foot = document.querySelector('.site-foot'); if (foot && D.built) { const s = document.createElement('span'); s.textContent = `Data built ${D.built}`; foot.append(s); }
try { A.rendered.delete(A.state.tab); A.go(A.state.tab); } catch (e) { console.error(e); }
})();
