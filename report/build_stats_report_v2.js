// Builds report/Group15_Statistics_Report.docx: the <= 5-page statistics report required by the instruction note.
//   python report/report_data.py && python report/report_figures.py && node report/build_stats_report.js
const fs = require('fs');
const path = require('path');
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, ImageRun, Footer, PageNumber } = require('docx');

const R = __dirname, ROOT = path.join(R, '..');
const D = JSON.parse(fs.readFileSync(path.join(R, 'report_data.json'), 'utf8'));
const OR = (v => [Math.round(Math.min(...v)), Math.round(Math.max(...v))])(D.loc.by_locality.filter(r => r.locality === 'Other region').map(r => r['share_of_links_%']));
const I = D.insts, SH = { 'MANIT Bhopal': 'MANIT', 'NIT Jamshedpur': 'NITJ', 'NIT Silchar': 'NITS' };
const S = Object.fromEntries(D.summary.map(r => [r.institution, r]));
const n = x => Number(x).toLocaleString('en-US');
const FIG = f => path.join(ROOT, 'data', 'out', 'figures', f), RFIG = f => path.join(R, 'figures', f);
const W = 11906 - 2 * 850, ACCENT = '1F4E79';
const short = t => t.length > 70 ? t.slice(0, 67) + '…' : t;
const abbr = s => s.replace('National Institute of Technology', 'NIT').replace('Indian Institute of Technology', 'IIT').replace('Indian Institute of Information Technology', 'IIIT');

function runs(text, base = {}) {
  return String(text).split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(p => p.startsWith('**') ? new TextRun({ text: p.slice(2, -2), bold: true, ...base }) : new TextRun({ text: p, ...base }));
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run || {}), spacing: { after: 60, line: 252 }, ...o.p });
const H = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
let tn = 0, fn = 0;
const cap = (k, t) => new Paragraph({ children: [new TextRun({ text: `${k} ${k === 'Table' ? ++tn : ++fn}. `, bold: true, size: 15, color: ACCENT }), new TextRun({ text: t, size: 15, color: '404040' })], spacing: { before: 40, after: 40 }, keepNext: k === 'Table' });
const b = { style: BorderStyle.SINGLE, size: 4, color: 'C8C8C8' }, borders = { top: b, bottom: b, left: b, right: b };
function table(c, heads, rows, fr, numCols = [], size = 14) {
  const tot = fr.reduce((a, x) => a + x, 0), cw = fr.map(f => Math.floor(f / tot * W)); cw[cw.length - 1] += W - cw.reduce((a, x) => a + x, 0);
  const cell = (t, j, head, z) => new TableCell({ width: { size: cw[j], type: WidthType.DXA }, borders, shading: { fill: head ? 'DCE6F2' : z ? 'F5F8FC' : 'FFFFFF', type: ShadingType.CLEAR, color: 'auto' },
    margins: { top: 20, bottom: 20, left: 60, right: 60 }, children: [new Paragraph({ alignment: numCols.includes(j) ? AlignmentType.RIGHT : AlignmentType.LEFT, children: runs(t ?? '', { size, bold: head }) })] });
  return [...(c ? [cap('Table', c)] : []), new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: cw,
    rows: [new TableRow({ tableHeader: true, children: heads.map((h, j) => cell(h, j, true)) }), ...rows.map((r, k) => new TableRow({ cantSplit: true, children: r.map((t, j) => cell(String(t), j, false, k % 2)) }))] }),
    new Paragraph({ spacing: { after: 40 }, children: [] })];
}
const pngSize = f => { const x = fs.readFileSync(f); return [x.readUInt32BE(16), x.readUInt32BE(20)]; };
const img = (f, w) => { const [pw, ph] = pngSize(f); return new ImageRun({ type: 'png', data: fs.readFileSync(f), transformation: { width: w, height: Math.round(w * ph / pw) }, altText: { title: path.basename(f), description: path.basename(f), name: path.basename(f) } }); };
const SCALE = Number(process.env.FIG_SCALE || .88);
// two figures side by side
function pair(f1, f2, c1, c2, ratio = .5, scale = SCALE) {
  const w1 = Math.round(590 * scale * ratio), w2 = Math.round(590 * scale) - w1, half = [Math.floor(W * ratio), W - Math.floor(W * ratio)];
  const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' }, nb = { top: none, bottom: none, left: none, right: none };
  const c = (f, w, t, k) => new TableCell({ width: { size: half[k], type: WidthType.DXA }, borders: nb, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [img(f, w - 8)] }), cap('Figure', t)] });
  return [new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: half, rows: [new TableRow({ cantSplit: true, children: [c(f1, w1, c1, 0), c(f2, w2, c2, 1)] })] })];
}

