"""Deterministic answer writer: turns tool results into the standard five-part answer without an LLM.

Direct answer / Supporting evidence / Network interpretation / Limitations (the figure and references are shown by the UI).
Every number comes straight from the tool result, so these answers are grounded by construction. With an LLM key the same
tool results are given to the model instead (llm.py) and the text is checked by grounding.py.
"""

def _fmt(v):
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:,.0f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def _bul(items):
    return "\n".join(f"- {i}" for i in items)


def render(result):
    """Markdown for one tool result."""
    t, d = result["tool"], result["data"]
    if not result["ok"]:
        return f"**{result['summary']}**\n\n{result.get('coverage', '')}"
    fn = FORMATTERS.get(t)
    direct, evidence, interp = fn(d, result) if fn else (result["summary"], [f"{k}: {_fmt(v)}" for k, v in list(d.items())[:8] if not isinstance(v, (dict, list))], [])
    parts = [f"**Direct answer.** {direct}"]
    if evidence:
        parts.append("**Supporting evidence**\n" + _bul(evidence))
    if interp:
        parts.append("**Network interpretation**\n" + _bul(interp))
    if result.get("coverage"):
        parts.append(f"**Limitations.** {result['coverage']}")
    return "\n\n".join(parts)


def _partner(d, r):
    if "by_our_institute" in d:
        ev = [f"{b['institute']}: {b['partner_institutes']} {d['type']} partner institutes, {b['joint_paper_links']} joint-paper links; top: " +
              ", ".join(f"{p['partner']} ({p['joint_papers']})" for p in b["top_partners"][:3]) for b in d["by_our_institute"]]
        best = max(d["by_our_institute"], key=lambda b: b["joint_paper_links"])
        if d.get("people"):
            ev.append(f"Most frequent {d['type']} co-authors: " + "; ".join(f"{x['name']} ({x['institute']}, {x['joint_papers']} paper(s), with {', '.join(x['worked_with'][:2])})" for x in d["people"][:6]))
        return f"{best['institute']} has the most {d['type']} joint-paper links ({best['joint_paper_links']}). " + r["summary"] + ".", ev, ["Open the Reach tab for the full partner list, locality and year trends."]
    links = d.get("links", [])
    if not links:
        return r["summary"], [], []
    ev = [f"{x['your_inst']}: {x['shared_papers']} joint paper(s)" + (f", {x['first_year']}-{x['last_year']}" if x.get("first_year") else "") +
          (f", {x['faculty_involved']} faculty involved (e.g. {x['top_faculty']})" if x.get("top_faculty") else "") +
          (f"; {d['partner']} cites {x['your_inst']} {x['cites_from_partner']} times, {x['your_inst']} cites {d['partner']} {x['cites_to_partner']} times" if x.get("cites_from_partner") is not None else "") for x in links]
    ppl = d.get("people", [])
    if ppl:
        ev.append(f"{d['partner']} co-authors named in the data: " + "; ".join(f"{x['name']} ({x['joint_papers']} paper(s), {x['years']}, with {', '.join(x['worked_with'][:2])})" for x in ppl[:8]))
    return f"Yes. {d['partner']} has joint papers with {len(links)} of the three institutes ({', '.join(x['your_inst'] for x in links)}).", ev, ["More detail (year trend, partner profile, citation direction) is in the dashboard; see the links below."]


def _experts(d, r):
    rows = d["faculty"]
    direct = (f"{d['papers_matched']} paper(s) in the corpus match '{d['topic']}'. The faculty with the most papers on it: " +
              "; ".join(f"**{x['name']}** ({x['institution']}, {x['department']}): {x['relevant_papers']} paper(s), {x['citations_on_these_papers']} citations" for x in rows[:3]) + ".")
    ev = [f"{x['name']} ({x['institution']}): {x['relevant_papers']} relevant paper(s), {x['first_year']}-{x['latest_year']}, {x['recent_papers_2022_on']} since 2022, e.g. {x['example_papers'][0]}" for x in rows[:6]]
    ev.append("Relevant papers by the institute: " + ", ".join(f"{k} {v}" for k, v in d["papers_by_our_institute"].items()) + f". Terms searched: {', '.join(d['terms_searched'])}.")
    return direct, ev, ["Ranked by output on the topic, not by overall quality. Approach people whose recent papers (last column above) match your sub-area."]


