"""Collect every number and table the Word report needs into report/report_data.json.

Standard library only. Run from the project folder:
    python report/report_data.py && node report/build_report.js
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"
ST = OUT / "stats"
INSTS = ["MANIT Bhopal", "NIT Jamshedpur", "NIT Silchar"]
SLUG = {i: i.replace(" ", "_") for i in INSTS}


def rd(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def js(name):
    return json.loads((ST / name).read_text(encoding="utf-8"))


pub = js("publication_results.json")
net = js("network_results.json")
fnet = js("faculty_network_results.json")

# faculty leaderboards (top 10 by h-index, ties by citations)
leaders = {}
for i in INSTS:
    rows = rd(ST / f"faculty_ranking_{SLUG[i]}.csv")
    rows.sort(key=lambda r: (-int(r["h_index"]), -int(r["citations"])))
    leaders[i] = [{k: r[k] for k in ("faculty_name", "department", "h_index", "papers", "citations",
                                      "q1_share_%", "q1_papers", "top_journal")} for r in rows[:10]]

# departments: top 6 by papers (excluding unknown)
dept = {i: sorted([r for r in rd(ST / "department_stats.csv") if r["institution"] == i and r["department"] != "Unknown department"],
                  key=lambda r: -int(r["papers"]))[:6] for i in INSTS}

# in-degree distribution (citation network)
cm = rd(ST / "citation_node_metrics.csv")
indeg = Counter(int(r["in_degree"]) for r in cm)
bands = [("0", 0, 0), ("1", 1, 1), ("2", 2, 2), ("3-4", 3, 4), ("5-9", 5, 9), ("10-19", 10, 19), ("20+", 20, 10**9)]
indeg_bands = [{"band": b, "papers": sum(c for d, c in indeg.items() if lo <= d <= hi)} for b, lo, hi in bands]

# Louvain communities on the faculty network
nodes = rd(OUT / "faculty_network_nodes.csv")
by_c = defaultdict(list)
for n in nodes:
    if int(n["collaborators"]) > 0:
        by_c[n["community_louvain"]].append(n)
comms = []
for c, mem in sorted(by_c.items(), key=lambda kv: -len(kv[1]))[:10]:
    inst = Counter(m["institution"] for m in mem).most_common(1)[0]
    dep = Counter(m["department"] for m in mem).most_common(1)[0]
    lead = sorted(mem, key=lambda m: -int(m["collaborators"]))[:3]
    comms.append({"community": c, "size": len(mem), "institute": inst[0], "inst_share_%": round(100 * inst[1] / len(mem)),
                  "department": dep[0], "dept_share_%": round(100 * dep[1] / len(mem)),
                  "leaders": ", ".join(m["faculty_name"] for m in lead)})

brokers = {i: [r for r in rd(ST / "author_brokers.csv") if r["institution"] == i][:5] for i in INSTS}
bridges = {i: [r for r in rd(ST / "bridge_authors.csv") if r["institution"] == i][:5] for i in INSTS}
fc = rd(ST / "citation_flow_by_cluster.csv")
flow_cluster = {i: {d: [r for r in fc if r["your_inst"] == i and r["direction"] == d][:4] for d in ("incoming", "outgoing")} for i in INSTS}
inc = rd(OUT / "incoming_citations_by_institute.csv")
outg = rd(OUT / "outgoing_citations_by_institute.csv")
partners = rd(OUT / "indian_connections.csv")
vel = [r for r in rd(ST / "citation_velocity.csv") if r["table"].startswith("publication-year")]


import re as _re
_br = (OUT / "build_report.txt").read_text(encoding="utf-8")
_m = rd(OUT / "group15_data.csv")
_ff = rd(ROOT / "data" / "faculty_final.csv")
_dropped = json.loads(_re.search(r"Dropped \d+ non journal/conference items: (\{.*\})", _br).group(1).replace("'", '"'))
headline = {
    "raw_works": int(_re.search(r"Unique works downloaded: (\d+)", _br).group(1)),
    "nonresearch_dropped": int(_re.search(r"Dropped (\d+) non-research", _br).group(1)),
    "dup_doi_dropped": int(_re.search(r"Dropped (\d+) duplicate DOIs", _br).group(1)),
    "other_dropped": sum(_dropped.values()), "book_chapters_dropped": _dropped.get("book-chapter", 0),
    "preprints_dropped": _dropped.get("preprint", 0),
    "papers_kept_before_faculty_filter": int(_re.search(r"Papers kept: (\d+)", _br).group(1)),
    "papers": len({r["openalex_work_id"] for r in _m}), "rows": len(_m),
    "faculty_with_papers": sum(len({r["faculty_name"] for r in _m if r["institution"] == i}) for i in INSTS),
    "list_total": len(_ff), "list_official": sum(r["source"] == "official faculty page" for r in _ff),
    "list_former": sum(r["source"].startswith("official faculty page (former") for r in _ff),
    "list_added": sum(r["source"].startswith("added after") for r in _ff),
    "list_matched": sum(r["match_status"] == "matched" for r in _ff),
    "list_not_found": sum(r["match_status"] == "not_found" for r in _ff),
}

_val = (OUT / "validate_report.txt").read_text(encoding="utf-8") if (OUT / "validate_report.txt").exists() else ""
_sum = _re.search(r"SUMMARY: (\d+) passed, (\d+) failed, (\d+) warnings", _val)
_fm = _re.search(r"former faculty: (\d+)% of their papers fall within.*?; (\d+) of (\d+) people", _val)
_full = rd(OUT / "all_authors" / "group15_data.csv") if (OUT / "all_authors" / "group15_data.csv").exists() else _m
_pp = {}
for _r in _m:
    _pp[_r["openalex_work_id"]] = _r
_nets = json.loads((ST / "network_results.json").read_text(encoding="utf-8"))
headline.update({
    "rows_removed_non_faculty": sum(r["is_faculty"] != "TRUE" for r in _full),
    "citation_edges": len(rd(OUT / "citation_network.csv")), "author_pairs": len(rd(OUT / "authorship_network.csv")),
    "connection_rows": len(rd(OUT / "indian_connections.csv")),
    "overrides": len(rd(ROOT / "data" / "faculty_overrides.csv")),
    "multi_author_papers": sum(r["is_multi_author_10plus"] == "TRUE" for r in _pp.values()),
    "multi_author_pct": round(100 * sum(r["is_multi_author_10plus"] == "TRUE" for r in _pp.values()) / len(_pp), 1),
    "max_authors": max(int(r["n_authors"]) for r in rd(OUT / "papers_enriched.csv")),
    "core_ranked_papers": sum(r["quartile"] in ("A*", "A", "B", "C") for r in _pp.values()),
    "shared_by_two_or_three": _nets["indian_connections"]["papers_with_authors_from_2_or_3_of_our_institutes"],
    "validate_passed": int(_sum.group(1)) if _sum else None, "validate_failed": int(_sum.group(2)) if _sum else None,
    "former_fit_pct": int(_fm.group(1)) if _fm else None, "former_fit_people": int(_fm.group(2)) if _fm else None,
    "former_people": int(_fm.group(3)) if _fm else None,
})

_cit = set()
_citing = ROOT / "data" / "raw" / "links" / "citing.jsonl"
if _citing.exists():
    for _l in open(_citing, encoding="utf-8"):
        _cit.add(json.loads(_l)["id"])
else:  # raw downloads are not on every machine: keep the count from the last full run
    _prev = ROOT / "report" / "report_data.json"
    _cit = range(json.loads(_prev.read_text(encoding="utf-8")).get("headline", {}).get("citing_works", 0) if _prev.exists() else 0)
_pe = rd(OUT / "papers_enriched.csv")
_tn = lambda t: _re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
_dupc = Counter((_tn(r["title"]), r["year"]) for r in _pe)
_re_ = rd(ST / "multi_author_reanalysis.csv")
_q1 = {}
for _r in _re_:
    _q1.setdefault(_r["institution"], {})[_r["scope"]] = float(_r["journal_Q1_share_%"])

headline.update({
    "citing_works": len(_cit),
    "estimated_rows": sum(r["quartile_source"].startswith("estimated") for r in _m),
    "estimated_pct": round(100 * sum(r["quartile_source"].startswith("estimated") for r in _m) / len(_m)),
    "dup_title_pairs": sum(1 for k, v in _dupc.items() if v > 1),
    "conf_share_pct": round(100 * sum(r["type"] == "conference" for r in _pp.values()) / len(_pp)),
    "multi_q1_max_shift": round(max(abs(v["all papers"] - v["without >10-author papers"]) for v in _q1.values()), 1),
})

data = {
    "headline": headline,
    "insts": INSTS,
    "summary": rd(ST / "institution_summary.csv"),
    "ppy": rd(ST / "papers_per_year.csv"),
    "cagr": pub["growth_2016_to_2025_cagr_%"],
    "type_split": pub["type_split"],
    "quartiles": pub["quartiles"],
    "conf": pub["conference_rank"],
    "conf_venues": pub["top5_conference_venues"],
    "areas": pub["research_areas"],
    "top_journals": {i: rd(ST / f"top_journals_{SLUG[i]}.csv")[:5] for i in INSTS},
    "top10_cited": {i: rd(ST / f"top10_cited_{SLUG[i]}.csv") for i in INSTS},
    "top30_sum": rd(ST / "top30_summary.csv"),
    "top30": {i: rd(ST / f"top30_papers_{SLUG[i]}.csv")[:10] for i in INSTS},
    "hdist": rd(ST / "h_index_distribution.csv"),
    "fac_results": js("faculty_results.json"),
    "author_analysis": js("author_analysis.json"),
    "leaders": leaders,
    "dept": dept,
    "hyper": rd(ST / "hyper_authorship_performance.csv"),
    "reanalysis": rd(ST / "multi_author_reanalysis.csv"),
    "cit_macro": js("citation_network_macro.json"),
    "cit_net": net["citation_network"],
    "indeg_bands": indeg_bands,
    "fac_net": fnet,
    "fac_net_extra": js("faculty_network_extra.json"),
    "communities": comms,
    "brokers": brokers,
    "bridges": bridges,
    "inflow": js("inflow_results.json"),
    "ratio": rd(ST / "citation_ratio.csv"),
    "flow_cluster": flow_cluster,
    "incoming": {i: [r for r in inc if r["your_inst"] == i][:5] for i in INSTS},
    "outgoing": {i: [r for r in outg if r["your_inst"] == i][:5] for i in INSTS},
    "partners": {i: [r for r in partners if r["your_inst"] == i][:5] for i in INSTS},
    "velocity": vel,
    "scopus": js("scopus_results.json"),
    "loc": js("locality_results.json"),
    "partner_res": js("partner_results.json"),
    "peers": rd(ST / "locality" / "peer_institutes.csv"),
}
(ROOT / "report" / "report_data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("report/report_data.json written")
