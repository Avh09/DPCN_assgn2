"""Step 8 + network analysis (Step 10). Local data only, no API calls.

Writes to data/out/:
  citation_network.csv           source_doi, target_doi, source_inst, target_inst, year
                                 (edges between papers of OUR corpus only; edges to papers
                                 outside the corpus need links.py / the OpenAlex lookups)
  authorship_network.csv         author_a, author_b, paper_doi, inst_a, inst_b, year
  authorship_network_ids.csv     same + author ids and countries (used for the analysis)
  indian_connections.csv         your_inst, partner_inst, shared_papers, total_citations
  indian_connections_detailed.csv  + partner type / cluster
and data/out/stats/network_results.json
"""
import itertools
import json
import re
from collections import Counter

import networkx as nx
import numpy as np
import pandas as pd

import config

OUT = config.OUT_DIR
STATS = OUT / "stats"
STATS.mkdir(exist_ok=True)
MAX_AUTHORS = 30  # papers with more authors stay in the files but are left out of the analysis


def doi_or_id(doi, wid):
    return doi if isinstance(doi, str) and doi else f"openalex:{wid}"


def cluster_of(name, typ):
    n = (name or "").lower()
    if "indian institute of technology" in n or re.search(r"\biit\b", n):
        return "IIT"
    if "national institute of technology" in n or re.search(r"\bnit\b", n):
        return "NIT"
    if "indian institute of information technology" in n or "international institute of information technology" in n or "iiit" in n or "iiitdm" in n:
        return "IIIT"
    if "iiser" in n or "science education and research" in n:
        return "IISER"
    if "council of scientific" in n or "csir" in n:
        return "CSIR"
    if "indian institute of science" in n or "indian statistical" in n or "tata institute" in n:
        return "Premier science inst."
    if "atomic" in n or "bhabha" in n:
        return "DAE"
    if typ == "company":
        return "Industry"
    if typ == "healthcare" or "medical" in n or "aiims" in n or "hospital" in n:
        return "Medical/health"
    if "universit" in n or typ == "education":
        return "University/college"
    if typ == "government":
        return "Government lab/agency"
    return "Other"


def citation_flow_matrix(ce, insts=None):
    """Citation-flow matrix from an edge table with columns source_inst, target_inst ("A;B" for papers of several institutes).

    Convention: row = CITING institute, column = CITED institute, entry (A, B) = citations from papers of A to papers of B.
    A paper written with authors from several of our institutes belongs to ALL of them (full counting), so a citation between
    two joint papers adds to every (A, B) pair; it is never assigned by author order. Returns (counts, row percentages, edge table
    with the helper columns cites_from, cites_to, within)."""
    insts = list(insts or config.INSTITUTES)
    ce = ce.copy()
    split = lambda s: [x for x in s.split(";") if x] if isinstance(s, str) and s else ["none"]
    ce["cites_from"] = ce.source_inst.map(split)
    ce["cites_to"] = ce.target_inst.map(split)
    pair_counts = {}
    for S_, T_ in zip(ce.cites_from, ce.cites_to):
        for a in S_:
            for b in T_:
                pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1
    flow = pd.Series(pair_counts, dtype=float).unstack(fill_value=0).reindex(index=insts, columns=insts, fill_value=0).astype(int)
    flow_pct = (flow.div(flow.sum(axis=1), axis=0) * 100).round(1)
    ce["within"] = [bool(set(a) & set(b)) for a, b in zip(ce.cites_from, ce.cites_to)]
    return flow, flow_pct, ce


