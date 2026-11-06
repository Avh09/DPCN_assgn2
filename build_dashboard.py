"""Bundle the final tables in data/out/ into dashboard/data.js for the interactive dashboard.

Standard library only (no pandas needed). Run from the project folder:
    python build_dashboard.py
then open dashboard/index.html in a browser.

Leaves out partner_results.json and figures 10-11 (partners.py still runs on the old corpus);
the partner list in indian_connections.csv is current and is included.
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "out"
ST = OUT / "stats"
DASH = ROOT / "dashboard"
INSTS = ["MANIT Bhopal", "NIT Jamshedpur", "NIT Silchar"]
SLUG = {i: i.replace(" ", "_") for i in INSTS}


def rd(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(x, cast=float, default=None):
    try:
        return cast(float(x)) if cast is int else cast(x)
    except (TypeError, ValueError):
        return default


def truthy(x):
    return str(x).strip().upper() == "TRUE"


def jload(name):
    return json.loads((ST / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ faculty
import movers
ALIAS = movers.aliases()      # one record per person who is listed at two of our institutes
rank = []
for i in INSTS:
    rank += [r for r in rd(ST / f"faculty_ranking_{SLUG[i]}.csv") if (r["institution"], r["faculty_name"]) not in ALIAS]
nodem = {(r["institution"], r["faculty_name"]): r for r in rd(ST / "faculty_node_metrics.csv")}
nodes = {(r["institution"], r["faculty_name"]): r for r in rd(OUT / "faculty_network_nodes.csv")}

fac, fidx = [], {}
for r in rank:
    k = (r["institution"], r["faculty_name"])
    m, n = nodem.get(k, {}), nodes.get(k, {})
    fidx[k] = len(fac)
    fac.append({
        "n": r["faculty_name"], "i": INSTS.index(r["institution"]), "d": "Unknown department" if r["department"] in ("", "Unknown") else r["department"],
        "s": r["faculty_status"], "des": r["designation"],
        "p": num(r["papers"], int, 0), "jp": num(r["journal_papers"], int, 0),
        "cp": num(r["conference_papers"], int, 0), "c": num(r["citations"], int, 0),
        "h": num(r["h_index"], int, 0), "q1": num(r["q1_share_%"]), "tj": r["top_journal"],
        "tjp": num(r["top_journal_papers"], int, 0), "q1p": num(r["q1_papers"], int, 0),
        "q5": num(r["q1_if_gt5_papers"], int, 0), "cpp": num(r["citations_per_paper"]),
        "ext": num(r["external_coauthor_papers_%"]), "fy": num(r["first_year"], int),
        "ly": num(r["last_year"], int), "rp": num(r["rank_papers"], int),
        "rc": num(r["rank_citations"], int), "rh": num(r["rank_h_index"], int),
        "deg": num(m.get("degree"), int, 0), "str": num(m.get("strength_joint_papers"), int, 0),
        "btw": num(m.get("betweenness"), float, 0), "clo": num(m.get("closeness"), float, 0),
        "eig": num(m.get("eigenvector"), float, 0), "kc": num(m.get("k_core"), int, 0),
        "lv": num(n.get("community_louvain"), int, -1), "ld": num(n.get("community_leiden"), int, -1),
        "clu": num(n.get("clustering"), float, 0), "xd": num(n.get("collaborators_other_dept"), int, 0),
        "xi": num(n.get("collaborators_other_inst"), int, 0),
    })

fedges = []
for r in rd(OUT / "faculty_network_edges.csv"):
    a, b = fidx.get((r["inst_a"], r["faculty_a"])), fidx.get((r["inst_b"], r["faculty_b"]))
    if a is not None and b is not None:
        fedges.append([a, b, num(r["joint_papers"], int, 1), num(r["first_year"], int), num(r["last_year"], int)])

# ------------------------------------------------------------------ papers (all joins use the canonical OpenAlex work ID; DOI is optional)
cmet = {r["openalex_work_id"]: r for r in rd(ST / "citation_node_metrics.csv")}
extras = {r["openalex_work_id"]: r for r in rd(OUT / "work_extras.csv")} if (OUT / "work_extras.csv").exists() else {}
topics = {r["openalex_work_id"]: r for r in rd(OUT / "work_topics.csv")} if (OUT / "work_topics.csv").exists() else {}
TITLE_REVIEW = re.compile(r"\b(review|survey|overview|state[- ]of[- ]the[- ]art)\b", re.I)
_pe = rd(OUT / "papers_enriched.csv")
nref = {r["openalex_work_id"]: len([x for x in r["referenced_works"].split(";") if x]) for r in _pe}
nauth = {r["openalex_work_id"]: num(r["n_authors"], int, 0) for r in _pe}
# distinct institutions and countries on each paper (all co-authors)
_inst, _cty = defaultdict(set), defaultdict(set)
for r in rd(OUT / "all_authors" / "authorships.csv"):
    for part in filter(None, r["institutions_detail"].split(";")):
        _inst[r["openalex_work_id"]].add(part.split("|")[0].strip())
    for c in filter(None, r["country_codes"].split(";")):
        _cty[r["openalex_work_id"]].add(c)
papers, pidx, pfac = [], {}, []
for r in rd(OUT / "group15_data.csv"):
    wid = r["openalex_work_id"]
    if wid not in pidx:
        doi = r["doi"].strip()
        m = cmet.get(wid, {})
        x, tp = extras.get(wid, {}), topics.get(wid, {})
        pidx[wid] = len(papers)
        flag = 2 if truthy(r["q1_impact_gt10"]) else 1 if truthy(r["q1_impact_gt5"]) else 0
        papers.append([
            r["title"], num(r["year"], int), 0 if r["type"] == "journal" else 1, r["journal_name"],
            num(r["citations"], int, 0), doi, r["quartile"], r["field"], 0,
            round(num(m.get("pagerank"), float, 0) * 1e6, 1), num(m.get("in_degree"), int, 0),
            num(m.get("out_degree"), int, 0), flag, 1 if truthy(r["is_multi_author_10plus"]) else 0,
            num(m.get("in_degree_h_index"), int, 0),
            1 if truthy(r["cites_indian_inst"]) else 0, 1 if truthy(r["cited_by_indian_inst"]) else 0,
            # 17+: appended fields (see T in app.js)
            num(x.get("fwci"), float), r.get("venue_kind", ""), r.get("resolved_conference", ""), r.get("core_rank", ""),
            tp.get("subfield", ""), tp.get("topic", ""),
            num(m.get("in_self_citations"), int, 0), num(m.get("in_same_institute_other_author"), int, 0), num(m.get("in_between_our_institutes"), int, 0),
            num(m.get("pagerank_rank_in_year"), int), wid, 1 if (r["type"] == "review" or TITLE_REVIEW.search(r["title"])) else 0,
            r.get("quartile_source", ""), nref.get(wid, 0), nauth.get(wid, 0), len(_inst.get(wid, ())), len(_cty.get(wid, ())),
            # 34-35: journal impact (SCImago cites/doc, OpenAlex 2-year citedness); flag uses the lower one
            num(r.get("journal_cites_per_doc"), float), num(r.get("journal_2yr_citedness_openalex"), float),
        ])
        pfac.append([])
    p = pidx[wid]
    papers[p][8] |= 1 << INSTS.index(r["institution"])
    f = fidx.get((r["institution"], r["faculty_name"]))
    if f is not None and f not in pfac[p]:
        pfac[p].append(f)

# ------------------------------------------------------------------ per-faculty derived metrics (i10, cited share, years active, single-author equivalent)
_fp = defaultdict(list)
for _p, _fs in enumerate(pfac):
    for _f in _fs:
        _fp[_f].append(_p)
_dca = {(r["institution"], r["faculty_name"]): num(r.get("distinct_coauthors_all"), int) for r in rd(ST / "insights" / "connectivity_vs_impact.csv")} if (ST / "insights" / "connectivity_vs_impact.csv").exists() else {}
for _i, _f in enumerate(fac):
    ps = [papers[_p] for _p in _fp.get(_i, [])]
    cs = [x[4] for x in ps]
    na = [x[31] for x in ps if x[31]]
    _f["i10"] = sum(1 for c in cs if c >= 10)
    _f["cit"] = sum(1 for c in cs if c > 0)                                  # papers with at least one citation
    _f["ya"] = (_f["ly"] - _f["fy"] + 1) if _f.get("ly") and _f.get("fy") else 0
    _f["sae"] = round(sum(1.0 / x[31] for x in ps if x[31]), 1)              # single-author equivalent: each paper counts 1 / number of authors
    _f["na"] = round(sum(na) / len(na), 1) if na else 0
    _f["dca"] = _dca.get((INSTS[_f["i"]], _f["n"]))
    _f["mc"] = max(cs) if cs else 0                                          # most cited paper


cedges = []
for r in rd(OUT / "citation_network_ids.csv"):
    s_, t_ = pidx.get(r["source_id"]), pidx.get(r["target_id"])
    if s_ is not None and t_ is not None:
        cedges.append([s_, t_])

# ------------------------------------------------------------------ institute-level tables
def per_inst(pattern, limit=None):
    return {i: rd(ST / pattern.format(SLUG[i]))[:limit] for i in INSTS}


pub = jload("publication_results.json")
netres = jload("network_results.json")
def core_a_star_rows():
    """CORE A*/A conference papers with the people from the three institutes on them (none of them is a verified faculty member)."""
    f = ST / "core_a_star_a_papers.csv"
    if not f.exists():
        return []
    allp = OUT / "all_authors"
    pap = {r["openalex_work_id"]: r for r in rd(allp / "papers_enriched.csv")} if (allp / "papers_enriched.csv").exists() else {}
    aut = defaultdict(list)
    if (allp / "authorships.csv").exists():
        for r in rd(allp / "authorships.csv"):
            if r["our_inst"]:
                aut[r["openalex_work_id"]].append(r["author_name"])
    out = []
    for r in rd(f):
        w = r["openalex_work_id"]
        p = pap.get(w, {})
        out.append({"id": w, "rank": r["core_rank"], "conference": r["conference"], "title": p.get("title", ""), "year": p.get("year", ""),
                    "doi": p.get("doi", ""), "citations": p.get("citations", ""), "institute": p.get("our_institutes", ""),
                    "people": sorted(set(aut.get(w, []))), "faculty_authors": int(r["faculty_authors"]), "roles": r["author_roles"]})
    return out


# ------------------------------------------------------------------ faculty who moved between our institutes
# Same OpenAlex author ID listed at two of the three institutes. "former" row = where they were, "current" row = where they are.
def movers_table():
    ff = rd(ROOT / "data" / "faculty_final.csv")
    byid = {}
    for r in ff:
        for a in (r["openalex_author_ids"] or "").split(";"):
            if a.startswith("A"):
                byid.setdefault(a, {})[r["institution"]] = r
    edges = rd(OUT / "faculty_network_edges.csv")
    def collabs(name, inst):
        out = []
        for e in edges:
            if (e["faculty_a"], e["inst_a"]) == (name, inst):
                out.append((e["faculty_b"], e["inst_b"], int(e["joint_papers"])))
            elif (e["faculty_b"], e["inst_b"]) == (name, inst):
                out.append((e["faculty_a"], e["inst_a"], int(e["joint_papers"])))
        return sorted(out, key=lambda x: -x[2])
    res = []
    for a, rows in byid.items():
        if len(rows) < 2:
            continue
        rs = list(rows.values())
        old = next((r for r in rs if r["faculty_status"] == "former"), None)
        new = next((r for r in rs if r["faculty_status"] == "current" and r is not old), None)
        both_current = old is None
        if both_current:
            old, new = rs[0], rs[1]
        co, cn = collabs(old["name"], old["institution"]), collabs(new["name"], new["institution"])
        pack = lambda cl: [[n, INSTS.index(i), w] for n, i, w in cl[:6]]
        res.append({"n": new["name"], "id": a, "from": INSTS.index(old["institution"]), "to": INSTS.index(new["institution"]),
                    "bothCurrent": both_current, "d": new["department"], "des": new["designation"],
                    "seen": [num(old["first_seen"], int), num(old["last_seen"], int)],
                    "p": num(new["papers"], int, 0), "c": num(new["citations"], int, 0), "h": num(new["h_index_2016_2026"], int, 0),
                    "nOld": len(co), "nNew": len(cn), "cOld": pack(co), "cNew": pack(cn)})
    return sorted(res, key=lambda r: -r["c"])


def candidates_current():
    """Suggested collaborations between current faculty only; 11 hops is the model's placeholder for 'no path', shown as null."""
    st = {(r["institution"], r["name"]): r["faculty_status"] for r in rd(ROOT / "data" / "faculty_final.csv")}
    out = []
    for r in rd(ST / "collab_candidates.csv"):
        if st.get((r["institute_a"], r["faculty_a"])) == "former" or st.get((r["institute_b"], r["faculty_b"])) == "former":
            continue
        if r["hops"] and float(r["hops"]) == 11:
            r["hops"] = ""
        r["rank"] = len(out) + 1
        out.append(r)
        if len(out) == 600:
            break
    return out


