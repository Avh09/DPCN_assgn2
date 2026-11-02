"""Step 15: institute comparison, impact normalisation and the 'why' analyses behind the dashboard's Key Findings.

Everything here is computed from the final tables; nothing is hard-coded. Output folder: data/out/stats/insights/.

Definitions (also shown in the dashboard Methodology tab)
  research-active faculty     verified faculty with at least one paper in the corpus
  journal Q1 share            Q1 journal papers / journal papers that have a journal quartile (conference ranks are separate)
  FWCI                        OpenAlex field-weighted citation impact: citations / world average for works of the same type,
                              year and subfield (1 = world average). Missing for a few recent works.
  top 10% share               share of papers in the worldwide top 10% by citations for their year and subfield (OpenAlex percentile)
  citation attribution        faculty citations are FULL-counted (a paper's citations belong to each faculty author), and also
                              reported fractionally (citations / number of verified faculty authors on the paper)
  review-like                 strict: OpenAlex work type "review"; broad: strict OR title contains review / survey / overview /
                              state of the art / "a critical" / "perspective" (a title word alone is not evidence)
  international paper         an author with a country code other than IN on the paper
"""
import json
import re

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import config
import movers

OUT, STATS = config.OUT_DIR, config.OUT_DIR / "stats"
IN = STATS / "insights"
INSTS = list(config.INSTITUTES)
SHORT = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}
REVIEW_TITLE = re.compile(r"\b(review|survey|overview|state[- ]of[- ]the[- ]art|systematic|meta-analysis|a critical|perspectives?)\b", re.I)


def h_index(c):
    c = sorted((int(x) for x in c), reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return float("nan")
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def lorenz(x, pts=41):
    x = np.sort(np.asarray(x, dtype=float))
    cum = np.insert(np.cumsum(x) / x.sum(), 0, 0)
    q = np.linspace(0, 1, pts)
    return [round(float(np.interp(v, np.linspace(0, 1, len(cum)), cum)), 4) for v in q]


def top_share(x, frac):
    x = np.sort(np.asarray(x, dtype=float))[::-1]
    k = max(1, int(np.ceil(frac * len(x))))
    return round(float(x[:k].sum() / x.sum() * 100), 1)


def load():
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    m["cit"] = pd.to_numeric(m.citations, errors="coerce").fillna(0)
    m["yr"] = m.year.astype(int)
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str}, keep_default_na=False)
    p["cit"] = pd.to_numeric(p.citations, errors="coerce").fillna(0)
    p["yr"] = p.year.astype(int)
    for f, cols in ((OUT / "work_topics.csv", ["openalex_work_id", "subfield", "topic"]),
                    (OUT / "work_extras.csv", ["openalex_work_id", "fwci", "citation_percentile", "is_top_10pct", "is_top_1pct"])):
        if f.exists():
            p = p.merge(pd.read_csv(f, dtype=str, keep_default_na=False, usecols=cols), on="openalex_work_id", how="left")
    for c in ("fwci", "citation_percentile"):
        p[c] = pd.to_numeric(p.get(c), errors="coerce")
    p["is_review_strict"] = p.openalex_type.eq("review")
    p["is_review_broad"] = p.is_review_strict | p.title.map(lambda t: bool(REVIEW_TITLE.search(t or "")))
    # one row per (paper, institute)
    pi = m.drop_duplicates(["openalex_work_id", "institution"])[["openalex_work_id", "institution"]].merge(p, on="openalex_work_id", how="left")
    return m, p, pi


def one_record_per_person(fac):
    """A person listed at two of our institutes is counted once, at the current one (see movers.py)."""
    alias = movers.aliases()
    return fac[[(i, n) not in alias for i, n in zip(fac.institution, fac.faculty_name)]]


