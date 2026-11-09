"""Faculty whose affiliation was checked by hand: how much of their institute's numbers depend on them? (stats/affiliation_checks.json)

The professor asked to check the status of Prof. Kumarasamy Sudhakar, whose papers alone move MANIT's h-index. The checked facts
(status, year he left or went on leave, the other employer, evidence and sources) are in data/ref/faculty_status_checks.csv; this
script adds what the data says, so every number on the dashboard is computed, not typed in:

  per year        the person's papers in the corpus, and how many also list the other employer for him on the same paper
                  (OpenAlex institution names of his own authorship, authorships.csv)
  sensitivity     the institute h-index and citations three ways: all papers / his papers only up to the year he left /
                  without any of his papers; plus his share of the institute's papers and citations

The papers stay in the corpus: they carry the institute's name, so they are correctly attributed by the brief's rule. The point
is to show readers how much one person on leave contributes. Runs offline after faculty_stats.py.
"""
import json

import pandas as pd

import config
from metrics_defs import h_index

OUT = config.OUT_DIR
REF = config.ROOT / "data" / "ref" / "faculty_status_checks.csv"
STATS = OUT / "stats"


def main():
    checks = pd.read_csv(REF, dtype=str, keep_default_na=False)
    g = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    g["citations"] = pd.to_numeric(g.citations, errors="coerce").fillna(0).astype(int)
    g["year"] = g.year.astype(int)
    a = pd.read_csv(OUT / "authorships.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "author_id", "author_name", "institution_names"])
    amap = pd.read_csv(OUT / "author_faculty_map.csv", dtype=str, keep_default_na=False)
    perf = pd.read_csv(STATS / "faculty_performance.csv")
    out = []
    for c in checks.itertuples(index=False):
        inst = g[g.institution == c.institution].drop_duplicates("openalex_work_id")
        mine = g[(g.institution == c.institution) & (g.faculty_name == c.faculty_name)].drop_duplicates("openalex_work_id")
        # his own authorship rows: matched author ids, or NAME: keys (records without an OpenAlex id)
        keys = amap[(amap.institution == c.institution) & (amap.faculty_name == c.faculty_name)].author_id
        ids = {k for k in keys if not k.startswith("NAME:")}
        names = {k[5:] for k in keys if k.startswith("NAME:")}
        own = a[a.openalex_work_id.isin(mine.openalex_work_id) & (a.author_id.isin(ids) | a.author_name.str.lower().str.strip().isin(names))]
        dual_w = set(own[own.institution_names.str.contains(c.other_affiliation_match, case=False)].openalex_work_id)
        away = int(c.away_since_year)
        later = set(mine[mine.year > away].openalex_work_id)
        years = [{"year": int(y), "papers": int(len(d)), "also_other_affiliation": int(d.openalex_work_id.isin(dual_w).sum())}
                 for y, d in mine.groupby("year")]
        p = perf[(perf.institution == c.institution) & (perf.faculty_name == c.faculty_name)]
        rank_h = int((perf[perf.institution == c.institution].h_index > p.h_index.iloc[0]).sum() + 1) if len(p) else None
        out.append({
            "institution": c.institution, "faculty": c.faculty_name, "checked": c.checked, "status": c.status_found,
            "away_since": away, "other_affiliation": c.other_affiliation, "evidence": c.evidence,
            "sources": [s.strip() for s in c.sources.split(";") if s.strip()],
            "papers": int(len(mine)), "citations": int(mine.citations.sum()),
            "faculty_h_index": int(p.h_index.iloc[0]) if len(p) else None, "rank_by_h_in_institute": rank_h,
            "papers_after_away_year": int(len(later)),
            "papers_after_away_year_with_other_affiliation": int(len(later & dual_w)),
            "share_of_institute_papers_%": round(100 * len(mine) / len(inst), 1),
            "share_of_institute_citations_%": round(100 * mine.citations.sum() / inst.citations.sum(), 1),
            "institute_h_index": {
                "all_papers": h_index(inst.citations.tolist()),
                f"his_papers_up_to_{away}_only": h_index(inst[~inst.openalex_work_id.isin(later)].citations.tolist()),
                "without_his_papers": h_index(inst[~inst.openalex_work_id.isin(mine.openalex_work_id)].citations.tolist())},
            "institute_citations": {
                "all_papers": int(inst.citations.sum()),
                f"his_papers_up_to_{away}_only": int(inst[~inst.openalex_work_id.isin(later)].citations.sum()),
                "without_his_papers": int(inst[~inst.openalex_work_id.isin(mine.openalex_work_id)].citations.sum())},
            "by_year": years,
        })
    STATS.mkdir(exist_ok=True)
    (STATS / "affiliation_checks.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in out:
        print(f"{r['faculty']} ({r['institution']}): {r['papers']} papers, {r['papers_after_away_year']} after {r['away_since']} "
              f"({r['papers_after_away_year_with_other_affiliation']} with {r['other_affiliation']}) | institute h-index {r['institute_h_index']}")


if __name__ == "__main__":
    main()
