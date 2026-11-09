"""Step 5c: take retracted and withdrawn papers out of the analysis corpus, and keep them flagged in a separate table.

Why: a retracted paper should not count towards h-index, citations, Q1 share, rankings or collaboration links.
They are not deleted from the project: every removed row is kept, with the reason, in group15_retracted.csv.

Which papers
  data/ref/retracted_papers.csv   curated list, checked by hand on 2026-11-08: every paper OpenAlex flags as retracted
                                  (work_extras.csv, is_retracted) was confirmed with Crossref / the publisher's notice,
                                  plus papers whose title says WITHDRAWN. Columns: status, retraction_date, reason_category,
                                  reason_detail (Retraction Watch database or the publisher's notice), author_response.
  work_extras.csv is_retracted    any paper OpenAlex flags later and that is not yet in the list is removed too and
                                  reported as 'OpenAlex flag, not yet checked', so a new download is never silently counted.

Removes the papers from data/out/: group15_data.csv, papers_enriched.csv, authorships.csv and, when they exist,
citation_network_with_outside.csv (written by outflow.py). Writes
  group15_retracted.csv          the removed group15_data rows + is_retracted, status and reason columns
  stats/retractions.json         counts per institute, reason category and citations removed (dashboard, report)

Runs after corpus_filter.py (./run_all.sh faculty step) and can be rerun: papers already removed stay in
group15_retracted.csv. The aggregate citation-flow tables of outflow.py / inflow.py are rebuilt from the narrowed
corpus only when those steps rerun (they need data/raw/).
"""
import json

import pandas as pd

import config

OUT = config.OUT_DIR
REF = config.ROOT / "data" / "ref" / "retracted_papers.csv"
KEPT = OUT / "group15_retracted.csv"
STATS = OUT / "stats"


def retracted_list():
    ref = pd.read_csv(REF, dtype=str, keep_default_na=False)
    ex = OUT / "work_extras.csv"
    if ex.exists():
        w = pd.read_csv(ex, dtype=str, usecols=["openalex_work_id", "is_retracted"])
        new = sorted(set(w[w.is_retracted.str.lower() == "true"].openalex_work_id) - set(ref.openalex_work_id))
        if new:
            ref = pd.concat([ref, pd.DataFrame({"openalex_work_id": new, "status": "retracted",
                                                "reason_category": "OpenAlex flag, not yet checked"})], ignore_index=True).fillna("")
    return ref.set_index("openalex_work_id")


def main():
    lst = retracted_list()
    ids = set(lst.index)
    wid = lambda s: s.astype(str).str.split("/").str[-1]

    g = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    hit = wid(g.openalex_work_id).isin(ids)
    removed = g[hit].copy()
    removed["is_retracted"] = "TRUE"
    if KEPT.exists():                       # earlier run: keep what was removed then
        old = pd.read_csv(KEPT, dtype=str, keep_default_na=False)
        removed = pd.concat([old, removed], ignore_index=True).drop_duplicates(["openalex_work_id", "institution", "faculty_name"], keep="last")
    # status and reason always come from the current list, so a corrected reason reaches papers removed in earlier runs
    w = wid(removed.openalex_work_id)
    for c in ("status", "retraction_date", "reason_category", "reason_detail", "author_response"):
        removed["retraction_" + c if not c.startswith("retraction") else c] = w.map(lst[c]).fillna("") if c in lst else ""
    removed.to_csv(KEPT, index=False)
    g[~hit].to_csv(OUT / "group15_data.csv", index=False)

    p = pd.read_csv(OUT / "papers_enriched.csv", dtype=str, keep_default_na=False)
    pids = set(p[p.openalex_work_id.isin(ids)].doi.str.strip()) - {""} | {f"openalex:{x}" for x in ids}
    p[~p.openalex_work_id.isin(ids)].to_csv(OUT / "papers_enriched.csv", index=False)

    a = pd.read_csv(OUT / "authorships.csv", dtype=str, keep_default_na=False)
    a[~a.openalex_work_id.isin(ids)].to_csv(OUT / "authorships.csv", index=False)

    cw = OUT / "citation_network_with_outside.csv"
    if cw.exists():
        c = pd.read_csv(cw, dtype=str, keep_default_na=False)
        dois = pids | set(removed.doi) - {""}
        c[~(c.source_doi.isin(dois) | c.target_doi.isin(dois))].to_csv(cw, index=False)

    papers = removed.drop_duplicates("openalex_work_id")
    papers = papers.assign(citations=pd.to_numeric(papers.citations, errors="coerce").fillna(0).astype(int))
    per_inst = removed.drop_duplicates(["openalex_work_id", "institution"]).assign(
        citations=lambda d: pd.to_numeric(d.citations, errors="coerce").fillna(0).astype(int))
    res = {
        "papers_removed": int(len(papers)),
        "citations_of_removed_papers": int(papers.citations.sum()),
        "by_status": papers.retraction_status.value_counts().to_dict(),
        "by_reason_category": papers.retraction_reason_category.value_counts().to_dict(),
        "by_institution": {i: {"papers": int(len(d)), "citations": int(d.citations.sum())} for i, d in per_inst.groupby("institution")},
        "faculty_rows_removed": int(len(removed)),
        "source": "data/ref/retracted_papers.csv (Crossref, Retraction Watch database and publisher notices, checked 2026-11-08)",
        "papers": [{"wid": r.openalex_work_id.split("/")[-1], "inst": r.institution, "title": r.title, "year": r.year, "cites": int(r.citations),
                    "doi": r.doi, "status": r.retraction_status, "category": r.retraction_reason_category,
                    "faculty": "; ".join(sorted(set(removed[removed.openalex_work_id == r.openalex_work_id].faculty_name)))}
                   for r in papers.sort_values("citations", ascending=False).itertuples()],
    }
    STATS.mkdir(exist_ok=True)
    (STATS / "retractions.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"retracted/withdrawn papers removed: {res['papers_removed']} ({res['citations_of_removed_papers']} citations), "
          f"faculty rows {res['faculty_rows_removed']} -> {KEPT.name}")
    for i, v in res["by_institution"].items():
        print(f"  {i}: {v['papers']} papers, {v['citations']} citations")


if __name__ == "__main__":
    main()
