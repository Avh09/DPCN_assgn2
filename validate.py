"""Checks every deliverable. Prints PASS / FAIL / WARN per check and a summary.

  python validate.py           all local checks (structure, consistency, maths functions)
  python validate.py --live    also re-checks random samples directly against OpenAlex

Local checks use a SECOND, simpler implementation where possible (e.g. the
cited_by_indian_inst flag is recomputed from the raw download without inflow.py's code),
so a bug in one implementation shows up as a disagreement.

Run order (later scripts add columns to group15_data.csv; enrich.py rewrites it and blanks the
citation flags, so after rerunning it, rerun everything below it):
  fetch.py -> build_tables.py -> enrich.py -> networks.py -> links.py -> outflow.py -> inflow.py
  -> faculty_match.py -> faculty_stats.py -> faculty_network.py -> partners.py -> validate.py
"""
import json
import random
import re
import sys
from collections import defaultdict

import pandas as pd

import config

OUT = config.OUT_DIR
results = []


def check(name, ok, detail="", warn=False):
    status = "PASS" if ok else ("WARN" if warn else "FAIL")
    results.append(status)
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))


def structure():
    print("\n== 1. Submission files: columns, years, institutes")
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str)
    need = ["group", "institution", "author", "title", "year", "type", "journal_name", "issn", "doi",
            "citations", "quartile", "coauthor_institutes", "cites_indian_inst", "cited_by_indian_inst"]
    check("group15_data.csv has all 14 required columns", not set(need) - set(m.columns), str(set(need) - set(m.columns) or ""))
    check("group column is 15 everywhere", (m.group == "15").all())
    y = m.year.astype(int)
    check("years within 2016-2026", y.between(2016, 2026).all(), f"{y.min()}-{y.max()}")
    check("all 3 institutes present", set(m.institution) == set(config.INSTITUTES), str(m.institution.value_counts().to_dict()))
    check("type is journal or conference", m.type.isin(["journal", "conference"]).all())
    check("no duplicate (paper, author, institute) rows", not m.duplicated(["openalex_work_id", "author_id", "institution"]).any(),
          str(m.duplicated(["openalex_work_id", "author_id", "institution"]).sum()))
    for c in ("cites_indian_inst", "cited_by_indian_inst"):
        v = m[c].fillna("")
        check(f"{c} is TRUE/FALSE (blank only where no data)", v.isin(["TRUE", "FALSE", ""]).all(),
              f"blank {(v == '').mean():.1%}", warn=False)
    check("cited_by_indian_inst filled for every row", m.cited_by_indian_inst.notna().all())
    doi = m.doi.dropna()
    check("DOIs in https://doi.org/ form", doi.str.startswith("https://doi.org/").all())
    check("group15_data.csv holds faculty rows only", (m.is_faculty == "TRUE").all())
    blanks = {c: int((m[c].fillna("") == "").sum()) for c in need if c not in ("doi", "issn")}
    check("no empty cell in the required columns (DOI and conference ISSN excepted)", not any(blanks.values()), str({k: v for k, v in blanks.items() if v}))
    check("quartile values valid", m.quartile.dropna().isin(["Q1", "Q2", "Q3", "Q4", "A*", "A", "B", "C", "Unranked"]).all())
    for f, cols in {"citation_network.csv": ["source_doi", "target_doi", "source_inst", "target_inst", "year"],
                    "authorship_network.csv": ["author_a", "author_b", "paper_doi", "inst_a", "inst_b", "year"],
                    "indian_connections.csv": ["your_inst", "partner_inst", "shared_papers", "total_citations"]}.items():
        d = pd.read_csv(OUT / f, nrows=5)
        check(f"{f} has exactly the required columns", list(d.columns) == cols, str(list(d.columns)))
    c = pd.read_csv(OUT / "citation_network.csv")
    ids = set(m.doi.dropna()) | {f"openalex:{w}" for w in m.openalex_work_id}
    check("citation_network: every source and target paper is in the dataset",
          c.source_doi.isin(ids).all() and c.target_doi.isin(ids).all())
    check("citation_network: no paper cites itself", not (c.source_doi == c.target_doi).any())
    check("required columns kept after our scripts (is_faculty, department)",
          {"is_faculty", "faculty_name", "department"} <= set(m.columns))
    return m