def _place_impact(d, r):
    ev = [f"Highest: {x['place']}: mean FWCI {x['mean_fwci']} (median {x['median_fwci']}), {x['papers']} papers" for x in d["highest"]]
    ev += [f"Lowest: {x['place']}: mean FWCI {x['mean_fwci']} (median {x['median_fwci']}), {x['papers']} papers" for x in d["lowest"]]
    return (f"For {d['scope']}, papers average FWCI {d['baseline_mean_fwci']} (median {d['baseline_median_fwci']}). {d['places_above_average']} of {d['places_listed']} partner places have a higher mean than that. "
            f"Highest: " + "; ".join(f"**{x['place']}** {x['mean_fwci']}" for x in d["highest"][:3]) + ". Lowest: " + "; ".join(f"{x['place']} {x['mean_fwci']}" for x in d["lowest"][:3]) + "."), ev, ["This is an association, not proof that the partner place causes the difference."]


def _give_take(d, r):
    ev, direct = [], ""
    for i, g in d["by_institute"].items():
        pv = g["private_universities"]
        direct += f"**{i}**: received {g['citations_received']:,} citations from other Indian institutes and gave {g['citations_given']:,}. Private universities (named list) cite {i} {pv['cites_us']:,} times and {i} cites them {pv['we_cite']:,} times. "
        ev.append(f"{i}: institutes that cite {i} far more than {i} cites them: " + "; ".join(f"{x['institute']} ({x['cites_us']:,} vs {x['we_cite']:,})" for x in g["cite_us_much_more_than_we_cite_them"][:4]))
        ev.append(f"{i}: institutes that {i} cites far more than they cite {i}: " + "; ".join(f"{x['institute']} ({x['we_cite']:,} vs {x['cites_us']:,})" for x in g["we_cite_much_more_than_they_cite_us"][:4]))
    return direct.strip(), ev, ["Private-university grouping is approximate (matched by name)."]


def _why(d, r):
    y = d["yearly_papers"]
    yrs = sorted(y)
    ev = [f"{yr}: " + ", ".join(f"{k.split()[0] if k.startswith('NIT') is False else k} {v}" for k, v in y[yr].items()) + f" (most: {d['yearly_leader'][yr]})" for yr in yrs[-4:]]
    for inst, c in (d.get("institute_context_nirf") or {}).items():
        ev.append(f"{inst} (NIRF-reported, outside the publication data): " + "; ".join(c["facts"]))
    return d["findings"][0], ev, d["findings"][1:] + ["NIRF figures are as reported in submissions and are not complete for every institute; they give context, not proof of cause. Not available: " + "; ".join(d["not_in_dataset"]) + "."]


