"""Collaboration prediction v2: richer features, pooled training windows, gradient boosting, rolling-origin evaluation.

What changed against link_prediction.py (which is left untouched, v1 numbers are reproduced here under the same protocol):
  data      train windows are pooled (T' = 2017, 2018, ... as long as the 3-year outcome ends by the test T), so there are
            more positives; evaluation is rolling-origin (test T = 2020, 2021, 2022), headline = T = 2022 (outcome 2023-25)
  features  v1 features plus: shared references (TF-IDF cosine), citations between the two people's papers, title TF-IDF
            cosine, fine-grained topic cosine, shared venues, shared co-authors incl. outside people (Adamic-Adar weighted),
            3-hop paths, Katz score, spectral (SVD) embedding similarity, seniority (first year seen), citations, department-
            pair history, degree
  models    logistic regression (quantile-normalised), LightGBM, and the rank average of both
  selection hyper-parameters chosen on validation fold T = 2021 only (never on the headline fold)
  operating point  "flag the top q% of pairs", q chosen to maximise F1 on the validation fold, then applied unchanged to the test fold
No feature at time T uses a paper after T. Run: python link_prediction_v2.py
"""
import json
import pickle
import warnings

import numpy as np
import pandas as pd
import scipy.sparse as sp
import scipy.sparse.linalg
from scipy.sparse.csgraph import shortest_path
from sklearn.feature_extraction.text import TfidfTransformer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import QuantileTransformer
import lightgbm as lgb
import networkx as nx

import collab_model as cm
import config
import link_prediction as lp

warnings.filterwarnings("ignore")
STATS = config.OUT_DIR / "stats"
MODELS = config.OUT_DIR / "models"
HORIZON = 3
NO_PATH = 11
V1_NEW = cm.NEW_LINK_FEATURES
V1_REP = cm.FEATURES
NEW_V2 = ["refs_cosine", "cite_min", "cite_max", "title_cosine", "topic_fine_cosine", "venue_cosine", "coauth_shared", "coauth_aa", "coauth_cosine",
          "paths3", "katz", "spectral_cos", "spectral_dot", "first_year_min", "first_year_max", "log_cites_min", "log_cites_max",
          "dept_pair_joint_hist", "deg_min", "deg_max", "recent_trend_min", "recent_trend_max"]
GROUPS = {"network (v1)": ["common_neighbours", "jaccard_neighbours", "adamic_adar", "resource_allocation", "pref_attachment", "hop_distance", "same_community",
                           "joint_papers_hist", "years_since_last_joint"],
          "topic (v1 subfield)": ["topic_cosine", "topic_weighted_jaccard", "shared_subfields", "field_cosine"],
          "structure+activity (v1)": ["same_department", "same_institute", "institute_pair_joint_papers_hist", "log_papers_min", "log_papers_max",
                                      "recent_papers_min", "recent_papers_max"],
          "content (v2)": ["refs_cosine", "title_cosine", "topic_fine_cosine", "venue_cosine"],
          "citation links (v2)": ["cite_min", "cite_max"],
          "co-author overlap (v2)": ["coauth_shared", "coauth_aa", "coauth_cosine"],
          "graph embedding (v2)": ["paths3", "katz", "spectral_cos", "spectral_dot"],
          "career/impact (v2)": ["first_year_min", "first_year_max", "log_cites_min", "log_cites_max", "deg_min", "deg_max", "recent_trend_min",
                                 "recent_trend_max", "dept_pair_joint_hist"]}