const DEPT = { 'Computer Science and Engineering': 'CSE', 'Mechanical Engineering': 'ME', 'Electrical Engineering': 'EE', 'Civil Engineering': 'CE', 'Electronics and Communication Engineering': 'ECE' };
const tidy = x => {
  const m = String(x).match(/^(.*?)(?: \(([^)]+)\))?$/);
  let name = m[1] === 'Sanja y' ? 'S. Sanjay' : m[1].replace(/\b[A-Z]{2,}\b/g, w => w.charAt(0) + w.slice(1).toLowerCase());
  return m[2] ? `${name} (${DEPT[m[2]] || m[2]})` : name;
};
const C = [];
const add = (...x) => x.flat().forEach(y => C.push(y));
const CN = D.cit_net, FN = D.fac_net, LC = D.loc;

add(new Paragraph({ children: [new TextRun({ text: 'Statistics Report · Group 15 · MANIT Bhopal, NIT Jamshedpur, NIT Silchar (2016–2026) | Dashboard: https://dpcngroup15asgn2.streamlit.app/', bold: true, size: 30, color: ACCENT })], spacing: { after: 40 } }),
  P(`**Data and method:** ${n(D.headline.papers)} journal and conference papers by ${n(D.headline.faculty_with_papers)} verified faculty (current and former; PhD scholars, staff and guests removed), OpenAlex, 2016–2026 (2026 partial). Quartiles: SCImago SJR, Scopus CiteScore, CORE 2023; **${D.headline.estimated_pct}% of rows have an estimated quartile** (flagged in the data). IF = SCImago citations per document, not the Clarivate impact factor. ${D.headline.multi_author_papers} papers have more than 10 authors; all our authors on them are verified faculty and none was flagged as guest or former (Table 10). Full detail is in the dashboard and the detailed report.`, { run: { size: 16, color: '404040' } }),
);