def _assess(d, r):
    a, b = d["a"], d["b"]
    direct = f"{a['name']} ({a['institution']}, {a['department']}) and {b['name']} ({b['institution']}, {b['department']}): **{d['relationship']}**."
    ev = []
    if d["joint_papers"]:
        ev.append(f"{d['joint_papers']} joint paper(s), e.g. " + "; ".join(f"{p['title']} ({p['year']})" for p in d["joint_paper_list"][:3]))
    else:
        ev.append("No joint paper in the 2016-2026 corpus of verified faculty.")
    if d["shortest_path"]:
        ev.append(f"Shortest collaboration path: {d['shortest_path_hops']} hop(s): " + " -> ".join(d["shortest_path"]))
    else:
        ev.append("No collaboration path exists between them in the verified-faculty network.")
    cc = d["common_collaborators"]
    ev.append(f"{len(cc)} common collaborator(s)" + (": " + ", ".join(f"{c['name']} ({c['joint_with_a']} / {c['joint_with_b']} joint papers)" for c in cc[:5]) if cc else ""))
    t = d.get("research_topic_similarity")
    if t:
        ev.append(f"Research-topic similarity (OpenAlex subfields): cosine {_fmt(t['topic_cosine'])}, weighted Jaccard {_fmt(t['topic_weighted_jaccard'])}, {t['shared_subfields']} shared subfield(s); main overlaps: " + ", ".join(t["top_shared_subfields"][:3]))
    ev.append(f"Same department: {'yes' if d['same_department'] else 'no'}; same institute: {'yes' if d['same_institute'] else 'no'}.")
    ev.append(f"Network similarity: Jaccard of collaborator sets {_fmt(d['network_similarity']['jaccard_of_collaborators'])}, Adamic-Adar {_fmt(d['network_similarity']['adamic_adar'])}.")
    m = d.get("model")
    if m:
        top = ", ".join(f"{f} ({'+' if c > 0 else ''}{c})" for f, c in m["feature_contributions_logistic"][:4])
        ev.append(f"Link-prediction ranking scores (not probabilities): logistic {_fmt(m['score_logistic'])}, random forest {_fmt(m['score_random_forest'])}. Strongest logistic contributions: {top}.")
    interp = []
    if d["shortest_path_hops"] == 2:
        interp.append("Two hops means they share at least one collaborator, a classic precondition for new collaborations (triadic closure).")
    elif d["shortest_path_hops"] and d["shortest_path_hops"] > 3:
        interp.append("A long path means they sit in different parts of the network; any collaboration would bridge distant groups.")
    if not d["joint_papers"] and t and t["topic_cosine"] >= 0.5:
        interp.append("Their publication topics overlap substantially, which supports research compatibility; this is evidence of compatibility, not a prediction.")
    elif not d["joint_papers"] and t and t["topic_cosine"] < 0.2:
        interp.append("Their topic profiles overlap little at subfield level, so compatibility would rest on complementary rather than shared interests.")
    return direct, ev, interp


def _recommend(d, r):
    s = d["suggestions"]
    direct = f"{len(s)} suggested collaborator(s) (no previous joint paper), ranked by {d['basis']}."
    ev = [f"**{x['name']}** ({x['institution']}, {x['department']}): rank score {_fmt(x['rank_score'])}, path {x['hops']} hop(s), topic cosine {_fmt(x['topic_cosine'])}; shared subfields: {', '.join(x['shared_subfields'][:3]) or 'none'}"
          + (f"; common collaborators: {', '.join(x['common_collaborators'][:3])}" if x["common_collaborators"] else "") for x in s]
    return direct, ev, ["Scores rank candidates against each other; they do not say a collaboration will happen."]


def _compare_inst(d, r):
    t = d["table"]
    best = lambda k, hi=True: max(t, key=lambda x: x[k] if hi else -x[k])
    direct = ("No single winner: " + f"{best('papers')['institution']} has the most papers, {best('papers_per_active_faculty')['institution']} the most papers per research-active faculty, "
              f"{best('citations_per_paper')['institution']} the most citations per paper, {best('journal_Q1_share_%')['institution']} the highest Q1 share of ranked journals.")
    ev = [f"{x['institution']}: {_fmt(x['papers'])} papers, {_fmt(x['research_active_faculty'])} active faculty ({_fmt(x['papers_per_active_faculty'])} per faculty), {_fmt(x['citations_per_paper'])} citations/paper "
          f"(median {_fmt(x['median_citations_per_paper'])}), institute h-index {x['institute_h_index']}, Q1 {_fmt(x['journal_Q1_share_%'])}% ({x['journal_Q1_papers']}/{x['journal_ranked_papers']}), FWCI {_fmt(x.get('fwci_mean'))}"
          f", growth 2016-20 to 2021-25 {_fmt(x['growth_2016_2020_to_2021_2025_%'])}%" for x in t]
    h = d.get("h_index_at_equal_size")
    interp = []
    if h:
        interp.append("At equal size (same number of papers drawn from each institute): " + "; ".join(f"{i} h-index {v['mean_h_at_equal_size']} (observed {v['observed_h']})" for i, v in h.items()))
    return direct, ev, interp


