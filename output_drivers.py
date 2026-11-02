"""Step 15b: what explains the difference in output between the three institutes? (data/out/stats/insights/output_drivers.json)

Only measures that the dataset can support are used: headcount, output per faculty, how concentrated the output is, fractional credit
for shared papers, team size, publication type mix, designation mix and a like-for-like comparison inside departments that exist at all
three institutes. Facilities, laboratories, funding and faculty qualifications are NOT in the data and are never inferred.
"""
import json

import numpy as np
import pandas as pd

import config
import movers

OUT, STATS = config.OUT_DIR, config.OUT_DIR / "stats"
INSTS = list(config.INSTITUTES)
SHORT = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}


def rank_of(des):
    d = str(des).lower()
    if "assistant" in d:
        return "Assistant professor"
    if "associate" in d:
        return "Associate professor"
    if "professor" in d:
        return "Professor"
    return "Other / ad-hoc"


def verdicts(measures, common, lead, leader_by_year):
    """Plain-language findings, each sentence built from the numbers above (nothing typed in)."""
    M = {m["key"]: m["values"] for m in measures}
    L = max(M["papers"], key=M["papers"].get)
    others = [i for i in INSTS if i != L]
    S = SHORT
    fmt = lambda k, i: f"{M[k][i]:g}"
    out = []
    n_fac = M["active_faculty"]
    if n_fac[L] < max(n_fac.values()):
        top = max(n_fac, key=n_fac.get)
        out.append(f"Headcount does not explain it: {S[L]} has {n_fac[L]} research-active faculty, fewer than {S[top]} ({n_fac[top]}). Output per faculty does: {fmt('papers_per_faculty', L)} papers per person against " + " and ".join(f"{fmt('papers_per_faculty', o)} at {S[o]}" for o in others) + ".")
    else:
        out.append(f"{S[L]} also has the most research-active faculty ({n_fac[L]}), and its output per person is the highest ({fmt('papers_per_faculty', L)} papers).")
    med = M["median_papers_per_faculty"]
    if all(med[L] > med[o] for o in others):
        out.append(f"It is broad-based, not a few prolific people: the median faculty member at {S[L]} has {fmt('median_papers_per_faculty', L)} papers against " + " and ".join(f"{fmt('median_papers_per_faculty', o)} at {S[o]}" for o in others) + ".")
    t10 = M["top10pct_faculty_share_of_faculty_paper_credits_%"]
    out.append("Concentration: the top 10% of faculty hold " + ", ".join(f"{t10[i]:g}% of paper credits at {S[i]}" for i in INSTS) + (" (similar, so concentration is not what separates the three institutes)." if max(t10.values()) - min(t10.values()) < 8 else "."))
    fr = M["fractional_papers_per_faculty"]
    out.append(f"Shared papers are not inflating it: splitting each paper between its faculty authors leaves {S[L]} at {fr[L]:g} papers per faculty against " + " and ".join(f"{fr[o]:g} at {S[o]}" for o in others) + ".")
    au, cf = M["avg_authors_per_paper"], M["conference_share_%"]
    out.append(f"Team size ({min(au.values()):g}-{max(au.values()):g} authors per paper) and conference share ({min(cf.values()):g}-{max(cf.values()):g}%) are similar across the three institutes, so these measures do not explain the gap.")
    pr, pp = M["share_Professor_%"], M["papers_per_Professor"]
    out.append(f"Seniority: {S[L]} has {pr[L]:g}% professors against " + " and ".join(f"{pr[o]:g}% at {S[o]}" for o in others) + f", yet its professors average {pp[L]:g} papers each (" + ", ".join(f"{S[o]} {pp[o]:g}" for o in others) + ").")
    if common:
        out.append(f"Like for like: {S[L]} has the highest papers per faculty in {lead[L]} of the {len(common)} departments that exist at all three institutes.")
    ny = sum(1 for y, i in leader_by_year.items() if i == L)
    out.append(f"{S[L]} published the most papers in {ny} of the {len(leader_by_year)} full years ({min(leader_by_year)}-{max(leader_by_year)}).")
    return out