// 1 trend + Q1
add(H('1. Publication trend and Q1 fraction'),
  ...table('Institute summary', ['Metric', ...I.map(i => SH[i])], [
    ['Papers (journal / conference)', ...I.map(i => `${n(S[i].papers)} (${n(S[i].journal_papers)} / ${n(S[i].conference_papers)})`)],
    ['Growth 2016→2025 (CAGR)', ...I.map(i => D.cagr[i] + '%')],
    ['Citations · per paper · institute h-index', ...I.map(i => `${n(S[i].total_citations)} · ${S[i].citations_per_paper} · ${S[i].institute_h_index}`)],
    ['Journal Q1 / Q2 / Q3 / Q4 (%)', ...I.map(i => `**${S[i]['journal_Q1_%']}** / ${S[i]['journal_Q2_%']} / ${S[i]['journal_Q3_%']} / ${S[i]['journal_Q4_%']}`)],
    ['Q1 papers with IF > 5 / > 10', ...I.map(i => `${n(S[i].Q1_and_IF_gt5)} / ${S[i].Q1_and_IF_gt10}`)],
    ['Conference: CORE B / C · Scopus Q1–Q2 proceedings', ...I.map(i => { const c = D.conf[i]; return `${c.rank_counts.B || 0} / ${c.rank_counts.C || 0} · ${(c.scopus_quartile_counts.Q1 || 0) + (c.scopus_quartile_counts.Q2 || 0)}`; })]],
    [2.4, 1.5, 1.5, 1.5], [1, 2, 3]),
  ...table('Papers per year', ['Year', ...D.ppy.map(r => r.year === '2026' ? '2026*' : r.year)], [...I.map(i => [SH[i], ...D.ppy.map(r => n(r[i]))]), ['All (unique)', ...D.ppy.map(r => n(r['all (unique papers)']))]],
    [1.3, ...D.ppy.map(() => .75)], D.ppy.map((r, k) => k + 1)),
  ...pair(FIG('01_papers_per_year.png'), FIG('03_quartiles.png'), 'Papers per year (2026 partial, dotted).', 'Journal quartile mix and Q1 share by year.', .42),
  P(`Output roughly tripled from 2016 to 2025. NITS is the largest producer and has the highest Q1 share (${S['NIT Silchar']['journal_Q1_%']}%). MANIT and NITS raised Q1 share to above 40% in 2024–25; NITJ stayed at ${Math.floor(Math.min(...Object.values(D.quartiles['NIT Jamshedpur']['Q1_fraction_by_year_%']).slice(0, -1)))}–${Math.ceil(Math.max(...Object.values(D.quartiles['NIT Jamshedpur']['Q1_fraction_by_year_%'])))}%. Only ${D.headline.core_ranked_papers} conference papers have a CORE rank (B/C, none A/A*); most proceedings are Scopus Q3–Q4.`),
  ...pair(RFIG('R5_conference_rank.png'), RFIG('R6_top_journals.png'), 'Conference papers by venue rank (CORE, else Scopus quartile).', 'Top 5 journals per institute (colour = quartile).', .38, 1),
);

// 2 journals, cited papers, areas
add(H('2. Top journals, most-cited papers and research areas'),
  ...table('Top 5 journals per institution (papers, quartile)', I.map(i => SH[i]), [0, 1, 2, 3, 4].map(k => I.map(i => { const j = D.top_journals[i][k]; return `${j.journal_name} (${j.papers}, ${j.quartile})`; })), [1, 1, 1]),
  ...table('Top 10 most-cited papers (all three institutes)', ['#', 'Paper', 'Inst.', 'Journal, year', 'Cites', 'DOI'],
    I.flatMap(i => D.top10_cited[i].map(p => ({ ...p, i }))).sort((a, b) => b.citations - a.citations).slice(0, 10)
      .map((p, k) => [k + 1, short(p.title), SH[p.i], `${short(p.journal_name)}, ${p.year}`, n(p.citations), p.doi.replace('https://doi.org/', '')]), [.3, 3.6, .6, 2.2, .6, 1.9], [0, 4], 13),
  ...table('Research areas (% of papers, OpenAlex field)', ['Institute', 'Top 5 fields', 'Domain split'], I.map(i => [SH[i],
    Object.entries(D.areas[i]['fields_top8_%']).slice(0, 5).map(([k, v]) => `${k} ${v}%`).join(', '), Object.entries(D.areas[i]['domains_%']).map(([k, v]) => `${k.replace(' Sciences', '')} ${v}%`).join(', ')]), [.7, 3.6, 2.4]),
  ...table('Largest departments (papers, papers per faculty, median h, journal Q1 %)', I.map(i => SH[i]), [0, 1, 2, 3].map(k => I.map(i => { const d = D.dept[i][k]; return d ? `${d.department.replace(' Engineering', ' Eng.')}: ${n(d.papers)} · ${d.papers_per_faculty}/fac · h ${d.median_h_index} · ${d['q1_share_%']}%` : ''; })), [1, 1, 1], [], 13),
  ...pair(RFIG('R15_field_impact.png'), RFIG('R14_departments.png'), 'Research fields: size vs citations per paper.', 'Departments: papers per faculty vs Q1 share.', .5),
);

