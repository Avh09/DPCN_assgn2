// Builds report/Group15_DPCN_Report.docx from report_data.json, the figures and the dashboard screenshots.
//   python report/report_data.py && python report/report_figures.py && node report/build_report.js
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType,
  ShadingType, BorderStyle, ImageRun, TableOfContents, Footer, Header, PageNumber, LevelFormat, PageBreak, ExternalHyperlink,
} = require('docx');

const R = __dirname, ROOT = path.join(R, '..');
const D = JSON.parse(fs.readFileSync(path.join(R, 'report_data.json'), 'utf8'));
const HL = D.headline;
const I = D.insts, SH = { 'MANIT Bhopal': 'MANIT', 'NIT Jamshedpur': 'NITJ', 'NIT Silchar': 'NITS' };
const FIG = f => path.join(ROOT, 'data', 'out', 'figures', f);
const RFIG = f => path.join(R, 'figures', f);
const SHOT = f => path.join(R, 'screenshots', f);
const n = x => Number(x).toLocaleString('en-US');
const S = Object.fromEntries(D.summary.map(r => [r.institution, r]));

const FONT = 'Calibri', BODY = 21, W = 9026; // A4 with 1-inch margins
const ACCENT = '1F4E79', HEAD_FILL = 'DCE6F2', ZEBRA = 'F5F8FC';

// ------------------------------------------------------------------ helpers
// "**bold**" and "*italic*" inline markup
function runs(text, base = {}) {
  const out = [];
  String(text).split(/(\*\*[^*]+\*\*|\*[^*]+\*)/).forEach(part => {
    if (!part) return;
    if (part.startsWith('**')) out.push(new TextRun({ text: part.slice(2, -2), bold: true, ...base }));
    else if (part.startsWith('*')) out.push(new TextRun({ text: part.slice(1, -1), italics: true, ...base }));
    else out.push(new TextRun({ text: part, ...base }));
  });
  return out;
}
const P = (text, o = {}) => new Paragraph({ children: runs(text, o.run || {}), spacing: { after: 120, line: 276 }, alignment: o.align, ...(o.p || {}) });
const H1 = (t, brk = true) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: brk, spacing: brk ? undefined : { before: 480, after: 200 } });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = t => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (text, lvl = 0) => new Paragraph({ numbering: { reference: 'bul', level: lvl }, children: runs(text), spacing: { after: 60, line: 264 } });
const NUM = text => new Paragraph({ numbering: { reference: 'num', level: 0 }, children: runs(text), spacing: { after: 60, line: 264 } });
const NOTE = text => new Paragraph({ children: runs(text, { italics: true, color: '595959', size: 19 }), spacing: { after: 140 } });

let tabNo = 0, figNo = 0;
const caption = (kind, text) => new Paragraph({ children: [new TextRun({ text: `${kind} ${kind === 'Table' ? ++tabNo : ++figNo}. `, bold: true, size: 19, color: ACCENT }), ...runs(text, { size: 19, color: '404040' })],
  spacing: { before: kind === 'Table' ? 160 : 60, after: kind === 'Table' ? 60 : 200 }, keepNext: kind === 'Table' });

const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
const borders = { top: border, bottom: border, left: border, right: border };
// table(caption, headers, rows, widths as fractions, numeric column indexes)
function table(cap, headers, rows, fr, numCols = [], o = {}) {
  const tot = fr.reduce((a, b) => a + b, 0);
  const cw = fr.map(f => Math.floor(f / tot * W)); cw[cw.length - 1] += W - cw.reduce((a, b) => a + b, 0);
  const cell = (t, j, head, z) => new TableCell({
    width: { size: cw[j], type: WidthType.DXA }, borders,
    shading: { fill: head ? HEAD_FILL : z ? ZEBRA : 'FFFFFF', type: ShadingType.CLEAR, color: 'auto' },
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ alignment: numCols.includes(j) ? AlignmentType.RIGHT : AlignmentType.LEFT, children: runs(t ?? '', { size: o.size || 18, bold: head }) })],
  });
  const out = [];
  if (cap) out.push(caption('Table', cap));
  out.push(new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: cw,
    rows: [new TableRow({ tableHeader: true, children: headers.map((h, j) => cell(h, j, true)) }),
      ...rows.map((r, k) => new TableRow({ cantSplit: true, children: r.map((t, j) => cell(String(t), j, false, k % 2)) }))],
  }));
  out.push(new Paragraph({ spacing: { after: 80 }, children: [] }));
  return out;
}
function pngSize(file) { const b = fs.readFileSync(file); return [b.readUInt32BE(16), b.readUInt32BE(20)]; }
function figure(file, cap, widthPx = 600) {
  const [w, h] = pngSize(file);
  const width = Math.min(widthPx, 602), height = Math.round(width * h / w);
  return [new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120 }, children: [new ImageRun({ type: 'png', data: fs.readFileSync(file), transformation: { width, height },
    altText: { title: cap.slice(0, 60), description: cap, name: path.basename(file) } })] }), caption('Figure', cap)];
}
function callout(title, lines) {
  return [new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: [W], rows: [new TableRow({ children: [new TableCell({
    width: { size: W, type: WidthType.DXA }, shading: { fill: 'FFF7E0', type: ShadingType.CLEAR, color: 'auto' },
    borders: { top: { style: BorderStyle.SINGLE, size: 6, color: 'E0B000' }, bottom: { style: BorderStyle.SINGLE, size: 6, color: 'E0B000' }, left: { style: BorderStyle.SINGLE, size: 24, color: 'E0B000' }, right: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' } },
    margins: { top: 100, bottom: 100, left: 160, right: 160 },
    children: [new Paragraph({ children: [new TextRun({ text: title, bold: true, size: 20 })], spacing: { after: 60 } }), ...lines.map(l => new Paragraph({ children: runs(l, { size: 19 }), spacing: { after: 40 } }))],
  })] })] }), new Paragraph({ spacing: { after: 120 }, children: [] })];
}

// ------------------------------------------------------------------ content
const C = [];
const add = (...xs) => xs.flat().forEach(x => C.push(x));

// ---------- title page
add(
  new Paragraph({ spacing: { before: 2200 }, children: [new TextRun({ text: 'DPCN · Assignment 2 · Group 15', size: 24, color: '7F7F7F' })] }),
  new Paragraph({ spacing: { before: 200, after: 200 }, children: [new TextRun({ text: 'Research Output and Collaboration Networks of MANIT Bhopal, NIT Jamshedpur and NIT Silchar, 2016–2026', size: 48, bold: true, color: ACCENT })] }),
  new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 4 } }, spacing: { after: 300 }, children: [new TextRun({ text: 'Dataset construction, publication statistics, citation and co-authorship network analysis, and an interactive dashboard', size: 26, color: '404040' })] }),
  P('**Report status:** working draft, 19 October 2026. Editable; sections and numbers can be changed directly in Word.'),
  P(`**Corpus:** ${n(D.headline.papers)} distinct journal and conference papers by ${n(D.headline.faculty_with_papers)} verified faculty members (current and former), from OpenAlex.`),
  P('**Deliverables covered:** (1) statistics report specification and results; (2) interactive dashboard (dashboard/index.html).'),
  new Paragraph({ spacing: { before: 400 } }),
  ...callout('Status of this document', [
    'Every pipeline step, including partners.py and the full validate.py run (citation-flow and live lookups included), has been rerun on the final corpus. All tables, figures and dashboard screenshots in this report come from that run.',
    'Partner types now come from the parent-organisation lookup in partners.py (CSIR, DAE, DRDO, ICAR, ISRO, IIT, NIT …), with citations in both directions for every partner and topic similarity for each institute\'s top 25 partners (Sections 5.3–5.4).',
  ]),
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({ children: [new TextRun({ text: 'Contents', bold: true, size: 32, color: ACCENT })], spacing: { after: 200 } }),
  new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-2' }),
  NOTE('Right-click the table of contents and choose "Update field" if page numbers are missing.'),
);

// ---------- 1 executive summary
const silo = D.cit_net.per_institute_outgoing_share;
add(H1('1. Executive summary'),
  P('We built a verified, faculty-level publication dataset for three National Institutes of Technology and analysed it as a set of publication statistics and two networks: a directed citation network between our papers and an undirected co-authorship network between faculty. The headline findings:'),
  B(`**Volume.** NIT Silchar is the largest producer (${n(S['NIT Silchar'].papers)} papers), ahead of MANIT Bhopal (${n(S['MANIT Bhopal'].papers)}) and NIT Jamshedpur (${n(S['NIT Jamshedpur'].papers)}). Output roughly tripled from 2016 to 2025. NIT Jamshedpur grew fastest (CAGR ${D.cagr['NIT Jamshedpur']}% a year, against ${D.cagr['NIT Silchar']}% for NITS and ${D.cagr['MANIT Bhopal']}% for MANIT).`),
  B(`**Quality.** NIT Silchar has the highest share of journal papers in Q1 (${S['NIT Silchar']['journal_Q1_%']}%), then MANIT (${S['MANIT Bhopal']['journal_Q1_%']}%) and NITJ (${S['NIT Jamshedpur']['journal_Q1_%']}%). MANIT and NITS raised their Q1 share from about 22–35% in 2016 to over 40% in 2024–25. About ${HL.conf_share_pct}% of all papers are conference papers, mostly in Q3–Q4 proceedings (Lecture Notes series, Materials Today Proceedings), and only ${HL.core_ranked_papers} have a CORE rank.`),
  B(`**Impact.** MANIT has the highest citations per paper (${S['MANIT Bhopal'].citations_per_paper}) and the highest institute h-index (${S['MANIT Bhopal'].institute_h_index}, against ${S['NIT Silchar'].institute_h_index} for NITS and ${S['NIT Jamshedpur'].institute_h_index} for NITJ). Citations are very concentrated: the top 10 faculty of MANIT hold ${D.author_analysis['MANIT Bhopal']['top10_share_of_citations_%']}% of its citations (Gini ${D.author_analysis['MANIT Bhopal'].gini_citations_per_faculty}).`),
  B(`**Faculty.** Median faculty h-index (2016–26 papers) is ${D.fac_results['NIT Silchar'].h_index.median} at NITS, ${D.fac_results['MANIT Bhopal'].h_index.median} at MANIT and ${D.fac_results['NIT Jamshedpur'].h_index.median} at NITJ. NITS has ${D.fac_results['NIT Silchar'].h_index.h_20_or_more} faculty with h ≥ 20, against ${D.fac_results['MANIT Bhopal'].h_index.h_20_or_more} at MANIT and ${D.fac_results['NIT Jamshedpur'].h_index.h_20_or_more} at NITJ.`),
  B(`**Citation network.** ${n(D.cit_net.edges)} citation links connect ${n(D.cit_net.nodes_in_edges)} of our papers. ${silo['MANIT Bhopal']['to_same_inst_%']}–${silo['NIT Silchar']['to_same_inst_%']}% of the links stay within the same institute, so the three institutes barely cite each other. ${D.cit_macro['whole corpus']['papers_never_cited_in_corpus_%']}% of papers are never cited by another paper in the corpus.`),
  B(`**Co-authorship network.** ${n(D.fac_net.whole_network.nodes)} faculty and ${n(D.fac_net.whole_network.edges)} links, but only ${D.fac_net.whole_network.cross_institute_edges} links cross institutes. The network splits into tight, department-shaped communities (Louvain modularity ${D.fac_net.whole_network.louvain.modularity}, NMI with departments ${Math.min(...I.map(i => D.fac_net[i].community_vs_department.NMI))}–${Math.max(...I.map(i => D.fac_net[i].community_vs_department.NMI))}). A few brokers hold groups together, for example Vijay Bhaskar Semwal and Rajesh Purohit at MANIT.`),
  B(`**Citation flows in India.** All three cite other Indian institutes more than they are cited by them (in/out ratio ${I.map(i => S[i].in_over_out_ratio).join(', ')}). They cite mostly IITs, but are cited mostly by private universities (VIT, Saveetha, LPU, SRM), which account for about 75% of incoming Indian citations.`),
  B(`**Reach and locality.** About a third of papers involve another Indian institute and 11–15% a partner abroad. Most partner links go outside the home region (${Math.round(Math.min(...D.loc.by_locality.filter(x => x.locality === 'Other region').map(x => x['share_of_links_%'])))}–${Math.round(Math.max(...D.loc.by_locality.filter(x => x.locality === 'Other region').map(x => x['share_of_links_%'])))}%). Other NITs, IITs, IIITs, IISERs and IISc account for about 30% of Indian links (for example NITS–IIT Guwahati, MANIT–NIT Raipur, NITJ–IIT (ISM) Dhanbad), while the three assigned institutes share only ${HL.shared_by_two_or_three} papers.`),
  P('All figures and tables in this report are generated from the final verified dataset and can be regenerated with the scripts listed in Section 7. The interactive dashboard (Section 6) shows every table here and lets the reader drill down from any chart, node or table row to the faculty member or paper behind it.'),
);

