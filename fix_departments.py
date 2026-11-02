"""Apply confirmed department corrections to the faculty lists and every output table that carries a
department, then recompute stats/department_stats.csv (same rules as faculty_stats.py).

Standard library only, so it runs without the pipeline's .venv:
    python fix_departments.py
The source lists (data/faculty/*.csv, faculty_final.csv) are corrected too, so a full ./run_all.sh rerun
keeps the change. Network-level summaries that depend on departments (cross-department edge share,
community-vs-department NMI in faculty_network_results.json) update on the next faculty_network.py run.
"""
import csv
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "out"
ST = OUT / "stats"

# (institute, faculty name) -> department, with the evidence for each correction
FIXES = {
    ("MANIT Bhopal", "Kumarasamy Sudhakar"): (
        "Energy Science and Engineering",
        "Permanent position at MANIT Bhopal (Energy Centre); currently Associate Professor, Universiti Malaysia Pahang "
        "(confirmed by the team, Oct 2026). Co-authors and papers are mainly Energy Science."),
    ("NIT Jamshedpur", "Manikant Paswan"): (
        "Mechanical Engineering",
        "NITJ Vidwan profile (nitjsr/sliet.irins.org, ID 586323): Department of Mechanical Engineering; NIRF 2021-23 lists him as a "
        "NITJ Professor. Web search found a later SLIET directorship, so his current post may differ (found Nov 2026)."),
    ("NIT Silchar", "Kh. Lakshman Singh"): (
        "Civil Engineering",
        "NIT Silchar Vidwan profile (nits.irins.org, ID 55336): Khwairakpam Lakshman Singh, Civil Engineering, transportation engineering (found Nov 2026)."),
}
UNKNOWN = {"", "Unknown department"}


def read(p):
    with open(p, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def write(p, cols, rows):
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def patch(p, pairs):
    """pairs: list of (inst_col, name_col, dept_col)."""
    cols, rows = read(p)
    n = 0
    for r in rows:
        for ic, nc, dc in pairs:
            key = (r.get(ic), r.get(nc))
            if key in FIXES and r.get(dc, "") in UNKNOWN:
                r[dc] = FIXES[key][0]
                n += 1
    if n:
        write(p, cols, rows)
    return n


targets = [
    (ROOT / "data" / "faculty" / "MANIT_Bhopal.csv", [("institution", "name", "department")]),
    (ROOT / "data" / "faculty_final.csv", [("institution", "name", "department")]),
    (OUT / "group15_data.csv", [("institution", "faculty_name", "department")]),
    (OUT / "all_authors" / "group15_data.csv", [("institution", "faculty_name", "department")]),
    (OUT / "faculty_matched.csv", [("institution", "faculty_name", "department")]),
    (OUT / "author_faculty_map.csv", [("institution", "faculty_name", "department")]),
    (OUT / "author_roles.csv", [("institution", "faculty_name", "department")]),
    (OUT / "faculty_network_nodes.csv", [("institution", "faculty_name", "department")]),
    (OUT / "faculty_network_edges.csv", [("inst_a", "faculty_a", "dept_a"), ("inst_b", "faculty_b", "dept_b")]),
    (ST / "faculty_node_metrics.csv", [("institution", "faculty_name", "department")]),
    (ST / "faculty_performance.csv", [("institution", "faculty_name", "department")]),
    (ST / "faculty_ranking_MANIT_Bhopal.csv", [("institution", "faculty_name", "department")]),
    (ST / "faculty_ranking_NIT_Jamshedpur.csv", [("institution", "faculty_name", "department")]),
    (ST / "faculty_ranking_NIT_Silchar.csv", [("institution", "faculty_name", "department")]),
    (ST / "author_brokers.csv", [("institution", "faculty_name", "department")]),
    (ST / "locality" / "faculty_within_outside.csv", [("institution", "faculty_name", "department")]),
]
for p, pairs in targets:
    if p.exists():
        n = patch(p, pairs)
        print(f"{n:6d} rows  {p.relative_to(ROOT)}")

# note the evidence in faculty_final.csv
cols, rows = read(ROOT / "data" / "faculty_final.csv")
for r in rows:
    if (r["institution"], r["name"]) in FIXES and "department confirmed" not in r["verification"]:
        r["verification"] = (r["verification"] + "; department confirmed: " + FIXES[(r["institution"], r["name"])][1]).strip("; ")
write(ROOT / "data" / "faculty_final.csv", cols, rows)


# ------------------------------------------------------------------ department_stats.csv (faculty_stats.py rules)
def h_index(c):
    c = sorted(c, reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


def q1_share(rows):
    j = [r for r in rows if r["type"] == "journal"]
    return round(100 * sum(r["quartile"] == "Q1" for r in j) / len(j), 1) if j else ""


_, g = read(OUT / "group15_data.csv")
seen, f = set(), []
for r in g:
    if r["is_faculty"] != "TRUE":
        continue
    k = (r["institution"], r["faculty_name"], r["openalex_work_id"])
    if k not in seen:
        seen.add(k)
        r["dept"] = (r["department"] or "Unknown department").split("; ")[0]
        r["c"] = int(float(r["citations"] or 0))
        f.append(r)
_, perf = read(ST / "faculty_performance.csv")
_, fm = read(OUT / "faculty_matched.csv")
listed = defaultdict(int)
for r in fm:
    if r.get("status") != "same_name_different_people" and r["faculty_status"] == "current":
        listed[(r["institution"], (r["department"] or "").split("; ")[0])] += 1
pdept = defaultdict(list)
for r in perf:
    pdept[(r["institution"], (r["department"] or "Unknown department").split("; ")[0])].append(r)
groups = defaultdict(list)
for r in f:
    groups[(r["institution"], r["dept"])].append(r)
out = []
for (inst, dept), rs in groups.items():
    papers = list({r["openalex_work_id"]: r for r in rs}.values())
    p = pdept[(inst, dept)]
    hs = [int(x["h_index"]) for x in p]
    out.append({"institution": inst, "department": dept, "faculty_listed": listed.get((inst, dept), 0),
                "faculty_matched": len(p), "of_which_former": sum(x["faculty_status"] == "former" for x in p),
                "papers": len(papers), "citations": sum(r["c"] for r in papers),
                "papers_per_faculty": round(len(papers) / len(p), 1) if p else "",
                "median_h_index": float(statistics.median(hs)) if hs else "", "max_h_index": max(hs) if hs else "",
                "q1_share_%": q1_share(papers)})
out.sort(key=lambda r: (r["institution"], -r["papers"]))
cols, old = read(ST / "department_stats.csv")
same = sum(1 for a in old for b in out if a["institution"] == b["institution"] and a["department"] == b["department"]
           and str(a["papers"]) == str(b["papers"]) and str(a["citations"]) == str(b["citations"]))
write(ST / "department_stats.csv", cols, out)
print(f"department_stats.csv rebuilt: {len(out)} rows ({same} unchanged)")
for r in out:
    if r["institution"] == "MANIT Bhopal" and r["department"] in ("Energy Science and Engineering", "Unknown department"):
        print("  ", r)