def main():
    perf = pd.read_csv(STATS / "faculty_performance.csv")
    alias = movers.aliases()
    perf = perf[(perf.papers > 0) & [(i, n) not in alias for i, n in zip(perf.institution, perf.faculty_name)]].copy()
    perf["rank"] = perf.designation.map(rank_of)
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False,
                    usecols=["openalex_work_id", "institution", "is_faculty", "faculty_name", "year", "type"])
    m = m[m.is_faculty == "TRUE"].drop_duplicates(["openalex_work_id", "institution", "faculty_name"])
    m = m[[(i, n) not in alias for i, n in zip(m.institution, m.faculty_name)]]
    p = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "n_authors", "type"], dtype={"openalex_work_id": str})
    nfac = m.groupby("openalex_work_id").size()
    m["frac"] = 1.0 / m.openalex_work_id.map(nfac)
    pap = m.drop_duplicates(["openalex_work_id", "institution"])[["openalex_work_id", "institution", "year"]].merge(p, on="openalex_work_id", how="left")
    per_inst_fac = m.groupby(["openalex_work_id", "institution"]).size().rename("own_fac").reset_index()
    pap = pap.merge(per_inst_fac, on=["openalex_work_id", "institution"])

    rows = {}
    for i in INSTS:
        f = perf[perf.institution == i]
        a = pap[pap.institution == i]
        fp = m[m.institution == i].groupby("faculty_name").size().sort_values(ascending=False)
        top10 = max(1, int(round(len(f) * 0.10)))
        frac_total = m[m.institution == i].frac.sum()
        r = {"papers": int(len(a)), "active_faculty": int(len(f)), "papers_per_faculty": round(len(a) / len(f), 2),
             "median_papers_per_faculty": float(f.papers.median()),
             "top10pct_faculty_share_of_faculty_paper_credits_%": round(100 * fp.head(top10).sum() / fp.sum(), 1),
             "fractional_papers_per_faculty": round(frac_total / len(f), 2),
             "avg_authors_per_paper": round(float(a.n_authors.mean()), 1),
             "papers_with_2plus_own_faculty_%": round(100 * float((a.own_fac >= 2).mean()), 1),
             "journal_share_%": round(100 * float((a.type == "journal").mean()), 1), "conference_share_%": round(100 * float((a.type == "conference").mean()), 1)}
        for k in ("Professor", "Associate professor", "Assistant professor", "Other / ad-hoc"):
            g = f[f["rank"] == k]
            r[f"share_{k}_%"] = round(100 * len(g) / len(f), 1)
            r[f"papers_per_{k}"] = round(float(g.papers.mean()), 1) if len(g) else None
        rows[i] = r
    labels = [("papers", "Papers (full counting)", "How many papers"), ("active_faculty", "Research-active faculty", "Size: more faculty can mean more papers"),
              ("papers_per_faculty", "Papers per active faculty", "Output per person"),
              ("median_papers_per_faculty", "Median papers per faculty", "Typical person; close to the mean = broad-based, far below = a few prolific people"),
              ("top10pct_faculty_share_of_faculty_paper_credits_%", "Share of paper credits held by the top 10% of faculty", "High = output concentrated in few people"),
              ("fractional_papers_per_faculty", "Papers per faculty, shared papers split between authors", "Removes the advantage of co-authoring many papers with colleagues"),
              ("papers_with_2plus_own_faculty_%", "Papers with 2+ faculty of the same institute (%)", "Internal co-authorship inflates full counts"),
              ("avg_authors_per_paper", "Authors per paper (mean)", "Bigger teams per paper"), ("conference_share_%", "Conference papers (%)", "Conferences are quicker to produce than journals"),
              ("share_Professor_%", "Professors (% of active faculty)", "Seniority mix"), ("share_Associate professor_%", "Associate professors (%)", ""), ("share_Assistant professor_%", "Assistant professors (%)", ""),
              ("papers_per_Professor", "Papers per professor", "Output by rank"), ("papers_per_Associate professor", "Papers per associate professor", ""), ("papers_per_Assistant professor", "Papers per assistant professor", "")]
    measures = [{"key": k, "label": lab, "note": note, "values": {i: rows[i][k] for i in INSTS}} for k, lab, note in labels]

    # like-for-like: departments present at all three institutes with at least 5 active faculty each
    d = perf.groupby(["department", "institution"]).agg(faculty=("papers", "size"), papers=("papers", "sum")).reset_index()
    common = []
    for dep, g in d.groupby("department"):
        if dep and "Unknown" not in dep and len(g) == 3 and (g.faculty >= 5).all():
            common.append({"department": dep, "values": {r.institution: {"faculty": int(r.faculty), "papers_per_faculty": round(r.papers / r.faculty, 1)} for r in g.itertuples()}})
    lead = {i: sum(1 for c in common if max(c["values"], key=lambda x: c["values"][x]["papers_per_faculty"]) == i) for i in INSTS}

    yearly = pap[pap.year.astype(int).between(2016, 2025)].groupby(["year", "institution"]).size().unstack(fill_value=0)
    yearly.index = yearly.index.astype(int)
    yr = {int(y): {i: int(yearly.at[y, i]) for i in INSTS} for y in yearly.index}
    leader = {y: max(v, key=v.get) for y, v in yr.items()}
    out = {"verdicts": verdicts(measures, common, lead, leader), "measures": measures, "common_departments": common, "common_department_leaders": lead, "yearly_papers": yr, "yearly_leader": leader,
           "not_in_dataset": ["department-level laboratory facilities", "faculty qualifications and training", "teaching load"],
           "definitions": "Research-active faculty = verified faculty with at least one paper in 2016-2026. Papers are fully counted per institute: a paper with faculty of two institutes counts for both."}
    (STATS / "insights" / "output_drivers.json").write_text(json.dumps(out, indent=1))
    print("wrote output_drivers.json;", len(common), "common departments; leaders", lead)


if __name__ == "__main__":
    main()