// ---------- 2 scope
add(H1('2. Scope and data sources', false),
  P('The study covers papers published from 1 January 2016 to the download date in 2026 (2026 is a partial year), by authors affiliated to the three institutes below. Institutes were resolved to OpenAlex institution IDs through their ROR records.'),
  ...table('Institutes and identifiers', ['Short name', 'Official name', 'OpenAlex ID', 'ROR'], [
    ['MANIT Bhopal', 'Maulana Azad National Institute of Technology', 'I91277730', 'ror.org/026vtd268'],
    ['NIT Jamshedpur', 'National Institute of Technology Jamshedpur', 'I187761245', 'ror.org/01sebzx27'],
    ['NIT Silchar', 'National Institute of Technology Silchar', 'I151903974', 'ror.org/001ws2a36']], [1.3, 3, 1.3, 1.6]),
  ...table('Data sources', ['Source', 'Used for'], [
    ['OpenAlex API (works, authors, institutions)', 'Papers, authors, affiliations, citation counts, reference lists, citing papers, fields'],
    ['Official faculty pages (current)', 'List of current faculty with department and designation (740 people)'],
    ['Internet Archive (Wayback Machine) snapshots of faculty pages, 2016–2025', 'Former faculty who left during the period (126 people, 276 page copies)'],
    ['SCImago Journal Rank (SJR)', 'Journal quartiles; citations per document as an impact-factor proxy'],
    ['Scopus CiteScore percentiles (Elsevier API)', 'Quartiles of conference proceedings and journals missing from SJR'],
    ['CORE 2023 conference ranking', 'A*/A/B/C ranks for computing conferences'],
    ['Scopus affiliation search', 'Coverage check of the OpenAlex corpus (Section 3.8)']], [2.2, 4]),
);

// ---------- 3 dataset creation
const neg = x => '−' + n(x);
const funnel = [['Unique works downloaded from OpenAlex', n(HL.raw_works)], ['Non-research items dropped (errata, paratext, retractions)', neg(HL.nonresearch_dropped)], ['Duplicate DOIs dropped', neg(HL.dup_doi_dropped)],
  [`Non journal/conference items dropped (book chapters ${n(HL.book_chapters_dropped)}; preprints ${n(HL.preprints_dropped)}; other ${n(HL.other_dropped - HL.book_chapters_dropped - HL.preprints_dropped)})`, neg(HL.other_dropped)], ['Journal and conference papers kept', n(HL.papers_kept_before_faculty_filter)],
  ['Papers with at least one verified faculty author (final corpus)', n(HL.papers)], ['Rows in group15_data.csv (paper × faculty author × institute)', n(HL.rows)]];
add(H1('3. Dataset creation'),
  P('The dataset was built in five stages, each a separate script. run_all.sh runs them in order and then validate.py.'),
  H2('3.1 Download and cleaning'),
  P('fetch.py downloads every OpenAlex work with at least one author affiliated to one of the three institution IDs in the window. build_tables.py then cleans it:'),
  B('Non-research types (erratum, paratext, retraction) are dropped, and duplicate DOIs are removed.'),
  B('Only journal articles and conference papers are kept. OpenAlex types are mapped to journal or conference using the source type, so a conference paper in a book series is still a conference paper.'),
  B('Authorship is exploded into one row per paper, author and institute, keeping the raw affiliation string for later checks.'),
  ...table('Corpus funnel', ['Step', 'Count'], funnel, [5, 1.2], [1]),

  H2('3.2 Faculty lists and verification'),
  P('The assignment asks for faculty-level results, so we did not use affiliation alone. Anyone who prints an institute affiliation (PhD scholars, project staff, visitors, external collaborators) would otherwise count as faculty. We first built a verified list of faculty and then kept only their papers.'),
  H3('Current faculty'),
  P('scrape_faculty.py collected names, departments and designations from the official department pages of all three institutes (740 people). faculty_match.py matches each name to OpenAlex author IDs that published from the same institute:'),
  B('Names are normalised for case, honorifics, dots and joined initials ("RK" becomes "R K").'),
  B('The surname must match and the given names must agree in full or as initials: "Krishna K Dhote" matches "K. K. Dhote" but not "Rahul Dhote".'),
  B('One person can have several OpenAlex IDs. All of them are merged.'),
  B('Safety rules: for common names, only IDs with the main profile\'s ORCID are kept. Initial-only names drop IDs with a different full first name. Reversed names are allowed only with full names. Same-name colleagues are kept apart by department.'),
  H3('Former faculty'),
  P(`scrape_former_faculty.py reads 276 archived copies of the institutes' faculty pages (Internet Archive, 2016–2025). A name counts only when a faculty designation follows it, which keeps out scholars and staff listed on the same pages. Former faculty go through the same matching and carry first_seen and last_seen years. **Check:** ${HL.former_fit_pct}% of former faculty's papers fall inside the years they appear on the pages (±2 years), and ${HL.former_fit_people} of ${HL.former_people} people fit, which supports the matches.`),
  H3('Verification'),
  B('A random sample of 50 matches was checked by hand: 45 correct, 2 wrong (the rule that caused them was fixed), 3 unsure, so **about 90% precision**.'),
  B('A 90-row sample of uncertain matches was checked against ORCID, faculty pages and Google Scholar: 44 confirmed, 8 wrong, 38 not verifiable. The rule errors found (initial surnames, spelling variants, prefix matches, ORCID splits) were fixed for all rows.'),
  B(`${HL.overrides} evidence-backed corrections (faculty-to-record assignments and paper-level fixes) are kept in data/faculty_overrides.csv, and validate.py checks that each one is applied.`),
  ...table('Faculty list after verification', ['Institute', 'Current', 'Former', 'Faculty with papers', 'Median h', 'h ≥ 20'],
    I.map(i => [i, D.fac_results[i].matched_current ?? '', D.fac_results[i].matched_former ?? '', S[i].faculty_with_papers, D.fac_results[i].h_index.median, D.fac_results[i].h_index.h_20_or_more]), [2, 1, 1, 1.5, 1, 1], [1, 2, 3, 4, 5]),
  P(`In total ${n(HL.list_total)} people are on the final list (${n(HL.list_official)} from official pages, ${n(HL.list_former)} former from archived pages, ${n(HL.list_added)} added after verification). ${n(HL.list_matched)} of them were matched to OpenAlex papers and ${n(HL.list_not_found)} had none. ${n(HL.faculty_with_papers)} have at least one paper in the final corpus.`),

  H2('3.3 Keeping only faculty authors'),
  P(`corpus_filter.py removes author rows that are not verified faculty (${n(HL.rows_removed_non_faculty)} rows). Each removed row has a role from OpenAlex evidence and the official pages: probable PhD scholar or visitor, probable faculty not on any list, or unclear. A paper stays in the corpus if at least one verified faculty member is an author.`),

  H2('3.4 Quartiles and impact proxies'),
  P('Every paper gets a venue quartile from the best available source, recorded in the quartile_source column:'),
  ...table('Quartile sources (rows of group15_data.csv)', ['quartile_source', 'Journal rows', 'Conference rows', 'Meaning'], [
    ['sjr_approx', '10,894', '0', 'SCImago SJR quartile (recomputed per subject, best category)'],
    ['scopus_citescore', '91', '3,385', 'Scopus CiteScore percentile converted to a quartile'],
    ['core', '0', '33', 'CORE 2023 rank (B or C)'],
    ['estimated_openalex', '401', '2,253', 'Estimated from OpenAlex venue citedness (58% exact, 96% within one quartile when tested)'],
    ['estimated_publisher', '1', '766', 'Estimated from the publisher series'],
    ['none (Unranked)', '20', '50', 'No usable venue information']], [1.6, 1, 1.1, 4], [1, 2]),
  P('**IF > 5 / IF > 10.** No free source gives the Clarivate impact factor, so we use SCImago\'s citations per document (2 years) as the proxy. q1_impact_gt5 and q1_impact_gt10 mark journal papers that are Q1 and whose journal is above 5 or 10 on that measure.'),

  H2('3.5 Papers with more than 10 authors'),
  P(`${HL.multi_author_papers} papers have more than 10 authors (at most ${HL.max_authors} in the data). They are flagged in is_multi_author_10plus and analysed separately (Section 4.4). They are ${HL.multi_author_pct}% of papers and do not change any headline figure.`),

  H2('3.6 Output schema'),
  P('The main file, group15_data.csv, has one row per paper, faculty author and institute. The required columns are:'),
  ...table('Required columns of group15_data.csv', ['Column', 'Content'], [
    ['group, institution', 'Group number (15) and our institute'], ['author', 'Author name as in OpenAlex (faculty only)'],
    ['title, year, type', 'Paper title, publication year, journal or conference'], ['journal_name, issn, doi', 'Venue name, ISSN, DOI in https://doi.org/ form'],
    ['citations', 'OpenAlex cited-by count'], ['quartile', 'Q1–Q4, CORE B/C, or Unranked'],
    ['coauthor_institutes', 'Other institutes on the paper'], ['cites_indian_inst, cited_by_indian_inst', 'Whether the paper cites / is cited by another Indian institute']], [2.2, 4]),
  P(`Added columns include faculty_name, department, faculty_status (current or former), field and domain (OpenAlex topic), quartile_source, venue_h_index, journal_cites_per_doc, is_multi_author_10plus and the two IF flags. The other required files are citation_network.csv (${n(HL.citation_edges)} directed edges), authorship_network.csv (${n(HL.author_pairs)} author pairs) and indian_connections.csv (${n(HL.connection_rows)} institute pairs).`),

  H2('3.7 Validation'),
  P(`validate.py runs ${HL.validate_passed + HL.validate_failed} checks in five groups. **Structure:** required columns, years, institutes, no duplicates. **Consistency:** cited_by_indian_inst recomputed with separate code (0 differences), totals equal across files. **Maths:** h-index, NMI, ARI and Jaccard on known test cases. **Faculty:** each author ID belongs to one person, and all corrections are applied. It also runs live OpenAlex spot checks (citation flags, paper counts, CSIR labels).`),
  P(`**Current status:** ${HL.validate_passed} of ${HL.validate_passed + HL.validate_failed} checks pass on the final data${HL.validate_failed ? ` (${HL.validate_failed} fail: see data/out/validate_report.txt)` : ''}.`),

  H2('3.8 Coverage compared with Scopus'),
  ...table('OpenAlex vs Scopus coverage (before the faculty filter)', ['Institute', 'Scopus docs', 'OpenAlex docs', 'Scopus found in ours', 'Ours found in Scopus', 'Scopus-only (main types)'],
    I.map(i => { const s = D.scopus[i], t = s.scopus_only_by_type; return [i, n(s.scopus_docs), n(s.openalex_docs), s['scopus_found_in_ours_%'] + '%', s['openalex_found_in_scopus_%'] + '%', `${n(s.scopus_only)} (chapters ${t['Book Chapter'] || 0}, conf. ${t['Conference Paper'] || 0}, articles ${t.Article || 0})`]; }),
    [1.5, 1, 1.1, 1.1, 1.1, 2.6], [1, 2, 3, 4]),
  P('About 85% of Scopus records are in our corpus. Most of the gap is book chapters, which we exclude by design, plus conference papers that OpenAlex attributes to another affiliation.'),
);

