"""Can research-topic similarity and network structure predict future faculty collaborations? (temporal link prediction)

Design, so that nothing from the future leaks into the features:
  features at year T use only papers up to T (collab_model.py);
  the label of a pair is whether the two faculty co-author at least one paper in the next 3 years;
  candidate faculty are those with a paper in the 3 years up to T (activity is known at T, not afterwards);
  TRAIN  T = 2019, outcome 2020-2022          TEST  T = 2022, outcome 2023-2025 (2026 is a partial year and is not used)
Two different tasks, never mixed:
  new       pairs with NO joint paper up to T: will they start collaborating?   (rare positives)
  repeat    pairs with at least one joint paper up to T: will they collaborate again?
Models: single-feature baselines (common neighbours, Adamic-Adar, Jaccard, preferential attachment, topic similarity),
logistic regression (standardised, class-balanced), random forest (balanced). Metrics suited to rare positives: average
precision (vs the base rate), precision@K and recall@K, ROC-AUC as a supplement. Probabilities are reported only if the
calibrated model passes a calibration check on the TEST window (slope 0.7-1.3 of observed on predicted); otherwise the
output is a ranking score.
Forward-looking output: models refit on both windows and applied to features at T = 2025, ranking pairs that have not
collaborated yet. This ranking has been validated only through the temporal test above, not for 2026 onwards.

Run: python link_prediction.py        Writes stats/link_prediction_results.json, stats/collab_candidates.csv, models/*.pkl
"""
import json
import pickle

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import collab_model as cm
import config

STATS = config.OUT_DIR / "stats"
MODELS = config.OUT_DIR / "models"
SPLITS = {"train": (2019, 2020, 2022), "test": (2022, 2023, 2025)}      # T, outcome start, outcome end
BASELINES = {"common neighbours": "common_neighbours", "Adamic-Adar": "adamic_adar", "Jaccard (neighbours)": "jaccard_neighbours",
             "preferential attachment": "pref_attachment", "topic cosine": "topic_cosine", "topic weighted Jaccard": "topic_weighted_jaccard",
             "shortest path (closer = higher)": "hop_distance"}


def dataset(C, T, y0, y1, task):
    H = C.history(T)
    mats = C.feature_matrices(H)
    act = C.active(H)
    outcome = set(C.pair_papers(y0, y1))
    pairs = []
    for a in range(len(act)):
        for b in range(a + 1, len(act)):
            i, j = act[a], act[b]
            linked = H["A"][i, j] > 0
            if (task == "new") != linked:
                pairs.append((i, j))
    df = C.pair_frame(H, mats, pairs)
    df["y"] = [int((min(u, v), max(u, v)) in outcome) for u, v in zip(df.u, df.v)]
    return df, H, mats


def metrics(y, score, ks=(50, 100, 500)):
    y, score = np.asarray(y), np.asarray(score, dtype=float)
    order = np.argsort(-score, kind="stable")
    out = {"positives": int(y.sum()), "pairs": int(len(y)), "base_rate": round(float(y.mean()), 5),
           "average_precision": round(float(average_precision_score(y, score)), 4), "roc_auc": round(float(roc_auc_score(y, score)), 4)}
    out["ap_lift_over_base_rate"] = round(out["average_precision"] / max(out["base_rate"], 1e-12), 1)
    for k in ks:
        k2 = min(k, len(y))
        hit = int(y[order[:k2]].sum())
        out[f"precision@{k}"], out[f"recall@{k}"] = round(hit / k2, 4), round(hit / max(y.sum(), 1), 4)
    return out


def calibration(y, p, bins=5):
    y, p = np.asarray(y), np.asarray(p)
    q = np.quantile(p, np.linspace(0, 1, bins + 1))
    rows = []
    for a, b in zip(q[:-1], q[1:]):
        sel = (p >= a) & (p <= b) if b == q[-1] else (p >= a) & (p < b)
        if sel.sum():
            rows.append({"mean_predicted": round(float(p[sel].mean()), 5), "observed_rate": round(float(y[sel].mean()), 5), "n": int(sel.sum())})
    # slope of observed on predicted (weighted least squares through the bins)
    x = np.array([r["mean_predicted"] for r in rows])
    o = np.array([r["observed_rate"] for r in rows])
    slope = float(np.polyfit(x, o, 1)[0]) if len(rows) > 2 and x.std() > 0 else float("nan")
    return {"bins": rows, "slope": round(slope, 3), "brier": round(float(brier_score_loss(y, p)), 5)}


def models():
    return {"logistic regression": make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000)),
            "random forest": RandomForestClassifier(n_estimators=150, min_samples_leaf=10, max_depth=18, class_weight="balanced_subsample", n_jobs=-1, random_state=15)}


