"""Per-faculty collaborator suggestions for the dashboard's "Find collaborators" box.

Two lists per current faculty member, because the two models answer different questions and their scores cannot be merged honestly:
  new     pairs that never co-authored, ranked by the v5 model (3-year horizon; collab_scores_v5.csv.gz from forward_ranking_v5.py)
  repeat  people they already co-authored with, ranked by the v3 repeat model (LightGBM + logistic regression, v2 features, trained on snapshots 2016-2024,
          applied to features at 2025): who they are most likely to publish with again
Writes stats/faculty_suggestions.json and stats/collab_scores_repeat_v3.csv.gz. Scores are rankings, not probabilities.
Run: python faculty_suggestions.py
"""
import json
import os

os.environ["HORIZON"] = "1"
import numpy as np
import pandas as pd

import config
import link_prediction_v2 as v2
import reasons

STATS = config.OUT_DIR / "stats"
NOW, TOP = 2025, 5


def main():
    C = v2.Corpus2()
    v2.HORIZON = 1
    setup = json.load(open(STATS / "link_prediction_v3_results.json"))["tasks"]["repeat"]["setup"]
    fe = list(dict.fromkeys(v2.V1_REP + v2.NEW_V2))
    tr = v2.train_set(C, NOW, "repeat", 2016)                      # snapshots 2016..2024, labels through 2025
    now = v2.dataset(C, NOW, "repeat")                             # features at 2025 for every pair that already co-authored (active faculty)
    lgb_model, lgb = v2.fit_predict("lgb", setup["lgb"], tr, now, fe)
    lr = v2.fit_predict("lr", setup["lr_C"], tr, now, fe)[1]
    now["rank_score"] = (v2.rank01(lgb) + v2.rank01(lr)) / 2
    now[["u", "v", "rank_score", "joint_papers_hist", "years_since_last_joint"]].round(5).to_csv(STATS / "collab_scores_repeat_v3.csv.gz", index=False)
    print(f"repeat model: trained on {len(tr)} rows ({int(tr.y.sum())} positives); scored {len(now)} pairs", flush=True)

    H0, mats = v2._cache[("mats", NOW)]
    ridx = {(int(u), int(v)): n for n, (u, v) in enumerate(zip(now.u, now.v))}
    rcontrib = lgb_model.predict(now[fe], pred_contrib=True)[:, :-1]
    rdrv = reasons.theme_drivers(rcontrib, fe)
    ndrv = json.load(open(STATS / "new_drivers_v5.json"))
    new = pd.read_csv(STATS / "collab_scores_v5.csv.gz")
    status = {(r.institution, r.name): r.faculty_status for r in pd.read_csv(config.OUT_DIR.parent / "faculty_final.csv").itertuples()}
    cur = np.array([status.get((C.inst[i], C.name[i]), "current") != "former" for i in range(C.n)])
    new = new[cur[new.u.values] & cur[new.v.values]]
    rep = now[cur[now.u.values] & cur[now.v.values]]

    def side(df):
        a = df[["u", "v", "rank_score"]].rename(columns={"u": "me", "v": "other"})
        b = df[["v", "u", "rank_score"]].rename(columns={"v": "me", "u": "other"})
        return pd.concat([a, b]).sort_values("rank_score", ascending=False)

    def facts(i, j, e):
        return {"hops": e["hops"] if e["hops"] < 11 else None, "common": e["common_collaborators"], "shared_other": float(mats["coauth_shared"][i, j]), "subfields": e["shared_subfields"],
                "topic": float(mats["topic_cosine"][i, j]), "refs": float(mats["refs_cosine"][i, j]), "same_dept": bool(mats["same_department"][i, j]),
                "same_inst": bool(mats["same_institute"][i, j]), "dept": C.dept[i], "inst": C.inst[i], "joint": int(H0["W"][i, j]),
                "last_year": int(H0["last"][i, j]) if H0["last"][i, j] else None}

    def why(drv, f):
        out = [p for p in (reasons.phrase(t, f) for t, _ in drv) if p]
        return out or ["a combination of many smaller signals, none of them dominant"]

    def rwhy(i, j):
        f = facts(i, j, C.explain(H0, mats, i, j))
        rest = [p for t, _ in rdrv[ridx[(min(i, j), max(i, j))]] if t != "history" for p in [reasons.phrase(t, f)] if p]
        return [reasons.phrase("history", f)] + (rest or [])

    ns, rs = side(new), side(rep)
    nt, rt = ns.groupby("me").head(TOP), rs.groupby("me").head(TOP)
    out = {}
    for i in range(C.n):
        if not cur[i]:
            continue
        key = f"{C.inst[i]}|{C.name[i]}"
        entry = {"name": C.name[i], "institute": C.inst[i], "department": C.dept[i], "new": [], "repeat": []}
        for r in nt[nt.me == i].itertuples():
            j = int(r.other)
            e = C.explain(H0, mats, i, j)
            entry["new"].append({"name": C.name[j], "institute": C.inst[j], "department": C.dept[j], "score": round(float(r.rank_score), 3),
                                 "hops": e["hops"] if e["hops"] < 11 else None, "common": e["common_collaborators"][:3], "subfields": e["shared_subfields"][:2],
                                 "topic": round(float(mats["topic_cosine"][i, j]), 2),
                                 "why": why(ndrv.get(f"{min(i, j)},{max(i, j)}", []), facts(i, j, e))})
        for r in rt[rt.me == i].itertuples():
            j = int(r.other)
            lj = int(H0["last"][i, j]) if H0["last"][i, j] else None
            entry["repeat"].append({"name": C.name[j], "institute": C.inst[j], "department": C.dept[j], "score": round(float(r.rank_score), 3),
                                    "joint_papers": int(H0["W"][i, j]), "last_joint_year": lj,
                                    "why": rwhy(i, j)})
        out[key] = entry
    (STATS / "faculty_suggestions.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    have_new = sum(1 for e in out.values() if e["new"])
    have_rep = sum(1 for e in out.values() if e["repeat"])
    print(f"written: {len(out)} faculty; {have_new} with new suggestions, {have_rep} with repeat suggestions")


if __name__ == "__main__":
    main()