// ---------- 4 statistics
const ppyRows = D.ppy.map(r => [r.year + (r.year === '2026' ? '*' : ''), ...I.map(i => n(r[i])), n(r['all (unique papers)'])]);
const qs = i => D.quartiles[i]['shares_%'];
add(H1('4. Statistics report (Deliverable 1)'),
  P('This section follows the Deliverable 1 specification: (4.1) institutional breakdown, (4.2) faculty analytics, (4.3) the top-30 papers deep-dive and (4.4) multi-author papers. Network summaries are in Section 5. Each figure is produced by plots.py or report/report_figures.py, and each table comes from a CSV in data/out/stats/.'),
  NOTE('Slide/page plan for the ≤10-slide / ≤5-page version: 1 scorecard (Table 8) · 2 output trend (Figure 1) · 3 quartiles and conference ranks (Figure 3, Table 11) · 4 top journals (Table 12) · 5 h-index (Figure 6) · 6 leaderboards (Figure 7) · 7 top-30 (Figure 9, Table 20) · 8 citation network (Tables 25–26) · 9 co-authorship (Figure 14, Table 27) · 10 flows (Figure 16).'),
  H2('4.1 Institutional breakdown'),
  ...table('Institute scorecard (institution_summary.csv)', ['Metric', ...I.map(i => SH[i])], [
    ['Papers (journal / conference)', ...I.map(i => `${n(S[i].papers)} (${n(S[i].journal_papers)} / ${n(S[i].conference_papers)})`)],
    ['Faculty with papers', ...I.map(i => S[i].faculty_with_papers)], ['Total citations', ...I.map(i => n(S[i].total_citations))],
    ['Citations per paper', ...I.map(i => S[i].citations_per_paper)], ['Institute h-index', ...I.map(i => S[i].institute_h_index)],
    ['Journal Q1 / Q2 / Q3 / Q4 (%)', ...I.map(i => `${S[i]['journal_Q1_%']} / ${S[i]['journal_Q2_%']} / ${S[i]['journal_Q3_%']} / ${S[i]['journal_Q4_%']}`)],
    ['Q1 papers with IF > 5 / > 10', ...I.map(i => `${n(S[i].Q1_and_IF_gt5)} / ${S[i].Q1_and_IF_gt10}`)],
    ['Papers with > 10 authors (%)', ...I.map(i => S[i]['papers_over_10_authors_%'])],
    ['Citations from / to other Indian institutes', ...I.map(i => `${n(S[i].in_cites_from_other_indian)} / ${n(S[i].out_cites_to_other_indian)}`)],
    ['In/out ratio', ...I.map(i => S[i].in_over_out_ratio)]], [2.6, 1.6, 1.6, 1.6], [1, 2, 3]),
  H3('Publication volume, 2016–2026'),
  ...figure(FIG('01_papers_per_year.png'), 'Papers per year by institute. The dotted 2026 segment is a partial year.'),
  ...table('Papers per year (a paper with authors from two of our institutes counts once in "All")', ['Year', ...I.map(i => SH[i]), 'All (unique)'], ppyRows, [1, 1, 1, 1, 1.2], [1, 2, 3, 4]),
  NOTE('* 2026 is a partial year. Growth 2016→2025 (CAGR): MANIT ' + D.cagr['MANIT Bhopal'] + '%, NITJ ' + D.cagr['NIT Jamshedpur'] + '%, NITS ' + D.cagr['NIT Silchar'] + '%.'),
  ...figure(FIG('02_paper_types.png'), 'Journal papers against conference papers.'),
  H3('Journal quartile shares'),
  ...table('Journal quartile share (% of journal papers with a quartile)', ['Institute', 'Journal papers', 'Q1', 'Q2', 'Q3', 'Q4', 'Unranked'],
    I.map(i => [i, n(D.quartiles[i].journal_papers), qs(i).Q1, qs(i).Q2, qs(i).Q3, qs(i).Q4, D.quartiles[i].unranked]), [2, 1.3, .8, .8, .8, .8, 1], [1, 2, 3, 4, 5, 6]),
  ...figure(FIG('03_quartiles.png'), 'Journal quartile mix (left) and Q1 share by year (right).'),
  P(`Q1 share rose clearly at MANIT (${D.quartiles['MANIT Bhopal']['Q1_fraction_by_year_%']['2016']}% in 2016 to ${D.quartiles['MANIT Bhopal']['Q1_fraction_by_year_%']['2024']}% in 2024) and NITS (${D.quartiles['NIT Silchar']['Q1_fraction_by_year_%']['2016']}% to ${D.quartiles['NIT Silchar']['Q1_fraction_by_year_%']['2025']}% in 2025), but stayed between ${Math.floor(Math.min(...Object.values(D.quartiles['NIT Jamshedpur']['Q1_fraction_by_year_%']).slice(0, -1)))}% and ${Math.ceil(Math.max(...Object.values(D.quartiles['NIT Jamshedpur']['Q1_fraction_by_year_%'])))}% at NITJ.`),
  H3('Conference ranks'),
  ...table('Conference papers by venue rank', ['Institute', 'Conference papers', 'CORE-ranked (B / C)', 'Proceedings Q1', 'Q2', 'Q3', 'Q4', 'Unranked'],
    I.map(i => { const c = D.conf[i], q = c.scopus_quartile_counts; return [i, n(c.conference_papers), `${c.with_CORE_rank} (${c.rank_counts.B || 0} / ${c.rank_counts.C || 0})`, q.Q1 || 0, q.Q2 || 0, n(q.Q3 || 0), n(q.Q4 || 0), c.unranked]; }),
    [1.8, 1.2, 1.4, 1.1, .7, .8, .8, 1], [1, 2, 3, 4, 5, 6, 7]),
  ...figure(RFIG('R5_conference_rank.png'), 'Conference papers by venue rank: CORE 2023 rank where the conference is listed, otherwise the Scopus quartile of the proceedings.'),
  P('Almost no conference paper is in a CORE-ranked venue (' + HL.core_ranked_papers + ' in total, none A or A*). Most appear in Scopus-indexed proceedings series, which rank Q3–Q4. Top conference venues: ' + I.map(i => `${SH[i]}: ${Object.entries(D.conf_venues[i]).slice(0, 2).map(([k, v]) => `${k} (${v})`).join(', ')}`).join('; ') + '.'),
  H3('Top 5 journals per institute'),
  ...table('Top 5 journals by paper count', ['Institute', 'Journal', 'Papers', 'Citations', 'Quartile'],
    I.flatMap(i => D.top_journals[i].map((j, k) => [k ? '' : i, j.journal_name, j.papers, n(j.citations), j.quartile])), [1.5, 4, .8, .9, .8], [2, 3]),
  ...figure(RFIG('R6_top_journals.png'), 'Top 5 journals per institute by paper count; bar colour shows the SCImago quartile.'),
  P('Multimedia Tools and Applications and Arabian Journal for Science and Engineering are in the top five at more than one institute. MANIT\'s most frequent venue is a Q3 journal (National Academy Science Letters, 64 papers), while NITS\'s top-cited frequent venue is the International Journal of Hydrogen Energy (2,935 citations from 44 papers).'),
  H3('Research areas and citations'),
  ...figure(FIG('06_research_areas.png'), 'Research areas: OpenAlex field of each paper, top 8.'),
  ...table('Research-area profile (% of papers, top 5 fields) and best-cited fields (≥ 50 papers)', ['Institute', 'Top fields', 'Highest mean citations per paper'],
    I.map(i => [i, Object.entries(D.areas[i]['fields_top8_%']).slice(0, 5).map(([k, v]) => `${k} ${v}%`).join(', '), Object.entries(D.areas[i]['highest_mean_citations_fields(min 50 papers)']).slice(0, 3).map(([k, v]) => `${k} ${v}`).join(', ')]), [1.4, 3.4, 2.6]),
  ...figure(FIG('05_citations.png'), 'Citation distribution: most papers get few citations and a few get very many.'),
  ...figure(RFIG('R15_field_impact.png'), 'Research fields by size (papers, log scale) and citation impact (mean citations per paper). Energy, Environmental Science and Agricultural Sciences are small but highly cited; Engineering is large but closer to the average.'),
);

