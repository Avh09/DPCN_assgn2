"""Collaboration prediction v3: train on 2016-2024, test on 2025, with a GNN.

Protocol (strictly temporal, one-year-ahead; papers are available through 2025 in full, 2026 is partial and unused):
  snapshot T  = features from papers up to year T, label = pair first/also co-authors a paper in year T+1
  train       T = 2016 .. 2023   (labels 2017..2024)           -> final test: T = 2024, label = 2025 co-authorship
  validation  train T = 2016 .. 2022, validate on T = 2023 (label 2024); all hyper-parameters / epochs chosen here only
Models: v1 logistic regression (baseline), LightGBM on v2 features, relational GNN (3 graphs: collaboration, co-author overlap,
content kNN) with a pair decoder that also sees the hand-crafted pair features, and rank-average ensembles.
Run: python link_prediction_v3.py
"""
import json
import warnings

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import QuantileTransformer

import config
import link_prediction_v2 as v2

warnings.filterwarnings("ignore")
torch.set_num_threads(16)
v2.HORIZON = 1
FIRST, VAL_T, TEST_T = 2016, 2023, 2024
STATS = config.OUT_DIR / "stats"
SEEDS = [0, 1, 2]
EPOCHS = 60
import time
T0 = time.time()


def log(*a):
    print(f"[{(time.time() - T0) / 60:6.1f} min]", *a, flush=True)


# ------------------------------------------------------------------------------------------------ graph inputs
def sym_norm(M):
    M = M + np.eye(len(M))
    d = M.sum(1) ** -0.5
    return M * d[:, None] * d[None, :]


def snapshot(C, T):
    H, mats = v2._cache[("mats", T)]
    n = C.n
    nz = lambda M: np.divide(M, M.sum(1, keepdims=True), out=np.zeros_like(M), where=M.sum(1, keepdims=True) > 0)
    inst = np.eye(len(set(C.inst)))[pd.factorize(pd.Series(C.inst))[0]]
    deg = H["A"].sum(1)
    age = T - np.where(np.isnan(C.first_year.astype(float)), T, C.first_year.astype(float))
    X = np.hstack([nz(H["sub"]), nz(H["fld"]), np.log1p(H["papers"])[:, None], np.log1p(H["recent"])[:, None], np.log1p(deg)[:, None],
                   np.log1p(np.maximum(age, 0))[:, None], inst])
    X = (X - X.mean(0)) / np.maximum(X.std(0), 1e-6)
    a1 = sym_norm(np.log1p(H["W"]))
    a2 = sym_norm(np.log1p(mats["coauth_shared"] * (1 - np.eye(n))))
    S = mats["refs_cosine"] + mats["topic_fine_cosine"] + mats["title_cosine"]
    S = S * (1 - np.eye(n))
    k = 10
    thr = -np.sort(-S, axis=1)[:, k - 1:k]
    a3 = sym_norm(((S >= thr) & (S > 0)).astype(float))
    t = lambda M: torch.tensor(M, dtype=torch.float32)
    return {"X": t(X), "A": [t(a1), t(a2), t(a3)]}


class Net(nn.Module):
    def __init__(self, d_in, n_pair, hid=64, drop=0.3, use_pair=True):
        super().__init__()
        self.use_pair = use_pair
        self.self1, self.self2 = nn.Linear(d_in, hid), nn.Linear(hid, hid)
        self.rel1 = nn.ModuleList([nn.Linear(d_in, hid, bias=False) for _ in range(3)])
        self.rel2 = nn.ModuleList([nn.Linear(hid, hid, bias=False) for _ in range(3)])
        self.drop = nn.Dropout(drop)
        self.pair = nn.Sequential(nn.Linear(n_pair, 32), nn.ReLU()) if use_pair else None
        self.dec = nn.Sequential(nn.Linear(2 * hid + (32 if use_pair else 0), 64), nn.ReLU(), nn.Dropout(drop), nn.Linear(64, 1))

    def encode(self, snap):
        x = self.drop(snap["X"])
        h = torch.relu(self.self1(x) + sum(a @ r(x) for a, r in zip(snap["A"], self.rel1)))
        h = self.drop(h)
        return torch.relu(self.self2(h) + sum(a @ r(h) for a, r in zip(snap["A"], self.rel2)))

    def score(self, z, u, v, pf):
        zu, zv = z[u], z[v]
        parts = [zu * zv, (zu - zv).abs()]
        if self.use_pair:
            parts.append(self.pair(pf))
        return self.dec(torch.cat(parts, 1)).squeeze(1)