def citations(m):
    print("\n== 2. Citation flow: recomputed independently from the raw download")
    p = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "our_institutes", "citations"])
    our = {w: set(o.split(";")) for w, o in zip(p.openalex_work_id, p.our_institutes) if isinstance(o, str)}
    own_names = {v["official_name"].lower(): k for k, v in config.INSTITUTES.items()}
    flag = set()
    found = defaultdict(int)
    seen = set()
    da = OUT / "duplicate_audit.csv"       # a paper merged into another copy is cited under the kept copy
    dd = pd.read_csv(da, dtype=str) if da.exists() else pd.DataFrame(columns=["decision", "other_work_id", "kept_work_id"])
    merged_into = dict(zip(dd[dd.decision == "merged"].other_work_id, dd[dd.decision == "merged"].kept_work_id))
    for line in open(config.RAW_DIR / "links" / "citing.jsonl"):
        r = json.loads(line)
        for w in r["cites_our"]:
            w = merged_into.get(w, w)
            if (r["id"], w) in seen or w not in our:
                continue
            seen.add((r["id"], w))
            for inst in our[w]:
                found[inst] += 1
                for _, name, cc, ours, _ in r["insts"]:
                    mine = ours or own_names.get((name or "").lower(), "")
                    if cc == "IN" and name and mine != inst:
                        flag.add((w, inst))
    got = {(w, i) for w, i, v in zip(m.openalex_work_id, m.institution, m.cited_by_indian_inst) if v == "TRUE"}
    rows = {(w, i) for w, i in zip(m.openalex_work_id, m.institution)}
    check("cited_by_indian_inst matches the independent recomputation", got == (flag & rows),
          f"{len(got)} TRUE, differences {len(got ^ (flag & rows))}")
    res = json.loads((OUT / "stats" / "inflow_results.json").read_text())
    for inst in config.INSTITUTES:
        tot = int(p[p.our_institutes.fillna("").str.contains(inst)].citations.sum())
        check(f"{inst}: citing works found = {found[inst]:,} of {tot:,} OpenAlex citations",
              found[inst] / tot > 0.97, f"{found[inst] / tot:.1%}")
        check(f"{inst}: inflow_results agrees", res[inst]["citations_found"] == found[inst])
    flow = pd.read_csv(OUT / "citation_flow_by_year.csv")
    byy = pd.read_csv(OUT / "incoming_citations_by_year.csv")
    byy = byy[byy.year.between(2016, 2026)]
    check("flow chart in_cites = yearly incoming file", flow.in_cites.sum() == byy.from_other_indian.sum())
    out = pd.read_csv(OUT / "outgoing_citations_by_year.csv")
    check("flow chart out_cites = yearly outgoing file", flow.out_cites.sum() == out.to_other_indian.sum())
    for inst in config.INSTITUTES:
        r = res[inst]
        check(f"{inst}: impact ratio = in / out", abs(r["impact_ratio_in_over_out"] -
              r["in_cites_from_other_indian_institutes"] / r["out_cites_to_other_indian_institutes"]) < 0.01,
              f"{r['impact_ratio_in_over_out']}")


