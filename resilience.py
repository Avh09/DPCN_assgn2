"""Network resilience of the verified-faculty co-authorship network (structural experiment, not a personnel claim).

Research question: how dependent are the collaboration networks on a few structurally important researchers?

Graph: nodes = verified faculty (isolated faculty stay in as nodes, so every curve is measured against the same N0),
edges = at least one joint paper in the corpus (weight = joint papers). Scopes: all three institutes, and each institute
alone (edges between faculty of that institute only).

Removal strategies (nodes are removed one by one; metrics are recorded at fixed fractions of N0):
  random                  uniform random order, 50 runs (mean and 2.5-97.5 percentile band)
  degree (static)         highest initial degree first
  betweenness (static)    highest initial betweenness first
  betweenness (adaptive)  betweenness recomputed after every removal
Metrics, all relative to the ORIGINAL network so curves are comparable:
  lcc_fraction            size of the largest connected component / N0
  global_efficiency       mean of 1/d(i, j) over all N0 (N0 - 1) ordered pairs (0 for disconnected pairs) / the value at 0 % removal
  components              number of connected components among the surviving nodes (isolates included)
Null model: the same targeted attacks on 20 degree-preserving rewirings of the network (igraph rewire), to separate what the
degree sequence alone explains from what the wiring adds.
Summary numbers: R20 = mean LCC fraction over 0-20 % removal (higher = more robust), collapse point = removed fraction at
which the LCC first falls below half of N0, fragility index = 1 - R20(targeted) / R20(random).
Also: single-removal impact and articulation points for the top brokers, and layouts of the network before and after
removing the top 5 % by betweenness.

Run: python resilience.py      (about two minutes; seeded, so a rerun gives identical numbers)
Writes stats/resilience_results.json, stats/resilience_curves.csv, stats/critical_faculty.csv.
"""
import json

import igraph as ig
import numpy as np
import pandas as pd

import config

STATS = config.OUT_DIR / "stats"
INSTS = list(config.INSTITUTES)
FRACS = np.round(np.arange(0, 0.401, 0.02), 3)
N_RANDOM, N_NULL, SEED = 50, 20, 15


def build(scope):
    nodes = pd.read_csv(STATS / "faculty_node_metrics.csv")
    if scope != "all":
        nodes = nodes[nodes.institution == scope]
    nodes = nodes.reset_index(drop=True)
    idx = {(r.institution, r.faculty_name): k for k, r in enumerate(nodes.itertuples())}
    e = pd.read_csv(config.OUT_DIR / "faculty_network_edges.csv")
    ed, w = [], []
    for r in e.itertuples():
        a, b = idx.get((r.inst_a, r.faculty_a)), idx.get((r.inst_b, r.faculty_b))
        if a is not None and b is not None and a != b:
            ed.append((a, b))
            w.append(int(r.joint_papers))
    g = ig.Graph(n=len(nodes), edges=ed)
    g.es["weight"] = w
    return g, nodes


def efficiency_sum(sub):
    """Sum over ordered pairs of 1/d (disconnected pairs contribute 0)."""
    if sub.vcount() < 2:
        return 0.0
    d = np.array(sub.distances(), dtype=float)
    np.fill_diagonal(d, np.inf)
    return float((1.0 / d).sum())


def record(g, alive, n0, eff0):
    sub = g.induced_subgraph(list(alive))
    comps = sub.connected_components()
    sizes = comps.sizes()
    return (max(sizes) / n0 if sizes else 0.0, efficiency_sum(sub) / (n0 * (n0 - 1)) / eff0 if eff0 else 0.0, len(sizes))


def removal_order(g, strategy, rng=None):
    if strategy == "random":
        return list(rng.permutation(g.vcount()))
    score = np.array(g.degree() if strategy == "degree" else g.betweenness(), dtype=float)
    return list(np.lexsort((np.arange(g.vcount()), -score)))        # highest first, ties by index


