"""Collaboration prediction v5: v2 faculty model + big-graph network features + recency-weighted content similarity, bagged, with per-faculty hit rates.

Adds to the v2 feature set (faculty-pair rows, same temporal protocol as v3/v4):
  big-graph  common neighbours / Adamic-Adar / resource allocation / Jaccard / 3-step paths / degrees computed on the graph of ALL co-authors of the
             verified corpus (v4's Big graph), not only faculty
  recency    reference, topic and venue TF-IDF cosine and citation links using only the last 2 years of each person's papers
Models: A = v3 LightGBM reference (v2 features); A2 = LightGBM on the extended features (params chosen on the validation fold), bagged over 5 seeds;
LR2 = logistic regression on the same features; E = rank average of A2 and LR2.
HORIZON env var: 1 (default; label = year T+1) or 3 (label = any collaboration in T+1..T+3).
Reports per fold and pooled over folds (ranks normalised inside each fold): average precision, ROC-AUC, precision@100, and per-faculty hit@k / precision@k.
Run: HORIZON=1 python link_prediction_v5.py
"""
import json
import os
import time
import warnings

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.metrics import average_precision_score, roc_auc_score

import config
import link_prediction_v2 as v2
import link_prediction_v4 as v4

warnings.filterwarnings("ignore")
H = int(os.environ.get("HORIZON", "1"))
v2.HORIZON = H
STATS = config.OUT_DIR / "stats"
FIRST = 2016
FOLDS = [2020, 2021, 2022, 2023, 2024] if H == 1 else [2020, 2021, 2022]
VAL_T = 2023 if H == 1 else 2021
PARAMS_A = dict(n=200, lr=0.03, leaves=7, mcs=30, spw=10)
REC = ["refs_cos_r", "topic_cos_r", "venue_cos_r", "cite_r_min", "cite_r_max"]
T0 = time.time()
log = lambda *a: print(f"[{(time.time() - T0) / 60:6.1f} min]", *a, flush=True)


def recency(C, T, win=2):
    m = ((C.year_arr > T - win) & (C.year_arr <= T)).astype(float)
    Pf = sp.diags(m) @ C.Pf
    PfT = Pf.T.tocsr()
    X = (PfT @ C.Cit @ Pf).toarray()
    X = X + X.T
    return {"refs_cos_r": C._tfidf_cos(PfT @ C.Pr), "topic_cos_r": C._tfidf_cos(PfT @ C.Pt), "venue_cos_r": C._tfidf_cos(PfT @ C.Pv),
            "cite_r_min": np.minimum(X, X.T), "cite_r_max": np.maximum(X, X.T)}


_data = {}


def frame(C, B, T):
    if T not in _data:
        d = v2.dataset(C, T, "new").copy()
        big = B.features(T, d.u.values, d.v.values).drop(columns=["n_fac"])
        big.columns = ["big_" + c for c in big.columns]
        R = recency(C, T)
        rec = pd.DataFrame({k: R[k][d.u.values, d.v.values] for k in R})
        _data[T] = pd.concat([d.reset_index(drop=True), big, rec], axis=1)
    return _data[T]


def per_faculty(df, s, ks=(3, 5, 10)):
    d = pd.DataFrame({"u": df.u.values, "v": df.v.values, "y": df.y.values, "s": s})
    long = pd.concat([d.rename(columns={"u": "f"})[["f", "y", "s"]], d.rename(columns={"v": "f"})[["f", "y", "s"]]])
    has = long.groupby("f").y.sum()
    has = has[has > 0].index
    srt = long[long.f.isin(has)].sort_values("s", ascending=False)
    out = {"faculty_with_a_new_link": int(len(has))}
    for k in ks:
        g = srt.groupby("f").head(k).groupby("f").y
        out[f"hit@{k}"] = round(float((g.sum() > 0).reindex(has, fill_value=False).mean()), 4)
        out[f"precision@{k}"] = round(float(g.mean().reindex(has, fill_value=0).mean()), 4)
    return out


def basic(y, s):
    y = np.asarray(y)
    o = np.argsort(-np.asarray(s), kind="stable")
    r = {"positives": int(y.sum()), "pairs": len(y), "average_precision": round(float(average_precision_score(y, s)), 4), "roc_auc": round(float(roc_auc_score(y, s)), 4)}
    for k in (100, 500):
        r[f"precision@{k}"], r[f"recall@{k}"] = round(float(y[o[:k]].mean()), 3), round(float(y[o[:k]].sum() / y.sum()), 3)
    return r