def faculty(m):
    print("\n== 3. Faculty matching and faculty statistics")
    from faculty_match import h_index
    amap = pd.read_csv(OUT / "author_faculty_map.csv")
    former_dir = config.ROOT / "data" / "faculty_former"
    lists = list(config.FACULTY_DIR.glob("*.csv")) + [p for p in former_dir.glob("*.csv") if p.stat().st_size > 10]
    fl = pd.concat([pd.read_csv(p) for p in lists])
    check("each author id belongs to at most one faculty member",
          not amap.duplicated(["institution", "author_id"]).any())
    names = {(i, n.replace("​", "").strip()) for i, n in zip(fl.institution, fl.name)}
    names |= {(i, n.split(" ", 1)[1]) for i, n in names if n.startswith("essor ")}
    # same-name colleagues are named "<name> (<department>)"
    plain = lambda n: re.sub(r"\s*\([^)]*\)$", "", n)
    names = {(i, re.sub(r"\s+", " ", n)) for i, n in names}
    check("every matched faculty member is on the official list",
          all((i, plain(n)) in names for i, n in zip(amap.institution, amap.faculty_name)))
    hom = pd.read_csv(OUT / "faculty_matched.csv")
    hom = set(zip(*[hom[hom.status == "same_name_different_people"][c] for c in ("institution", "faculty_name")]))
    check("same-name-different-people faculty are not matched",
          not any(k in hom for k in zip(amap.institution, amap.faculty_name)))
    key = set(zip(amap.institution, amap.author_id))
    isf = pd.Series([k in key for k in zip(m.institution, m.author_id)], index=m.index)
    ov_path = config.ROOT / "data" / "faculty_overrides.csv"
    ov = pd.read_csv(ov_path, dtype=str).fillna("") if ov_path.exists() else pd.DataFrame(columns=["action"])
    for r in ov[ov.action.isin(["work_assign", "work_unassign"])].itertuples(index=False):
        k = (m.institution == r.institution) & (m.openalex_work_id == r.work_id) & (m.author_id == r.author_id)
        isf[k] = r.action == "work_assign"
    check("is_faculty TRUE exactly for matched author ids (after paper-level corrections)",
          (isf == (m.is_faculty == "TRUE")).all())
    # every correction in faculty_overrides.csv is applied
    amap_key = dict(zip(zip(amap.institution, amap.author_id), amap.faculty_name))
    ok = []
    for r in ov.itertuples(index=False):
        if r.action == "assign":
            ok.append(amap_key.get((r.institution, r.author_id)) == r.faculty_name)
        elif r.action == "unassign":
            ok.append((r.institution, r.author_id) not in amap_key)
        else:
            k = (m.institution == r.institution) & (m.openalex_work_id == r.work_id) & (m.author_id == r.author_id)
            want = ("TRUE", r.faculty_name) if r.action == "work_assign" else ("FALSE", "")
            # a paper-level correction about a work that is no longer in the corpus (e.g. now a book chapter) has nothing to apply to
            ok.append((not k.any() and r.work_id not in set(m.openalex_work_id)) or bool(k.any()) and all(tuple(x) == want for x in m.loc[k, ["is_faculty", "faculty_name"]]
                                            .fillna("").values))
    check(f"all {len(ov)} corrections in faculty_overrides.csv are applied", all(ok), f"{ok.count(False)} not applied")
    check("every correction states its evidence", ov.get("evidence", pd.Series(dtype=str)).astype(bool).all())
    perf = pd.read_csv(OUT / "stats" / "faculty_performance.csv")
    f = m[m.is_faculty == "TRUE"].copy()
    f["citations"] = f.citations.astype(int)
    g = f.drop_duplicates(["institution", "faculty_name", "openalex_work_id"]).groupby(["institution", "faculty_name"])
    rec = pd.DataFrame({"p": g.size(), "c": g.citations.sum(), "h": g.citations.apply(h_index)}).reset_index()
    x = perf.merge(rec, on=["institution", "faculty_name"])
    check("faculty table: papers, citations, h-index match a recount",
          len(x) == len(perf) and (x.papers == x.p).all() and (x.citations == x.c).all() and (x.h_index == x.h).all(),
          f"{len(perf)} faculty")
    # former faculty: if the match is right, their papers at the institute should mostly fall in
    # the years they were on the faculty pages (2 years slack: papers appear after people leave)
    fm = pd.read_csv(OUT / "faculty_matched.csv")
    fo = fm[(fm.get("faculty_status") == "former") & (fm.status == "matched")] if "faculty_status" in fm else fm[:0]
    if len(fo):
        f2 = f.drop_duplicates(["institution", "faculty_name", "openalex_work_id"])
        f2 = f2.merge(fo[["institution", "faculty_name", "first_seen", "last_seen"]], on=["institution", "faculty_name"])
        y = f2.year.astype(int)
        inside = y.between(f2.first_seen - 2, f2.last_seen + 2)
        per = inside.groupby([f2.institution, f2.faculty_name]).mean()
        check(f"former faculty: {inside.mean():.0%} of their papers fall within the years they were on the "
              f"faculty pages (+-2 years); {int((per >= .5).sum())} of {len(per)} people mostly inside",
              inside.mean() >= 0.8, warn=True)
    audit = pd.read_csv(OUT / "faculty_match_audit_checked.csv")
    ok = (audit.correct == "Y").mean()
    check(f"manual audit precision {ok:.0%} (50 random matches)", ok >= 0.85)


