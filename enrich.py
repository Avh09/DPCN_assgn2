"""Steps 5, 6 and 9 (local version, no API calls).

* is_core_author : inferred faculty (>= CORE_MIN_PAPERS papers over >= CORE_MIN_YEARS
                   different years at that institute). Official faculty lists are not
                   available yet, so this is a proxy and is labelled as such.
* h_index        : computed from the citations of the author's papers in OUR corpus.
* quartile       : journals -> approximate SJR quartile (see sjr_quartiles());
                   conferences -> CORE rank (A*/A/B/C).
Writes data/out/authors.csv and data/out/group15_data.csv.
"""
import csv
import io
import re

import pandas as pd
import requests
from rapidfuzz import fuzz, process

import config

CORE_MIN_PAPERS, CORE_MIN_YEARS = 10, 3
REF = config.ROOT / "data" / "ref"


def h_index(cites):
    c = sorted(cites, reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


# ---------------------------------------------------------------- quartiles
def sjr_quartiles():
    """{issn8: {year: 'Q1'..'Q4'}} from the SCImago SJR values (mirror of scimagojr.com).

    The mirror has SJR per journal, year and BROAD subject area (27 ASJC areas) but no
    quartile column, so quartiles are recomputed: within each (year, area) journals are
    ranked by SJR and split into four equal parts; a journal in several areas gets its
    best quartile. This is close to, but not identical to, SCImago's own quartiles
    (those use ~300 narrower categories).
    """
    d = pd.read_csv(REF / "sjr_all.csv", low_memory=False,
                    usecols=["field", "year", "SJR", "Issn", "Sourceid"])
    d = d[d.year >= 2014].dropna(subset=["SJR"])
    d["rank_pct"] = d.groupby(["year", "field"]).SJR.rank(ascending=False, method="first") \
        .sub(1).div(d.groupby(["year", "field"]).SJR.transform("size"))
    d["q"] = pd.cut(d.rank_pct, [-1, .25, .5, .75, 2], labels=[1, 2, 3, 4], right=False).astype(int)
    best = d.groupby(["Sourceid", "year"]).agg(q=("q", "min"), Issn=("Issn", "first")).reset_index()
    out = {}
    for sid, yr, q, issns in best[["Sourceid", "year", "q", "Issn"]].itertuples(index=False):
        for i in str(issns).replace(" ", "").split(","):
            if i:
                out.setdefault(i, {})[int(yr)] = f"Q{q}"
    return out


def lookup_quartile(q_by_issn, issn_l, issn_all, year):
    issns = {x.replace("-", "") for x in str(issn_all).split(";") if x and x != "nan"}
    if isinstance(issn_l, str):
        issns.add(issn_l.replace("-", ""))
    for i in issns:
        yrs = q_by_issn.get(i)
        if yrs:
            y = min(yrs, key=lambda k: abs(k - min(int(year), max(yrs))))  # nearest year
            return yrs[y]
    return ""


# -------------------------------------------------------------- CORE ranks
def norm_conf(s):
    s = str(s).lower()
    s = re.sub(r"\b(19|20)\d\d\b", " ", s)
    s = re.sub(r"\b\d+(st|nd|rd|th)\b", " ", s)
    s = re.sub(r"\b(proceedings|proceeding|of|the|in|on|and|annual|international|intl|ieee|acm)\b", " ", s)
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def core_ranks(names):
    r = requests.get("https://portal.core.edu.au/conf-ranks/",
                     params={"search": "", "by": "all", "source": "CORE2023", "sort": "atitle", "do": "Export"},
                     timeout=60)
    (REF / "core.csv").write_text(r.text)
    rows = [x for x in csv.reader(io.StringIO(r.text)) if len(x) > 4 and x[4] in ("A*", "A", "B", "C")]
    core = {norm_conf(x[1]): x[4] for x in rows if norm_conf(x[1])}
    keys = list(core)
    out = {}
    for n in names:
        nn = norm_conf(n)
        if len(nn) < 8:
            continue
        m = process.extractOne(nn, keys, scorer=fuzz.token_sort_ratio, score_cutoff=90)
        if m:
            out[n] = core[m[0]]
    return out


# --------------------------------------------------------------------- main
def main():
    a, b = config.OUT_DIR / "authorships.csv", config.OUT_DIR / "all_authors" / "authorships.csv"
    if b.exists() and a.stat().st_size < b.stat().st_size:
        raise SystemExit("authorships.csv is the narrowed (faculty-only) copy left by corpus_filter.py: run build_tables.py first")
    papers = pd.read_csv(config.OUT_DIR / "papers.csv", dtype={"issn": str})
    auth = pd.read_csv(config.OUT_DIR / "authorships.csv", usecols=[
        "openalex_work_id", "author_id", "author_name", "orcid", "is_our_inst", "our_inst"])

    # ~6% of our-institute authorships have no OpenAlex author id: fall back to the name
    auth["author_id"] = auth.author_id.fillna("NAME:" + auth.author_name.str.lower().str.strip())

    # quartile / rank per paper
    q_by_issn = sjr_quartiles()
    papers["quartile"] = ""
    j = papers.type == "journal"
    papers.loc[j, "quartile"] = [lookup_quartile(q_by_issn, a, b, y) for a, b, y in
                                 zip(papers.loc[j, "issn"], papers.loc[j, "issn_all"], papers.loc[j, "year"])]
    c = papers.type == "conference"
    cr = core_ranks(papers.loc[c, "journal_name"].dropna().unique())
    papers.loc[c, "quartile"] = papers.loc[c, "journal_name"].map(cr).fillna("")
    papers.to_csv(config.OUT_DIR / "papers_enriched.csv", index=False)
    print("journal quartile match:", round((papers.loc[j, "quartile"] != "").mean() * 100, 1), "%;",
          "conference CORE match:", round((papers.loc[c, "quartile"] != "").mean() * 100, 1), "%")

    # author x institute x paper
    o = auth[auth.is_our_inst].copy()
    o["our_inst"] = o.our_inst.str.split(";")
    o = o.explode("our_inst").rename(columns={"our_inst": "institution"})
    o = o.merge(papers[["openalex_work_id", "year", "citations", "field"]], on="openalex_work_id")

    # authors table
    def mode(s):
        s = s.dropna()
        return s.mode().iat[0] if len(s) else ""
    rows = []
    for (inst, aid), g in o.groupby(["institution", "author_id"]):
        rows.append({
            "institution": inst, "author_id": aid,
            "author": g.author_name.mode().iat[0], "orcid": mode(g.orcid),
            "papers": g.openalex_work_id.nunique(), "years_active": g.year.nunique(),
            "first_year": g.year.min(), "last_year": g.year.max(),
            "total_citations": int(g.drop_duplicates("openalex_work_id").citations.sum()),
            "h_index": h_index(g.drop_duplicates("openalex_work_id").citations),
            "main_field": mode(g.field),
        })
    authors = pd.DataFrame(rows)
    authors["is_core_author"] = (authors.papers >= CORE_MIN_PAPERS) & (authors.years_active >= CORE_MIN_YEARS)
    authors.sort_values(["institution", "papers"], ascending=[True, False]).to_csv(
        config.OUT_DIR / "authors.csv", index=False)
    print(authors.groupby("institution").is_core_author.agg(["sum", "size"]))

    # final main file
    d = o.merge(papers, on="openalex_work_id", suffixes=("", "_p"))
    d = d.merge(authors[["institution", "author_id", "is_core_author", "h_index"]],
                on=["institution", "author_id"])
    d = d.rename(columns={"author_name": "author", "year": "year", "citations": "citations"})
    d["group"] = config.GROUP
    # co-author institutions of the paper as seen from this row's institute: everything on the paper except
    # the row's own institute, so a MANIT row lists NIT Silchar when a NIT Silchar author is on the paper
    other = [";".join(x for x in str(o_).split(";") if x and x != "nan" and x != inst)
             for o_, inst in zip(d.our_institutes, d.institution)]
    d["coauthor_institutes"] = [";".join(x for x in (str(a) if isinstance(a, str) else "", b) if x)
                                for a, b in zip(d.coauthor_institutes, other)]
    d["cites_indian_inst"] = ""   # needs the OpenAlex citation lookups (links.py)
    d["cited_by_indian_inst"] = ""
    cols = ["group", "institution", "author", "title", "year", "type", "journal_name", "issn", "doi",
            "citations", "quartile", "coauthor_institutes", "cites_indian_inst", "cited_by_indian_inst",
            "openalex_work_id", "author_id", "is_core_author", "field", "domain"]
    d = d.rename(columns={"title": "title"})[cols] if "title" in d else d
    # OpenAlex sometimes lists the same author twice on one paper (121 papers): keep one row
    d = d.drop_duplicates(["openalex_work_id", "author_id", "institution"])
    d.sort_values(["institution", "year", "openalex_work_id"]).to_csv(config.OUT_DIR / "group15_data.csv", index=False)
    print("group15_data.csv rows:", len(d))


if __name__ == "__main__":
    main()
