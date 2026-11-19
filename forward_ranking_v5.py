"""Forward-looking ranking with the v5 model: pairs of current faculty that have NOT co-authored, ranked by how likely they are to start in the next 3 years.

Model: rank average of the 5-seed LightGBM (A2) and the logistic regression (LR2) from link_prediction_v5.py, 3-year horizon, refit on every snapshot whose
3-year outcome is fully known (T = 2016 .. 2022), then applied to features at T = 2025 (papers up to 2025). The score is a ranking, not a probability.
Also writes stats/collab_scores_v5.csv.gz (all candidate pairs). Writes stats/collab_candidates_v5.csv (top 3000 pairs, same columns as collab_candidates.csv, so the dashboard and the assistant can read either).
Run: python forward_ranking_v5.py
"""
import json
import os

os.environ["HORIZON"] = "3"
import numpy as np
import pandas as pd

import config
import link_prediction_v2 as v2
import link_prediction_v4 as v4
import link_prediction_v5 as v5

STATS = config.OUT_DIR / "stats"
NOW = 2025


def main():
    C = v2.Corpus2()
    B = v4.Big(C)
    prm = json.load(open(STATS / "link_prediction_v5_h3_results.json"))["params"]
    PX, lr_c = prm["A2"], prm["LR2_C"]
    f2 = list(dict.fromkeys(v2.V1_NEW + v2.NEW_V2))
    fx = f2 + ["big_" + c for c in v4.FEATS if c != "n_fac"] + v5.REC
    train_T = range(v5.FIRST, NOW - 3 + 1)
    tr = pd.concat([v5.frame(C, B, T) for T in train_T])
    print(f"training on T={train_T[0]}..{train_T[-1]}: {len(tr)} rows, {int(tr.y.sum())} positives", flush=True)
    now = v5.frame(C, B, NOW)                       # features at 2025 for every never-collaborated pair of active faculty (its label column is unused)
    bag = np.mean([v2.make_lgb({**PX}).set_params(random_state=s).fit(tr[fx], tr.y).predict_proba(now[fx])[:, 1] for s in range(5)], 0)
    lr = v2.make_lr(lr_c).fit(tr[fx], tr.y).predict_proba(now[fx])[:, 1]
    now["score_lgb"], now["score_lr"] = bag, lr
    now["rank_score"] = (v2.rank01(bag) + v2.rank01(lr)) / 2
    now[["u", "v", "rank_score", "score_lgb", "score_lr"]].round(6).to_csv(STATS / "collab_scores_v5.csv.gz", index=False)     # every candidate pair, for the assistant
    top = now.sort_values("rank_score", ascending=False).head(3000).copy()
    H0, mats = v2._cache[("mats", NOW)]
    ev = [C.explain(H0, mats, int(u), int(v)) for u, v in zip(top.u, top.v)]
    top["faculty_a"], top["institute_a"], top["department_a"] = [C.name[u] for u in top.u], [C.inst[u] for u in top.u], [C.dept[u] for u in top.u]
    top["faculty_b"], top["institute_b"], top["department_b"] = [C.name[v] for v in top.v], [C.inst[v] for v in top.v], [C.dept[v] for v in top.v]
    top["common_collaborators"] = ["; ".join(e["common_collaborators"]) for e in ev]
    top["shared_subfields"] = ["; ".join(e["shared_subfields"]) for e in ev]
    top["hops"] = [e["hops"] for e in ev]
    top["rank"] = range(1, len(top) + 1)
    top[["rank", "faculty_a", "institute_a", "department_a", "faculty_b", "institute_b", "department_b", "rank_score", "score_lgb", "score_lr", "hops",
         "common_neighbours", "topic_cosine", "topic_weighted_jaccard", "common_collaborators", "shared_subfields", "same_department", "same_institute"]].to_csv(
        STATS / "collab_candidates_v5.csv", index=False)
    print("written", len(top), "of", len(now), "pairs")
    print(top[["faculty_a", "institute_a", "faculty_b", "institute_b", "rank_score", "hops"]].head(8).to_string())


if __name__ == "__main__":
    main()