def _top_faculty(d, r):
    rows = d["rows"]
    extra = [c for c in rows[0] if c not in ("name", "institution", "department", "papers", "citations")] if rows else []
    k = extra[0] if extra else (d.get("metric") or r.get("data", {}).get("metric") or "citations")
    return f"Top {len(rows)} by {k}: " + ", ".join(f"{x['name']} ({_fmt(x[k])})" for x in rows[:5]) + ("..." if len(rows) > 5 else ""), [f"{x['name']} - {x['institution']}, {x['department']}: {k} {_fmt(x[k])}, {x['papers']} papers, {x['citations']} citations" for x in rows], []


def _pattern(d, r):
    return r["summary"], [f"{x['name']} ({x['institution']}): degree {x['degree']}, betweenness {_fmt(x['betweenness'])}, {x['papers']} papers, {x['citations']} citations" for x in d["rows"]], [f"Thresholds were computed over {d['thresholds_computed_over']}."]


def _resilience(d, r):
    s = d["summary"]
    direct = (f"The {d['scope']} faculty network ({d['nodes']} faculty, {d['edges']} links, {d['isolated']} isolated) is robust to random loss but fragile under targeted loss: "
              f"half of the network is lost after removing {_fmt(s['random']['collapse_at'] * 100) if s['random']['collapse_at'] else '>40'}% at random, but only "
              f"{_fmt(s['betweenness']['collapse_at'] * 100)}% by highest betweenness ({_fmt(s['betweenness_adaptive']['collapse_at'] * 100)}% when betweenness is recomputed).")
    ev = [f"Robustness R20 (mean largest-component fraction over 0-20% removal): random {_fmt(s['random']['R20'])}, degree {_fmt(s['degree']['R20'])}, betweenness {_fmt(s['betweenness']['R20'])}, adaptive {_fmt(s['betweenness_adaptive']['R20'])}.",
          f"Fragility index (1 - R20 targeted / R20 random): degree {_fmt(s['degree']['fragility_index'])}, betweenness {_fmt(s['betweenness']['fragility_index'])}."]
    ev += [f"Single removal of {x['faculty_name']} ({x['institution']}): efficiency loss {_fmt(x['efficiency_loss_%'])}%, largest component change {_fmt(x['lcc_change_pp'])} pp" + (", articulation point" if x["articulation_point"] else "") for x in d["most_critical_single_removals"][:4]]
    return direct, ev, ["A structural simulation: removing a node does not mean a faculty member leaves the institute."]


def _removal(d, r):
    b, a = d["before"], d["after"]
    return (r["summary"], [f"Components {b['components']} -> {a['components']}; global efficiency {_fmt(b['global_efficiency'])} -> {_fmt(a['global_efficiency'])}"], ["Structural simulation only."])


def _network(d, r):
    s = d["summary"] or {}
    st = d.get("structure") or {}
    return (f"{s.get('nodes')} faculty, {s.get('edges')} links, {s.get('isolated_faculty')} without links; largest component {s.get('largest_component_%')}% of faculty.",
            [f"Average collaborators {s.get('avg_collaborators')}, clustering {s.get('avg_clustering')}, density {s.get('density')}",
             f"Diameter {st.get('diameter_largest_component')}, average path {st.get('avg_shortest_path_largest_component')}; degree assortativity {st.get('degree_assortativity')}, h-index assortativity {st.get('h_index_assortativity')}",
             f"Louvain communities {s.get('louvain', {}).get('communities')} (modularity {s.get('louvain', {}).get('modularity')}), Leiden {s.get('leiden', {}).get('communities')}"], [])


def _flows(d, r):
    a = d.get("answer")
    if a:
        return (f"{a['from']} -> {a['to']}: {a['citations']} citations ({a['share_of_a_citations_%']}% of {a['from']}'s citations); reverse {a['reverse']['from']} -> {a['reverse']['to']}: {a['reverse']['citations']} ({a['reverse']['share_%']}%).",
                [f"Convention: {d['convention']}"], [])
    return ("Citation flows between the three NITs (row = citing, column = cited).", [f"{i}: " + ", ".join(f"{j} {v}" for j, v in row.items()) for i, row in d["counts_row_citing_column_cited"].items()] + [d["note"]], [])