def institute_comparison(m, p, pi):
    rows = []
    fac = one_record_per_person(m.drop_duplicates(["institution", "faculty_name", "openalex_work_id"]))
    for i in INSTS:
        g = pi[pi.institution == i]
        fi = fac[fac.institution == i]
        percit = fi.groupby("faculty_name").cit.apply(list)
        hs = percit.map(h_index)
        j = g[(g.type == "journal") & g.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
        yrs = g.groupby("yr").size()
        early, late = yrs.loc[2016:2020].sum(), yrs.loc[2021:2025].sum()
        cit_f = fi.groupby("faculty_name").cit.sum()
        rows.append({"institution": i, "papers": len(g), "research_active_faculty": fi.faculty_name.nunique(),
                     "papers_per_active_faculty": round(len(g) / fi.faculty_name.nunique(), 2),
                     "median_papers_per_faculty": float(fi.groupby("faculty_name").size().median()),
                     "citations": int(g.cit.sum()), "citations_per_paper": round(g.cit.mean(), 2), "median_citations_per_paper": float(g.cit.median()),
                     "institute_h_index": h_index(g.cit), "journal_Q1_papers": int((j.quartile == "Q1").sum()), "journal_ranked_papers": len(j),
                     "journal_papers": int((g.type == "journal").sum()), "ranking_coverage_%": round(len(j) / max((g.type == "journal").sum(), 1) * 100, 1),
                     "journal_Q1_share_%": round((j.quartile == "Q1").mean() * 100, 1),
                     "fwci_mean": round(g.fwci.mean(), 3), "fwci_median": round(g.fwci.median(), 3), "papers_with_fwci": int(g.fwci.notna().sum()),
                     "top10pct_share_%": round((g.is_top_10pct == "True").sum() / max(g.is_top_10pct.isin(["True", "False"]).sum(), 1) * 100, 1) if "is_top_10pct" in g else None,
                     "growth_2016_2020_to_2021_2025_%": round((late / max(early, 1) - 1) * 100, 1), "papers_2016_2020": int(early), "papers_2021_2025": int(late),
                     "faculty_h_median": float(hs.median()), "faculty_h_20_plus": int((hs >= 20).sum()),
                     "citation_gini_faculty": round(gini(cit_f), 3), "top10_faculty_share_of_citations_%": top_share(cit_f, 10 / max(len(cit_f), 1)),
                     "review_share_of_papers_%": round(g.is_review_broad.mean() * 100, 1), "review_share_of_citations_%": round(g[g.is_review_broad].cit.sum() / max(g.cit.sum(), 1) * 100, 1)})
    d = pd.DataFrame(rows)
    d.to_csv(IN / "institute_comparison.csv", index=False)
    return d


def h_index_size_test(pi):
    """Does MANIT's higher institute h-index survive when institutes are compared at the SAME number of papers?"""
    rng = np.random.default_rng(15)
    n_min = int(pi.groupby("institution").size().min())
    out = {"papers_per_sample": n_min, "draws": 500, "institutes": {}}
    for i in INSTS:
        c = pi[pi.institution == i].cit.values
        hs = [h_index(rng.choice(c, n_min, replace=False)) for _ in range(500)]
        out["institutes"][i] = {"observed_h": h_index(c), "papers": len(c), "mean_h_at_equal_size": round(float(np.mean(hs)), 1),
                                "p5": float(np.percentile(hs, 5)), "p95": float(np.percentile(hs, 95))}
    out["note"] = "h-index grows with the number of papers; drawing the same number of papers from each institute compares the institutes at equal size"
    pct = {i: {q: float(np.percentile(pi[pi.institution == i].cit, q)) for q in (50, 75, 90, 95, 99)} for i in INSTS}
    out["citation_percentiles"] = pct
    (IN / "h_index_size_test.json").write_text(json.dumps(out, indent=1))
    return out


def concentration(m, pi):
    fac = one_record_per_person(m.drop_duplicates(["institution", "faculty_name", "openalex_work_id"])).copy()
    nfac = fac.groupby(["institution", "openalex_work_id"]).faculty_name.transform("nunique")
    fac["cit_frac"] = fac.cit / nfac
    out = {"definition": "full counting: a paper's citations count for every verified faculty author; fractional: divided by the number of verified faculty authors"}
    for i in INSTS:
        g = fac[fac.institution == i]
        full, frac = g.groupby("faculty_name").cit.sum(), g.groupby("faculty_name").cit_frac.sum()
        pap = pi[pi.institution == i].cit
        top1 = full.sort_values(ascending=False)
        out[i] = {"faculty": len(full), "gini_full": round(gini(full), 3), "gini_fractional": round(gini(frac), 3), "gini_papers_citations": round(gini(pap), 3),
                  "faculty_top1_5_10_share_full": [top_share(full, f) for f in (.01, .05, .10)], "faculty_top1_5_10_share_fractional": [top_share(frac, f) for f in (.01, .05, .10)],
                  "paper_top1_5_10_share": [top_share(pap, f) for f in (.01, .05, .10)], "lorenz_faculty_full": lorenz(full), "lorenz_papers": lorenz(pap),
                  "top_faculty": [{"name": n, "citations": int(v), "share_%": round(v / full.sum() * 100, 1)} for n, v in top1.head(5).items()]}
    (IN / "citation_concentration.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def reviews(pi):
    rows = []
    for i in INSTS:
        g = pi[pi.institution == i]
        for label, mask in (("review (strict: OpenAlex type)", g.is_review_strict), ("review-like (broad: type or title words)", g.is_review_broad), ("not review", ~g.is_review_broad)):
            s = g[mask]
            top30 = g.nlargest(30, "cit")
            rows.append({"institution": i, "group": label, "papers": len(s), "share_of_papers_%": round(len(s) / len(g) * 100, 1), "citations": int(s.cit.sum()),
                         "share_of_citations_%": round(s.cit.sum() / g.cit.sum() * 100, 1), "mean_citations": round(s.cit.mean(), 1), "median_citations": float(s.cit.median()),
                         "mean_fwci": round(s.fwci.mean(), 2), "median_year": float(s.yr.median()),
                         "in_top30": int(top30.index.isin(s.index).sum())})
    d = pd.DataFrame(rows)
    d.to_csv(IN / "review_analysis.csv", index=False)
    return d


def surge(m, pi, inst="NIT Jamshedpur"):
    g = pi[pi.institution == inst]
    top = g.nlargest(30, "cit")
    fac = m[(m.institution == inst)].drop_duplicates(["openalex_work_id", "faculty_name"])
    on = fac.groupby("openalex_work_id").faculty_name.apply(list)
    cnt = pd.Series([n for ids in top.openalex_work_id for n in on.get(ids, [])]).value_counts()
    out = {"institute": inst, "top30_by_year": top.yr.value_counts().sort_index().to_dict(), "top30_by_field": top.field.value_counts().to_dict(),
           "top30_by_subfield": top.subfield.value_counts().head(8).to_dict() if "subfield" in top else {}, "top30_faculty_involvement": cnt.head(6).to_dict()}
    lead = cnt.index[0] if len(cnt) else None
    if lead:
        theirs = set(fac[fac.faculty_name == lead].openalex_work_id)
        rest = g[~g.openalex_work_id.isin(theirs)]
        out["lead_faculty"] = lead
        out["with_vs_without_lead_faculty"] = {"all": {"papers": len(g), "citations": int(g.cit.sum()), "h": h_index(g.cit), "median_cit": float(g.cit.median())},
                                               "without_lead": {"papers": len(rest), "citations": int(rest.cit.sum()), "h": h_index(rest.cit), "median_cit": float(rest.cit.median())},
                                               "lead_share_of_citations_%": round(g[g.openalex_work_id.isin(theirs)].cit.sum() / g.cit.sum() * 100, 1)}
    y2020 = g[g.yr == 2020]
    out["year_2020"] = {"papers": len(y2020), "citations": int(y2020.cit.sum()), "share_of_institute_citations_%": round(y2020.cit.sum() / g.cit.sum() * 100, 1),
                        "top30_from_2020": int((top.yr == 2020).sum())}
    (IN / "nitj_2020_surge.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def quartile_impact(pi):
    j = pi[(pi.type == "journal") & pi.quartile.isin(["Q1", "Q2", "Q3", "Q4"])].drop_duplicates("openalex_work_id")
    j = j.assign(period=pd.cut(j.yr, [2015, 2018, 2021, 2023, 2026], labels=["2016-18", "2019-21", "2022-23", "2024-26"]))
    rows = []
    for (per, q), g in j.groupby(["period", "quartile"], observed=True):
        rows.append({"period": per, "quartile": q, "papers": len(g), "median_citations": float(g.cit.median()), "mean_fwci": round(g.fwci.mean(), 2),
                     "median_fwci": round(g.fwci.median(), 2)})
    # field-controlled: median FWCI by quartile within the five largest fields
    big = j.field.value_counts().head(5).index
    for f in big:
        for q, g in j[j.field == f].groupby("quartile"):
            rows.append({"period": "all (field: " + f + ")", "quartile": q, "papers": len(g), "median_citations": float(g.cit.median()), "mean_fwci": round(g.fwci.mean(), 2), "median_fwci": round(g.fwci.median(), 2)})
    c = pi[(pi.type == "conference")].drop_duplicates("openalex_work_id")
    rows.append({"period": "all (conference papers)", "quartile": "conference", "papers": len(c), "median_citations": float(c.cit.median()), "mean_fwci": round(c.fwci.mean(), 2),
                 "median_fwci": round(c.fwci.median(), 2)})
    d = pd.DataFrame(rows)
    d.to_csv(IN / "quartile_vs_impact.csv", index=False)
    return d


def team_size(m, p, pi):
    """>10 authors vs the rest: impact, venue quality, international collaboration."""
    au = pd.read_csv(OUT / "all_authors" / "authorships.csv", usecols=["openalex_work_id", "country_codes"], dtype=str, keep_default_na=False)
    intl = au.groupby("openalex_work_id").country_codes.apply(lambda s: any(c not in ("", "IN") for x in s for c in x.split(";") if c)).to_dict()
    g = pi.copy()
    g["intl"] = g.openalex_work_id.map(intl).fillna(False)
    g["team"] = np.where(g.is_multi_author_10plus == "TRUE", "more than 10 authors", "10 or fewer") if "is_multi_author_10plus" in g else "n/a"
    if "is_multi_author_10plus" not in g:
        g["team"] = np.where(g.n_authors.astype(int) > 10, "more than 10 authors", "10 or fewer")
    rows = []
    for i in INSTS + ["all"]:
        s = g.drop_duplicates("openalex_work_id") if i == "all" else g[g.institution == i]
        for t, x in s.groupby("team"):
            jr = x[(x.type == "journal") & x.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
            rows.append({"institution": i, "team_size": t, "papers": len(x), "mean_citations": round(x.cit.mean(), 1), "median_citations": float(x.cit.median()),
                         "mean_fwci": round(x.fwci.mean(), 2), "journal_Q1_share_%": round((jr.quartile == "Q1").mean() * 100, 1) if len(jr) else None,
                         "international_collaboration_%": round(x.intl.mean() * 100, 1), "conference_share_%": round((x.type == "conference").mean() * 100, 1)})
    d = pd.DataFrame(rows)
    d.to_csv(IN / "team_size.csv", index=False)
    return d


def connectivity_vs_impact(m):
    """Faculty: distinct collaborators (verified-faculty graph and all co-authors) against productivity and normalised impact."""
    nm = pd.read_csv(STATS / "faculty_node_metrics.csv")
    pe = pd.read_csv(OUT / "work_extras.csv", dtype=str, usecols=["openalex_work_id", "fwci"]) if (OUT / "work_extras.csv").exists() else None
    f = m.drop_duplicates(["institution", "faculty_name", "openalex_work_id"])
    if pe is not None:
        f = f.merge(pe, on="openalex_work_id", how="left")
        f["fwci"] = pd.to_numeric(f.fwci, errors="coerce")
    g = f.groupby(["institution", "faculty_name"]).agg(papers=("openalex_work_id", "nunique"), citations=("cit", "sum"), mean_fwci=("fwci", "mean"), median_fwci=("fwci", "median")).reset_index()
    au = pd.read_csv(OUT / "all_authors" / "authorships.csv", usecols=["openalex_work_id", "author_id"], dtype=str, keep_default_na=False)
    coa = au.groupby("openalex_work_id").author_id.apply(set).to_dict()
    amap = pd.read_csv(OUT / "author_faculty_map.csv", dtype=str)
    ids = amap.groupby(["institution", "faculty_name"]).author_id.apply(set).to_dict()
    papers_of = f.groupby(["institution", "faculty_name"]).openalex_work_id.apply(list).to_dict()
    distinct = {k: len(set().union(*[coa.get(w, set()) for w in ws]) - ids.get(k, set())) for k, ws in papers_of.items()}
    al = movers.aliases()      # one row per person: a person listed at two institutes is counted once
    g = g[[(a, b) not in al for a, b in zip(g.institution, g.faculty_name)]].reset_index(drop=True)
    g["distinct_coauthors_all"] = [distinct.get((a, b), 0) for a, b in zip(g.institution, g.faculty_name)]
    g = g.merge(nm[["institution", "faculty_name", "degree", "betweenness", "participation_dept", "h_index"]], on=["institution", "faculty_name"], how="left")
    g.to_csv(IN / "connectivity_vs_impact.csv", index=False)
    res = {"n": len(g)}
    ok = g.dropna(subset=["mean_fwci"])
    for x, y in (("degree", "mean_fwci"), ("distinct_coauthors_all", "mean_fwci"), ("degree", "citations"), ("betweenness", "mean_fwci")):
        rho = spearmanr(ok[x], ok[y])
        res[f"spearman_{x}_vs_{y}"] = [round(float(rho[0]), 3), float(f"{rho[1]:.2g}")]
    # partial association controlling for productivity (rank-residual method)
    from scipy.stats import rankdata
    def resid(a, c):
        a, c = rankdata(a), rankdata(c)
        slope = np.polyfit(c, a, 1)
        return a - np.polyval(slope, c)
    for x in ("degree", "distinct_coauthors_all"):
        r = spearmanr(resid(ok[x], ok.papers), resid(ok.mean_fwci, ok.papers))
        res[f"partial_{x}_vs_mean_fwci_controlling_papers"] = [round(float(r[0]), 3), float(f"{r[1]:.2g}")]
    res["note"] = "association, not causation; productivity is controlled by rank-residuals; field mix and career stage are not controlled (career stage is not available)"
    (IN / "connectivity_vs_impact.json").write_text(json.dumps(res, indent=1))
    return res


def specialisation(pi):
    rows = []
    allf = pi.drop_duplicates("openalex_work_id")
    for level in ("field", "subfield", "topic"):
        if level not in pi:
            continue
        base = allf[level].value_counts(normalize=True)
        for i in INSTS:
            g = pi[pi.institution == i]
            vc = g[level].value_counts()
            for name, n in vc.head(60 if level == "field" else 40).items():
                if not name:
                    continue
                s = g[g[level] == name]
                rows.append({"level": level, "institution": i, "name": name, "papers": int(n), "share_%": round(n / len(g) * 100, 2),
                             "location_quotient": round((n / len(g)) / base.get(name, np.nan), 2), "mean_citations": round(s.cit.mean(), 1), "median_citations": float(s.cit.median()),
                             "mean_fwci": round(s.fwci.mean(), 2), "total_citations": int(s.cit.sum()), "median_year": float(s.yr.median())})
    d = pd.DataFrame(rows)
    d.to_csv(IN / "specialisation.csv", index=False)
    return d


def venue_explorer(pi):
    rows = []
    for (i, v, f), g in pi.groupby(["institution", "journal_name", "field"]):
        if not v:
            continue
        rows.append({"institution": i, "venue": v, "field": f, "type": g.type.mode().iat[0], "papers": len(g), "citations": int(g.cit.sum()), "mean_fwci": round(g.fwci.mean(), 2),
                     "quartile": g.quartile.mode().iat[0], "quartile_source": g.get("quartile_source", pd.Series([""])).mode().iat[0] if "quartile_source" in g else ""})
    d = pd.DataFrame(rows).sort_values("papers", ascending=False)
    d.to_csv(IN / "venue_explorer.csv", index=False)
    return d


def mix_by_year(pi):
    rows = []
    for i in INSTS:
        g = pi[pi.institution == i]
        for y, x in g.groupby("yr"):
            j = x[(x.type == "journal") & x.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
            rows.append({"institution": i, "year": int(y), "papers": len(x), "journal": int((x.type == "journal").sum()), "conference": int((x.type == "conference").sum()),
                         "conference_share_%": round((x.type == "conference").mean() * 100, 1), "journal_ranked": len(j), "journal_Q1": int((j.quartile == "Q1").sum()),
                         "journal_Q1_share_%": round((j.quartile == "Q1").mean() * 100, 1) if len(j) else None,
                         "mean_fwci": round(x.fwci.mean(), 2), "partial_year": bool(y == 2026)})
    d = pd.DataFrame(rows)
    d["growth_vs_previous_year_%"] = d.groupby("institution").papers.pct_change().mul(100).round(1)
    d.to_csv(IN / "publication_mix_by_year.csv", index=False)
    return d


def main():
    IN.mkdir(exist_ok=True)
    m, p, pi = load()
    comp = institute_comparison(m, p, pi)
    print(comp.set_index("institution").T.to_string())
    print(json.dumps(h_index_size_test(pi)["institutes"], indent=0))
    c = concentration(m, pi)
    print({i: (c[i]["gini_full"], c[i]["faculty_top1_5_10_share_full"], c[i]["paper_top1_5_10_share"]) for i in INSTS})
    print(reviews(pi).to_string(index=False))
    print(json.dumps(surge(m, pi), indent=0, default=float)[:1200])
    print(quartile_impact(pi).head(8).to_string(index=False))
    print(team_size(m, p, pi).to_string(index=False))
    print(connectivity_vs_impact(m))
    specialisation(pi)
    venue_explorer(pi)
    mix_by_year(pi)


if __name__ == "__main__":
    main()