def prep(df, feats, qt):
    return torch.tensor(qt.transform(df[feats]), dtype=torch.float32).clamp(-5, 5)


_prep_cache = {}


def prepare(tr, feats):
    key = (id(tr), tuple(feats))
    if key not in _prep_cache:
        qt = QuantileTransformer(n_quantiles=200, output_distribution="normal", subsample=10 ** 9, random_state=15).fit(tr[feats])
        groups = {}
        for T, g in tr.groupby("T"):
            groups[T] = {"u": torch.tensor(g.u.values), "v": torch.tensor(g.v.values), "y": torch.tensor(g.y.values, dtype=torch.float32), "pf": prep(g, feats, qt),
                         "pos": np.where(g.y.values == 1)[0], "neg": np.where(g.y.values == 0)[0]}
        _prep_cache[key] = (qt, groups)
    return _prep_cache[key]


def train_gnn(snaps, tr, feats, seed, epochs, use_pair=True, neg_ratio=30, eval_cb=None):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    qt, groups = prepare(tr, feats)
    net = Net(snaps[next(iter(groups))]["X"].shape[1], len(feats), use_pair=use_pair)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-3)
    hist = []
    for ep in range(epochs):
        net.train()
        loss = 0
        for T, g in groups.items():
            idx = np.concatenate([g["pos"], g["neg"][rng.integers(0, len(g["neg"]), neg_ratio * len(g["pos"]))]])
            idx = torch.tensor(idx)
            z = net.encode(snaps[T])
            logit = net.score(z, g["u"][idx], g["v"][idx], g["pf"][idx])
            w = torch.where(g["y"][idx] == 1, torch.tensor(float(neg_ratio) ** 0.5), torch.tensor(1.0))
            loss = loss + (nn.functional.binary_cross_entropy_with_logits(logit, g["y"][idx], reduction="none") * w).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if eval_cb and (ep + 1) % 10 == 0:
            hist.append((ep + 1, eval_cb(net, qt)))
    return net, qt, hist


@torch.no_grad()
def predict_gnn(net, qt, snap, df, feats):
    net.eval()
    z = net.encode(snap)
    return torch.sigmoid(net.score(z, torch.tensor(df.u.values), torch.tensor(df.v.values), prep(df, feats, qt))).numpy()


# ------------------------------------------------------------------------------------------------ evaluation
def metrics(y, s):
    y = np.asarray(y)
    o = np.argsort(-np.asarray(s), kind="stable")
    r = {"positives": int(y.sum()), "pairs": len(y), "base_rate": round(float(y.mean()), 5), "average_precision": round(float(average_precision_score(y, s)), 4),
         "roc_auc": round(float(roc_auc_score(y, s)), 4)}
    for k in (50, 100, 500):
        r[f"precision@{k}"], r[f"recall@{k}"] = round(float(y[o[:k]].mean()), 3), round(float(y[o[:k]].sum() / y.sum()), 3)
    return r


