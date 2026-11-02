"""Step 10: publication statistics per institute. Writes data/out/stats/*.csv and
data/out/stats/publication_results.json. Only uses data we already have."""
import json

import numpy as np
import pandas as pd

import config

OUT, STATS = config.OUT_DIR, config.OUT_DIR / "stats"
STATS.mkdir(exist_ok=True)
INSTS = list(config.INSTITUTES)


def main():
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str})
    authors = pd.read_csv(OUT / "authors.csv")
    res = {}

    def of(inst):
        return p[p.our_institutes.fillna("").str.contains(inst, regex=False)]

    # ---------- 1. papers per year (a paper with 2 of our institutes counts for both)
    yr = pd.DataFrame({i: of(i).groupby("year").size() for i in INSTS}).fillna(0).astype(int)
    yr["all (unique papers)"] = p.groupby("year").size()
    yr.to_csv(STATS / "papers_per_year.csv")
    cagr = {}
    for i in INSTS:
        a, b = yr.loc[2016, i], yr.loc[2025, i]
        cagr[i] = round(((b / a) ** (1 / 9) - 1) * 100, 1)
    res["papers_per_year"] = yr.to_dict()
    res["growth_2016_to_2025_cagr_%"] = cagr
    res["totals"] = {i: len(of(i)) for i in INSTS} | {"unique_papers": len(p)}

    # ---------- 2. types
    res["type_split"] = {i: of(i).type.value_counts().to_dict() for i in INSTS}

    # ---------- 3. quartiles (journals) and CORE (conferences)
    qs = {}
    for i in INSTS:
        j = of(i)[of(i).type == "journal"]
        withq = j[j.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]       # "Unranked" = no Scopus/SCImago rank exists
        sh = withq.quartile.value_counts(normalize=True).reindex(["Q1", "Q2", "Q3", "Q4"]).fillna(0) * 100
        byyr = withq.groupby("year").apply(lambda g: round((g.quartile == "Q1").mean() * 100, 1))
        qs[i] = {"journal_papers": len(j), "with_quartile": len(withq),
                 "match_rate_%": round(len(withq) / len(j) * 100, 1), "unranked": len(j) - len(withq),
                 "Q1_fraction_%": round(sh["Q1"], 1), "shares_%": sh.round(1).to_dict(),
                 "Q1_fraction_by_year_%": byyr.to_dict()}
    res["quartiles"] = qs
    core = {}
    for i in INSTS:
        c = of(i)[of(i).type == "conference"]
        is_core = c.quartile.isin(["A*", "A", "B", "C"])
        is_q = c.quartile.isin(["Q1", "Q2", "Q3", "Q4"])          # conference book series with a Scopus CiteScore quartile
        core[i] = {"conference_papers": len(c), "with_CORE_rank": int(is_core.sum()),
                   "rank_counts": c[is_core].quartile.value_counts().to_dict(),
                   "with_scopus_quartile": int(is_q.sum()), "scopus_quartile_counts": c[is_q].quartile.value_counts().to_dict(),
                   "unranked": int((~is_core & ~is_q).sum())}
    res["conference_rank"] = core

    # ---------- 4. top journals, top conference venues
    tj, tc = {}, {}
    for i in INSTS:
        s = of(i)
        j = s[s.type == "journal"].groupby("journal_name").agg(
            papers=("year", "size"), citations=("citations", "sum"),
            quartile=("quartile", lambda x: x.mode().iat[0] if x.notna().any() and len(x.mode()) else "")) \
            .sort_values("papers", ascending=False)
        tj[i] = j.head(5).reset_index().to_dict("records")
        j.head(20).to_csv(STATS / f"top_journals_{i.replace(' ', '_')}.csv")
        c = s[s.type == "conference"].journal_name.value_counts().head(5)
        tc[i] = c.to_dict()
    res["top5_journals"] = tj
    res["top5_conference_venues"] = tc

    # ---------- 5. citations & most cited
    cit, top10 = {}, {}
    for i in INSTS:
        s = of(i)
        cit[i] = {"total_citations": int(s.citations.sum()), "mean_per_paper": round(s.citations.mean(), 2),
                  "median": float(s.citations.median()),
                  "uncited_%": round((s.citations == 0).mean() * 100, 1),
                  "papers_with_100plus": int((s.citations >= 100).sum()),
                  "share_of_citations_from_top_1%_papers_%": round(
                      s.citations.nlargest(max(1, len(s) // 100)).sum() / s.citations.sum() * 100, 1),
                  "mean_citations_by_year": s.groupby("year").citations.mean().round(1).to_dict()}
        top10[i] = s.nlargest(10, "citations")[["title", "journal_name", "year", "citations", "doi"]] \
            .to_dict("records")
        s.nlargest(10, "citations")[["title", "journal_name", "year", "citations", "doi"]] \
            .to_csv(STATS / f"top10_cited_{i.replace(' ', '_')}.csv", index=False)
    res["citations"] = cit
    res["top10_most_cited"] = top10

    # ---------- 6. authors / h-index
    ha = {}
    for i in INSTS:
        a = authors[authors.institution == i]
        c = a[a.is_core_author]
        ha[i] = {"authors_in_data": len(a), "core_authors(inferred faculty)": len(c),
                 "core_h_index_quantiles(min,25,50,75,90,max)": [int(x) for x in c.h_index.quantile(
                     [0, .25, .5, .75, .9, 1])],
                 "core_h_index_mean": round(c.h_index.mean(), 1),
                 "core_papers_median": float(c.papers.median()),
                 "core_authors_share_of_all_author_rows_%": None,
                 "top10_by_h_index": c.nlargest(10, "h_index")[
                     ["author", "h_index", "papers", "total_citations", "main_field"]].to_dict("records"),
                 "top5_by_papers": c.nlargest(5, "papers")[["author", "papers", "h_index"]].to_dict("records")}
        # share of papers written with at least one core author
        auth = pd.read_csv(OUT / "group15_data.csv", usecols=["institution", "openalex_work_id", "is_core_author"])
        g = auth[auth.institution == i].groupby("openalex_work_id").is_core_author.any()
        ha[i]["papers_with_at_least_one_core_author_%"] = round(g.mean() * 100, 1)
        # h-index histogram
        bins = [0, 1, 3, 5, 8, 12, 20, 200]
        ha[i]["core_h_index_histogram"] = pd.cut(c.h_index, bins, right=False).value_counts().sort_index() \
            .rename(lambda x: f"{int(x.left)}-{int(x.right) - 1}").to_dict()
        a.sort_values("papers", ascending=False).to_csv(STATS / f"authors_{i.replace(' ', '_')}.csv", index=False)
    res["authors"] = ha

    # ---------- 7. research areas
    ra = {}
    for i in INSTS:
        s = of(i)
        ra[i] = {"fields_top8_%": (s.field.value_counts(normalize=True).head(8) * 100).round(1).to_dict(),
                 "domains_%": (s.domain.value_counts(normalize=True) * 100).round(1).to_dict(),
                 "field_missing_%": round(s.field.isna().mean() * 100, 1)}
        # fields by mean citations (min 50 papers)
        f = s.groupby("field").agg(papers=("year", "size"), mean_cites=("citations", "mean"))
        ra[i]["highest_mean_citations_fields(min 50 papers)"] = f[f.papers >= 50].mean_cites.round(1) \
            .sort_values(ascending=False).head(4).to_dict()
    res["research_areas"] = ra

    # ---------- 8. data-quality facts
    res["data_quality"] = {
        "papers_without_doi": int(p.doi.isna().sum()), "papers_without_source": int(p.journal_name.isna().sum()),
        "papers_without_field": int(p.field.isna().sum()),
        "2026_is_partial_year": True,
        "pubs_with_more_than_30_authors": int((p.n_authors > 30).sum()),
        "max_authors_on_one_paper": int(p.n_authors.max()),
    }
    (STATS / "publication_results.json").write_text(json.dumps(res, indent=1, default=str))
    print("ok")


if __name__ == "__main__":
    main()
