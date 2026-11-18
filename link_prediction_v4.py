"""Collaboration prediction v4: learn link prediction on the WHOLE co-author graph, then score faculty pairs.

Why: the faculty-only data has ~100-250 new links a year. The full co-author graph of the verified corpus (faculty + all their co-authors,
~17k people) has ~350-600 new links a year among pairs that are two steps apart, so ~4x more training positives.

Protocol (strictly temporal, one-year-ahead, same faculty test pairs as v3):
  snapshot T: graph of papers up to T; label = the pair co-authors a paper in T+1 and had never done so before
  fold test_T: train on snapshots T' <= test_T - 1, test on faculty-faculty never-collaborated pairs at test_T (label = year test_T + 1)
  folds 2020..2024; headline = 2024 (label 2025); predictions of the 5 folds are also pooled (rank-normalised inside each fold)
Models (all LightGBM):
  A  faculty-only data, v2 features                  (= the v3 LightGBM, the reference)
  B  structural features from the big graph, trained on faculty pairs + all other author pairs (the new idea)
  C  same structural features, trained on faculty pairs only (ablation: does the extra data matter, or just the features?)
  A+B, A+C rank averages
Run: python link_prediction_v4.py
"""
import json
import time
import warnings

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.metrics import average_precision_score, roc_auc_score

import config
import link_prediction_v2 as v2

warnings.filterwarnings("ignore")
v2.HORIZON = 1
STATS = config.OUT_DIR / "stats"
FIRST, FOLDS, VAL_T = 2016, [2020, 2021, 2022, 2023, 2024], 2023
PARAMS_A = dict(n=200, lr=0.03, leaves=7, mcs=30, spw=10)       # as selected for the v3 LightGBM
T0 = time.time()
FEATS = ["cn", "aa", "ra", "jac", "pa", "deg_min", "deg_max", "pap_min", "pap_max", "rec_min", "rec_max", "age_min", "age_max", "paths3", "n_fac"]


def log(*a):
    print(f"[{(time.time() - T0) / 60:6.1f} min]", *a, flush=True)


