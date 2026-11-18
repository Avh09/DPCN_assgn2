"""Two extra network studies on the verified faculty (new files only; nothing existing is modified).

1. Bibliographic coupling network: faculty are linked by the references their papers share (all references, 2016-2025 papers).
   Also a within-corpus co-citation network (faculty whose papers are cited together by papers of the three institutes; sparse by construction).
2. Time-decayed collaboration network: every joint paper counts exp(-ln2 * age / half_life) (half-life 3 years, reference year 2025) so recent
   collaborations weigh more; degree (strength), betweenness and harmonic closeness are recomputed and compared with the static network.
Run: python coupling_decay_study.py
"""
import json
import warnings
from collections import defaultdict
from itertools import combinations

import networkx as nx
import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.metrics import normalized_mutual_info_score

import config
import link_prediction_v2 as v2

warnings.filterwarnings("ignore")
STATS = config.OUT_DIR / "stats"
REF_YEAR, HALF = 2025, 3.0


def main():
    C = v2.Corpus2()
    n = C.n
    name = lambda i: f"{C.name[i]} ({C.inst[i]})"
    keep = (C.year_arr <= REF_YEAR).astype(float)
    Pf = sp.diags(keep) @ C.Pf
    # ---------------------------------------------------------------- collaboration graph (static and decayed)
    joint = defaultdict(list)
    for pid, fs in C.paper_fac.items():
        y = C.paper_year[pid]
        if len(fs) > 1 and y <= REF_YEAR:
            for a, b in combinations(sorted(fs), 2):
                joint[(a, b)].append(y)
    Gs, Gd = nx.Graph(), nx.Graph()
    Gs.add_nodes_from(range(n)); Gd.add_nodes_from(range(n))
    for (a, b), ys in joint.items():
        Gs.add_edge(a, b, weight=len(ys))
        w = sum(0.5 ** ((REF_YEAR - y) / HALF) for y in ys)
        Gd.add_edge(a, b, weight=w, dist=1 / w)
    # ---------------------------------------------------------------- 1. bibliographic coupling
    # coupling is computed from SINGLE-faculty papers only: a joint paper has one reference list, so co-authors would "share" references
    # automatically and the result would be circular (coupling would just rediscover who already collaborates)
    nfac = np.asarray(C.Pf.sum(1)).ravel()
    Ps = sp.diags(keep * (nfac == 1)) @ C.Pf
    R = (Ps.T @ C.Pr).tocsr()
    R.data[:] = 1                                   # set of distinct references cited by each person
    shared = (R @ R.T).toarray()
    np.fill_diagonal(shared, 0)
    cos = C._tfidf_cos(sp.csr_matrix(Ps.T @ C.Pr))
    np.fill_diagonal(cos, 0)
    Cc = (C.Cit.T @ C.Cit).tocsr()                  # papers co-cited by the same corpus paper
    Cc.setdiag(0); Cc.eliminate_zeros()
    cocite = (Pf.T @ Cc @ Pf).toarray()
    np.fill_diagonal(cocite, 0)
    A = np.zeros((n, n))
    for a, b in Gs.edges():
        A[a, b] = A[b, a] = 1
    iu = np.triu_indices(n, 1)
    s, c, co, a_ = shared[iu], cos[iu], cocite[iu], A[iu]
    out = {"coupling (single-faculty papers only)": {"pairs_with_any_shared_reference": int((s > 0).sum()), "pairs_with_>=10_shared_references": int((s >= 10).sum()),
                        "co_citation_pairs_nonzero": int((co > 0).sum()), "collaborating_pairs": int(a_.sum())}}
    # how strongly does coupling go with real collaboration?
    pos = c > 0
    q = pd.qcut(pd.Series(c[pos]).rank(method="first"), 5, labels=False).values
    out["collaboration_rate_by_coupling_quintile (pairs with any coupling; 4 = most coupled)"] = {int(k): round(float(a_[pos][q == k].mean()), 4) for k in range(5)}
    out["collaboration_rate_pairs_with_no_coupling"] = round(float(a_[~pos].mean()), 5)
    out["pairs_with_any_coupling"] = int(pos.sum())
    out["coupling_vs_collaboration"] = {"share_of_collab_pairs_with_shared_refs": round(float((s[a_ == 1] > 0).mean()), 3),
                                        "share_of_noncollab_pairs_with_shared_refs": round(float((s[a_ == 0] > 0).mean()), 3),
                                        "median_shared_refs_collab_pairs": float(np.median(s[a_ == 1])), "median_shared_refs_other_pairs": float(np.median(s[a_ == 0]))}
    # coupled but never collaborated = opportunity list (cross-person, ranked by tf-idf cosine)
    rows = [(int(i), int(j), int(shared[i, j]), round(float(cos[i, j]), 4)) for i, j in zip(*np.where(np.triu((cos > 0.12) & (A == 0), 1)))]
    rows.sort(key=lambda r: -r[3])
    pd.DataFrame([{"faculty_a": C.name[i], "institute_a": C.inst[i], "faculty_b": C.name[j], "institute_b": C.inst[j], "shared_references": sh, "coupling_cosine": cs,
                   "same_institute": C.inst[i] == C.inst[j]} for i, j, sh, cs in rows[:1000]]).to_csv(STATS / "coupling_opportunities_top.csv", index=False)
    # coupling network: keep each person's strongest 8 links, then communities and centrality
    Gc = nx.Graph()
    Gc.add_nodes_from(range(n))
    for i in range(n):
        for j in np.argsort(-cos[i])[:8]:
            if cos[i, j] > 0.02:
                Gc.add_edge(i, int(j), weight=float(cos[i, j]))
    comm_c = nx.community.louvain_communities(Gc, weight="weight", seed=15)
    comm_s = nx.community.louvain_communities(Gs, seed=15)
    lab = lambda comms: np.array([next((k for k, cm in enumerate(comms) if i in cm), -1) for i in range(n)])
    lc, ls = lab(comm_c), lab(comm_s)
    act = np.array([Gc.degree(i) > 0 and Gs.degree(i) > 0 for i in range(n)])
    out["coupling_network"] = {"nodes_with_links": int(sum(Gc.degree(i) > 0 for i in range(n))), "edges": Gc.number_of_edges(), "communities": len(comm_c),
                               "modularity": round(nx.community.modularity(Gc, comm_c, weight="weight"), 3),
                               "collaboration_network_communities": len(comm_s), "agreement_with_collaboration_communities_NMI": round(float(normalized_mutual_info_score(lc[act], ls[act])), 3),
                               "share_of_coupling_edges_that_are_real_collaborations": round(float(np.mean([A[i, j] for i, j in Gc.edges()])), 4),
                               "share_of_coupling_edges_within_one_institute": round(float(np.mean([C.inst[i] == C.inst[j] for i, j in Gc.edges()])), 3)}
    bet_c = nx.betweenness_centrality(Gc, weight=None)
    cm = pd.DataFrame({"faculty": [C.name[i] for i in range(n)], "institute": C.inst, "coupling_strength": [sum(d["weight"] for _, _, d in Gc.edges(i, data=True)) for i in range(n)],
                       "coupling_degree": [Gc.degree(i) for i in range(n)], "coupling_betweenness": [bet_c[i] for i in range(n)], "coupling_community": lc})
    cm.to_csv(STATS / "coupling_faculty_metrics.csv", index=False)
    # ---------------------------------------------------------------- 2. time-decayed collaboration metrics
    gs_b = nx.betweenness_centrality(Gs, weight=None)
    gd_b = nx.betweenness_centrality(Gd, weight="dist")
    gd_h = nx.harmonic_centrality(Gd, distance="dist")
    gs_h = nx.harmonic_centrality(Gs)
    dm = pd.DataFrame({"faculty": [C.name[i] for i in range(n)], "institute": C.inst, "static_strength": [Gs.degree(i, weight="weight") for i in range(n)],
                       "decayed_strength": [Gd.degree(i, weight="weight") for i in range(n)], "static_betweenness": [gs_b[i] for i in range(n)],
                       "decayed_betweenness": [gd_b[i] for i in range(n)], "static_harmonic": [gs_h[i] for i in range(n)], "decayed_harmonic": [gd_h[i] for i in range(n)]})
    dm["recent_share_of_strength"] = dm.decayed_strength / dm.static_strength.replace(0, np.nan)
    for m in ("strength", "betweenness", "harmonic"):
        dm[f"{m}_rank_change"] = dm[f"static_{m}"].rank(ascending=False) - dm[f"decayed_{m}"].rank(ascending=False)    # + = more important now than overall
    dm.to_csv(STATS / "decay_faculty_metrics.csv", index=False)
    act2 = dm.static_strength > 0
    top = lambda col, asc=False, k=8: dm[act2].sort_values(col, ascending=asc).head(k)[["faculty", "institute", col]].round(3).to_dict("records")
    out["decay"] = {"half_life_years": HALF, "reference_year": REF_YEAR,
                    "spearman_static_vs_decayed": {m: round(float(dm[act2][f"static_{m}"].corr(dm[act2][f"decayed_{m}"], method="spearman")), 3) for m in ("strength", "betweenness", "harmonic")},
                    "rising_brokers (rank up most, betweenness)": top("betweenness_rank_change"), "fading_brokers (rank down most, betweenness)": top("betweenness_rank_change", True),
                    "top_decayed_betweenness": top("decayed_betweenness"), "top_static_betweenness": top("static_betweenness")}
    (STATS / "coupling_decay_summary.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
