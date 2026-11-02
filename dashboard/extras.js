/* Research Atlas: added analyses (key findings, institute comparison, citation sources, resilience, potential collaborations,
   data quality). Everything here is drawn from DATA keys produced by the pipeline; no number is typed in. Needs app.js. */
(() => {
const A = window.atlas, D = window.DATA, I = D.insts, SH = A.SHORT, P = D.papers, T = A.T;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = A.fmt, fmt1 = A.fmt1, fmt2 = A.fmt2, css = A.css;
const num = v => v === '' || v == null ? null : +v;
const instOf = n => I.indexOf(n);
const card = (title, sub, body, cls = '') => `<div class="card ${cls}"><div class="card-h"><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ''}</div></div>${body}</div>`;
const table = (heads, rows) => `<div class="tbl-wrap"><table><thead><tr>${heads.map((h, i) => `<th class="${i ? 'r' : ''}">${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((c, i) => `<td class="${i ? 'r num' : ''}">${c ?? '—'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const chart = (id, h = 320) => `<div class="chart" id="${id}" style="height:${h}px"></div>`;
const style = document.createElement('style');
style.textContent = `.kf{margin:0 0 18px}.kf .kf-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:12px}.kf .kf-h h2{margin:0}.kf .kf-n{font:500 11.5px var(--mono,monospace);color:var(--brandInk,#7a3fd0);letter-spacing:.04em}
.kf .kf-live{font-size:12.5px;opacity:.8;margin:0 0 12px}.kf .kf-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.kf .kf-i{position:relative;padding:12px 14px 12px 16px;border-radius:10px;background:var(--surface2,rgba(128,128,128,.10));cursor:pointer}.kf .kf-i::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:3px;background:var(--brand1,#7a3fd0)}
.kf .kf-i.hyp::before{background:var(--c3,#e0a030)}.kf .kf-t{font-weight:600;font-size:13.5px;margin-bottom:4px}.kf .kf-t small{font-weight:500;font-size:10.5px;margin-left:6px;padding:1px 6px;border-radius:8px;background:var(--c3,#e0a030);color:#fff;vertical-align:1px}
.kf .kf-x{font-size:13px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.kf .kf-x b{color:var(--brandInk,#7a3fd0);font-weight:650}.kf .kf-i.open .kf-x{display:block;-webkit-line-clamp:unset}
.kf .kf-c{display:none;font-size:12px;opacity:.75;margin-top:6px}.kf .kf-i.open .kf-c{display:block}.kf .dim{opacity:.4}.kf .kf-more{margin-top:12px;font-size:12.5px;background:none;border:0;color:var(--brandInk,#7a3fd0);cursor:pointer;padding:0}
.istrip{display:flex;align-items:center;gap:22px;margin:30px 0 0;padding:16px 0 0;border-top:1px solid var(--rule,rgba(128,128,128,.25))}.istrip[hidden]{display:none}.istrip .is-img{width:132px;height:88px;object-fit:cover;border-radius:10px;flex:none;box-shadow:0 1px 0 var(--rule,rgba(128,128,128,.25))}.istrip .is-body{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 28px;flex:1;min-width:0}.istrip .is-name{font:500 15px var(--serif,inherit);display:flex;align-items:center;gap:8px}.istrip .is-name small{font:400 12px var(--mono,monospace);color:var(--muted);letter-spacing:.02em}.istrip .is-i{font-size:13px;color:var(--ink2)}.istrip .is-i b{color:var(--ink);font-weight:600}.istrip .is-i small{color:var(--muted);font-size:11.5px}.istrip .is-facts{flex-basis:100%;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 24px}.istrip .is-img{cursor:zoom-in;transition:transform .15s ease}.istrip .is-img:hover{transform:scale(1.03)}.lbx{position:fixed;inset:0;z-index:5000;background:rgba(6,6,10,.86);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:24px;cursor:zoom-out}.lbx[hidden]{display:none}.lbx img{max-width:min(92vw,1100px);max-height:80vh;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.5);object-fit:contain}.lbx .lbx-cap{color:#d9d8d4;font-size:13px;text-align:center}.lbx .lbx-cap small{display:block;color:#9a9893;font-size:11.5px;margin-top:3px}.lbx .lbx-x{position:absolute;top:18px;right:22px;color:#fff;font-size:26px;line-height:1;background:none;border:0;cursor:pointer;opacity:.8}.istrip .is-src{font:500 10.5px var(--mono,monospace);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);align-self:baseline}@media(max-width:640px){.istrip{flex-direction:column;align-items:flex-start}}.why{margin:0 0 6px;padding-left:18px}.why li{margin:6px 0;font-size:13.5px;line-height:1.5}.why b{color:var(--brandInk,#7a3fd0)}.note-warn{border-left:3px solid var(--c3,#e0a030);padding:6px 12px;margin:8px 0;font-size:13px}`;
document.head.append(style);

// ---------------------------------------------------------------- key findings (static, from the pipeline) + a live line that follows the filters
const KF_TAB = { overview: 'overview', pubs: 'publications', faculty: 'faculty', papers: 'papers', citnet: 'citations', collab: 'coauthorship', reach: 'reach', flows: 'flows', resil: 'resilience', potential: 'collaborations' };
function liveLine(tab) {
  const ins = A.instsShown(), ps = P.filter(x => ins.some(i => x[T.mask] & (1 << i)) && A.inYears(x));
  if (!ps.length) return '';
  const jq = ps.filter(x => x[T.type] === 0 && /^Q[1-4]$/.test(x[T.q])), cites = ps.reduce((a, x) => a + x[T.cites], 0), q1 = jq.filter(x => x[T.q] === 'Q1').length;
  const who = A.state.inst < 0 ? 'All three institutes' : I[A.state.inst];
  return `<p class="kf-live"><b>${who}, ${A.yrLabel()}:</b> ${fmt(ps.length)} papers · ${fmt(cites)} citations (${fmt1(cites / ps.length)} per paper)${jq.length ? ` · Q1 share ${fmt1(100 * q1 / jq.length)}%` : ''}. The findings below cover all years${A.state.inst < 0 ? '' : `; those mentioning ${SH[A.state.inst]} come first`}.</p>`;
}
const KF_SHOW = 6;
const emph = t => esc(t).replace(/(?<![A-Za-z\d.])(\+?\d[\d,]*\.?\d*%?)(?![A-Za-z\d])/g, '<b>$1</b>');
const NO_FINDINGS = new Set(['citnet']);      // tabs that show no Key findings box
function renderFindings(tab) {
  const sec = $('#tab-' + tab); if (!sec || !D.findings || NO_FINDINGS.has(tab)) return;
  const list = D.findings.filter(f => f.tab === KF_TAB[tab]);
  if (!list.length) return;
  let host = sec.querySelector('.kf');
  if (!host) { host = document.createElement('div'); host.className = 'kf card'; const ph = sec.querySelector('.page-head, .hero'); ph ? ph.after(host) : sec.prepend(host); }
  const sel = A.state.inst >= 0 ? SH[A.state.inst] : null, rel = f => sel && f.text.includes(sel) ? 0 : 1;
  const sorted = [...list].sort((a, b) => rel(a) - rel(b)), open = host.dataset.all === '1';
  host.innerHTML = `<div class="kf-h"><h2>What stands out?</h2><span class="kf-n">${list.length} FROM THE DATA</span></div>` + liveLine(tab) +
    `<div class="kf-grid">` + sorted.map((f, k) => `<div class="kf-i ${f.kind === 'possible explanation' ? 'hyp' : ''} ${sel && !f.text.includes(sel) ? 'dim' : ''}" ${!open && k >= KF_SHOW ? 'hidden' : ''}>` +
      `<div class="kf-t">${esc(f.title)}${f.kind === 'possible explanation' ? '<small>hypothesis</small>' : ''}</div><div class="kf-x">${emph(f.text)}</div>${f.caveat ? `<div class="kf-c">Caveat: ${esc(f.caveat)}</div>` : ''}</div>`).join('') + `</div>` +
    (list.length > KF_SHOW ? `<button class="kf-more">${open ? 'Show fewer' : `Show all ${list.length}`}</button>` : '');
  host.querySelectorAll('.kf-i').forEach(el => el.onclick = () => el.classList.toggle('open'));
  const more = host.querySelector('.kf-more'); if (more) more.onclick = () => { host.dataset.all = open ? '0' : '1'; renderFindings(tab); };
}

// ---------------------------------------------------------------- extra sections placed inside existing tabs
function addSection(tab, id, html, where = 'end') { const sec = $('#tab-' + tab); if (!sec || $('#' + id)) return; const d = document.createElement('div'); d.id = id; d.className = 'mt'; d.innerHTML = html; const foot = sec.querySelector('.site-foot'); where === 'end' ? sec.append(d) : sec.prepend(d); }

function overviewExtra() {
  const C = D.insights.institute_comparison, H = D.insights.h_index_size_test;
  const row = (l, k, f = v => fmt1(+v)) => [l, ...I.map(n => { const r = C.find(c => c.institution === n); return r ? f(r[k]) : '—'; })];
  const rows = [row('Papers', 'papers', v => fmt(+v)), row('Research-active faculty', 'research_active_faculty', v => fmt(+v)), row('Papers per active faculty', 'papers_per_active_faculty'),
    row('Citations per paper (mean)', 'citations_per_paper'), row('Citations per paper (median)', 'median_citations_per_paper'), row('Field-weighted impact, median (1 = world)', 'fwci_median', v => fmt2(+v)),
    row('Top-10% most-cited share of papers (%)', 'top10pct_share_%'), row('Institute h-index (observed)', 'institute_h_index', v => fmt(+v)),
    row('Institute h-index at equal size*', 'institute_h_index', (v) => ''), row('Journal Q1 share (%)', 'journal_Q1_share_%'), row('Journal ranking coverage (%)', 'ranking_coverage_%'),
    row('Growth 2016–20 → 2021–25 (%)', 'growth_2016_2020_to_2021_2025_%', v => fmt(+v)), row('Faculty citation Gini', 'citation_gini_faculty', v => fmt2(+v)), row('Review-like papers (% of papers)', 'review_share_of_papers_%')];
  rows[8] = ['Institute h-index at equal size*', ...I.map(n => H.institutes[n] ? fmt1(H.institutes[n].mean_h_at_equal_size) : '—')];
  addSection('overview', 'ov-compare', card('How do the institutes compare like for like?', 'Raw totals next to size-normalised measures. Equal-size h-index: ' + H.papers_per_sample.toLocaleString() + ' papers drawn at random from each institute, ' + H.draws + ' draws.',
    table(['Measure', ...SH], rows) + `<p class="explain">* ${esc(H.note || '')} All values use 2016–2026 papers by verified faculty (2026 is a partial year). Q1 share = Q1 journal papers ÷ journal papers with a quartile; conference ranks are reported separately.</p>`));
}

function openLightbox(src, title, credit) {
  let box = $('#lbx');
  if (!box) {
    box = document.createElement('div'); box.id = 'lbx'; box.className = 'lbx'; box.hidden = true;
    box.innerHTML = '<button class="lbx-x" aria-label="Close">×</button><img alt=""><div class="lbx-cap"></div>';
    box.onclick = () => { box.hidden = true; };
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !box.hidden) { box.hidden = true; e.stopPropagation(); } }, true);
    document.body.append(box);
  }
  box.querySelector('img').src = src; box.querySelector('img').alt = title;
  box.querySelector('.lbx-cap').innerHTML = `${esc(title)}${credit ? `<small>${esc(credit)}</small>` : ''}`;
  box.hidden = false;
}

// one-institute lens: a quiet line under the header with that institute's own numbers and its NIRF facts
function instStrip() {
  const hero = $('#tab-overview .hero'); if (!hero) return;
  let el = $('#instStrip');
  if (!el) { el = document.createElement('div'); el.id = 'instStrip'; el.className = 'istrip'; const act = hero.querySelector('.hero-actions'); act ? act.after(el) : hero.append(el); }
  const k = A.state.inst;
  if (k < 0) { el.hidden = true; return; }
  const n = I[k], f = (D.instFacts || {})[n] || {}, st = A.instStat ? A.instStat(k) : null;
  const people = D.fac.filter(x => x.i === k && x.p > 0), depts = new Set(people.filter(x => x.d !== 'Unknown department').map(x => x.d));
  const own = [[fmt(people.length), 'faculty'], [depts.size, 'departments'], ...(st ? [[fmt(st.papers), 'papers'], [st.h, 'h-index']] : [])];
  const facts = (f.facts || []).map(x => `<span class="is-i">${esc(x.label)} <b>${esc(x.value)}</b>${x.note ? ` <small>${esc(x.note)}</small>` : ''}</span>`).join('');
  el.hidden = false;
  el.innerHTML = (f.image ? `<img class="is-img" src="${f.image}" alt="${esc(n)} campus" title="Click to enlarge">` : '') + `<div class="is-body"><span class="is-name"><span class="dot" style="background:${A.instColor(k)}"></span>${esc(n)}${f.location ? ` <small>${esc(f.location)}</small>` : ''}</span>` +
    own.map(([v, l]) => `<span class="is-i"><b>${v}</b> ${l}</span>`).join('') + (facts ? `<div class="is-facts"><span class="is-src">NIRF 2025</span>${facts}</div>` : '') + `</div>`;
    own.map(([v, l]) => `<span class="is-i"><b>${v}</b> ${l}</span>`).join('') + (facts ? `<div class="is-facts"><span class="is-src">NIRF 2025</span>${facts}</div>` : '');
  const im = el.querySelector('.is-img'); if (im) im.onclick = () => openLightbox(f.imageFull || f.image, n + (f.location ? ' · ' + f.location : ''), (D.instFacts || {}).image_source ? D.instFacts.image_source[n] : '');
}

function whyExtra() {
  const OD = D.insights.output_drivers; if (!OD) return;
  const val = v => v == null ? '—' : fmt1(+v).replace(/\.0$/, '');
  const rows = OD.measures.filter(m => ['active_faculty', 'papers_per_faculty', 'median_papers_per_faculty', 'top10pct_faculty_share_of_faculty_paper_credits_%', 'fractional_papers_per_faculty', 'avg_authors_per_paper', 'conference_share_%', 'share_Professor_%', 'papers_per_Professor', 'papers_per_Assistant professor'].includes(m.key))
    .map(m => [`<b>${esc(m.label)}</b>${m.note ? `<br><small>${esc(m.note)}</small>` : ''}`, ...I.map(n => val(m.values[n]))]);
  const dep = OD.common_departments.map(c => [esc(c.department), ...I.map(n => `<b>${val(c.values[n].papers_per_faculty)}</b> <small>(${c.values[n].faculty} faculty)</small>`)]);
  const leadL = I.map(n => `${SH[instOf(n)]} ${OD.common_department_leaders[n]}`).join(' · ');
  addSection('overview', 'ov-why', card('Why do the institutes differ in output?', 'Measured from the data',
    `<ul class="why">${OD.verdicts.map(v => `<li>${emph(v)}</li>`).join('')}</ul>` +
    `<div class="grid g2 mt">` + card('What measures sit behind this?', 'All institutes side by side', table(['Measure', ...SH], rows)) +
    card('How do matching departments compare across institutes?', `Papers per research-active faculty (departments with at least 5 faculty at each). Highest in: ${leadL}.`, table(['Department', ...SH], dep)) + `</div>`));
}

function papersExtra() {
  const Tm = D.insights.team_size;
  const tm = Tm.filter(r => r.institution === 'all').map(r => [r.team_size, fmt(+r.papers), fmt1(+r.mean_citations), fmt1(+r.median_citations), fmt1(+r['journal_Q1_share_%']) + '%', fmt1(+r['international_collaboration_%']) + '%']);
  addSection('papers', 'pp-extra', card('Do papers with many authors get more citations?', 'Papers with more than 10 authors versus the rest (all institutes)', table(['Team size', 'Papers', 'Mean cites', 'Median cites', 'Q1 share', 'Foreign author'], tm)));
}

function citnetExtra() {
  const CS = D.citSources, ob = CS.edges_by_kind;
  const names = ['overall', ...I], kinds = [['author_self', 'Author self-citation'], ['same_institute_other_author', 'Same institute, other authors'], ['between_our_institutes', 'Between the three institutes']];
  addSection('citnet', 'cn-extra', `<div class="grid g2">` + card('Who cites the institutes’ papers inside the set?', 'Citation links between the institutes’ papers, by kind. Row-wise percent.', chart('cn-src', 300)) +
    card('How many citations do papers give and receive inside the set?', 'Complementary distribution (share of papers with at least k links)', chart('cn-ccdf', 300)) + `</div>` +
    `<div class="note-warn">PageRank and in-degree here are <b>within-corpus</b> measures: they count only links between papers by the verified faculty of the three institutes. They are not worldwide citations (shown separately) and are dominated by author self-citations, so a paper with many worldwide citations can have low in-corpus PageRank. Older papers have had longer to collect links; use the per-year rank in the paper drawer.</div>`);
  const yrs = [...new Set(P.map(p => p[T.year]))].sort((a, b) => a - b);
  if (!$('#cn-yr-sel')) {
    const host = $('#cn-extra'); const c = document.createElement('div'); c.innerHTML = card('Which papers were most influential each year?', 'PageRank within the corpus, ranked among papers of the same publication year (a fair comparison: old papers have had longer to be cited).',
      `<label>Year <select id="cn-yr-sel">${yrs.map(y => `<option value="${y}" ${y === 2020 ? 'selected' : ''}>${y}${y === 2026 ? ' (partial)' : ''}</option>`).join('')}</select></label><div id="cn-yr-list" class="mt"></div>`, 'mt'); host.append(c);
    $('#cn-yr-sel').onchange = drawYearInfluence;
  }
  function drawYearInfluence() {
    const y = +$('#cn-yr-sel').value, ins = A.instsShown();
    const list = P.map((p, i) => [p, i]).filter(([p]) => p[T.year] === y && p[T.prYear] != null && ins.some(k => p[T.mask] & (1 << k))).sort((a, b) => a[0][T.prYear] - b[0][T.prYear]).slice(0, 10);
    $('#cn-yr-list').innerHTML = table(['Rank in year', 'Paper', 'Institutes', 'Worldwide citations', 'In-degree: papers that cite it', 'of which self'], list.map(([p, i]) =>
      [p[T.prYear], `<a href="#" data-p="${i}" class="yp">${esc(p[T.title])}</a>`, instNames(p[T.mask]), fmt(p[T.cites]), fmt(p[T.indeg]), fmt(p[T.inSelf])]));
    $('#cn-yr-list').querySelectorAll('.yp').forEach(a => a.onclick = e => { e.preventDefault(); A.openPaper(+a.dataset.p); });
  }
  const instNames = mask => [0, 1, 2].filter(k => mask & (1 << k)).map(k => SH[k]).join(', ');
  drawYearInfluence();
  // out-degree: references to papers of our corpus, and all references OpenAlex lists for the paper
  if (!$('#cn-outdeg')) {
    const c2 = document.createElement('div'); c2.className = 'grid g2 mt';
    c2.innerHTML = card('How many papers do the institutes’ papers cite inside the set?', 'Out-degree: how many papers in the set each paper cites (its references that are also in the set)', chart('cn-outdeg', 300)) +
      card('How many references does a paper have?', 'Every reference OpenAlex lists, inside or outside the corpus. The network only has the institutes’ papers as nodes, so only the first chart is a network measure.', chart('cn-nref', 300));
    $('#cn-extra').append(c2);
  }
  const hist = (vals) => { const m = new Map(); vals.forEach(v => m.set(v, (m.get(v) || 0) + 1)); return [...m].filter(([k]) => k > 0).sort((p, q) => p[0] - q[0]); };
  const ins = A.instsShown(), PS = P.filter(p => ins.some(k => p[T.mask] & (1 << k)) && A.inYears(p));
  const dot = (h, color, name) => ({ type: 'scatter', mode: 'markers', name, x: h.map(d => d[0]), y: h.map(d => d[1]), marker: { size: 8, color, line: { color: css('--surface'), width: 1.5 } }, hovertemplate: name + ' %{x}: %{y} papers<extra></extra>' });
  A.plot('cn-outdeg', [dot(hist(PS.map(p => p[T.outdeg])), css('--c2'), 'Cites')], { xaxis: { type: 'log', title: { text: 'Out-degree: number of papers in the set that this paper cites (log)' } }, yaxis: { type: 'log', title: { text: 'Number of papers (log)' } } });
  A.plot('cn-nref', [dot(hist(PS.map(p => p[T.nref] || 0)), css('--c4'), 'References')], { xaxis: { type: 'log', title: { text: 'References listed for the paper (log)' } }, yaxis: { type: 'log', title: { text: 'Number of papers (log)' } } });
  const noRef = PS.filter(p => !(p[T.nref] > 0)).length;
  let nrefNote = $('#cn-nref-note');
  if (!nrefNote) { nrefNote = document.createElement('p'); nrefNote.id = 'cn-nref-note'; nrefNote.className = 'explain'; $('#cn-nref').after(nrefNote); }
  nrefNote.textContent = `${fmt(noRef)} of ${fmt(PS.length)} papers (${fmt1(100 * noRef / Math.max(PS.length, 1))}%) have no reference list in OpenAlex, so their out-degree is 0 for that reason, not because they cite nothing.`;
  A.plot('cn-src', kinds.map(([k, l], j) => ({ type: 'bar', name: l, y: names.map(n => n === 'overall' ? 'All' : SH[instOf(n)]), orientation: 'h', x: names.map(n => { const o = ob[n], t = d3.sum(Object.values(o)); return 100 * o[k] / t; }),
    customdata: names.map(n => ob[n][k]), hovertemplate: l + ': %{customdata:,} links (%{x:.1f}%)<extra></extra>', marker: { color: css('--c' + (j + 1)) } })), { barmode: 'stack', xaxis: { title: { text: '% of links (target paper’s institute for rows)' }, range: [0, 100] }, yaxis: { autorange: 'reversed' } });
  const dd = D.citDegree.map(r => ({ k: +r.degree, ci: +r.ccdf_in, co: +r.ccdf_out })).filter(r => r.k > 0);
  A.plot('cn-ccdf', [{ type: 'scatter', mode: 'lines+markers', name: 'In-degree (cited by)', x: dd.map(r => r.k), y: dd.map(r => r.ci), line: { color: css('--c1') } },
    { type: 'scatter', mode: 'lines+markers', name: 'Out-degree (cites)', x: dd.map(r => r.k), y: dd.map(r => r.co), line: { color: css('--c2') } }],
    { xaxis: { type: 'log', title: { text: 'k links (log)' } }, yaxis: { type: 'log', title: { text: 'Share of papers with ≥ k links (log)' } } });
}

function collabExtra() {
  const F = D.fac, n = F.length, adj = F.map(() => []);
  D.fedges.forEach(([a, b, w, fy, ly]) => { adj[a].push([b, w]); adj[b].push([a, w]); });
  const sel = A.state.inst;
  // components
  const comp = new Array(n).fill(-1); let nc = 0; const csize = [];
  for (let s = 0; s < n; s++) if (comp[s] < 0 && adj[s].length) { const st = [s]; comp[s] = nc; let c = 0; while (st.length) { const u = st.pop(); c++; adj[u].forEach(([v]) => { if (comp[v] < 0) { comp[v] = nc; st.push(v); } }); } csize.push(c); nc++; }
  const isolated = adj.filter(l => !l.length).length, sizes = csize.slice().sort((a, b) => b - a);
  // partitions: normalised mutual information between two labelings
  const nmi = (la, lb) => { const N = la.length, ca = new Map(), cb = new Map(), cab = new Map(); la.forEach((a, i) => { const b = lb[i]; ca.set(a, (ca.get(a) || 0) + 1); cb.set(b, (cb.get(b) || 0) + 1); const k = a + '|' + b; cab.set(k, (cab.get(k) || 0) + 1); });
    const H = m => -d3.sum([...m.values()], v => v / N * Math.log(v / N)); let I = 0; cab.forEach((v, k) => { const [a, b] = k.split('|'); I += v / N * Math.log(v * N / ca.get(a) / cb.get(b)); });
    const ha = H(ca), hb = H(cb); return ha + hb ? 2 * I / (ha + hb) : 1; };
  const linked = F.map((f, i) => i).filter(i => adj[i].length);
  const nmiLD = nmi(linked.map(i => String(F[i].lv)), linked.map(i => String(F[i].ld)));
  const nmiLDept = nmi(linked.map(i => String(F[i].lv)), linked.map(i => F[i].d));
  const nLv = new Set(linked.map(i => F[i].lv)).size, nLd = new Set(linked.map(i => F[i].ld)).size;
  // participation coefficient P_i = 1 - sum_c (k_ic / k_i)^2 over communities (Louvain) and over departments; needs at least 3 links to mean anything
  const part = (i, lab) => { const k = adj[i].length, m = new Map(); adj[i].forEach(([j]) => m.set(lab(j), (m.get(lab(j)) || 0) + 1)); return 1 - d3.sum([...m.values()], v => (v / k) ** 2); };
  const pr = linked.filter(i => adj[i].length >= 3 && (sel < 0 || F[i].i === sel)).map(i => ({ i, k: adj[i].length, pc: part(i, j => F[j].lv), pd: part(i, j => F[j].d) })).sort((a, b) => b.pc - a.pc).slice(0, 12);
  // strongest pairs
  const pairs = D.fedges.filter(e => sel < 0 || F[e[0]].i === sel || F[e[1]].i === sel).slice().sort((a, b) => b[2] - a[2]).slice(0, 12);
  const cross = D.fedges.filter(e => F[e[0]].i !== F[e[1]].i && (sel < 0 || F[e[0]].i === sel || F[e[1]].i === sel)).slice().sort((a, b) => b[2] - a[2]).slice(0, 8);
  const pairRow = e => [`${esc(F[e[0]].n)} <small>${SH[F[e[0]].i]}</small>`, `${esc(F[e[1]].n)} <small>${SH[F[e[1]].i]}</small>`, e[2], e[3] ? `${e[3]}–${e[4]}` : '—'];
  const defs = [['Collaborators (degree)', 'Number of other verified faculty a person has co-authored a paper with.'], ['Joint papers (strength)', 'Papers written together; the weight of a link.'],
    ['Betweenness', 'How often a person lies on the shortest path between two other faculty. High = a bridge between groups.'], ['Eigenvector', 'Being linked to well-connected people counts more than being linked to many.'],
    ['Clustering', 'Share of a person’s collaborators who also collaborate with each other.'], ['k-core', 'The largest k for which the person is still in a group where everyone has at least k links inside it.'],
    ['Participation coefficient', '0 = all collaborators in one community (or department); close to 1 = collaborators spread evenly across many.']];
  addSection('collab', 'cl-extra', `<div class="grid g2">` + card('What do the measures mean?', 'Plain-language definitions of the numbers used in this tab', table(['Measure', 'Meaning'], defs.map(d => [`<b>${d[0]}</b>`, d[1]]).map(r => r.map((c, i) => i ? `<span style="font-weight:400">${c}</span>` : c)))) +
    card('How is the network split into groups?', 'The network is built from verified faculty only; a link means at least one joint paper.', table(['Measure', 'Value'], [['Faculty with at least one link', fmt(linked.length)], ['Faculty with no link to another verified faculty member', fmt(isolated)], ['Connected components (2 or more people)', fmt(nc)],
      ['Largest component', fmt(sizes[0]) + ' (' + fmt1(100 * sizes[0] / linked.length) + '% of linked faculty)'], ['Next largest components', sizes.slice(1, 6).join(', ')], ['Louvain communities', fmt(nLv)], ['Leiden communities', fmt(nLd)],
      ['Louvain vs Leiden agreement (NMI, 1 = identical)', fmt2(nmiLD)], ['Louvain communities vs departments (NMI)', fmt2(nmiLDept)]]) +
      `<p class="explain">Louvain and Leiden are two algorithms that split a network into groups that are densely connected inside and sparsely connected to the rest (they maximise modularity). Leiden is a refinement that guarantees well-connected groups. Both are heuristics: a different random start can change small groups, so treat the borders as approximate. A NMI close to 1 means both found nearly the same groups.</p>`) + `</div>` +
    `<div class="grid g2 mt">` + card('Which pairs collaborate most?', 'Most joint papers between two verified faculty', table(['Faculty A', 'Faculty B', 'Joint papers', 'Years'], pairs.map(pairRow))) +
    card('Which pairs across institutes collaborate most?', 'Collaborations between different institutes', table(['Faculty A', 'Faculty B', 'Joint papers', 'Years'], cross.map(pairRow))) + `</div>` +
    card('Who connects different communities?', 'Participation coefficient of faculty with at least 3 collaborators. High values mean collaborators spread over many communities (research groups) or many departments; compare with betweenness above.',
      table(['Faculty', 'Institute', 'Collaborators', 'Across communities', 'Across departments'], pr.map(r => [`${esc(F[r.i].n)}`, SH[F[r.i].i], r.k, fmt2(r.pc), fmt2(r.pd)])), 'mt'));
}

// ---------------------------------------------------------------- faculty who moved between our institutes
function moversExtra() {
  const M = D.movers || [];
  if (!M.length) return;
  const moved = M.filter(m => !m.bothCurrent), both = M.filter(m => m.bothCurrent);
  const names = [...I.map(n => SH[instOf(n)] + ' (before)'), ...moved.map(m => m.n), ...I.map(n => SH[instOf(n)] + ' (now)')];
  const k = I.length, src = [], tgt = [], val = [], col = [], tip = [];
  const cl = (list, w) => list.length ? list.map(c => `${c[0]} (${SH[c[1]]}, ${c[2]})`).join('; ') : 'none';
  moved.forEach((m, j) => {
    const mid = k + j;
    [[m.from, mid, 'before'], [mid, k + moved.length + m.to, 'now']].forEach(([a, b, w]) => {
      src.push(a); tgt.push(b); val.push(1); col.push(A.instColor(w === 'before' ? m.from : m.to) + '88');
      tip.push(`<b>${esc(m.n)}</b><br>${SH[m.from]} → ${SH[m.to]}${m.seen[0] ? ` (listed at ${SH[m.from]} ${m.seen[0]}–${m.seen[1]})` : ''}<br>${fmt(m.p)} papers · ${fmt(m.c)} citations (2016–2026)`);
    });
  });
  const html = card('Who has moved between the three institutes?', 'Each person is listed at two of the three institutes with the same OpenAlex author ID: once as former faculty (left) and once as current faculty (right). Every flow is one person. Hover for details.',
      chart('mv-sankey', 90 + 60 * moved.length)) +
    `<div class="mt">` + card('Who moved, and when?', 'Papers, citations and h-index are 2016–2026 totals for the person, so they are the same at both institutes.',
      table(['Person', 'From → to', 'Years listed at old institute', 'Papers', 'Citations', 'h-index'],
        moved.map(m => [`<b>${esc(m.n)}</b><br><small>${esc(m.d || '')}</small>`, `${SH[m.from]} → ${SH[m.to]}`, m.seen[0] ? (m.seen[0] === m.seen[1] ? m.seen[0] : `${m.seen[0]}–${m.seen[1]}`) : '—', fmt(m.p), fmt(m.c), m.h]))) + `</div>`;
  addSection('collab', 'mv-extra', html);
  if (!$('#mv-sankey') || !window.Plotly) return;
  A.plot('mv-sankey', [{ type: 'sankey', arrangement: 'snap', node: { label: names, pad: 14, thickness: 14, line: { width: 0 },
      color: names.map((_, i) => i < k ? A.instColor(i) : i >= k + moved.length ? A.instColor(i - k - moved.length) : css('--ink2')) },
    link: { source: src, target: tgt, value: val, color: col, customdata: tip, hovertemplate: '%{customdata}<extra></extra>' } }], { margin: { l: 10, r: 10, t: 10, b: 10 } });
}

function pubsExtra() {
  const CR = D.confRank, inc = CR.in_final_corpus;
  const vm = new Map(); D.insights.venue_explorer.forEach(r => { const o = vm.get(r.venue) || { venue: r.venue, papers: 0, citations: 0, type: r.type }; o.papers += +r.papers; o.citations += +(r.citations || 0); vm.set(r.venue, o); });
  const vx = [...vm.values()].sort((a, b) => b.papers - a.papers).slice(0, 25);
  addSection('pubs', 'pb-extra', `<div class="grid g2">` + card('How were conferences identified and ranked?', 'Conference papers resolved through Crossref event names',
    table(['Measure', 'Papers'], [['Conference papers', fmt(inc.conference_papers)], ['Named conference identified', fmt(inc.named_conference)], ['Only a publisher series (Lecture Notes, AIP, …)', fmt(inc.generic_series)], ...Object.entries(inc.core_ranked).map(([k, v]) => ['CORE ' + k, fmt(v)])]) +
    `<p class="explain">CORE ranks only computer-science conferences, so A*/A absence reflects the field mix as well as quality.</p>`) +
    card('Can I explore venues in detail?', 'Most-used venues, all three institutes combined. “Lecture notes” and similar are publisher series that hold many different conferences.', table(['Venue', 'Papers', 'Citations', 'Kind'], vx.map(r => [esc(r.venue), fmt(r.papers), fmt(r.citations), esc(r.type || '')]))) + `</div>`);
}

function facultyExtra() {
  const CC = D.insights.citation_concentration, CV = D.insights.connectivity_vs_impact;
  const rows = I.map(n => { const c = CC[n]; return [SH[instOf(n)], fmt2(c.gini_full), fmt2(c.gini_fractional), ...c.faculty_top1_5_10_share_full.map(v => fmt1(v) + '%'), esc(c.top_faculty[0].name) + ' (' + c.top_faculty[0]['share_%'] + '%)']; });
  addSection('faculty', 'fc-extra', card('How concentrated are citations in a few papers?', 'Gini coefficient (0 = equal, 1 = one researcher holds everything) and share held by the top 1%, 5% and 10% of faculty. Full counting credits a shared paper to every faculty author; fractional splits it.',
    table(['Institute', 'Gini (full)', 'Gini (fractional)', 'Top 1%', 'Top 5%', 'Top 10%', 'Largest single share'], rows)) +
    `<p class="explain">Performance versus connectivity: Spearman ρ between faculty collaborators and mean field-weighted impact is ${fmt2(CV.spearman_degree_vs_mean_fwci[0])} (n=${CV.n}); controlling for number of papers ${fmt2(CV.partial_degree_vs_mean_fwci_controlling_papers[0])}. h-index shown for each faculty member counts only their 2016–2026 papers in this corpus, not their career h-index.</p>`);
}

// ---------------------------------------------------------------- new pages: Resilience and Potential collaborations
function addPage(key, label, num, html) {
  const nav = $('#nav'); const b = document.createElement('button'); b.dataset.tab = key; b.innerHTML = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/></svg><span class="t">${label}</span><span class="k">${num}</span>`; nav.append(b);
  b.onclick = () => A.go(key);
  const s = document.createElement('section'); s.className = 'tab'; s.id = 'tab-' + key; s.innerHTML = html; const foot = $('.site-foot'); foot.parentNode.insertBefore(s, foot);
}
const SCOPES = ['all', ...I];
const sname = k => k === 'all' ? 'All three institutes' : k;

function renderResil() {
  const R = D.resilience, sc = A.state.inst < 0 ? 'all' : I[A.state.inst], S = R.scopes[sc], sm = S.summary;
  const rows = ['random', 'degree', 'betweenness', 'betweenness_adaptive', 'degree_null', 'betweenness_null'].map(k => [{ random: 'Random (mean of runs)', degree: 'Highest degree first', betweenness: 'Highest betweenness first (static)', betweenness_adaptive: 'Highest betweenness first (recomputed)', degree_null: 'Degree attack on rewired null networks', betweenness_null: 'Betweenness attack on rewired null networks' }[k],
    fmt2(sm[k].R20), sm[k].collapse_at == null ? '—' : fmt(100 * sm[k].collapse_at) + '%', sm[k].fragility_index != null ? fmt2(sm[k].fragility_index) : '—']);
  $('#rs-body').innerHTML = `<div class="grid g2">` + card('How fast does the network fall apart as faculty leave?', `${sname(sc)}: ${S.nodes} faculty, ${S.edges} links, ${S.isolated} isolated. Shaded band: 95% interval of ${R.runs || 50} random runs.`, chart('rs-curve', 340)) +
    card('What is the short summary?', 'R20 = mean largest-component share over 0–20% removed (higher = more robust). Collapse = fraction removed when the largest component falls below half its starting size.', table(['Strategy', 'R20', 'Collapse at', 'Fragility index'], rows)) + `</div>` +
    card('Whose removal would hurt the network most?', 'Effect of removing one faculty member from the network', table(['Faculty', 'Institute', 'Betweenness', 'Cut-vertex', 'LCC change (pp)', 'Efficiency loss'],
      D.criticalFaculty.filter(r => r.scope === (sc === 'all' ? 'all' : sc)).slice(0, 12).map(r => [esc(r.faculty_name), SH[instOf(r.institution)], fmt(+r.betweenness), r.articulation_point === 'True' ? 'yes' : 'no', fmt2(+r.lcc_change_pp), fmt2(+r['efficiency_loss_%']) + '%'])), 'mt') +
    `<div class="note-warn">${esc(R.definitions.note)} Interpret the curves as structural dependence on a few bridging researchers, not as a prediction. “Random” removes faculty uniformly; “targeted” removes the highest-ranked first. Comparison with degree-preserving rewiring shows whether the observed wiring is more or less fragile than its degree sequence alone implies.</div>`;
  const X = R.fractions.map(f => 100 * f), cur = S.curves, col = { random: '--c1', degree: '--c2', betweenness: '--c3', betweenness_adaptive: '--c4' };
  const tr = [];
  if (cur.random.lcc_lo) tr.push({ x: [...X, ...X.slice().reverse()], y: [...cur.random.lcc_hi, ...cur.random.lcc_lo.slice().reverse()], fill: 'toself', fillcolor: 'rgba(120,120,120,.2)', line: { width: 0 }, hoverinfo: 'skip', showlegend: false });
  Object.keys(col).forEach(k => tr.push({ type: 'scatter', mode: 'lines', name: { random: 'Random', degree: 'By degree', betweenness: 'By betweenness', betweenness_adaptive: 'By betweenness (recomputed)' }[k], x: X, y: cur[k].lcc, line: { color: css(col[k]) } }));
  if (S.null_model?.betweenness) tr.push({ type: 'scatter', mode: 'lines', name: 'Betweenness, null model', x: X, y: S.null_model.betweenness.lcc, line: { color: css('--c3'), dash: 'dot' } });
  A.plot('rs-curve', tr, { xaxis: { title: { text: '% of faculty removed' } }, yaxis: { title: { text: 'Largest component (share of faculty)' }, range: [0, 1] } });
}

function renderPotential() {
  const L = D.linkPred, nw = L.tasks.new, rp = L.tasks.repeat, sel = A.state.inst;
  const M = (t, m) => t.metrics[m];
  const mrows = (t) => Object.entries(t.metrics).map(([k, v]) => [k, (+v.average_precision).toFixed(3), fmt2(v.roc_auc), fmt1(100 * v['precision@100']) + '%', fmt1(100 * v['recall@500']) + '%']);
  const cands = D.candidates.filter(r => sel < 0 || r.institute_a === I[sel] || r.institute_b === I[sel]).slice(0, 40);
  $('#pc-body').innerHTML = `<div class="note-warn"><b>Three different things.</b> “Existing” is a recorded joint paper. “Compatibility” is topic overlap, shared collaborators and structure today. “Predicted” is a model ranking of pairs that did not collaborate before but might. New-link scores are <b>rankings, not probabilities</b>: the calibration check failed (slope ${fmt2(nw.calibration['logistic regression'].slope)}). They are a way to prioritise conversations, not evidence that a collaboration will happen.</div>` +
    `<div class="grid g2">` + card('Which pairs could start collaborating?', `Trained on features at ${nw.train.T || 2019}, tested on ${nw.test.T || 2022} features and 2023–2025 outcomes. Base rate ${(M(nw, 'logistic regression').base_rate * 100).toFixed(2)}%.`, table(['Model', 'Avg precision', 'ROC-AUC', 'Precision@100', 'Recall@500'], mrows(nw))) +
    card('Which pairs are likely to work together again?', 'A separate task; the probabilities pass the calibration check for the random forest.', table(['Model', 'Avg precision', 'ROC-AUC', 'Precision@100', 'Recall@500'], mrows(rp))) + `</div>` +
    card('Who could collaborate next?', 'Highest-ranked pairs with no joint paper so far, from 2025 features. Rank score is a ranking, not a probability.', table(['#', 'Faculty A', 'Faculty B', 'Hops', 'Common collaborators', 'Topic similarity', 'Shared subfields'], cands.map(r => [r.rank, `${esc(r.faculty_a)} <small>${SH[instOf(r.institute_a)]}</small>`, `${esc(r.faculty_b)} <small>${SH[instOf(r.institute_b)]}</small>`, r.hops === '' ? 'not connected' : r.hops, esc(r.common_collaborators || '—'), fmt2(+r.topic_cosine), esc((r.shared_subfields || '').split(';').slice(0, 2).join(';'))])), 'mt') +
    `<p class="explain">Ask the AI Research Assistant page for pair-level explanations (“Can X collaborate with Y?”).</p>`;
}

// ---------------------------------------------------------------- Method: data quality
function methodExtra() {
  const du = D.dupAudit, cr = D.confRank, unk = F_unknown();
  addSection('method', 'md-quality', card('How reliable is the data and what do terms mean?', 'Counts are computed from the final tables.', table(['Check', 'Value'], [
    ['Papers in corpus (verified faculty, 2016–2026)', fmt(P.length)], ['Papers without a DOI (kept; analysed by OpenAlex work ID)', fmt(P.filter(p => !p[T.doi]).length)],
    ['Duplicate records merged into one paper', fmt(D.dupMerged)], ['Faculty with department “Unknown department”', fmt(unk)], ['Papers with a field-weighted impact value', fmt(P.filter(p => p[T.fwci] != null).length)],
    ['Conference papers with an identified conference', fmt(cr.in_final_corpus.named_conference) + ' of ' + fmt(cr.in_final_corpus.conference_papers)]])) +
    `<div class="note-warn">Definitions. <b>Q1 share</b> = Q1 journal papers ÷ journal papers with a quartile; conferences use CORE ranks separately. <b>Within-corpus PageRank/in-degree</b> use only links between papers in this corpus. <b>Not calculated ≠ zero</b>: topic similarity is blank when a paper has no topic assignment. <b>2026</b> is a partial year in every time series. <b>Career h-index</b> is not computed; faculty h-index counts only 2016–2026 papers here.</div>`);
}
function F_unknown() { return D.fac.filter(f => f.d === 'Unknown department').length; }

// ---------------------------------------------------------------- wiring
if ($('#facCount')) $('#facCount').textContent = fmt(D.fac.length);
const wrap = { collab: () => { collabExtra(); moversExtra(); }, overview: () => { overviewExtra(); whyExtra(); instStrip(); }, pubs: pubsExtra, faculty: facultyExtra, papers: papersExtra, citnet: citnetExtra, method: methodExtra };
const original = { ...A.RENDER };
Object.keys(wrap).forEach(tab => { const base = A.RENDER[tab]; A.RENDER[tab] = () => { base(); try { wrap[tab](); } catch (e) { console.error('extras', tab, e); } renderFindings(tab); }; });
['reach', 'flows'].forEach(tab => { const base = A.RENDER[tab]; A.RENDER[tab] = () => { base(); renderFindings(tab); }; });
addPage('resil', 'Resilience', 10, `<div class="page-head"><div class="eyebrow">10 — Network resilience</div><h1>How <em>fragile</em> is collaboration?</h1><p class="lede">Remove faculty at random or by importance and watch the network fall apart.</p></div><div id="rs-body"></div>`);
addPage('potential', 'Potential', 11, `<div class="page-head"><div class="eyebrow">11 — Link prediction</div><h1>Who might <em>collaborate</em> next?</h1><p class="lede">Temporal prediction of faculty collaborations from past structure and topics, with no future information in the features.</p></div><div id="pc-body"></div>`);
A.RENDER.resil = () => { renderResil(); renderFindings('resil'); };
A.RENDER.potential = () => { renderPotential(); renderFindings('potential'); };
// the first page was rendered before this file loaded
try { const h = (window.__startHash || '').split('?')[0]; A.rendered.delete(A.state.tab); A.go(A.RENDER[h] ? h : A.state.tab); } catch (e) { document.body.dataset.err = String(e.stack).slice(0, 500); console.error(e); }
document.addEventListener('atlas:inst', () => { A.rendered.delete('resil'); A.rendered.delete('potential'); if (['resil', 'potential'].includes(A.state.tab)) A.go(A.state.tab); else renderFindings(A.state.tab); });
})();