class Corpus2(cm.Corpus):
    def __init__(self):
        super().__init__()
        out = config.OUT_DIR
        g = pd.read_csv(out / "group15_data.csv", dtype=str, keep_default_na=False, usecols=["institution", "faculty_name", "author_id"])
        g["key"] = g.institution + "|" + g.faculty_name
        own = g.groupby("key").author_id.apply(set).to_dict()
        pe = pd.read_csv(out / "papers_enriched.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "journal_name", "citations", "referenced_works"])
        pe = pe[pe.openalex_work_id.isin(self.paper_fac)].drop_duplicates("openalex_work_id")
        self.pids = sorted(self.paper_fac)
        self.pidx = {p: i for i, p in enumerate(self.pids)}
        pe = pe.set_index("openalex_work_id").reindex(self.pids).fillna("")
        self.year_arr = np.array([self.paper_year[p] for p in self.pids])
        self.cites = pd.to_numeric(pe.citations, errors="coerce").fillna(0).values
        # paper x faculty
        r, c = zip(*[(self.pidx[p], f) for p, fs in self.paper_fac.items() for f in fs])
        self.Pf = sp.csr_matrix((np.ones(len(r)), (r, c)), shape=(len(self.pids), self.n))
        # paper x all authors (own authors of each faculty are removed later)
        a = pd.read_csv(out / "authorships.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "author_id"])
        a = a[a.openalex_work_id.isin(self.pidx) & (a.author_id != "")].drop_duplicates()
        aid = {x: i for i, x in enumerate(sorted(a.author_id.unique()))}
        self.Pa = sp.csr_matrix((np.ones(len(a)), (a.openalex_work_id.map(self.pidx), a.author_id.map(aid))), shape=(len(self.pids), len(aid)))
        self.own_cols = [[aid[x] for x in own.get(k, ()) if x in aid] for k in self.keys]
        # paper x reference (all refs), paper -> paper citations inside the corpus
        refs = [x.split(";") if x else [] for x in pe.referenced_works]
        rv = {}
        rr, rc, cr, cc = [], [], [], []
        for i, lst in enumerate(refs):
            for x in lst:
                rr.append(i)
                rc.append(rv.setdefault(x, len(rv)))
                if x in self.pidx:
                    cr.append(i)
                    cc.append(self.pidx[x])
        self.Pr = sp.csr_matrix((np.ones(len(rr)), (rr, rc)), shape=(len(self.pids), len(rv)))
        self.Cit = sp.csr_matrix((np.ones(len(cr)), (cr, cc)), shape=(len(self.pids), len(self.pids)))
        # paper x venue, paper x fine topic
        ven = {v: i for i, v in enumerate(sorted({v for v in pe.journal_name if v}))}
        vr = [(i, ven[v]) for i, v in enumerate(pe.journal_name) if v]
        self.Pv = sp.csr_matrix((np.ones(len(vr)), tuple(zip(*vr))), shape=(len(self.pids), len(ven)))
        t = pd.read_csv(out / "work_topics.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "topic"])
        t = t[t.openalex_work_id.isin(self.pidx) & (t.topic != "")].drop_duplicates("openalex_work_id")
        tv = {v: i for i, v in enumerate(sorted(t.topic.unique()))}
        self.Pt = sp.csr_matrix((np.ones(len(t)), (t.openalex_work_id.map(self.pidx), t.topic.map(tv))), shape=(len(self.pids), len(tv)))
        self.first_year = self.rows.groupby("key").year.min().reindex(self.keys).values

    # ---------------------------------------------------------------------------------------------- helpers
    @staticmethod
    def _tfidf_cos(M):
        if M.nnz == 0:
            return np.zeros((M.shape[0], M.shape[0]))
        X = TfidfTransformer(sublinear_tf=True).fit_transform(M)
        return (X @ X.T).toarray()

    def feature_matrices(self, H):
        T, n, A = H["T"], self.n, H["A"]
        base = self._base_features(H)
        m = (self.year_arr <= T).astype(float)
        Pf = sp.diags(m) @ self.Pf                 # papers up to T only
        PfT = Pf.T.tocsr()
        deg = A.sum(1)
        # content similarities
        base["refs_cosine"] = self._tfidf_cos(PfT @ self.Pr)
        base["venue_cosine"] = self._tfidf_cos(PfT @ self.Pv)
        base["topic_fine_cosine"] = self._tfidf_cos(PfT @ self.Pt)
        docs = [" ".join(self.paper_title[self.pids[p]] for p in Pf[:, i].nonzero()[0]) for i in range(n)]
        try:
            X = TfidfVectorizer(stop_words="english", min_df=2, sublinear_tf=True, ngram_range=(1, 2)).fit_transform(docs)
            base["title_cosine"] = (X @ X.T).toarray()
        except ValueError:
            base["title_cosine"] = np.zeros((n, n))
        # citations between the two people's papers (either direction)
        X = (PfT @ self.Cit @ Pf).toarray()
        np.fill_diagonal(X, 0)
        base["cite_min"], base["cite_max"] = np.minimum(X, X.T), np.maximum(X, X.T)
        # shared co-authors (people on their papers, excluding themselves)
        M = (PfT @ self.Pa).tolil()
        for i, cols in enumerate(self.own_cols):
            for c in cols:
                M[i, c] = 0
        M = M.tocsr()
        B = (M > 0).astype(float)
        adeg = np.asarray(B.sum(0)).ravel()
        w = sp.diags(np.divide(1, np.log(np.maximum(adeg, 2)), out=np.zeros_like(adeg), where=adeg > 1))
        base["coauth_shared"] = (B @ B.T).toarray()
        base["coauth_aa"] = (B @ w @ B.T).toarray()
        base["coauth_cosine"] = self._tfidf_cos(M)
        # higher-order graph scores
        A2 = A @ A
        A3 = A2 @ A
        base["paths3"] = A3
        beta = 0.05
        base["katz"] = beta * A + beta ** 2 * A2 + beta ** 3 * A3
        d = np.maximum(deg, 1) ** -0.5
        Z = sp.csr_matrix(A * d[:, None] * d[None, :])
        k = min(16, n - 2)
        try:
            u, s, _ = sp.linalg.svds(Z, k=k, random_state=15)
            E = u * np.sqrt(np.abs(s))
        except Exception:
            E = np.zeros((n, k))
        nrm = np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-12)
        base["spectral_cos"] = (E / nrm) @ (E / nrm).T * (deg[:, None] > 0) * (deg[None, :] > 0)
        base["spectral_dot"] = E @ E.T
        # career / impact
        fy = np.where(np.isnan(self.first_year.astype(float)), T, self.first_year.astype(float))
        fy = T - np.minimum(fy, T)
        base["first_year_min"], base["first_year_max"] = np.minimum(fy[:, None], fy[None, :]), np.maximum(fy[:, None], fy[None, :])
        lc = np.log1p(np.asarray(PfT @ self.cites).ravel())
        base["log_cites_min"], base["log_cites_max"] = np.minimum(lc[:, None], lc[None, :]), np.maximum(lc[:, None], lc[None, :])
        base["deg_min"], base["deg_max"] = np.minimum(deg[:, None], deg[None, :]), np.maximum(deg[:, None], deg[None, :])
        # trend: papers in last 3 years minus papers in the 3 years before
        prev = np.asarray(sp.diags(((self.year_arr <= T - 3) & (self.year_arr > T - 6)).astype(float)).dot(self.Pf).sum(0)).ravel()
        tr = H["recent"] - prev
        base["recent_trend_min"], base["recent_trend_max"] = np.minimum(tr[:, None], tr[None, :]), np.maximum(tr[:, None], tr[None, :])
        # department-pair history: papers already linking the two people's (institute, department) pairs
        keys = np.array([f"{i}|{d}" for i, d in zip(self.inst, self.dept)])
        uk, inv = np.unique(keys, return_inverse=True)
        D = sp.csr_matrix((np.ones(n), (np.arange(n), inv)), shape=(n, len(uk)))
        dp = (D.T @ sp.csr_matrix(H["W"]) @ D).toarray()
        base["dept_pair_joint_hist"] = dp[inv][:, inv]
        return base

    def _base_features(self, H):
        """v1 features without igraph (networkx Louvain, scipy shortest paths)."""
        A, n = H["A"], self.n
        deg = A.sum(1)
        cn = A @ A
        union = deg[:, None] + deg[None, :] - cn
        jac = np.divide(cn, union, out=np.zeros_like(cn), where=union > 0)
        aa = (A * np.where(deg > 1, 1 / np.log(np.maximum(deg, 2)), 0)[None, :]) @ A
        ra = (A * np.divide(1, deg, out=np.zeros_like(deg), where=deg > 0)[None, :]) @ A
        G = nx.from_numpy_array(A)
        memb = np.zeros(n)
        for ci, comp in enumerate(nx.community.louvain_communities(G, seed=15)):
            memb[list(comp)] = ci
        dist = shortest_path(sp.csr_matrix(A), unweighted=True, directed=False)
        dist = np.minimum(np.where(np.isinf(dist), NO_PATH, dist), NO_PATH)

        def norm(M):
            s = M.sum(1, keepdims=True)
            return np.divide(M, s, out=np.zeros_like(M), where=s > 0)
        S, F = norm(H["sub"]), norm(H["fld"])

        def cos(M):
            N = M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-12)
            return N @ N.T
        wj = np.zeros((n, n))
        for i in range(n):
            wj[i] = np.divide(np.minimum(S[i], S).sum(1), np.maximum(S[i], S).sum(1), out=np.zeros(n), where=np.maximum(S[i], S).sum(1) > 0)
        present = (H["sub"] > 0).astype(float)
        lp_ = np.log1p(H["papers"])
        inst_idx = np.array([H["ii"][x] for x in self.inst])
        dept = np.array([f"{i}|{d}" for i, d in zip(self.inst, self.dept)])
        yrs = np.where(H["last"] > 0, H["T"] - H["last"], np.nan)
        return {"common_neighbours": cn, "jaccard_neighbours": jac, "adamic_adar": aa, "resource_allocation": ra, "pref_attachment": np.outer(deg, deg),
                "hop_distance": dist, "same_community": (memb[:, None] == memb[None, :]).astype(float), "joint_papers_hist": H["W"],
                "years_since_last_joint": yrs, "topic_cosine": cos(S), "topic_weighted_jaccard": wj, "shared_subfields": present @ present.T,
                "field_cosine": cos(F), "log_papers_min": np.minimum(lp_[:, None], lp_[None, :]), "log_papers_max": np.maximum(lp_[:, None], lp_[None, :]),
                "recent_papers_min": np.minimum(H["recent"][:, None], H["recent"][None, :]), "recent_papers_max": np.maximum(H["recent"][:, None], H["recent"][None, :]),
                "same_department": (dept[:, None] == dept[None, :]).astype(float) * (np.array(self.dept)[:, None] != ""),
                "same_institute": (inst_idx[:, None] == inst_idx[None, :]).astype(float),
                "institute_pair_joint_papers_hist": H["ipair"][inst_idx][:, inst_idx], "_memb": memb}

    def pair_frame2(self, mats, pairs):
        ii, jj = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        out = pd.DataFrame({f: mats[f][ii, jj] for f in V1_REP + NEW_V2})
        out["u"], out["v"] = ii, jj
        out["years_since_last_joint"] = out.years_since_last_joint.fillna(-1)
        return out


_cache = {}


def dataset(C, T, task):
    if (T, task) in _cache:
        return _cache[(T, task)]
    key = ("mats", T)
    if key not in _cache:
        H0 = C.history(T)
        _cache[key] = (H0, C.feature_matrices(H0))
    H, mats = _cache[key]
    act = C.active(H)
    outcome = set(C.pair_papers(T + 1, T + HORIZON))
    pairs = [(act[a], act[b]) for a in range(len(act)) for b in range(a + 1, len(act)) if (task == "new") != (H["A"][act[a], act[b]] > 0)]
    df = C.pair_frame2(mats, pairs)
    df["y"] = [int((min(u, v), max(u, v)) in outcome) for u, v in zip(df.u, df.v)]
    df["T"] = T
    _cache[(T, task)] = df
    return df


def train_set(C, test_T, task, first=2017):
    return pd.concat([dataset(C, t, task) for t in range(first, test_T - HORIZON + 1)])


# ------------------------------------------------------------------------------------------------ models
def make_lr(C_=0.3):
    return make_pipeline(QuantileTransformer(n_quantiles=200, output_distribution="normal", subsample=10 ** 9, random_state=15),
                         LogisticRegression(C=C_, class_weight="balanced", max_iter=3000))


def make_lgb(p):
    return lgb.LGBMClassifier(n_estimators=p["n"], learning_rate=p["lr"], num_leaves=p["leaves"], min_child_samples=p["mcs"], subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.7, reg_lambda=5.0, scale_pos_weight=p["spw"], random_state=15, n_jobs=16, verbose=-1)


def rank01(x):
    return pd.Series(x).rank(pct=True).values


def fit_predict(kind, params, tr, te, feats):
    if kind == "lr":
        m = make_lr(params).fit(tr[feats], tr.y)
    else:
        m = make_lgb(params).fit(tr[feats], tr.y)
    return m, m.predict_proba(te[feats])[:, 1]


def operating(y, score, q):
    """Flag the top q fraction of pairs as 'will collaborate'."""
    y = np.asarray(y)
    k = max(1, int(round(q * len(y))))
    order = np.argsort(-np.asarray(score), kind="stable")
    pred = np.zeros(len(y), int)
    pred[order[:k]] = 1
    tp, fp = int(((pred == 1) & (y == 1)).sum()), int(((pred == 1) & (y == 0)).sum())
    fn, tn = int(((pred == 0) & (y == 1)).sum()), int(((pred == 0) & (y == 0)).sum())
    P, R = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    F1 = 2 * P * R / max(P + R, 1e-12)
    mcc = (tp * tn - fp * fn) / max(np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)), 1e-12)
    return {"flagged_fraction": round(q, 5), "flagged": k, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "accuracy": round((tp + tn) / len(y), 5),
            "precision": round(P, 4), "recall": round(R, 4), "f1": round(F1, 4), "mcc": round(mcc, 4)}