// 4.2 faculty
const leaderRows = i => D.leaders[i].map((f, k) => [k + 1, f.faculty_name, f.department, f.h_index, f.papers, n(f.citations), f['q1_share_%'] || '—', f.top_journal]);
add(H2('4.2 Faculty analytics'),
  P('Faculty metrics use each person\'s 2016–2026 papers in the corpus. The h-index is therefore a period h-index, lower than a career h-index on Google Scholar.'),
  ...table('Faculty h-index distribution (number of faculty)', ['h-index', ...I.map(i => SH[i])], ['0', '1-4', '5-9', '10-14', '15-19', '20-29', '30+'].map(b => [b, ...I.map(i => (D.hdist.find(r => r.institution === i && r.h_index === b) || {}).faculty || 0)]), [1.2, 1, 1, 1], [1, 2, 3]),
  ...figure(FIG('04_h_index.png'), 'h-index histogram of verified faculty per institute (2016–2026 papers); dashed line = median.'),
  ...figure(RFIG('R1_faculty_h_index.png'), 'The same distribution as a share of each institute\'s faculty, so the three institutes can be compared directly.'),
  P(`NITJ has the most faculty at h ≤ 4 (${Math.round(100 * (22 + 104) / 241)}%), which fits its high share of ad-hoc and short-term posts. NITS has a much thicker upper tail: ${D.fac_results['NIT Silchar'].h_index.h_20_or_more} faculty at h ≥ 20, mostly in Chemistry and Mechanical Engineering.`),
  ...I.flatMap(i => table(`Top-10 faculty by h-index, ${i}`, ['#', 'Faculty', 'Department', 'h', 'Papers', 'Cites', 'Q1 %', 'Most frequent journal'], leaderRows(i), [.35, 1.9, 1.9, .45, .65, .8, .6, 2.3], [0, 3, 4, 5, 6], { size: 17 })),
  NOTE('Kumarasamy Sudhakar (MANIT, Energy Science and Engineering, h 55) holds a permanent position at MANIT and is currently Associate Professor at Universiti Malaysia Pahang (UMP). This explains why UMP is MANIT’s largest foreign partner (Section 5.4). He was missing from the scraped faculty pages and was added after verification.'),
  ...figure(FIG('15_top_faculty.png'), 'Top faculty by h-index per institute.'),
  ...figure(FIG('16_author_concentration.png'), 'Concentration of papers and citations across faculty (Lorenz curves).'),
  ...table('Concentration of output across faculty', ['Institute', 'Median papers / faculty', 'Gini (papers)', 'Gini (citations)', 'Top-10 share of citations', 'Median faculty Q1 share'],
    I.map(i => { const a = D.author_analysis[i]; return [i, a.papers_per_faculty_median, a.gini_papers_per_faculty, a.gini_citations_per_faculty, a['top10_share_of_citations_%'] + '%', a['faculty_median_q1_share_%'] + '%']; }), [1.6, 1.2, 1, 1, 1.2, 1.2], [1, 2, 3, 4, 5]),
  ...table('Largest departments (by papers)', ['Institute', 'Department', 'Faculty', 'Papers', 'Papers / faculty', 'Median h', 'Max h', 'Q1 %'],
    I.flatMap(i => D.dept[i].map((d, k) => [k ? '' : SH[i], d.department, d.faculty_matched, n(d.papers), d.papers_per_faculty, d.median_h_index, d.max_h_index, d['q1_share_%']])), [.8, 2.8, .8, .8, 1, .8, .7, .7], [2, 3, 4, 5, 6, 7], { size: 17 }),
  ...figure(RFIG('R14_departments.png'), 'Departments with 40+ papers: papers per faculty member against journal Q1 share (bubble size = papers). NITS Chemistry stands out on both axes; NITS ECE is highly productive but mostly outside Q1.'),
);

// 4.3 top 30
const t30 = D.top30_sum, T30 = Object.fromEntries(t30.map(r => [r.institution, r]));
add(H2('4.3 Top-30 papers deep-dive'),
  P('For each institute we take the 30 most-cited papers and ask how good their venues are and who wrote them.'),
  ...table('Top-30 papers per institute', ['Metric', ...I.map(i => SH[i])], [
    ['Total citations', ...I.map(i => n(T30[i].citations_total))], ['Citations of #1 / median / #30', ...I.map(i => `${T30[i].citations_max} / ${T30[i].citations_median} / ${T30[i].citations_min}`)],
    ['Journal / conference papers', ...I.map(i => `${T30[i].journal_papers} / ${T30[i].conference_papers}`)], ['Q1 papers (share)', ...I.map(i => `${T30[i].Q1} (${T30[i]['Q1_share_%']}%)`)],
    ['Q1 and IF > 5', ...I.map(i => T30[i].Q1_and_IF_gt5)], ['Q1 and IF > 10', ...I.map(i => T30[i].Q1_and_IF_gt10)],
    ['Median venue h-index', ...I.map(i => T30[i].median_venue_h_index)], ['Papers with a faculty author of h ≥ 20', ...I.map(i => T30[i].papers_with_faculty_h_20_plus)],
    ['Median h of the best faculty author', ...I.map(i => T30[i].median_max_faculty_h)], ['Papers with > 10 authors', ...I.map(i => T30[i].papers_with_10plus_authors)]], [2.8, 1.3, 1.3, 1.3], [1, 2, 3]),
  ...figure(FIG('13_top30_quality.png'), 'Venue quality of the top-30 papers: Q1 with IF > 10, Q1 with IF 5–10, other Q1, not Q1.'),
  P('NITJ\'s top 30 has the highest Q1 share (80%) and the most IF > 10 papers (4), even though its citation counts are the lowest. MANIT\'s top 30 has the most citations (13,526) and is led by review articles in Renewable and Sustainable Energy Reviews and the International Journal of Hydrogen Energy.'),
  ...table('Five most-cited papers per institute (full lists: top10_cited_<institute>.csv, top30_papers_<institute>.csv)', ['Institute', 'Paper', 'Venue, year', 'Cites', 'DOI'],
    I.flatMap(i => D.top10_cited[i].slice(0, 5).map((p, k) => [k ? '' : SH[i], p.title, `${p.journal_name}, ${p.year}`, n(p.citations), p.doi.replace('https://doi.org/', '')])), [.7, 3.2, 2, .6, 1.8], [3], { size: 16 }),
);

// 4.4 hyper
add(H2('4.4 Papers with more than 10 authors'),
  ...table('Papers with more than 10 authors against the rest', ['Institute', 'Group', 'Papers', 'Share', 'Mean cites', 'Median cites', 'Share of cites', 'Journal Q1 %'],
    D.hyper.map(r => [SH[r.institution], r.group, n(r.papers), r['share_of_papers_%'] + '%', r.mean_citations, r.median_citations, r['share_of_citations_%'] + '%', r['journal_Q1_%']]), [.8, 1.8, .8, .7, .8, .8, .9, .9], [2, 3, 4, 5, 6, 7]),
  ...figure(FIG('12_multi_author_10plus.png'), 'Papers with more than 10 authors: count, journal Q1 share and faculty with h ≥ 20.'),
  P(`They are cited more and published in Q1 more often, but they are too few to matter. Removing them changes the institute Q1 share by at most ${HL.multi_q1_max_shift} points and leaves the median faculty h-index unchanged (multi_author_reanalysis.csv).`),
);

