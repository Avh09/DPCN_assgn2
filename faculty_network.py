"""Faculty co-authorship network (run faculty_match.py first).

Same idea as the authorship analysis in networks.py, but nodes are FACULTY MEMBERS from the
official lists instead of OpenAlex author ids: all ids of one person are merged into one node
(OpenAlex splits people), and every node has a department. Edge weight = number of joint papers
(full counting); papers with more than MAX_AUTHORS authors are left out, as in networks.py.

Analysis:
  degree / weighted degree / betweenness (exact), clustering, components
  communities with Louvain AND Leiden; Louvain can return communities that are not internally
  connected, Leiden guarantees connected ones, so we report how many Louvain ones are broken
  do collaboration communities follow departments? NMI and ARI between community and department
  (0 = unrelated, 1 = identical), per institute; assortativity by institute and by department

Writes to data/out/:
  faculty_network_nodes.csv   one row per faculty member with all node metrics and communities
  faculty_network_edges.csv   faculty_a, faculty_b, inst_a, inst_b, dept_a, dept_b, joint_papers, first_year, last_year
  stats/faculty_network_results.json
"""
import itertools
import json
import math
from collections import Counter, defaultdict

import igraph as ig
import leidenalg
import networkx as nx
import pandas as pd

import config
import movers

OUT = config.OUT_DIR
MAX_AUTHORS = 30
SEED = 42


def nmi(a, b):
    """normalised mutual information (arithmetic mean normalisation) of two labelings"""
    n = len(a)
    ca, cb, cab = Counter(a), Counter(b), Counter(zip(a, b))
    h = lambda c: -sum(v / n * math.log(v / n) for v in c.values())
    mi = sum(v / n * math.log(v * n / (ca[x] * cb[y])) for (x, y), v in cab.items())
    ha, hb = h(ca), h(cb)
    return mi / ((ha + hb) / 2) if ha + hb else 1.0


def ari(a, b):
    """adjusted Rand index of two labelings"""
    c2 = lambda x: x * (x - 1) / 2
    n = len(a)
    s_ab = sum(c2(v) for v in Counter(zip(a, b)).values())
    s_a, s_b = sum(c2(v) for v in Counter(a).values()), sum(c2(v) for v in Counter(b).values())
    exp = s_a * s_b / c2(n)
    mx = (s_a + s_b) / 2
    return (s_ab - exp) / (mx - exp) if mx != exp else 1.0


