"""Step 12: the extra analyses the instructor asked for. Runs after extras.py. Local data only.

 1. Papers with more than 10 authors (hyper-authored): who is on them, and the results again without them
      stats/multi_author_10plus_papers.csv   every such paper, our faculty on it, and review flags
      stats/multi_author_reanalysis.csv      per institute: all papers vs without the >10-author papers
 2. Incoming / outgoing citations
      stats/citation_ratio.csv               per institute and year: in-cites, out-cites, ratio (+ whole period)
 3. Top 30 papers per institute: h-index, citations, Q1, Q1 with IF > 5, Q1 with IF > 10
      stats/top30_summary.csv                one row per institute
 4. Author-based analysis (faculty)
      stats/faculty_ranking_<institute>.csv  all faculty with ranks by papers, citations, h-index
      stats/h_index_distribution.csv         histogram bins per institute
      stats/author_brokers.csv               collaboration hubs and brokers (degree, betweenness)
      stats/author_analysis.json             concentration, productivity, collaboration summary
All numbers come from group15_data.csv (faculty rows), so they describe the faculty corpus.
"""
import json

import numpy as np
import pandas as pd

import config

OUT, STATS = config.OUT_DIR, config.OUT_DIR / "stats"
ALL = OUT / "all_authors"
INSTS = list(config.INSTITUTES)


def h_index(c):
    c = sorted(c, reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return float("nan")
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def load():
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    m["cit"] = pd.to_numeric(m.citations, errors="coerce").fillna(0)
    m["yr"] = pd.to_numeric(m.year)
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str, "issn_all": str}, keep_default_na=False)
    p["n_authors"] = pd.to_numeric(p.n_authors)
    return m, p


