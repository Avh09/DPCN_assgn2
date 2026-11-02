"""Outgoing citations: which Indian institutes' papers do our authors cite?

Needs data/raw/links/referenced.jsonl from `links.py refs` (institutes of every paper our
papers cite). References that are themselves in our dataset use the author affiliations we
already have. An institute counts as "another Indian institute" for a citing paper of
institute X when it has country IN and is not X itself.

Writes to data/out/:
  outgoing_citations_by_institute.csv   your_inst, cited_inst, cluster, citations, citing_papers, cited_papers
  outgoing_citations_by_year.csv        your_inst, year, references, resolved, to_other_indian
  citation_network_with_outside.csv     citation_network.csv + edges to outside Indian papers
  group15_data.csv                      cites_indian_inst filled in (TRUE/FALSE)
  stats/outflow_results.json
"""
import json
from collections import Counter, defaultdict

import pandas as pd

import config
from networks import cluster_of

OUT = config.OUT_DIR


def main():
    papers = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str})
    auth = pd.read_csv(OUT / "authorships.csv", usecols=["openalex_work_id", "institutions_detail"])

    # institutions of every referenced work: {work_id: [(name, country, ours, type), ...]}
    insts = {}
    for line in open(config.RAW_DIR / "links" / "referenced.jsonl"):
        r = json.loads(line)
        insts[r["id"]] = [(n, c, o, t) for _, n, c, o, t in r["insts"] if n]
    fetched = len(insts)
    corpus = defaultdict(dict)
    for wid, det in zip(auth.openalex_work_id, auth.institutions_detail):
        for d in str(det).split(";"):
            x = d.split("|")
            if len(x) == 3 and x[0] and x[0] != "nan":
                corpus[wid][x[0]] = (x[0], x[1], "", x[2])
    for wid, d in corpus.items():
        insts[wid] = list(d.values())
    resolved_ids = {w for w, v in insts.items() if v}
    print("fetched", fetched, "| works with institute info:", len(resolved_ids))

    # recognise our own institutes by name too (references that are in our own dataset
    # carry no institute id), so a paper's own institute is never counted as "another" one
    own_by_name = {v["official_name"].lower(): k for k, v in config.INSTITUTES.items()}
    for w in insts:
        insts[w] = [(n, c, o or own_by_name.get(n.lower(), ""), t) for n, c, o, t in insts[w]]

    P = papers.set_index("openalex_work_id")
    pid = {w: (d if isinstance(d, str) and d else f"openalex:{w}") for w, d in zip(papers.openalex_work_id, papers.doi)}
    ours_set = set(config.INSTITUTES)

    cnt = Counter()                # (your, cited) -> citations
    citing = defaultdict(set)      # (your, cited) -> citing paper ids
    cited_w = defaultdict(set)     # (your, cited) -> cited work ids
    yr = defaultdict(lambda: [0, 0, 0])    # (your, year) -> refs, resolved, to other indian
    paper_flag = {}                # (paper, your) -> bool
    outside_edges = []
    for wid, refs, year, our in zip(papers.openalex_work_id, papers.referenced_works, papers.year,
                                    papers.our_institutes):
        if not (isinstance(refs, str) and isinstance(our, str)):
            continue
        refs = refs.split(";")
        for your in our.split(";"):
            flag = False
            y = yr[(your, int(year))]
            for r in refs:
                y[0] += 1
                if r not in resolved_ids:
                    continue
                y[1] += 1
                indian = [(n, t) for n, c, o, t in insts[r] if c == "IN" and o != your]
                if indian:
                    flag = True
                    y[2] += 1
                    for n, t in indian:
                        k = (your, n)
                        cnt[k] += 1
                        citing[k].add(wid)
                        cited_w[k].add(r)
                    if r not in P.index:   # a paper outside our dataset -> edge for the network file
                        outside_edges.append((pid[wid], f"openalex:{r}", your,
                                              ";".join(n for n, _ in indian), int(year)))
            paper_flag[(wid, your)] = flag

    types = {}
    for w in insts.values():
        for n, c, o, t in w:
            types.setdefault(n, t)
    rows = [{"your_inst": k[0], "cited_inst": k[1], "cluster": cluster_of(k[1], types.get(k[1], "")),
             "citations": v, "citing_papers": len(citing[k]), "cited_papers": len(cited_w[k])}
            for k, v in cnt.items()]
    by_inst = pd.DataFrame(rows).sort_values(["your_inst", "citations"], ascending=[True, False])
    by_inst.to_csv(OUT / "outgoing_citations_by_institute.csv", index=False)
    by_year = pd.DataFrame([{"your_inst": k[0], "year": k[1], "references": v[0], "resolved": v[1],
                             "to_other_indian": v[2]} for k, v in sorted(yr.items())])
    by_year.to_csv(OUT / "outgoing_citations_by_year.csv", index=False)

    # network file with outside edges
    base = pd.read_csv(OUT / "citation_network.csv")
    ex = pd.DataFrame(outside_edges, columns=["source_doi", "target_doi", "source_inst", "target_inst", "year"])
    ex["source_inst"] = ex.source_inst
    pd.concat([base, ex[base.columns]]).to_csv(OUT / "citation_network_with_outside.csv", index=False)

    # paper flag into the main file
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    m["cites_indian_inst"] = [paper_flag.get((w, i)) for w, i in zip(m.openalex_work_id, m.institution)]
    m["cites_indian_inst"] = m.cites_indian_inst.map({True: "TRUE", False: "FALSE"}).fillna("")
    m.to_csv(OUT / "group15_data.csv", index=False)

    res = {}
    for your in config.INSTITUTES:
        d = by_inst[by_inst.your_inst == your]
        y = by_year[by_year.your_inst == your]
        tot_ref, tot_res, tot_ind = int(y.references.sum()), int(y.resolved.sum()), int(y.to_other_indian.sum())
        pp = [v for (w, i), v in paper_flag.items() if i == your]
        res[your] = {
            "references_total": tot_ref, "references_with_institute_info": tot_res,
            "resolved_%": round(tot_res / tot_ref * 100, 1),
            "references_to_other_indian_institutes": tot_ind,
            "share_of_resolved_refs_to_other_indian_%": round(tot_ind / tot_res * 100, 1),
            "distinct_indian_institutes_cited": len(d),
            "papers_citing_another_indian_institute_%": round(sum(pp) / len(pp) * 100, 1),
            "top10_cited_institutes": d.head(10)[["cited_inst", "cluster", "citations", "citing_papers"]].to_dict("records"),
            "citations_by_cluster": d.groupby("cluster").citations.sum().sort_values(ascending=False).to_dict(),
            "by_year": {int(a): {"to_other_indian": int(b), "resolved": int(c)} for a, b, c in
                        zip(y.year, y.to_other_indian, y.resolved)},
            "to_our_other_two_institutes": {own_by_name[n.lower()]: int(c) for n, c in zip(d.cited_inst, d.citations)
                                            if n.lower() in own_by_name},
        }
    (OUT / "stats" / "outflow_results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: {x: y for x, y in v.items() if x in ("references_total", "resolved_%",
          "share_of_resolved_refs_to_other_indian_%", "distinct_indian_institutes_cited",
          "papers_citing_another_indian_institute_%")} for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