// ---------- 5 networks
const cm = D.cit_macro, CN = D.cit_net;
add(H1('5. Network analysis'),
  H2('5.1 Citation network'),
  P('**Definition.** Nodes are our papers. A directed edge A → B means paper A cites paper B, where both are in the corpus. Edges come from OpenAlex reference lists. The network is a DAG in principle; the rare reciprocal pairs come from early-access versions citing each other.'),
  ...table('Macro structure of the citation network (citation_network_macro.json)', ['Measure', 'All', ...I.map(i => SH[i])], [
    ['Papers (nodes)', ...['whole corpus', ...I].map(s => n(cm[s].papers))], ['Citation links (edges)', ...['whole corpus', ...I].map(s => n(cm[s].citation_links))],
    ['Density', ...['whole corpus', ...I].map(s => cm[s].density)], ['Average clustering (undirected)', ...['whole corpus', ...I].map(s => cm[s].avg_clustering_undirected)],
    ['Reciprocity', ...['whole corpus', ...I].map(s => cm[s].reciprocity)], ['Weakly connected components', ...['whole corpus', ...I].map(s => n(cm[s].weak_components))],
    ['Largest component (% of papers)', ...['whole corpus', ...I].map(s => cm[s]['largest_component_share_%'])], ['Papers never cited inside the corpus (%)', ...['whole corpus', ...I].map(s => cm[s]['papers_never_cited_in_corpus_%'])]],
    [2.8, 1, 1, 1, 1], [1, 2, 3, 4]),
  P(`Per-institute rows count links inside that institute only. Per-paper metrics are in citation_node_metrics.csv: in-degree, out-degree, PageRank (damping 0.85), HITS authority and hub scores, and the in-degree h-index.`),
  H3('In-degree distribution'),
  ...table('In-degree distribution (citations received from other corpus papers)', ['In-degree', ...D.indeg_bands.map(b => b.band)], [['Papers', ...D.indeg_bands.map(b => n(b.papers))]], [1.3, ...D.indeg_bands.map(() => 1)], D.indeg_bands.map((b, k) => k + 1)),
  P(`The distribution is heavy-tailed. The median in-degree of cited papers is ${CN.in_degree_median_over_cited}, the 90th percentile ${CN.in_degree_quantiles_over_cited[1]} and the maximum ${CN.in_degree_max}. On a log–log plot it is close to a straight line (see the dashboard\'s Citation graph tab).`),
  ...figure(RFIG('R7_in_degree.png'), 'In-degree distribution of the citation network on log–log axes: many papers are cited once or twice inside the corpus, very few more than 20 times.', 480),
  H3('PageRank top 10'),
  ...table('Top 10 papers by PageRank', ['#', 'Paper', 'Inst.', 'Year', 'PageRank', 'In-deg.', 'Cites'],
    CN.top10_pagerank.map((p, k) => [k + 1, `${p.title} (${p.journal})`, SH[p.inst], p.year, p.pagerank.toFixed(4), p.in_degree_in_corpus, p.citations_openalex]), [.35, 4.3, .7, .6, .9, .7, .6], [0, 3, 4, 5, 6], { size: 17 }),
  P('PageRank picks out foundational papers inside each local citation chain, not simply the most-cited ones. Eight of the top 10 are from NITS (stochastic composites, TFET devices, biodiesel catalysts), because NITS has the largest and densest internal citation component (51% of its papers). HITS authorities are dominated by NITS photocatalysis and dye-removal papers (Md. Ahmaruzzaman\'s group), with that group\'s recent reviews as the hubs.'),
  ...figure(RFIG('R8_pagerank_top10.png'), 'Top 10 papers by PageRank, with their in-corpus in-degree and total citations. PageRank rewards being cited by other well-cited papers, so it does not simply follow total citations.'),
  H3('Cross-institute citation flow'),
  ...table('Citation flow between the three institutes (rows cite columns)', ['Citing ↓ / cited →', ...I.map(i => SH[i]), 'Share to own institute'],
    I.map(a => [a, ...I.map(b => n(CN.flow_matrix_source_rows_target_cols[a][b])), CN.per_institute_outgoing_share[a]['to_same_inst_%'] + '%']), [1.8, 1, 1, 1, 1.4], [1, 2, 3, 4]),
  ...figure(FIG('07_citation_flow.png'), 'Citations between our institutes (papers in the corpus only).', 420),
  P(`Only ${n(CN.edges_cross_institute)} of ${n(CN.edges)} links (${(CN.edges_cross_institute / CN.edges * 100).toFixed(1)}%) cross institutes. Most citations inside the corpus are self-citations at the group level: researchers citing their own earlier work.`),
  ...figure(FIG('08_citation_network.png'), 'Citation network: best-connected papers of each institute.', 520),
  ...figure(FIG('17_citation_velocity.png'), 'Citation velocity: citations received per year (left) and citations per paper per year of age by publication cohort (right).'),
);

const FN = D.fac_net, FX = Object.fromEntries(D.fac_net_extra.map(x => [x.scope, x]));
const scopes = ['whole_network', ...I], scopeX = s => s === 'whole_network' ? 'all three institutes' : s;
add(H2('5.2 Faculty co-authorship network'),
  P('**Definition.** Nodes are verified faculty members, with all of a person\'s OpenAlex IDs merged. An undirected edge joins two faculty who co-authored at least one paper in the corpus, weighted by the number of joint papers. Papers with more than 30 authors are left out. Communities were found with Louvain and checked with Leiden.'),
  ...table('Faculty network summary', ['Measure', 'All', ...I.map(i => SH[i])], [
    ['Faculty (nodes) / links', ...scopes.map(s => `${FN[s].nodes} / ${n(FN[s].edges)}`)], ['Isolated faculty', ...scopes.map(s => FN[s].isolated_faculty)],
    ['Density', ...scopes.map(s => FN[s].density)], ['Average collaborators', ...scopes.map(s => FN[s].avg_collaborators)], ['Average clustering', ...scopes.map(s => FN[s].avg_clustering)],
    ['Largest component (%)', ...scopes.map(s => FN[s]['largest_component_%'])], ['Diameter (largest comp.)', ...scopes.map(s => FX[scopeX(s)].diameter_largest_component)],
    ['Average shortest path', ...scopes.map(s => FX[scopeX(s)].avg_shortest_path_largest_component)], ['Degree assortativity', ...scopes.map(s => FX[scopeX(s)].degree_assortativity)],
    ['h-index assortativity', ...scopes.map(s => FX[scopeX(s)].h_index_assortativity)], ['Max k-core (faculty in it)', ...scopes.map(s => `${FX[scopeX(s)].max_k_core} (${FX[scopeX(s)].faculty_in_max_core})`)],
    ['Cross-department links (%)', ...scopes.map(s => FN[s]['cross_department_edges_%'])], ['Louvain communities (modularity)', ...scopes.map(s => `${FN[s].louvain.communities} (${FN[s].louvain.modularity})`)],
    ['Leiden communities (modularity)', ...scopes.map(s => `${FN[s].leiden.communities} (${FN[s].leiden.modularity})`)],
    ['Communities vs departments: NMI / ARI', 'n/a', ...I.map(i => `${FN[i].community_vs_department.NMI} / ${FN[i].community_vs_department.ARI}`)]], [2.6, 1.1, 1.1, 1.1, 1.1], [1, 2, 3, 4]),
  P(`The network is sparse and highly modular. Only ${FN.whole_network.cross_institute_edges} links cross institutes (assortativity by institute ${FN.whole_network.assortativity_by_institute}). Inside an institute, research groups mostly follow departments (assortativity by department ${FN.whole_network.assortativity_by_department}), and NITJ is the most interdisciplinary (lowest NMI). Positive h-index assortativity (${FX['all three institutes'].h_index_assortativity}) means high-h faculty tend to work with other high-h faculty.`),
  ...figure(FIG('09_coauthor_network.png'), 'Faculty co-authorship network coloured by institute: three almost separate clusters joined by a handful of links.', 560),
  ...figure(RFIG('R2_faculty_network.png'), 'The same network coloured by Louvain community (the eight largest; the rest grey). Communities sit inside one institute and mostly inside one department.', 560),
  ...table('Largest Louvain communities', ['Comm.', 'Size', 'Institute', 'Main department (share)', 'Most connected members'],
    D.communities.slice(0, 8).map(c => [`C${c.community}`, c.size, `${SH[c.institute]} (${c['inst_share_%']}%)`, `${c.department} (${c['dept_share_%']}%)`, c.leaders]), [.6, .6, 1.1, 2.4, 2.8], [1], { size: 17 }),
  H3('Brokers and bridges'),
  ...table('Brokers: highest betweenness centrality per institute', ['Institute', 'Faculty', 'Department', 'Betweenness', 'Collaborators', 'h'],
    I.flatMap(i => D.brokers[i].slice(0, 3).map((b, k) => [k ? '' : SH[i], b.faculty_name, b.department, b.betweenness, b.collaborators, b.h_index])), [.8, 1.9, 2.4, 1, 1, .5], [3, 4, 5], { size: 17 }),
  P('Betweenness picks out people who join groups that would otherwise be separate. Some brokers have few collaborators (Vimlesh Kumar Soni, Emon Barua) but sit on the only path between two clusters, so losing them would split the network.'),
  ...table('Bridge authors: co-authorship edges to other Indian institutes', ['Institute', 'Faculty', 'Cross-institute edges', 'Partner institutes', 'Joint papers'],
    I.flatMap(i => D.bridges[i].slice(0, 3).map((b, k) => [k ? '' : SH[i], b.faculty_name, b.cross_institute_edges, b.distinct_indian_partner_institutes, b.joint_papers])), [.8, 2.4, 1.3, 1.3, 1.1], [2, 3, 4]),
  ...figure(FIG('19_bridge_authors.png'), 'Bridge authors: number of different Indian institutes each faculty member co-authored with.'),
);

const IF = D.inflow;
add(H2('5.3 Citation flows with other Indian institutes'),
  P(`Using ${n(HL.citing_works)} papers that cite our papers (incoming) and the reference lists of our papers (outgoing), we count citations exchanged with authors at other Indian institutes. A citation counts as "from another Indian institute" if the citing paper has an author at an Indian institute other than the cited paper's own institute.`),
  ...table('Incoming and outgoing citations with other Indian institutes', ['Measure', ...I.map(i => SH[i])], [
    ['Citations received from other Indian institutes', ...I.map(i => n(S[i].in_cites_from_other_indian))], ['Citations given to other Indian institutes', ...I.map(i => n(S[i].out_cites_to_other_indian))],
    ['Impact ratio (in ÷ out)', ...I.map(i => S[i].in_over_out_ratio)], ['Self-institute citations (%)', ...I.map(i => IF[i]['self_institute_citations_%'])],
    ['Distinct Indian institutes citing us', ...I.map(i => n(IF[i].distinct_indian_institutes_citing))], ['Papers cited by another Indian institute (%)', ...I.map(i => IF[i]['papers_cited_by_another_indian_institute_%'])]], [3, 1.2, 1.2, 1.2], [1, 2, 3]),
  ...figure(FIG('14_citation_ratio.png'), 'In/out citation ratio by year and overall. Early years are low by construction: citations received in 2016 can only go to papers published since 2016.'),
  ...table('Flow by type of institute (share of citations, %)', ['Institute', 'Direction', ...D.flow_cluster['MANIT Bhopal'].incoming.map(r => r.cluster)],
    I.flatMap(i => ['incoming', 'outgoing'].map((d, k) => { const m = Object.fromEntries(D.flow_cluster[i][d].map(r => [r.cluster, r['share_%']])); const cl = D.flow_cluster['MANIT Bhopal'].incoming.map(r => r.cluster); return [k ? '' : SH[i], d === 'incoming' ? 'cited by' : 'cites', ...cl.map(c => m[c] ?? '—')]; })),
    [.8, .9, 1.4, 1, 1, 1], [2, 3, 4, 5]),
  ...figure(FIG('18_flow_by_cluster.png'), 'Citations received from and given to each type of Indian institute.'),
  ...table('Top citing and top cited Indian institutes', ['Institute', 'Who cites us most (citations)', 'Whom we cite most (citations)'],
    I.map(i => [SH[i], D.incoming[i].slice(0, 4).map(r => `${r.citing_inst} (${n(r.citations)})`).join('; '), D.outgoing[i].slice(0, 4).map(r => `${r.cited_inst} (${n(r.citations)})`).join('; ')]), [.7, 3, 3], [], { size: 17 }),
  P('We cite mostly IITs (IIT Roorkee, Delhi, Kharagpur), but are cited mostly by large private universities. Saveetha University is a top-two citer for all three institutes. It has been reported in the press for unusual citation practices, so this result should be read with that in mind.'),
  ...table('Top Indian co-authorship partners (indian_connections.csv, current)', ['Institute', 'Partner', 'Shared papers', 'Citations of shared papers'],
    I.flatMap(i => D.partners[i].map((p, k) => [k ? '' : SH[i], p.partner_inst, p.shared_papers, n(p.total_citations)])), [1, 3.4, 1.1, 1.4], [2, 3]),
  ...figure(RFIG('R16_citers_cited.png'), 'Who cites us most and whom we cite most among other Indian institutes (stacked by our institute).'),
  H3('Indian partner institutes and their type'),
  ...figure(FIG('10_indian_partners.png'), 'Top 10 Indian partner institutes per institute by number of co-authored papers.'),
  ...figure(FIG('11_partner_types.png'), 'Type of Indian partner institute (parent-organisation lookup), as a share of each institute\'s Indian co-authorship links.'),
  ...table('Indian partners by exact type (all three institutes)', ['Partner type', 'Institutes', 'Joint papers', 'They cite our papers', 'Our papers cite them'],
    (() => { const m = {}; I.forEach(i => (D.partner_res[i].cross_cluster || []).forEach(r => { const o = m[r.partner_cluster] || (m[r.partner_cluster] = [0, 0, 0, 0]); o[0] += r.partners; o[1] += r.shared_papers; o[2] += r.cites_from_partner; o[3] += r.cites_to_partner; }));
      return Object.entries(m).sort((a, b) => b[1][1] - a[1][1]).map(([k, v]) => [k, v[0], n(v[1]), n(v[2]), n(v[3])]); })(), [2.2, 1, 1.1, 1.3, 1.3], [1, 2, 3, 4]),
  P('Universities and colleges supply most joint papers and most incoming citations. With IITs, CSIR and DAE labs the flow is one-sided: our papers cite them several times more often than they cite ours. Joint papers with CSIR labs are concentrated at NIT Jamshedpur through the National Metallurgical Laboratory in Jamshedpur.'),
  ...figure(RFIG('R12_partner_types_citations.png'), 'Indian partners by exact type: joint papers, citations they give to our papers, and citations our papers give to them (log scale).'),
  H3('Topic similarity and collaboration'),
  P(`For each institute\'s top 25 partners, OpenAlex gives paper counts per subfield, and the weighted Jaccard index compares the two subfield profiles (0 = no overlap, 1 = identical). Similarity barely predicts how much two institutes publish together (Spearman ρ: ${I.map(i => `${SH[i]} ${D.partner_res[i].similarity_vs_shared_papers_spearman.rho}`).join(', ')}; none significant). Partners are chosen mostly by geography and personal ties, not by topic overlap.`),
  ...figure(RFIG('R13_similarity_vs_collab.png'), 'Research-topic similarity against joint papers for the top partners of each institute.'),
  NOTE('Full partner tables: data/out/indian_connections_detailed.csv (type, citations both ways, topic similarity) and stats/partner_results.json.'),
);