// 3 faculty
const hb = ['0', '1-4', '5-9', '10-14', '15-19', '20-29', '30+'];
add(H('3. Faculty: h-index distribution and leaderboards'),
  ...table('Faculty h-index distribution (number of faculty; 2016–26 papers)', ['h-index', ...hb, 'Median', 'h ≥ 20'], I.map(i => [SH[i], ...hb.map(x => (D.hdist.find(r => r.institution === i && r.h_index === x) || {}).faculty || 0), D.fac_results[i].h_index.median, D.fac_results[i].h_index.h_20_or_more]),
    [1, .7, .7, .7, .7, .7, .7, .7, .8, .8], [1, 2, 3, 4, 5, 6, 7, 8, 9]),
  ...table('Top-10 faculty per institution: h-index · papers · citations', ['#', ...I.map(i => SH[i])], [...Array(10).keys()].map(k => [k + 1, ...I.map(i => { const f = D.leaders[i][k]; return `${tidy(f.faculty_name)} — h ${f.h_index} · ${f.papers} · ${n(f.citations)}`; })]), [.3, 2, 2, 2], [0], 13),
  P('Note: Kumarasamy Sudhakar (MANIT, h 55) holds a permanent position at MANIT’s Energy Centre and is also Associate Professor at Universiti Malaysia Pahang; he was added after verification.', { run: { size: 14, color: '595959' } }),
  ...pair(RFIG('R1_faculty_h_index.png'), FIG('16_author_concentration.png'), 'Faculty h-index distribution (share of faculty).', 'Concentration of papers and citations across faculty.', .5),
  P(`Median faculty h-index is ${D.fac_results['NIT Silchar'].h_index.median} (NITS), ${D.fac_results['MANIT Bhopal'].h_index.median} (MANIT) and ${D.fac_results['NIT Jamshedpur'].h_index.median} (NITJ). Citations are concentrated: the top 10 faculty hold ${D.author_analysis['MANIT Bhopal']['top10_share_of_citations_%']}% (MANIT), ${D.author_analysis['NIT Jamshedpur']['top10_share_of_citations_%']}% (NITJ) and ${D.author_analysis['NIT Silchar']['top10_share_of_citations_%']}% (NITS) of citations.`),
);

// 4 top 30
const T = Object.fromEntries(D.top30_sum.map(r => [r.institution, r]));
add(H('4. Top-30 papers deep-dive'),
  ...table('Top 30 papers per institute by citations', ['Institute', 'Total cites', '#1 / median / #30', 'Q1 (share)', 'Q1 · IF>5', 'Q1 · IF>10', 'Median venue h', 'With faculty h≥20', 'Median best-author h'],
    I.map(i => [SH[i], n(T[i].citations_total), `${n(T[i].citations_max)} / ${n(Math.round(T[i].citations_median))} / ${n(T[i].citations_min)}`, `${T[i].Q1} (${T[i]['Q1_share_%']}%)`, T[i].Q1_and_IF_gt5, T[i].Q1_and_IF_gt10, Math.round(T[i].median_venue_h_index), T[i].papers_with_faculty_h_20_plus, Math.round(T[i].median_max_faculty_h)]),
    [.8, .9, 1.3, .9, .7, .7, .9, 1, 1], [1, 3, 4, 5, 6, 7, 8]),
  ...table('Papers with more than 10 authors vs the rest', ['Institute', 'Group', 'Papers', 'Share', 'Mean cites', 'Median cites', 'Journal Q1 %'],
    D.hyper.map(r => [SH[r.institution], r.group, n(r.papers), r['share_of_papers_%'] + '%', r.mean_citations, r.median_citations, r['journal_Q1_%']]), [.8, 1.8, .8, .7, .9, .9, .9], [2, 3, 4, 5, 6], 13),
  ...pair(FIG('13_top30_quality.png'), FIG('12_multi_author_10plus.png'), 'Venue quality of the top-30 papers (Q1 with IF > 10 / 5–10).', 'Papers with more than 10 authors: count, Q1 share, faculty h ≥ 20.', .45),
);