def inst_facts():
    """NIRF facts per institute (data/institute_facts.json) plus a small embedded photo (data/institute_images/<short>.jpg)."""
    import base64
    f = ROOT / "data" / "institute_facts.json"
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    short = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}
    for i, k in short.items():
        img = ROOT / "data" / "institute_images" / f"{k}.jpg"
        full = ROOT / "data" / "institute_images" / f"{k}_full.jpg"
        if img.exists() and isinstance(d.get(i), dict):
            d[i]["image"] = "data:image/jpeg;base64," + base64.b64encode(img.read_bytes()).decode()
            if full.exists():
                d[i]["imageFull"] = "data:image/jpeg;base64," + base64.b64encode(full.read_bytes()).decode()
    return d


data = {
    "insts": INSTS,
    "built": __import__("datetime").date.today().isoformat(),
    "summary": rd(ST / "institution_summary.csv"),
    "ppy": rd(ST / "papers_per_year.csv"),
    "pub": {k: pub[k] for k in ("growth_2016_to_2025_cagr_%", "type_split", "quartiles",
                                "conference_rank", "top5_conference_venues", "research_areas")
            if k in pub},
    "topJournals": per_inst("top_journals_{}.csv", 10),
    "top10": per_inst("top10_cited_{}.csv"),
    "top30": per_inst("top30_papers_{}.csv"),
    "top30sum": rd(ST / "top30_summary.csv"),
    "hdist": rd(ST / "h_index_distribution.csv"),
    "dept": rd(ST / "department_stats.csv"),
    "hyper": rd(ST / "hyper_authorship_performance.csv"),
    "reanalysis": rd(ST / "multi_author_reanalysis.csv"),
    "ratio": rd(ST / "citation_ratio.csv"),
    "flowCluster": rd(ST / "citation_flow_by_cluster.csv"),
    "velocity": rd(ST / "citation_velocity.csv"),
    "bridges": rd(ST / "bridge_authors.csv"),
    "brokers": rd(ST / "author_brokers.csv"),
    "incoming": {i: [r for r in rd(OUT / "incoming_citations_by_institute.csv") if r["your_inst"] == i][:12] for i in INSTS},
    "outgoing": {i: [r for r in rd(OUT / "outgoing_citations_by_institute.csv") if r["your_inst"] == i][:12] for i in INSTS},
    "partners": {i: [r for r in rd(OUT / "indian_connections.csv") if r["your_inst"] == i][:15] for i in INSTS},
    "citMacro": jload("citation_network_macro.json"),
    "citNet": {k: v for k, v in netres["citation_network"].items() if k != "top10_pagerank"},
    "top10pr": netres["citation_network"]["top10_pagerank"],
    "facNet": jload("faculty_network_results.json"),
    "facNetExtra": jload("faculty_network_extra.json"),
    "fac": fac, "fedges": fedges, "movers": movers_table(),
    "instFacts": inst_facts(),
    "papers": papers, "pfac": pfac, "cedges": cedges,
    # --- new analyses (all produced by the pipeline, nothing typed in)
    "citSources": jload("citation_sources.json"),
    "citDegree": rd(ST / "citation_degree_distribution.csv"),
    "resilience": jload("resilience_results.json"),
    "resCurves": rd(ST / "resilience_curves.csv"),
    "criticalFaculty": [r for sc in ["all"] + INSTS for r in [x for x in rd(ST / "critical_faculty.csv") if x["scope"] == sc][:12]],
    "linkPred": jload("link_prediction_results.json"),
    "candidates": candidates_current(),
    "insights": {n: (jload(f"insights/{n}.json") if (ST / "insights" / f"{n}.json").exists() else rd(ST / "insights" / f"{n}.csv"))
                 for n in ("institute_comparison", "h_index_size_test", "citation_concentration", "review_analysis",
                           "quartile_vs_impact", "team_size", "connectivity_vs_impact", "specialisation", "venue_explorer", "publication_mix_by_year", "output_drivers", "new_views")},
    "confRank": jload("conference_ranking.json"),
    "coreAStar": core_a_star_rows(),
    "findings": jload("key_findings.json"),
    "dupAudit": rd(OUT / "duplicate_audit.csv")[:200] if (OUT / "duplicate_audit.csv").exists() else [],
}

