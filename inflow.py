"""Incoming citations: which Indian institutes cite our papers? (mirror of outflow.py)

Needs data/raw/links/citing.jsonl from `links.py citing` (every work that cites one of our
papers, with the institutes of its authors). Same counting rule as outflow.py: a citation
of a paper of institute X counts as coming from "another Indian institute" when the citing
work has an author at an institute with country IN that is not X itself.

One citation = one (citing work, cited paper) pair. In the per-institute table a citing work
with authors at two Indian institutes counts for both; in the totals it counts once.

Writes to data/out/:
  incoming_citations_by_institute.csv   your_inst, citing_inst, cluster, citations, citing_papers, cited_papers
  incoming_citations_by_year.csv        your_inst, year, citations, resolved, from_other_indian, from_own_inst
  citation_flow_by_year.csv             your_inst, year, in_cites, out_cites (for the flow chart)
  group15_data.csv                      cited_by_indian_inst filled in (TRUE/FALSE)
  stats/inflow_results.json             totals, top 10 citing institutes, impact ratio
"""
import json
from collections import Counter, defaultdict

import pandas as pd

import config
from networks import cluster_of

OUT = config.OUT_DIR
LINKS = config.RAW_DIR / "links"


def main():
    papers = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "our_institutes", "citations"])
    our_of = {w: o.split(";") for w, o in zip(papers.openalex_work_id, papers.our_institutes) if isinstance(o, str)}

    # papers whose citing works were actually fetched (a batch is only marked done when complete)
    p_all = pd.read_csv(OUT / "papers.csv", usecols=["openalex_work_id", "citations"])
    cited_ids = p_all[p_all.citations > 0].openalex_work_id.tolist()
    done = set((LINKS / "citing.done").read_text().split()) if (LINKS / "citing.done").exists() else set()
    checked = set()
    for i in range(0, len(cited_ids), 50):
        if cited_ids[i] in done:
            checked.update(cited_ids[i:i + 50])
    f = LINKS / "citing.checked"                                    # per-work record written by links.py (survives corpus changes)
    if f.exists():
        checked |= set(f.read_text().split())
    checked |= set(p_all[p_all.citations == 0].openalex_work_id)   # nothing to fetch: not cited
    # a paper merged into another copy (duplicate_audit.csv) is cited under the kept copy's id
    merged_into = {}
    da = OUT / "duplicate_audit.csv"
    if da.exists():
        d = pd.read_csv(da, dtype=str)
        merged_into = dict(zip(d[d.decision == "merged"].other_work_id, d[d.decision == "merged"].kept_work_id))
    missing = len(cited_ids) - len(done) * 50
    print(f"batches done {len(done)} of {-(-len(cited_ids) // 50)}", "(INCOMPLETE)" if missing > 0 else "")

    own_by_name = {v["official_name"].lower(): k for k, v in config.INSTITUTES.items()}
    cnt = Counter()                 # (your, citing inst) -> citations
    citing = defaultdict(set)       # (your, citing inst) -> citing work ids
    cited_w = defaultdict(set)      # (your, citing inst) -> our cited papers
    yr = defaultdict(lambda: [0, 0, 0, 0])   # (your, year) -> citations, resolved, from other indian, from own
    paper_flag = defaultdict(bool)  # (paper, your) -> cited by another Indian institute
    types = {}
    seen = set()
    for line in open(LINKS / "citing.jsonl"):
        r = json.loads(line)
        insts = [(n, c, o or own_by_name.get((n or "").lower(), ""), t) for _, n, c, o, t in r["insts"] if n]
        for n, c, o, t in insts:
            types.setdefault(n, t)
        for p in r["cites_our"]:
            p = merged_into.get(p, p)
            if (r["id"], p) in seen or p not in our_of:   # batches can overlap on re-runs
                continue
            seen.add((r["id"], p))
            for your in our_of[p]:
                y = yr[(your, r["year"])]
                y[0] += 1
                if not insts:
                    continue
                y[1] += 1
                if any(o == your for _, _, o, _ in insts):
                    y[3] += 1
                indian = {n for n, c, o, t in insts if c == "IN" and o != your}
                if indian:
                    y[2] += 1
                    paper_flag[(p, your)] = True
                    for n in indian:
                        k = (your, n)
                        cnt[k] += 1
                        citing[k].add(r["id"])
                        cited_w[k].add(p)

    rows = [{"your_inst": k[0], "citing_inst": k[1], "cluster": cluster_of(k[1], types.get(k[1], "")),
             "citations": v, "citing_papers": len(citing[k]), "cited_papers": len(cited_w[k])}
            for k, v in cnt.items()]
    by_inst = pd.DataFrame(rows).sort_values(["your_inst", "citations", "citing_inst"], ascending=[True, False, True])
    by_inst.to_csv(OUT / "incoming_citations_by_institute.csv", index=False)
    by_year = pd.DataFrame([{"your_inst": k[0], "year": k[1], "citations": v[0], "resolved": v[1],
                             "from_other_indian": v[2], "from_own_inst": v[3]}
                            for k, v in sorted(yr.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))])
    by_year.to_csv(OUT / "incoming_citations_by_year.csv", index=False)

    # year-wise flow chart data: in = citations received that year, out = references made by papers of that year
    out_y = pd.read_csv(OUT / "outgoing_citations_by_year.csv")
    flow = (by_year[by_year.year.between(config.YEAR_FROM, config.YEAR_TO)]
            .rename(columns={"from_other_indian": "in_cites"})[["your_inst", "year", "in_cites"]]
            .merge(out_y.rename(columns={"to_other_indian": "out_cites"})[["your_inst", "year", "out_cites"]],
                   on=["your_inst", "year"], how="outer").fillna(0))
    flow[["year", "in_cites", "out_cites"]] = flow[["year", "in_cites", "out_cites"]].astype(int)
    flow.sort_values(["your_inst", "year"]).to_csv(OUT / "citation_flow_by_year.csv", index=False)

    # paper flag into the main file: TRUE/FALSE where checked, blank where the batch was not fetched
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str)
    m["cited_by_indian_inst"] = ["TRUE" if paper_flag[(w, i)] else ("FALSE" if w in checked else "")
                                 for w, i in zip(m.openalex_work_id, m.institution)]
    m.to_csv(OUT / "group15_data.csv", index=False)

    out_res = json.loads((OUT / "stats" / "outflow_results.json").read_text())
    res = {}
    for your in config.INSTITUTES:
        d = by_inst[by_inst.your_inst == your]
        y = by_year[by_year.your_inst == your]
        tot, resolved, ind, own = (int(y[c].sum()) for c in ("citations", "resolved", "from_other_indian", "from_own_inst"))
        out_ind = out_res[your]["references_to_other_indian_institutes"]
        pp = [paper_flag[(w, your)] for w, o in our_of.items() if your in o and w in checked]
        res[your] = {
            "citations_found": tot,
            "openalex_cited_by_total": int(papers[papers.our_institutes.str.contains(your, na=False)].citations.sum()),
            "citations_with_institute_info": resolved,
            "resolved_%": round(resolved / tot * 100, 1) if tot else None,
            "in_cites_from_other_indian_institutes": ind,
            "share_of_resolved_from_other_indian_%": round(ind / resolved * 100, 1) if resolved else None,
            "self_institute_citations_%": round(own / resolved * 100, 1) if resolved else None,
            "out_cites_to_other_indian_institutes": out_ind,
            "impact_ratio_in_over_out": round(ind / out_ind, 2) if out_ind else None,
            "distinct_indian_institutes_citing": len(d),
            "papers_cited_by_another_indian_institute_%": round(sum(pp) / len(pp) * 100, 1) if pp else None,
            "top10_citing_institutes": d.head(10)[["citing_inst", "cluster", "citations", "citing_papers"]].to_dict("records"),
            "citations_by_cluster": d.groupby("cluster").citations.sum().sort_values(ascending=False).to_dict(),
            "from_our_other_two_institutes": {own_by_name[n.lower()]: int(c) for n, c in zip(d.citing_inst, d.citations)
                                              if n.lower() in own_by_name},
        }
    (OUT / "stats" / "inflow_results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: {x: v[x] for x in ("citations_found", "openalex_cited_by_total", "resolved_%",
          "in_cites_from_other_indian_institutes", "out_cites_to_other_indian_institutes",
          "impact_ratio_in_over_out", "self_institute_citations_%",
          "papers_cited_by_another_indian_institute_%")} for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
