/* Research Atlas: one short caption under every chart and network: what the x axis and y axis mean, plus one fact read from the data
   that is plotted right now (it changes with the institute lens, the year range and the chart's own controls).
   The axis wording is written by hand below; the "In this chart" sentence is computed from the plotted data. Needs app.js. */
(() => {
const A = window.atlas, $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = v => Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en') : Math.abs(v) >= 100 ? String(Math.round(v)) : String(+(+v).toFixed(2));
const clean = s => String(s ?? '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();

const style = document.createElement('style');
style.textContent = `.cap{margin:6px 2px 2px;font-size:12.5px;line-height:1.5;color:var(--muted)}.cap b{color:var(--ink);font-weight:600}.cap .ci{display:block;margin-top:2px;color:var(--ink)}.cap .ci::before{content:"In this chart: ";color:var(--brandInk,#7c3aed);font-weight:600}`;
document.head.append(style);

// what each axis means, in plain words
const X = (x, y, read = '') => ({ x, y, read });
const CAP = {
  'ov-trend': X('year', 'papers published that year (2026 is only part of a year)'),
  'ov-q': X('share of journal papers (%) in each quartile, Q1 best', 'institute'),
  'pb-trend': X('year', 'papers published that year (2026 is only part of a year)'),
  'pb-q1y': X('year', 'share of ranked journal papers that are in Q1 journals (%)'),
  'pb-q': X('share of journal papers (%) in each quartile, Q1 best', 'institute'),
  'pb-conf': X('share of conference papers (%) by venue rank', 'institute'),
  'pb-fields': X('number of papers', 'research field'),
  'pb-fieldimpact': X('papers in the field (log scale)', 'mean citations per paper; each dot is one field'),
  'tr-chart': X('year', 'the measure chosen in the “Measure” box'),
  'rd-chart': X('each spoke is a subject area', 'distance from the centre is the number of papers, on a square-root scale; one shape per institute'),
  'fc-h': X('h-index band', 'number of faculty in that band'),
  'fc-lb': X('h-index', 'faculty member'),
  'fc-dept': X('papers per faculty member in the department', 'share of journal papers in Q1 (%); each dot is a department'),
  'pp-t30chart': X('a characteristic of the 30 most-cited papers', 'how many (or what %) of those papers have it'),
  'sc-chart': X('publication year', 'the measure chosen in “Vertical axis”; each dot is one paper'),
  'cn-indeg': X('in-degree: how many papers in the set cite this paper (log scale)', 'number of papers with that in-degree (log scale)'),
  'cn-flow': X('cited institute (column)', 'citing institute (row); each cell is the number, or share, of citation links'),
  'cn-src': X('share of citation links (%)', 'institute of the cited paper; bars split by who cites'),
  'cn-ccdf': X('number of links (log scale)', 'share of papers with at least that many links (log scale)'),
  'cn-outdeg': X('out-degree: how many papers in the set this paper cites, its references that are in the set (log scale)', 'number of papers with that out-degree (log scale)'),
  'cn-nref': X('references listed for a paper (log scale)', 'number of papers (log scale)'),
  'fn-bridges': X('co-authorship links to faculty of other institutes', 'faculty member'),
  'mv-sankey': X('left: institute before the move; right: institute now', 'one middle box per person who moved; ribbon width is one person'),
  'cd-hist': X('co-author steps from the selected person', 'number of faculty at that distance'),
  'rc-upset': X('which of the three institutes work with the partner', 'number of Indian partner institutes in that group'),
  'rc-loc': X('share of joint-paper links (%)', 'institute; bars split by how near the partner is'),
  'rc-sankey': X('left: institute', 'right: type of partner; ribbon width is joint-paper links'),
  'rc-region': X('region of the partner institute', 'joint-paper links, coloured by institute'),
  'rc-trend': X('year', 'joint papers with peer institutes'),
  'rc-scatter': X('co-authors inside the faculty member’s own institute (log scale)', 'co-authors outside it (log scale); each dot is one faculty member'),
  'rc-inst': X('papers written with the three institutes', 'outside institute'),
  'rc-cit': X('share of all citations received (%)', 'where the citing paper comes from'),
  'rm-country': X('number of papers', 'foreign country of the co-author'),
  'rm-coauth': X('papers written with the institutes', 'citations of those papers; each dot is one outside co-author'),
  'pl-chart': X('mean impact (FWCI) of papers with a co-author there, minus the institute average', 'place · number of papers'),
  'fl-ratio': X('year', 'citations received ÷ citations given; 1 means balanced, below 1 means more given than received'),
  'fl-vel': X('publication year of the papers', 'citations per paper per year'),
  'fl-cluster': X('type of institute', 'share of citations (%), log scale'),
  'fl-in': X('citations received from the institute', 'citing institute'),
  'fl-out': X('citations given to the institute', 'cited institute'),
  'fl-partners': X('co-authored papers', 'partner institute · which institute it works with'),
  'fl-types': X('count (log scale)', 'type of partner'),
  'fl-jac': X('research-topic similarity, 0 to 1', 'joint papers (log scale); each dot is one partner'),
  'gt-bars': X('citations: left given, right received by the selected institute', 'partner institute'),
  'md-funnel': X('number of records left', 'each bar is one cleaning step'),
  'md-qsrc': X('number of papers (log scale)', 'where the quartile label came from'),
  'rs-curve': X('share of faculty removed (%)', 'share of faculty still in the largest connected group; one line per way of removing people')
};

// a fact read from the plotted data
const arr = v => (v == null ? [] : Array.from(v));
const series = gd => (gd.data || []).filter(t => t.visible !== 'legendonly' && !/partial/i.test(t.name || ''));
function points(t) {
  const x = arr(t.x), y = arr(t.y), h = t.orientation === 'h';
  return x.map((xv, i) => ({ s: t.name || '', t, lab: clean(h ? y[i] : xv), val: +(h ? xv : y[i]), x: xv, y: y[i], i })).filter(p => isFinite(p.val));
}
const nm = p => (p.s ? ` (${clean(p.s)})` : '');
const unit = (gd, t) => { const ax = gd.layout[t.orientation === 'h' ? 'xaxis' : 'yaxis'], ti = ax && ax.title && (ax.title.text || ax.title); return /%|share/i.test(ti || '') ? '%' : ''; };
const labelOf = (t, i) => { const c = arr(t.customdata)[i]; const v = Array.isArray(c) ? c.find(z => typeof z === 'string') : c; const x = typeof v === 'string' ? v : arr(t.text)[i]; return clean(typeof x === 'string' ? x.split('<br>')[0] : ''); };
function insight(id, gd) {
  const S = series(gd); if (!S.length) return '';
  const t0 = S[0];
  if (id === 'mv-sankey') {
    const lab = arr(t0.node.label), src = arr(t0.link.source), tgt = arr(t0.link.target), mid = new Map(), cnt = {};
    src.forEach((a, k) => { if (/before/.test(lab[a])) mid.set(tgt[k], clean(lab[a]).replace(/ \(.*$/, '')); });
    src.forEach((a, k) => { if (mid.has(a)) { const key = mid.get(a) + ' → ' + clean(lab[tgt[k]]).replace(/ \(.*$/, ''); cnt[key] = (cnt[key] || 0) + 1; } });
    return `${mid.size} faculty moved: ` + Object.entries(cnt).map(([k, v]) => `${k} (${v})`).join(', ') + '.';
  }
  if (t0.type === 'sankey') {
    const l = t0.link, lab = t0.node.label, v = arr(l.value); if (!v.length) return '';
    const k = v.indexOf(Math.max(...v)); return `largest flow: ${clean(lab[arr(l.source)[k]])} → ${clean(lab[arr(l.target)[k]])} (${fmt(v[k])}) out of ${fmt(v.reduce((a, c) => a + c, 0))} in total.`;
  }
  if (t0.type === 'funnel') { const x = arr(t0.x); return `${fmt(x[x.length - 1])} of the ${fmt(x[0])} records remain (${(100 * x[x.length - 1] / x[0]).toFixed(0)}%).`; }
  if (t0.type === 'heatmap') {
    let b = null; const z = arr(t0.z).map(arr), xs = arr(t0.x), ys = arr(t0.y);
    z.forEach((r, i) => r.forEach((v, j) => { if (v != null && (!b || v > b.v)) b = { v, i, j }; })); if (!b) return '';
    return `highest cell: ${clean(ys[b.i])} → ${clean(xs[b.j]).replace(/^→ /, '')} with ${fmt(b.v)}.`;
  }
  if (t0.type === 'scatterpolar') return S.map(t => { const r = arr(t.r), k = r.indexOf(Math.max(...r)); return `${clean(t.name)}: largest in ${clean(arr(t.theta)[k])}`; }).join('; ') + '.';
  if (id === 'fl-ratio') return S.filter(t => t.name).map(t => { const y = arr(t.y).map(Number), n = y.filter(v => v < 1).length; return `${clean(t.name)} is below 1 in ${n} of ${y.length} years`; }).join('; ') + '.';
  if (id === 'rs-curve') {
    const at = S.filter(t => t.name).map(t => { const x = arr(t.x).map(Number), k = x.findIndex(v => v >= 10); return k >= 0 ? `${clean(t.name)} ${(+arr(t.y)[k] * (arr(t.y)[k] <= 1 ? 100 : 1)).toFixed(0)}%` : null; }).filter(Boolean);
    return at.length ? `after 10% of faculty are removed, the largest group holds: ${at.join('; ')}.` : '';
  }
  if (['ov-trend', 'pb-trend', 'tr-chart', 'rc-trend', 'fl-vel', 'pb-q1y'].includes(id)) {
    const P = S.flatMap(points), best = P.reduce((m, p) => (!m || p.val > m.val ? p : m), null); if (!best) return '';
    const ls = S.map(t => ({ t, p: points(t) })).filter(o => o.p.length), ly = ls.length ? ls[0].p[ls[0].p.length - 1].lab : '';
    const last = ls.map(o => `${clean(o.t.name)} ${fmt(o.p[o.p.length - 1].val)}${unit(gd, o.t) || ''}`);
    return `highest value: ${best.lab}${nm(best)} with ${fmt(best.val)}${unit(gd, best.t || S[0])}; latest ${(gd.data || []).some(t => /partial/i.test(t.name || '')) ? 'complete ' : ''}year (${ly}): ${last.join(', ')}.`;
  }
  const P = S.flatMap(points); if (P.length < 2) return '';
  const hi = P.reduce((m, p) => (p.val > m.val ? p : m)), lo = P.reduce((m, p) => (p.val < m.val ? p : m));
  const isBar = t0.type === 'bar';
  const u = unit(gd, hi.t || t0);
  if (id === 'cn-indeg' || id === 'cn-outdeg') { const mx = P.reduce((m, p) => (+p.x > +m.x ? p : m)), one = +hi.x === 1 ? 'only 1 paper' : `${fmt(+hi.x)} papers`; return id === 'cn-indeg' ? `${fmt(hi.val)} papers are cited by ${one} in the set; the most any paper receives is ${fmt(+mx.x)} citations from papers in the set.` : `${fmt(hi.val)} papers cite ${one} in the set; the most any paper cites is ${fmt(+mx.x)}.`; }
  if (id === 'cd-hist') return `most faculty (${fmt(hi.val)}) are ${hi.lab} steps away; the farthest person is ${P[P.length - 1].lab} steps away.`;
  if (id === 'pl-chart') return `highest: ${hi.lab.split(' · ')[0]} (${hi.val >= 0 ? '+' : ''}${fmt(hi.val)} above the institute average); lowest: ${lo.lab.split(' · ')[0]} (${fmt(lo.val)}).`;
  if (!isBar) { const nmx = labelOf(hi.t, hi.i); return `${fmt(P.length)} dots; the highest is ${fmt(hi.val)}${nmx ? ` (${nmx})` : ` at x = ${fmt(+hi.x)}`}.`; }
  return S.length === 1 && P.length >= 3 ? `highest: ${hi.lab} (${fmt(hi.val)}${u}); lowest: ${lo.lab} (${fmt(lo.val)}${u}).` : `highest: ${hi.lab}${nm(hi)} with ${fmt(hi.val)}${u}.`;
}

function put(host, html) {
  let cap = host.nextElementSibling && host.nextElementSibling.classList.contains('cap') ? host.nextElementSibling : null;
  if (!cap) { cap = document.createElement('div'); cap.className = 'cap'; host.after(cap); }
  cap.innerHTML = html;
}
function caption(gd) {
  const c = CAP[gd.id]; if (!c) return;
  let ins = ''; try { ins = insight(gd.id, gd); } catch (e) { ins = ''; }
  put(gd, `<b>X axis:</b> ${esc(c.x)}. <b>Y axis:</b> ${esc(c.y)}.${ins ? `<span class="ci">${esc(ins)}</span>` : ''}`);
}
const NET = {
  'cn-wrap': ['Each circle is a paper, sized by the measure chosen above; an arrow points from the citing paper to the cited one.', '#cn-stats'],
  'fn-wrap': ['Each circle is a faculty member, sized by the chosen measure and coloured by research community; a line means at least one joint paper.', '#fn-stats'],
  'in-wrap': ['The three large circles are the institutes; every other circle is a partner institute pulled towards the institutes it publishes with.', '#in-stats']
};
function netCaption(id) {
  const w = $('#' + id), c = NET[id]; if (!w) return;
  const st = $(c[1]), tx = st ? clean(st.innerHTML.replace(/<br\s*\/?>/g, ' · ')).replace(/\s*·?\s*Louvain.*$/, '') : '';
  put(w, `<b>How to read it:</b> ${esc(c[0])}${tx ? `<span class="ci">${esc(tx)}</span>` : ''}`);
}
function refresh(tab) {
  document.querySelectorAll(`#tab-${tab} .js-plotly-plot`).forEach(gd => {
    caption(gd);
    if (!gd._capOn && gd.on) { gd._capOn = true; gd.on('plotly_afterplot', () => caption(gd)); }
  });
  Object.keys(NET).forEach(id => { if ($(`#tab-${tab} #${id}`)) netCaption(id); });
}
for (const tab of Object.keys(A.RENDER)) {
  const base = A.RENDER[tab];
  A.RENDER[tab] = () => { base(); try { refresh(tab); setTimeout(() => refresh(tab), 700); } catch (e) { console.error('captions', tab, e); } };
  document.getElementById('tab-' + tab)?.addEventListener('change', () => setTimeout(() => refresh(tab), 450));
  document.getElementById('tab-' + tab)?.addEventListener('input', () => setTimeout(() => refresh(tab), 700));
}
try { A.rendered.delete(A.state.tab); A.go(A.state.tab); } catch (e) { console.error(e); }
})();
