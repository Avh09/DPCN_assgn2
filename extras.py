"""Step 11: extra columns and the top-30 tables asked for in the brief. Runs last (after faculty_*.py).

Adds to group15_data.csv (journal_cites_per_doc = the SCImago number behind the IF > 5 / > 10 flags):
  is_multi_author_10plus   TRUE if the paper has more than 10 authors (OpenAlex author count)
  q1_impact_gt5            TRUE if the journal is Q1 and its citations per document is above 5
  q1_impact_gt10           TRUE if the journal is Q1 and its citations per document is above 10
SCImago has no journal impact factor. Its "avg_citations" column (citations per document over
the last years) is the closest free number, so IF > 5 / IF > 10 are approximated with it. The
quartile itself is approximate too (recomputed from SJR, see enrich.py). Say so in the report.

Writes data/out/stats/top30_papers_<institute>.csv: the 30 most cited papers of each institute with
the flags above and the best h-index among the institute's faculty authors of the paper.
"""
import pandas as pd

import config

ALL = config.OUT_DIR / "all_authors"
OUT, STATS, REF = config.OUT_DIR, config.OUT_DIR / "stats", config.REF_DIR if hasattr(config, "REF_DIR") else config.ROOT / "data" / "ref"


def cites_per_doc():
    """{issn8: {year: citations per document}} from the SCImago mirror."""
    d = pd.read_csv(REF / "sjr_all.csv", low_memory=False, usecols=["year", "avg_citations", "Issn"])
    d = d[d.year >= 2014].dropna(subset=["avg_citations"])
    out = {}
    for yr, v, issns in d[["year", "avg_citations", "Issn"]].itertuples(index=False):
        for i in str(issns).replace(" ", "").split(","):
            if i:
                cur = out.setdefault(i, {})
                cur[int(yr)] = max(cur.get(int(yr), 0), float(v))
    return out


def lookup(c_by_issn, issn_l, issn_all, year):
    issns = {x.replace("-", "") for x in str(issn_all).split(";") if x and x != "nan"}
    if isinstance(issn_l, str):
        issns.add(issn_l.replace("-", ""))
    for i in issns:
        yrs = c_by_issn.get(i)
        if yrs:
            return yrs[min(yrs, key=lambda k: abs(k - min(int(year), max(yrs))))]
    return float("nan")


def tidy_blanks():
    """Say what a blank means instead of leaving it empty (the brief wants no unexplained empty cells)."""
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    n = lambda c: int((m[c] == "").sum())
    print("blank before: coauthor_institutes", n("coauthor_institutes"), "| cites_indian_inst", n("cites_indian_inst"),
          "| department", n("department"), "| field", n("field"))
    # no other institution named on the paper
    # "none" when every author on the paper has an institution in OpenAlex; "unknown" when some co-author has none
    af = ALL / "authorships.csv" if (ALL / "authorships.csv").exists() else OUT / "authorships.csv"
    a = pd.read_csv(af, usecols=["openalex_work_id", "institution_names"], keep_default_na=False)
    unknown = set(a[a.institution_names == ""].openalex_work_id)
    blank = m.coauthor_institutes == ""
    m.loc[blank, "coauthor_institutes"] = ["unknown" if w in unknown else "none" for w in m.loc[blank, "openalex_work_id"]]
    # OpenAlex lists no references for the paper, so it cannot cite another Indian institute's paper we know of
    m.loc[m.cites_indian_inst == "", "cites_indian_inst"] = "FALSE"
    # venue recorded nowhere (OpenAlex, Scopus, Crossref)
    m.loc[m.journal_name == "", "journal_name"] = "Unknown venue (not recorded)"
    # faculty with no department on any page
    m.loc[m.department == "", "department"] = "Unknown department"
    m.loc[m.faculty_status == "", "faculty_status"] = "unknown"
    for c in ["field", "domain"]:
        m.loc[m[c] == "", c] = "Unknown"
    m = apply_field_overrides(m)
    m.to_csv(OUT / "group15_data.csv", index=False)