def run(C, task):
    f1set = v2.V1_NEW if task == "new" else v2.V1_REP
    f2set = list(dict.fromkeys(f1set + v2.NEW_V2))
    for T in range(FIRST, TEST_T + 1):
        v2.dataset(C, T, task)
    snaps = {T: snapshot(C, T) for T in range(FIRST, TEST_T + 1)}
    qgrid = np.unique(np.r_[np.linspace(0.0005, 0.01, 20), np.linspace(0.01, 0.2, 20)]) if task == "new" else np.linspace(0.05, 1.0, 20)
    tr_val, va = v2.train_set(C, VAL_T, task, FIRST), v2.dataset(C, VAL_T, task)
    tr_fin, te = v2.train_set(C, TEST_T, task, FIRST), v2.dataset(C, TEST_T, task)
    print(f"[{task}] train T {tr_fin['T'].min()}..{tr_fin['T'].max()} rows {len(tr_fin)} pos {int(tr_fin.y.sum())}; test pairs {len(te)} pos {int(te.y.sum())}", flush=True)

    # ---- validation: pick LGB params and GNN epoch count on T = 2023 (training windows <= 2022)
    scored = []
    for n in (200, 400):
        for mcs in (30, 100):
            for spw in (1, 10):
                p = dict(n=n, lr=0.03, leaves=7, mcs=mcs, spw=spw)
                _, sc = v2.fit_predict("lgb", p, tr_val, va, f2set)
                scored.append((average_precision_score(va.y, sc), p))
    scored.sort(key=lambda x: -x[0])
    best = scored[0][1]
    lr_c = max((average_precision_score(va.y, v2.fit_predict("lr", c, tr_val, va, f2set)[1]), c) for c in (0.03, 0.1, 0.3, 1.0))[1]
    cb = lambda net, qt: average_precision_score(va.y, predict_gnn(net, qt, snaps[VAL_T], va, f2set))
    _, _, hist = train_gnn(snaps, tr_val, f2set, 0, EPOCHS, eval_cb=cb)
    best_ep = EPOCHS  # fixed: the validation curve is too noisy to select an epoch from
    log(f"[{task}] val: LGB {best} AP {scored[0][0]:.4f}; LR C={lr_c}; GNN val-AP by epoch {[(e, round(a, 4)) for e, a in hist]} -> {best_ep}")

    # validation scores for every model (needed for the operating point)
    def all_scores(trn, tst, T, ep):
        out = {}
        out["v1 baseline: LR, v1 feats (single window)"] = v2.fit_predict("lr", lr_c, trn[trn["T"] == trn["T"].max()], tst, f1set)[1]
        out["LR, v2 feats"] = v2.fit_predict("lr", lr_c, trn, tst, f2set)[1]
        out["LightGBM, v2 feats"] = v2.fit_predict("lgb", best, trn, tst, f2set)[1]
        for name, up in (("GNN (graph only)", False), ("GNN + pair features", True)):
            fe = f2set if up else f1set[:1]
            ss = []
            for sd in SEEDS:
                log(f"   training {name} seed {sd} on T<={trn['T'].max()}")
                net, qt, _ = train_gnn(snaps, trn, fe, sd, ep, use_pair=up)
                ss.append(predict_gnn(net, qt, snaps[T], tst, fe))
            out[name] = np.mean(ss, 0)
        r = v2.rank01
        out["ensemble LGB + LR"] = (r(out["LightGBM, v2 feats"]) + r(out["LR, v2 feats"])) / 2
        out["ensemble LGB + GNN+pair"] = (r(out["LightGBM, v2 feats"]) + r(out["GNN + pair features"])) / 2
        out["ensemble LGB + LR + GNN+pair"] = (r(out["LightGBM, v2 feats"]) + r(out["LR, v2 feats"]) + r(out["GNN + pair features"])) / 3
        return out

    log('validation done; scoring validation fold')
    sv = all_scores(tr_val, va, VAL_T, best_ep)
    log('final: training on all windows through 2023')
    st = all_scores(tr_fin, te, TEST_T, best_ep)
    res = {"setup": {"train_T": [FIRST, TEST_T - 1], "test_T": TEST_T, "test_outcome_year": TEST_T + 1, "gnn_epochs": best_ep, "lgb": best, "lr_C": lr_c}, "test": {}, "validation": {}}
    for name in st:
        qv = v2.best_q(va.y, sv[name], qgrid)
        res["test"][name] = {**metrics(te.y, st[name]), "ci95_ap": v2.boot_ci(te.y, st[name], average_precision_score), "ci95_auc": v2.boot_ci(te.y, st[name], roc_auc_score),
                             "operating_point": {"q_from_validation": qv, **v2.operating(te.y, st[name], qv)}}
        res["validation"][name] = metrics(va.y, sv[name])
        m = res["test"][name]
        print(f"  [{task}] {name:34s} AP {m['average_precision']:.4f} {m['ci95_ap']}  AUC {m['roc_auc']:.4f}  P@100 {m['precision@100']}  R@500 {m['recall@500']}  "
              f"acc {m['operating_point']['accuracy']:.4f} F1 {m['operating_point']['f1']:.4f}", flush=True)
    pd.DataFrame({"u": te.u, "v": te.v, "y": te.y, **{k: v for k, v in st.items()}}).assign(
        a=lambda d: [C.name[i] for i in d.u], b=lambda d: [C.name[i] for i in d.v]).sort_values("ensemble LGB + LR + GNN+pair", ascending=False).head(3000).to_csv(
        STATS / f"link_prediction_v3_{task}_top.csv", index=False)
    return res


def main():
    C = v2.Corpus2()
    out = {"design": __doc__.split("Run:")[0].strip(), "tasks": {}}
    for task in ("new", "repeat"):
        out["tasks"][task] = run(C, task)
        (STATS / "link_prediction_v3_results.json").write_text(json.dumps(out, indent=1, default=float))
    print("written")


if __name__ == "__main__":
    main()