// 5 networks
const cm = D.cit_macro, FX = Object.fromEntries(D.fac_net_extra.map(x => [x.scope, x]));
add(H('5. Citation network summary'),
  P(`Directed graph: ${n(cm['whole corpus'].papers)} papers, ${n(CN.edges)} citation links (density ${cm['whole corpus'].density}); ${cm['whole corpus']['papers_never_cited_in_corpus_%']}% of papers are never cited inside the corpus. In-degree distribution (papers): ${D.indeg_bands.map(x => `${x.band}: ${n(x.papers)}`).join(' · ')}. Max in-degree ${CN.in_degree_max}; heavy-tailed.`),
  ...table('PageRank top 10', ['#', 'Paper', 'Inst.', 'Year', 'PageRank', 'In-deg.', 'Cites'], CN.top10_pagerank.map((p, k) => [k + 1, short(p.title), SH[p.inst], p.year, p.pagerank.toFixed(4), p.in_degree_in_corpus, p.citations_openalex]), [.3, 4.5, .6, .5, .8, .6, .6], [0, 3, 4, 5, 6], 13),
  ...table('Cross-institute citation flow (rows cite columns)', ['Citing ↓ / cited →', ...I.map(i => SH[i]), 'To own institute'], I.map(a => [SH[a], ...I.map(c => n(CN.flow_matrix_source_rows_target_cols[a][c])), CN.per_institute_outgoing_share[a]['to_same_inst_%'] + '%']), [1.4, 1, 1, 1, 1.2], [1, 2, 3, 4]),
  P(`Only ${n(CN.edges_cross_institute)} links (${(CN.edges_cross_institute / CN.edges * 100).toFixed(1)}%) cross institutes. With other Indian institutes, in/out citation ratios are ${I.map(i => `${SH[i]} ${S[i].in_over_out_ratio}`).join(', ')}: all three cite India (mostly IITs) more than India cites them (mostly private universities: VIT, Saveetha, LPU, SRM).`),
  ...pair(RFIG('R7_in_degree.png'), RFIG('R8_pagerank_top10.png'), 'In-degree distribution (log–log, heavy-tailed).', 'Top 10 papers by PageRank.', .4),
);
add(H('6. Authorship network summary'),
  ...table('Faculty co-authorship network', ['Measure', 'All', ...I.map(i => SH[i])], [
    ['Faculty / links / isolated', ...['whole_network', ...I].map(s => `${FN[s].nodes} / ${n(FN[s].edges)} / ${FN[s].isolated_faculty}`)],
    ['Avg collaborators (degree) · clustering', ...['whole_network', ...I].map(s => `${FN[s].avg_collaborators} · ${FN[s].avg_clustering}`)],
    ['Diameter · avg path (largest comp.)', ...['all three institutes', ...I].map(s => `${FX[s].diameter_largest_component} · ${FX[s].avg_shortest_path_largest_component}`)],
    ['Louvain communities (Q) · Leiden (Q)', ...['whole_network', ...I].map(s => `${FN[s].louvain.communities} (${FN[s].louvain.modularity}) · ${FN[s].leiden.communities} (${FN[s].leiden.modularity})`)],
    ['Communities vs departments NMI', 'n/a', ...I.map(i => FN[i].community_vs_department.NMI)]], [2.4, 1.3, 1.3, 1.3, 1.3], [1, 2, 3, 4], 13),
  ...table('Most collaborative (degree) and brokers (betweenness)', ['Institute', 'Highest degree (collaborators)', 'Highest betweenness'],
    I.map(i => [SH[i], D.leaders && FN[i].top5_collaborators.slice(0, 3).map(r => `${r.faculty_name} (${r.collaborators})`).join('; '), D.brokers[i].slice(0, 3).map(r => `${r.faculty_name} (${(+r.betweenness).toFixed(3)})`).join('; ')]), [.7, 3, 3], [], 13),
  ...table('Largest Louvain communities', ['Comm.', 'Size', 'Institute', 'Main department', 'Leaders'], D.communities.slice(0, 5).map(c => [`C${c.community}`, c.size, SH[c.institute], `${c.department} (${c['dept_share_%']}%)`, c.leaders]), [.5, .5, .6, 2.6, 3.2], [1], 13),
  ...pair(RFIG('R2_faculty_network.png'), RFIG('R4_within_outside.png'), 'Faculty co-authorship network, Louvain communities.', 'Co-authors within vs outside the institute.', .5),
  ...table('Bridge authors: co-authorship edges to other Indian institutes (top 3)', ['Institute', 'Faculty (edges · partner institutes · joint papers)'],
    I.map(i => [SH[i], D.bridges[i].slice(0, 3).map(b => `${b.faculty_name} (${b.cross_institute_edges} · ${b.distinct_indian_partner_institutes} · ${b.joint_papers})`).join('; ')]), [.7, 6], [], 13),
);