def run_task(C, task, feats):
    tr, _, _ = dataset(C, *SPLITS["train"], task)
    te, Hte, mte = dataset(C, *SPLITS["test"], task)
    res = {"train": {"T": 2019, "outcome": "2020-2022", "pairs": len(tr), "positives": int(tr.y.sum())},
           "test": {"T": 2022, "outcome": "2023-2025", "pairs": len(te), "positives": int(te.y.sum())}, "metrics": {}, "calibration": {}}
    for name, col in BASELINES.items():
        sc = -te[col] if col == "hop_distance" else te[col]
        if te.y.sum() and sc.std() > 0:
            res["metrics"][name] = metrics(te.y, sc)
    fitted, scores = {}, {}
    for name, mdl in models().items():
        mdl.fit(tr[feats], tr.y)
        scores[name] = mdl.predict_proba(te[feats])[:, 1]
        res["metrics"][name] = metrics(te.y, scores[name])
        fitted[name] = mdl
        # calibrated version (sigmoid, 3-fold on the training window)
        cal = CalibratedClassifierCV(models()[name], method="sigmoid", cv=3).fit(tr[feats], tr.y)
        pc = cal.predict_proba(te[feats])[:, 1]
        res["calibration"][name] = calibration(te.y, pc)
        res["calibration"][name]["probabilities_reported"] = bool(0.7 <= res["calibration"][name]["slope"] <= 1.3)
    rf = fitted["random forest"]
    res["rf_importance"] = {f: round(float(v), 4) for f, v in sorted(zip(feats, rf.feature_importances_), key=lambda x: -x[1])}
    lr = fitted["logistic regression"]
    res["lr_coefficients_standardised"] = {f: round(float(v), 3) for f, v in sorted(zip(feats, lr[-1].coef_[0]), key=lambda x: -abs(x[1]))}
    # ablation: network-only vs research-only vs combined, random forest
    groups = {"network features only": [f for f in feats if f in ("common_neighbours", "jaccard_neighbours", "adamic_adar", "resource_allocation", "pref_attachment",
                                                                  "hop_distance", "same_community", "joint_papers_hist", "years_since_last_joint")],
              "research features only": ["topic_cosine", "topic_weighted_jaccard", "shared_subfields", "field_cosine"],
              "structure + activity only": ["same_department", "same_institute", "institute_pair_joint_papers_hist", "log_papers_min", "log_papers_max",
                                            "recent_papers_min", "recent_papers_max"]}
    res["ablation_random_forest"] = {}
    for g, cols in groups.items():
        cols = [c for c in cols if c in feats]
        m = models()["random forest"].fit(tr[cols], tr.y)
        res["ablation_random_forest"][g] = metrics(te.y, m.predict_proba(te[cols])[:, 1])
    res["ablation_random_forest"]["all features"] = res["metrics"]["random forest"]
    return res, fitted, tr, te


def main():
    C = cm.Corpus()
    print(f"{C.n} faculty, {len(C.subfields)} subfields", flush=True)
    results = {"design": __doc__.split("Run:")[0].strip(), "tasks": {}}
    MODELS.mkdir(exist_ok=True)
    allfit = {}
    for task in ("new", "repeat"):
        feats = cm.NEW_LINK_FEATURES if task == "new" else cm.FEATURES
        res, fitted, tr, te = run_task(C, task, feats)
        results["tasks"][task] = res
        m = res["metrics"]
        print(f"[{task}] test pairs {res['test']['pairs']}, positives {res['test']['positives']} (base rate {m['random forest']['base_rate']})")
        for name in m:
            print(f"   {name:34s} AP {m[name]['average_precision']:.3f}  AUC {m[name]['roc_auc']:.3f}  P@100 {m[name]['precision@100']:.3f}  R@500 {m[name]['recall@500']:.3f}")
        # final models: refit on train + test windows, then score pairs at T = 2025
        full = pd.concat([tr, te])
        final = {n: mdl.fit(full[feats], full.y) for n, mdl in models().items()}
        allfit[task] = {"models": final, "features": feats}
    pickle.dump(allfit, open(MODELS / "collab_models.pkl", "wb"))

    # forward-looking ranking of pairs that have not collaborated yet (history to 2025)
    H = C.history(2025)
    mats = C.feature_matrices(H)
    act = C.active(H)
    pairs = [(act[a], act[b]) for a in range(len(act)) for b in range(a + 1, len(act)) if H["A"][act[a], act[b]] == 0]
    df = C.pair_frame(H, mats, pairs)
    feats = cm.NEW_LINK_FEATURES
    rf, lr = allfit["new"]["models"]["random forest"], allfit["new"]["models"]["logistic regression"]
    df["score_rf"] = rf.predict_proba(df[feats])[:, 1]
    df["score_lr"] = lr.predict_proba(df[feats])[:, 1]
    df["rank_score"] = (df.score_rf.rank(pct=True) + df.score_lr.rank(pct=True)) / 2
    top = df.sort_values("rank_score", ascending=False).head(3000).copy()
    ev = [C.explain(H, mats, u, v) for u, v in zip(top.u, top.v)]
    top["faculty_a"], top["institute_a"], top["department_a"] = [C.name[u] for u in top.u], [C.inst[u] for u in top.u], [C.dept[u] for u in top.u]
    top["faculty_b"], top["institute_b"], top["department_b"] = [C.name[v] for v in top.v], [C.inst[v] for v in top.v], [C.dept[v] for v in top.v]
    top["common_collaborators"] = ["; ".join(e["common_collaborators"]) for e in ev]
    top["shared_subfields"] = ["; ".join(e["shared_subfields"]) for e in ev]
    top["hops"] = [e["hops"] for e in ev]
    top["rank"] = range(1, len(top) + 1)
    top[["rank", "faculty_a", "institute_a", "department_a", "faculty_b", "institute_b", "department_b", "rank_score", "score_rf", "score_lr", "hops",
         "common_neighbours", "topic_cosine", "topic_weighted_jaccard", "common_collaborators", "shared_subfields", "same_department", "same_institute"]].to_csv(
        STATS / "collab_candidates.csv", index=False)
    results["forward_ranking"] = {"history_to": 2025, "candidate_pairs": len(df), "note": "ranking score (mean of the two models' percentile ranks), not a probability"}
    (STATS / "link_prediction_results.json").write_text(json.dumps(results, default=float, indent=1))
    print("candidates written:", len(top), "of", len(df), "pairs")


if __name__ == "__main__":
    main()