def best_q(y, score, grid):
    return max(grid, key=lambda q: operating(y, score, q)["f1"])


def boot_ci(y, s, fn, B=100, seed=15):
    rng = np.random.default_rng(seed)
    y, s = np.asarray(y), np.asarray(s)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    vals = []
    for _ in range(B):
        idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        vals.append(fn(y[idx], s[idx]))
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


# ------------------------------------------------------------------------------------------------ experiment
def run_task(C, task):
    f1set = V1_NEW if task == "new" else V1_REP
    f2set = f1set + (NEW_V2 if task == "new" else NEW_V2)
    f2set = list(dict.fromkeys(f2set))
    qgrid = np.unique(np.r_[np.linspace(0.0005, 0.01, 20), np.linspace(0.01, 0.2, 20)]) if task == "new" else np.linspace(0.05, 1.0, 20)
    res = {"folds": {}, "selection": {}}
    # --- hyper-parameter selection on validation fold T = 2021 (train windows end by 2021)
    vtr, vte = train_set(C, 2021, task), dataset(C, 2021, task)
    grid = [dict(n=n, lr=0.03, leaves=l, mcs=m, spw=s) for n in (200, 400) for l in (7,) for m in (30, 100) for s in (1, 10)]
    scored = []
    for p in grid:
        _, sc = fit_predict("lgb", p, vtr, vte, f2set)
        scored.append((average_precision_score(vte.y, sc), p))
    scored.sort(key=lambda x: -x[0])
    best = scored[0][1]
    lr_scored = []
    for c in (0.03, 0.1, 0.3, 1.0):
        _, sc = fit_predict("lr", c, vtr, vte, f2set)
        lr_scored.append((average_precision_score(vte.y, sc), c))
    best_c = max(lr_scored)[1]
    res["selection"] = {"validation_T": 2021, "best_lgb": best, "best_lgb_val_AP": round(scored[0][0], 4), "best_lr_C": best_c,
                        "best_lr_val_AP": round(max(lr_scored)[0], 4), "lgb_grid_size": len(grid)}
    print(f"[{task}] selected LGB {best}  val AP {scored[0][0]:.4f}; LR C={best_c}", flush=True)

    def configs():
        return {"v1 baseline: logistic regression (v1 feats, single window)": None,
                "LR, v1 features, pooled windows": ("lr", best_c, f1set),
                "LightGBM, v1 features, pooled windows": ("lgb", best, f1set),
                "LR, v2 features": ("lr", best_c, f2set),
                "LightGBM, v2 features": ("lgb", best, f2set),
                "ensemble (LR + LightGBM, v2 features)": "ens"}

    qsel = None
    for T in (2020, 2021, 2022):
        te = dataset(C, T, task)
        tr = train_set(C, T, task)
        fold = {"train_windows": sorted(tr["T"].unique().tolist()), "train_pairs": len(tr), "train_positives": int(tr.y.sum()),
                "test_pairs": len(te), "test_positives": int(te.y.sum()), "metrics": {}, "scores": {}}
        for name, cfg in configs().items():
            if cfg is None:        # exact v1 protocol: single train window T-3, LR (standardised, balanced), v1 features
                from sklearn.preprocessing import StandardScaler
                t1 = dataset(C, T - HORIZON, task)
                m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000)).fit(t1[f1set], t1.y)
                sc = m.predict_proba(te[f1set])[:, 1]
            elif cfg == "ens":
                sc = (rank01(fold["scores"]["LR, v2 features"]) + rank01(fold["scores"]["LightGBM, v2 features"])) / 2
            else:
                _, sc = fit_predict(cfg[0], cfg[1], tr, te, cfg[2])
            fold["scores"][name] = sc
            fold["metrics"][name] = lp.metrics(te.y, sc, ks=(50, 100, 500))
        res["folds"][T] = {k: v for k, v in fold.items() if k != "scores"}
        res["folds"][T]["_y"], res["folds"][T]["_scores"] = te.y.values, fold["scores"]
        print(f"  fold T={T}: " + " | ".join(f"{k[:28]} AP {v['average_precision']:.3f}" for k, v in fold["metrics"].items()), flush=True)
    # --- operating point chosen on validation fold, applied to headline fold
    val, head = res["folds"][2021], res["folds"][2022]
    res["operating_point"] = {}
    for name in val["_scores"]:
        q = best_q(val["_y"], val["_scores"][name], qgrid)
        res["operating_point"][name] = {"q_from_validation_2021": round(float(q), 5), "validation_F1": operating(val["_y"], val["_scores"][name], q)["f1"],
                                        "test_2022": operating(head["_y"], head["_scores"][name], q)}
    # --- bootstrap CIs on headline fold
    res["headline_ci95"] = {}
    for name in head["_scores"]:
        y, s = head["_y"], head["_scores"][name]
        res["headline_ci95"][name] = {"average_precision": boot_ci(y, s, average_precision_score), "roc_auc": boot_ci(y, s, roc_auc_score)}
    # --- feature-group ablation (LightGBM v2, headline fold) and importance
    te, tr = dataset(C, 2022, task), train_set(C, 2022, task)
    res["ablation_lgb_v2"] = {}
    for g, cols in GROUPS.items():
        cols = [c for c in cols if c in f2set]
        if not cols:
            continue
        _, s_only = fit_predict("lgb", best, tr, te, cols)
        rest = [c for c in f2set if c not in cols]
        _, s_drop = fit_predict("lgb", best, tr, te, rest)
        res["ablation_lgb_v2"][g] = {"only_AP": round(float(average_precision_score(te.y, s_only)), 4), "only_AUC": round(float(roc_auc_score(te.y, s_only)), 4),
                                     "drop_AP": round(float(average_precision_score(te.y, s_drop)), 4), "drop_AUC": round(float(roc_auc_score(te.y, s_drop)), 4)}
    m, _ = fit_predict("lgb", best, tr, te, f2set)
    imp = m.booster_.feature_importance("gain")
    res["lgb_gain_importance"] = {f: round(float(v / imp.sum()), 4) for f, v in sorted(zip(f2set, imp), key=lambda x: -x[1])[:15]}
    # final models fit on every window with a finished outcome, for the forward ranking
    full = train_set(C, 2025, task)
    final = {"lr": make_lr(best_c).fit(full[f2set], full.y), "lgb": make_lgb(best).fit(full[f2set], full.y)}
    return res, {"models": final, "features": f2set}


def strip(res):
    res = dict(res)
    res["folds"] = {T: {k: v for k, v in f.items() if k not in ("_y", "_scores")} for T, f in res["folds"].items()}
    return json.loads(json.dumps(res, default=float))


def main():
    C = Corpus2()
    print(f"{C.n} faculty, {len(C.pids)} papers", flush=True)
    results, allfit = {"design": __doc__.split("Run:")[0].strip(), "tasks": {}}, {}
    for task in ("new", "repeat"):
        res, fit = run_task(C, task)
        results["tasks"][task] = strip(res)
        allfit[task] = fit
        (STATS / f"link_prediction_v2_{task}.json").write_text(json.dumps(results["tasks"][task], indent=1, default=float))
    pickle.dump(allfit, open(MODELS / "collab_models_v2.pkl", "wb"))
    # forward ranking at T = 2025 (never-collaborated pairs)
    H, mats = _cache.get(("mats", 2025)) or (C.history(2025), None)
    if mats is None:
        mats = C.feature_matrices(H)
    act = C.active(H)
    pairs = [(act[a], act[b]) for a in range(len(act)) for b in range(a + 1, len(act)) if H["A"][act[a], act[b]] == 0]
    df = C.pair_frame2(mats, pairs)
    f = allfit["new"]["features"]
    df["score_lgb"] = allfit["new"]["models"]["lgb"].predict_proba(df[f])[:, 1]
    df["score_lr"] = allfit["new"]["models"]["lr"].predict_proba(df[f])[:, 1]
    df["rank_score"] = (rank01(df.score_lgb) + rank01(df.score_lr)) / 2
    top = df.sort_values("rank_score", ascending=False).head(3000).copy()
    top["faculty_a"], top["institute_a"] = [C.name[u] for u in top.u], [C.inst[u] for u in top.u]
    top["faculty_b"], top["institute_b"] = [C.name[v] for v in top.v], [C.inst[v] for v in top.v]
    top["rank"] = range(1, len(top) + 1)
    top[["rank", "faculty_a", "institute_a", "faculty_b", "institute_b", "rank_score", "score_lgb", "score_lr", "refs_cosine", "title_cosine", "coauth_shared",
         "common_neighbours", "same_department", "same_institute"]].to_csv(STATS / "collab_candidates_v2.csv", index=False)
    (STATS / "link_prediction_v2_results.json").write_text(json.dumps(results, indent=1, default=float))
    print("written")


if __name__ == "__main__":
    main()