def curve(g, order_fn, adaptive=False):
    n0 = g.vcount()
    eff0 = efficiency_sum(g) / (n0 * (n0 - 1))
    out = []
    alive = set(range(n0))
    order = None if adaptive else order_fn(g)
    removed = 0
    for f in FRACS:
        target = int(round(f * n0))
        while removed < target:
            if adaptive:
                sub = g.induced_subgraph(sorted(alive))
                b = sub.betweenness()
                v = sorted(alive)[int(np.lexsort((np.arange(len(b)), -np.array(b)))[0])]
            else:
                v = order[removed]
            alive.discard(v)
            removed += 1
        out.append(record(g, alive, n0, eff0))
    return np.array(out)       # rows: fractions, columns: lcc, efficiency, components


def r20(c):
    sel = FRACS <= 0.2 + 1e-9
    return float(np.trapezoid(c[sel, 0], FRACS[sel]) / 0.2)


def collapse(c):
    below = np.where(c[:, 0] < 0.5)[0]
    return float(FRACS[below[0]]) if len(below) else None


def single_removal(g, nodes, top=30):
    n0 = g.vcount()
    eff0 = efficiency_sum(g) / (n0 * (n0 - 1))
    lcc0 = max(g.connected_components().sizes()) / n0
    aps = set(g.articulation_points())
    bet = np.array(g.betweenness())
    cand = list(dict.fromkeys(list(np.argsort(-bet)[:top]) + list(np.argsort(-np.array(g.degree()))[:top])))
    rows = []
    for v in cand:
        alive = [i for i in range(n0) if i != v]
        sub = g.induced_subgraph(alive)
        sizes = sub.connected_components().sizes()
        sub_eff = efficiency_sum(sub) / (n0 * (n0 - 1)) / eff0
        r = nodes.iloc[v]
        rows.append({"faculty_name": r.faculty_name, "institution": r.institution, "department": r.department, "degree": int(g.degree(v)),
                     "betweenness": round(float(bet[v]), 5), "participation_dept": r.participation_dept, "participation_community": r.participation_community,
                     "community_leiden": r.community_leiden, "articulation_point": bool(v in aps),
                     "lcc_fraction_after": round(max(sizes) / n0, 4), "lcc_change_pp": round((max(sizes) / n0 - lcc0) * 100, 2),
                     "efficiency_after_rel": round(sub_eff, 4), "efficiency_loss_%": round((1 - sub_eff) * 100, 2),
                     "components_after": len(sizes)})
    return pd.DataFrame(rows).sort_values("efficiency_loss_%", ascending=False)


def snapshot(g, nodes, k_frac=0.05):
    """Layout of the network with the top k_frac by betweenness removed (static)."""
    n0 = g.vcount()
    k = max(1, int(round(k_frac * n0)))
    order = removal_order(g, "betweenness")
    removed = set(order[:k])
    ig.set_random_number_generator(__import__("random").Random(SEED))
    lay = g.layout_fruchterman_reingold(niter=300)
    alive = [i for i in range(n0) if i not in removed]
    sub = g.induced_subgraph(alive)
    memb = sub.connected_components().membership
    sizes = pd.Series(memb).value_counts()
    lcc_label = sizes.index[0] if len(sizes) else None
    in_lcc = {alive[i] for i, m in enumerate(memb) if m == lcc_label}
    pos = [[round(float(x), 3), round(float(y), 3)] for x, y in lay.coords]
    return {"removed_count": k, "removed": [{"i": int(v), "faculty_name": nodes.faculty_name[v], "institution": nodes.institution[v]} for v in order[:k]],
            "nodes": [{"x": pos[i][0], "y": pos[i][1], "inst": INSTS.index(nodes.institution[i]), "name": nodes.faculty_name[i],
                       "removed": i in removed, "lcc_after": i in in_lcc, "deg": int(g.degree(i))} for i in range(n0)],
            "edges": [[a, b] for a, b in g.get_edgelist()], "lcc_fraction_before": round(max(g.connected_components().sizes()) / n0, 4),
            "lcc_fraction_after": round(len(in_lcc) / n0, 4), "components_after": int(len(sizes))}


