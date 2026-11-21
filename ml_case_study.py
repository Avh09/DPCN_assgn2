"""Worked example for the report: the deployed new-collaboration model, trained only on snapshots up to 2023 and tested on what really happened in 2025.

Model: v5 (LightGBM 5-seed bag + logistic regression, rank-averaged), one-year horizon, features from papers up to 2024.
Train: snapshots T = 2016..2023 (labels = new co-authorship in T+1, so up to 2024). Test: features at T = 2024, label = new co-authorship in 2025.
Reports how many faculty who really started a new faculty collaboration in 2025 had that partner among their top 5 / top 10 suggestions,
and lists correctly predicted pairs with the 2025 joint paper. Writes stats/ml_case_study.json.
Run: python ml_case_study.py
"""
import json
import os

os.environ["HORIZON"] = "1"
import numpy as np
import pandas as pd

import config
import link_prediction_v2 as v2
import link_prediction_v4 as v4
import link_prediction_v5 as v5

ST = config.OUT_DIR / "stats"
TEST_T = 2024


def main():
    C = v2.Corpus2()
    B = v4.Big(C)
    prm = json.load(open(ST / "link_prediction_v5_h1_results.json"))["params"]
    f2 = list(dict.fromkeys(v2.V1_NEW + v2.NEW_V2))
    fx = f2 + ["big_" + c for c in v4.FEATS if c != "n_fac"] + v5.REC
    tr = pd.concat([v5.frame(C, B, T) for T in range(v5.FIRST, TEST_T)])
    te = v5.frame(C, B, TEST_T).copy()
    bag = np.mean([v2.make_lgb({**prm["A2"]}).set_params(random_state=s).fit(tr[fx], tr.y).predict_proba(te[fx])[:, 1] for s in range(5)], 0)
    lr = v2.make_lr(prm["LR2_C"]).fit(tr[fx], tr.y).predict_proba(te[fx])[:, 1]
    te["score"] = (v2.rank01(bag) + v2.rank01(lr)) / 2
    print(f"train snapshots {v5.FIRST}-{TEST_T - 1}: {len(tr)} pairs, {int(tr.y.sum())} new links; test 2025: {len(te)} pairs, {int(te.y.sum())} new links", flush=True)
    long = pd.concat([te[["u", "v", "y", "score"]].rename(columns={"u": "f", "v": "o"}), te[["v", "u", "y", "score"]].rename(columns={"v": "f", "u": "o"})])
    long["rank"] = long.groupby("f").score.rank(ascending=False, method="first")
    has = long.groupby("f").y.sum()
    has = has[has > 0].index
    L = long[long.f.isin(has)]
    hit = {k: int(L[(L["rank"] <= k) & (L.y == 1)].f.nunique()) for k in (1, 5, 10)}
    n = int(len(has))
    cands = int(long.groupby("f").size().median())
    # correctly predicted pairs: the true 2025 partner was in the person's top 5; keep the pair once, best rank first
    ok = L[(L["rank"] <= 5) & (L.y == 1)].sort_values("rank")
    seen, ex = set(), []
    for r in ok.itertuples():
        pair = tuple(sorted((int(r.f), int(r.o))))
        if pair in seen:
            continue
        seen.add(pair)
        u, v = pair
        papers = [p for p, fs in C.paper_fac.items() if C.paper_year[p] == TEST_T + 1 and u in fs and v in fs]
        ex.append({"faculty": f"{C.name[int(r.f)]} ({C.inst[int(r.f)]}, {C.dept[int(r.f)]})", "suggested": f"{C.name[int(r.o)]} ({C.inst[int(r.o)]}, {C.dept[int(r.o)]})",
                   "rank_in_list": int(r.rank), "joint_paper_2025": C.paper_title[papers[0]] if papers else None, "same_department": C.dept[u] == C.dept[v] and C.inst[u] == C.inst[v]})
    res = {"design": __doc__.split("Run:")[0].strip(), "faculty_with_new_link_2025": n, "median_candidates_per_faculty": cands,
           "hits": {f"top{k}": v for k, v in hit.items()}, "hit_rate": {f"top{k}": round(v / n, 3) for k, v in hit.items()},
           "random_top5_expected": round(5 / cands, 4), "correct_pairs_top5": len(seen), "true_new_pairs_2025": int(te.y.sum()), "examples": ex[:12]}
    (ST / "ml_case_study.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in res if k not in ("design", "examples")}, indent=1))
    for e in ex[:8]:
        print(e)


if __name__ == "__main__":
    main()
