"""Region dynamics: (1) a gravity model with a distance decay that may change year by year, (2) a Markov chain of faculty collaboration reach.

1. Gravity model (spatial interaction). Joint papers between one of our institutes k and the partner institutes of Indian state s in year t:
       E[papers_kst] = exp( a_kt + b_s + delta * same_state_ks - gamma_t * ln distance_ks )
   a_kt absorbs how much institute k publishes that year, b_s how attractive state s is overall, delta a home-state bonus, and gamma_t is the
   distance decay: how much harder collaboration gets with distance in year t (gamma = 1: twice as far, half as many joint papers). A falling
   gamma means distance matters less over time. Poisson regression with fixed effects; 95% intervals by resampling states (bootstrap).
   Distances: great-circle km from each institute to the approximate centre of the partner's state (floor 50 km). Partners whose state is unknown
   or that are national multi-site bodies are left out.
2. Markov chain. Each faculty member, each year, is in one state: no papers, within the institute only, nearby partner (same state or region),
   elsewhere in India, or abroad (the farthest partner on any of their papers that year). Counting year-to-year moves (2016-2025, inside each
   person's span: first paper to 2025 for current faculty, to the last paper for former faculty) gives a transition matrix; its stationary distribution is where the mix settles if today's habits continue.
Writes stats/region_dynamics.json.
Run: python region_dynamics.py
"""
import json
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

import config

warnings.filterwarnings("ignore")
OUT, ST = config.OUT_DIR, config.OUT_DIR / "stats"
LOC = ST / "locality"
YEARS = list(range(2016, 2026))
HOME = {"MANIT Bhopal": (23.21, 77.41, "Madhya Pradesh"), "NIT Jamshedpur": (22.78, 86.14, "Jharkhand"), "NIT Silchar": (24.76, 92.80, "Assam")}
SH = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}
CENTRE = {"Uttar Pradesh": (27.1, 80.9), "West Bengal": (23.0, 87.7), "Tamil Nadu": (11.1, 78.7), "Maharashtra": (19.6, 75.7), "Madhya Pradesh": (23.5, 78.5),
          "Karnataka": (15.3, 75.7), "Delhi": (28.61, 77.21), "Odisha": (20.5, 84.4), "Andhra Pradesh": (15.9, 79.7), "Rajasthan": (26.6, 73.8), "Telangana": (17.9, 79.0),
          "Gujarat": (22.7, 71.6), "Assam": (26.2, 92.9), "Uttarakhand": (30.1, 79.2), "Punjab": (30.9, 75.4), "Jharkhand": (23.6, 85.3), "Bihar": (25.7, 85.6),
          "Jammu & Kashmir": (33.5, 75.1), "Haryana": (29.1, 76.1), "Chhattisgarh": (21.3, 81.9), "Kerala": (10.4, 76.5), "Himachal Pradesh": (31.9, 77.2),
          "Arunachal Pradesh": (28.0, 94.6), "Meghalaya": (25.5, 91.3), "Manipur": (24.7, 93.9), "Puducherry": (11.94, 79.83), "Tripura": (23.8, 91.7), "Goa": (15.4, 74.0),
          "Sikkim": (27.5, 88.5), "Mizoram": (23.2, 92.8), "Nagaland": (26.1, 94.5), "Chandigarh": (30.73, 76.78)}
STATES_MC = ["No papers", "Within institute only", "Nearby (same state or region)", "Elsewhere in India", "Abroad"]


def km(a, b):
    la1, lo1, la2, lo2 = map(np.radians, (a[0], a[1], b[0], b[1]))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))


