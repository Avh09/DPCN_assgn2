"""Feature engine for faculty collaboration prediction and compatibility scoring.

All features for a pair (u, v) at time T use only papers published up to year T, so they can be used for temporal
validation without leakage (see link_prediction.py). The same code scores arbitrary pairs for the assistant.

Features (per unordered pair of verified faculty)
  network     common_neighbours, jaccard_neighbours, adamic_adar, resource_allocation, pref_attachment (deg_u * deg_v),
              hop_distance (shortest path in the history graph, 11 = no path), same_community (Louvain on the history graph),
              joint_papers_hist, years_since_last_joint
  research    topic_cosine, topic_weighted_jaccard (OpenAlex subfields, shares of each person's papers), shared_subfields,
              field_cosine
  activity    log papers of each (history), papers in the last 3 years of each
  structure   same_department, same_institute, institute_pair_joint_papers_hist (papers that already link the two institutes)
"""
import numpy as np
import pandas as pd

import config

OUT = config.OUT_DIR
FEATURES = ["common_neighbours", "jaccard_neighbours", "adamic_adar", "resource_allocation", "pref_attachment", "hop_distance",
            "same_community", "joint_papers_hist", "years_since_last_joint", "topic_cosine", "topic_weighted_jaccard",
            "shared_subfields", "field_cosine", "log_papers_min", "log_papers_max", "recent_papers_min", "recent_papers_max",
            "same_department", "same_institute", "institute_pair_joint_papers_hist"]
NEW_LINK_FEATURES = [f for f in FEATURES if f not in ("joint_papers_hist", "years_since_last_joint")]
NO_PATH = 11