// ---------- 5.4 reach and locality
const LC = D.loc, RCH = Object.fromEntries(LC.collaboration_reach.map(r => [r.institution, r]));
const locShare = (i, l) => (LC.by_locality.find(r => r.your_inst === i && r.locality === l) || {})['share_of_links_%'] || 0;
const clRow = (i, c) => LC.by_cluster.find(r => r.your_inst === i && r.partner_cluster === c) || {};
const peerTop = (i, c, k = 3) => D.peers.filter(r => r.your_inst === i && r.partner_cluster === c).slice(0, k)
  .map(r => `${r.partner_inst.replace('National Institute of Technology', 'NIT').replace('Indian Institute of Technology', 'IIT').replace('Indian Institute of Information Technology', 'IIIT')} (${r.shared_papers}, ${r.locality.toLowerCase()})`).join('; ');
const TW = LC.top_faculty_within_vs_outside;
add(H2('5.4 Collaboration reach and locality'),
  P('This section asks how far our faculty reach beyond their own institute. Do they work with other NITs and IITs that are not in our assignment, with nearby institutes or with distant ones, and which people, institutes and papers matter most inside versus outside each institute? It is computed by locality_reach.py from the final tables, with no OpenAlex calls.'),
  P(`**Method.** Partner institutes come from every co-author\'s affiliation on our ${n(D.headline.papers)} papers. Partner type uses name rules plus a list of known CSIR, DAE, DRDO, ICAR, ISRO and ICMR labs and central universities. Each Indian partner gets a state from a curated list of place names and well-known institutes, which covers ${LC['state_mapping_coverage_%_of_links']}% of partner links. Its region is then compared with the home state (MANIT: Madhya Pradesh, Central; NITJ: Jharkhand, East; NITS: Assam, North-East).`),
  ...table('Collaboration reach of each institute\'s papers', ['Measure', ...I.map(i => SH[i])], [
    ['Papers with another Indian institute', ...I.map(i => RCH[i]['with_other_indian_inst_%'] + '%')], ['Papers with a partner abroad', ...I.map(i => RCH[i]['with_foreign_inst_%'] + '%')],
    ['Papers with one of our other two institutes', ...I.map(i => RCH[i]['with_our_other_two_%'] + '%')], ['Papers with own-institute authors only', ...I.map(i => RCH[i]['own_institute_only_%'] + '%')],
    ['Distinct Indian partner institutes', ...I.map(i => RCH[i].distinct_indian_partners)], ['Distinct foreign partner institutes', ...I.map(i => RCH[i].distinct_foreign_partners)]], [3, 1.2, 1.2, 1.2], [1, 2, 3]),
  ...figure(RFIG('R3_locality_partner_type.png'), 'Locality of Indian partner links (left) and partner type (right).'),
  ...figure(RFIG('R9_institute_network.png'), 'Institute collaboration network. Our three institutes are fixed at the corners; each partner is pulled towards the institutes it co-authors with, so partners shared by two or three of ours sit in the middle. Dashed lines: joint papers between our three.', 600),
  ...table('Locality of Indian partner links (% of joint-paper links)', ['Institute', 'Same state', 'Same region', 'Other region', 'National body', 'Unknown'],
    I.map(i => [i, ...['Same state', 'Same region', 'Other region', 'National body', 'Unknown'].map(l => locShare(i, l))]), [2, 1, 1, 1, 1, 1], [1, 2, 3, 4, 5]),
  P(`Collaboration is mostly **not local**. ${locShare('NIT Silchar', 'Other region')}% of NITS\'s Indian partner links and ${locShare('MANIT Bhopal', 'Other region')}% of MANIT\'s go to institutes outside their region. NITJ is the most local: ${(locShare('NIT Jamshedpur', 'Same state') + locShare('NIT Jamshedpur', 'Same region')).toFixed(1)}% of its links stay in Jharkhand or eastern India, through IIT (ISM) Dhanbad, CSIR-NML Jamshedpur, NIT Patna and NIT Rourkela. MANIT\'s local links are mainly Bhopal neighbours: IIIT Bhopal, IIITDM Jabalpur, RGPV, Barkatullah University, AMPRI and IISER Bhopal. NITS\'s are North-East partners: IIT Guwahati, Mizoram University, NIT Meghalaya, NIT Agartala and Assam University.`),
  H3('Other NITs, IITs, IIITs, IISERs and IISc'),
  ...table('Links with peer institutes outside our group (joint-paper links; top partners with locality)', ['Institute', 'Type', 'Partners', 'Links', 'Top partners (papers, locality)'],
    I.flatMap(i => ['NIT', 'IIT', 'IIIT', 'IISER', 'IISc'].map((c, k) => [k ? '' : SH[i], c, clRow(i, c).partners || 0, clRow(i, c).partner_links || 0, peerTop(i, c)])), [.8, .7, .8, .7, 5], [2, 3], { size: 16 }),
  P(`Peer institutes (other NITs, IITs, IIITs, IISERs and IISc) account for about 30% of Indian partner links at each institute. Each institute has 25–28 NIT partners and 21–22 IIT partners. The strongest peer links are NITS–IIT Guwahati (${(D.peers.find(r => r.your_inst === 'NIT Silchar' && r.partner_inst.includes('Guwahati') && r.partner_cluster === 'IIT') || {}).shared_papers} papers), NITS–NIT Durgapur, MANIT–NIT Raipur and NITJ–IIT (ISM) Dhanbad. They grew fastest after 2020 (see the dashboard\'s Reach & locality tab).`),
  ...figure(RFIG('R11_peer_trend.png'), 'Joint papers with peer institutes outside our group per year. Links with other NITs and IITs grew sharply after 2019.'),
  ...table('Collaboration between our own three institutes', ['Pair', 'Joint papers'], [...Object.entries(LC.between_our_institutes.joint_papers).map(([k, v]) => [k, v]), ['All three on one paper', LC.between_our_institutes.papers_with_all_three],
    ['Faculty co-authorship links across our institutes', LC.between_our_institutes.faculty_links]], [4, 1.2], [1]),
  P(`The three institutes are almost separate: ${Object.values(LC.between_our_institutes.joint_papers).reduce((a, b) => a + b, 0)} joint papers in total and no paper with all three. The strongest cross-institute faculty pair is ${LC.between_our_institutes.faculty_pairs[0].a} (${SH[LC.between_our_institutes.faculty_pairs[0].inst_a]}) and ${LC.between_our_institutes.faculty_pairs[0].b} (${SH[LC.between_our_institutes.faculty_pairs[0].inst_b]}), with ${LC.between_our_institutes.faculty_pairs[0].joint_papers} papers.`),
  ...figure(RFIG('R10_connectedness.png'), 'How connected are the three? Left: Indian partners by which of our institutes work with them (150 work with all three). Right: joint papers, faculty co-authorship links and citations between each pair.'),
  P('So the three institutes are connected mainly indirectly: they share many partners (150 Indian institutes work with all three) and cite each other a few hundred times, but they almost never write papers together.'),
  H3('Highest nodes within and outside the institute'),
  P(`We split each faculty member\'s distinct co-authors into four groups: same institute (faculty only, since students were removed), our other two institutes, elsewhere in India, and abroad. We also built the **full author network**, where every co-author is a node: ${n(LC.full_author_network.nodes)} authors and ${n(LC.full_author_network.edges)} links, ${n(LC.full_author_network.other_indian_nodes)} other-Indian and ${n(LC.full_author_network.foreign_nodes)} foreign authors, Louvain modularity ${LC.full_author_network.louvain_modularity}. We computed approximate betweenness on it.`),
  ...table('Top 5 faculty: most co-authors within vs outside the institute, and top brokers in the full author network', ['Institute', 'Most within (same-inst. co-authors)', 'Most outside (co-authors outside)', 'Top full-network betweenness'],
    I.map(i => [SH[i], TW[i].within.slice(0, 5).map(r => `${r.faculty_name} (${r.coauthors_same_institute})`).join('; '), TW[i].outside.slice(0, 5).map(r => `${r.faculty_name} (${r.coauthors_outside_institute})`).join('; '),
      TW[i].full_network_betweenness.slice(0, 5).map(r => `${r.faculty_name} (${(+r.betweenness_full_network).toFixed(3)})`).join('; ')]), [.7, 2.2, 2.2, 2.2], [], { size: 16 }),
  ...figure(RFIG('R4_within_outside.png'), 'Co-authors within vs outside the institute for every faculty member (log scales; dotted line = equal).', 480),
  P(`The two kinds of node are different people. The internal hubs (Rajesh Purohit, Krishna Murari Pandey, Shashi Bhushan Prasad) anchor department groups. The external hubs (Samuel Lalthazuala Rokhum, ${TW['NIT Silchar'].outside[0].coauthors_outside_institute} outside co-authors; Tikendra Nath Verma; Balram Ambade; Sunil Kumar) have large networks beyond the institute but few internal co-authors. Within and outside counts are only weakly correlated at MANIT and NITJ (Spearman ${LC.within_vs_outside_spearman['MANIT Bhopal']} and ${LC.within_vs_outside_spearman['NIT Jamshedpur']}) and moderately at NITS (${LC.within_vs_outside_spearman['NIT Silchar']}). 76% of faculty have more co-authors outside their institute than inside it.`),
  ...table('Top outside nodes', ['Kind', 'Top nodes'], [
    ['External authors connected to most of our faculty', LC.top_external_authors.slice(0, 6).map(r => `${r.author} (${r.institution}; ${r.faculty_connected} faculty)`).join('; ')],
    ['Indian institutes: most papers with us', LC.institute_network.top_indian_by_papers.slice(0, 6).map(r => `${r.institution} (${r.papers_with_us})`).join('; ')],
    ['Foreign institutes: most papers with us', LC.institute_network.top_foreign_by_papers.slice(0, 6).map(r => `${r.institution} (${r.papers_with_us})`).join('; ')],
    ['Institute network: highest betweenness (excluding ours)', LC.institute_network.top_by_betweenness.slice(0, 6).map(r => r.institution).join('; ')]], [2, 5], [], { size: 17 }),
  ...table('Where citations come from (share of OpenAlex citations)', ['Institute', 'Citations', 'From same institute', 'From our other two', 'From outside the corpus'],
    I.map(i => { const c = LC.citation_origin[i]; return [i, n(c.citations), c['from_same_institute_%'] + '%', c['from_our_other_two_%'] + '%', (100 - c['from_same_institute_%'] - c['from_our_other_two_%']).toFixed(1) + '%']; }), [2, 1.2, 1.3, 1.3, 1.5], [1, 2, 3, 4]),
  P('At the paper level, the papers most cited from inside an institute are mostly follow-up work from the same research group. The papers most cited from outside are the large reviews (for example hydrogen embrittlement, floating PV, ZnO nanomaterials). Both top-10 lists are in the dashboard.'),
  NOTE(`Data note: OpenAlex gives some Indian institutes a wrong or missing country (for example NIT Hamirpur appears as BD). We count them as Indian here, so this analysis finds ${n(LC.by_cluster.reduce((a, r) => a + r.partners, 0))} institute links against ${n(HL.connection_rows)} in indian_connections.csv, which keeps only country = IN. Topic similarity (Jaccard) is available for the top partners only (partners.py).`),
);

