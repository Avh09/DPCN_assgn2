"""Step 16: Key Findings for every dashboard tab, generated from the computed tables (nothing is typed in).

Each finding is {tab, title, text, evidence, period, kind, caveat}:
  kind      'observation' (a computed fact) or 'possible explanation' (a hypothesis the numbers are consistent with, not tested as a cause)
  evidence  the exact metrics behind the sentence, so a reader can check it
Writes stats/key_findings.json. The dashboard shows them under each tab; the assistant reuses them.
"""
import json

import numpy as np
import pandas as pd

import config

OUT, ST = config.OUT_DIR, config.OUT_DIR / "stats"
IN = ST / "insights"
INSTS = list(config.INSTITUTES)
SH = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}
PERIOD = "2016-2026 (2026 partial)"


def best(df, col, hi=True):
    r = df.loc[df[col].idxmax() if hi else df[col].idxmin()]
    return r.institution, r[col]


def F(tab, title, text, evidence, kind="observation", caveat="", period=PERIOD):
    return {"tab": tab, "title": title, "text": text, "evidence": evidence, "kind": kind, "caveat": caveat, "period": period}


def main():
    out = []
    comp = pd.read_csv(IN / "institute_comparison.csv")
    hs = json.load(open(IN / "h_index_size_test.json"))
    conc = json.load(open(IN / "citation_concentration.json"))
    rev = pd.read_csv(IN / "review_analysis.csv")
    surge = json.load(open(IN / "nitj_2020_surge.json"))
    qi = pd.read_csv(IN / "quartile_vs_impact.csv")
    team = pd.read_csv(IN / "team_size.csv")
    cvi = json.load(open(IN / "connectivity_vs_impact.json"))
    mix = pd.read_csv(IN / "publication_mix_by_year.csv")
    cs = json.load(open(ST / "citation_sources.json"))
    nm = pd.read_csv(ST / "citation_node_metrics.csv")
    net = json.load(open(ST / "network_results.json"))["citation_network"]
    fnr = json.load(open(ST / "faculty_network_results.json"))
    fx = {x["scope"]: x for x in json.load(open(ST / "faculty_network_extra.json"))}
    R = json.load(open(ST / "resilience_results.json"))
    LP = json.load(open(ST / "link_prediction_results.json"))
    conf = json.load(open(ST / "conference_ranking.json"))
    ratio = pd.read_csv(ST / "citation_ratio.csv")
    ratio = ratio[ratio.year == "2016-2026"].set_index("your_inst")
    reach = pd.read_csv(ST / "locality" / "collaboration_reach.csv")
    c = comp.set_index("institution")

    # ------------------------------------------------------------- Overview
    pa, ppa = best(comp, "papers"), best(comp, "papers_per_active_faculty")
    out.append(F("overview", "Productivity: size or output per faculty?", f"{SH[pa[0]]} has the most papers ({int(pa[1]):,}); per research-active faculty member {SH[best(comp, 'papers_per_active_faculty')[0]]} is first "
                 f"({', '.join(f'{SH[i]} {c.at[i, 'papers_per_active_faculty']:.1f}' for i in INSTS)} papers per faculty), so size and output per faculty member {'agree' if pa[0] == ppa[0] else 'give different leaders'}.",
                 {"papers": comp.set_index("institution").papers.to_dict(), "papers_per_active_faculty": comp.set_index("institution").papers_per_active_faculty.to_dict()}))
    cp, med, fw = best(comp, "citations_per_paper"), best(comp, "median_citations_per_paper"), best(comp, "fwci_median")
    out.append(F("overview", "Impact depends on the measure", f"Mean citations per paper is highest at {SH[cp[0]]} ({cp[1]:.1f}), the median is highest at {SH[med[0]]} ({med[1]:.0f}) and the median field-weighted impact "
                 f"(FWCI, 1 = world average) at {SH[fw[0]]} ({fw[1]:.2f}). A mean ahead of the median means a few very highly cited papers lift the average.",
                 {"mean": comp.set_index("institution").citations_per_paper.to_dict(), "median": comp.set_index("institution").median_citations_per_paper.to_dict(),
                  "fwci_median": comp.set_index("institution").fwci_median.to_dict(), "fwci_mean": comp.set_index("institution").fwci_mean.to_dict()}))
    hi = comp.set_index("institution").institute_h_index
    eq = hs["institutes"]
    top_h = hi.idxmax()
    eq_rank = sorted(INSTS, key=lambda i: -eq[i]["mean_h_at_equal_size"])
    out.append(F("overview", "Institute h-index and size", f"{SH[top_h]} has the highest institute h-index ({int(hi[top_h])}). h-index grows with the number of papers; drawing the same number of papers ({hs['papers_per_sample']:,}) "
                 f"from each institute gives mean h-indices of {', '.join(f'{SH[i]} {eq[i]['mean_h_at_equal_size']:.1f}' for i in eq_rank)}, so the ordering {'survives' if eq_rank[0] == top_h else 'changes after'} size normalisation.",
                 {"observed": hi.to_dict(), "equal_size_mean": {i: eq[i]["mean_h_at_equal_size"] for i in INSTS}, "percentiles": hs["citation_percentiles"]},
                 caveat="h-index counts only the 2016-2026 papers of verified faculty."))
    q1 = best(comp, "journal_Q1_share_%")
    out.append(F("overview", "Journal quality", f"{SH[q1[0]]} has the highest Q1 share of ranked journal papers ({q1[1]:.1f}%). Q1 share = Q1 journal papers / journal papers with a quartile "
                 f"({', '.join(f'{SH[i]} {int(c.at[i, 'journal_Q1_papers']):,}/{int(c.at[i, 'journal_ranked_papers']):,}' for i in INSTS)}); ranking coverage is at least {comp['ranking_coverage_%'].min():.1f}% of journal papers.",
                 {"q1_share": comp.set_index("institution")["journal_Q1_share_%"].to_dict(), "coverage": comp.set_index("institution")["ranking_coverage_%"].to_dict()},
                 caveat="Some quartiles are estimated from venue statistics (see Methodology); conference ranks are reported separately."))
    gr = best(comp, "growth_2016_2020_to_2021_2025_%")
    out.append(F("overview", "Growth", f"{SH[gr[0]]} grew most between 2016-2020 and 2021-2025 (+{gr[1]:.0f}%), from the smallest base ({int(c.at[gr[0], 'papers_2016_2020']):,} papers). "
                 f"Others: {', '.join(f'{SH[i]} +{c.at[i, 'growth_2016_2020_to_2021_2025_%']:.0f}%' for i in INSTS if i != gr[0])}.",
                 {"growth_%": comp.set_index("institution")["growth_2016_2020_to_2021_2025_%"].to_dict()}, kind="observation"))

    # ------------------------------------------------------------- Publications
    q1y = mix.groupby(["institution"]).apply(lambda g: (g[g.year.isin([2016, 2017])]["journal_Q1"].sum() / max(g[g.year.isin([2016, 2017])]["journal_ranked"].sum(), 1) * 100,
                                                         g[g.year.isin([2024, 2025])]["journal_Q1"].sum() / max(g[g.year.isin([2024, 2025])]["journal_ranked"].sum(), 1) * 100), include_groups=False)
    out.append(F("publications", "Q1 share over time", "Q1 share of ranked journal papers, 2016-17 -> 2024-25: " + "; ".join(f"{SH[i]} {a:.0f}% -> {b:.0f}%" for i, (a, b) in q1y.items()) +
                 ". " + ("Q1 share rose at " + ", ".join(SH[i] for i, (a, b) in q1y.items() if b > a + 1) + "; " + (", ".join(SH[i] for i, (a, b) in q1y.items() if b <= a + 1) + " is flat. " if any(b <= a + 1 for a, b in q1y.values) else "") if True else "") + "2026 is excluded (partial year).", {"q1_share_2016_17_to_2024_25": {i: [round(a, 1), round(b, 1)] for i, (a, b) in q1y.items()}},
                 caveat="Historical papers use the quartile of the journal in the paper's year where available (SCImago per year); Scopus CiteScore quartiles use the nearest available year.", period="2016-2025"))
    cshare = mix[mix.year <= 2025].groupby("institution")["conference_share_%"].agg(["min", "max"])
    out.append(F("publications", "Conference share", "The conference share of papers stays within " + "; ".join(f"{SH[i]} {r['min']:.0f}-{r['max']:.0f}%" for i, r in cshare.iterrows()) + " of papers in a given year (2016-2025).",
                 {"conference_share_range_%": cshare.round(1).to_dict("index")}, period="2016-2025"))
    inc = conf["in_final_corpus"]
    out.append(F("publications", "Conference rankings", f"Of {inc['conference_papers']:,} conference papers, {inc['named_conference']:,} have an identifiable conference and {inc['generic_series']:,} appear only as a publisher series "
                 f"(Lecture Notes, AIP, Materials Today Proceedings). CORE ranks exist for {sum(inc['core_ranked'].values())} papers ({', '.join(f'{k} {v}' for k, v in inc['core_ranked'].items())}); "
                 f"there is no CORE A* or A paper among faculty papers. The unfiltered download holds {conf['a_star_a_papers']} CORE A*/A conference papers that were identified (EMNLP 2023; two EACL 2026 Findings papers); none has a verified faculty author (the authors of these papers from the three institutes are students or visitors). Conferences hidden behind a publisher series cannot be ranked, so this count is a lower bound.",
                 {"conference_ranking": conf}, caveat="CORE ranks computer-science conferences only; most conference papers here are engineering conferences, so absence of A*/A reflects the field mix as well as quality."))
    q = qi[qi.period.isin(["2016-18", "2019-21"]) & qi.quartile.isin(["Q1", "Q4"])].groupby("quartile").median_citations.median()
    cf = qi[qi.quartile == "conference"].iloc[0]
    out.append(F("publications", "Quartile and citations", f"For journal papers published 2016-2021 the median citations are about {q.get('Q1', float('nan')):.0f} for Q1 and {q.get('Q4', float('nan')):.0f} for Q4 journals; conference papers have a median of {cf.median_citations:.0f}. "
                 "The gap is shown as an association; journal quartile is not a direct measure of a paper's quality, and field and publication year differ between groups.",
                 {"median_citations": q.to_dict(), "conference_median": float(cf.median_citations)}, "observation", "Compare within fields (Methodology) before drawing conclusions.", "2016-2021 papers"))
    sp = pd.read_csv(IN / "specialisation.csv")
    f = sp[(sp.level == "field") & (sp.papers >= 100)].sort_values("location_quotient", ascending=False).head(3)
    out.append(F("publications", "Relative specialisation", "Fields where an institute publishes most above its share of the combined corpus (location quotient): " + "; ".join(f"{SH[r.institution]} {r['name']} ({r.location_quotient:.1f}x)" for _, r in f.iterrows()) + ".",
                 {"top_location_quotients": f[["institution", "name", "papers", "location_quotient"]].to_dict("records")}))

    # ------------------------------------------------------------- Faculty
    g = {i: conc[i] for i in INSTS}
    out.append(F("faculty", "Citation concentration", "Faculty citation Gini (full counting): " + ", ".join(f"{SH[i]} {g[i]['gini_full']:.2f}" for i in INSTS) + ". The top 10% of faculty hold " +
                 ", ".join(f"{g[i]['faculty_top1_5_10_share_full'][2]:.0f}% ({SH[i]})" for i in INSTS) + " of citations; fractional counting (citations split among verified faculty authors) gives Gini " +
                 ", ".join(f"{g[i]['gini_fractional']:.2f}" for i in INSTS) + ".", {i: {"gini_full": g[i]["gini_full"], "gini_fractional": g[i]["gini_fractional"], "top1_5_10_share": g[i]["faculty_top1_5_10_share_full"], "top_faculty": g[i]["top_faculty"][:3]} for i in INSTS},
                 caveat="Gini over verified faculty with at least one paper; one shared highly cited paper counts fully for each faculty author in full counting."))
    top = max(INSTS, key=lambda i: g[i]["top_faculty"][0]["share_%"])
    out.append(F("faculty", "Reliance on single researchers", f"The largest single contributor to citations at each institute: " + "; ".join(f"{SH[i]} {g[i]['top_faculty'][0]['name']} ({g[i]['top_faculty'][0]['share_%']}%)" for i in INSTS) + ".",
                 {i: g[i]["top_faculty"][:3] for i in INSTS}))
    sp1, sp2 = cvi["spearman_degree_vs_mean_fwci"], cvi["partial_degree_vs_mean_fwci_controlling_papers"]
    out.append(F("faculty", "Connectivity and impact", f"Across {cvi['n']} faculty, the number of faculty collaborators and mean field-weighted impact are {'weakly' if abs(sp1[0]) < .3 else 'moderately'} associated (Spearman {sp1[0]:.2f}, p {sp1[1]:.2g}); "
                 f"controlling for number of papers the association is {sp2[0]:.2f} (p {sp2[1]:.2g}). This is an association, not evidence that collaborating raises impact.",
                 cvi, "possible explanation", "Field mix and career stage are not controlled; career stage is not available in the data."))

    # ------------------------------------------------------------- Papers
    r = rev[rev.group.str.startswith("review-like")]
    ms = r.set_index("institution")
    out.append(F("papers", "Review articles", "Papers whose type is review or whose title says review/survey/overview: " + "; ".join(f"{SH[i]} {ms.at[i, 'share_of_papers_%']:.1f}% of papers but {ms.at[i, 'share_of_citations_%']:.1f}% of citations "
                 f"({int(ms.at[i, 'in_top30'])} of the top 30)" for i in INSTS) + ". The strict OpenAlex 'review' type alone is under 1% of papers, so most such papers are identified from titles.",
                 rev.to_dict("records"), caveat="A title word is not proof of a review article; both definitions are shown in the Papers tab."))
    t = team[team.institution == "all"].set_index("team_size")
    if len(t) == 2:
        a, b = t.loc["more than 10 authors"], t.loc["10 or fewer"]
        out.append(F("papers", "Large author teams", f"{int(a.papers)} papers have more than 10 authors ({a.papers / (a.papers + b.papers) * 100:.1f}% of papers). Their mean citations are {a.mean_citations:.1f} versus {b.mean_citations:.1f}, "
                     f"{a['journal_Q1_share_%']:.0f}% versus {b['journal_Q1_share_%']:.0f}% of their ranked journal papers are Q1, and {a['international_collaboration_%']:.0f}% versus {b['international_collaboration_%']:.0f}% include a foreign author. "
                     "They are too few to move any institute-level figure.", t.reset_index().to_dict("records")))

    # ------------------------------------------------------------- Citations
    k = cs["edges_by_kind"]["overall"]
    tot = sum(k.values())
    top50 = nm.nlargest(50, "pagerank")
    out.append(F("citations", "What the internal citation network measures", f"{k['author_self'] / tot * 100:.1f}% of the {tot:,} citation links between the three institutes' papers are author self-citations (a shared verified faculty author), "
                 f"{k['same_institute_other_author'] / tot * 100:.1f}% are same-institute citations by other authors and {k['between_our_institutes'] / tot * 100:.1f}% go between the three institutes. "
                 "In-corpus in-degree and PageRank therefore describe research groups building on their own work, not influence across institutes.", cs["edges_by_kind"]))
    out.append(F("citations", "PageRank favours older papers", f"{int((top50.year <= 2018).sum())} of the 50 highest-PageRank papers were published in 2016-2018 and {int((top50.year > 2022).sum())} after 2022, although later years have more papers. "
                 "Older papers have had longer to be cited; the dashboard therefore also ranks each paper within its publication year.", {"top50_by_year": top50.year.value_counts().sort_index().to_dict()}, "possible explanation"))
    out.append(F("citations", "Between-institute citation share", f"{net['edges_cross_institute']:,} of {net['edges']:,} in-corpus links ({net['edges_cross_institute'] / net['edges'] * 100:.1f}%) connect papers with no institute in common.", {"flow_matrix_row_pct": net["flow_matrix_row_pct"]}, caveat="Row = citing institute; joint papers count for every institute they belong to."))

    # ------------------------------------------------------------- Co-authorship
    w = fnr["whole_network"]
    ex = fx["all three institutes"]
    out.append(F("coauthorship", "Structure", f"The verified-faculty network has {w['nodes']} faculty and {w['edges']:,} links; {w['isolated_faculty']} faculty have no link to another verified faculty member (they may still collaborate with students or outside authors). "
                 f"The largest component holds {w['largest_component_%']}% of faculty; average path length {ex['avg_shortest_path_largest_component']}, diameter {ex['diameter_largest_component']}.", {"whole_network": w, "structure": ex}))
    out.append(F("coauthorship", "Communities follow departments", f"Louvain finds {w['louvain']['communities']} communities (modularity {w['louvain']['modularity']}); agreement with formal departments (NMI) is "
                 + ", ".join(f"{SH[i]} {fnr[i]['community_vs_department']['NMI']}" for i in INSTS) + ". Only " + f"{w['cross_institute_edges']} links cross institutes.", {i: fnr[i]["community_vs_department"] for i in INSTS}))

    # ------------------------------------------------------------- Resilience
    s = {k: R["scopes"][k]["summary"] for k in R["scopes"]}
    frag = {k: s[k]["betweenness"]["fragility_index"] for k in INSTS}
    worst = max(frag, key=frag.get)
    a = R["scopes"]["all"]["summary"]
    out.append(F("resilience", "Fragile under targeted loss", f"Removing faculty at random breaks the combined network's largest component to half its original size only after {a['random']['collapse_at'] * 100:.0f}% of faculty are gone; removing the highest-betweenness faculty first needs {a['betweenness']['collapse_at'] * 100:.0f}% "
                 f"({a['betweenness_adaptive']['collapse_at'] * 100:.0f}% when betweenness is recomputed after each removal). Fragility index (1 - R20 targeted/random, betweenness): " + ", ".join(f"{SH[i]} {frag[i]:.2f}" for i in INSTS) + f"; {SH[worst]} depends most on a few bridge researchers.",
                 {"summary": s}, caveat="A structural simulation on the verified-faculty graph; removing a node does not mean a faculty member leaves."))
    nullb = a["betweenness_null"]["R20"]
    out.append(F("resilience", "Wiring beyond the degree sequence", f"Targeted betweenness attacks on degree-preserving random rewirings give R20 {nullb:.2f} against {a['betweenness']['R20']:.2f} on the real network, so the real network is {'more' if a['betweenness']['R20'] < nullb else 'less'} fragile than its degree sequence alone implies.",
                 {"real_R20": a["betweenness"]["R20"], "null_R20": nullb}, "observation"))

    # ------------------------------------------------------------- Potential collaborations
    nw, rp = LP["tasks"]["new"], LP["tasks"]["repeat"]
    m = nw["metrics"]["logistic regression"]
    out.append(F("collaborations", "Predicting new collaborations", f"Trained on 2016-2019 history and tested on 2023-2025 outcomes from 2022 features, the best model ranks the true new links with average precision {m['average_precision']:.3f} against a base rate of {m['base_rate']:.4f} "
                 f"({m['ap_lift_over_base_rate']:.0f}x) and finds {m['precision@100'] * 100:.0f}% true links among its top 100 pairs. Network features, department/institute structure and topic similarity each contribute; the output is a ranking score, not a probability (calibration check failed).",
                 {"metrics": nw["metrics"], "ablation": nw["ablation_random_forest"], "calibration": nw["calibration"]}, caveat="New links are rare; absolute precision is low even though it is far above chance."))
    r_ = rp["metrics"]["random forest"]
    out.append(F("collaborations", "Predicting repeat collaborations", f"For pairs that already co-authored, the random forest reaches average precision {r_['average_precision']:.2f} (base rate {r_['base_rate']:.2f}) and ROC-AUC {r_['roc_auc']:.2f}; its calibrated probabilities pass the calibration check "
                 f"(slope {rp['calibration']['random forest']['slope']:.2f}). Recency of the last joint paper and the strength of shared collaborator groups matter most.", {"metrics": rp["metrics"], "importance": rp["rf_importance"]}))

    # ------------------------------------------------------------- Reach and flows
    rr = reach.set_index("institution")
    if rr is not None:
        out.append(F("reach", "How far do collaborations reach?", "Share of papers with another Indian institute / a foreign partner: " + "; ".join(f"{SH[i]} {rr.at[i, 'with_other_indian_inst_%']:.0f}% / {rr.at[i, 'with_foreign_inst_%']:.0f}%" for i in INSTS) +
                     f". Distinct partner institutes: " + "; ".join(f"{SH[i]} {int(rr.at[i, 'distinct_indian_partners'])} Indian, {int(rr.at[i, 'distinct_foreign_partners'])} foreign" for i in INSTS) + ".", rr.reset_index().to_dict("records")))
    out.append(F("flows", "Citation flows with other Indian institutes", "In/out ratio (citations received from / given to other Indian institutes): " + ", ".join(f"{SH[i]} {ratio.at[i, 'in_over_out']:.2f}" for i in INSTS) +
                 ". A ratio below 1 means the institute cites other Indian institutes more than it is cited by those institutes, which is common for institutes that read widely; it is not a quality ranking.", ratio.reset_index().to_dict("records")))
    (ST / "key_findings.json").write_text(json.dumps(out, indent=1, default=str))
    print(len(out), "findings")
    for f in out:
        print("-", f["tab"], "|", f["title"], "|", f["text"][:200])


if __name__ == "__main__":
    main()