def gravity():
    p = pd.read_csv(LOC / "partners_locality.csv")
    p = p[p.state.isin(CENTRE)]
    g = p.groupby(["your_inst", "state"])[[f"y{y}" for y in YEARS]].sum()
    rows = []
    for k in HOME:
        for s in CENTRE:
            d = max(50.0, km(HOME[k][:2], CENTRE[s]))
            for y in YEARS:
                rows.append({"inst": k, "state": s, "year": y, "papers": float(g.loc[(k, s), f"y{y}"]) if (k, s) in g.index else 0.0,
                             "logd": np.log(d), "same": float(HOME[k][2] == s), "km": d})
    df = pd.DataFrame(rows)
    df = df[df.groupby("state").papers.transform("sum") > 0]          # states with no joint paper at all carry no information

    def design(x):
        X = pd.get_dummies(x.state, prefix="s", dtype=float).join(pd.get_dummies(x.inst + "_" + x.year.astype(str), prefix="k", dtype=float))
        for y in YEARS:
            X[f"g{y}"] = -x.logd * (x.year == y)
        X["same"] = x.same
        return X

    def fit(x):
        x = x.reset_index(drop=True)
        X = design(x)
        m = PoissonRegressor(alpha=1e-6, max_iter=3000).fit(X, x.papers)
        coef = dict(zip(X.columns, m.coef_))
        return np.array([coef[f"g{y}"] for y in YEARS]), coef["same"]

    gam, same = fit(df)
    rng = np.random.default_rng(15)
    states = df.state.unique()
    boots = []
    for _ in range(200):
        pick = rng.choice(states, len(states))
        bx = pd.concat([df[df.state == s].assign(state=f"{s}#{i}") for i, s in enumerate(pick)])
        try:
            boots.append(fit(bx)[0])
        except Exception:
            continue
    B = np.array(boots)
    lo, hi = np.percentile(B, 2.5, 0), np.percentile(B, 97.5, 0)
    slope = np.polyfit(YEARS, gam, 1)[0]
    bslope = np.array([np.polyfit(YEARS, b, 1)[0] for b in B])
    early, late = gam[:3].mean(), gam[-3:].mean()
    return {"years": YEARS, "gamma": gam.round(3).tolist(), "lo": lo.round(3).tolist(), "hi": hi.round(3).tolist(),
            "home_state_bonus_factor": round(float(np.exp(same)), 2), "trend_per_year": round(float(slope), 4),
            "trend_ci95": [round(float(np.percentile(bslope, 2.5)), 4), round(float(np.percentile(bslope, 97.5)), 4)],
            "gamma_2016_18": round(float(early), 3), "gamma_2023_25": round(float(late), 3),
            "joint_papers_used": int(df.papers.sum()), "states": int(df.state.nunique()), "bootstrap_runs": int(len(B)),
            "partners_left_out_unknown_state": int((pd.read_csv(LOC / "partners_locality.csv").state.isin(["Unknown", "National (multi-site)"])).sum()),
            "by_distance_band": distance_bands(p)}


def distance_bands(p):
    """Share of joint papers with Indian partners by distance band, per year (descriptive companion to the model)."""
    bands = [(0, 300, "under 300 km"), (300, 1000, "300-1,000 km"), (1000, 99999, "over 1,000 km")]
    p = p.copy()
    p["km"] = [max(50.0, km(HOME[k][:2], CENTRE[s])) for k, s in zip(p.your_inst, p.state)]
    out = {}
    for a, b, lab in bands:
        sub = p[(p.km >= a) & (p.km < b)]
        out[lab] = [int(sub[f"y{y}"].sum()) for y in YEARS]
    tot = np.array([sum(out[l][i] for l in out) for i in range(len(YEARS))])
    return {k: [round(100 * v / t, 1) if t else None for v, t in zip(vals, tot)] for k, vals in out.items()}


