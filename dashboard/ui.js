/* Research Atlas: interaction layer (command palette, chart toolbars, KPI motion, toasts, shortcuts). Needs app.js. */
(() => {
const A = window.atlas, D = window.DATA, F = D.fac, P = D.papers, I = D.insts;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const TABS = [...document.querySelectorAll('#nav button')].map(b => [b.dataset.tab, b.querySelector('.t').textContent.trim()]);
const typing = () => /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) && !document.activeElement.readOnly;
const store = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} } };

// ---------------------------------------------------------------- toasts
function toast(msg, color) {
  const t = document.createElement('div'); t.className = 'toast';
  t.innerHTML = `<span class="dot" style="background:${color || 'var(--brand1)'}"></span>${esc(msg)}`;
  $('#toasts').append(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, 2400);
}
document.addEventListener('atlas:toast', e => toast(e.detail));
document.addEventListener('atlas:inst', e => toast(e.detail < 0 ? 'Showing all three institutes' : `Filtered to ${I[e.detail]}`, e.detail < 0 ? null : A.instColor(e.detail)));

// ---------------------------------------------------------------- breadcrumbs
const setCrumb = t => { const x = TABS.find(([k]) => k === t); if (x && $('#crumbTab')) $('#crumbTab').textContent = x[1]; };
document.addEventListener('atlas:tab', e => { setCrumb(e.detail); requestAnimationFrame(reveal); });
setCrumb(A.state.tab);

// ---------------------------------------------------------------- sidebar collapse
const app = $('.app');
const toggleSide = () => {};

