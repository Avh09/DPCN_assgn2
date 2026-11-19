"""Citation dynamics with the Wang-Song-Barabasi (WSB) model (Science 2013), fitted to every paper's yearly citation history.

Model. A paper i gains citations at a rate that grows with how many it already has (preferential attachment), with its own attractiveness
(fitness eta_i) and with an ageing factor (novelty fades, log-normal in time):
        dc_i/dt  ~  eta_i * (c_i + m) * P_i(t),      P_i(t) = log-normal ageing with parameters mu_i, sigma_i
Solving gives the cumulative citations after t years:
        c_i(t) = m * ( exp( lambda_i * Phi( (ln t - mu_i) / sigma_i ) ) - 1 )
  lambda_i  relative fitness: how strongly the paper attracts citations; it alone sets the ultimate impact c_inf = m (e^lambda - 1)
  mu_i      immediacy: e^mu is roughly the age (years) at which the paper gains citations fastest
  sigma_i   longevity: how slowly the paper's attention fades
  m = 30    average references per paper (the constant of the original paper); Phi = standard normal cumulative distribution

Data: OpenAlex yearly citation counts (counts_by_year) for every paper; 2026 is partial and is not used (histories end in 2025). t = years since
publication + 1 (t = 1 at the end of the publication year).
Fits: papers published 2016-2021 (at least 5 yearly points) with at least 10 citations by 2025; least squares on log(1 + cumulative citations) with a
weak prior towards the typical parameters of papers whose citation peak is already visible (otherwise fitness and immediacy cannot be separated).
Prediction test: papers published 2016-2018 are fitted on their first 5 years only and must predict their citations in 2025, against a simple
baseline (citations after 5 years x the typical growth ratio, learned on the other half of the papers).
Writes stats/citation_dynamics.json (results) and stats/citation_dynamics_papers.json (per-paper parameters and histories for the dashboard).
Run: python citation_dynamics.py
"""
import json
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.special import ndtr
from scipy.stats import spearmanr

import config

warnings.filterwarnings("ignore")
OUT, ST = config.OUT_DIR, config.OUT_DIR / "stats"
M, LAST = 30.0, 2025
SH = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}


def wsb(t, lam, mu, sig):
    return M * (np.exp(lam * ndtr((np.log(t) - mu) / sig)) - 1)


PRIOR = None          # (centre, scale) per parameter, set from well-identified papers in main(); None = plain least squares
PW = 0.05            # prior weight (residual units of log citations)


def fit(c):
    """c: cumulative citations at t = 1..n -> (lam, mu, sig, r2_log). With PRIOR, a weak pull towards typical values keeps
    lambda and mu identifiable for papers that have not yet reached their citation peak (lambda and mu trade off there)."""
    t = np.arange(1, len(c) + 1, dtype=float)
    y = np.log1p(c)
    best = None
    for mu0 in (0.3, 1.0, 1.8):
        for sig0 in (0.6, 1.2):
            lam0 = np.log1p(c[-1] / M) / max(ndtr((np.log(t[-1]) - mu0) / sig0), 0.2)
            try:
                if PRIOR is None:
                    res_f = lambda p: np.log1p(wsb(t, *p)) - y
                else:
                    res_f = lambda p: np.r_[np.log1p(wsb(t, *p)) - y, PW * (np.asarray(p) - PRIOR[0]) / PRIOR[1]]
                r = least_squares(res_f, [min(max(lam0, 0.05), 7.9), mu0, sig0],
                                  bounds=([0.01, -1.0, 0.15], [8.0, 4.0, 4.0]))
            except ValueError:
                continue
            if best is None or r.cost < best.cost:
                best = r
    lam, mu, sig = best.x
    ss = ((y - y.mean()) ** 2).sum()
    sse = float(((np.log1p(wsb(t, lam, mu, sig)) - y) ** 2).sum())
    return float(lam), float(mu), float(sig), float(1 - sse / ss) if ss > 0 else None