// ---------- 6 dashboard
add(H1('6. Interactive dashboard (Deliverable 2)'),
  P('The dashboard is a single-page web app in dashboard/. build_dashboard.py bundles the final CSV and JSON files into dashboard/data.js (about 6 MB). index.html and app.js draw the charts with Plotly.js and the two network graphs with D3.js force layouts. Both libraries are stored in dashboard/vendor/, so it works offline and needs no server.'),
  H3('How to run'),
  NUM('python build_dashboard.py   (rebuild data.js after any pipeline rerun)'),
  NUM('Open dashboard/index.html in Chrome, Edge or Firefox.'),
  P('Deep links open a specific view, for example index.html#collab?f=4 (a faculty member in the network) or #citnet?p=10197 (a paper in the citation graph).'),
  ...table('Required panels and where they are', ['Required panel (Deliverable 2)', 'Implementation'], [
    ['1. Publication trend chart', 'Overview and Publications tabs: line chart by institute (2026 dashed as partial) or stacked journal/conference bars. Clicking a point opens that year\'s papers.'],
    ['2. Journal quartile distribution', 'Stacked 100% bars or donuts per institute, Q1 share by year, and conference venue rank (Scopus quartile plus CORE). Clicking a segment filters the paper explorer.'],
    ['3. Faculty performance table', 'Faculty tab: sortable and searchable table of all ' + n(HL.faculty_with_papers) + ' faculty (name, department, h-index, papers, citations, Q1 %, Q1 papers, top-journal papers, collaborators) with department, status and h-band filters.'],
    ['4. Top journals and most-cited papers', 'Top 5 (and up to 10) journals per institute. Top 10 most-cited papers with DOI links. Top-30 deep-dive table with quartile, IF flags and best-author h.'],
    ['5. Research area breakdown', 'Field bar chart and a field-impact bubble chart (papers against mean citations). Clicking a field lists its papers.'],
    ['6a. Directed citation graph', 'D3 force graph of the top-N papers by PageRank (50–2,000), with filters for rank (Q1–Q4), Q1 & IF > 5 / > 10, CORE rank, field, Indian citation links, papers with > 10 authors, minimum in-degree, links within or between institutes, and views for the largest component, small clusters or a paper\'s 1- or 2-hop ego network. Node size = PageRank, in-degree, citations or betweenness. Colour = institute, field, quartile or year. Arrows show direction.'],
    ['Extra: Reach & locality tab', 'Locality of partner links (same state / region / other), partner-type Sankey, region and state bars, peer NITs/IITs/IIITs/IISERs table, links between our three, within-vs-outside scatter, highest nodes within / outside / full-network brokers, top outside authors and institutes, citation origin, full partner explorer. Clicking a partner opens its joint papers and faculty.'],
    ['Extra: institute network and connectedness', 'Reach tab: network of our three institutes and their partner institutes (filter by partner type, minimum joint papers; colour by type, distance or sharing), and a panel on how connected the three are (joint papers, faculty links, citations, shared partners, topic similarity).'],
    ['Extra: year range', 'A global year range (both ends included) filters every chart built from paper records; panels with whole-period figures are labelled.'],
    ['6b. Co-authorship graph', 'D3 force graph of the faculty network, coloured by Louvain community (or institute, department, k-core), sized by collaborators, h-index, betweenness, papers or eigenvector. Filter by minimum joint papers.']], [2, 5]),
  H3('Interactions'),
  B('**Global institute switch and year range** (All / MANIT / NITJ / NITS; from–to years) filter every panel. Colours are fixed per institute.'),
  B('**Global search** ("/" shortcut) over faculty names and all ' + n(HL.papers) + ' paper titles.'),
  B('**Faculty profile drawer**, opened from any name, table row, leaderboard bar or network node. It shows rank within the institute, journal/conference split, quartile mix, papers per year, all network metrics (degree, strength, betweenness, closeness, eigenvector, k-core, community), clickable collaborators and the full paper list with DOIs.'),
  B('**Paper drawer**, opened from any paper. It shows faculty authors (clickable), PageRank rank, in- and out-degree, in-degree h-index, and the in-corpus papers it cites and that cite it.'),
  B('**Network focus.** "Show in collaboration network" zooms to a person\'s ego network and dims the rest. "Show in citation graph" pulls a paper\'s neighbours into the graph. Clicking a community in the legend or table highlights it.'),
  B('**Chart → data.** Clicking any trend point, quartile segment, field, journal or department filters the Paper explorer or the faculty table.'),
  B('Light and dark themes; responsive layout down to phone width.'),
  ...figure(SHOT('overview.png'), 'Dashboard overview: key findings, KPI tiles, trend and quartile share.'),
  ...figure(SHOT('fac_drawer.png'), 'Clicking a node opens the faculty profile and highlights that person\'s ego network.'),
  ...figure(SHOT('collab.png'), 'Collaboration network tab, coloured by Louvain community.'),
  ...figure(SHOT('paper_drawer.png'), 'Citation graph with a paper\'s in-corpus neighbours highlighted, and its paper panel.'),
  ...figure(SHOT('faculty.png'), 'Faculty tab: h-index distribution, leaderboard and the sortable performance table.'),
  ...figure(SHOT('reach.png'), 'Reach & locality tab: collaboration KPIs and the institute collaboration network.'),
  ...figure(SHOT('citnet.png'), 'Citation graph with its filter panel (rank, impact, CORE, field, Indian links, team size, view and display options).'),
  ...figure(SHOT('pubs.png'), 'Publications tab: annual output, Q1 share by year, journal quartiles and conference papers by venue rank.'),
);

// ---------- 7 reproducibility
add(H1('7. Reproducibility', false),
  P('Everything is scripted. run_all.sh runs the steps in order from a chosen starting step, checks that every input exists before changing any file, fixes the hash seed so reruns are identical, and ends with validate.py.'),
  ...table('Pipeline steps (run_all.sh)', ['Step', 'Scripts', 'Output'], [
    ['fetch', 'fetch.py', 'Raw OpenAlex works (data/raw/)'], ['build', 'build_tables.py', 'papers.csv, authorships.csv, authors.csv'],
    ['enrich', 'enrich.py', 'Quartiles from SJR, fields, venue metrics; group15_data.csv'], ['quartiles', 'scopus_quartiles.py', 'Scopus CiteScore quartiles for proceedings'],
    ['faculty', 'faculty_match.py, author_resolution.py, corpus_filter.py', 'Verified faculty, author roles, faculty-only corpus'],
    ['networks', 'networks.py', 'citation_network.csv, authorship_network.csv, indian_connections.csv'], ['outflow / inflow', 'outflow.py, inflow.py (links.py downloads)', 'Citations to / from other Indian institutes'],
    ['partners', 'partners.py', 'Partner types and topic similarity'], ['facstats', 'faculty_stats.py, faculty_network.py, extras.py, deep_analysis.py, extra_metrics.py', 'Faculty tables, faculty network, top-30, bridges, citation metrics'],
    ['report', 'stats.py, plots.py, audit_summary.py', 'stats/*.csv, figures 01–19, AUDIT_SUMMARY.md']], [1, 3, 3]),
  P('This report and the dashboard are built on top of those outputs:'),
  B('python build_dashboard.py → dashboard/data.js'),
  B('python locality_reach.py → data/out/stats/locality/ (reach, locality, institute network)'),
  B('python report/report_data.py → report/report_data.json; python report/report_figures.py and report/report_figures_extra.py → report/figures/R1–R16; node report/build_report.js → this document'),
);