def main():
    perf = pd.read_csv(OUT / "stats" / "faculty_performance.csv")
    alias = movers.aliases()      # a person listed at two of our institutes becomes ONE node (their current record)
    dept_of = {(i, f): d.split("; ")[0] for i, f, d in zip(perf.institution, perf.faculty_name, perf.department) if (i, f) not in alias}
    status_of = dict(zip(zip(perf.institution, perf.faculty_name), perf.faculty_status))

    papers = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "year", "n_authors"])
    year = dict(zip(papers.openalex_work_id, papers.year))
    small = set(papers[papers.n_authors <= MAX_AUTHORS].openalex_work_id)

    # faculty on each paper from the corrected main file (includes paper-level corrections
    # from faculty_overrides.csv, e.g. papers of a same-name person removed from a record)
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str,
                    usecols=["openalex_work_id", "institution", "is_faculty", "faculty_name"])
    m = m[m.is_faculty == "TRUE"]
    on_paper = defaultdict(set)
    for w, i, f in zip(m.openalex_work_id, m.institution, m.faculty_name):
        if w in small:
            on_paper[w].add(alias.get((i, f), (i, f)))
    wt, yrs = Counter(), defaultdict(list)
    for w, fs in on_paper.items():
        for a, b in itertools.combinations(sorted(fs), 2):
            wt[(a, b)] += 1
            yrs[(a, b)].append(year[w])

    G = nx.Graph()
    G.add_nodes_from(dept_of)                  # every matched faculty member, also those with no faculty co-author
    for (a, b), w in wt.items():
        G.add_edge(a, b, weight=w)
    for n in G.nodes:
        G.nodes[n]["inst"], G.nodes[n]["dept"] = n[0], dept_of.get(n, "")
    print(f"faculty nodes {G.number_of_nodes()}, edges {G.number_of_edges()}, "
          f"isolated {nx.number_of_isolates(G)}")

    # ---------------------------------------------------------------- node metrics
    H = G.subgraph([n for n in G if G.degree(n) > 0]).copy()     # communities need edges
    deg_c = nx.degree_centrality(G)
    bet = nx.betweenness_centrality(G, weight=None)
    clust = nx.clustering(G)

    louv = nx.community.louvain_communities(H, weight="weight", seed=SEED)
    louv_of = {n: k for k, c in enumerate(sorted(louv, key=len, reverse=True)) for n in c}
    broken = sum(1 for c in louv if not nx.is_connected(H.subgraph(c)))

    idx = {n: k for k, n in enumerate(H.nodes)}
    g_ig = ig.Graph(n=len(idx), edges=[(idx[a], idx[b]) for a, b in H.edges])
    g_ig.es["weight"] = [H[a][b]["weight"] for a, b in H.edges]
    part = leidenalg.find_partition(g_ig, leidenalg.ModularityVertexPartition, weights="weight", seed=SEED)
    nodes_h = list(H.nodes)
    leid = [set(nodes_h[v] for v in c) for c in part]
    leid_of = {n: k for k, c in enumerate(sorted(leid, key=len, reverse=True)) for n in c}

    nodes = pd.DataFrame([{
        "faculty_name": n[1], "institution": n[0], "department": G.nodes[n]["dept"],
        "faculty_status": status_of.get(n, ""),
        "collaborators": G.degree(n), "joint_papers": int(G.degree(n, weight="weight")),
        "degree_centrality": round(deg_c[n], 5), "betweenness": round(bet[n], 5),
        "clustering": round(clust[n], 3),
        "community_louvain": louv_of.get(n, -1), "community_leiden": leid_of.get(n, -1),
        "collaborators_other_dept": sum(1 for m in G[n] if G.nodes[m]["dept"] != G.nodes[n]["dept"]),
        "collaborators_other_inst": sum(1 for m in G[n] if m[0] != n[0]),
    } for n in G.nodes]).sort_values("betweenness", ascending=False)
    nodes.to_csv(OUT / "faculty_network_nodes.csv", index=False)

    edges = pd.DataFrame([{"faculty_a": a[1], "faculty_b": b[1], "inst_a": a[0], "inst_b": b[0],
                           "dept_a": dept_of.get(a, ""), "dept_b": dept_of.get(b, ""), "joint_papers": w,
                           "first_year": int(min(yrs[(a, b)])), "last_year": int(max(yrs[(a, b)]))}
                          for (a, b), w in wt.items()]).sort_values("joint_papers", ascending=False)
    edges.to_csv(OUT / "faculty_network_edges.csv", index=False)

    # ---------------------------------------------------------------- network summary
    def summary(Gx, comms_l, comms_v):
        lcc = max(nx.connected_components(Gx), key=len) if Gx.number_of_edges() else set()
        e = list(Gx.edges)
        return {
            "nodes": Gx.number_of_nodes(), "edges": Gx.number_of_edges(),
            "isolated_faculty": nx.number_of_isolates(Gx),
            "density": round(nx.density(Gx), 4),
            "avg_collaborators": round(2 * len(e) / max(1, Gx.number_of_nodes()), 2),
            "avg_clustering": round(nx.average_clustering(Gx), 3),
            "largest_component_%": round(len(lcc) / Gx.number_of_nodes() * 100, 1),
            "cross_department_edges_%": round(sum(Gx.nodes[a]["dept"] != Gx.nodes[b]["dept"] for a, b in e)
                                              / max(1, len(e)) * 100, 1),
            "cross_institute_edges": sum(a[0] != b[0] for a, b in e),
            "louvain": {"communities": len(comms_l),
                        "modularity": round(nx.community.modularity(Gx.subgraph(set().union(*comms_l)), comms_l, weight="weight"), 3)},
            "leiden": {"communities": len(comms_v),
                       "modularity": round(nx.community.modularity(Gx.subgraph(set().union(*comms_v)), comms_v, weight="weight"), 3)},
        }

    res = {"whole_network": summary(G, louv, leid)}
    res["whole_network"]["louvain"]["communities_not_internally_connected"] = broken
    res["whole_network"]["assortativity_by_institute"] = round(nx.attribute_assortativity_coefficient(H, "inst"), 3)
    res["whole_network"]["assortativity_by_department"] = round(nx.attribute_assortativity_coefficient(H, "dept"), 3)

    for inst in config.INSTITUTES:
        sub = H.subgraph([n for n in H if n[0] == inst])
        lab_d = [sub.nodes[n]["dept"] for n in sub]
        lab_c = [leid_of[n] for n in sub]
        r = summary(G.subgraph([n for n in G if n[0] == inst]),
                    [c & set(sub) for c in louv if c & set(sub)], [c & set(sub) for c in leid if c & set(sub)])
        r["community_vs_department"] = {"NMI": round(nmi(lab_c, lab_d), 3), "ARI": round(ari(lab_c, lab_d), 3),
                                        "departments": len(set(lab_d))}
        r["assortativity_by_department"] = round(nx.attribute_assortativity_coefficient(sub, "dept"), 3)
        n_i = nodes[nodes.institution == inst]
        r["top5_collaborators"] = n_i.sort_values("collaborators", ascending=False).head(5)[
            ["faculty_name", "department", "collaborators", "joint_papers"]].to_dict("records")
        r["top5_brokers_betweenness"] = n_i.head(5)[
            ["faculty_name", "department", "betweenness", "collaborators", "collaborators_other_dept"]].to_dict("records")
        res[inst] = r

    # largest communities: who is in them and which departments they span
    res["largest_leiden_communities"] = []
    for c in sorted(leid, key=len, reverse=True)[:8]:
        res["largest_leiden_communities"].append({
            "size": len(c), "institutes": dict(Counter(n[0] for n in c).most_common()),
            "departments": dict(Counter(dept_of.get(n, "") for n in c).most_common(4)),
            "top_members": [n[1] for n in sorted(c, key=lambda x: G.degree(x, weight="weight"), reverse=True)[:3]]})
    (OUT / "stats" / "faculty_network_results.json").write_text(json.dumps(res, indent=1, default=str))

    w = res["whole_network"]
    print(json.dumps({k: w[k] for k in w}, indent=1))
    for inst in config.INSTITUTES:
        r = res[inst]
        print(f"\n== {inst}: {r['nodes']} faculty, {r['edges']} links, cross-dept {r['cross_department_edges_%']}%, "
              f"community vs department {r['community_vs_department']}")
        print("   brokers:", [(x["faculty_name"], x["department"][:22]) for x in r["top5_brokers_betweenness"]])
    print("\nlargest communities:")
    for c in res["largest_leiden_communities"]:
        print("  ", c["size"], c["institutes"], c["departments"], c["top_members"])


if __name__ == "__main__":
    main()
