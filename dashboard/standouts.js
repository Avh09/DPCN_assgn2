/* Research Atlas: "Worth noticing" cards and plain-word glossaries, one per tab.
   Every number is computed from DATA when the page loads (all three institutes, 2016-2026), so nothing here is typed in by hand.
   Each fact has a "Check it out" button that scrolls to the chart or table that shows it. Needs app.js, extras.js and more.js. */
(() => {
const A = window.atlas, D = window.DATA, I = D.insts, SH = A.SHORT, P = D.papers, F = D.fac, T = A.T;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fmt = A.fmt, fmt1 = A.fmt1, fmt2 = A.fmt2;
const NV = (D.insights || {}).new_views || {};
const C = D.insights.institute_comparison, num = v => +v;
const cmpRow = n => C.find(c => c.institution === n);
const pct = (a, b) => b ? 100 * a / b : 0;
const argmax = v => v.indexOf(Math.max(...v)), argmin = v => v.indexOf(Math.min(...v));
const b = s => `<b>${s}</b>`;
const the = n => esc(/^United /.test(n) ? 'the ' + n : n);
const inst = i => I[i];
const mask = i => P.filter(x => x[T.mask] & (1 << i));

const style = document.createElement('style');
style.textContent = `.so{margin-top:18px}.so-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:4px}.so-h h2{margin:0}.so-n{font:500 11px var(--mono,monospace);letter-spacing:.06em;text-transform:uppercase;color:var(--brandInk,#7c3aed)}
.so-sub{font-size:12.5px;color:var(--muted);margin:0 0 12px}.so-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px}
.so-i{border:1px solid var(--rule,rgba(128,128,128,.25));border-radius:14px;padding:14px 16px;display:flex;flex-direction:column;gap:8px;background:var(--surface,transparent)}
.so-t{font-weight:650;font-size:14px;line-height:1.3}.so-x{font-size:13.5px;line-height:1.5}.so-bars{display:grid;gap:5px;margin-top:2px}
.so-b{display:grid;grid-template-columns:50px 1fr auto;gap:8px;align-items:center;font-size:12px;color:var(--muted)}.so-b i{display:block;height:8px;border-radius:4px;min-width:3px}
.so-b span.v{font-variant-numeric:tabular-nums;color:var(--ink)}.so-go{align-self:flex-start;margin-top:auto;background:none;border:1px solid var(--rule,rgba(128,128,128,.35));color:var(--brandInk,#7c3aed);border-radius:999px;padding:5px 12px;font:inherit;font-size:12.5px;cursor:pointer}
.so-go:hover{background:var(--brandInk,#7c3aed);color:#fff}.so-gl{margin-top:14px;border-top:1px solid var(--rule,rgba(128,128,128,.25));padding-top:10px}.so-gl summary{cursor:pointer;font-weight:600;font-size:13.5px}
.so-gl table{margin-top:8px}.so-gl td{vertical-align:top;font-size:13px;padding:7px 10px}.so-gl td:first-child{white-space:nowrap;font-weight:600}
@keyframes soflash{0%{box-shadow:0 0 0 3px var(--brand1,#8b5cf6)}100%{box-shadow:0 0 0 3px transparent}}.so-flash{animation:soflash 1.8s ease-out 1}`;
document.head.append(style);

// find the card whose heading is `text`
const card = text => { const h = [...document.querySelectorAll('h2')].find(e => e.textContent.trim() === text); return h ? (h.closest('.card') || h.parentElement) : null; };
const jump = (target, tab) => {
  const go = () => { const sb = { '#fn-wrap': '#fnStar', '#in-wrap': '#inStar', '#cn-wrap': '#cnStar' }[target]; if (sb && $(sb) && !$(sb).checked) { $(sb).checked = true; $(sb).dispatchEvent(new Event('input')); } const el = typeof target === 'string' ? (card(target) || (/^[#.]/.test(target) ? $(target) : null)) : target; if (!el) return; el.scrollIntoView({ behavior: 'smooth', block: 'start' }); el.classList.remove('so-flash'); void el.offsetWidth; el.classList.add('so-flash'); };
  if (tab && A.state.tab !== tab) { A.go(tab); setTimeout(go, 400); } else go();
};

// fact = { t: title, x: html text, bars: [[value x3], fmt, 'unit'], look: [heading or selector, label, tab?] }
const bars = (vals, f) => { const mx = Math.max(...vals.map(Math.abs), 1e-9); return `<div class="so-bars">${vals.map((v, i) => `<div class="so-b"><span>${SH[i]}</span><i style="width:${Math.max(2, 100 * Math.abs(v) / mx)}%;background:${A.instColor(i)}"></i><span class="v">${f(v)}</span></div>`).join('')}</div>`; };
const render = (facts, gloss) => `<div class="so-h"><h2>What is worth noticing here?</h2><span class="so-n">${facts.length} unusual facts</span></div>
  <p class="so-sub">Computed from the data for the three institutes, all years 2016–2026. Use “Check it out” to jump to where each one is shown.</p>
  <div class="so-grid">${facts.map((f, k) => `<div class="so-i"><div class="so-t">${f.t}</div><div class="so-x">${f.x}</div>${f.bars ? bars(f.bars[0], f.bars[1]) : ''}${f.look ? `<button class="so-go" data-k="${k}">Check it out: ${esc(f.look[1])} →</button>` : ''}</div>`).join('')}</div>
  ${gloss.length ? `<details class="so-gl"><summary>Terms on this page in plain words</summary><div class="tbl-wrap"><table><thead><tr><th>Term</th><th>What it means</th><th>Why it helps</th></tr></thead><tbody>${gloss.map(g => `<tr><td>${g[0]}</td><td>${g[1]}</td><td>${g[2]}</td></tr>`).join('')}</tbody></table></div></details>` : ''}`;

// ------------------------------------------------------------------ the facts, per tab
const G = {
  hindex: ['h-index', 'A person has h-index 20 if 20 of their papers have at least 20 citations each. Here it counts only 2016–2026 papers.', 'One number that rewards both volume and impact, so one hugely cited paper does not dominate.'],
  fwci: ['FWCI (field-weighted citation impact)', 'Citations divided by what a paper of the same subject, year and type normally gets. 1.0 = world average, 2.0 = twice the average.', 'Lets a maths paper and a medicine paper be compared fairly, which raw citation counts cannot do.'],
  q1: ['Q1 / Q2 / Q3 / Q4', 'Journals are ranked within their subject and split into four equal groups. Q1 is the top quarter.', 'A quick quality check on where papers are published.'],
  sae: ['Single-author equivalent', 'Each paper counts as 1 shared among its authors, so a 4-author paper is worth a quarter to each.', 'Shows how much work a person did alone against how much came from big teams.'],
  gini: ['Gini / concentration', '0 means everyone has the same number of citations, 1 means one person has them all.', 'Shows whether the success is spread across many faculty or a few stars.'],
  spear: ['Spearman correlation', 'How closely two rankings agree, from −1 to +1. Around 0 means no link.', 'Tells whether, say, more collaborators goes with higher impact.'],
  deg: ['Collaborators (degree)', 'The number of other faculty someone has written a paper with.', 'The simplest measure of how well connected a person is.'],
  btw: ['Betweenness', 'How often a person sits on the shortest path between two other faculty.', 'Finds the brokers who link different groups. Losing them splits the network.'],
  eig: ['Eigenvector score', 'Being linked to well-connected people counts more than being linked to many people.', 'Finds people close to the influential core, not just popular ones.'],
  pr: ['PageRank', 'A paper is important if important papers cite it. Computed only inside these institutes’ papers, not worldwide.', 'Finds papers that the group builds on, but it favours older papers.'],
  indeg: ['In-degree / out-degree', 'In-degree is how many papers in the set cite this paper. Out-degree is how many papers in the set it cites.', 'Shows which papers are built on and which build on others.'],
  comm: ['Community (Louvain / Leiden)', 'A group of faculty who write together much more than with others, found automatically from the links.', 'Shows the real research groups, which can differ from official departments.'],
  mod: ['Modularity', 'How cleanly the network splits into groups: near 0 = no groups, near 1 = very clear groups.', 'Tells how separate the research groups are.'],
  jac: ['Jaccard / weighted Jaccard', 'Topic overlap between two institutes: shared subjects divided by all subjects. Weighted counts how much work is in each subject.', 'Shows whether institutes work on similar topics.'],
  lcc: ['Largest connected component', 'The biggest group of faculty who can all reach each other through co-authors.', 'Shows how much of the network holds together.'],
  eff: ['Efficiency', 'How short, on average, the co-author routes between faculty are.', 'Drops when key people are removed, showing how much they shorten connections.'],
  artic: ['Articulation point', 'A person whose removal alone breaks the network into more pieces.', 'Finds the single people the network most depends on.'],
  ratio: ['Impact ratio (in ÷ out)', 'Citations the institute receives from other Indian institutes divided by citations it gives them.', 'Below 1 means the institute cites others more than others cite it.'],
  velocity: ['Citation velocity', 'Citations per paper per year after publication.', 'Compares how fast older and newer papers earn citations.'],
  link: ['Link prediction', 'A model that learns, from the past, which pairs of faculty end up writing together, then scores pairs that have not yet.', 'Suggests who might collaborate next. A score ranks pairs; it is not a promise.'],
  cos: ['Topic similarity', 'How alike two faculty’s research subjects are, from 0 to 1.', 'Similar topics make a joint paper more likely.'],
  scimago: ['SCImago SJR / CiteScore / CORE', 'Public rankings of journals (SJR), conference and journal series (CiteScore) and computer-science conferences (CORE).', 'Where the Q1–Q4 and A*/A labels in this dashboard come from.'],
  partner: ['Partner institute', 'Any outside institute with at least one paper written together with one of the three.', 'Shows who the institutes work with beyond their own campus.'],
  impact: ['Impact factor (IF)', 'The average number of citations a journal’s articles receive in a recent period (the Clarivate figure). The “IF > 5 / > 10” filters here use SCImago citations per document as a stand-in, not the Clarivate value.', 'A rough guide to how widely read and cited a journal is.'],
  unranked: ['Estimated and unranked quartiles', 'Where a journal has no official quartile, it is estimated from its OpenAlex statistics (about 58% exactly right, 96% within one quartile), or from the publisher’s other journals. Venues OpenAlex does not know stay unranked.', 'Every paper gets a label where possible. Unranked papers are left out of the Q1 share, so they never count as Q1 or as not-Q1.'],
  openalex: ['OpenAlex', 'A free, open index of papers, authors, institutes and citations.', 'The source of every paper in this dashboard.']
};

// number of cut vertices (people whose removal alone splits a group) in the verified-faculty network
function countCuts() {
  const n = F.length, adj = F.map(() => []); D.fedges.forEach(([a, b]) => { if (F[a].n !== F[b].n) { adj[a].push(b); adj[b].push(a); } });
  const disc = new Int32Array(n).fill(-1), low = new Int32Array(n), par = new Int32Array(n).fill(-1), ptr = new Int32Array(n), cut = new Uint8Array(n); let t = 0;
  for (let s = 0; s < n; s++) {
    if (disc[s] >= 0) continue; let rc = 0; disc[s] = low[s] = t++; const st = [s];
    while (st.length) {
      const u = st[st.length - 1];
      if (ptr[u] < adj[u].length) { const v = adj[u][ptr[u]++]; if (disc[v] < 0) { par[v] = u; disc[v] = low[v] = t++; st.push(v); if (u === s) rc++; } else if (v !== par[u]) low[u] = Math.min(low[u], disc[v]); }
      else { st.pop(); const p = par[u]; if (p >= 0) { low[p] = Math.min(low[p], low[u]); if (p !== s && low[u] >= disc[p]) cut[p] = 1; } }
    }
    if (rc > 1) cut[s] = 1;
  }
  return cut.reduce((a, c) => a + c, 0);
}
function facts() {
  const S = D.summary.map(s => Object.fromEntries(Object.entries(s).map(([k, v]) => [k, isNaN(+v) ? v : +v])));
  const cr = I.map(cmpRow), ppf = cr.map(r => num(r.papers_per_active_faculty)), act = cr.map(r => num(r.research_active_faculty));
  const LEAD = (name, vals, f = fmt1) => `${SH[argmax(vals)]} ${f(Math.max(...vals))}`;
  const out = {};

  // ---- Overview
  const fwm = cr.map(r => num(r.fwci_median)), cpp = cr.map(r => num(r.citations_per_paper)), q1 = cr.map(r => num(r['journal_Q1_share_%'])), hix = cr.map(r => num(r.institute_h_index)), gr = cr.map(r => num(r['growth_2016_2020_to_2021_2025_%']));
  out.overview = [
    { t: `${SH[argmax(ppf)]} publishes the most per person, with fewer faculty`, x: `${b(I[argmax(ppf)])} has ${b(act[argmax(ppf)])} research-active faculty against ${b(Math.max(...act))} at ${SH[argmax(act)]}, yet ${b(fmt1(Math.max(...ppf)))} papers per person against ${b(fmt1(Math.min(...ppf)))} at ${SH[argmin(ppf)]}. The gap is about output per person, not headcount.`,
      bars: [ppf, fmt1], look: ['How do the institutes compare like for like?', 'comparison table'] },
    { t: 'The leader changes with the measure', x: `Most papers: ${b(SH[argmax(cr.map(r => num(r.papers)))])} · most citations per paper: ${b(SH[argmax(cpp)])} (${fmt1(Math.max(...cpp))}) · best median FWCI: ${b(SH[argmax(fwm)])} (${fmt2(Math.max(...fwm))}) · highest Q1 share: ${b(SH[argmax(q1)])} (${fmt1(Math.max(...q1))}%) · highest h-index: ${b(SH[argmax(hix)])} (${Math.max(...hix)}). No institute wins everything.`,
      bars: [fwm, fmt2], look: ['How do the institutes compare like for like?', 'comparison table'] },
    { t: `${SH[argmax(gr)]} grew fastest`, x: `Papers per year rose ${b(fmt(Math.max(...gr)) + '%')} between 2016–20 and 2021–25 at ${b(I[argmax(gr)])}; the slowest growth was ${b(fmt(Math.min(...gr)) + '%')} at ${SH[argmin(gr)]}.`, bars: [gr, v => fmt(v) + '%'], look: ['How many papers does each institute publish each year?', 'yearly output chart', 'pubs'] }
  ];

  // ---- Publications
  const conf = I.map((_, i) => pct(S[i].conference_papers, S[i].papers)), q1s = S.map(s => s['journal_Q1_%']);
  const topJ = I.map((_, i) => { const m = new Map(); mask(i).forEach(x => { if (x[T.type] === 0 && x[T.venue]) m.set(x[T.venue], (m.get(x[T.venue]) || 0) + 1); }); return [...m].sort((a, c) => c[1] - a[1])[0]; });
  const rv = P.filter(x => x[T.review]), rvC = d3.sum(rv, x => x[T.cites]), allC = d3.sum(P, x => x[T.cites]);
  out.pubs = [
    { t: `${SH[argmax(q1s)]} has the highest share of top-quartile journal papers`, x: `${b(fmt1(Math.max(...q1s)) + '%')} of ${I[argmax(q1s)]} journal papers are in Q1 journals, against ${b(fmt1(Math.min(...q1s)) + '%')} at ${SH[argmin(q1s)]}.`, bars: [q1s, v => fmt1(v) + '%'], look: ['Is the Q1 share rising over the years?', 'Q1 share by year'] },
    { t: `${SH[argmax(conf)]} relies most on conference papers`, x: `${b(fmt1(Math.max(...conf)) + '%')} of ${SH[argmax(conf)]} output is conference papers, against ${b(fmt1(Math.min(...conf)) + '%')} at ${SH[argmin(conf)]}. Conference papers are harder to rank for quality.`, bars: [conf, v => fmt1(v) + '%'], look: ['How good are the conferences the institutes publish in?', 'conference ranks'] },
    { t: 'The favourite journal differs by institute', x: I.map((n, i) => `${b(SH[i])}: ${esc(topJ[i][0])} (${topJ[i][1]} papers)`).join('<br>'), look: ['Which journals do the institutes publish in most?', 'journal lists'] },
    { t: 'Review articles are few but heavily cited', x: `Review-type papers are ${b(fmt1(pct(rv.length, P.length)) + '%')} of all papers but ${b(fmt1(pct(rvC, allC)) + '%')} of all citations.`, look: ['Can I explore venues in detail?', 'venue explorer'] }
  ];

  // ---- Faculty
  const top10 = cr.map(r => num(r['top10_faculty_share_of_citations_%'])), fh = [...F.keys()].sort((a, c) => F[c].h - F[a].h)[0];
  const loner = [...F.keys()].filter(i => F[i].deg === 0).sort((a, c) => F[c].p - F[a].p)[0], hub = [...F.keys()].sort((a, c) => F[c].deg - F[a].deg)[0];
  const CV = D.insights.connectivity_vs_impact;
  out.faculty = [
    { t: 'A handful of faculty hold a third of the citations', x: `The top 10 faculty at each institute hold ${b(fmt1(Math.min(...top10)) + '–' + fmt1(Math.max(...top10)) + '%')} of its faculty citations. ${I[argmax(top10)]} is the most concentrated.`, bars: [top10, v => fmt1(v) + '%'], look: ['Who are the top 10 faculty?', 'top 10 leaderboard'] },
    { t: `Highest h-index: ${esc(F[fh].n)}`, x: `${b(esc(F[fh].n))} (${SH[F[fh].i]}, ${esc(F[fh].d)}) has h-index ${b(F[fh].h)} from ${b(F[fh].p)} papers and ${b(fmt(F[fh].c))} citations. The most-connected faculty member is ${b(esc(F[hub].n))} (${SH[F[hub].i]}) with ${b(F[hub].deg)} co-authors from the three institutes.`, look: ['How does each faculty member perform?', 'faculty table'] },
    { t: 'Productive, yet no co-author among the three institutes', x: `${b(esc(F[loner].n))} (${SH[F[loner].i]}) has ${b(F[loner].p)} papers but has not written with any other verified faculty member. Many prolific people work with outside partners only.`, look: ['How does each faculty member perform?', 'faculty table'] },
    { t: 'More collaborators do not by themselves mean more impact', x: `Collaborators and average impact (FWCI) are linked (ρ = ${b(fmt2(CV.spearman_degree_vs_mean_fwci[0]))}), but once the number of papers is taken into account the link nearly vanishes (${b(fmt2(CV.partial_degree_vs_mean_fwci_controlling_papers[0]))}). Productive people simply have more co-authors.`, look: ['How do two faculty compare?', 'compare two faculty'] }
  ];

  // ---- Papers
  const mc = P.reduce((m, x) => (x[T.cites] > m[T.cites] ? x : m)), unc = I.map((_, i) => pct(mask(i).filter(x => x[T.cites] === 0).length, mask(i).length));
  const big = P.reduce((m, x) => (x[T.nauth] > m[T.nauth] ? x : m));
  out.papers = [
    { t: 'The most-cited paper', x: `${b(esc(mc[T.title]))} (${mc[T.year]}) has ${b(fmt(mc[T.cites]))} citations. Nothing else comes close, so a few papers carry a large share of all citations.`, look: ['Which 10 papers are cited most?', 'top 10 papers'] },
    { t: `${SH[argmax(unc)]} has the most papers with no citation yet`, x: `${b(fmt1(Math.max(...unc)) + '%')} of ${SH[argmax(unc)]} papers are uncited, against ${b(fmt1(Math.min(...unc)) + '%')} at ${SH[argmin(unc)]}. Recent papers have had little time to be cited.`, bars: [unc, v => fmt1(v) + '%'], look: ['Can I search and filter every paper?', 'paper explorer'] },
    { t: 'A paper with a very large author list', x: `${b(fmt(big[T.nauth]))} authors wrote ${b(esc(big[T.title]))}. Papers with more than 10 authors are rare and too few to move any institute’s totals.`, look: ['How does every paper look at a glance?', 'every paper as a dot'] }
  ];

  // ---- Citations
  const ek = D.citSources.edges_by_kind.overall, tot = ek.author_self + ek.same_institute_other_author + ek.between_our_institutes, mac = D.citMacro['whole corpus'];
  const mw = P.reduce((m, x) => (x[T.cites] > m[T.cites] ? x : m)), pk = P.reduce((m, x) => (x[T.indeg] > m[T.indeg] ? x : m)), pp = P.reduce((m, x) => (x[T.pr] > m[T.pr] ? x : m));
  const sc = I.map(n => pct(D.citSources.edges_by_kind[n].author_self, d3.sum(Object.values(D.citSources.edges_by_kind[n]))));
  out.citnet = [
    { t: 'Most citations inside the set are authors citing themselves', x: `${b(fmt1(pct(ek.author_self, tot)) + '%')} of the ${b(fmt(tot))} citation links between the institutes’ papers share an author. Only ${b(fmt1(pct(ek.between_our_institutes, tot)) + '%')} go from one institute to another.`, bars: [sc, v => fmt1(v) + '%'], look: ['Who cites the institutes’ papers inside the set?', 'who cites whom'] },
    { t: 'The paper the others build on most', x: `${b(esc(pk[T.title]))} (${pk[T.year]}) is cited by ${b(pk[T.indeg])} other papers in the set but has ${b(fmt(pk[T.cites]))} citations worldwide. The paper with the highest PageRank is ${b(esc(pp[T.title]))} (${pp[T.year]}), and the most cited worldwide is ${b(esc(mw[T.title]))} (${b(fmt(mw[T.cites]))} citations). All three are ringed on the network when they are in view.`, look: ['#cn-wrap', 'ringed in the network'] },
    { t: 'Citations almost never go both ways', x: `Across all ${b(fmt(mac.citation_links))} citation links, only ${b(fmt2(mac.reciprocity * 100) + '%')} run both ways (reciprocity ${mac.reciprocity}): when paper A cites paper B, B almost never cites A. ${b(fmt1(mac['papers_never_cited_in_corpus_%']) + '%')} of papers are never cited by another paper in the set.`, look: ['How many papers are cited often by the institutes’ own papers?', 'in-degree chart'] },
    { t: 'The three institutes barely cite each other', x: `Row by row, at most ${b(fmt1(Math.max(...I.map(a => I.reduce((s, c) => (a === c ? s : s + D.citNet.flow_matrix_row_pct[a][c]), 0)))) + '%')} of any institute’s in-set citations go to another of the three institutes.`, look: ['How often do the three institutes cite each other?', 'citation heatmap'] }
  ];

  // ---- Collaboration
  const bt = D.loc.between, fp = bt.faculty_pairs[0], wn = D.facNet.whole_network, br = [...F.keys()].sort((a, c) => F[c].btw - F[a].btw)[0], hubC = [...F.keys()].sort((a, c) => F[c].deg - F[a].deg)[0];
  const jp = Object.entries(bt.joint_papers).sort((a, c) => c[1] - a[1]);
  out.collab = [
    { t: `Only ${bt.faculty_links} of ${fmt(wn.edges)} faculty links cross institutes`, x: `Almost all co-authorship stays inside one institute. The strongest cross-institute pair is ${b(esc(fp.a))} (${SH[I.indexOf(fp.inst_a)]}) and ${b(esc(fp.b))} (${SH[I.indexOf(fp.inst_b)]}) with ${b(fp.joint_papers)} joint papers.`, look: ['#fn-wrap', 'orange links and the pair ringed in the network'] },
    { t: 'Joint papers between the institutes are very uneven', x: jp.map(([k, v]) => `${k.split(' & ').map(n => SH[I.indexOf(n)]).join(' & ')}: ${b(v)}`).join(' · ') + `. The two eastern institutes are the closest pair; MANIT is the outlier.`, look: ['How are the institutes and their partners linked?', 'institute network', 'reach'] },
    { t: `${esc(F[hubC].n)} has the most co-authors`, x: `${b(esc(F[hubC].n))} (${SH[F[hubC].i]}, ${esc(F[hubC].d)}) has written with ${b(F[hubC].deg)} other verified faculty, more than anyone else; ${b(F[hubC].xi)} of them are at another institute and ${b(F[hubC].xd)} are in another department. Marked with a ring on the network.`, look: ['#fn-wrap', 'ringed in the network'] },
    { t: `The biggest broker is ${esc(F[br].n)}`, x: `${b(esc(F[br].n))} (${SH[F[br].i]}) has the highest betweenness: the most shortest co-author routes pass through this person. Ringed on the network. ${b(wn.isolated_faculty)} faculty have no link to another verified faculty member at all.`, look: ['#fn-wrap', 'ringed in the network'] }
  ];

  // ---- Reach
  const rch = D.loc.reach, fshare = rch.map(r => r['with_foreign_inst_%']), own = rch.map(r => r['own_institute_only_%']), fr = NV.fwci_places && NV.fwci_places.all, cn = (NV.countries || {}).all || [];
  const us = fr && fr.rows.find(r => r.place === 'United States'), dl = fr && fr.rows.find(r => r.place === 'India: Delhi'), mal = fr && fr.rows.find(r => r.place === 'Malaysia'), ff = D.loc.foreign[0];
  const IN = D.loc.instNodes || [], tp = IN.slice().sort((p, q) => num(q.papers_with_us) - num(p.papers_with_us))[0], all3 = IN.filter(n => (n.linked_to || '').split(';').length === 3).sort((p, q) => num(q.papers_with_us) - num(p.papers_with_us));
  out.reach = [
    { t: `${SH[argmax(fshare)]} has the most papers with a foreign institute`, x: `${b(fmt1(Math.max(...fshare)) + '%')} of ${SH[argmax(fshare)]} papers have a co-author at a foreign institute, against ${b(fmt1(Math.min(...fshare)) + '%')} at ${SH[argmin(fshare)]}.`, bars: [fshare, v => fmt1(v) + '%'], look: ['Which foreign countries do the institutes write papers with?', 'foreign countries'] },
    { t: 'Most papers stay within one institute', x: `${b(fmt1(Math.min(...own)) + '–' + fmt1(Math.max(...own)) + '%')} of each institute’s papers have no co-author from any other institute. ${SH[argmax(own)]} is the most inward-looking.`, bars: [own, v => fmt1(v) + '%'], look: ['How local is collaboration?', 'how local is collaboration'] },
    ...(tp ? [{ t: `${esc(tp.institution)} is the top partner`, x: `${b(esc(tp.institution))} has ${b(tp.papers_with_us)} joint papers with the three institutes. ${b(all3.length)} partner institutes work with all three; the biggest are ${all3.slice(0, 3).map(n => esc(n.institution)).join(', ')}. The top partner and the three biggest shared partners are ringed on the institute network.`, look: ['#in-wrap', 'ringed in the network'] }] : []),
    ...(us && dl ? [{ t: 'Papers with US and Delhi co-authors are cited more', x: `Papers with a United States co-author average FWCI ${b(fmt2(us.mean))} and with a Delhi co-author ${b(fmt2(dl.mean))}, against ${b(fmt2(fr.baseline.mean))} for all papers.${mal ? ` Malaysia is higher still (${b(fmt2(mal.mean))}), driven by a few very highly cited joint papers.` : ''}`, look: ['Do co-authors from some places lift the institutes’ impact?', 'impact by partner place'] }] : []),
    ...(cn.length ? [{ t: `${the(cn[0].name).replace(/^the/, "The")} is the top foreign partner country`, x: `${b(cn[0].papers)} papers have a co-author based in ${the(cn[0].name)}, followed by ${the(cn[1].name)} (${cn[1].papers}). The single foreign institute with the most joint papers is ${b(esc(ff[1]))} (${ff[3]} papers with ${SH[ff[0]]}).`, look: ['Which foreign countries do the institutes write papers with?', 'foreign countries'] }] : [])
  ];

  // ---- Flows
  const GT = NV.give_take, pv = I.map(n => GT && GT[n].private_univ), pr = pv.map(p => p ? p.cites_us / p.we_cite : 0), io = S.map(s => s.in_over_out_ratio);
  let imb = null; if (GT) I.forEach(n => GT[n].rows.forEach(r => { if (r.cites_us >= 300 && r.we_cite >= 0) { const q = r.cites_us / Math.max(r.we_cite, 1); if (!imb || q > imb.q) imb = { q, ...r, n }; } }));
  out.flows = [
    ...(GT ? [{ t: 'Private universities cite the institutes more than they are cited back', x: `Private universities cite ${b(SH[argmax(pr)])} ${b(fmt2(Math.max(...pr)) + '×')} as often as ${SH[argmax(pr)]} cites them. This is a name-based grouping, so it is approximate.`, bars: [pr, v => fmt2(v) + '×'], look: ['Do private universities boost the institutes’ citations?', 'give-and-take card'] }] : []),
    ...(imb ? [{ t: 'One-sided citing', x: `${b(esc(imb.name))} cites ${b(SH[I.indexOf(imb.n)])} papers ${b(fmt(imb.cites_us))} times, but ${SH[I.indexOf(imb.n)]} cites it only ${b(fmt(imb.we_cite))} times.`, look: ['#fl-gt', 'who cites more than is cited'] }] : []),
    { t: 'The institutes cite other Indian institutes more than they are cited', x: `Citations received ÷ citations given: ${I.map((n, i) => `${b(SH[i])} ${b(fmt2(io[i]))}`).join(', ')}. A value below 1 means giving more than receiving.`, bars: [io, fmt2], look: ['Do the institutes receive more citations than the institutes give?', 'impact ratio by year'] }
  ];

  // ---- Method
  const dm = D.dupMerged;
  out.method = [
    { t: 'How many records survive the cleaning', x: `${b(fmt(D.funnel[0][1]))} records were downloaded, ${b(fmt(D.funnel[1][1]))} remain after removing errata, retractions and duplicates, and ${b(fmt(P.length))} papers belong to verified faculty of the three institutes.`, look: ['How was the paper set built?', 'corpus funnel'] },
    { t: 'People listed at two institutes are counted once', x: `${b(dm)} faculty records were merged because the same person appeared at two of the three institutes (for example after moving), so no one is double counted.`, look: ['Who has moved between the three institutes?', 'movers', 'collab'] },
    { t: 'Where the quality labels come from, and papers without one', x: D.qsrc.map(([k, v]) => `${esc(k)}: ${b(fmt(v))} papers`).join(' · ') + '. A missing quartile is estimated from the journal’s OpenAlex statistics (58% exactly right, 96% within one quartile). Only ' + b(fmt((D.qsrc.find(q => /No ranking/.test(q[0])) || [0, 0])[1])) + ' papers stay unranked, and they are left out of every Q1 share.', look: ['Where do the quartile labels come from?', 'quartile sources'] }
  ];

  // ---- Resilience
  const rs = D.resilience, fr10 = rs.fractions.indexOf(0.1), cv = rs.scopes.all.curves, crit = D.criticalFaculty.filter(r => r.scope === 'all'), cutCount = countCuts();
  out.resil = [
    ...(fr10 >= 0 ? [{ t: 'Losing the best-connected people hurts far more than random loss', x: `Removing 10% of faculty at random leaves ${b(fmt1(cv.random.lcc[fr10] * 100) + '%')} of faculty in the largest connected group; removing the 10% with most bridging routes leaves ${b(fmt1(cv.betweenness.lcc[fr10] * 100) + '%')} (from ${fmt1(rs.scopes.all.lcc_fraction_0 * 100)}% to start with).`, look: ['How fast does the network fall apart as faculty leave?', 'removal curves'] }] : []),
    { t: 'Many people are single points of failure', x: `${b(cutCount)} of the ${b(F.length)} faculty are cut vertices: removing any one of them alone would split a connected group in two or more. The single removal that shortens routes most is ${b(esc(crit.sort((a, c) => num(c['efficiency_loss_%']) - num(a['efficiency_loss_%']))[0].faculty_name))}. The simulator at the bottom of this tab lets you remove people and watch this happen.`, look: ['#sim-wrap', 'live removal simulator'] }
  ];

  // ---- Potential
  const cd = D.candidates, c0 = cd[0], x0 = cd.find(r => r.institute_a !== r.institute_b);
  out.potential = [
    { t: 'The model’s top suggestion', x: `${b(esc(c0.faculty_a))} (${SH[I.indexOf(c0.institute_a)]}) and ${b(esc(c0.faculty_b))} (${SH[I.indexOf(c0.institute_b)]}) are ranked first: they are ${b(c0.hops)} co-author steps apart, share ${b(Math.round(num(c0.common_neighbours)))} collaborator and have topic similarity ${b(fmt2(num(c0.topic_cosine)))}.`, look: ['Who could collaborate next?', 'candidate pairs'] },
    ...(x0 ? [{ t: 'The best suggestion across two institutes', x: `${b(esc(x0.faculty_a))} (${SH[I.indexOf(x0.institute_a)]}) and ${b(esc(x0.faculty_b))} (${SH[I.indexOf(x0.institute_b)]}), ranked ${b('#' + x0.rank)}. Cross-institute pairs are rare in the data, so these would be new bridges.`, look: ['Who could collaborate next?', 'candidate pairs'] }] : [])
  ];
  return out;
}

const GLOSS = {
  overview: [G.hindex, G.fwci, G.impact, G.q1, G.gini, ['Equal-size h-index', 'The h-index recomputed on the same number of papers for each institute, drawn at random many times.', 'Removes the advantage of simply having more papers.']],
  pubs: [G.impact, G.q1, G.unranked, G.fwci, G.sae, G.scimago, ['i10', 'Number of papers with at least 10 citations.', 'A simple count of solidly cited work.']],
  faculty: [G.hindex, G.gini, G.spear, G.deg, G.btw, G.sae, ['i10 / Cited % / Active years', 'i10 = papers with 10+ citations. Cited % = share of the person’s papers cited at least once. Active years = years between first and last paper.', 'Show depth and steadiness, not only totals.']],
  papers: [G.fwci, G.impact, G.pr, G.indeg, ['Review article', 'A paper that summarises many other papers instead of reporting new results.', 'Reviews are often cited more, so they can lift an average.']],
  citnet: [G.pr, G.indeg, G.impact, ['Self-citation', 'A paper citing an earlier paper that shares an author.', 'Shows how much citing inside the set is authors building on their own work.'], ['Density / reciprocity / clustering', 'Density: share of possible links that exist. Reciprocity: how often citing goes both ways. Clustering: how often two neighbours are linked to each other.', 'Describe how tightly the citation web is knit.']],
  collab: [G.deg, G.btw, G.eig, ['Closeness', 'How short the co-author routes are from someone to everyone else.', 'Finds people who can reach the whole network fastest.'], ['k-core', 'A group where everyone has at least k links inside the group.', 'Finds the dense inner core of the network.'], G.comm, G.mod, ['Clustering', 'How often a person’s collaborators also write with each other.', 'High = a tight team; low = a person linking separate people.']],
  reach: [G.partner, G.jac, ['Same state / region', 'Whether the partner is in the institute’s own state or region of India.', 'Shows how local collaboration is.'], G.fwci, G.spear],
  flows: [G.ratio, G.velocity, G.jac, ['Cluster', 'A group of similar institutes, such as IITs, NITs, private universities, government labs or industry.', 'Shows what kinds of organisation cite and are cited.']],
  method: [G.impact, G.openalex, G.scimago, G.q1, G.unranked, G.sae, ['Verified faculty', 'People whose identity and institute were checked by hand against the faculty lists.', 'Only their papers are counted, so every number refers to real faculty.']],
  resil: [G.lcc, G.eff, G.artic, G.btw, ['Random vs targeted removal', 'Removing people by chance, or removing the best-connected first.', 'Shows how much the network depends on a few people.'], ['Null model', 'A shuffled network with the same number of links per person but random wiring.', 'Checks whether the real structure is more fragile than chance would give.']],
  potential: [G.link, G.cos, ['Common neighbours / hops', 'Common neighbours: collaborators two people share. Hops: co-author steps between them.', 'Fewer hops and more shared collaborators make a joint paper likelier.'], ['Score vs probability', 'The score ranks pairs against each other; it is not the chance of a collaboration.', 'Use it to decide whom to talk to first, not as a forecast.']]
};

const done = new Set();
function mount(tab) {
  const sec = $('#tab-' + tab), list = (window.__so || (window.__so = facts()))[tab];
  if (!sec || !list || !list.length || done.has(tab)) return;
  const host = document.createElement('div'); host.className = 'card so'; host.id = 'so-' + tab; host.innerHTML = render(list, GLOSS[tab] || []);
  const anchor = sec.querySelector('.kf') || sec.querySelector('.page-head, .hero'); anchor ? anchor.after(host) : sec.prepend(host);
  host.querySelectorAll('.so-go').forEach(btn => btn.onclick = () => { const f = list[+btn.dataset.k]; jump(f.look[0], f.look[2]); });
  done.add(tab);
}
for (const tab of Object.keys(A.RENDER)) { const base = A.RENDER[tab]; A.RENDER[tab] = () => { base(); try { mount(tab); } catch (e) { console.error('standouts', tab, e); } }; }
try { A.rendered.delete(A.state.tab); A.go(A.state.tab); } catch (e) { console.error(e); }
})();