# ------------------------------------------------------------------ 1. more than 10 authors
def multi_author(m, p):
    n_auth = dict(zip(p.openalex_work_id, p.n_authors))
    m["n_authors"] = m.openalex_work_id.map(n_auth)
    big = m[m.is_multi_author_10plus == "TRUE"]
    full = pd.read_csv(ALL / "group15_data.csv", dtype=str, keep_default_na=False) if (ALL / "group15_data.csv").exists() else m

    rows = []
    for (inst, wid), g in big.groupby(["institution", "openalex_work_id"]):
        a = full[(full.institution == inst) & (full.openalex_work_id == wid)]
        fac = a[a.is_faculty == "TRUE"]
        non = a[a.is_faculty != "TRUE"]
        # warning signs for "not really permanent faculty": a former faculty member outside the years on the page,
        # a person whose OpenAlex record is mostly at other institutes (visiting / guest / moved on)
        warn = []
        for r in fac.itertuples():
            if r.faculty_status == "former" and r.paper_in_window == "FALSE":
                warn.append(f"{r.faculty_name}: former, paper outside page years")
            if r.affiliation_note == "mostly_elsewhere":
                warn.append(f"{r.faculty_name}: record mostly at other institutes")
        rows.append({"institution": inst, "openalex_work_id": wid, "title": g.title.iloc[0], "year": g.year.iloc[0],
                     "type": g.type.iloc[0], "journal_name": g.journal_name.iloc[0], "quartile": g.quartile.iloc[0],
                     "citations": int(g.cit.iloc[0]), "n_authors": int(g.n_authors.iloc[0]),
                     "our_faculty_on_paper": "; ".join(sorted(set(fac.faculty_name))),
                     "n_our_faculty": fac.faculty_name.nunique(),
                     "n_our_non_faculty_removed": non.author_id.nunique(),
                     "non_faculty_roles": ", ".join(f"{k}:{v}" for k, v in non.author_role.value_counts().items()),
                     "review_flags": " | ".join(warn)})
    d = pd.DataFrame(rows).sort_values(["institution", "n_authors"], ascending=[True, False])
    d.to_csv(STATS / "multi_author_10plus_papers.csv", index=False)

    # re-analysis: same metrics with and without the >10-author papers
    out = []
    for inst in INSTS:
        g = m[m.institution == inst]
        for label, gg in (("all papers", g), ("without >10-author papers", g[g.is_multi_author_10plus != "TRUE"])):
            pp = gg.drop_duplicates("openalex_work_id")
            j = pp[(pp.type == "journal") & pp.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
            per = gg.drop_duplicates(["faculty_name", "openalex_work_id"]).groupby("faculty_name").cit.apply(list)
            hs = per.map(h_index)
            out.append({"institution": inst, "scope": label, "papers": len(pp), "citations": int(pp.cit.sum()),
                        "citations_per_paper": round(pp.cit.mean(), 2), "journal_Q1_share_%": round((j.quartile == "Q1").mean() * 100, 1),
                        "faculty_with_papers": len(per), "median_faculty_h": float(hs.median()),
                        "p90_faculty_h": float(hs.quantile(.9)), "faculty_h_20_plus": int((hs >= 20).sum()),
                        "max_faculty_h": int(hs.max()), "papers_with_10plus_authors": int((pp.is_multi_author_10plus == "TRUE").sum())})
    r = pd.DataFrame(out)
    r.to_csv(STATS / "multi_author_reanalysis.csv", index=False)
    return d, r


# ------------------------------------------------------------------ 2. incoming / outgoing citations
def citation_ratio():
    f = pd.read_csv(OUT / "citation_flow_by_year.csv")
    f = f[f.year.between(2016, 2026)]
    f["in_over_out"] = (f.in_cites / f.out_cites.replace(0, np.nan)).round(3)
    tot = f.groupby("your_inst")[["in_cites", "out_cites"]].sum().reset_index()
    tot["year"] = "2016-2026"
    tot["in_over_out"] = (tot.in_cites / tot.out_cites).round(3)
    r = pd.concat([f.assign(year=f.year.astype(str)), tot[f.columns.tolist()]], ignore_index=True)
    r.to_csv(STATS / "citation_ratio.csv", index=False)
    return r


# ------------------------------------------------------------------ 3. top 30 papers
def top30_summary(m):
    """Top papers per institute. Q1 share uses the one definition in metrics_defs.journal_q1_share (Q1 journal papers /
    ranked journal papers); the numerator, denominator and ranking coverage are all kept so tooltips can show them."""
    from metrics_defs import journal_q1_share
    rows = []
    for inst in INSTS:
        t = pd.read_csv(STATS / f"top30_papers_{inst.replace(' ', '_')}.csv")
        q1, ranked, share, cov = journal_q1_share(t)
        rows.append({"institution": inst, "papers": len(t), "citations_min": int(t.citations.min()),
                     "citations_median": float(t.citations.median()), "citations_max": int(t.citations.max()),
                     "citations_total": int(t.citations.sum()),
                     "journal_papers": int(t.type.eq("journal").sum()), "conference_papers": int(t.type.eq("conference").sum()),
                     "Q1": q1, "journal_ranked": ranked, "Q1_share_%": share, "ranking_coverage_%": cov,
                     "Q1_all_30_share_%": round(q1 / len(t) * 100, 1),
                     "Q1_and_IF_gt5": int(t.q1_impact_gt5.astype(str).str.upper().eq("TRUE").sum()),
                     "Q1_and_IF_gt10": int(t.q1_impact_gt10.astype(str).str.upper().eq("TRUE").sum()),
                     "median_venue_h_index": float(t.venue_h_index.median()),
                     "papers_with_faculty_h_20_plus": int((t.max_faculty_h_index >= 20).sum()),
                     "median_max_faculty_h": float(t.max_faculty_h_index.median()),
                     "papers_with_10plus_authors": int(t.is_multi_author_10plus.astype(str).str.upper().eq("TRUE").sum()),
                     "estimated_quartiles_in_top30": int(t.quartile_source.astype(str).str.startswith("estimated").sum())})
    r = pd.DataFrame(rows)
    r.to_csv(STATS / "top30_summary.csv", index=False)
    return r


# ------------------------------------------------------------------ 4. author-based analysis
def authors(m):
    fp = pd.read_csv(STATS / "faculty_performance.csv")
    nodes = pd.read_csv(OUT / "faculty_network_nodes.csv")
    f = m.drop_duplicates(["institution", "faculty_name", "openalex_work_id"])
    extra = []
    for (inst, name), g in f.groupby(["institution", "faculty_name"]):
        j = g[g.type == "journal"].journal_name
        tj = j.value_counts()
        extra.append({"institution": inst, "faculty_name": name,
                      "top_journal_papers": int(tj.iloc[0]) if len(tj) else 0,
                      "q1_papers": int(g.quartile.eq("Q1").sum()),
                      "q1_if_gt5_papers": int(g.q1_impact_gt5.eq("TRUE").sum()),
                      "papers_10plus_authors": int(g.is_multi_author_10plus.eq("TRUE").sum()),
                      "citations_per_paper": round(g.cit.mean(), 1),
                      "external_coauthor_papers_%": round((~g.coauthor_institutes.isin(["none", "unknown"])).mean() * 100, 1)})
    fp = fp.merge(pd.DataFrame(extra), on=["institution", "faculty_name"], how="left")
    fp = fp.merge(nodes[["faculty_name", "institution", "collaborators", "degree_centrality", "betweenness",
                         "community_leiden", "collaborators_other_inst"]], on=["faculty_name", "institution"], how="left")
    res = {}
    dist = []
    bins = [(0, 0), (1, 4), (5, 9), (10, 14), (15, 19), (20, 29), (30, 999)]
    for inst in INSTS:
        g = fp[fp.institution == inst].copy()
        for c in ("papers", "citations", "h_index"):
            g[f"rank_{c}"] = g[c].rank(ascending=False, method="min").astype(int)
        g = g.sort_values(["h_index", "citations"], ascending=False)
        g.to_csv(STATS / f"faculty_ranking_{inst.replace(' ', '_')}.csv", index=False)
        for lo, hi in bins:
            dist.append({"institution": inst, "h_index": f"{lo}" if lo == hi else (f"{lo}+" if hi == 999 else f"{lo}-{hi}"),
                         "faculty": int(g.h_index.between(lo, hi).sum())})
        act = g[g.papers > 0]
        top10 = act.nlargest(10, "citations")
        res[inst] = {
            "faculty_listed": len(g), "faculty_with_papers": len(act), "faculty_without_papers": len(g) - len(act),
            "papers_per_faculty_median": float(act.papers.median()), "papers_per_faculty_mean": round(act.papers.mean(), 1),
            "h_index_median": float(act.h_index.median()), "h_index_p90": float(act.h_index.quantile(.9)),
            "h_index_max": int(act.h_index.max()), "faculty_h_20_plus": int((act.h_index >= 20).sum()),
            "top10_share_of_citations_%": round(top10.citations.sum() / act.citations.sum() * 100, 1),
            "top10_by_papers_share_of_papers_%": round(act.nlargest(10, "papers").papers.sum() / act.papers.sum() * 100, 1),
            "gini_papers_per_faculty": round(gini(act.papers), 3), "gini_citations_per_faculty": round(gini(act.citations), 3),
            "faculty_median_q1_share_%": float(act["q1_share_%"].median()),
            "top5_h_index": act.nlargest(5, "h_index")[["faculty_name", "h_index", "papers", "citations"]].to_dict("records"),
            "top5_papers": act.nlargest(5, "papers")[["faculty_name", "papers", "citations", "h_index"]].to_dict("records"),
            "top5_citations": act.nlargest(5, "citations")[["faculty_name", "citations", "papers", "h_index"]].to_dict("records"),
            "top5_top_journal_papers": act.nlargest(5, "top_journal_papers")[["faculty_name", "top_journal", "top_journal_papers"]].to_dict("records"),
            "current_vs_former": g.faculty_status.value_counts().to_dict(),
            "median_collaborators_in_faculty_network": float(g.collaborators.median()),
        }
    pd.DataFrame(dist).to_csv(STATS / "h_index_distribution.csv", index=False)
    brokers = fp.sort_values("betweenness", ascending=False).head(30)[
        ["institution", "faculty_name", "department", "collaborators", "collaborators_other_inst", "degree_centrality",
         "betweenness", "community_leiden", "papers", "h_index"]]
    brokers.to_csv(STATS / "author_brokers.csv", index=False)
    res["brokers_top5"] = brokers.head(5)[["faculty_name", "institution", "betweenness", "collaborators"]].to_dict("records")
    res["note"] = "faculty corpus only (group15_data.csv); h-index counts 2016-2026 papers of the corpus"
    json.dump(res, open(STATS / "author_analysis.json", "w"), indent=1, default=float)
    return res


def main():
    STATS.mkdir(exist_ok=True)
    m, p = load()
    d, r = multi_author(m, p)
    print("papers with more than 10 authors:", d.groupby("institution").size().to_dict(),
          "| flagged for review:", int((d.review_flags != "").sum()), "| max authors:", int(d.n_authors.max()))
    print(r[["institution", "scope", "papers", "citations", "journal_Q1_share_%", "median_faculty_h", "faculty_h_20_plus"]].to_string(index=False))
    cr = citation_ratio()
    print("\nincoming/outgoing citations 2016-2026:")
    print(cr[cr.year == "2016-2026"][["your_inst", "in_cites", "out_cites", "in_over_out"]].to_string(index=False))
    t = top30_summary(m)
    print("\ntop 30 papers per institute:")
    print(t[["institution", "citations_min", "citations_max", "Q1", "Q1_and_IF_gt5", "Q1_and_IF_gt10", "papers_with_faculty_h_20_plus"]].to_string(index=False))
    a = authors(m)
    for inst in INSTS:
        x = a[inst]
        print(f"\n{inst}: {x['faculty_with_papers']} faculty with papers of {x['faculty_listed']}, median h {x['h_index_median']}, "
              f"top-10 hold {x['top10_share_of_citations_%']}% of citations, Gini(papers) {x['gini_papers_per_faculty']}")


if __name__ == "__main__":
    main()
