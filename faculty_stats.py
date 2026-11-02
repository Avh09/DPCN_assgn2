"""Faculty- and department-level statistics from the matched faculty (run faculty_match.py first).

A paper counts once per faculty member (even if two of their author ids are on it) and once per
department. h-index is computed from the 2016-2026 corpus only. Q1 share = Q1 papers / journal
papers that have a quartile.

Writes to data/out/stats/:
  faculty_performance.csv   one row per matched faculty member (dashboard performance table)
  department_stats.csv      one row per institute x department
  faculty_results.json      h-index distribution per institute, top faculty, comparison with core authors
"""
import json

import pandas as pd

import config
from faculty_match import h_index

OUT = config.OUT_DIR
STATS = OUT / "stats"


def q1_share(g):
    j = g[(g.type == "journal") & g.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
    return round((j.quartile == "Q1").mean() * 100, 1) if len(j) else None


def main():
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str)
    m["citations"] = pd.to_numeric(m.citations, errors="coerce").fillna(0).astype(int)
    fm = pd.read_csv(OUT / "faculty_matched.csv")
    m["department"] = m.department.fillna("").replace("", "Unknown department")
    f = m[m.is_faculty == "TRUE"].drop_duplicates(["institution", "faculty_name", "openalex_work_id"])

    rows = []
    for (inst, name), g in f.groupby(["institution", "faculty_name"]):
        j = g[g.type == "journal"].journal_name.dropna()
        rows.append({"institution": inst, "faculty_name": name, "department": g.department.iloc[0],
                     "papers": len(g), "journal_papers": int((g.type == "journal").sum()),
                     "conference_papers": int((g.type == "conference").sum()),
                     "citations": int(g.citations.sum()), "h_index": h_index(g.citations),
                     "q1_share_%": q1_share(g), "top_journal": j.mode().iloc[0] if len(j) else "",
                     "first_year": int(g.year.min()), "last_year": int(g.year.max())})
    perf = (pd.DataFrame(rows)
            .merge(fm[["institution", "faculty_name", "designation", "faculty_status", "first_seen", "last_seen",
                       "n_ids", "match_quality", "common_name"]],
                   on=["institution", "faculty_name"], how="left")
            .sort_values(["institution", "h_index", "citations"], ascending=[True, False, False]))
    perf.to_csv(STATS / "faculty_performance.csv", index=False)

    # departments: a joint appointment ("Mathematics; Bioinformatics") counts for its first department
    f = f.assign(dept=f.department.str.split("; ").str[0])
    perf["dept"] = perf.department.str.split("; ").str[0]
    listed = fm[(fm.status != "same_name_different_people") & (fm.faculty_status == "current")]
    listed = listed.assign(dept=listed.department.str.split("; ").str[0])
    drows = []
    for (inst, dept), g in f.groupby(["institution", "dept"]):
        papers = g.drop_duplicates("openalex_work_id")
        p = perf[(perf.institution == inst) & (perf.dept == dept)]
        drows.append({"institution": inst, "department": dept,
                      "faculty_listed": int(((listed.institution == inst) & (listed.dept == dept)).sum()),
                      "faculty_matched": len(p), "of_which_former": int((p.faculty_status == "former").sum()),
                      "papers": len(papers), "citations": int(papers.citations.sum()),
                      "papers_per_faculty": round(len(papers) / len(p), 1),
                      "median_h_index": float(p.h_index.median()), "max_h_index": int(p.h_index.max()),
                      "q1_share_%": q1_share(papers)})
    dept = pd.DataFrame(drows).sort_values(["institution", "papers"], ascending=[True, False])
    dept.to_csv(STATS / "department_stats.csv", index=False)

    authors = pd.read_csv(OUT / "authors.csv")
    res = {}
    for inst, p in perf.groupby("institution"):
        core = authors[(authors.institution == inst) & authors.is_core_author]
        h = p.h_index
        res[inst] = {
            "faculty_listed_today": int((listed.institution == inst).sum()), "faculty_matched": len(p),
            "matched_current": int((p.faculty_status == "current").sum()),
            "matched_former": int((p.faculty_status == "former").sum()),
            "median_h_current_only": float(p[p.faculty_status == "current"].h_index.median()),
            "h_index": {"median": float(h.median()), "p75": float(h.quantile(.75)), "p90": float(h.quantile(.9)),
                        "max": int(h.max()), "h_20_or_more": int((h >= 20).sum())},
            "h_index_histogram": h.value_counts(bins=[-1, 0, 5, 10, 15, 20, 30, 100], sort=False)
                                  .rename(lambda b: f"{int(b.left) + 1}-{int(b.right)}").to_dict(),
            "core_authors_for_comparison": {"number": len(core), "median_h": float(core.h_index.median())},
            "papers_with_a_faculty_author_%": round(
                m[(m.institution == inst) & (m.is_faculty == "TRUE")].openalex_work_id.nunique()
                / m[m.institution == inst].openalex_work_id.nunique() * 100, 1),
            "top5_by_h_index": p.head(5)[["faculty_name", "faculty_status", "department", "h_index", "papers",
                                         "citations"]].to_dict("records"),
            "top_departments_by_papers": dept[dept.institution == inst].head(5)[
                ["department", "faculty_matched", "papers", "median_h_index", "q1_share_%"]].to_dict("records"),
        }
    (STATS / "faculty_results.json").write_text(json.dumps(res, indent=1, default=str))
    for inst, r in res.items():
        print(f"\n== {inst}: {r['matched_current']} current of {r['faculty_listed_today']} listed today "
              f"+ {r['matched_former']} former faculty matched, "
              f"{r['papers_with_a_faculty_author_%']}% of papers have a faculty author")
        print("   h-index", r["h_index"], "| core authors:", r["core_authors_for_comparison"])
        print("   top:", ", ".join(f"{x['faculty_name']} ({x['h_index']})" for x in r["top5_by_h_index"]))
    pd.set_option("display.width", 200)
    print("\n", dept.to_string(index=False))


if __name__ == "__main__":
    main()