class Corpus:
    """Verified-faculty papers with years, subfields and fields; builds history graphs for any cut-off year."""

    def __init__(self):
        m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False,
                        usecols=["openalex_work_id", "year", "faculty_name", "institution", "department", "title"])
        m["year"] = m.year.astype(int)
        import movers
        alias = movers.aliases()          # a person listed at two of our institutes is one person: keep the current record (it carries all their papers)
        m = m[[(i, n) not in alias for i, n in zip(m.institution, m.faculty_name)]]
        m["key"] = m.institution + "|" + m.faculty_name
        t = pd.read_csv(OUT / "work_topics.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "field", "subfield"])
        m = m.merge(t, on="openalex_work_id", how="left").fillna("")
        self.rows = m.drop_duplicates(["openalex_work_id", "key"])
        info = self.rows.drop_duplicates("key").set_index("key")
        self.keys = sorted(info.index)
        self.idx = {k: i for i, k in enumerate(self.keys)}
        self.dept = [info.at[k, "department"] for k in self.keys]
        self.inst = [info.at[k, "institution"] for k in self.keys]
        self.name = [info.at[k, "faculty_name"] for k in self.keys]
        self.subfields = sorted(s for s in self.rows.subfield.unique() if s)
        self.fields = sorted(s for s in self.rows.field.unique() if s)
        self.n = len(self.keys)
        # paper -> faculty indices, years
        self.paper_fac = self.rows.groupby("openalex_work_id").key.apply(lambda s: sorted({self.idx[k] for k in s})).to_dict()
        self.paper_year = dict(zip(self.rows.openalex_work_id, self.rows.year))
        self.paper_title = dict(zip(self.rows.openalex_work_id, self.rows.title))

    # ------------------------------------------------------------------ history
    def pair_papers(self, y0, y1):
        """{(i, j): [paper ids]} for faculty pairs on papers published in [y0, y1]."""
        out = {}
        for pid, fs in self.paper_fac.items():
            if y0 <= self.paper_year[pid] <= y1 and len(fs) > 1:
                for a in range(len(fs)):
                    for b in range(a + 1, len(fs)):
                        out.setdefault((fs[a], fs[b]), []).append(pid)
        return out

    def history(self, T, since=2000):
        """Adjacency (binary), joint paper counts, last joint year, per-person subfield / field counts, papers, recent papers."""
        pp = self.pair_papers(since, T)
        A = np.zeros((self.n, self.n))
        Wm = np.zeros((self.n, self.n))
        last = np.zeros((self.n, self.n))
        for (i, j), ps in pp.items():
            A[i, j] = A[j, i] = 1
            Wm[i, j] = Wm[j, i] = len(ps)
            last[i, j] = last[j, i] = max(self.paper_year[p] for p in ps)
        sub = np.zeros((self.n, len(self.subfields)))
        fld = np.zeros((self.n, len(self.fields)))
        npap, rec = np.zeros(self.n), np.zeros(self.n)
        sidx = {s: k for k, s in enumerate(self.subfields)}
        fidx = {s: k for k, s in enumerate(self.fields)}
        rowmap = self.rows[self.rows.year <= T]
        for key, sf, fl, yr in zip(rowmap.key, rowmap.subfield, rowmap.field, rowmap.year):
            i = self.idx[key]
            npap[i] += 1
            rec[i] += yr > T - 3
            if sf:
                sub[i, sidx[sf]] += 1
            if fl:
                fld[i, fidx[fl]] += 1
        # papers linking pairs of institutes
        insts = sorted(set(self.inst))
        ii = {x: k for k, x in enumerate(insts)}
        ipair = np.zeros((len(insts), len(insts)))
        for pid, fs in self.paper_fac.items():
            if self.paper_year[pid] <= T:
                s = sorted({ii[self.inst[f]] for f in fs})
                for a in range(len(s)):
                    for b in range(a + 1, len(s)):
                        ipair[s[a], s[b]] += 1
                        ipair[s[b], s[a]] += 1
        return {"A": A, "W": Wm, "last": last, "sub": sub, "fld": fld, "papers": npap, "recent": rec, "ipair": ipair, "ii": ii, "T": T}

    # ------------------------------------------------------------------ features
    def feature_matrices(self, H):
        import igraph as ig
        A, n = H["A"], self.n
        deg = A.sum(1)
        cn = A @ A
        union = deg[:, None] + deg[None, :] - cn
        jac = np.divide(cn, union, out=np.zeros_like(cn), where=union > 0)
        w_aa = np.where(deg > 1, 1 / np.log(np.maximum(deg, 2)), 0)
        aa = (A * w_aa[None, :]) @ A
        ra = (A * np.divide(1, deg, out=np.zeros_like(deg), where=deg > 0)[None, :]) @ A
        g = ig.Graph.Adjacency((A > 0).tolist(), mode="undirected")
        ig.set_random_number_generator(__import__("random").Random(15))
        memb = np.array(g.community_multilevel().membership)
        dist = np.array(g.distances(), dtype=float)
        dist[np.isinf(dist)] = NO_PATH
        dist = np.minimum(dist, NO_PATH)
        # research similarity
        def norm(M):
            s = M.sum(1, keepdims=True)
            return np.divide(M, s, out=np.zeros_like(M), where=s > 0)
        S, F = norm(H["sub"]), norm(H["fld"])
        cos = lambda M: (M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-12)) @ (M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-12)).T
        scos, fcos = cos(S), cos(F)
        wj = np.zeros((n, n))
        for i in range(n):
            mn = np.minimum(S[i], S).sum(1)
            mx = np.maximum(S[i], S).sum(1)
            wj[i] = np.divide(mn, mx, out=np.zeros(n), where=mx > 0)
        present = (H["sub"] > 0).astype(float)
        shared = present @ present.T
        lp = np.log1p(H["papers"])
        inst_idx = np.array([H["ii"][x] for x in self.inst])
        dept = np.array([f"{i}|{d}" for i, d in zip(self.inst, self.dept)])
        T = H["T"]
        yrs_since = np.where(H["last"] > 0, T - H["last"], np.nan)
        return {"common_neighbours": cn, "jaccard_neighbours": jac, "adamic_adar": aa, "resource_allocation": ra,
                "pref_attachment": np.outer(deg, deg), "hop_distance": dist, "same_community": (memb[:, None] == memb[None, :]).astype(float),
                "joint_papers_hist": H["W"], "years_since_last_joint": yrs_since, "topic_cosine": scos, "topic_weighted_jaccard": wj,
                "shared_subfields": shared, "field_cosine": fcos,
                "log_papers_min": np.minimum(lp[:, None], lp[None, :]), "log_papers_max": np.maximum(lp[:, None], lp[None, :]),
                "recent_papers_min": np.minimum(H["recent"][:, None], H["recent"][None, :]),
                "recent_papers_max": np.maximum(H["recent"][:, None], H["recent"][None, :]),
                "same_department": (dept[:, None] == dept[None, :]).astype(float) * (np.array(self.dept)[:, None] != ""),
                "same_institute": (inst_idx[:, None] == inst_idx[None, :]).astype(float),
                "institute_pair_joint_papers_hist": H["ipair"][inst_idx][:, inst_idx],
                "_memb": memb}

    def pair_frame(self, H, mats, pairs):
        """DataFrame of FEATURES for the given (i, j) index pairs."""
        ii, jj = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        d = {f: mats[f][ii, jj] for f in FEATURES}
        out = pd.DataFrame(d)
        out["u"], out["v"] = ii, jj
        out["years_since_last_joint"] = out.years_since_last_joint.fillna(-1)
        return out

    def active(self, H, window=3):
        """Faculty who published at least once in the `window` years up to T (no future information)."""
        T = H["T"]
        r = self.rows[(self.rows.year > T - window) & (self.rows.year <= T)]
        return sorted({self.idx[k] for k in r.key})

    def explain(self, H, mats, i, j, topn=5):
        """Human-readable evidence for a pair: common neighbours, shared subfields, path length."""
        A = H["A"]
        common = [self.name[k] for k in np.where((A[i] > 0) & (A[j] > 0))[0]][:topn]
        si, sj = H["sub"][i], H["sub"][j]
        both = [(self.subfields[k], min(si[k] / max(si.sum(), 1), sj[k] / max(sj.sum(), 1))) for k in np.where((si > 0) & (sj > 0))[0]]
        both = [s for s, _ in sorted(both, key=lambda x: -x[1])[:topn]]
        return {"common_collaborators": common, "shared_subfields": both, "hops": int(mats["hop_distance"][i, j])}