def networks(m):
    print("\n== 4. Faculty network")
    import networkx as nx
    e = pd.read_csv(OUT / "faculty_network_edges.csv")
    n = pd.read_csv(OUT / "faculty_network_nodes.csv")
    check("no self-links", not ((e.faculty_a == e.faculty_b) & (e.inst_a == e.inst_b)).any())
    check("no repeated links", not e.duplicated(["inst_a", "faculty_a", "inst_b", "faculty_b"]).any())
    # recount joint papers from the main file (papers with <= 30 authors)
    small = set(pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "n_authors"])
                .query("n_authors <= 30").openalex_work_id)
    f = m[(m.is_faculty == "TRUE") & m.openalex_work_id.isin(small)]
    on = f.groupby("openalex_work_id").apply(lambda g: set(zip(g.institution, g.faculty_name)), include_groups=False)
    random.seed(1)
    bad = 0
    for _, r in e.sample(40, random_state=1).iterrows():
        a, b = (r.inst_a, r.faculty_a), (r.inst_b, r.faculty_b)
        bad += sum(1 for s in on if a in s and b in s) != r.joint_papers
    check("40 random links: joint paper count matches a recount", bad == 0, f"{bad} wrong")
    G = nx.Graph()
    G.add_edges_from(zip(zip(e.inst_a, e.faculty_a), zip(e.inst_b, e.faculty_b)))
    deg = dict(G.degree())
    check("node table collaborators = degree in edge file",
          all(deg.get((i, fn), 0) == c for i, fn, c in zip(n.institution, n.faculty_name, n.collaborators)))


def functions():
    print("\n== 5. Maths functions on cases with known answers")
    from faculty_match import h_index
    from faculty_network import ari, nmi
    check("h-index", [h_index(x) for x in ([10, 8, 5, 4, 3], [25, 8, 5, 3, 3], [0], [1, 1, 1], [])] == [4, 3, 0, 1, 0])
    a, b = [0, 0, 1, 1, 2, 2], [5, 5, 7, 7, 9, 9]
    check("NMI = 1 for the same grouping with other labels", abs(nmi(a, b) - 1) < 1e-9)
    check("NMI = 0 for independent groupings", abs(nmi([0, 0, 1, 1], [0, 1, 0, 1])) < 1e-9)
    check("ARI = 1 for the same grouping, -0.5 for the textbook example",
          abs(ari(a, b) - 1) < 1e-9 and abs(ari([0, 0, 1, 1], [0, 1, 0, 1]) + 0.5) < 1e-9)
    sub = json.loads((config.RAW_DIR / "links" / "subfields.json").read_text())
    det = pd.read_csv(OUT / "indian_connections_detailed.csv").dropna(subset=["weighted_jaccard"]).iloc[0]
    A, B = sub[config.INSTITUTES[det.your_inst]["openalex_id"]], sub[det.partner_id]
    sa = {k: v / sum(A.values()) for k, v in A.items()}
    sb = {k: v / sum(B.values()) for k, v in B.items()}
    ks = set(sa) | set(sb)
    wj = sum(min(sa.get(k, 0), sb.get(k, 0)) for k in ks) / sum(max(sa.get(k, 0), sb.get(k, 0)) for k in ks)
    check(f"weighted Jaccard recomputed by hand ({det.your_inst} - {det.partner_inst})", abs(wj - det.weighted_jaccard) < 0.001,
          f"{wj:.3f} vs {det.weighted_jaccard}")