// 7 reach
const RC = Object.fromEntries(LC.collaboration_reach.map(r => [r.institution, r]));
const lsh = (i, l) => (LC.by_locality.find(r => r.your_inst === i && r.locality === l) || {})['share_of_links_%'] || 0;
const cl = (i, c) => LC.by_cluster.find(r => r.your_inst === i && r.partner_cluster === c) || {};
const pt = (i, c) => D.peers.filter(r => r.your_inst === i && r.partner_cluster === c).slice(0, 2).map(r => `${abbr(r.partner_inst)} (${r.shared_papers})`).join(', ');
const TW = LC.top_faculty_within_vs_outside;
add(H('7. Indian connections, locality and reach'),
  ...table('Collaboration reach and locality', ['Measure', ...I.map(i => SH[i])], [
    ['Papers with another Indian inst. / abroad', ...I.map(i => `${RC[i]['with_other_indian_inst_%']}% / ${RC[i]['with_foreign_inst_%']}%`)],
    ['Partner links: same state / same region / other region', ...I.map(i => `${lsh(i, 'Same state')} / ${lsh(i, 'Same region')} / ${lsh(i, 'Other region')}%`)],
    ['Links with IITs · NITs (share)', ...I.map(i => `${cl(i, 'IIT').share_of_links_pct || cl(i, 'IIT')['share_of_links_%']}% · ${cl(i, 'NIT')['share_of_links_%']}%`)],
    ['Top peer IITs', ...I.map(i => pt(i, 'IIT'))], ['Top peer NITs', ...I.map(i => pt(i, 'NIT'))],
    ['Most co-authors within institute', ...I.map(i => TW[i].within.slice(0, 2).map(r => `${r.faculty_name} (${r.coauthors_same_institute})`).join(', '))],
    ['Most co-authors outside institute', ...I.map(i => TW[i].outside.slice(0, 2).map(r => `${r.faculty_name} (${r.coauthors_outside_institute})`).join(', '))],
    ['Top Indian citers', ...I.map(i => D.incoming[i].slice(0, 2).map(r => abbr(r.citing_inst).replace(' University', ' Univ.')).join(', '))]], [2.2, 1.6, 1.6, 1.6], [], 13),
  P(`Collaboration is mostly long-distance: ${OR[0]}–${OR[1]}% of Indian partner links leave the home region. NITJ is the most local (IIT (ISM) Dhanbad, CSIR-NML, NIT Patna). Peer institutes not in our group (NITs, IITs, IIITs, IISERs, IISc) account for about 30% of links. The three assigned institutes barely work together: ${Object.values(LC.between_our_institutes.joint_papers).reduce((a, x) => a + x, 0)} joint papers and ${LC.between_our_institutes.faculty_links} faculty links. Internal and external hubs are different people (Spearman ${I.map(i => LC.within_vs_outside_spearman[i]).join(' / ')}).`),
  ...pair(RFIG('R9_institute_network.png'), RFIG('R10_connectedness.png'), 'Institute collaboration network: our three institutes and partners with 12+ joint papers.', 'Shared partners and direct links between our three institutes.', .45),
  ...pair(FIG('10_indian_partners.png'), RFIG('R11_peer_trend.png'), 'Top 10 Indian partner institutes per institute.', 'Joint papers with peer NITs, IITs, IIITs, IISERs and IISc per year.', .55),
);
add(H('8. Citation flows and partner types'),
  ...table('Citations exchanged with other Indian institutes (2016–2026)', ['Measure', ...I.map(i => SH[i])], [
    ['Received from / given to other Indian institutes', ...I.map(i => `${n(S[i].in_cites_from_other_indian)} / ${n(S[i].out_cites_to_other_indian)}`)],
    ['Impact ratio (in ÷ out)', ...I.map(i => S[i].in_over_out_ratio)],
    ['Self-institute citations', ...I.map(i => D.inflow[i]['self_institute_citations_%'] + '%')],
    ['Distinct Indian institutes citing us', ...I.map(i => n(D.inflow[i].distinct_indian_institutes_citing))],
    ['Papers cited by another Indian institute', ...I.map(i => D.inflow[i]['papers_cited_by_another_indian_institute_%'] + '%')]], [2.6, 1.3, 1.3, 1.3], [1, 2, 3], 13),
  ...table('Indian partners by exact type (all three institutes)', ['Partner type', 'Institutes', 'Joint papers', 'They cite our papers', 'Our papers cite them'],
    (() => { const m = {}; I.forEach(i => (D.partner_res[i].cross_cluster || []).forEach(r => { const o = m[r.partner_cluster] || (m[r.partner_cluster] = [0, 0, 0, 0]); o[0] += r.partners; o[1] += r.shared_papers; o[2] += r.cites_from_partner; o[3] += r.cites_to_partner; }));
      return Object.entries(m).sort((a, b) => b[1][1] - a[1][1]).slice(0, 7).map(([k, v]) => [k, v[0], n(v[1]), n(v[2]), n(v[3])]); })(), [2, 1, 1.1, 1.3, 1.3], [1, 2, 3, 4], 13),
  ...pair(FIG('14_citation_ratio.png'), RFIG('R16_citers_cited.png'), 'In/out citation ratio by year and overall.', 'Who cites us most and whom we cite most.', .45),
  ...pair(FIG('18_flow_by_cluster.png'), RFIG('R13_similarity_vs_collab.png'), 'Citations received from and given to each partner cluster (% of the institute’s total).', 'Topic similarity vs joint papers (top partners).', .5),
  P(`In/out ratios ${I.map(i => S[i].in_over_out_ratio).join(', ')}: we cite IITs, CSIR and DAE labs far more than they cite us; private universities supply most incoming citations. Topic similarity does not predict collaboration (ρ ${I.map(i => D.partner_res[i].similarity_vs_shared_papers_spearman.rho).join(' / ')}). Not included: top 10 papers citing our institutes.`, { run: { size: 15 } }),
);

const doc = new Document({
  creator: 'Group 15', title: 'Group 15 Statistics Report',
  styles: { default: { document: { run: { font: 'Calibri', size: 17 } } },
    paragraphStyles: [{ id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 21, bold: true, color: ACCENT, font: 'Calibri' }, paragraph: { spacing: { before: 120, after: 50 }, outlineLevel: 1, keepNext: true } }] },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 720, right: 850, bottom: 700, left: 850 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ['Group 15 · Statistics report · page ', PageNumber.CURRENT, ' of ', PageNumber.TOTAL_PAGES], size: 14, color: '8C8C8C' })] })] }) },
    children: C }],
});
const out = path.join(R, process.env.REPORT_OUT || 'Group15_Statistics_Report.docx');
Packer.toBuffer(doc).then(x => { fs.writeFileSync(out, x); console.log('wrote', out, `${tn} tables, ${fn} figures`); });