def main():
    rng = np.random.default_rng(SEED)
    results, rows, crit = {"fractions": FRACS.tolist(), "scopes": {}}, [], []
    for scope in ["all"] + INSTS:
        g, nodes = build(scope)
        n0 = g.vcount()
        res = {"nodes": n0, "edges": g.ecount(), "isolated": int(sum(1 for d in g.degree() if d == 0)),
               "lcc_fraction_0": round(max(g.connected_components().sizes()) / n0, 4), "curves": {}}
        # random removal, many runs
        runs = np.array([curve(g, lambda gg, r=rng: removal_order(gg, "random", r)) for _ in range(N_RANDOM)])
        mean, lo, hi = runs.mean(axis=0), np.percentile(runs, 2.5, axis=0), np.percentile(runs, 97.5, axis=0)
        res["curves"]["random"] = {"lcc": mean[:, 0].round(4).tolist(), "lcc_lo": lo[:, 0].round(4).tolist(), "lcc_hi": hi[:, 0].round(4).tolist(),
                                    "eff": mean[:, 1].round(4).tolist(), "eff_lo": lo[:, 1].round(4).tolist(), "eff_hi": hi[:, 1].round(4).tolist(),
                                    "components": mean[:, 2].round(2).tolist()}
        strat = {"degree": curve(g, lambda gg: removal_order(gg, "degree")),
                 "betweenness": curve(g, lambda gg: removal_order(gg, "betweenness")),
                 "betweenness_adaptive": curve(g, None, adaptive=True)}
        for k, c in strat.items():
            res["curves"][k] = {"lcc": c[:, 0].round(4).tolist(), "eff": c[:, 1].round(4).tolist(), "components": c[:, 2].astype(int).tolist()}
        # degree-preserving null model
        nulls = {"degree": [], "betweenness": []}
        for _ in range(N_NULL):
            h = g.copy()
            h.rewire(n=10 * g.ecount())
            nulls["degree"].append(curve(h, lambda gg: removal_order(gg, "degree")))
            nulls["betweenness"].append(curve(h, lambda gg: removal_order(gg, "betweenness")))
        res["null_model"] = {k: {"lcc": np.mean(v, axis=0)[:, 0].round(4).tolist(), "eff": np.mean(v, axis=0)[:, 1].round(4).tolist()} for k, v in nulls.items()}
        summ = {"random": {"R20": r20(mean), "collapse_at": collapse(mean)}}
        for k, c in strat.items():
            summ[k] = {"R20": r20(c), "collapse_at": collapse(c)}
        for k in ("degree", "betweenness"):
            summ[k + "_null"] = {"R20": r20(np.mean(nulls[k], axis=0)), "collapse_at": collapse(np.mean(nulls[k], axis=0))}
        for k in ("degree", "betweenness", "betweenness_adaptive"):
            summ[k]["fragility_index"] = round(1 - summ[k]["R20"] / summ["random"]["R20"], 4)
        res["summary"] = {k: {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items()} for k, v in summ.items()}
        res["snapshot"] = snapshot(g, nodes)
        results["scopes"][scope] = res
        for s_, cur in [("random", mean)] + list(strat.items()):
            for f, r in zip(FRACS, cur):
                rows.append({"scope": scope, "strategy": s_, "fraction_removed": f, "lcc_fraction": round(r[0], 4), "efficiency_rel": round(r[1], 4), "components": round(r[2], 2)})
        c = single_removal(g, nodes)
        c.insert(0, "scope", scope)
        crit.append(c)
        print(f"{scope:15s} N0={n0} LCC0={res['lcc_fraction_0']} | R20 random {res['summary']['random']['R20']:.3f} degree {res['summary']['degree']['R20']:.3f} "
              f"betweenness {res['summary']['betweenness']['R20']:.3f} adaptive {res['summary']['betweenness_adaptive']['R20']:.3f} | collapse at "
              f"{[res['summary'][k]['collapse_at'] for k in ('random', 'degree', 'betweenness', 'betweenness_adaptive')]}", flush=True)
    pd.DataFrame(rows).to_csv(STATS / "resilience_curves.csv", index=False)
    pd.concat(crit).to_csv(STATS / "critical_faculty.csv", index=False)
    results["definitions"] = {"R20": "mean LCC fraction over 0-20% removal", "fragility_index": "1 - R20(targeted) / R20(random)",
                              "note": "structural simulation on the verified-faculty graph; removing a node does not mean a faculty member leaves"}
    (STATS / "resilience_results.json").write_text(json.dumps(results, default=float))


if __name__ == "__main__":
    main()