def partners():
    print("\n== 6. Indian partners")
    det = pd.read_csv(OUT / "indian_connections_detailed.csv")
    ic = pd.read_csv(OUT / "indian_connections.csv")
    check("detailed file has the same partner rows as indian_connections.csv",
          set(zip(det.your_inst, det.partner_inst)) == set(zip(ic.your_inst, ic.partner_inst)))
    inc = pd.read_csv(OUT / "incoming_citations_by_institute.csv")
    x = det.merge(inc, left_on=["your_inst", "partner_inst"], right_on=["your_inst", "citing_inst"])
    check("cites_from_partner = incoming file", (x.cites_from_partner == x.citations).all())
    check("no partner is one of our own institutes counted as 'other'",
          not det.partner_inst.isin([v["official_name"] for v in config.INSTITUTES.values()]).any(), warn=True)


def live(m):
    print("\n== 7. Live re-checks against OpenAlex (random samples)")
    import requests
    api = lambda path, **p: requests.get("https://api.openalex.org/" + path,
                                         params=dict(p, api_key=config.API_KEY, mailto=config.EMAIL), timeout=90).json()
    own = {v["openalex_id"] for v in config.INSTITUTES.values()}
    p = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "citations", "our_institutes"])
    p = p[p.citations.between(1, 40) & ~p.our_institutes.fillna(";").str.contains(";")].sample(12, random_state=7)
    agree = 0
    for w, inst in zip(p.openalex_work_id, p.our_institutes):
        d = api("works", filter=f"cites:{w}", per_page=50, select="authorships")
        live_flag = any(i.get("country_code") == "IN" and not ({x.rsplit("/", 1)[-1] for x in i.get("lineage") or []} &
                        {config.INSTITUTES[inst]["openalex_id"]})
                        for r in d["results"] for a in r["authorships"] for i in a["institutions"])
        ours = m[(m.openalex_work_id == w) & (m.institution == inst)].cited_by_indian_inst.iloc[0] == "TRUE"
        agree += live_flag == ours
    check(f"cited_by_indian_inst agrees with a fresh OpenAlex lookup for {agree}/12 papers", agree >= 11)
    perf = pd.read_csv(OUT / "stats" / "faculty_performance.csv")
    amap = pd.read_csv(OUT / "author_faculty_map.csv")
    ok = 0
    sample = perf[perf.papers >= 5].sample(6, random_state=3)
    for i, fn, papers in zip(sample.institution, sample.faculty_name, sample.papers):
        ids = "|".join(a for a in amap[(amap.institution == i) & (amap.faculty_name == fn)].author_id if a.startswith("A"))
        d = api("works", filter=f"author.id:{ids},institutions.id:{config.INSTITUTES[i]['openalex_id']},"
                f"publication_year:2016-2026,type:article|review|conference-paper|letter", per_page=1)
        if "meta" not in d:
            print(f"      {fn} ({i}): OpenAlex error {str(d)[:150]}")
            continue
        n = d["meta"]["count"]
        ok += 0.85 * n <= papers <= n * 1.1 + 1
        print(f"      {fn} ({i}): ours {papers}, OpenAlex {n}")
    check(f"faculty paper counts within ~15% of OpenAlex for {ok}/6 faculty", ok >= 5)
    det = pd.read_csv(OUT / "indian_connections_detailed.csv")
    csir = det[det.partner_cluster == "CSIR"].drop_duplicates("partner_id").sample(4, random_state=2)
    d = api("institutions", filter="openalex_id:" + "|".join(csir.partner_id), select="display_name,associated_institutions")
    good = sum(any("scientific and industrial research" in a["display_name"].lower()
                   for a in r.get("associated_institutions") or []) for r in d["results"])
    check(f"partners labelled CSIR really have CSIR as parent ({good}/4)", good == 4,
          ", ".join(r["display_name"] for r in d["results"]))


def main():
    m = structure()
    citations(m)
    # the faculty checks need every author row (group15_data.csv keeps faculty rows only): corpus_filter.py keeps the full table
    full = OUT / "all_authors" / "group15_data.csv"
    faculty(pd.read_csv(full, dtype=str) if full.exists() else m)
    networks(m)
    functions()
    partners()
    if "--live" in sys.argv:
        live(m)
    print(f"\nSUMMARY: {results.count('PASS')} passed, {results.count('FAIL')} failed, {results.count('WARN')} warnings")
    sys.exit(1 if "FAIL" in results else 0)


if __name__ == "__main__":
    main()
