/* Research Atlas: live removal simulation for the Resilience tab.
   Pick who may be removed, how they are ranked and how many to remove; the network, the largest-group share, the number of
   pieces and the cut vertices (people whose removal alone splits a group) update at once. Uses DATA.fac and DATA.fedges only. Needs app.js and extras.js. */
(() => {
const A = window.atlas, D = window.DATA, I = D.insts, SH = A.SHORT, F = D.fac;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = A.fmt, fmt1 = A.fmt1, css = A.css;

const style = document.createElement('style');
style.textContent = `.sim-bar{display:flex;flex-wrap:wrap;gap:12px 16px;align-items:flex-end;margin:6px 0 12px}.sim-bar label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted)}
.sim-bar select,.sim-bar input[type=number]{background:var(--surface,transparent);border:1px solid var(--rule,rgba(128,128,128,.3));border-radius:10px;padding:8px 10px;font:inherit;font-size:13.5px;color:var(--ink)}
.sim-run{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:4px 0 12px}.sim-run input[type=range]{flex:1 1 280px;min-width:220px}.sim-run b.num{min-width:90px}
.sim-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px}.sim-t{border:1px solid var(--rule,rgba(128,128,128,.25));border-radius:12px;padding:10px 12px}
.sim-t .v{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}.sim-t .l{font-size:12px;color:var(--muted);margin-top:2px}.sim-t.hot .v{color:var(--brand2,#ec4899)}
.sim-grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:16px}@media(max-width:900px){.sim-grid{grid-template-columns:1fr}}
.sim-net{position:relative;height:560px;border:1px solid var(--rule,rgba(128,128,128,.25));border-radius:14px;overflow:hidden}.sim-net svg{width:100%;height:100%}
.sim-lg{position:absolute;left:10px;bottom:8px;font-size:11.5px;color:var(--muted);background:var(--raise,rgba(255,255,255,.8));padding:6px 9px;border-radius:9px;line-height:1.6}
.sim-lg i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}.sim-cuts{font-size:13px;line-height:1.6;margin:8px 0 0}.sim-cuts span{display:inline-block;margin:2px 6px 2px 0;padding:2px 9px;border:1px solid var(--brand2,#ec4899);border-radius:999px;font-size:12.5px}
.sim-msg{font-size:13px;color:var(--muted);margin:6px 0}`;
document.head.append(style);

// ranking choices: [key, label, getter(face value), adaptive?]
const BY = [
  ['btw', 'Betweenness: who sits on the most shortest routes', f => f.btw],
  ['deg', 'Collaborators: most co-authors first', f => f.deg],
  ['degA', 'Collaborators, re-ranked after every removal', null],
  ['eig', 'Eigenvector: linked to the best-connected people', f => f.eig],
  ['clo', 'Closeness: can reach everyone fastest', f => f.clo],
  ['str', 'Joint papers with other faculty', f => f.str],
  ['xi', 'Collaborators at other institutes', f => f.xi],
  ['xd', 'Collaborators in other departments', f => f.xd],
  ['h', 'h-index', f => f.h],
  ['p', 'Papers', f => f.p],
  ['c', 'Citations', f => f.c],
  ['rnd', 'Random (a fixed shuffle)', null]
];
const S = { seed: 7, k: 0, play: null, curve: null, order: [], net: null };

function mulberry(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

// the network for the chosen scope: local indices into `ids`
function buildNet(scope, minW) {
  const ids = F.map((_, i) => i).filter(i => scope === 'all' || I[F[i].i] === scope), loc = new Map(ids.map((g, k) => [g, k]));
  const adj = ids.map(() => []);
  D.fedges.forEach(([a, b, w]) => { if (w >= minW && F[a].n !== F[b].n && loc.has(a) && loc.has(b)) { const x = loc.get(a), y = loc.get(b); adj[x].push(y); adj[y].push(x); } });
  return { ids, adj, n: ids.length, m: adj.reduce((s, a) => s + a.length, 0) / 2 };
}

// components, largest group and cut vertices of the people who are still in (iterative, linear time)
function analyse(adj, alive) {
  const n = adj.length, disc = new Int32Array(n).fill(-1), low = new Int32Array(n), par = new Int32Array(n).fill(-1), ptr = new Int32Array(n), comp = new Int32Array(n).fill(-1), extra = new Int32Array(n);
  let t = 0, nc = 0, lcc = 0, linked = 0, isolated = 0, lccId = -1; const sizes = [];
  for (let s = 0; s < n; s++) {
    if (!alive[s] || disc[s] >= 0) continue;
    let size = 1, rc = 0; disc[s] = low[s] = t++; comp[s] = nc; const st = [s];
    while (st.length) {
      const u = st[st.length - 1];
      if (ptr[u] < adj[u].length) {
        const v = adj[u][ptr[u]++]; if (!alive[v]) continue;
        if (disc[v] < 0) { par[v] = u; disc[v] = low[v] = t++; comp[v] = nc; size++; st.push(v); if (u === s) rc++; }
        else if (v !== par[u]) low[u] = Math.min(low[u], disc[v]);
      } else {
        st.pop(); const p = par[u];
        if (p >= 0) { low[p] = Math.min(low[p], low[u]); if (p !== s && low[u] >= disc[p]) extra[p]++; }
      }
    }
    if (rc > 1) extra[s] = rc - 1;
    sizes.push(size); if (size > lcc) { lcc = size; lccId = nc; } if (size === 1) isolated++; else linked++;
    nc++;
  }
  let cuts = 0; for (let i = 0; i < n; i++) if (extra[i] > 0) cuts++;
  return { lcc, lccId, comp, extra, pieces: nc, linked, isolated, cuts };
}

function candidates(net, from, dept) {
  return net.ids.map((g, k) => k).filter(k => (from === 'all' || I[F[net.ids[k]].i] === from) && (!dept || F[net.ids[k]].d === dept));
}
function ordering(net, cand, by) {
  if (by === 'rnd') { const r = mulberry(S.seed), a = cand.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
  if (by === 'degA') {   // always take the person who currently has the most remaining collaborators
    const alive = new Uint8Array(net.n).fill(1), deg = net.adj.map(a => a.length), left = new Set(cand), out = [];
    while (left.size) { let b = -1; left.forEach(k => { if (b < 0 || deg[k] > deg[b] || (deg[k] === deg[b] && k < b)) b = k; }); left.delete(b); alive[b] = 0; out.push(b); net.adj[b].forEach(v => { if (alive[v]) deg[v]--; }); }
    return out;
  }
  const get = BY.find(b => b[0] === by)[2];
  return cand.slice().sort((a, b) => get(F[net.ids[b]]) - get(F[net.ids[a]]) || a - b);
}
function curve(net, order) {
  const alive = new Uint8Array(net.n).fill(1), out = [];
  const rec = () => { const r = analyse(net.adj, alive); out.push({ lcc: r.lcc / net.n, pieces: r.pieces - (net.n - order.length ? 0 : 0), cuts: r.cuts, linked: r.linked }); };
  rec(); order.forEach(k => { alive[k] = 0; rec(); });
  return out;
}

const ctl = () => ({ scope: $('#simScope').value, from: $('#simFrom').value, dept: $('#simDept').value, by: $('#simBy').value, minW: +$('#simMinW').value });
function recompute() {
  const c = ctl(); S.net = buildNet(c.scope, c.minW);
  const cand = candidates(S.net, c.from === 'all' ? 'all' : c.from, c.dept);
  S.order = ordering(S.net, cand, c.by); S.curve = curve(S.net, S.order);
  $('#simK').max = S.order.length; S.k = Math.min(S.k, S.order.length); $('#simK').value = S.k;
  $('#simShuf').style.display = c.by === 'rnd' ? '' : 'none';
  layout(); drawCurves(); update();
}

// one fixed layout for the people who have at least one link at the start
function layout() {
  const net = S.net, wrap = $('#sim-net'), svg = d3.select('#sim-svg'); svg.selectAll('*').remove();
  const W = wrap.clientWidth || 700, H = wrap.clientHeight || 560;
  const ids = []; net.adj.forEach((a, k) => { if (a.length) ids.push(k); });
  const nodes = ids.map(k => ({ k })), byK = new Map(nodes.map(n => [n.k, n])), links = [];
  net.adj.forEach((a, x) => a.forEach(y => { if (x < y && byK.has(x) && byK.has(y)) links.push({ source: byK.get(x), target: byK.get(y) }); }));
  const sim = d3.forceSimulation(nodes).force('link', d3.forceLink(links).distance(22).strength(.5)).force('charge', d3.forceManyBody().strength(-30).distanceMax(240))
    .force('x', d3.forceX(W / 2).strength(.07)).force('y', d3.forceY(H / 2).strength(.07)).force('collide', d3.forceCollide(5)).stop();
  for (let i = 0; i < 280; i++) sim.tick();
  const xs = d3.extent(nodes, n => n.x), ys = d3.extent(nodes, n => n.y), sc = Math.min((W - 40) / ((xs[1] - xs[0]) || 1), (H - 40) / ((ys[1] - ys[0]) || 1), 3);
  nodes.forEach(n => { n.px = W / 2 + (n.x - (xs[0] + xs[1]) / 2) * sc; n.py = H / 2 + (n.y - (ys[0] + ys[1]) / 2) * sc; });
  const g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([.5, 8]).on('zoom', e => g.attr('transform', e.transform))).on('dblclick.zoom', null);
  S.link = g.append('g').selectAll('line').data(links).join('line').attr('x1', l => l.source.px).attr('y1', l => l.source.py).attr('x2', l => l.target.px).attr('y2', l => l.target.py).attr('stroke', css('--axis')).attr('stroke-width', 1);
  S.node = g.append('g').selectAll('circle').data(nodes).join('circle').attr('cx', n => n.px).attr('cy', n => n.py).attr('r', 4.2).style('cursor', 'pointer')
    .on('click', (e, n) => A.openFaculty(net.ids[n.k]));
  S.node.append('title').text(n => { const f = F[net.ids[n.k]]; return `${f.n} (${SH[f.i]}, ${f.d}) · ${f.deg} collaborators · betweenness ${f.btw.toFixed(3)}`; });
  S.nodeData = nodes; S.linkData = links;
}

function update() {
  const net = S.net, k = S.k, alive = new Uint8Array(net.n).fill(1); for (let i = 0; i < k; i++) alive[S.order[i]] = 0;
  const r = analyse(net.adj, alive), c = S.curve[k], left = net.n - k, edgesLeft = (() => { let m = 0; net.adj.forEach((a, x) => { if (alive[x]) a.forEach(y => { if (alive[y] && x < y) m++; }); }); return m; })();
  const start = S.curve[0];
  $('#sim-tiles').innerHTML = [
    [`${k} of ${S.order.length}`, 'removed so far', ''],
    [fmt(left), 'faculty still in the network', ''],
    [fmt(edgesLeft), `joint-paper links left (of ${fmt(net.m)})`, ''],
    [`${fmt1(100 * r.lcc / net.n)}%`, `largest connected group, share of all ${fmt(net.n)} faculty (${fmt1(100 * start.lcc)}% at the start)`, ''],
    [fmt(r.linked), `connected groups of 2 or more people (${fmt(r.isolated)} people on their own)`, ''],
    [fmt(r.cuts), 'cut vertices: people whose removal alone would split a group', r.cuts ? 'hot' : '']
  ].map(([v, l, cl]) => `<div class="sim-t ${cl}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  // colours
  const lccOf = r.lccId;
  S.node.attr('fill', n => { const g = net.ids[n.k], a = alive[n.k]; return !a ? 'transparent' : A.instColor(F[g].i); })
    .attr('opacity', n => (!alive[n.k] ? .9 : r.comp[n.k] === lccOf ? 1 : .45))
    .attr('stroke', n => (!alive[n.k] ? css('--c4') : r.extra[n.k] > 0 ? css('--brand2') : css('--surface'))).attr('stroke-width', n => (!alive[n.k] ? 1 : r.extra[n.k] > 0 ? 3 : 1))
    .attr('stroke-dasharray', n => (!alive[n.k] ? '2 2' : null)).attr('r', n => (r.extra[n.k] > 0 && alive[n.k] ? 6.5 : 4.2));
  S.link.attr('stroke-opacity', l => (alive[l.source.k] && alive[l.target.k] ? (r.comp[l.source.k] === lccOf ? .55 : .3) : 0));
  const cutList = []; for (let i = 0; i < net.n; i++) if (r.extra[i] > 0 && alive[i]) cutList.push([i, r.extra[i]]);
  cutList.sort((a, b) => b[1] - a[1] || F[net.ids[b[0]]].btw - F[net.ids[a[0]]].btw);
  $('#sim-cuts').innerHTML = cutList.length ? `<b>Cut vertices now (${cutList.length}):</b> ` + cutList.slice(0, 8).map(([i, e]) => `<span title="removing this person alone leaves ${e + 1} separate pieces">${esc(F[net.ids[i]].n)} (${SH[F[net.ids[i]].i]}) → ${e + 1} pieces</span>`).join('') + (cutList.length > 8 ? ` and ${cutList.length - 8} more` : '') : '<b>No cut vertex left:</b> no single person’s removal would split a group any further.';
  const last = S.order.slice(Math.max(0, k - 6), k).reverse().map(i => F[net.ids[i]].n), next = S.order[k];
  $('#sim-msg').innerHTML = `${k ? `<b>Last removed:</b> ${last.map(esc).join(', ')}. ` : ''}${next != null ? `<b>Next in line:</b> ${esc(F[net.ids[next]].n)} (${SH[F[net.ids[next]].i]}).` : '<b>Everyone allowed by the filters has been removed.</b>'}`;
  $('#simKv').textContent = `${k} removed`;
  if (window.Plotly) ['sim-c1', 'sim-c2'].forEach((id, j) => { const gd = document.getElementById(id); if (gd && gd.layout) Plotly.relayout(gd, { shapes: [{ type: 'line', x0: k, x1: k, y0: 0, y1: 1, yref: 'paper', line: { color: css('--brand3'), width: 2 } }] }); });
}

function drawCurves() {
  const cv = S.curve, xs = cv.map((_, i) => i), col = css('--brandInk');
  A.plot('sim-c1', [{ type: 'scatter', mode: 'lines', x: xs, y: cv.map(c => c.lcc * 100), line: { color: col, width: 2.5 }, hovertemplate: '%{x} removed: %{y:.1f}% of faculty in the largest group<extra></extra>' }],
    { margin: { l: 46, r: 10, t: 6, b: 38 }, xaxis: { title: { text: 'People removed' } }, yaxis: { title: { text: 'Largest group (% of faculty)' }, rangemode: 'tozero', ticksuffix: '%' }, shapes: [] });
  A.plot('sim-c2', [{ type: 'scatter', mode: 'lines', x: xs, y: cv.map(c => c.cuts), line: { color: css('--brand3'), width: 2.5 }, hovertemplate: '%{x} removed: %{y} cut vertices<extra></extra>' }],
    { margin: { l: 46, r: 10, t: 6, b: 38 }, xaxis: { title: { text: 'People removed' } }, yaxis: { title: { text: 'Cut vertices' }, rangemode: 'tozero' }, shapes: [] });
}

function init() {
  const sec = $('#tab-resil'); if (!sec || $('#sim-wrap')) return;
  const depts = [...new Set(F.map(f => f.d))].sort(), opt = (arr) => arr.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
  const wrap = document.createElement('div'); wrap.id = 'sim-wrap'; wrap.className = 'mt';
  wrap.innerHTML = `<div class="card"><div class="card-h"><div><h2>What happens when faculty are removed one by one?</h2><p>Choose who can be removed and how they are ranked, then drag the slider or press Play. The network, the share held by the largest group and the cut vertices update at once.</p></div></div>
    <div class="sim-bar">
      <label>Network <select id="simScope">${opt([['all', 'All three institutes'], ...I.map(n => [n, n])])}</select></label>
      <label>Remove people from <select id="simFrom">${opt([['all', 'Everyone in the network'], ...I.map(n => [n, n])])}</select></label>
      <label>Department <select id="simDept">${opt([['', 'All departments'], ...depts.map(d => [d, d])])}</select></label>
      <label>Rank by (removed first) <select id="simBy">${opt(BY.map(b => [b[0], b[1]]))}</select></label>
      <label>Count a link only from <select id="simMinW">${opt([[1, '1 joint paper'], [2, '2 joint papers'], [3, '3 joint papers'], [5, '5 joint papers']])}</select></label>
    </div>
    <div class="sim-run"><button class="btn" id="simM1">−1</button><input type="range" id="simK" min="0" max="0" value="0"><button class="btn" id="simP1">+1</button><button class="btn" id="simP5">+5</button><button class="btn grad-btn" id="simPlay">Play</button><button class="btn" id="simReset">Reset</button><button class="btn" id="simShuf" style="display:none">Reshuffle</button><b class="num" id="simKv">0 removed</b></div>
    <div class="sim-tiles" id="sim-tiles"></div>
    <div class="sim-grid"><div><div class="sim-net" id="sim-net"><svg id="sim-svg"></svg><div class="sim-lg"><i style="background:${A.instColor(0)}"></i>${SH[0]} <i style="background:${A.instColor(1)}"></i>${SH[1]} <i style="background:${A.instColor(2)}"></i>${SH[2]}<br>Faded = cut off from the largest group · pink ring = cut vertex · dashed = removed</div></div>
      <p class="sim-msg" id="sim-msg"></p><p class="sim-cuts" id="sim-cuts"></p></div>
      <div><div class="chart" id="sim-c1" style="height:260px"></div><p class="cap">Largest group, share of all faculty, as more people are removed. The orange vertical line marks where you are.</p><div class="chart" id="sim-c2" style="height:260px"></div><p class="cap">Cut vertices left in the network as more people are removed.</p></div></div>
    <p class="note">A <b>cut vertex</b> (articulation point) is a person whose removal alone splits a connected group into two or more pieces. People who are not linked to any other faculty member are not drawn; they are counted as “on their own”. Only links between verified faculty of the three institutes are used.</p></div>`;
  const anchor = $('#rs-body'); anchor ? anchor.after(wrap) : sec.append(wrap);
  ['simScope', 'simFrom', 'simDept', 'simBy', 'simMinW'].forEach(id => $('#' + id).addEventListener('change', () => { S.k = 0; stop(); recompute(); }));
  $('#simScope').addEventListener('change', () => { if ($('#simScope').value !== 'all') $('#simFrom').value = $('#simScope').value; });
  $('#simK').addEventListener('input', () => { S.k = +$('#simK').value; update(); });
  const step = d => { stop(); S.k = Math.max(0, Math.min(S.order.length, S.k + d)); $('#simK').value = S.k; update(); };
  $('#simM1').onclick = () => step(-1); $('#simP1').onclick = () => step(1); $('#simP5').onclick = () => step(5);
  $('#simReset').onclick = () => { stop(); S.k = 0; $('#simK').value = 0; update(); };
  $('#simShuf').onclick = () => { S.seed = Math.floor(Math.random() * 1e6); S.k = 0; stop(); recompute(); };
  function stop() { if (S.play) { clearInterval(S.play); S.play = null; $('#simPlay').textContent = 'Play'; } }
  $('#simPlay').onclick = () => {
    if (S.play) return stop();
    if (S.k >= S.order.length) S.k = 0;
    $('#simPlay').textContent = 'Pause';
    S.play = setInterval(() => { if (S.k >= S.order.length) return stop(); S.k++; $('#simK').value = S.k; update(); }, 220);
  };
  recompute();
}
const base = A.RENDER.resil;
A.RENDER.resil = () => { base(); try { init(); } catch (e) { console.error('simulator', e); } };
try { A.rendered.delete('resil'); if (A.state.tab === 'resil') A.go('resil'); } catch (e) { console.error(e); }
})();
