"""Read-only data layer for the assistant: loads the final tables once and builds the faculty collaboration graph.

Everything is loaded lazily and cached on the Store object (Streamlit keeps one Store per server process), so expensive objects
(graph, collaboration-model features) are built once. Paths come from config.py, so the assistant works from the repository root
on a laptop and on Streamlit Community Cloud.
"""
import json
import pickle
import re
from functools import cached_property
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"
ST = OUT / "stats"
INSTS = ["MANIT Bhopal", "NIT Jamshedpur", "NIT Silchar"]
SHORT = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}


def fid(inst, name):
    return f"{inst}|{name}"


class Store:
    # ------------------------------------------------------------------ faculty
    @cached_property
    def faculty(self):
        fp = pd.read_csv(ST / "faculty_performance.csv")
        nm = pd.read_csv(ST / "faculty_node_metrics.csv").drop(columns=["papers", "h_index", "department"], errors="ignore")
        ff = pd.read_csv(ROOT / "data" / "faculty_final.csv", dtype=str, keep_default_na=False)[["institution", "name", "openalex_author_ids", "verification"]].rename(columns={"name": "faculty_name"})
        cv = pd.read_csv(ST / "insights" / "connectivity_vs_impact.csv") if (ST / "insights" / "connectivity_vs_impact.csv").exists() else None
        d = fp.merge(nm, on=["institution", "faculty_name"], how="left", suffixes=("", "_node")).merge(ff, on=["institution", "faculty_name"], how="left")
        if cv is not None:
            d = d.merge(cv[["institution", "faculty_name", "mean_fwci", "median_fwci", "distinct_coauthors_all", "participation_dept"]], on=["institution", "faculty_name"], how="left", suffixes=("", "_cv"))
        import sys
        sys.path.insert(0, str(ROOT))
        from movers import aliases
        alias = aliases()      # a person listed at two of the three institutes is one person (their current record)
        d = d[[(i, n) not in alias for i, n in zip(d.institution, d.faculty_name)]].copy()
        d["id"] = [fid(i, n) for i, n in zip(d.institution, d.faculty_name)]
        d["short_inst"] = d.institution.map(SHORT)
        return d.set_index("id", drop=False)

    @cached_property
    def fac_papers(self):
        m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False,
                        usecols=["openalex_work_id", "institution", "faculty_name", "department", "year", "title", "type", "journal_name", "doi", "citations", "quartile", "field"])
        m["id"] = [fid(i, n) for i, n in zip(m.institution, m.faculty_name)]
        m = m[m.id.isin(self.faculty.index)]            # papers stay with the person's current record
        m["year"] = m.year.astype(int)
        m["citations"] = pd.to_numeric(m.citations, errors="coerce").fillna(0).astype(int)
        return m.drop_duplicates(["openalex_work_id", "id"])

    @cached_property
    def papers(self):
        p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str}, keep_default_na=False,
                        usecols=["openalex_work_id", "doi", "title", "year", "type", "journal_name", "citations", "field", "quartile", "our_institutes", "n_authors"])
        p["year"] = p.year.astype(int)
        p["citations"] = pd.to_numeric(p.citations, errors="coerce").fillna(0).astype(int)
        for f, cols in ((OUT / "work_topics.csv", ["openalex_work_id", "subfield", "topic"]), (OUT / "work_extras.csv", ["openalex_work_id", "fwci"]),
                        (ST / "citation_node_metrics.csv", ["openalex_work_id", "pagerank", "in_degree", "out_degree", "in_self_citations", "in_same_institute_other_author",
                                                            "in_between_our_institutes", "pagerank_rank_in_year"])):
            if f.exists():
                p = p.merge(pd.read_csv(f, usecols=cols, dtype={"openalex_work_id": str}), on="openalex_work_id", how="left")
        return p.set_index("openalex_work_id", drop=False)

    # ------------------------------------------------------------------ faculty graph
    @cached_property
    def graph(self):
        G = nx.Graph()
        for r in self.faculty.itertuples():
            G.add_node(r.id, institution=r.institution, department=r.department, name=r.faculty_name)
        e = pd.read_csv(OUT / "faculty_network_edges.csv")
        for r in e.itertuples():
            G.add_edge(fid(r.inst_a, r.faculty_a), fid(r.inst_b, r.faculty_b), weight=int(r.joint_papers), first_year=int(r.first_year), last_year=int(r.last_year))
        return G

    @cached_property
    def pair_papers(self):
        """{frozenset({id_a, id_b}): [openalex work ids]} for every pair of verified faculty on a paper."""
        out = {}
        for w, g in self.fac_papers.groupby("openalex_work_id"):
            ids = sorted(g.id)
            for a in range(len(ids)):
                for b in range(a + 1, len(ids)):
                    out.setdefault(frozenset((ids[a], ids[b])), []).append(w)
        return out

    # ------------------------------------------------------------------ institutes
    @cached_property
    def partners(self):
        p = pd.read_csv(ST / "locality" / "partners_locality.csv")
        return p

    @cached_property
    def ext_people(self):
        """One row per (paper, outside co-author, outside institute): the people on joint papers who are not the verified faculty or our own authors."""
        a = pd.read_csv(OUT / "all_authors" / "authorships.csv", dtype=str, keep_default_na=False,
                        usecols=["openalex_work_id", "author_id", "author_name", "institutions_detail", "is_our_inst"])
        fac_ids = set(x for v in pd.read_csv(ROOT / "data" / "faculty_final.csv", dtype=str, keep_default_na=False).openalex_author_ids for x in v.split(";"))
        a = a[a.openalex_work_id.isin(self.papers.index) & (a.is_our_inst != "True") & (a.institutions_detail != "") & ~a.author_id.isin(fac_ids)]
        rows = []
        for w, aid, nm, det in zip(a.openalex_work_id, a.author_id, a.author_name, a.institutions_detail):
            for part in det.split(";"):
                bits = part.split("|")
                if bits[0].strip():
                    rows.append((w, aid, nm.strip(), bits[0].strip()))
        return pd.DataFrame(rows, columns=["work", "author_id", "author", "partner"]).drop_duplicates()

    @cached_property
    def foreign(self):
        f = ST / "locality" / "foreign_partners.csv"
        return pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["your_inst", "partner_inst", "country", "shared_papers", "total_citations"])

    @cached_property
    def institute_summary(self):
        return pd.read_csv(ST / "insights" / "institute_comparison.csv") if (ST / "insights" / "institute_comparison.csv").exists() else pd.read_csv(ST / "institution_summary.csv")

    # ------------------------------------------------------------------ results files
    def json(self, rel):
        f = ST / rel
        return json.loads(f.read_text()) if f.exists() else None

    @cached_property
    def resilience(self):
        return self.json("resilience_results.json")

    @cached_property
    def link_results(self):
        return self.json("link_prediction_results.json")

    @cached_property
    def candidates(self):
        f = ST / "collab_candidates.csv"
        return pd.read_csv(f) if f.exists() else None

    # ------------------------------------------------------------------ collaboration model (lazy: ~10 s)
    @cached_property
    def collab(self):
        import collab_model as cm
        C = cm.Corpus()
        H = C.history(2025)
        mats = C.feature_matrices(H)
        models = pickle.load(open(OUT / "models" / "collab_models.pkl", "rb")) if (OUT / "models" / "collab_models.pkl").exists() else None
        return {"corpus": C, "H": H, "mats": mats, "models": models}


_STORE = None


def store():
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE
