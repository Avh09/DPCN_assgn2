"""Step 14: the remaining network and institute metrics from the metric checklist. Local data only. Runs after deep_analysis.py.

Citation network (papers, directed; citation_network.csv)
    stats/citation_node_metrics.csv     in-degree, out-degree, PageRank, HITS authority / hub, in-degree h-index per paper
    stats/citation_network_macro.json   density, clustering, reciprocity, components (whole corpus and per institute)
    stats/citation_velocity.csv         citations received per year (by year of the citing paper), cumulative, and the
                                        citations per paper and per year of age for each publication-year cohort
    stats/citation_flow_by_cluster.csv  share of incoming / outgoing citations by partner cluster (IIT, NIT, IISc, CSIR, ...)
Faculty co-authorship network (faculty_network_edges.csv, weights = joint papers)
    stats/faculty_node_metrics.csv      degree, strength, betweenness, closeness, eigenvector, k-core, Leiden community
    stats/faculty_network_extra.json    diameter, average shortest path, degree / h-index assortativity, max k-core
    stats/bridge_authors.csv            top 10 faculty per institute by co-authorship edges to other Indian institutes
Institutes
    stats/institution_summary.csv       one row per institute: volume, citations, institute h-index, quality, citation ratio
    stats/hyper_authorship_performance.csv  papers with more than 10 authors vs the rest
"""
import json

import networkx as nx
import numpy as np
import pandas as pd

import config
import movers

OUT, STATS = config.OUT_DIR, config.OUT_DIR / "stats"
INSTS = list(config.INSTITUTES)


def h_index(c):
    c = sorted((int(x) for x in c), reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


# ------------------------------------------------------------------------------ citation network
def citation_metrics():
    """Per-paper citation-network metrics, keyed by the canonical OpenAlex work id (DOI is optional, 86 papers have none).

    in_degree / pagerank are WITHIN THE CORPUS (citations between our own papers). They are not global influence:
    citations_openalex is the worldwide count. Each in-corpus citing link is classified as
      author self-citation        the two papers share a verified faculty author
      same institute, other author the papers share an institute but no faculty author
      between our institutes       the papers have no institute in common
    so "influence" can be read with self-citation removed (pagerank_excl_self, in_degree_excl_self)."""
    e = pd.read_csv(OUT / "citation_network_ids.csv", dtype=str).drop_duplicates(["source_id", "target_id"])
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str}, keep_default_na=False)
    p["cit"] = pd.to_numeric(p.citations, errors="coerce").fillna(0).astype(int)
    info = p.drop_duplicates("openalex_work_id").set_index("openalex_work_id")
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "faculty_name", "institution"])
    fac = m.groupby("openalex_work_id").faculty_name.apply(set).to_dict()
    insts = m.groupby("openalex_work_id").institution.apply(set).to_dict()
    G = nx.DiGraph()
    G.add_nodes_from(info.index)                       # every paper is a node, cited or not
    G.add_edges_from(zip(e.source_id, e.target_id))
    G.remove_edges_from(nx.selfloop_edges(G))
    kind = {}
    for s_, t_ in G.edges():
        if fac.get(s_, set()) & fac.get(t_, set()):
            kind[(s_, t_)] = "author_self"
        elif insts.get(s_, set()) & insts.get(t_, set()):
            kind[(s_, t_)] = "same_institute_other_author"
        else:
            kind[(s_, t_)] = "between_our_institutes"
    G2 = G.copy()
    G2.remove_edges_from([k for k, v in kind.items() if v == "author_self"])
    pr = nx.pagerank(G, alpha=0.85)
    pr2 = nx.pagerank(G2, alpha=0.85)
    hubs, auth = nx.hits(G, max_iter=1000, tol=1e-8)
    rows = []
    for n in G:
        cit = [info.cit.get(s_, 0) for s_ in G.predecessors(n)]
        c = {k: sum(1 for s_ in G.predecessors(n) if kind[(s_, n)] == k) for k in ("author_self", "same_institute_other_author", "between_our_institutes")}
        rows.append({"openalex_work_id": n, "doi": info.at[n, "doi"], "title": info.at[n, "title"], "year": info.at[n, "year"],
                     "institutes": info.at[n, "our_institutes"], "type": info.at[n, "type"], "citations_openalex": int(info.at[n, "cit"]),
                     "in_degree": G.in_degree(n), "out_degree": G.out_degree(n),
                     "in_self_citations": c["author_self"], "in_same_institute_other_author": c["same_institute_other_author"],
                     "in_between_our_institutes": c["between_our_institutes"], "in_degree_excl_self": G2.in_degree(n),
                     "pagerank": pr[n], "pagerank_excl_self": pr2[n], "hits_authority": auth[n], "hits_hub": hubs[n],
                     "in_degree_h_index": h_index(cit)})
    d = pd.DataFrame(rows)
    # citation-age bias: PageRank is dominated by old papers, so also rank each paper within its own publication year
    d["pagerank_rank_in_year"] = d.groupby("year").pagerank.rank(ascending=False, method="min").astype(int)
    d["pagerank_pct_in_year"] = (d.groupby("year").pagerank.rank(pct=True) * 100).round(1)
    d["citations_pct_in_year"] = (d.groupby("year").citations_openalex.rank(pct=True) * 100).round(1)
    d = d.sort_values("pagerank", ascending=False)
    d.to_csv(STATS / "citation_node_metrics.csv", index=False)

    # who cites us, by kind of link, per institute (full counting for joint papers) and overall
    ek = pd.DataFrame([{"s": a, "t": b, "kind": k} for (a, b), k in kind.items()])
    src = {"overall": ek.kind.value_counts().to_dict()}
    for i in INSTS:
        sel = ek[[i in insts.get(a, set()) for a in ek.s]]
        src[i] = sel.kind.value_counts().to_dict()
    top_self = d.nlargest(1, "in_self_citations")[["title", "in_degree", "in_self_citations"]].to_dict("records")
    json.dump({"edges_by_kind": src, "definition": "author_self: citing and cited paper share a verified faculty author; same_institute_other_author: same institute, no shared faculty author; between_our_institutes: no institute in common",
               "most_self_cited_paper": top_self}, open(STATS / "citation_sources.json", "w"), indent=1, default=float)

    # degree distributions (in and out), zero-degree counted separately, plus CCDF
    ind, outd = pd.Series(dict(G.in_degree())), pd.Series(dict(G.out_degree()))
    ks = sorted(set(ind) | set(outd))
    dist = pd.DataFrame({"degree": ks, "papers_in_degree": [int((ind == k).sum()) for k in ks], "papers_out_degree": [int((outd == k).sum()) for k in ks]})
    dist["ccdf_in"] = [round(float((ind >= k).mean()), 6) for k in ks]
    dist["ccdf_out"] = [round(float((outd >= k).mean()), 6) for k in ks]
    dist.to_csv(STATS / "citation_degree_distribution.csv", index=False)

    macro = {}
    for label, nodes in [("whole corpus", set(G))] + [(i, {n for n in G if i in str(info.at[n, "our_institutes"])}) for i in INSTS]:
        H = G.subgraph(nodes)
        U = H.to_undirected()
        cc = list(nx.weakly_connected_components(H))
        macro[label] = {"papers": H.number_of_nodes(), "citation_links": H.number_of_edges(),
                        "density": round(nx.density(H), 6), "avg_clustering_undirected": round(nx.average_clustering(U), 4),
                        "reciprocity": round(nx.reciprocity(H) or 0, 4),
                        "weak_components": len(cc), "largest_component_share_%": round(max(len(c) for c in cc) / H.number_of_nodes() * 100, 1),
                        "papers_never_cited_in_corpus_%": round(sum(1 for n in H if H.in_degree(n) == 0) / H.number_of_nodes() * 100, 1),
                        "top3_by_authority": d[d.openalex_work_id.isin(nodes)].nlargest(3, "hits_authority")[["title", "hits_authority"]].to_dict("records"),
                        "top3_by_hub": d[d.openalex_work_id.isin(nodes)].nlargest(3, "hits_hub")[["title", "hits_hub"]].to_dict("records")}
    json.dump(macro, open(STATS / "citation_network_macro.json", "w"), indent=1, default=float)
    return d, macro


def citation_velocity():
    inc = pd.read_csv(OUT / "incoming_citations_by_year.csv")
    inc = inc[inc.year.between(2016, 2026)].assign(year=lambda x: x.year.astype(int))
    rows = []
    for i in INSTS:
        g = inc[inc.your_inst == i].sort_values("year")
        cum = g.citations.cumsum()
        for (_, r), c in zip(g.iterrows(), cum):
            rows.append({"institution": i, "table": "citations received, by year of the citing paper", "year": int(r.year),
                         "value": int(r.citations), "cumulative": int(c)})
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str}, keep_default_na=False)
    p["cit"] = pd.to_numeric(p.citations, errors="coerce").fillna(0)
    p["yr"] = pd.to_numeric(p.year)
    for i in INSTS:
        g = p[p.our_institutes.str.contains(i, regex=False)]
        for y, gg in g.groupby("yr"):
            age = max(2026.8 - y, 0.8)                 # 2026 data runs to about October
            rows.append({"institution": i, "table": "publication-year cohort: citations per paper per year of age", "year": int(y),
                         "value": round(gg.cit.mean() / age, 2), "cumulative": round(gg.cit.mean(), 2)})
    d = pd.DataFrame(rows)
    d.to_csv(STATS / "citation_velocity.csv", index=False)
    return d


def flow_by_cluster():
    rows = []
    for fname, col, direction in (("incoming_citations_by_institute.csv", "citing_inst", "incoming"),
                                  ("outgoing_citations_by_institute.csv", "cited_inst", "outgoing")):
        d = pd.read_csv(OUT / fname)
        t = d.groupby(["your_inst", "cluster"]).citations.sum().reset_index()
        t["share_%"] = (t.citations / t.groupby("your_inst").citations.transform("sum") * 100).round(1)
        t.insert(1, "direction", direction)
        rows.append(t)
    r = pd.concat(rows).sort_values(["your_inst", "direction", "citations"], ascending=[True, True, False])
    r.to_csv(STATS / "citation_flow_by_cluster.csv", index=False)
    return r


# ------------------------------------------------------------------------------ faculty network
def faculty_metrics():
    e = pd.read_csv(OUT / "faculty_network_edges.csv")
    fp = pd.read_csv(STATS / "faculty_performance.csv")
    nodes = pd.read_csv(OUT / "faculty_network_nodes.csv")
    G = nx.Graph()
    alias = movers.aliases()      # a person listed at two of our institutes is one node (their current record)
    for r in fp.itertuples():
        if (r.institution, r.faculty_name) in alias:
            continue
        G.add_node((r.institution, r.faculty_name), h=int(r.h_index), papers=int(r.papers), dept=r.department)
    for r in e.itertuples():
        G.add_edge((r.inst_a, r.faculty_a), (r.inst_b, r.faculty_b), weight=int(r.joint_papers))
    comp = max(nx.connected_components(G), key=len)
    L = G.subgraph(comp)
    close = nx.closeness_centrality(G)                      # Wasserman-Faust: fine for disconnected graphs
    eig = nx.eigenvector_centrality_numpy(L, weight="weight")
    core = nx.core_number(G)
    bet = dict(zip(zip(nodes.institution, nodes.faculty_name), nodes.betweenness))
    leid = dict(zip(zip(nodes.institution, nodes.faculty_name), nodes.community_leiden))
    def participation(n, label):
        """P_i = 1 - sum_c (k_ic / k_i)^2 : 0 when all links stay in one group, close to 1 when spread evenly over many
        groups. Undefined (NaN) for isolated nodes (k_i = 0), which are reported as such, not as 0."""
        k = G.degree(n)
        if k == 0:
            return float("nan")
        cnt = {}
        for nb in G.neighbors(n):
            cnt[label(nb)] = cnt.get(label(nb), 0) + 1
        return round(1 - sum((v / k) ** 2 for v in cnt.values()), 4)
    dept_of = lambda n: (G.nodes[n].get("dept", ""), n[0])
    rows = []
    for n in G:
        rows.append({"participation_dept": participation(n, dept_of), "participation_community": participation(n, lambda x: leid.get(x)),
                     "institution": n[0], "faculty_name": n[1], "department": G.nodes[n].get("dept", ""),
                     "papers": G.nodes[n].get("papers", 0), "h_index": G.nodes[n].get("h", 0),
                     "degree": G.degree(n), "strength_joint_papers": G.degree(n, weight="weight"),
                     "betweenness": bet.get(n, 0), "closeness": round(close[n], 5),
                     "eigenvector": round(eig.get(n, 0), 6), "k_core": core[n], "community_leiden": leid.get(n)})
    d = pd.DataFrame(rows).sort_values(["institution", "degree"], ascending=[True, False])
    d.to_csv(STATS / "faculty_node_metrics.csv", index=False)

    def macro(H, label):
        cc = max(nx.connected_components(H), key=len) if H.number_of_nodes() else set()
        Lc = H.subgraph(cc)
        hs = {n: H.nodes[n]["h"] for n in H}
        nx.set_node_attributes(H, hs, "h")
        return {"scope": label, "faculty": H.number_of_nodes(), "links": H.number_of_edges(),
                "largest_component_faculty": len(cc),
                "diameter_largest_component": nx.diameter(Lc) if len(cc) > 1 else 0,
                "avg_shortest_path_largest_component": round(nx.average_shortest_path_length(Lc), 3) if len(cc) > 1 else 0,
                "degree_assortativity": round(nx.degree_assortativity_coefficient(H), 3),
                "h_index_assortativity": round(nx.numeric_assortativity_coefficient(H, "h"), 3),
                "max_k_core": max(nx.core_number(H).values()) if H.number_of_edges() else 0,
                "faculty_in_max_core": sum(1 for v in nx.core_number(H).values() if v == max(nx.core_number(H).values()))}
    res = [macro(G, "all three institutes")] + [macro(G.subgraph([n for n in G if n[0] == i]).copy(), i) for i in INSTS]
    json.dump(res, open(STATS / "faculty_network_extra.json", "w"), indent=1, default=float)
    return d, res


def bridge_authors():
    amap = pd.read_csv(OUT / "author_faculty_map.csv", dtype=str)
    fid = dict(zip(zip(amap.institution, amap.author_id), amap.faculty_name))
    ours = set(INSTS)
    a = pd.read_csv(OUT / "authorship_network_ids.csv", dtype=str, keep_default_na=False,
                    usecols=["inst_a", "inst_b", "id_a", "id_b", "cc_a", "cc_b", "paper_doi"])
    rows = []
    for side, other in (("a", "b"), ("b", "a")):
        x = a[a[f"inst_{side}"].isin(ours)]
        x = x.assign(fac=[fid.get((i, k)) for i, k in zip(x[f"inst_{side}"], x[f"id_{side}"])])
        x = x[x.fac.notna() & (x[f"cc_{other}"] == "IN") & (x[f"inst_{other}"] != x[f"inst_{side}"])]
        rows.append(pd.DataFrame({"institution": x[f"inst_{side}"], "faculty_name": x.fac, "partner_inst": x[f"inst_{other}"],
                                  "doi": x.paper_doi}))
    d = pd.concat(rows)
    g = d.groupby(["institution", "faculty_name"]).agg(cross_institute_edges=("partner_inst", "size"),
                                                         distinct_indian_partner_institutes=("partner_inst", "nunique"),
                                                         joint_papers=("doi", "nunique")).reset_index()
    top = g.sort_values(["institution", "cross_institute_edges"], ascending=[True, False]).groupby("institution").head(10)
    top.to_csv(STATS / "bridge_authors.csv", index=False)
    return top