def _paper(d, r):
    ev = [f"{d['citations_worldwide']} citations worldwide (OpenAlex); FWCI {d.get('fwci')}; {d['type']} in {d['venue']} ({d['quartile']}); field {d['field']}",
          f"Within the corpus: cited by {d['corpus_in_degree']} paper(s), cites {d['corpus_out_degree']}; PageRank rank within its publication year {d['pagerank_rank_within_publication_year']}",
          "Faculty authors: " + ", ".join(f"{x['name']} ({x['institution']})" for x in d["faculty_authors"])]
    k = d["in_corpus_citations_by_kind"]
    if all(v is not None for v in k.values()):
        ev.append(f"In-corpus citing links: {k['author_self']} author self-citations, {k['same_institute_other_author']} same institute other authors, {k['between_our_institutes']} between the three institutes")
    return r["summary"], ev, []


def _pagerank(d, r):
    return (f"{r['summary']}. {d.get('self_citation_share_of_in_corpus_%')}% of its in-corpus citations are author self-citations.", [f"{d['in_corpus_citations_by_kind']}", d["explanation_inputs"]], [])


def _institute_collab(d, r):
    if "existing_links_to_faculty_there" in d:
        return (r["summary"], [f"{x['name']}: {x['joint_papers']} joint paper(s)" for x in d["existing_links_to_faculty_there"]] + [f"Suggested: {s['name']} ({s['department']}) path {s['hops']} hop(s)" for s in d["suggested_collaborators_there"]], [])
    ev = [f"Existing joint papers with this researcher: {d['existing_joint_papers_with_this_researcher']}"]
    ev += [f"{x['your_inst']} <-> {d['institute']}: {x['shared_papers']} joint paper(s), {x['total_citations']} citations, {x['first_year']}-{x['last_year']}, faculty: {x['top_faculty']}; topic similarity {x['weighted_jaccard'] if x['weighted_jaccard'] is not None else 'not calculated'}" for x in d["institute_level_links_with_our_institutes"]]
    return r["summary"], ev, []


def _profile(d, r):
    ev = [f"{d['papers']} papers ({d['journal_papers']} journal / {d['conference_papers']} conference), {d['citations']} citations, {d['citations_per_paper']} per paper; 2016-2026 h-index {d['h_index_2016_2026']}; Q1 share {d['q1_share_%']}%",
          f"Top journals: {', '.join(d['top_journals']) or 'none'}; most used conference or series: {', '.join(d['top_conferences_or_series']) or 'none'}",
          f"Network: {d['collaborators_in_faculty_network']} collaborators, betweenness {_fmt(d['betweenness'])}, k-core {d['k_core']}, community {d['community_leiden']}",
          "Top collaborators: " + ", ".join(f"{c['name']} ({c['joint_papers']})" for c in d["top_collaborators"][:5])]
    return r["summary"], ev, []


def _explain(d, r):
    return d.get("definition") or r["summary"], [], []


FORMATTERS = {"explain_metric": _explain, "assess_collaboration": _assess, "get_collaboration_history": _assess, "get_shortest_collaboration_path": _assess, "get_common_collaborators": _assess,
              "recommend_collaborators": _recommend, "compare_institutes": _compare_inst, "top_faculty": _top_faculty, "bridge_researchers": _top_faculty, "faculty_pattern": _pattern,
              "resilience_summary": _resilience, "simulate_node_removal": _removal, "network_overview": _network, "citation_flows": _flows, "get_paper": _paper, "explain_paper_pagerank": _pagerank,
              "assess_institute_collaboration": _institute_collab, "partner_institutes": _partner, "partner_place_impact": _place_impact, "citation_give_take": _give_take, "explain_output_difference": _why, "find_experts": _experts, "get_faculty_profile": _profile}