def markov():
    fp = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False, usecols=["institution", "faculty_name", "openalex_work_id", "year"])
    fp["year"] = fp.year.astype(int)
    fp = fp[fp.year.between(2016, 2025)].drop_duplicates(["institution", "faculty_name", "openalex_work_id"])
    pe = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "our_institutes"], keep_default_na=False).set_index("openalex_work_id").our_institutes
    pl = pd.read_csv(LOC / "partners_locality.csv", usecols=["your_inst", "partner_inst", "locality"])
    loc = {(a, b): c for a, b, c in zip(pl.your_inst, pl.partner_inst, pl.locality)}
    pp = pd.read_csv(LOC / "partner_papers.csv")
    near = {"Same state": 2, "Same region": 2}
    level = {}
    for k, part, w in zip(pp.your_inst, pp.partner_inst, pp.openalex_work_id):
        lv = near.get(loc.get((k, part)), 3)
        level[(k, w)] = max(level.get((k, w), 1), lv)
    for k, w in zip(*[pd.read_csv(LOC / "foreign_partner_papers.csv")[c] for c in ("your_inst", "openalex_work_id")]):
        level[(k, w)] = 4
    fp["lv"] = [max(level.get((k, w), 1), 3 if len([x for x in str(pe.get(w, "")).split(";") if x]) > 1 else 1) for k, w in zip(fp.institution, fp.openalex_work_id)]
    fy = fp.groupby(["institution", "faculty_name", "year"]).lv.max()
    trans = {k: np.zeros((5, 5)) for k in ["all"] + list(HOME)}
    last = {k: np.zeros(5) for k in ["all"] + list(HOME)}
    ff = pd.read_csv(OUT.parent / "faculty_final.csv", usecols=["institution", "name", "faculty_status"])
    current = {(a, b) for a, b, c in zip(ff.institution, ff.name, ff.faculty_status) if c != "former"}
    for (inst, name), g in fy.groupby(level=[0, 1]):
        yrs = g.index.get_level_values(2)
        end = 2025 if (inst, name) in current else yrs.max()          # current faculty: the span runs to 2025, so years without papers count
        seq = [int(g.get((inst, name, y), 0)) for y in range(yrs.min(), end + 1)]
        for a, b in zip(seq, seq[1:]):
            trans["all"][a, b] += 1
            trans[inst][a, b] += 1
        if end == 2025:
            last["all"][seq[-1]] += 1
            last[inst][seq[-1]] += 1
    out = {"states": STATES_MC}
    for k, Tm in trans.items():
        Pm = Tm / Tm.sum(1, keepdims=True)
        w, v = np.linalg.eig(Pm.T)
        st = np.real(v[:, np.argmin(np.abs(w - 1))])
        st = st / st.sum()
        out[SH.get(k, k)] = {"transition": Pm.round(3).tolist(), "moves": int(Tm.sum()), "stationary": (100 * st).round(1).tolist(),
                             "now_2025": (100 * last[k] / last[k].sum()).round(1).tolist(), "persistence_years": [round(1 / (1 - Pm[i, i]), 2) if Pm[i, i] < 1 else None for i in range(5)]}
    return out


def main():
    import os
    old = ST / "region_dynamics.json"
    grav = json.load(open(old))["gravity"] if os.environ.get("REUSE_GRAVITY") and old.exists() else gravity()
    res = {"design": __doc__.split("Run:")[0].strip(), "gravity": grav, "markov": markov()}
    (ST / "region_dynamics.json").write_text(json.dumps(res, indent=1, default=float))
    g = res["gravity"]
    print("gamma by year:", dict(zip(g["years"], g["gamma"])))
    print("CI lo:", g["lo"]); print("CI hi:", g["hi"])
    print("trend/yr", g["trend_per_year"], g["trend_ci95"], "| home bonus x", g["home_state_bonus_factor"], "| papers", g["joint_papers_used"], "states", g["states"])
    print("bands:", g["by_distance_band"])
    m = res["markov"]["all"]
    print("moves", m["moves"]); print("now 2025:", m["now_2025"]); print("stationary:", m["stationary"]); print("persistence:", m["persistence_years"])
    for r in m["transition"]: print("  ", r)


if __name__ == "__main__":
    main()