def main():
    C = v2.Corpus2()
    B = v4.Big(C)
    f2 = list(dict.fromkeys(v2.V1_NEW + v2.NEW_V2))
    bigf = ["big_" + c for c in v4.FEATS if c != "n_fac"]
    fx = f2 + bigf + REC
    for T in range(FIRST, FOLDS[-1] + 1):
        frame(C, B, T)
    log(f"HORIZON={H}: features built ({len(f2)} v2 + {len(bigf)} big-graph + {len(REC)} recency)")
    train = lambda test_T: pd.concat([frame(C, B, T) for T in range(FIRST, test_T - H + 1)])

    tr, va = train(VAL_T), frame(C, B, VAL_T)
    scored = []
    for lv in (7, 15):
        for mcs in (30, 100):
            for spw in (1, 10):
                p = dict(n=300, lr=0.03, leaves=lv, mcs=mcs, spw=spw)
                sc = v2.fit_predict("lgb", p, tr, va, fx)[1]
                scored.append((average_precision_score(va.y, sc), p))
    PX = max(scored, key=lambda x: x[0])[1]
    lr_c = max((average_precision_score(va.y, v2.fit_predict("lr", c, tr, va, fx)[1]), c) for c in (0.01, 0.03, 0.1, 0.3))[1]
    log(f"validation (T={VAL_T}): A2 params {PX} (AP {max(scored, key=lambda x: x[0])[0]:.4f}); LR C={lr_c}")

    res = {"design": __doc__.split("Run:")[0].strip(), "horizon_years": H, "params": {"A": PARAMS_A, "A2": PX, "LR2_C": lr_c}, "folds": {}, "pooled": {}}
    pool = {}
    for test_T in FOLDS:
        trn, te = train(test_T), frame(C, B, test_T)
        sc = {"A: LightGBM, v2 features (reference)": v2.fit_predict("lgb", PARAMS_A, trn, te, f2)[1]}
        bag = np.mean([v2.make_lgb({**PX}).set_params(random_state=s).fit(trn[fx], trn.y).predict_proba(te[fx])[:, 1] for s in range(5)], 0)
        lr = v2.fit_predict("lr", lr_c, trn, te, fx)[1]
        sc["A2: LightGBM, extended features, 5-seed bag"] = bag
        sc["LR2: logistic regression, extended features"] = lr
        sc["E: A2 + LR2 rank average"] = (v2.rank01(bag) + v2.rank01(lr)) / 2
        res["folds"][test_T] = {"label_years": f"{test_T + 1}-{test_T + H}", "train_positives": int(trn.y.sum()),
                                "models": {k: {**basic(te.y, s), **per_faculty(te, s)} for k, s in sc.items()}}
        if test_T == FOLDS[-1]:
            res["headline_ci95_ap"] = {k: v2.boot_ci(te.y, s, average_precision_score) for k, s in sc.items()}
        for k, s in sc.items():
            pool.setdefault(k, []).append((te.y.values, v2.rank01(s)))
        log(f"fold {test_T} ({int(te.y.sum())} positives): " + " | ".join(f"{k.split(':')[0]} AP {v['average_precision']:.4f} hit@5 {v['hit@5']}" for k, v in res["folds"][test_T]["models"].items()))
    for k, lst in pool.items():
        y, s = np.concatenate([x[0] for x in lst]), np.concatenate([x[1] for x in lst])
        w = np.array([res["folds"][t]["models"][k]["faculty_with_a_new_link"] for t in FOLDS], float)
        pf = {q: round(float(np.average([res["folds"][t]["models"][k][q] for t in FOLDS], weights=w)), 4) for q in ("hit@3", "hit@5", "hit@10", "precision@5")}
        res["pooled"][k] = {**basic(y, s), **pf, "mean_fold_precision@100": round(float(np.mean([basic(a, b)["precision@100"] for a, b in lst])), 4)}
        m = res["pooled"][k]
        log(f"POOLED {k[:46]:46s} AP {m['average_precision']:.4f} AUC {m['roc_auc']:.4f} P@100 {m['mean_fold_precision@100']} hit@3 {m['hit@3']} hit@5 {m['hit@5']} hit@10 {m['hit@10']} ({m['positives']} pos)")
    (STATS / f"link_prediction_v5_h{H}_results.json").write_text(json.dumps(res, indent=1, default=float))
    log("written")


if __name__ == "__main__":
    main()