# ------------------------------------------------------------------ locality and reach (locality_reach.py)
LOC = ST / "locality"
if (ST / "locality_results.json").exists():
    lr = json.loads((ST / "locality_results.json").read_text(encoding="utf-8"))
    partners = []
    for r in rd(LOC / "partners_locality.csv"):
        partners.append([INSTS.index(r["your_inst"]), r["partner_inst"], int(r["shared_papers"]), int(r["total_citations"]),
                         r["partner_cluster"], r["state"], r["region"], r["locality"], int(r["first_year"]), int(r["last_year"]),
                         int(r["faculty_involved"]), r["top_faculty"], num(r["jaccard_subfields"]), num(r["weighted_jaccard"]),
                         [int(r[f"y{y}"]) for y in range(2016, 2027)],
                         num(r.get("cites_from_partner"), int), num(r.get("cites_to_partner"), int)])
    wo = {}
    for r in rd(LOC / "faculty_within_outside.csv"):
        f = fidx.get((r["institution"], r["faculty_name"]))
        if f is not None:
            wo[f] = [int(r[k]) for k in ("coauthors_same_institute", "coauthors_our_other_two", "coauthors_other_indian",
                                         "coauthors_foreign", "coauthors_unknown", "coauthors_total")] + [float(r["betweenness_full_network"])]
    fpart = defaultdict(list)
    for r in rd(LOC / "faculty_partners.csv"):
        f = fidx.get((r["institution"], r["faculty_name"]))
        if f is not None and len(fpart[f]) < 10:
            fpart[f].append([r["partner_inst"], int(r["joint_papers"]), r["partner_cluster"], r["locality"]])
    pp = defaultdict(list)
    for r in rd(LOC / "partner_papers.csv"):
        if r["openalex_work_id"] in pidx:
            pp[r["partner_inst"]].append(pidx[r["openalex_work_id"]])
    fpp = defaultdict(set)
    if (LOC / "foreign_partner_papers.csv").exists():
        for r in rd(LOC / "foreign_partner_papers.csv"):
            if r["openalex_work_id"] in pidx:
                fpp[r["partner_inst"]].add(pidx[r["openalex_work_id"]])
    inodes = rd(LOC / "institute_network_nodes.csv")
    data["loc"] = {
        "partners": partners, "partnerPapers": {k: sorted(set(v)) for k, v in pp.items()}, "foreignPapers": {k: sorted(v) for k, v in fpp.items()}, "facWO": wo, "facPartners": fpart,
        "extAuthors": rd(LOC / "top_external_authors.csv")[:120],
        "instNodes": [r for r in inodes if r["country"] == "IN"][:150] + [r for r in inodes if r["country"] != "IN"][:150],
        "reach": lr["collaboration_reach"], "between": lr["between_our_institutes"], "fullNet": lr["full_author_network"],
        "instNet": lr["institute_network"]["our_institutes"], "spearman": lr["within_vs_outside_spearman"],
        "citOrigin": lr["citation_origin"], "home": lr["home_state"], "stateCoverage": lr["state_mapping_coverage_%_of_links"],
        "jacOurs": json.loads((ST / "partner_results.json").read_text(encoding="utf-8")).get("between_our_institutes", {}),
        "partnerRes": json.loads((ST / "partner_results.json").read_text(encoding="utf-8")),
        "foreign": [[INSTS.index(r["your_inst"]), r["partner_inst"], r["country"], int(r["shared_papers"]), int(r["total_citations"])]
                    for r in rd(LOC / "foreign_partners.csv") if int(r["shared_papers"]) >= 2] if (LOC / "foreign_partners.csv").exists() else [],
    }