# ------------------------------------------------------------------------------ institutes
def institutes():
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    m["cit"] = pd.to_numeric(m.citations, errors="coerce").fillna(0)
    cr = pd.read_csv(STATS / "citation_ratio.csv")
    cr = cr[cr.year == "2016-2026"].set_index("your_inst")
    rows, hy = [], []
    for i in INSTS:
        g = m[m.institution == i]
        pp = g.drop_duplicates("openalex_work_id")
        j = pp[(pp.type == "journal") & pp.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
        rows.append({"institution": i, "papers": len(pp), "journal_papers": int((pp.type == "journal").sum()),
                     "conference_papers": int((pp.type == "conference").sum()), "faculty_with_papers": g.faculty_name.nunique(),
                     "total_citations": int(pp.cit.sum()), "citations_per_paper": round(pp.cit.mean(), 2),
                     "institute_h_index": h_index(pp.cit), "journal_Q1_%": round((j.quartile == "Q1").mean() * 100, 1),
                     "journal_Q2_%": round((j.quartile == "Q2").mean() * 100, 1), "journal_Q3_%": round((j.quartile == "Q3").mean() * 100, 1),
                     "journal_Q4_%": round((j.quartile == "Q4").mean() * 100, 1),
                     "Q1_and_IF_gt5": int((pp.q1_impact_gt5 == "TRUE").sum()), "Q1_and_IF_gt10": int((pp.q1_impact_gt10 == "TRUE").sum()),
                     "papers_over_10_authors_%": round((pp.is_multi_author_10plus == "TRUE").mean() * 100, 2),
                     "in_cites_from_other_indian": int(cr.at[i, "in_cites"]), "out_cites_to_other_indian": int(cr.at[i, "out_cites"]),
                     "in_over_out_ratio": float(cr.at[i, "in_over_out"])})
        for label, gg in (("more than 10 authors", pp[pp.is_multi_author_10plus == "TRUE"]),
                          ("10 or fewer authors", pp[pp.is_multi_author_10plus != "TRUE"])):
            jj = gg[(gg.type == "journal") & gg.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
            hy.append({"institution": i, "group": label, "papers": len(gg), "share_of_papers_%": round(len(gg) / len(pp) * 100, 2),
                       "mean_citations": round(gg.cit.mean(), 2), "median_citations": float(gg.cit.median()),
                       "share_of_citations_%": round(gg.cit.sum() / pp.cit.sum() * 100, 2),
                       "journal_Q1_%": round((jj.quartile == "Q1").mean() * 100, 1) if len(jj) else None,
                       "conference_share_%": round((gg.type == "conference").mean() * 100, 1)})
    pd.DataFrame(rows).to_csv(STATS / "institution_summary.csv", index=False)
    pd.DataFrame(hy).to_csv(STATS / "hyper_authorship_performance.csv", index=False)
    return pd.DataFrame(rows), pd.DataFrame(hy)


def main():
    STATS.mkdir(exist_ok=True)
    d, macro = citation_metrics()
    print("citation network (whole corpus):", {k: v for k, v in macro["whole corpus"].items() if not k.startswith("top")})
    print("most authoritative paper:", d.nlargest(1, "hits_authority")[["title", "hits_authority"]].to_dict("records"))
    citation_velocity()
    flow_by_cluster()
    fd, res = faculty_metrics()
    for r in res:
        print("faculty network:", r)
    b = bridge_authors()
    print("bridge authors, top per institute:\n", b.groupby("institution").head(2).to_string(index=False))
    s, hy = institutes()
    print(s.T.to_string(header=False))
    print(hy.to_string(index=False))


if __name__ == "__main__":
    main()