// ---------- 8 limitations
add(H1('8. Limitations', false),
  B('**Affiliation-based counting.** A paper counts for an institute if a verified faculty member lists it. Visiting or adjunct authors who print the affiliation but are not faculty are excluded. Faculty who publish under another affiliation are missed.'),
  B('**Faculty matching precision is about 90%.** Common Indian names make author disambiguation hard. Wrong matches mostly add a few papers to the wrong person and rarely change institute totals.'),
  B(`**Estimated quartiles.** ${n(HL.estimated_rows)} rows (${HL.estimated_pct}%), mostly conference papers, have estimated rather than official quartiles. IF > 5 / > 10 use SCImago citations per document, not Clarivate JIF.`),
  B('**Truncation.** 2026 is partial, and recent papers have had less time to be cited. Compare citation measures across years only with that in mind.'),
  B('**Corpus-internal citation network.** It only sees citations between our own papers, so in-degree and PageRank measure influence inside the three institutes, not field-wide influence.'),
  B('**Co-authorship network scope.** Only faculty-to-faculty links among the three institutes are nodes. Collaboration with outside partners appears through bridge-author counts, not as nodes.'),
  B('**OpenAlex coverage.** About 85% of Scopus records are found (Section 3.8). The rest are mostly book chapters, which are excluded by design.'),
  B('**Locality** uses a curated state list (93% of links mapped) and treats multi-site bodies (CSIR HQ, DRDO, AcSIR) as national. OpenAlex country codes are sometimes wrong (NIT Hamirpur = BD), which also affects indian_connections.csv.'),
  B(`**Deduplication.** ${HL.dup_title_pairs} pairs of papers share a title and year under two DOIs (journal plus early-access copy, mostly Inderscience). They are kept as separate OpenAlex records; the specification asks for dedup by normalised title + year, so they should be merged in the next pipeline run.`),
  B('**Figures 04 and 09** in data/out/figures now use the verified faculty (h-index histogram and faculty co-authorship network), the same population as everything else in this report.'),
);

// ---------- 9 pending
add(H1('9. Open items and next steps', false),
  ...table('Open items', ['Item', 'Action', 'Affects'], [
    ['Top 10 most-cited papers citing our institutes', 'Needs the citation counts of the citing papers (one more OpenAlex lookup, then inflow.py)', 'Section 5.3 (work-plan item)'],
    [`Title + year dedup (${HL.dup_title_pairs} pairs)`, 'Merge early-access duplicates in build_tables.py or corpus_filter.py', 'All counts (< 0.6%)'],
    ['Jaccard for all partners', 'partners.py computes it for the top partners only; extend with more lookups', 'Sections 5.3–5.4'],
    ], [2, 2.6, 2.6]),
  P('Points the team may want to add: a short related-work paragraph, the Jaccard topic-similarity results from partners.py, and a ≤5-page cut of Sections 4–5 for the formal statistics report (the slide plan is in Section 4).'),
);

// ---------- appendix
add(H1('Appendix A. Metric definitions'),
  ...table(null, ['Metric', 'Definition'], [
    ['h-index (faculty / institute)', 'Largest h such that h papers in the corpus (2016–26) have at least h citations each.'],
    ['Q1 share', 'Q1 journal papers ÷ journal papers with a quartile.'],
    ['IF > 5 / IF > 10', 'Q1 journal whose SCImago citations per document (2 years) is above 5 / 10.'],
    ['In-degree / out-degree', 'Citations received from / given to other papers in the corpus.'],
    ['PageRank', 'Stationary probability of a random walk on the citation graph (damping 0.85); high for papers cited by other well-cited papers.'],
    ['HITS authority / hub', 'Authority: cited by good hubs. Hub: cites good authorities.'],
    ['In-degree h-index', 'For a paper: largest h such that h of its citing corpus papers each have in-degree ≥ h.'],
    ['Degree / strength', 'Number of faculty collaborators / number of joint papers with them.'],
    ['Betweenness', 'Share of shortest paths between other faculty that pass through a person (normalised).'],
    ['Closeness / eigenvector', 'Inverse mean distance to others / influence from being connected to well-connected people.'],
    ['k-core', 'Largest k such that the person is in a subgraph where everyone has at least k collaborators.'],
    ['Modularity (Louvain, Leiden)', 'Fraction of links inside communities minus the expected fraction; above 0.7 means very strong community structure.'],
    ['NMI / ARI', 'Agreement between communities and departments (1 = identical, 0 = unrelated).'],
    ['Assortativity', 'Correlation of a property (degree, h-index, department, institute) across linked pairs.'],
    ['Impact ratio', 'Citations received from other Indian institutes ÷ citations given to them.'],
    ['Gini', 'Inequality of papers or citations across faculty (0 = equal, 1 = one person has everything).']], [2, 5]),
  H1('Appendix B. Output files', false),
  ...table(null, ['File', 'Content'], [
    ['data/out/group15_data.csv', 'Main dataset (one row per paper × faculty author × institute)'], ['data/out/citation_network.csv', 'Directed citation edges between corpus papers'],
    ['data/out/authorship_network.csv', 'Co-author pairs per paper'], ['data/out/indian_connections.csv', 'Co-authorship with other Indian institutes'],
    ['data/out/faculty_network_nodes.csv / _edges.csv', 'Faculty co-authorship network'], ['data/out/stats/institution_summary.csv', 'Institute scorecard'],
    ['data/out/stats/faculty_ranking_<institute>.csv', 'Faculty leaderboard with network metrics'], ['data/out/stats/top30_papers_<institute>.csv', 'Top-30 deep dive'],
    ['data/out/stats/citation_node_metrics.csv', 'Per-paper in/out-degree, PageRank, HITS, in-degree h'], ['data/out/stats/faculty_node_metrics.csv', 'Per-faculty degree, strength, betweenness, closeness, eigenvector, k-core'],
    ['data/out/stats/*.json', 'All summary numbers used in this report'], ['data/out/stats/locality/*.csv', 'Partner locality, institute network, within/outside metrics'], ['data/out/figures/*.png', 'Figures 01–19'], ['report/figures/*.png', 'Report figures R1–R16'],
    ['dashboard/', 'Interactive dashboard (index.html, app.js, data.js, vendor/)']], [3, 4]),
);

add(H1('Appendix C. Compliance with the instruction note'),
  ...table(null, ['Requirement (instruction note / work plan)', 'Status', 'Where'], [
    ['group15_data.csv with the 14 required columns, 2016–2026, all 3 institutes', 'Done', '§3.6'],
    ['Faculty list, incl. ex-faculty by historical affiliation; non-faculty removed', 'Done', '§3.2–3.3'],
    ['Journal quartile (SCImago) and CORE conference rank', 'Done', '§3.4, Table 11'],
    ['Papers with > 10 authors flagged (is_multi_author_10plus)', 'Done', '§3.5, §4.4'],
    ['DOIs in https://doi.org/ form; dedup by DOI', 'Done', '§3.1'],
    ['Dedup by normalised title + year', `Partial: ${HL.dup_title_pairs} pairs kept`, '§8'],
    ['citation_network.csv (source_doi, target_doi, source_inst, target_inst, year)', 'Done', '§3.6'],
    ['authorship_network.csv (author_a, author_b, paper_doi, inst_a, inst_b, year)', 'Done', '§3.6'],
    ['indian_connections.csv (your_inst, partner_inst, shared_papers, total_citations)', 'Done', '§3.6'],
    ['Citation network: in-degree, PageRank top 10, cross-institute flow', 'Done', '§5.1'],
    ['Authorship network: degree, betweenness, Louvain/Leiden', 'Done', '§5.2'],
    ['Citation flow: in, out, ratio, top 10 citing institutes, year-wise chart', 'Done', '§5.3'],
    ['Top 10 most-cited papers citing our institutes', 'Pending (citing file)', '§9'],
    ['Connectivity: every partner, ranked, joint-paper strength', 'Done', '§5.3–5.4'],
    ['Cross-cluster links flagged (IIT ↔ CSIR etc.)', 'Done (parent-organisation lookup)', '§5.3–5.4'],
    ['Jaccard topic similarity with partners', 'Partial (top partners)', '§5.4, §9'],
    ['Hub authors bridging institutes', 'Done', '§5.2, §5.4'],
    ['Locality: nearby vs distant partners; other NITs / IITs', 'Done', '§5.4'],
    ['Highest nodes within vs outside each institute', 'Done', '§5.4'],
    ['Statistics report ≤ 10 slides / 5 pages', 'Done (separate file)', 'Group15_Statistics_Report.docx'],
    ['Dashboard: all required panels + citation and co-authorship graphs', 'Done', '§6']], [4.6, 1.6, 1.3]),
);

// ------------------------------------------------------------------ document
const doc = new Document({
  creator: 'Group 15', title: 'Group 15 DPCN Assignment 2 Report', description: 'Research output and collaboration networks of three NITs',
  styles: {
    default: { document: { run: { font: FONT, size: BODY } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 34, bold: true, color: ACCENT, font: FONT }, paragraph: { spacing: { before: 120, after: 200 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 27, bold: true, color: ACCENT, font: FONT }, paragraph: { spacing: { before: 300, after: 120 }, outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 23, bold: true, color: '262626', font: FONT }, paragraph: { spacing: { before: 220, after: 80 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } },
      { level: 1, format: LevelFormat.BULLET, text: '–', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1000, hanging: 270 } } } }] },
    { reference: 'num', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  features: { updateFields: true },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1300, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'DPCN Assignment 2 · Group 15', size: 16, color: '8C8C8C' })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ['Page ', PageNumber.CURRENT, ' of ', PageNumber.TOTAL_PAGES], size: 16, color: '8C8C8C' })] })] }) },
    children: C,
  }],
});
const out = path.join(R, process.env.REPORT_OUT || 'Group15_DPCN_Report.docx');
Packer.toBuffer(doc).then(b => { fs.writeFileSync(out, b); console.log('wrote', out, (b.length / 1e6).toFixed(1) + ' MB', `${tabNo} tables, ${figNo} figures`); });