FIELD_FILE = config.ROOT / "data" / "ref" / "field_overrides.csv"


def apply_field_overrides(df):
    """Papers OpenAlex gives no field (checked by hand, data/ref/field_overrides.csv: openalex_work_id, field, evidence)."""
    if FIELD_FILE.exists() and "field" in df.columns:
        o = pd.read_csv(FIELD_FILE, dtype=str).set_index("openalex_work_id").field.to_dict()
        hit = df.openalex_work_id.isin(o) & (df.field.isin(["", "Unknown"]) | df.field.isna())
        df.loc[hit, "field"] = df.loc[hit, "openalex_work_id"].map(o)
    return df


def main():
    STATS.mkdir(exist_ok=True)
    tidy_blanks()
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str, "issn_all": str})
    p = apply_field_overrides(p)
    c = cites_per_doc()
    p["cpd"] = [lookup(c, a, b, y) if t == "journal" else float("nan")
                for a, b, y, t in zip(p.issn, p.issn_all, p.year, p.type)]
    q1 = p.quartile.eq("Q1")
    flags = pd.DataFrame({"openalex_work_id": p.openalex_work_id,
                          "journal_cites_per_doc": p.cpd.round(2),
                          "is_multi_author_10plus": ["TRUE" if n > 10 else "FALSE" for n in p.n_authors],
                          "q1_impact_gt5": ["TRUE" if a and v > 5 else "FALSE" for a, v in zip(q1, p.cpd.fillna(0))],
                          "q1_impact_gt10": ["TRUE" if a and v > 10 else "FALSE" for a, v in zip(q1, p.cpd.fillna(0))]})
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    m = m.drop(columns=[x for x in flags.columns[1:] if x in m.columns]).merge(flags, on="openalex_work_id", how="left")
    m.to_csv(OUT / "group15_data.csv", index=False)
    print("papers with >10 authors:", int((flags.is_multi_author_10plus == "TRUE").sum()),
          "| Q1 and cites/doc > 5:", int((flags.q1_impact_gt5 == "TRUE").sum()),
          "| > 10:", int((flags.q1_impact_gt10 == "TRUE").sum()), "(of", len(flags), "papers)")

    # top 30 per institute, with the best faculty h-index among the paper's faculty authors
    fp = pd.read_csv(STATS / "faculty_performance.csv")
    h = {(r.institution, r.faculty_name): r.h_index for r in fp.itertuples()}
    m["citations_n"] = pd.to_numeric(m.citations)
    m["h"] = [h.get((i, f), 0) if f else 0 for i, f in zip(m.institution, m.faculty_name)]
    for inst in config.INSTITUTES:
        g = m[m.institution == inst]
        paper = g.groupby("openalex_work_id").agg(
            title=("title", "first"), year=("year", "first"), journal_name=("journal_name", "first"), type=("type", "first"),
            quartile=("quartile", "first"), citations=("citations_n", "first"), doi=("doi", "first"),
            faculty_authors=("faculty_name", lambda s: "; ".join(sorted({x for x in s if x}))),
            journal_cites_per_doc=("journal_cites_per_doc", "first"), venue_h_index=("venue_h_index", "first"),
            quartile_source=("quartile_source", "first"), max_faculty_h_index=("h", "max"), is_multi_author_10plus=("is_multi_author_10plus", "first"),
            q1_impact_gt5=("q1_impact_gt5", "first"), q1_impact_gt10=("q1_impact_gt10", "first"))
        top = paper.sort_values("citations", ascending=False).head(30).reset_index()
        top.insert(0, "rank", range(1, len(top) + 1))
        top.to_csv(STATS / f"top30_papers_{inst.replace(' ', '_')}.csv", index=False)
        print(inst, "top-30: citations", int(top.citations.min()), "to", int(top.citations.max()),
              "| Q1:", int((top.quartile == "Q1").sum()), "| with a faculty author:", int((top.faculty_authors != "").sum()))


if __name__ == "__main__":
    main()