# ------------------------------------------------------------------ method tab numbers (all read from the pipeline outputs)
rep = (OUT / "build_report.txt").read_text(encoding="utf-8")
dl = int(re.search(r"Unique works downloaded: (\d+)", rep).group(1))
dropped = int(re.search(r"Dropped (\d+) non-research items", rep).group(1)) + int(re.search(r"Dropped (\d+) duplicate DOIs", rep).group(1))
kept_types = dl - dropped - int(re.search(r"Dropped (\d+) non journal/conference items", rep).group(1))
merged = int(re.search(r"Merged (\d+) duplicate records", rep).group(1))
data["dupMerged"] = merged
data["funnel"] = [["Records downloaded from OpenAlex", dl], ["After removing errata, retractions and duplicate DOIs", dl - dropped],
                  ["Journal and conference papers", kept_types], [f"After merging {merged} duplicate records of the same paper", int(re.search(r"Papers kept: (\d+)", rep).group(1))],
                  ["Papers with a verified faculty author", len(papers)]]
QSRC = {"sjr_approx": "SCImago SJR (journals)", "scopus_citescore": "Scopus CiteScore percentile", "estimated_openalex": "Estimated from OpenAlex venue data",
        "estimated_publisher": "Estimated from the publisher series", "core": "CORE 2023 list", "none": "No ranking available"}
qs = defaultdict(int)
for r in rd(OUT / "papers_enriched.csv"):
    qs[QSRC.get(r.get("quartile_source", ""), "No ranking available")] += 1
data["qsrc"] = sorted(qs.items(), key=lambda kv: -kv[1])
data["group15Rows"] = sum(1 for _ in rd(OUT / "group15_data.csv"))
data["dupMerged"] = merged

DASH.mkdir(exist_ok=True)
js = "window.DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
(DASH / "data.js").write_text(js, encoding="utf-8")
print(f"dashboard/data.js: {len(js) / 1e6:.1f} MB | faculty {len(fac)}, faculty links {len(fedges)}, "
      f"papers {len(papers)}, citation links {len(cedges)}")