// ---------------------------------------------------------------- command palette
const partners = D.loc ? [...new Set(D.loc.partners.map(r => r[1]))] : [];
const pIdx = P.map((p, i) => [p[0].toLowerCase(), i]);
const fIdx = F.map((f, i) => [f.n.toLowerCase(), i, (f.d || '').toLowerCase()]);
const actions = [
  ['Toggle light / dark theme', 'T', () => $('#themeBtn').click()],
  ['Show keyboard shortcuts', '?', showKeys],
  ['Show all three institutes', '0', () => A.setInst(-1)],
  ...I.map((n, i) => [`Filter to ${n}`, '', () => A.setInst(i)]),
];
let items = [], sel = 0;
function score(text, q) { const i = text.indexOf(q); return i < 0 ? -1 : i === 0 ? 3 : text[i - 1] === ' ' ? 2 : 1; }
function buildList(q) {
  q = q.trim().toLowerCase();
  const groups = [];
  const pages = TABS.filter(([, l]) => !q || l.toLowerCase().includes(q)).map(([t, l], k) => ({ ic: '↗', tx: l, sub: `Go to page · ${TABS.findIndex(x => x[0] === t) + 1}`, run: () => A.go(t) }));
  if (pages.length) groups.push(['Pages', pages]);
  const acts = actions.filter(([l]) => !q || l.toLowerCase().includes(q)).map(([l, k, f]) => ({ ic: '⌘', tx: l, sub: k ? `shortcut ${k}` : '', run: f }));
  if (acts.length) groups.push(['Actions', q ? acts : acts.slice(0, 4)]);
  if (!q) {
    groups.push(['Top faculty', F.map((f, i) => i).sort((a, b) => F[b].h - F[a].h).slice(0, 5).map(i => fItem(i))]);
  } else if (q.length >= 2) {
    const fs = fIdx.map(([n, i, d]) => [Math.max(score(n, q), score(d, q) > 0 ? .5 : -1), i]).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0] || F[b[1]].h - F[a[1]].h).slice(0, 6);
    if (fs.length) groups.push(['Faculty', fs.map(([, i]) => fItem(i))]);
    const ps = partners.map(n => [score(n.toLowerCase(), q), n]).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0]).slice(0, 5);
    if (ps.length) groups.push(['Partner institutes', ps.map(([, n]) => ({ ic: '🏛', tx: n, sub: 'Indian partner', run: () => A.openPartner(n) }))]);
    const pp = pIdx.filter(([t]) => t.includes(q)).map(([, i]) => i).sort((a, b) => P[b][4] - P[a][4]).slice(0, 7);
    if (pp.length) groups.push(['Papers', pp.map(i => ({ ic: '📄', tx: P[i][0], sub: `${P[i][1]} · ${P[i][4].toLocaleString()} cites`, run: () => A.openPaper(i) }))]);
  }
  items = groups.flatMap(g => g[1]); sel = 0;
  let k = 0;
  $('#cmdkList').innerHTML = groups.map(([g, its]) => `<div class="cmdk-g">${g}</div>` + its.map(it => `<div class="cmdk-it" data-k="${k++}"><span class="ic">${it.ic}</span><span class="tx">${esc(it.tx)}</span><span class="sub">${esc(it.sub)}</span></div>`).join('')).join('')
    || `<div class="cmdk-g" style="padding:18px">No results for “${esc(q)}”</div>`;
  $('#cmdkList').querySelectorAll('.cmdk-it').forEach(e => { e.onmousemove = () => mark(+e.dataset.k); e.onclick = () => pick(+e.dataset.k); });
  mark(0);
}
function fItem(i) { const f = F[i]; return { ic: `<span class="dot" style="background:${A.instColor(f.i)}"></span>`, tx: f.n, sub: `${A.SHORT[f.i]} · ${f.d} · h ${f.h}`, run: () => A.openFaculty(i) }; }
function mark(k) { sel = Math.max(0, Math.min(items.length - 1, k)); $('#cmdkList').querySelectorAll('.cmdk-it').forEach(e => e.classList.toggle('act', +e.dataset.k === sel)); $('#cmdkList').querySelector('.act')?.scrollIntoView({ block: 'nearest' }); }
function pick(k) { const it = items[k]; if (!it) return; closePalette(); it.run(); }
function openPalette() { $('#cmdk').classList.add('on'); $('#cmdkIn').value = ''; buildList(''); setTimeout(() => $('#cmdkIn').focus(), 20); }
function closePalette() { $('#cmdk').classList.remove('on'); }
$('#cmdkIn').addEventListener('input', e => buildList(e.target.value));
$('#cmdkIn').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown') { mark(sel + 1); e.preventDefault(); } else if (e.key === 'ArrowUp') { mark(sel - 1); e.preventDefault(); }
  else if (e.key === 'Enter') { pick(sel); e.preventDefault(); } else if (e.key === 'Escape') closePalette();
});
$('#cmdk').addEventListener('mousedown', e => { if (e.target.id === 'cmdk') closePalette(); });
const q = $('#q'); q.addEventListener('focus', () => { q.blur(); openPalette(); }); q.addEventListener('click', openPalette);
document.querySelectorAll('[data-cmdk]').forEach(b => b.onclick = openPalette);
document.querySelectorAll('[data-go]').forEach(b => b.onclick = () => A.go(b.dataset.go));

// ---------------------------------------------------------------- modal (chart fullscreen, shortcuts)
function openModal(title, small) { $('#modalTitle').textContent = title; $('#modalBox').classList.toggle('small', !!small); $('#modalTools').innerHTML = ''; $('#modal').classList.add('on'); return $('#modalBody'); }
function closeModal() { const b = $('#modalBody'); if (b.querySelector('.js-plotly-plot')) Plotly.purge(b.querySelector('.js-plotly-plot')); b.innerHTML = ''; $('#modal').classList.remove('on'); }
$('#modalClose').onclick = closeModal;
$('#modal').addEventListener('mousedown', e => { if (e.target.id === 'modal') closeModal(); });
function showKeys() {
  const b = openModal('Keyboard shortcuts', true);
  b.innerHTML = `<div class="keys">${[['Command palette', 'Ctrl K  or  /'], ['Go to page 1–9', '1 … 9'], ['Toggle theme', 'T'], ['Show all institutes', '0'],
    ['Close panel / dialog', 'Esc'], ['This help', '?']].map(([a, k]) => `<span>${a}</span><span>${k.split('  ').map(x => `<kbd class="k2">${x}</kbd>`).join(' ')}</span>`).join('')}</div>
    <p class="note" style="margin-top:14px">Every chart has expand, PNG and CSV buttons in its top-right corner. Every table has a CSV button.</p>`;
}
$('#helpBtn').onclick = showKeys;