# ------------------------------------------------------------------------------------------------ big graph
class Big:
    def __init__(self, C):
        self.C, n = C, C.n
        out = config.OUT_DIR
        g = pd.read_csv(out / "group15_data.csv", dtype=str, keep_default_na=False, usecols=["institution", "faculty_name", "author_id"])
        kidx = {k: i for i, k in enumerate(C.keys)}
        node = {}
        for k, aid in zip(g.institution + "|" + g.faculty_name, g.author_id):
            if k in kidx and aid:
                node[aid] = kidx[k]
        a = pd.read_csv(out / "all_authors" / "authorships.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "author_id"])
        a = a[(a.author_id != "") & a.openalex_work_id.isin(C.pidx)]
        nxt = n
        for x in a.author_id.unique():
            if x not in node:
                node[x] = nxt
                nxt += 1
        a = pd.DataFrame({"w": a.openalex_work_id.map(C.pidx), "node": a.author_id.map(node)}).drop_duplicates()
        self.N = nxt
        self.py = C.year_arr
        self.M = sp.csr_matrix((np.ones(len(a)), (a.w.values, a.node.values)), shape=(len(C.pids), self.N))
        first = np.full(self.N, 9999)
        yy = self.py[a.w.values]
        np.minimum.at(first, a.node.values, yy)
        self.first = first
        log(f"big graph: {self.N} people ({n} faculty), {len(a)} authorships on {a.w.nunique()} papers")
        self._snap = {}

    def edges(self, mask):
        X = self.M[mask]
        A = (X.T @ X).tocsr()
        A.setdiag(0)
        A.eliminate_zeros()
        A.data[:] = 1
        return A

    def snap(self, T):
        if T not in self._snap:
            A = self.edges(self.py <= T)
            deg = np.asarray(A.sum(1)).ravel()
            s = {"A": A, "deg": deg, "P2": (A @ A).tocsr(),
                 "pap": np.asarray(self.M[self.py <= T].sum(0)).ravel(), "rec": np.asarray(self.M[(self.py > T - 3) & (self.py <= T)].sum(0)).ravel(),
                 "age": np.where(self.first <= T, T - self.first, 0).astype(float),
                 "w1": np.where(deg > 1, 1 / np.log(np.maximum(deg, 2)), 0), "w2": np.divide(1, deg, out=np.zeros_like(deg, dtype=float), where=deg > 0)}
            self._snap[T] = s
        return self._snap[T]

    def features(self, T, u, v, chunk=60000):
        s, n = self.snap(T), self.C.n
        A, P2 = s["A"], s["P2"]
        cn, aa, ra, p3 = (np.zeros(len(u)) for _ in range(4))
        for i in range(0, len(u), chunk):
            a, b = u[i:i + chunk], v[i:i + chunk]
            Z = A[a].multiply(A[b]).tocsr()
            cn[i:i + chunk], aa[i:i + chunk], ra[i:i + chunk] = np.asarray(Z.sum(1)).ravel(), Z @ s["w1"], Z @ s["w2"]
            p3[i:i + chunk] = np.asarray(P2[a].multiply(A[b]).sum(1)).ravel()
        du, dv = s["deg"][u], s["deg"][v]
        mm = lambda k: (np.minimum(s[k][u], s[k][v]), np.maximum(s[k][u], s[k][v]))
        pm, rm, am = mm("pap"), mm("rec"), mm("age")
        jac = np.divide(cn, du + dv - cn, out=np.zeros(len(u)), where=(du + dv - cn) > 0)
        return pd.DataFrame({"cn": cn, "aa": aa, "ra": ra, "jac": jac, "pa": du * dv, "deg_min": np.minimum(du, dv), "deg_max": np.maximum(du, dv),
                             "pap_min": pm[0], "pap_max": pm[1], "rec_min": rm[0], "rec_max": rm[1], "age_min": am[0], "age_max": am[1], "paths3": p3,
                             "n_fac": (u < n).astype(int) + (v < n).astype(int)})

    def other_pairs(self, T):
        """Two-step pairs (never linked) among recently active people, excluding faculty-faculty pairs, with the T+1 label."""
        s, n = self.snap(T), self.C.n
        A, P2 = s["A"], s["P2"].copy()
        P2.data[:] = 1
        two = (P2 - P2.multiply(A)).tocoo()
        keep = (two.row < two.col) & (s["rec"][two.row] > 0) & (s["rec"][two.col] > 0) & ~((two.row < n) & (two.col < n))
        u, v = two.row[keep], two.col[keep]
        New = self.edges(self.py == T + 1)
        y = np.concatenate([np.asarray(New[u[i:i + 100000], v[i:i + 100000]]).ravel() for i in range(0, len(u), 100000)]) if len(u) else np.zeros(0)
        df = self.features(T, u, v)
        df["u"], df["v"], df["y"], df["T"] = u, v, (y > 0).astype(int), T
        return df


_fac, _oth = {}, {}


def fac_pairs(B, C, T):
    if T not in _fac:
        d = v2.dataset(C, T, "new")
        f = B.features(T, d.u.values, d.v.values)
        f["u"], f["v"], f["y"], f["T"] = d.u.values, d.v.values, d.y.values, T
        _fac[T] = (d, f)
    return _fac[T]


def other(B, T):
    if T not in _oth:
        _oth[T] = B.other_pairs(T)
        log(f"  other pairs T={T}: {len(_oth[T])} rows, {int(_oth[T].y.sum())} positives")
    return _oth[T]


# ------------------------------------------------------------------------------------------------ metrics
def per_faculty(df, s, k=5):
    d = pd.DataFrame({"u": df.u.values, "v": df.v.values, "y": df.y.values, "s": s})
    long = pd.concat([d.rename(columns={"u": "f"})[["f", "y", "s"]], d.rename(columns={"v": "f"})[["f", "y", "s"]]])
    has = long.groupby("f").y.sum()
    has = has[has > 0].index
    top = long[long.f.isin(has)].sort_values("s", ascending=False).groupby("f").head(k)
    g = top.groupby("f").y
    return {"faculty_with_a_new_link": int(len(has)), f"hit@{k}": round(float((g.sum() > 0).reindex(has, fill_value=False).mean()), 4),
            f"precision@{k}": round(float(g.mean().reindex(has, fill_value=0).mean()), 4)}


def basic(y, s):
    y = np.asarray(y)
    o = np.argsort(-np.asarray(s), kind="stable")
    r = {"positives": int(y.sum()), "pairs": len(y), "average_precision": round(float(average_precision_score(y, s)), 4), "roc_auc": round(float(roc_auc_score(y, s)), 4)}
    for k in (100, 500):
        r[f"precision@{k}"], r[f"recall@{k}"] = round(float(y[o[:k]].mean()), 3), round(float(y[o[:k]].sum() / y.sum()), 3)
    return r


# ------------------------------------------------------------------------------------------------ experiment
def main():
    C = v2.Corpus2()
    B = Big(C)
    fA = list(dict.fromkeys(v2.V1_NEW + v2.NEW_V2))
    for T in range(FIRST, FOLDS[-1] + 1):
        v2.dataset(C, T, "new")
        fac_pairs(B, C, T)
        other(B, T)
    log("features built for all snapshots")

    def train_sets(test_T):
        ts = range(FIRST, test_T)
        facs = pd.concat([fac_pairs(B, C, T)[1] for T in ts])
        return facs, pd.concat([facs] + [other(B, T) for T in ts])

    # hyper-parameters for B chosen on the validation fold (test_T = 2023, training windows <= 2022)
    _, big_val = train_sets(VAL_T)
    teV = fac_pairs(B, C, VAL_T)[1]
    scored = []
    for lv in (7, 15):
        for spw in (1, 10):
            p = dict(n=300, lr=0.03, leaves=lv, mcs=100, spw=spw)
            m = v2.make_lgb(p).fit(big_val[FEATS], big_val.y)
            scored.append((average_precision_score(teV.y, m.predict_proba(teV[FEATS])[:, 1]), p))
            log(f"  val B {p}: AP {scored[-1][0]:.4f}")
    PB = max(scored, key=lambda x: x[0])[1]
    log(f"selected params for B: {PB}")

    res = {"design": __doc__.split("Run:")[0].strip(), "params": {"A": PARAMS_A, "B_and_C": PB}, "folds": {}, "pooled": {}}
    pool = {}
    for test_T in FOLDS:
        facs, big = train_sets(test_T)
        dte, fte = fac_pairs(B, C, test_T)
        trA = v2.train_set(C, test_T, "new", FIRST)
        sc = {}
        sc["A: LightGBM, faculty data, v2 features (v3 reference)"] = v2.fit_predict("lgb", PARAMS_A, trA, dte, fA)[1]
        sc["B: LightGBM, big-graph features, ALL authors' pairs"] = v2.make_lgb(PB).fit(big[FEATS], big.y).predict_proba(fte[FEATS])[:, 1]
        sc["C: LightGBM, big-graph features, faculty pairs only"] = v2.make_lgb(PB).fit(facs[FEATS], facs.y).predict_proba(fte[FEATS])[:, 1]
        r = v2.rank01
        a, b, c = (sc[k] for k in list(sc))
        sc["A+B rank average"], sc["A+C rank average"] = (r(a) + r(b)) / 2, (r(a) + r(c)) / 2
        res["folds"][test_T] = {"label_year": test_T + 1, "train_rows_B": len(big), "train_positives_B": int(big.y.sum()), "train_positives_faculty_only": int(facs.y.sum()),
                                "models": {k: {**basic(dte.y, s), **per_faculty(dte, s)} for k, s in sc.items()}}
        for k, s in sc.items():
            pool.setdefault(k, []).append((dte.y.values, r(s), dte, s))
        log(f"fold {test_T} (label {test_T + 1}, {int(dte.y.sum())} positives): " + " | ".join(f"{k[:2]} AP {v['average_precision']:.4f}" for k, v in res["folds"][test_T]["models"].items()))
        if test_T == FOLDS[-1]:
            res["headline_ci95_ap"] = {k: v2.boot_ci(dte.y, s, average_precision_score) for k, s in sc.items()}
    for k, lst in pool.items():
        y, s = np.concatenate([x[0] for x in lst]), np.concatenate([x[1] for x in lst])
        w = np.array([res["folds"][t]["models"][k]["faculty_with_a_new_link"] for t in FOLDS], float)
        pf = {"faculty_with_a_new_link(sum over folds)": int(w.sum()), **{q: round(float(np.average([res["folds"][t]["models"][k][q] for t in FOLDS], weights=w)), 4) for q in ("hit@5", "precision@5")}}
        res["pooled"][k] = {**basic(y, s), **pf, "mean_fold_precision@100": round(float(np.mean([basic(x[0], x[1])["precision@100"] for x in lst])), 4),
                            "mean_fold_recall@500": round(float(np.mean([basic(x[0], x[1])["recall@500"] for x in lst])), 4)}
        m = res["pooled"][k]
        log(f"POOLED 2020-24 {k[:48]:48s} AP {m['average_precision']:.4f} AUC {m['roc_auc']:.4f} P@100(avg fold) {m['mean_fold_precision@100']} hit@5 {m['hit@5']}  ({m['positives']} positives)")
    (STATS / "link_prediction_v4_results.json").write_text(json.dumps(res, indent=1, default=float))
    log("written")


if __name__ == "__main__":
    main()