def main():
    p = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "title", "year", "citations", "type", "field", "our_institutes"], keep_default_na=False)
    w = pd.read_csv(OUT / "work_extras.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "is_retracted", "counts_by_year"])
    d = p.merge(w, on="openalex_work_id")
    d = d[(d.is_retracted.str.lower() != "true") & (d.counts_by_year != "")]
    hist = {}
    for wid, y0, s in zip(d.openalex_work_id, d.year, d.counts_by_year):
        cy = {int(k): int(v) for k, v in json.loads(s).items()}
        hist[wid] = np.cumsum([cy.get(y, 0) for y in range(int(y0), LAST + 1)])
    d["c2025"] = [hist[w_][-1] if len(hist[w_]) else 0 for w_ in d.openalex_work_id]
    el = d[(d.year <= 2021) & (d.c2025 >= 10)].copy()
    print(f"fitting {len(el)} papers", flush=True)
    global PRIOR
    raw = np.array([fit(hist[w_])[:3] for w_ in el.openalex_work_id])
    n_pts = np.array([len(hist[w_]) for w_ in el.openalex_work_id])
    ok = (raw[:, 1] < np.log(n_pts) - 0.1) & (raw[:, 0] < 7.5)          # peak already observed and not at the bound: well identified
    PRIOR = (np.median(raw[ok], 0), np.maximum(raw[ok].std(0), [0.5, 0.3, 0.2]))
    print(f"prior from {int(ok.sum())} well-identified papers: centre {PRIOR[0].round(3)}, scale {PRIOR[1].round(3)}", flush=True)
    pars = [fit(hist[w_]) for w_ in el.openalex_work_id]
    el["lam"], el["mu"], el["sig"], el["r2"] = zip(*pars)
    el["peak_age"] = np.exp(el.mu)
    # projection anchored to the real 2025 count: real citations so far + the model's expected gain from 2025 to 2035
    el["c2035"] = [c + max(0.0, wsb(2035 - y + 1, l, m_, s) - wsb(LAST - y + 1, l, m_, s)) for c, y, l, m_, s in zip(el.c2025, el.year, el.lam, el.mu, el.sig)]
    el["insts"] = el.our_institutes.str.split(";")

    # ---------------------------------------------------------------- prediction test: first 5 years -> 2025
    te = d[(d.year <= 2018) & (d.c2025 >= 10)].copy()
    te["c5"] = [hist[w_][4] for w_ in te.openalex_work_id]
    te = te[te.c5 >= 3]
    rng = np.random.default_rng(15)
    te["half"] = rng.integers(0, 2, len(te))
    te["ratio"] = te.c2025 / te.c5
    base = []
    for r in te.itertuples():
        other = te[(te.half != r.half) & (te.year == r.year)]
        base.append(r.c5 * other.ratio.median())
    te["pred_base"] = base
    pf = [fit(hist[w_][:5]) for w_ in te.openalex_work_id]
    te["pred_wsb"] = [wsb(LAST - y + 1, l, m_, s) for y, (l, m_, s, _) in zip(te.year, pf)]
    te["pred_wsb"] = np.minimum(te.pred_wsb, 1e6)

    def score(col):
        e = np.abs(np.log(te[col].clip(lower=1) / te.c2025))
        top = te.c2025 >= te.c2025.quantile(0.9)
        pick = te[col] >= te[col].quantile(0.9)
        return {"median_error_factor": round(float(np.exp(e.median())), 3), "share_within_25pct": round(float((np.abs(te[col] / te.c2025 - 1) <= 0.25).mean()), 3),
                "rank_correlation": round(float(spearmanr(te[col], te.c2025)[0]), 3), "top10pct_found": round(float((pick & top).sum() / top.sum()), 3)}
    test = {"papers": int(len(te)), "years": "published 2016-2018, fitted on first 5 years, predicting citations in 2025",
            "wsb": score("pred_wsb"), "baseline": score("pred_base"), "baseline_desc": "citations after 5 years x median growth ratio of the other half of papers (same publication year)"}
    print("prediction test:", test, flush=True)

    # ---------------------------------------------------------------- summaries
    def summ(g):
        return {"papers": int(len(g)), "median_fitness": round(float(g.lam.median()), 3), "median_peak_age_years": round(float(g.peak_age.median()), 2),
                "median_longevity": round(float(g.sig.median()), 3), "share_high_fitness": round(float((g.lam >= el.lam.quantile(0.9)).mean()), 3)}
    by_inst = {SH[i]: summ(el[el.insts.map(lambda x: i in x)]) for i in SH}
    top_fields = el.field.value_counts().head(8).index
    by_field = {f: summ(el[el.field == f]) for f in top_fields}
    by_year = {int(y): summ(g) for y, g in el.groupby("year")}

    def row(r):
        return {"id": r.openalex_work_id, "title": r.title, "year": int(r.year), "insts": "; ".join(SH.get(i, i) for i in r.insts), "field": r.field, "citations_2025": int(r.c2025),
                "fitness": round(r.lam, 3), "peak_age": round(r.peak_age, 2), "longevity": round(r.sig, 3), "projected_2035": int(round(r.c2035))}
    el["n_years"] = LAST - el.year + 1
    # lists only use papers whose parameters are well determined: good fit, not at the bound, and the citation peak already visible in the data
    good = el[(el.r2 >= 0.8) & (el.lam < 7.5) & (el.mu < np.log(el.n_years))]
    early = el[(el.year >= 2020) & (el.r2 >= 0.8) & (el.lam < 7.5) & (el.mu < np.log(el.n_years) + 0.3) & (el.c2025 >= 30)]
    res = {"design": __doc__.split("Run:")[0].strip(), "m": M, "prior": {"centre": PRIOR[0].round(4).tolist(), "scale": PRIOR[1].round(4).tolist(), "weight": PW}, "fitted_papers": int(len(el)), "median_fit_r2": round(float(el.r2.median()), 3),
           "share_fit_r2_ge_0_9": round(float((el.r2 >= 0.9).mean()), 3), "prediction_test": test, "by_institute": by_inst, "by_field": by_field, "by_year": by_year,
           "fitness_hist": np.histogram(el.lam, bins=np.linspace(0, 8, 33))[0].tolist(), "fitness_bins": np.linspace(0, 8, 33).round(2).tolist(),
           "top_fitness": [row(r) for r in good.sort_values("lam", ascending=False).head(15).itertuples()],
           "early_stars": [row(r) for r in early.sort_values("lam", ascending=False).head(10).itertuples()],
           "list_rule": "lists use papers with fit R2 >= 0.8 whose citation peak is already visible in the data (early stars: nearly visible, and at least 30 citations)"}
    (ST / "citation_dynamics.json").write_text(json.dumps(res, indent=1, default=float))
    per = {r.openalex_work_id: [int(r.year), round(r.lam, 4), round(r.mu, 4), round(r.sig, 4), round(r.r2, 3) if r.r2 is not None else None, [int(x) for x in hist[r.openalex_work_id]]]
           for r in el.itertuples()}
    (ST / "citation_dynamics_papers.json").write_text(json.dumps(per, separators=(",", ":")))
    print(json.dumps({k: res[k] for k in ("fitted_papers", "median_fit_r2", "share_fit_r2_ge_0_9", "by_institute")}, indent=1))
    print("top fitness:", [(x["title"][:50], x["fitness"], x["citations_2025"], x["projected_2035"]) for x in res["top_fitness"][:5]])


if __name__ == "__main__":
    main()