// ---------------------------------------------------------------- chart toolbars
const ICON = {
  expand: '<svg viewBox="0 0 24 24"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>',
  png: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/></svg>',
  csv: '<svg viewBox="0 0 24 24"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>',
  full: '<svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
};
const slug = s => (s || 'chart').replace(/[^\w]+/g, '_').replace(/^_|_$/g, '').toLowerCase();
function traceCSV(el) {
  const rows = [['series', 'x', 'y', 'value']];
  (el.data || []).forEach(t => {
    if (t.type === 'pie') t.labels.forEach((l, k) => rows.push([t.name || '', l, '', t.values[k]]));
    else if (t.type === 'heatmap') t.y.forEach((y, r) => t.x.forEach((x, c) => rows.push([t.name || '', x, y, t.z[r][c] ?? ''])));
    else if (t.type === 'sankey') t.link.source.forEach((s, k) => rows.push(['link', t.node.label[s], t.node.label[t.link.target[k]], t.link.value[k]]));
    else (t.x || []).forEach((x, k) => rows.push([t.name || '', x, t.y ? t.y[k] : '', t.customdata && typeof t.customdata[k] !== 'object' ? t.customdata[k] : '']));
  });
  return rows.map(r => r.map(v => '"' + String(v ?? '').replace(/"/g, '""') + '"').join(',')).join('\n');
}
function addTools(card) {
  if (card.dataset.tools) return;
  const head = card.querySelector('.card-h'), chart = card.querySelector('.chart'), net = card.querySelector('.net-wrap');
  if (!head && !net) return;
  card.dataset.tools = 1;
  const title = card.querySelector('h2')?.textContent || 'Chart';
  const box = document.createElement('div'); box.className = 'card-tools';
  if (chart) {
    box.innerHTML = `<button class="tbtn" data-a="expand" title="Expand">${ICON.expand}</button><button class="tbtn" data-a="png" title="Download PNG">${ICON.png}</button><button class="tbtn" data-a="csv" title="Download data (CSV)">${ICON.csv}</button>`;
    box.onclick = e => {
      const a = e.target.closest('[data-a]')?.dataset.a; if (!a || !chart.data) return;
      if (a === 'png') { Plotly.downloadImage(chart, { format: 'png', width: 1600, height: 900, filename: slug(title) }); toast('PNG downloaded'); }
      if (a === 'csv') { const l = document.createElement('a'); l.href = URL.createObjectURL(new Blob(['﻿' + traceCSV(chart)], { type: 'text/csv' })); l.download = slug(title) + '.csv'; l.click(); toast('Chart data downloaded'); }
      if (a === 'expand') {
        const b = openModal(title); const d = document.createElement('div'); d.style.cssText = 'width:100%;height:100%'; b.append(d);
        Plotly.newPlot(d, JSON.parse(JSON.stringify(chart.data)), Object.assign(JSON.parse(JSON.stringify(chart.layout)), { autosize: true, height: null, width: null }), { displayModeBar: true, displaylogo: false, responsive: true });
      }
    };
  } else if (net) {
    box.innerHTML = `<button class="tbtn" data-a="full" title="Fullscreen">${ICON.full}</button>`;
    box.onclick = () => (document.fullscreenElement ? document.exitFullscreen() : net.requestFullscreen?.());
  }
  if (head) head.append(box); else { box.style.cssText = 'position:absolute;right:12px;top:auto;bottom:44px;opacity:1'; net.append(box); }
}
document.querySelectorAll('.card').forEach(addTools);
document.addEventListener('fullscreenchange', () => setTimeout(() => window.dispatchEvent(new Event('resize')), 100));

// ---------------------------------------------------------------- reveal on scroll
const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -40px 0px' }) : null;
function reveal() {
  document.querySelectorAll('section.tab.on .card:not(.reveal), section.tab.on .hero:not(.reveal)').forEach((c, k) => {
    c.classList.add('reveal'); c.style.transitionDelay = Math.min(k, 6) * 40 + 'ms';
    if (io) io.observe(c); else c.classList.add('in');
  });
}
reveal();

// ---------------------------------------------------------------- KPI count-up + sparklines
function countUp(el) {
  const txt = el.textContent, m = txt.match(/^([\d,]+(?:\.\d+)?)(.*)$/); if (!m) return;
  const target = +m[1].replace(/,/g, ''), dec = (m[1].split('.')[1] || '').length, suf = m[2];
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const t0 = performance.now(), dur = 700, token = (el._cu = (el._cu || 0) + 1);
  const show = v => { el.textContent = v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suf; };
  const step = () => { if (el._cu !== token) return; const p = Math.max(0, Math.min(1, (performance.now() - t0) / dur));
    show(target * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
  setTimeout(() => { if (el._cu === token) { el._cu++; show(target); } }, dur + 150); // always land on the real value
}
function spark(vals, color) {
  const w = 92, h = 34, mx = Math.max(...vals), mn = Math.min(...vals), sx = k => k / (vals.length - 1) * w, sy = v => h - 3 - (v - mn) / ((mx - mn) || 1) * (h - 6);
  const pts = vals.map((v, k) => `${sx(k).toFixed(1)},${sy(v).toFixed(1)}`).join(' '), id = 'g' + Math.random().toString(36).slice(2, 7);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".35"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
    <polygon points="0,${h} ${pts} ${w},${h}" fill="url(#${id})"/><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${sx(vals.length - 1)}" cy="${sy(vals[vals.length - 1])}" r="2.6" fill="${color}"/></svg>`;
}
function decorateKpis() {
  const cards = document.querySelectorAll('#kpis .kpi'); if (!cards.length || cards[0].dataset.done) return;
  const inst = A.state.inst, sh = inst < 0 ? I : [I[inst]], yrs = D.ppy.filter(r => +r.year <= 2025);
  const color = inst < 0 ? getComputedStyle(document.documentElement).getPropertyValue('--brand1').trim() : A.instColor(inst);
  const series = [
    yrs.map(r => inst < 0 ? +r['all (unique papers)'] : +r[I[inst]]),
    yrs.map(r => sh.reduce((a, i) => a + +((D.velocity.find(v => v.institution === i && v.table.startsWith('citations received') && v.year === r.year) || {}).value || 0), 0)),
    null, null,
    yrs.map(r => sh.reduce((a, i) => a + (D.pub.quartiles[i]['Q1_fraction_by_year_%'][r.year] || 0), 0) / sh.length),
  ];
  cards.forEach((c, k) => { c.dataset.done = 1; countUp(c.querySelector('.val')); if (series[k]) c.insertAdjacentHTML('beforeend', spark(series[k], color)); });
}
new MutationObserver(decorateKpis).observe($('#kpis'), { childList: true });
decorateKpis();

// ---------------------------------------------------------------- keyboard
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#cmdk').classList.contains('on') ? closePalette() : openPalette(); return; }
  if (e.key === 'Escape') { if ($('#cmdk').classList.contains('on')) closePalette(); else if ($('#modal').classList.contains('on')) closeModal(); return; }
  if (typing() || $('#cmdk').classList.contains('on') || e.ctrlKey || e.metaKey || e.altKey) return;
  if (/^[1-9]$/.test(e.key) && TABS[+e.key - 1]) { A.go(TABS[+e.key - 1][0]); }
  else if (e.key === '0') A.setInst(-1);
  else if (e.key.toLowerCase() === 't') $('#themeBtn').click();
  else if (e.key === '?') showKeys();
}, true);
})();

// ---------------------------------------------------------------- interaction hints (where to click)
(() => {
  const PTR = '<svg viewBox="0 0 24 24"><path d="M9 3v10l-2.5-2.5a1.8 1.8 0 00-2.6 2.5L9 19c1 1.2 2.3 2 4 2h1a6 6 0 006-6v-3.5a1.5 1.5 0 00-3 0V11m0 0V9.5a1.5 1.5 0 00-3 0V11m0 0V8.5a1.5 1.5 0 00-3 0V11M9 3a1.5 1.5 0 013 0v8"/></svg>';
  const HINTS = {
    'ov-trend': "Click a point to list that year's papers", 'ov-q': 'Click a segment to list those papers', 'ov-table': 'Click a row to filter the whole dashboard to that institute',
    'pb-trend': 'Click a point or bar to list those papers', 'pb-q1y': "Click a point to list that year's Q1 papers", 'pb-q': 'Click a segment to list those papers',
    'pb-conf': 'Click a segment to list those conference papers', 'pb-venues': 'Click a venue to list its papers', 'pb-fields': 'Click a field to list its papers', 'pb-fieldimpact': "Click a bubble to list that field's papers",
    'pb-journals': 'Click a journal to list its papers',
    'fc-h': 'Click a band to filter the faculty table', 'fc-lb': 'Click a bar to open that faculty profile',
    'fc-table': 'Click a name for the full profile: papers, collaborators, partners, network position', 'fc-dept': 'Click a bubble to filter the table to that department',
    'pp-top10': 'Click a row for paper details · DOI opens the publisher page', 'pp-t30': 'Click a row for paper details and its authors', 'pp-ex': 'Search or sort, then click a row for details',
    'cn-top': 'Click a row to show that paper and its citation neighbourhood', 'fl-types': 'Click a type to list its institutes', 'fl-jac': 'Click a dot to open that partner', 'fl-partners': 'Click a bar to open that partner',
    'fn-comms': 'Click a row to highlight the community · click a name for the profile', 'fn-brokers': 'Click a row to locate the person in the network', 'fn-bridges': 'Click a bar to open the profile',
    'rc-loc': 'Click a segment to list those partners in the explorer below', 'rc-region': 'Click a bar to filter the partner explorer', 'rc-upset': 'Click a bar to list the shared partner institutes', 'rc-pairs': 'Click a name below for the faculty profile', 'rc-sankey': 'Click a partner type, an institute or a band to list every institute behind it', 'rc-trend': 'Hover a point for the count',
    'rc-peers': 'Click a row for joint papers and the faculty behind the link', 'rc-scatter': 'Click a dot for that faculty profile', 'rc-topfac': 'Click a name for the profile',
    'rc-ext': 'Click a row to see which faculty of the three institutes work with that author', 'rc-inst': 'Click an Indian institute for its joint papers and faculty', 'rc-citpapers': 'Click a paper for details',
    'rc-all': "Click a row for the partner's joint papers and faculty",
  };
  const NET = { 'cn-wrap': 'Click a node for paper details · hover for a preview · scroll to zoom, drag to pan', 'fn-wrap': 'Click a node for the faculty profile and their collaborators · click the legend to highlight a community', 'in-wrap': 'Click a partner for its joint papers and faculty · click one of the three institutes to highlight only its partners' };
  const pill = t => `<span class="hint">${PTR}${t}</span>`;
  Object.entries(HINTS).forEach(([id, t]) => {
    const head = document.getElementById(id)?.closest('.card')?.querySelector('.card-h > div');
    if (head && !head.querySelector('.hint')) head.insertAdjacentHTML('beforeend', `<div>${pill(t)}</div>`);
  });
  Object.entries(NET).forEach(([id, t]) => {
    const w = document.getElementById(id); if (w) w.insertAdjacentHTML('beforebegin', `<div class="hint-row">${pill(t)}</div>`);
  });
  // one-time tip on the overview
  let off = false; try { off = localStorage.getItem('atlas-tip') === 'off'; } catch (e) {}
  const acts = document.querySelector('.hero-actions');
  if (acts && !off) {
    acts.insertAdjacentHTML('afterend', `<div class="tipbar">${pill('Everything is clickable: names, nodes, bars and rows open details. Press Ctrl K to search.')}<button id="tipOff">Got it</button></div>`);
    document.getElementById('tipOff').onclick = e => { try { localStorage.setItem('atlas-tip', 'off'); } catch (x) {} e.target.parentElement.remove(); };
  }
})();