def main():
    papers = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str})
    papers["pid"] = [doi_or_id(d, w) for d, w in zip(papers.doi, papers.openalex_work_id)]
    P = papers.set_index("openalex_work_id")
    auth = pd.read_csv(OUT / "authorships.csv")
    auth["author_key"] = auth.author_id.fillna("NAME:" + auth.author_name.str.lower().str.strip())
    authors = pd.read_csv(OUT / "authors.csv")
    core_keys = set(authors[authors.is_core_author].author_id)
    res = {}

    # ------------------------------------------------------------ citation network
    ids = set(papers.openalex_work_id)
    edges = []
    for wid, refs, yr, inst in zip(papers.openalex_work_id, papers.referenced_works,
                                   papers.year, papers.our_institutes):
        if not isinstance(refs, str):
            continue
        for r in refs.split(";"):
            if r in ids and r != wid:
                edges.append((wid, r, yr))
    ce = pd.DataFrame(edges, columns=["src", "dst", "year"])
    ce["source_doi"] = ce.src.map(P.pid)
    ce["target_doi"] = ce.dst.map(P.pid)
    ce["source_inst"] = ce.src.map(P.our_institutes)
    ce["target_inst"] = ce.dst.map(P.our_institutes)
    ce[["source_doi", "target_doi", "source_inst", "target_inst", "year"]].to_csv(
        OUT / "citation_network.csv", index=False)

    # the submission file is keyed by DOI (as the brief asks); this one is keyed by the canonical OpenAlex work id, which
    # every paper has, so DOI-less papers keep their network metrics
    ce[["src", "dst", "year", "source_inst", "target_inst"]].rename(columns={"src": "source_id", "dst": "target_id"}).to_csv(
        OUT / "citation_network_ids.csv", index=False)

    G = nx.DiGraph()
    G.add_edges_from(zip(ce.src, ce.dst))
    indeg = pd.Series(dict(G.in_degree()))
    pr = nx.pagerank(G, alpha=0.85)
    prs = pd.Series(pr).sort_values(ascending=False)
    top_pr = []
    for wid in prs.index[:10]:
        r = P.loc[wid]
        top_pr.append({"title": r.title, "year": int(r.year), "inst": r.our_institutes,
                       "journal": r.journal_name, "pagerank": round(prs[wid], 6),
                       "in_degree_in_corpus": int(indeg.get(wid, 0)), "citations_openalex": int(r.citations)})
    flow, flow_pct, ce = citation_flow_matrix(ce)
    within = int(ce.within.sum())
    joint_edges = int(sum(len(a) > 1 or len(b) > 1 for a, b in zip(ce.cites_from, ce.cites_to)))
    res["citation_network"] = {
        "nodes_in_edges": G.number_of_nodes(), "edges": G.number_of_edges(),
        "papers_in_corpus": len(papers),
        "share_papers_cited_by_another_corpus_paper": round((indeg > 0).sum() / len(papers) * 100, 1),
        "in_degree_max": int(indeg.max()), "in_degree_mean_over_all_papers":
            round(indeg.sum() / len(papers), 3),
        "in_degree_median_over_cited": float(indeg[indeg > 0].median()),
        "in_degree_quantiles_over_cited": indeg[indeg > 0].quantile([.5, .9, .99]).tolist(),
        "edges_within_same_institute": within, "edges_cross_institute": int(len(ce) - within),
        "edges_involving_joint_papers": joint_edges,
        # orient="index": {citing institute: {cited institute: citations}}  (to_dict() alone gives the transpose)
        "flow_matrix_source_rows_target_cols": flow.to_dict(orient="index"),
        "flow_matrix_row_pct": flow_pct.to_dict(orient="index"),
        "edges_per_source_year": ce.groupby("year").size().to_dict(),
        "weakly_connected_components": nx.number_weakly_connected_components(G),
        "largest_weak_component": len(max(nx.weakly_connected_components(G), key=len)),
        "top10_pagerank": top_pr,
    }
    # self-institute vs. cross-institute citation share per institute (as source)
    share = {}
    for i in config.INSTITUTES:
        s = ce[[i in x for x in ce.cites_from]]
        share[i] = {"edges_out": len(s), "to_same_inst_%": round(float(np.mean([i in t for t in s.cites_to])) * 100, 1) if len(s) else None}
    res["citation_network"]["per_institute_outgoing_share"] = share

    # --------------------------------------------------------- authorship network
    def label(row_names, row_ours):
        pass

    pairs = []
    for wid, g in auth.groupby("openalex_work_id", sort=False):
        yr = int(P.at[wid, "year"])
        pid = P.at[wid, "pid"]
        people = []
        for key, name, ours, inst, det in zip(g.author_key, g.author_name, g.our_inst,
                                               g.institution_names, g.institutions_detail):
            if isinstance(ours, str) and ours:
                lab, cc = ours.split(";")[0], "IN"
            else:
                dets = [d.split("|") for d in str(det).split(";") if d and d != "nan"]
                ind = [d for d in dets if len(d) > 1 and d[1] == "IN"]
                pick = (ind or dets or [["", ""]])[0]
                lab, cc = pick[0], (pick[1] if len(pick) > 1 else "")
            people.append((key, name, lab, cc))
        n = len(people)
        for a, b in itertools.combinations(people, 2):
            if a[0] == b[0]:
                continue
            pairs.append((a[1], b[1], pid, a[2], b[2], yr, a[0], b[0], a[3], b[3], n, wid))
    pe = pd.DataFrame(pairs, columns=["author_a", "author_b", "paper_doi", "inst_a", "inst_b", "year",
                                      "id_a", "id_b", "cc_a", "cc_b", "n_authors", "wid"])
    pe[["author_a", "author_b", "paper_doi", "inst_a", "inst_b", "year"]].to_csv(
        OUT / "authorship_network.csv", index=False)
    pe.drop(columns=["wid"]).to_csv(OUT / "authorship_network_ids.csv", index=False)

    ours_names = set(config.INSTITUTES)
    pe["ours_a"] = pe.inst_a.isin(ours_names)
    pe["ours_b"] = pe.inst_b.isin(ours_names)
    use = pe[pe.n_authors <= MAX_AUTHORS]
    both = use[use.ours_a & use.ours_b]
    w = both.groupby(["id_a", "id_b"]).size().reset_index(name="weight")
    name_of = dict(zip(authors.author_id, authors.author))
    inst_of = dict(zip(authors.author_id, authors.institution))
    field_of = dict(zip(authors.author_id, authors.main_field))
    GA = nx.Graph()
    GA.add_weighted_edges_from(w.itertuples(index=False, name=None))
    for n_ in GA.nodes:
        GA.nodes[n_]["inst"] = inst_of.get(n_, "")
    core_nodes = [n_ for n_ in GA.nodes if n_ in core_keys]
    GC = GA.subgraph(core_nodes).copy()

    def describe(Gx, exact_betw=True):
        d = {"nodes": Gx.number_of_nodes(), "edges": Gx.number_of_edges(),
             "density": round(nx.density(Gx), 5),
             "avg_degree": round(2 * Gx.number_of_edges() / max(1, Gx.number_of_nodes()), 2),
             "connected_components": nx.number_connected_components(Gx),
             "isolated_nodes": sum(1 for _ in nx.isolates(Gx)),
             "avg_clustering": round(nx.average_clustering(Gx), 3)}
        lcc = Gx.subgraph(max(nx.connected_components(Gx), key=len))
        d["largest_component_nodes"] = lcc.number_of_nodes()
        d["largest_component_share_%"] = round(lcc.number_of_nodes() / Gx.number_of_nodes() * 100, 1)
        comms = nx.community.louvain_communities(Gx, weight="weight", seed=42)
        d["louvain_communities"] = len(comms)
        d["louvain_modularity"] = round(nx.community.modularity(Gx, comms, weight="weight"), 3)
        big = sorted(comms, key=len, reverse=True)
        d["largest_communities"] = []
        for c in big[:6]:
            insts = Counter(inst_of.get(x, "") for x in c)
            fields = Counter(field_of.get(x, "") for x in c)
            top_auth = sorted(c, key=lambda x: Gx.degree(x, weight="weight"), reverse=True)[:3]
            d["largest_communities"].append({
                "size": len(c), "institutes": dict(insts.most_common()),
                "top_fields": dict(fields.most_common(2)), "top_members": [name_of.get(x, x) for x in top_auth]})
        d["assortativity_by_institute"] = round(nx.attribute_assortativity_coefficient(Gx, "inst"), 3)
        deg = nx.degree_centrality(Gx)
        k = None if exact_betw else 300
        bet = nx.betweenness_centrality(Gx, k=k, seed=1, weight=None)
        top = sorted(deg, key=deg.get, reverse=True)[:10]
        d["top10_degree"] = [{"author": name_of.get(x, x), "inst": inst_of.get(x, ""),
                              "collaborators": Gx.degree(x), "degree_centrality": round(deg[x], 4)} for x in top]
        topb = sorted(bet, key=bet.get, reverse=True)[:10]
        d["top10_betweenness"] = [{"author": name_of.get(x, x), "inst": inst_of.get(x, ""),
                                   "betweenness": round(bet[x], 4), "collaborators": Gx.degree(x)} for x in topb]
        cross = sum(1 for a, b in Gx.edges if inst_of.get(a) != inst_of.get(b))
        d["edges_between_our_institutes"] = cross
        d["edges_between_our_institutes_%"] = round(cross / max(1, Gx.number_of_edges()) * 100, 1)
        return d

    res["authorship_network_all_our_authors"] = describe(GA, exact_betw=False)
    res["authorship_network_core_authors"] = describe(GC, exact_betw=True)
    res["authorship_network_meta"] = {
        "pair_rows_in_file": len(pe), "pairs_used_in_analysis": len(use),
        "papers_over_30_authors_excluded": int(papers[papers.n_authors > MAX_AUTHORS].shape[0]),
        "counting": "full counting (every joint paper adds 1 to the edge weight)"}

    # ------------------------------------------------------ Indian connections
    types = {}
    for det in auth.institutions_detail.dropna():
        for d in det.split(";"):
            x = d.split("|")
            if len(x) == 3 and x[0]:
                types.setdefault(x[0], x[2])
    rows = []
    for wid, ours, partners, cites in zip(papers.openalex_work_id, papers.our_institutes,
                                          papers.coauthor_indian_institutes, papers.citations):
        if not (isinstance(ours, str) and isinstance(partners, str)):
            continue
        for o in ours.split(";"):
            for p_ in partners.split(";"):
                rows.append((o, p_, wid, cites))
    ic = pd.DataFrame(rows, columns=["your_inst", "partner_inst", "wid", "cites"])
    agg = ic.groupby(["your_inst", "partner_inst"]).agg(
        shared_papers=("wid", "nunique"), total_citations=("cites", "sum")).reset_index() \
        .sort_values(["your_inst", "shared_papers"], ascending=[True, False])
    agg.to_csv(OUT / "indian_connections.csv", index=False)
    agg["partner_type"] = agg.partner_inst.map(lambda n: types.get(n, ""))
    agg["partner_cluster"] = [cluster_of(n, t) for n, t in zip(agg.partner_inst, agg.partner_type)]
    agg["your_cluster"] = agg.your_inst.map(lambda n: cluster_of(config.INSTITUTES[n]["official_name"], "education"))
    agg.to_csv(OUT / "indian_connections_detailed.csv", index=False)

    ind = {}
    for i, g in agg.groupby("your_inst"):
        ind[i] = {
            "distinct_indian_partners": len(g),
            "top10_partners": g.head(10)[["partner_inst", "shared_papers", "total_citations"]].to_dict("records"),
            "shared_papers_by_partner_cluster": g.groupby("partner_cluster").shared_papers.sum()
            .sort_values(ascending=False).to_dict(),
            "partners_by_cluster_count": g.partner_cluster.value_counts().to_dict(),
        }
    # papers with at least one Indian / international coauthor
    cc = auth.copy()
    cc["countries"] = cc.country_codes.fillna("").str.split(";")
    pc = cc.groupby("openalex_work_id").countries.apply(lambda s: {c for l in s for c in l if c})
    papers["has_foreign"] = papers.openalex_work_id.map(lambda w: any(c != "IN" for c in pc.get(w, set())))
    papers["has_indian_partner"] = papers.coauthor_indian_institutes.notna()
    for i in config.INSTITUTES:
        s = papers[papers.our_institutes.fillna("").str.contains(i, regex=False)]
        ind[i]["papers"] = len(s)
        ind[i]["share_with_other_indian_institute_%"] = round(s.has_indian_partner.mean() * 100, 1)
        ind[i]["share_with_foreign_coauthor_%"] = round(s.has_foreign.mean() * 100, 1)
        cn = Counter(c for w_ in s.openalex_work_id for c in pc.get(w_, set()) if c != "IN")
        ind[i]["top_foreign_countries"] = dict(cn.most_common(8))
    # joint papers among our three institutes
    two = papers[papers.our_institutes.fillna("").str.contains(";")]
    ind["papers_with_authors_from_2_or_3_of_our_institutes"] = len(two)
    ind["pair_counts"] = two.our_institutes.value_counts().to_dict()
    # cross-cluster links (our NIT <-> partner cluster)
    ind["cross_cluster_shared_papers"] = agg.groupby(["your_cluster", "partner_cluster"]).shared_papers.sum() \
        .reset_index().sort_values("shared_papers", ascending=False).head(12).to_dict("records")

    # hub authors: our core authors with the most distinct OTHER Indian institutes (co-author pairs)
    hub = []
    for side in ("a", "b"):
        o_, p_ = ("a", "b") if side == "a" else ("b", "a")
        d = use[use[f"ours_{o_}"] & ~use[f"ours_{p_}"] & (use[f"cc_{p_}"] == "IN") & (use[f"inst_{p_}"] != "")]
        hub.append(d[[f"id_{o_}", f"inst_{p_}", "wid"]].rename(columns={f"id_{o_}": "aid", f"inst_{p_}": "partner"}))
    hub = pd.concat(hub)
    h = hub.groupby("aid").agg(partners=("partner", "nunique"), joint_papers=("wid", "nunique")) \
        .sort_values("partners", ascending=False)
    h = h[h.index.isin(core_keys)].head(10)
    ind["hub_authors_core"] = [{"author": name_of.get(a, a), "inst": inst_of.get(a, ""),
                                "distinct_indian_partner_institutes": int(r.partners),
                                "papers_with_them": int(r.joint_papers)} for a, r in h.iterrows()]
    # Jaccard of research fields between our institutes
    fs = {}
    for i in config.INSTITUTES:
        s = papers[papers.our_institutes.fillna("").str.contains(i, regex=False)]
        sh = s.field.value_counts(normalize=True)
        fs[i] = set(sh[sh >= 0.01].index)
    ind["jaccard_fields_between_our_institutes(fields>=1%_share)"] = {
        f"{a} vs {b}": round(len(fs[a] & fs[b]) / len(fs[a] | fs[b]), 3)
        for a, b in itertools.combinations(config.INSTITUTES, 2)}
    res["indian_connections"] = ind

    (STATS / "network_results.json").write_text(json.dumps(res, indent=1, default=str))
    print("done; citation edges", len(ce), "| author pairs", len(pe), "| connections rows", len(agg))


if __name__ == "__main__":
    main()
