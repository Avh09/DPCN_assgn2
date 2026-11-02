"""Allowlisted analysis tools. The assistant can only do what is in TOOLS: no free-form code, SQL or file access.

Every tool takes plain parameters, reads the real tables / graph, and returns a dict:
  ok, tool, summary (one line), data (structured, deterministic), evidence (records the user can open: faculty / paper /
  institute with DOI or OpenAlex links), coverage (what the data does and does not cover), figure (plotly Figure or None),
  needs_choice (set when a name is ambiguous: the UI asks the user to pick; nothing is silently guessed).
"""
import json
import math
import re
from functools import lru_cache
from urllib.parse import quote

import networkx as nx
import numpy as np
import pandas as pd

from . import entities as E
from . import viz
from .data import INSTS, OUT, SHORT, ST, store

COVERAGE_FAC = ("Verified faculty of MANIT Bhopal, NIT Jamshedpur and NIT Silchar (887 listed, 823 with papers), papers 2016-2026 "
                "(2026 is partial). Co-authorship links are between these faculty only; collaborators outside them are counted but not individually known.")
GLOSSARY = {
    "degree": "Number of distinct verified faculty a person has co-authored with. High = many collaborators; says nothing about paper quality.",
    "strength": "Total joint papers with other verified faculty (a repeated collaborator adds more than a one-off).",
    "betweenness": "Share of shortest collaboration paths between other pairs of faculty that pass through this person. High = a broker whose removal would stretch or break connections between groups.",
    "closeness": "How short, on average, the collaboration paths are from this person to everyone reachable. High = well placed to reach the whole network quickly.",
    "eigenvector": "Importance that comes from collaborating with other well-connected faculty (a collaborator of hubs scores high even with few links).",
    "clustering": "How often a person's collaborators also collaborate with each other (tight team = high).",
    "k_core": "The largest k such that the person belongs to a group where everyone has at least k collaborators inside the group. High = embedded in the dense core.",
    "participation": "P = 1 - sum over groups (links to group / all links)^2. 0 = all links in one group, close to 1 = links spread over many groups (an interdisciplinary connector).",
    "pagerank": "Importance of a paper inside the citation network of OUR corpus only, where a citation from an important paper counts more. It is not worldwide influence, and most corpus citations are author self-citations.",
    "fwci": "Field-weighted citation impact from OpenAlex: citations divided by the world average for papers of the same type, year and subfield (1 = average).",
    "h_index": "Largest h such that the person has h papers with at least h citations each. Here it is the 2016-2026 corpus h-index, NOT a career h-index.",
    "modularity": "How strongly the network divides into groups with many links inside and few between (0 = no structure, towards 1 = strong separation).",
    "louvain/leiden": "Algorithms that find groups ('communities') of faculty who collaborate mostly with each other.",
    "q1_share": "Q1 journal papers divided by journal papers that have a journal quartile. Conference ranks are separate.",
    "weighted_jaccard": "Research-topic similarity (0-1): sum of the smaller topic shares / sum of the larger shares over OpenAlex subfields. Computed only for top partners.",
}


def _res(tool, summary, data=None, evidence=None, coverage="", figure=None, ok=True, needs_choice=None, **extra):
    return {"ok": ok, "tool": tool, "summary": summary, "data": data or {}, "evidence": evidence or [], "coverage": coverage, "figure": figure, "needs_choice": needs_choice, **extra}


def _need(entity, query, cands, tool):
    return _res(tool, f"'{query}' matches several {entity}s", ok=False, needs_choice={"entity": entity, "query": query, "candidates": cands})


def _fac(query, tool, institute=None):
    r = E.resolve_faculty(query, institute)
    if not r["candidates"]:
        return None, _res(tool, f"No verified faculty matches '{query}'.", ok=False, coverage=COVERAGE_FAC)
    if r["ambiguous"]:
        return None, _need("faculty", query, r["candidates"], tool)
    return r["best"], None


def _flink(fid_):
    f = store().faculty.loc[fid_]
    return {"type": "faculty", "id": fid_, "label": f"{f.faculty_name} ({f.short_inst}, {f.department})",
            "url": f"https://openalex.org/authors/{str(f.openalex_author_ids).split(';')[0]}" if isinstance(f.openalex_author_ids, str) and f.openalex_author_ids else ""}


def _plink(wid):
    p = store().papers.loc[wid]
    return {"type": "paper", "id": wid, "label": f"{p.title} ({int(p.year)}, {p.journal_name})", "url": p.doi if str(p.doi).startswith("http") else f"https://openalex.org/{wid}"}


def _faculty_record(fid_):
    f = store().faculty.loc[fid_]
    g = lambda k, d=None: (None if pd.isna(f.get(k)) else f.get(k)) if k in f.index else d
    return {"id": fid_, "name": f.faculty_name, "institution": f.institution, "department": f.department, "designation": g("designation") or "", "status": f.faculty_status,
            "papers": int(f.papers), "journal_papers": int(f.journal_papers), "conference_papers": int(f.conference_papers), "citations": int(f.citations),
            "citations_per_paper": g("citations_per_paper"), "h_index_2016_2026": int(f.h_index), "q1_share_%": g("q1_share_%"), "top_journal": g("top_journal"),
            "years_active": f"{g('first_year')}-{g('last_year')}", "collaborators_in_faculty_network": int(g("degree", 0) or 0),
            "joint_papers_strength": int(g("strength_joint_papers", 0) or 0), "betweenness": g("betweenness"), "closeness": g("closeness"), "eigenvector": g("eigenvector"),
            "k_core": g("k_core"), "community_leiden": g("community_leiden"), "participation_dept": g("participation_dept"), "mean_fwci": g("mean_fwci"),
            "distinct_coauthors_all": g("distinct_coauthors_all"), "rank_in_institute": {"papers": g("rank_papers"), "citations": g("rank_citations"), "h_index": g("rank_h_index")}}


# ============================================================================ faculty tools
def find_faculty(query, institute=None):
    r = E.resolve_faculty(query, institute)
    return _res("find_faculty", f"{len(r['candidates'])} candidate(s) for '{query}'", {"candidates": r["candidates"], "ambiguous": r["ambiguous"]},
                [_flink(c["id"]) for c in r["candidates"][:5]], COVERAGE_FAC)


def get_faculty_profile(faculty):
    fid_, err = _fac(faculty, "get_faculty_profile")
    if err:
        return err
    S = store()
    rec = _faculty_record(fid_)
    fp = S.fac_papers[S.fac_papers.id == fid_]
    top = fp.sort_values("citations", ascending=False).head(5)
    by_year = fp.groupby("year").size().to_dict()
    venues = fp[fp.type == "conference"].journal_name.value_counts().head(3).to_dict()
    jv = fp[fp.type == "journal"].journal_name.value_counts().head(3).to_dict()
    G = S.graph
    nb = sorted(G[fid_].items(), key=lambda kv: -kv[1]["weight"])[:8]
    rec.update({"papers_per_year": by_year, "top_journals": jv, "top_conferences_or_series": venues,
                "top_cited_papers": [{"title": r.title, "year": int(r.year), "citations": int(r.citations), "venue": r.journal_name} for r in top.itertuples()],
                "top_collaborators": [{"name": G.nodes[n]["name"], "institution": G.nodes[n]["institution"], "joint_papers": d["weight"]} for n, d in nb],
                "fields": fp.field.value_counts().head(5).to_dict()})
    return _res("get_faculty_profile", f"{rec['name']} ({SHORT[rec['institution']]}, {rec['department']}): {rec['papers']} papers, {rec['citations']} citations, 2016-2026 h-index {rec['h_index_2016_2026']}",
                rec, [_flink(fid_)] + [_plink(w) for w in top.openalex_work_id], COVERAGE_FAC + " h-index is for the 2016-2026 corpus, not a career h-index.")


def compare_faculty(a, b):
    ia, e = _fac(a, "compare_faculty")
    if e:
        return e
    ib, e = _fac(b, "compare_faculty")
    if e:
        return e
    A, B = _faculty_record(ia), _faculty_record(ib)
    keys = ["papers", "journal_papers", "conference_papers", "citations", "citations_per_paper", "h_index_2016_2026", "q1_share_%", "mean_fwci", "collaborators_in_faculty_network", "betweenness", "k_core"]
    fig = viz.grouped_bar(["papers", "citations / 10", "h-index", "collaborators"], {A["name"]: [A["papers"], A["citations"] / 10, A["h_index_2016_2026"], A["collaborators_in_faculty_network"]],
                                                                               B["name"]: [B["papers"], B["citations"] / 10, B["h_index_2016_2026"], B["collaborators_in_faculty_network"]]}, "Comparison")
    return _res("compare_faculty", f"{A['name']} vs {B['name']}", {"a": {k: A[k] for k in keys + ["name", "institution", "department"]}, "b": {k: B[k] for k in keys + ["name", "institution", "department"]}},
                [_flink(ia), _flink(ib)], COVERAGE_FAC, fig)


# ============================================================================ collaboration
def _path(G, a, b):
    try:
        return nx.shortest_path(G, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def _topic_similarity(ia, ib):
    S = store()
    C = S.collab["corpus"]
    H = S.collab["H"]
    M = S.collab["mats"]
    i, j = C.idx.get(ia), C.idx.get(ib)
    if i is None or j is None:
        return None
    return {"topic_cosine": round(float(M["topic_cosine"][i, j]), 3), "topic_weighted_jaccard": round(float(M["topic_weighted_jaccard"][i, j]), 3),
            "shared_subfields": int(M["shared_subfields"][i, j]), "field_cosine": round(float(M["field_cosine"][i, j]), 3),
            "top_shared_subfields": C.explain(H, M, i, j)["shared_subfields"]}


def _model_score(ia, ib):
    """Model output for a pair with no joint paper up to 2025, or None when models are not available."""
    S = store()
    cm = S.collab
    if not cm["models"]:
        return None
    import collab_model as cmod
    C, H, M = cm["corpus"], cm["H"], cm["mats"]
    i, j = C.idx.get(ia), C.idx.get(ib)
    if i is None or j is None or H["A"][i, j] > 0:
        return None
    df = C.pair_frame(H, M, [(min(i, j), max(i, j))])
    fe = cmod.NEW_LINK_FEATURES
    lr = cm["models"]["new"]["models"]["logistic regression"]
    rf = cm["models"]["new"]["models"]["random forest"]
    p_lr, p_rf = float(lr.predict_proba(df[fe])[:, 1][0]), float(rf.predict_proba(df[fe])[:, 1][0])
    # percentile among all candidate pairs, using the stored ranking file when possible
    cand = S.candidates
    pct = None
    # contribution of each feature to the LR log-odds (standardised value x coefficient)
    pipe = lr
    scaler, clf = pipe[0], pipe[-1]
    z = scaler.transform(df[fe])[0]
    contrib = sorted(zip(fe, z * clf.coef_[0]), key=lambda t: -abs(t[1]))[:6]
    return {"score_logistic": round(p_lr, 4), "score_random_forest": round(p_rf, 4), "feature_contributions_logistic": [(f, round(float(c), 2)) for f, c in contrib],
            "ranking_only": True, "note": "ranking scores; calibration on the 2023-2025 test window failed for new-link prediction, so these are NOT probabilities"}


def assess_collaboration(a, b):
    ia, e = _fac(a, "assess_collaboration")
    if e:
        return e
    ib, e = _fac(b, "assess_collaboration")
    if e:
        return e
    if ia == ib:
        return _res("assess_collaboration", "Both names resolve to the same person.", ok=False)
    S = store()
    G = S.graph
    A, B = _faculty_record(ia), _faculty_record(ib)
    joint = S.pair_papers.get(frozenset((ia, ib)), [])
    common = sorted(set(G[ia]) & set(G[ib]))
    path = _path(G, ia, ib)
    nbrs_a, nbrs_b = set(G[ia]), set(G[ib])
    union = nbrs_a | nbrs_b
    jac = round(len(nbrs_a & nbrs_b) / len(union), 3) if union else 0.0
    aa = round(sum(1 / math.log(G.degree(z)) for z in common if G.degree(z) > 1), 3)
    same_dept = (A["institution"] == B["institution"]) and (A["department"] == B["department"])
    topic = _topic_similarity(ia, ib)
    model = _model_score(ia, ib)
    recent = lambda i_: [{"title": r.title, "year": int(r.year), "venue": r.journal_name} for r in S.fac_papers[S.fac_papers.id == i_].sort_values("year", ascending=False).head(3).itertuples()]
    if joint:
        status = "existing collaboration"
    elif path and len(path) == 3 and topic and topic["topic_cosine"] >= .5:
        status = "no joint paper yet; short path and clear topic overlap"
    elif path and len(path) <= 4:
        status = "no joint paper yet; connected through the collaboration network"
    else:
        status = "no joint paper yet; weakly connected" if path else "no joint paper yet; not connected in the faculty network"
    nodes = {ia, ib, *common, *(path or [])}
    for z in list(common)[:6]:
        nodes |= {n for n in G[z] if n in (nbrs_a | nbrs_b)}
    fig = viz.network_figure(nodes, center=[ia, ib], path=path, highlight=common, extra_edges=[] if joint else [(ia, ib)],
                             title=f"{A['name']} and {B['name']}: shortest path and common collaborators")
    data = {"a": {k: A[k] for k in ("name", "institution", "department", "papers", "citations", "h_index_2016_2026", "collaborators_in_faculty_network")},
            "b": {k: B[k] for k in ("name", "institution", "department", "papers", "citations", "h_index_2016_2026", "collaborators_in_faculty_network")},
            "relationship": status, "joint_papers": len(joint),
            "joint_paper_list": [{"title": S.papers.at[w, "title"], "year": int(S.papers.at[w, "year"]), "venue": S.papers.at[w, "journal_name"]} for w in joint[:8]],
            "shortest_path_hops": None if path is None else len(path) - 1, "shortest_path": None if path is None else [G.nodes[n]["name"] for n in path],
            "common_collaborators": [{"name": G.nodes[n]["name"], "institution": G.nodes[n]["institution"], "joint_with_a": G[ia][n]["weight"], "joint_with_b": G[ib][n]["weight"]} for n in common],
            "network_similarity": {"jaccard_of_collaborators": jac, "adamic_adar": aa}, "same_department": same_dept, "same_institute": A["institution"] == B["institution"],
            "research_topic_similarity": topic, "recent_papers_a": recent(ia), "recent_papers_b": recent(ib), "model": model,
            "betweenness_a": A["betweenness"], "betweenness_b": B["betweenness"]}
    ev = [_flink(ia), _flink(ib)] + [_flink(n) for n in common[:5]] + [_plink(w) for w in joint[:5]]
    cov = COVERAGE_FAC + " Topic similarity uses OpenAlex subfields of each person's 2016-2025 papers. " + ("The model is a ranking score trained on 2016-2022 history and tested on 2023-2025; it is not a probability." if model else "")
    return _res("assess_collaboration", f"{A['name']} - {B['name']}: {status}", data, ev, cov, fig)


def get_collaboration_history(a, b):
    r = assess_collaboration(a, b)
    if not r["ok"]:
        return r
    d = r["data"]
    return _res("get_collaboration_history", f"{d['a']['name']} and {d['b']['name']}: {d['joint_papers']} joint paper(s)", d, r["evidence"], r["coverage"], None)


def get_shortest_collaboration_path(a, b):
    r = assess_collaboration(a, b)
    if not r["ok"]:
        return r
    d = r["data"]
    s = (f"shortest path {d['shortest_path_hops']} hop(s): " + " -> ".join(d["shortest_path"])) if d["shortest_path"] else "no path in the verified-faculty network"
    return _res("get_shortest_collaboration_path", s, d, r["evidence"], r["coverage"], r["figure"])


def get_common_collaborators(a, b):
    r = assess_collaboration(a, b)
    if not r["ok"]:
        return r
    d = r["data"]
    return _res("get_common_collaborators", f"{len(d['common_collaborators'])} common collaborator(s)", d, r["evidence"], r["coverage"], r["figure"])


def get_ego_network(faculty, radius=1):
    fid_, err = _fac(faculty, "get_ego_network")
    if err:
        return err
    G = store().graph
    radius = int(min(max(radius, 1), 2))
    ego = nx.ego_graph(G, fid_, radius=radius)
    nodes = list(ego.nodes)
    if len(nodes) > 80:
        keep = sorted(nodes, key=lambda n: -G[fid_][n]["weight"] if n in G[fid_] else 0)[:80]
        nodes = list(dict.fromkeys([fid_] + keep))
    fig = viz.network_figure(nodes, center=[fid_], highlight=list(G[fid_])[:0], title=f"Collaboration network of {G.nodes[fid_]['name']} (radius {radius})")
    nb = [{"name": G.nodes[n]["name"], "institution": G.nodes[n]["institution"], "department": G.nodes[n]["department"], "joint_papers": G[fid_][n]["weight"]} for n in sorted(G[fid_], key=lambda n: -G[fid_][n]["weight"])]
    return _res("get_ego_network", f"{G.nodes[fid_]['name']} has {len(nb)} verified-faculty collaborators", {"collaborators": nb[:25], "total_collaborators": len(nb), "nodes_in_view": len(nodes)},
                [_flink(fid_)] + [_flink(n) for n in list(G[fid_])[:4]], COVERAGE_FAC, fig)


def _scope_filter(df, scope, me_inst):
    if scope == "same_institute":
        return df[df.institution == me_inst]
    if scope == "other_nits":
        return df[df.institution != me_inst]
    return df


def recommend_collaborators(faculty, k=5, scope="any", field=None, different_department=False, exclude_existing=True):
    """Ranks faculty who have not co-authored with `faculty` using the validated link-prediction models plus topic evidence."""
    fid_, err = _fac(faculty, "recommend_collaborators")
    if err:
        return err
    S = store()
    cm = S.collab
    C, H, M = cm["corpus"], cm["H"], cm["mats"]
    i = C.idx.get(fid_)
    if i is None:
        return _res("recommend_collaborators", "This person has no papers in the model's history.", ok=False)
    import collab_model as cmod
    act = set(C.active(H))
    me = S.faculty.loc[fid_]
    cands = [j for j in act if j != i and (not exclude_existing or H["A"][i, j] == 0)]
    rows = []
    for j in cands:
        key = C.keys[j]
        f = S.faculty.loc[key]
        if scope == "same_institute" and f.institution != me.institution:
            continue
        if scope == "other_nits" and f.institution == me.institution:
            continue
        if different_department and f.department == me.department and f.institution == me.institution:
            continue
        rows.append(j)
    if not rows:
        return _res("recommend_collaborators", "No candidates match these filters.", ok=False)
    df = C.pair_frame(H, M, [(min(i, j), max(i, j)) for j in rows])
    fe = cmod.NEW_LINK_FEATURES
    models = cm["models"]["new"]["models"] if cm["models"] else None
    if models:
        df["score"] = (models["random forest"].predict_proba(df[fe])[:, 1].argsort().argsort() + models["logistic regression"].predict_proba(df[fe])[:, 1].argsort().argsort()) / (2 * len(df))
        basis = "validated link-prediction ranking (logistic regression + random forest, temporal test 2023-2025)"
    else:
        df["score"] = 0.5 * df.topic_cosine.rank(pct=True) + 0.3 * df.adamic_adar.rank(pct=True) + 0.2 * (1 / df.hop_distance).rank(pct=True)
        basis = "transparent heuristic (topic similarity, Adamic-Adar, path distance): the trained model is not available"
    df["other"] = [rows[n] for n in range(len(rows))]
    if field:
        fld = E.resolve_field(field)["best"]
        if fld:
            have = set(S.fac_papers[(S.fac_papers.field == fld)].id) if fld in set(S.papers.field) else set(S.fac_papers[S.fac_papers.openalex_work_id.isin(S.papers[S.papers.subfield == fld].index)].id)
            df = df[[C.keys[j] in have for j in df.other]]
    top = df.sort_values("score", ascending=False).head(int(min(max(k, 1), 15)))
    out = []
    for r in top.itertuples():
        j = r.other
        key = C.keys[j]
        f = S.faculty.loc[key]
        ex = C.explain(H, M, i, j)
        out.append({"name": f.faculty_name, "institution": f.institution, "department": f.department, "papers": int(f.papers), "h_index": int(f.h_index), "rank_score": round(float(r.score), 3),
                    "hops": ex["hops"], "common_collaborators": ex["common_collaborators"], "shared_subfields": ex["shared_subfields"], "topic_cosine": round(float(r.topic_cosine), 2),
                    "same_department": bool(f.department == me.department and f.institution == me.institution)})
    ids = [C.keys[r.other] for r in top.itertuples()]
    fig = viz.network_figure([fid_] + ids + [n for r in out for n in []], center=[fid_], highlight=ids, extra_edges=[(fid_, n) for n in ids],
                             title=f"Suggested collaborators for {me.faculty_name} (dashed = no joint paper yet)")
    return _res("recommend_collaborators", f"{len(out)} suggestion(s) for {me.faculty_name}", {"suggestions": out, "basis": basis, "filters": {"scope": scope, "field": field, "different_department": different_department}},
                [_flink(fid_)] + [_flink(n) for n in ids], COVERAGE_FAC + " Scores rank pairs; they are not probabilities and do not predict that a collaboration will happen.", fig)


def assess_institute_collaboration(faculty, institute):
    fid_, err = _fac(faculty, "assess_institute_collaboration")
    if err:
        return err
    ri = E.resolve_institute(institute)
    if ri["ambiguous"]:
        return _need("institute", institute, ri["candidates"], "assess_institute_collaboration")
    if not ri["canonical"]:
        return _res("assess_institute_collaboration", f"No institute matches '{institute}' in the data.", ok=False, coverage="Partner institutes known from the co-authorship data of the three NITs.")
    inst = ri["canonical"]
    S = store()
    me = S.faculty.loc[fid_]
    lp = pd.read_csv(ST / "locality" / "faculty_partners.csv")
    mine = lp[(lp.institution == me.institution) & (lp.faculty_name == me.faculty_name) & (lp.partner_inst == inst)]
    inst_level = S.partners[(S.partners.your_inst == me.institution) & (S.partners.partner_inst == inst)]
    all_links = S.partners[S.partners.partner_inst == inst]
    data = {"researcher": me.faculty_name, "institute": inst, "kind": ri["kind"], "existing_joint_papers_with_this_researcher": int(mine.joint_papers.sum()) if len(mine) else 0}
    ev = [_flink(fid_)]
    cov = COVERAGE_FAC
    if ri["kind"] == "ours":
        if inst == me.institution:
            return _res("assess_institute_collaboration", f"{me.faculty_name} already belongs to {inst}.", ok=False)
        recs = recommend_collaborators(fid_, k=5, scope="other_nits") if inst != me.institution else None
        sub = recs["data"]["suggestions"] if recs and recs["ok"] else []
        sub = [s for s in sub if s["institution"] == inst]
        G = S.graph
        links = [{"name": G.nodes[n]["name"], "joint_papers": G[fid_][n]["weight"]} for n in G[fid_] if G.nodes[n]["institution"] == inst]
        data.update({"existing_links_to_faculty_there": links, "suggested_collaborators_there": sub})
        ev += [_flink(n) for n in G[fid_] if G.nodes[n]["institution"] == inst][:5]
        return _res("assess_institute_collaboration", f"{me.faculty_name} and {inst}: {len(links)} verified-faculty collaborator(s) there", data, ev, cov, recs["figure"] if recs and recs["ok"] else None)
    nan_to_none = lambda recs: [{k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()} for r in recs]
    data["institute_level_links_with_our_institutes"] = nan_to_none(all_links[["your_inst", "shared_papers", "total_citations", "first_year", "last_year", "faculty_involved", "top_faculty", "weighted_jaccard", "locality"]].to_dict("records"))
    data["links_with_researchers_own_institute"] = nan_to_none(inst_level[["shared_papers", "total_citations", "top_faculty", "weighted_jaccard"]].to_dict("records"))
    data["topic_similarity_note"] = "weighted_jaccard is null where research-topic similarity was not calculated (only the top 25 partners of each institute were profiled); null is NOT zero similarity"
    ext = pd.read_csv(ST / "locality" / "top_external_authors.csv")
    ea = ext[ext.iloc[:, :].astype(str).apply(lambda r: inst.lower() in " ".join(r).lower(), axis=1)] if len(ext) else ext
    data["external_authors_there_known_from_joint_papers"] = ea.head(8).to_dict("records") if len(ea) else []
    cov += (" Faculty lists and research profiles of outside institutes are NOT in this dataset: only the joint papers with the faculty of the three institutes are known. No outside collaborator is suggested "
            "beyond people who actually appear on joint papers with the faculty of the three institutes.")
    return _res("assess_institute_collaboration", f"{me.faculty_name} and {inst}: {data['existing_joint_papers_with_this_researcher']} joint paper(s) with this researcher; "
                f"{len(all_links)} link(s) between {inst} and the three institutes", data, ev, cov)



# ============================================================================ partner institutes (outside the three)
def _clean(df):
    return [{k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()} for r in df.to_dict("records")]


def _outside_people(partner_names, mine=None, limit=12):
    """Named co-authors from the outside institute(s) on joint papers with the faculty of the three institutes: how many papers, with whom. OpenAlex gives no job title."""
    S = store()
    x = S.ext_people
    x = x[x.partner.isin(partner_names)]
    if x.empty:
        return []
    fp = S.fac_papers[S.fac_papers.openalex_work_id.isin(x.work)]
    if mine:
        keep = set(fp[fp.institution == mine].openalex_work_id)
        x = x[x.work.isin(keep)]
    by_work = fp.groupby("openalex_work_id").apply(lambda g: sorted(set(zip(g.faculty_name, g.institution.map(SHORT)))), include_groups=False).to_dict()
    pap = S.papers
    out = []
    for (aid, name), g in x.groupby(["author_id", "author"]):
        ws = sorted(set(g.work), key=lambda w: -int(pap.at[w, "citations"]))
        ours = sorted({f"{n} ({i})" for w in ws for n, i in by_work.get(w, [])})
        yrs = [int(pap.at[w, "year"]) for w in ws]
        out.append({"name": name, "institute": ", ".join(sorted(set(g.partner))[:2]), "joint_papers": len(ws), "years": f"{min(yrs)}-{max(yrs)}",
                    "our_institutes": sorted({i for w in ws for _, i in by_work.get(w, [])}), "worked_with": ours[:5], "example_paper": f"{pap.at[ws[0], 'title']} ({pap.at[ws[0], 'year']})"})
    out.sort(key=lambda r: -r["joint_papers"])
    return out[:limit]


def partner_institutes(query, institute=None):
    """Joint work between the three institutes and one outside institute (e.g. 'IIITH', 'Jadavpur University') or a whole type ('IIT', 'IIIT', 'CSIR')."""
    S = store()
    q = query.strip()
    low = re.sub(r"[\s\-]+", " ", q.lower()).strip()
    mine = None
    if institute:
        ri = E.resolve_institute(institute)
        mine = ri["canonical"] if ri.get("canonical") in INSTS else None
    P = S.partners
    clusters = {str(c): str(c).lower() for c in S.partners.partner_cluster.dropna().unique()}
    cl = next((c for c, l in clusters.items() if low in (l, l + "s", l + " institutes", l + " institute")), None)
    cov = ("Partner institutes are known only from joint papers with the verified faculty (2016-2026). The people named are the outside co-authors on those papers "
           "(OpenAlex gives no job title, so a name may be a professor, a student or a staff member); the institute's full faculty list is not in this dataset.")
    if cl:
        rows = P[P.partner_cluster == cl]
        by = [{"institute": i, "partner_institutes": int(len(g)), "joint_paper_links": int(g.shared_papers.sum()), "top_partners": [
              {"partner": r.partner_inst, "joint_papers": int(r.shared_papers), "top_faculty": r.top_faculty} for r in g.sort_values("shared_papers", ascending=False).head(5).itertuples()]}
              for i, g in rows.groupby("your_inst")]
        return _res("partner_institutes", f"{cl} partners: {int(len(rows))} institute links, {int(rows.shared_papers.sum())} joint-paper links in total",
                    {"type": cl, "by_our_institute": by, "people": _outside_people(set(rows.partner_inst), None, 10)}, [], cov)
    r = E.resolve_institute(q)
    if r["ambiguous"]:
        return _need("institute", query, r["candidates"], "partner_institutes")
    if not r["canonical"]:
        return _res("partner_institutes", f"No partner institute or institute type matches '{query}'.", ok=False, coverage=cov)
    canon = r["canonical"]
    if r["kind"] == "ours":
        return _res("partner_institutes", f"{canon} is one of the three institutes; use institute_profile or strongest_pairs for links between the three institutes.", ok=False)
    rows = P[P.partner_inst == canon]
    fo = S.foreign[S.foreign.partner_inst == canon]
    cols = ["your_inst", "shared_papers", "total_citations", "first_year", "last_year", "faculty_involved", "top_faculty", "cites_from_partner", "cites_to_partner", "locality", "partner_cluster", "state"]
    links = _clean(rows[[c for c in cols if c in rows.columns]]) if len(rows) else []
    if not len(rows) and not len(fo):
        return _res("partner_institutes", f"No joint paper between {canon} and {mine or 'the three institutes'} in the data.", {"partner": canon, "links": []}, [], cov)
    tot = int(rows.shared_papers.sum()) if len(rows) else int(fo.shared_papers.sum())
    data = {"partner": canon, "asked_about_our_institute": mine, "people": _outside_people({canon}, None, 12), "links": links if len(rows) else _clean(fo[[c for c in ["your_inst", "shared_papers", "total_citations", "country"] if c in fo.columns]])}
    return _res("partner_institutes", f"{canon}: {tot} joint-paper link(s) with {len(data['links'])} of the institute(s)", data, [], cov)


# ============================================================================ institutes
def compare_institutes(institutes=None):
    S = store()
    d = S.institute_summary
    if institutes:
        want = []
        for t in institutes:
            r = E.resolve_institute(t)
            if r["canonical"] in INSTS:
                want.append(r["canonical"])
        if want:
            d = d[d.institution.isin(want)]
    cols = [c for c in ["institution", "papers", "research_active_faculty", "papers_per_active_faculty", "citations", "citations_per_paper", "median_citations_per_paper", "institute_h_index",
                        "journal_Q1_share_%", "journal_Q1_papers", "journal_ranked_papers", "fwci_mean", "fwci_median", "top10pct_share_%", "growth_2016_2020_to_2021_2025_%", "faculty_h_median",
                        "citation_gini_faculty", "review_share_of_citations_%"] if c in d.columns]
    d = d[cols]
    hs = S.json("insights/h_index_size_test.json")
    need = ["papers_per_active_faculty", "citations_per_paper", "journal_Q1_share_%", "faculty_h_median"]
    fig = viz.grouped_bar(["papers / faculty", "citations / paper", "Q1 share % (ranked journals)", "median faculty h"],
                          {r["institution"]: [float(r[c]) for c in need] for r in d.to_dict("records") if all(c in r for c in need)}, "Institute comparison (normalised measures)") \
        if all(c in d.columns for c in need) else None
    return _res("compare_institutes", "Institute comparison", {"table": d.to_dict("records"), "h_index_at_equal_size": hs["institutes"] if hs else None,
                                                                "note": "Q1 share = Q1 journal papers / journal papers with a quartile; FWCI is world-normalised (1 = average); growth compares 2016-2020 with 2021-2025."},
                [{"type": "institute", "id": i, "label": i, "url": ""} for i in d.institution], COVERAGE_FAC, fig)


def institute_profile(institute):
    r = E.resolve_institute(institute)
    if r["canonical"] not in INSTS:
        return _res("institute_profile", "Detailed profiles exist only for MANIT Bhopal, NIT Jamshedpur and NIT Silchar.", ok=False)
    S = store()
    inst = r["canonical"]
    d = S.institute_summary
    row = d[d.institution == inst].iloc[0].to_dict()
    pa = S.partners[S.partners.your_inst == inst].sort_values("shared_papers", ascending=False)
    row["top_indian_partners"] = pa.head(5)[["partner_inst", "shared_papers", "partner_cluster"]].to_dict("records")
    fo = S.foreign[S.foreign.your_inst == inst].sort_values("shared_papers", ascending=False).head(5)
    row["top_foreign_partners"] = fo[["partner_inst", "country", "shared_papers"]].to_dict("records")
    row["distinct_indian_partners"] = int(len(pa))
    row["distinct_foreign_partners"] = int(len(S.foreign[S.foreign.your_inst == inst]))
    fac = S.faculty[S.faculty.institution == inst]
    row["departments"] = fac.groupby("department").agg(faculty=("id", "count"), papers=("papers", "sum"), citations=("citations", "sum")).sort_values("papers", ascending=False).head(8).reset_index().to_dict("records")
    return _res("institute_profile", f"{inst}: {int(row['papers'])} papers, {int(row['citations'])} citations", row, [{"type": "institute", "id": inst, "label": inst, "url": ""}], COVERAGE_FAC)


# ============================================================================ rankings and patterns
METRICS = {"papers": "papers", "citations": "citations", "h_index": "h_index", "betweenness": "betweenness", "degree": "degree", "collaborators": "degree", "closeness": "closeness",
           "eigenvector": "eigenvector", "q1_share": "q1_share_%", "citations_per_paper": "citations_per_paper", "fwci": "mean_fwci", "participation": "participation_dept", "k_core": "k_core",
           "q1_papers": "q1_papers"}


def top_faculty(metric="citations", institute=None, department=None, n=10, status=None, min_papers=1):
    S = store()
    col = METRICS.get(metric.lower().replace(" ", "_"))
    if col is None or col not in S.faculty.columns:
        return _res("top_faculty", f"Unknown metric '{metric}'. Available: {sorted(METRICS)}", ok=False)
    f = S.faculty[S.faculty.papers >= min_papers]
    if institute:
        ri = E.resolve_institute(institute)
        if ri["canonical"] in INSTS:
            f = f[f.institution == ri["canonical"]]
    if department:
        rd = E.resolve_department(department, ri["canonical"] if institute and ri["canonical"] in INSTS else None)
        if rd["best"]:
            f = f[f.department == rd["best"]]
    if status:
        f = f[f.faculty_status == status]
    top = f.sort_values(col, ascending=False).head(int(min(max(n, 1), 25)))
    rows = [{"name": top.iloc[k].faculty_name, "institution": top.iloc[k].institution, "department": top.iloc[k].department,
             metric: (None if pd.isna(top.iloc[k][col]) else float(top.iloc[k][col])), "papers": int(top.iloc[k].papers), "citations": int(top.iloc[k].citations)}
            for k in range(len(top))]
    fig = viz.bar_figure([f"{r['name']} ({SHORT[r['institution']]})" for r in rows], [r[metric] for r in rows], f"Top faculty by {metric}", metric)
    return _res("top_faculty", f"Top {len(rows)} by {metric}", {"rows": rows, "filters": {"institute": institute, "department": department, "status": status}},
                [_flink(i) for i in top.id], COVERAGE_FAC, fig)


def faculty_pattern(pattern, institute=None, n=10):
    """Named patterns: high_betweenness_low_degree, high_citations_few_collaborators, connected_but_low_citations, interdisciplinary_bridges."""
    S = store()
    f = S.faculty[S.faculty.papers >= 3].copy()
    if institute:
        ri = E.resolve_institute(institute)
        if ri["canonical"] in INSTS:
            f = f[f.institution == ri["canonical"]]
    q = lambda c, p: f[c].quantile(p)
    if pattern == "high_betweenness_low_degree":
        sel = f[(f.betweenness >= q("betweenness", .9)) & (f.degree <= q("degree", .5))]
        desc = "betweenness in the top 10% but degree at or below the median: brokers with few collaborators"
        sel = sel.sort_values("betweenness", ascending=False)
    elif pattern == "high_citations_few_collaborators":
        sel = f[(f.citations >= q("citations", .9)) & (f.degree <= q("degree", .5))].sort_values("citations", ascending=False)
        desc = "citations in the top 10% but at most the median number of verified-faculty collaborators"
    elif pattern == "connected_but_low_citations":
        sel = f[(f.degree >= q("degree", .9)) & (f.citations <= q("citations", .5))].sort_values("degree", ascending=False)
        desc = "degree in the top 10% but citations at or below the median"
    elif pattern == "interdisciplinary_bridges":
        f = f[f.degree >= 3]
        sel = f[(f.participation_dept >= q("participation_dept", .85))].sort_values("betweenness", ascending=False)
        desc = "participation coefficient across departments in the top 15% (degree >= 3), ordered by betweenness"
    else:
        return _res("faculty_pattern", f"Unknown pattern. Options: high_betweenness_low_degree, high_citations_few_collaborators, connected_but_low_citations, interdisciplinary_bridges", ok=False)
    sel = sel.head(int(min(max(n, 1), 20)))
    rows = [{"name": r.faculty_name, "institution": r.institution, "department": r.department, "papers": int(r.papers), "citations": int(r.citations), "degree": int(r.degree),
             "betweenness": round(float(r.betweenness), 4), "participation_dept": None if pd.isna(r.participation_dept) else float(r.participation_dept)} for r in sel.itertuples()]
    return _res("faculty_pattern", f"{len(rows)} faculty match: {desc}", {"rows": rows, "definition": desc, "thresholds_computed_over": f"{len(f)} faculty with at least 3 papers"},
                [_flink(i) for i in sel.id], COVERAGE_FAC, viz.scatter_figure(f, "degree", "betweenness", hover="faculty_name", title="Collaborators vs betweenness (all faculty with 3+ papers)"))


def network_overview(scope="all"):
    S = store()
    fn = S.json("faculty_network_results.json")
    ex = S.json("faculty_network_extra.json")
    key = "whole_network" if scope in ("all", None) else (E.resolve_institute(scope)["canonical"] or "whole_network")
    data = {"summary": fn.get(key), "structure": next((x for x in ex if (x["scope"] == "all three institutes" if key == "whole_network" else x["scope"] == key)), None)}
    return _res("network_overview", f"Faculty collaboration network: {key}", data, [], COVERAGE_FAC + " Faculty with no links here may still collaborate with students and external authors.")


def resilience_summary(scope="all"):
    S = store()
    R = S.resilience
    if not R:
        return _res("resilience_summary", "Resilience results have not been generated (run resilience.py).", ok=False)
    key = "all" if scope in ("all", None) else (E.resolve_institute(scope)["canonical"] or "all")
    s = R["scopes"][key]
    crit = pd.read_csv(ST / "critical_faculty.csv")
    crit = crit[crit.scope == key].head(8)
    data = {"scope": key, "nodes": s["nodes"], "edges": s["edges"], "isolated": s["isolated"], "intact_lcc_fraction": s["lcc_fraction_0"], "summary": s["summary"],
            "most_critical_single_removals": crit[["faculty_name", "institution", "degree", "betweenness", "articulation_point", "lcc_change_pp", "efficiency_loss_%"]].to_dict("records"),
            "interpretation_note": "structural simulation: removing a node does not mean a faculty member leaves"}
    return _res("resilience_summary", f"Resilience of the {key} faculty network", data, [_flink(f"{r.institution}|{r.faculty_name}") for r in crit.itertuples()][:4], COVERAGE_FAC, viz.resilience_figure(key, "lcc"))


def simulate_node_removal(faculty_list, scope="all"):
    """Remove the named faculty and report the effect on connectivity (largest component, components, efficiency)."""
    ids = []
    for q in faculty_list:
        i, err = _fac(q, "simulate_node_removal")
        if err:
            return err
        ids.append(i)
    S = store()
    G = S.graph.copy()
    before = _net_stats(G)
    G.remove_nodes_from(ids)
    after = _net_stats(G, n0=before["nodes"])
    keep = [n for n in S.graph.nodes if any(n in S.graph[i] for i in ids) or n in ids]
    fig = viz.network_figure(keep[:100], center=ids, title="Neighbourhood of the removed faculty (removed = large dark-outlined nodes)")
    names = [S.graph.nodes[i]["name"] for i in ids]
    return _res("simulate_node_removal", f"Removing {', '.join(names)}: largest component {before['lcc_fraction']:.3f} -> {after['lcc_fraction']:.3f}", {"before": before, "after": after, "removed": names,
                "note": "structural simulation only"}, [_flink(i) for i in ids], COVERAGE_FAC, fig)


def _net_stats(G, n0=None):
    import igraph as ig
    nodes = list(G.nodes)
    idx = {n: k for k, n in enumerate(nodes)}
    g = ig.Graph(n=len(nodes), edges=[(idx[a], idx[b]) for a, b in G.edges()])
    n0 = n0 or len(nodes)
    comps = g.connected_components().sizes()
    d = np.array(g.distances(), dtype=float)
    np.fill_diagonal(d, np.inf)
    eff = float((1 / d).sum()) / (n0 * (n0 - 1))
    return {"nodes": n0 if n0 else len(nodes), "nodes_remaining": len(nodes), "lcc_fraction": max(comps) / n0, "components": len(comps), "global_efficiency": round(eff, 5)}


def filter_network_by_weight(min_joint_papers=3, scope="all"):
    S = store()
    G = S.graph
    H = nx.Graph()
    H.add_nodes_from(G.nodes(data=True))
    H.add_edges_from((a, b, d) for a, b, d in G.edges(data=True) if d["weight"] >= min_joint_papers)
    if scope not in ("all", None):
        inst = E.resolve_institute(scope)["canonical"]
        H = H.subgraph([n for n in H if H.nodes[n]["institution"] == inst]).copy()
    comps = sorted(nx.connected_components(H), key=len, reverse=True)
    nonzero = [c for c in comps if len(c) > 1]
    top = nx.Graph(H.subgraph(nonzero[0])) if nonzero else H
    data = {"min_joint_papers": min_joint_papers, "nodes": H.number_of_nodes(), "edges": H.number_of_edges(), "isolated_nodes": sum(1 for n in H if H.degree(n) == 0),
            "components_with_links": len(nonzero), "largest_component": len(nonzero[0]) if nonzero else 0, "density": round(nx.density(H), 5),
            "avg_clustering": round(nx.average_clustering(H), 4), "strongest_pairs": [{"a": H.nodes[a]["name"], "b": H.nodes[b]["name"], "joint_papers": d["weight"]}
                                                                                  for a, b, d in sorted(H.edges(data=True), key=lambda e: -e[2]["weight"])[:8]]}
    fig = viz.network_figure(list(top.nodes)[:120], title=f"Largest group when only collaborations with at least {min_joint_papers} joint papers are kept") if nonzero else None
    return _res("filter_network_by_weight", f"Keeping pairs with >= {min_joint_papers} joint papers: {data['edges']} links, largest group {data['largest_component']}", data, [], COVERAGE_FAC, fig)


def bridge_researchers(scope="all", n=10):
    return top_faculty("betweenness", None if scope in ("all", None) else scope, n=n)


def strongest_pairs(kind="any", n=10):
    S = store()
    G = S.graph
    rows = []
    for a, b, d in G.edges(data=True):
        same = G.nodes[a]["institution"] == G.nodes[b]["institution"]
        if kind == "cross_institute" and same or kind == "within_institute" and not same:
            continue
        rows.append((d["weight"], a, b, d["first_year"], d["last_year"]))
    rows.sort(reverse=True)
    out = [{"a": G.nodes[a]["name"], "institution_a": G.nodes[a]["institution"], "b": G.nodes[b]["name"], "institution_b": G.nodes[b]["institution"], "joint_papers": w,
            "years": f"{y0}-{y1}"} for w, a, b, y0, y1 in rows[:int(min(n, 20))]]
    return _res("strongest_pairs", f"Strongest {kind} faculty pairs", {"pairs": out}, [_flink(r[1]) for r in rows[:4]] + [_flink(r[2]) for r in rows[:4]], COVERAGE_FAC)


def interdisciplinary_communities(n=5):
    S = store()
    f = S.faculty[S.faculty.community_leiden.notna()]
    rows = []
    for c, g in f.groupby("community_leiden"):
        if len(g) < 5:
            continue
        shares = g.department.value_counts(normalize=True)
        entropy = float(-(shares * np.log2(shares)).sum())
        rows.append({"community": int(c), "size": len(g), "institutions": g.institution.value_counts().to_dict(), "departments": g.department.value_counts().head(4).to_dict(),
                     "department_entropy_bits": round(entropy, 2), "n_departments": int(g.department.nunique()), "leaders": g.sort_values("degree", ascending=False).faculty_name.head(3).tolist()})
    rows.sort(key=lambda r: -r["department_entropy_bits"])
    return _res("interdisciplinary_communities", "Leiden communities ordered by departmental diversity (entropy)", {"communities": rows[:int(n)], "note": "entropy of the department shares inside a community; higher = more mixed"}, [], COVERAGE_FAC)


# ============================================================================ papers and citations
def top_papers(metric="citations", institute=None, n=10, year_from=None, year_to=None, field=None, kind=None):
    S = store()
    p = S.papers
    if institute:
        r = E.resolve_institute(institute)
        if r["canonical"] in INSTS:
            p = p[p.our_institutes.str.contains(r["canonical"], regex=False)]
    if year_from:
        p = p[p.year >= int(year_from)]
    if year_to:
        p = p[p.year <= int(year_to)]
    if field:
        fl = E.resolve_field(field)["best"]
        if fl:
            p = p[(p.field == fl) | (p.subfield == fl)]
    if kind in ("journal", "conference"):
        p = p[p.type == kind]
    col = {"citations": "citations", "fwci": "fwci", "pagerank": "pagerank", "in_degree": "in_degree"}.get(metric, "citations")
    top = p.sort_values(col, ascending=False).head(int(min(n, 25)))
    rows = [{"title": r.title, "year": int(r.year), "venue": r.journal_name, "citations_worldwide": int(r.citations), "fwci": None if pd.isna(r.fwci) else round(float(r.fwci), 2),
             "corpus_in_degree": None if pd.isna(r.in_degree) else int(r.in_degree), "institutes": r.our_institutes} for r in top.itertuples()]
    return _res("top_papers", f"Top {len(rows)} papers by {col}", {"papers": rows, "note": "citations_worldwide is the OpenAlex count; corpus_in_degree counts only citations from other papers of these three institutes"},
                [_plink(w) for w in top.index[:5]], COVERAGE_FAC)


def get_paper(query):
    r = E.resolve_paper(query)
    if not r["candidates"]:
        return _res("get_paper", f"No paper matches '{query}'.", ok=False)
    if r["ambiguous"]:
        return _need("paper", query, r["candidates"], "get_paper")
    S = store()
    w = r["best"]
    p = S.papers.loc[w]
    fac = S.fac_papers[S.fac_papers.openalex_work_id == w]
    data = {"title": p.title, "year": int(p.year), "venue": p.journal_name, "type": p.type, "quartile": p.quartile, "field": p.field, "subfield": p.get("subfield"), "topic": p.get("topic"),
            "citations_worldwide": int(p.citations), "fwci": None if pd.isna(p.fwci) else round(float(p.fwci), 2), "authors_total": int(p.n_authors),
            "faculty_authors": [{"name": r.faculty_name, "institution": r.institution} for r in fac.itertuples()],
            "corpus_in_degree": None if pd.isna(p.in_degree) else int(p.in_degree), "corpus_out_degree": None if pd.isna(p.out_degree) else int(p.out_degree),
            "in_corpus_citations_by_kind": {"author_self": None if pd.isna(p.in_self_citations) else int(p.in_self_citations),
                                            "same_institute_other_author": None if pd.isna(p.in_same_institute_other_author) else int(p.in_same_institute_other_author),
                                            "between_our_institutes": None if pd.isna(p.in_between_our_institutes) else int(p.in_between_our_institutes)},
            "pagerank_within_corpus": None if pd.isna(p.pagerank) else float(p.pagerank), "pagerank_rank_within_publication_year": None if pd.isna(p.pagerank_rank_in_year) else int(p.pagerank_rank_in_year)}
    return _res("get_paper", f"{p.title} ({int(p.year)})", data, [_plink(w)] + [_flink(f"{r.institution}|{r.faculty_name}") for r in fac.itertuples()][:4], COVERAGE_FAC)


def citation_neighbourhood(paper):
    r = get_paper(paper)
    if not r["ok"]:
        return r
    S = store()
    w = E.resolve_paper(paper)["best"]
    e = pd.read_csv(OUT / "citation_network_ids.csv", dtype=str)
    cites = e[e.source_id == w].target_id.tolist()
    cited_by = e[e.target_id == w].source_id.tolist()
    ids = [w] + cites[:15] + cited_by[:25]
    import plotly.graph_objects as go
    G = nx.DiGraph()
    G.add_nodes_from(ids)
    G.add_edges_from([(w, c) for c in cites[:15]] + [(c, w) for c in cited_by[:25]])
    pos = nx.spring_layout(G, seed=15, k=0.9)
    fig = go.Figure()
    for a, b in G.edges():
        fig.add_annotation(x=pos[b][0], y=pos[b][1], ax=pos[a][0], ay=pos[a][1], xref="x", yref="y", axref="x", ayref="y", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="#b8b6b0")
    fig.add_trace(go.Scatter(x=[pos[n][0] for n in G], y=[pos[n][1] for n in G], mode="markers", marker=dict(size=[28 if n == w else 12 for n in G], color=["#0b0b0b" if n == w else "#2a78d6" if n in cited_by else "#eb6834" for n in G]),
                             text=[f"{S.papers.at[n, 'title'][:70]} ({int(S.papers.at[n, 'year'])})" if n in S.papers.index else n for n in G], hoverinfo="text", showlegend=False))
    fig.update_layout(**{**viz.LAYOUT, "height": 480}, title=dict(text="Citation neighbourhood inside the corpus (blue = cites this paper, orange = cited by this paper)", x=0.01), xaxis=dict(visible=False), yaxis=dict(visible=False))
    d = dict(r["data"])
    d.update({"cited_by_in_corpus": len(cited_by), "cites_in_corpus": len(cites), "cited_by_titles": [S.papers.at[c, "title"] for c in cited_by[:8] if c in S.papers.index]})
    return _res("citation_neighbourhood", f"{r['summary']}: cited by {len(cited_by)} corpus paper(s), cites {len(cites)}", d, r["evidence"], COVERAGE_FAC + " Only citations between papers of these three institutes are shown.", fig)


def explain_paper_pagerank(paper):
    r = get_paper(paper)
    if not r["ok"]:
        return r
    S = store()
    w = E.resolve_paper(paper)["best"]
    p = S.papers.loc[w]
    allp = S.papers
    rank_pr = int((allp.pagerank > p.pagerank).sum() + 1) if not pd.isna(p.pagerank) else None
    rank_cit = int((allp.citations > p.citations).sum() + 1)
    d = r["data"]
    kinds = d["in_corpus_citations_by_kind"]
    tot = sum(v or 0 for v in kinds.values())
    d.update({"pagerank_rank_overall": rank_pr, "citations_rank_overall": rank_cit, "self_citation_share_of_in_corpus_%": round((kinds["author_self"] or 0) / tot * 100, 1) if tot else None,
              "explanation_inputs": "PageRank counts only citations inside the corpus; a paper can rank high with few worldwide citations when many of its few corpus citations come from papers that are themselves cited"})
    return _res("explain_paper_pagerank", f"{p.title[:70]}: PageRank rank {rank_pr}, worldwide-citation rank {rank_cit}", d, r["evidence"], COVERAGE_FAC)


def citation_flows(citing=None, cited=None):
    S = store()
    net = S.json("network_results.json")["citation_network"]
    M, P = net["flow_matrix_source_rows_target_cols"], net["flow_matrix_row_pct"]
    a = E.resolve_institute(citing)["canonical"] if citing else None
    b = E.resolve_institute(cited)["canonical"] if cited else None
    data = {"counts_row_citing_column_cited": M, "row_percent": P, "convention": "row = citing institute, column = cited institute; joint papers count for every institute they belong to"}
    if a in INSTS and b in INSTS:
        data["answer"] = {"from": a, "to": b, "citations": M[a][b], "share_of_a_citations_%": P[a][b], "reverse": {"from": b, "to": a, "citations": M[b][a], "share_%": P[b][a]}}
    fl = S.json("inflow_results.json")
    data["indian_flows"] = {i: {k: fl[i][k] for k in ("in_cites_from_other_indian_institutes", "out_cites_to_other_indian_institutes", "impact_ratio_in_over_out")} for i in INSTS} if fl else None
    data["note"] = "an in/out ratio below 1 means the institute cites other Indian institutes more than it is cited by them; it is not a quality measure"
    return _res("citation_flows", "Citation flows between the three NITs and with other Indian institutes", data, [], "Citations between papers of these institutes (corpus), and OpenAlex-based flows with other Indian institutes where affiliation data exist.")


def review_analysis(institute=None):
    S = store()
    f = ST / "insights" / "review_analysis.csv"
    if not f.exists():
        return _res("review_analysis", "Review analysis has not been generated.", ok=False)
    d = pd.read_csv(f)
    if institute:
        r = E.resolve_institute(institute)
        if r["canonical"] in INSTS:
            d = d[d.institution == r["canonical"]]
    return _res("review_analysis", "Review vs non-review papers", {"table": d.to_dict("records"), "definitions": "strict = OpenAlex type review; broad = type or title words (review, survey, overview, ...)"}, [], COVERAGE_FAC)


def fastest_growing_topics(since=2020, level="subfield", n=8):
    S = store()
    p = S.papers[S.papers.get(level).notna() & (S.papers.year <= 2025)]
    early, late = p[p.year < since], p[p.year >= since]
    rows = []
    for t in set(late[level]) | set(early[level]):
        if not t:
            continue
        a, b = (early[level] == t).sum(), (late[level] == t).sum()
        if b >= 40:
            rows.append({level: t, f"papers_before_{since}": int(a), f"papers_{since}_2025": int(b), "share_before_%": round(a / len(early) * 100, 2), "share_after_%": round(b / len(late) * 100, 2),
                         "share_change_pp": round(b / len(late) * 100 - a / len(early) * 100, 2)})
    rows.sort(key=lambda r: -r["share_change_pp"])
    return _res("fastest_growing_topics", f"Largest gains in share of publications after {since} ({level})", {"rows": rows[:int(n)], "note": "2026 excluded (partial year); topics with at least 40 papers after the cut-off"}, [], COVERAGE_FAC)


def explain_metric(name):
    k = name.lower().strip().replace(" ", "_").replace("-", "_")
    alias = {"between": "betweenness", "eigen": "eigenvector", "h": "h_index", "hindex": "h_index", "page_rank": "pagerank", "q1": "q1_share", "core": "k_core", "jaccard": "weighted_jaccard", "community": "louvain/leiden"}
    k = alias.get(k, k)
    for key in GLOSSARY:
        if k == key or k in key:
            return _res("explain_metric", GLOSSARY[key], {"metric": key, "definition": GLOSSARY[key]})
    return _res("explain_metric", f"Defined metrics: {', '.join(GLOSSARY)}", {"metrics": list(GLOSSARY)}, ok=False)


# ============================================================================ registry
# ============================================================================ topic experts (paper-first)
SYNONYMS = {
    "blockchain": ["blockchain", "distributed ledger", "smart contract", "cryptocurrenc", "bitcoin", "ethereum"],
    "machine learning": ["machine learning", "deep learning", "neural network", "random forest", "support vector"],
    "deep learning": ["deep learning", "neural network", "convolutional", "lstm", "transformer"],
    "nlp": ["natural language", "nlp", "language model", "text classification", "sentiment", "machine translation"],
    "iot": ["internet of things", "iot", "wireless sensor", "smart home"],
    "solar": ["solar", "photovoltaic", "pv "],
    "security": ["security", "cryptograph", "authentication", "encryption", "privacy", "intrusion"],
}


def find_experts(topic, keywords=None, institute=None, n=8, include_former=False):
    """Faculty ranked by the papers they wrote on a topic: papers are matched first (title, OpenAlex topic and subfield), then the faculty on those papers."""
    S = store()
    terms = [t.strip().lower() for t in (keywords or []) if isinstance(t, str) and t.strip()]
    if not terms:
        terms = SYNONYMS.get(topic.strip().lower(), [topic.strip().lower()])
    pat = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + ")", re.I)
    p = S.papers
    text = (p.title.fillna("") + " | " + p.topic.fillna("") + " | " + p.subfield.fillna(""))
    hit = p[text.map(lambda x: bool(pat.search(x)))]
    cov = ("Matching uses paper titles and OpenAlex topic/subfield labels of the verified-faculty corpus (2016-2026); papers that use other words for the topic can be missed. "
           "Only faculty of MANIT Bhopal, NIT Jamshedpur and NIT Silchar are covered; this is output on the topic, not a quality ranking.")
    if hit.empty:
        return _res("find_experts", f"No paper in the corpus matches '{topic}' (searched: {', '.join(terms)}).", {"terms": terms, "papers_matched": 0}, [], cov, ok=False)
    fp = S.fac_papers[S.fac_papers.openalex_work_id.isin(hit.index)]
    ri = E.resolve_institute(institute) if institute else None
    if ri and ri.get("canonical") in INSTS:
        fp = fp[fp.institution == ri["canonical"]]
    fac = S.faculty
    status = fac.faculty_status.to_dict()
    if not include_former:
        fp = fp[fp.id.map(lambda i: status.get(i) != "former")]
    if fp.empty:
        return _res("find_experts", f"{len(hit)} paper(s) match '{topic}', but none by the selected faculty.", {"terms": terms, "papers_matched": int(len(hit))}, [], cov, ok=False)
    rows = []
    for fid_, g in fp.groupby("id"):
        g = g.sort_values("citations", ascending=False)
        f = fac.loc[fid_]
        rows.append({"id": fid_, "name": f.faculty_name, "institution": f.institution, "department": f.department, "status": f.faculty_status,
                     "relevant_papers": int(len(g)), "citations_on_these_papers": int(g.citations.sum()), "first_year": int(g.year.min()), "latest_year": int(g.year.max()),
                     "recent_papers_2022_on": int((g.year >= 2022).sum()), "example_papers": [f"{t} ({y})" for t, y in zip(g.title.head(2), g.year.head(2))],
                     "papers_total": int(f.papers), "h_index_2016_2026": int(f.h_index)})
    rows.sort(key=lambda r: (-r["relevant_papers"], -r["citations_on_these_papers"]))
    top = rows[:max(1, min(int(n or 8), 15))]
    by_inst = fp.drop_duplicates("openalex_work_id").groupby("institution").size().to_dict()
    data = {"topic": topic, "terms_searched": terms, "papers_matched": int(len(hit)), "papers_by_our_institute": {k: int(v) for k, v in by_inst.items()},
            "faculty": top, "rows": [{k: v for k, v in r.items() if k != "example_papers"} for r in top]}
    ev = [_flink(r["id"]) for r in top[:5]] + [_plink(w) for w in hit.sort_values("citations", ascending=False).index[:3]]
    return _res("find_experts", f"{len(hit)} papers on '{topic}'; most active faculty: " + ", ".join(f"{r['name']} ({r['relevant_papers']})" for r in top[:3]), data, ev, cov)



def _institute_context():
    """NIRF facts the group supplied (rank, PhD scholars, sponsored research, consultancy, lab equipment spend); separate from the publication data."""
    f = OUT.parent / "institute_facts.json"
    if not f.exists():
        return {}, ""
    d = json.loads(f.read_text(encoding="utf-8"))
    ctx = {k: {"location": v.get("location"), "facts": [f"{x['label']}: {x['value']}" + (f" ({x['note']})" if x.get("note") else "") for x in v["facts"]]}
           for k, v in d.items() if isinstance(v, dict) and "facts" in v}
    return ctx, d.get("rank_source", "")


def explain_output_difference(metric="papers"):
    """Why one institute publishes more than another, using only measured drivers (headcount, per-faculty output, concentration, shared papers, team size, seniority, like-for-like departments, yearly leader)."""
    f = ST / "insights" / "output_drivers.json"
    if not f.exists():
        return _res("explain_output_difference", "The output-driver analysis has not been generated (run output_drivers.py).", ok=False)
    d = json.loads(f.read_text(encoding="utf-8"))
    y = d["yearly_papers"]
    data = {"findings": d["verdicts"], "measures": {m["label"]: m["values"] for m in d["measures"]}, "yearly_papers": y, "yearly_leader": d["yearly_leader"],
            "common_departments_papers_per_faculty": {c["department"]: {k: v["papers_per_faculty"] for k, v in c["values"].items()} for c in d["common_departments"]},
            "common_department_leaders": d["common_department_leaders"],
            "not_in_dataset": ["teaching load", "faculty qualifications and training", "department-level lab facilities"]}
    ctx, src = _institute_context()
    if ctx:
        data["institute_context_nirf"] = ctx
    return _res("explain_output_difference", d["verdicts"][0], data, [],
                "Publication drivers are measured from OpenAlex. The NIRF figures (rank, PhD scholars, sponsored research, consultancy, lab equipment spend) are as reported in NIRF submissions supplied by the group, "
                f"not from the publication data, and are partial per institute ({src}). A measured gap or a NIRF figure is context, not a proven cause. "
                "Teaching load, faculty qualifications and department-level labs are not available. Papers are counted fully per institute; 2026 is partial.")


def _new_views():
    f = ST / "insights" / "new_views.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def partner_place_impact(institute=None, n=5):
    """Mean/median FWCI of the institutes’ papers that have a co-author in each place (Indian state or foreign country) against the institute's own average."""
    nv = _new_views()
    if not nv or "fwci_places" not in nv:
        return _res("partner_place_impact", "The partner-place analysis has not been generated (run new_views.py).", ok=False)
    inst = E.resolve_institute(institute)["canonical"] if institute else None
    sc = nv["fwci_places"].get(inst if inst in INSTS else "all")
    base, rows = sc["baseline"], sc["rows"]
    n = max(1, min(int(n or 5), 15))
    hi = sorted(rows, key=lambda r: -r["lift"])[:n]
    lo = sorted(rows, key=lambda r: r["lift"])[:n]
    shape = lambda r: {"place": r["place"].replace("India: ", "") + (" (India)" if r["place"].startswith("India: ") else ""), "papers": r["n"], "mean_fwci": r["mean"], "median_fwci": r["median"], "mean_vs_ours": r["lift"]}
    above = sum(1 for r in rows if r["lift"] > 0)
    data = {"scope": inst if inst in INSTS else "all three institutes", "baseline_mean_fwci": base["mean"], "baseline_median_fwci": base["median"], "places_listed": len(rows), "places_above_average": above,
            "highest": [shape(r) for r in hi], "lowest": [shape(r) for r in lo]}
    return _res("partner_place_impact", f"Our papers average FWCI {base['mean']}; {above} of {len(rows)} partner places are above that. Highest: " + ", ".join(f"{shape(r)['place']} ({r['mean']})" for r in hi[:3]) + ".", data, [],
                "Association only: papers with a co-author in a place are compared with the institute's average; it does not show that working with that place causes higher impact. A place needs at least 25 papers to be listed. "
                "The mean is pulled up by a few highly cited papers, so the median is given too. Shown in the Reach tab.")


def citation_give_take(institute=None, n=8):
    """Which institutes cite us more than we cite them (and the reverse), and how private universities, other universities, premier institutes, labs and industry compare."""
    nv = _new_views()
    if not nv or "give_take" not in nv:
        return _res("citation_give_take", "The citation give-and-take analysis has not been generated (run new_views.py).", ok=False)
    inst = E.resolve_institute(institute)["canonical"] if institute else None
    insts = [inst] if inst in INSTS else INSTS
    n = max(1, min(int(n or 8), 15))
    out = {}
    for i in insts:
        g = nv["give_take"][i]
        rows = [r for r in g["rows"] if r["cites_us"] + r["we_cite"] >= 100]
        take = sorted(rows, key=lambda r: -(r["cites_us"] - r["we_cite"]))[:n]
        give = sorted(rows, key=lambda r: (r["cites_us"] - r["we_cite"]))[:n]
        f = lambda r: {"institute": r["name"], "cites_us": r["cites_us"], "we_cite": r["we_cite"]}
        ratio = lambda b: round(b["cites_us"] / b["we_cite"], 2) if b["we_cite"] else None
        out[i] = {"citations_received": g["total_in"], "citations_given": g["total_out"], "cite_us_much_more_than_we_cite_them": [f(r) for r in take], "we_cite_much_more_than_they_cite_us": [f(r) for r in give],
                  "private_universities": {**g["private_univ"], "ratio_received_to_given": ratio(g["private_univ"])}, "other_universities": {**g["other_univ"], "ratio_received_to_given": ratio(g["other_univ"])},
                  "iit_nit_iiit_iiser": {**g["premier"], "ratio_received_to_given": ratio(g["premier"])}, "industry": {**g["industry"], "ratio_received_to_given": ratio(g["industry"])}}
    first = out[insts[0]]
    pv = first["private_universities"]
    return _res("citation_give_take", f"{insts[0]}: {pv['institutes']} private universities cite {i} {pv['cites_us']:,} times and {i} cites them {pv['we_cite']:,} times.", {"by_institute": out}, [],
                "Counts of citations between the institutes’ papers and papers of other Indian institutes (OpenAlex). 'Private universities' are matched by name from a list, so the grouping is approximate; the data has no public/private flag. "
                "A gap does not show unfairness: larger or same-field institutes cite the institute more often than the reverse, and papers can only cite older work. Shown in the Citation flows tab.")


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


S_ = {"type": "string"}
I_ = {"type": "integer"}
TOOLS = {
    "find_faculty": (find_faculty, "Find verified faculty by (possibly partial) name. Returns candidates with institute, department, papers, h-index.", _schema({"query": S_, "institute": S_}, ["query"])),
    "get_faculty_profile": (get_faculty_profile, "Full profile of one faculty member: papers, citations, h-index (2016-2026), venues, collaborators, network metrics.", _schema({"faculty": S_}, ["faculty"])),
    "compare_faculty": (compare_faculty, "Compare two faculty on productivity, impact and network position.", _schema({"a": S_, "b": S_}, ["a", "b"])),
    "assess_collaboration": (assess_collaboration, "Everything about whether two faculty already collaborate or could: joint papers, shortest path, common collaborators, topic similarity, model score, network figure.", _schema({"a": S_, "b": S_}, ["a", "b"])),
    "get_collaboration_history": (get_collaboration_history, "Joint papers of two faculty.", _schema({"a": S_, "b": S_}, ["a", "b"])),
    "get_shortest_collaboration_path": (get_shortest_collaboration_path, "Shortest collaboration path between two faculty with a highlighted figure.", _schema({"a": S_, "b": S_}, ["a", "b"])),
    "get_common_collaborators": (get_common_collaborators, "Faculty who have co-authored with both people.", _schema({"a": S_, "b": S_}, ["a", "b"])),
    "get_ego_network": (get_ego_network, "Collaboration network around one faculty member (radius 1 or 2).", _schema({"faculty": S_, "radius": I_}, ["faculty"])),
    "recommend_collaborators": (recommend_collaborators, "Rank potential collaborators for a faculty member (no joint paper yet). scope: any | same_institute | other_nits.",
                                _schema({"faculty": S_, "k": I_, "scope": {"type": "string", "enum": ["any", "same_institute", "other_nits"]}, "field": S_, "different_department": {"type": "boolean"}}, ["faculty"])),
    "assess_institute_collaboration": (assess_institute_collaboration, "Can a faculty member collaborate with an institute (one of the three or an outside partner)? Uses only data that exists.", _schema({"faculty": S_, "institute": S_}, ["faculty", "institute"])),
    "compare_institutes": (compare_institutes, "Compare the three institutes on normalised metrics (productivity per faculty, citations per paper, FWCI, Q1 share, growth).", _schema({"institutes": {"type": "array", "items": S_}})),
    "institute_profile": (institute_profile, "Profile of one of the three institutes including partners and departments.", _schema({"institute": S_}, ["institute"])),
    "top_faculty": (top_faculty, "Rank faculty by a metric: papers, citations, h_index, betweenness, degree, closeness, eigenvector, q1_share, citations_per_paper, fwci, participation, k_core.",
                    _schema({"metric": S_, "institute": S_, "department": S_, "n": I_, "status": {"type": "string", "enum": ["current", "former"]}})),
    "faculty_pattern": (faculty_pattern, "Find faculty with a pattern: high_betweenness_low_degree, high_citations_few_collaborators, connected_but_low_citations, interdisciplinary_bridges.",
                        _schema({"pattern": S_, "institute": S_, "n": I_}, ["pattern"])),
    "network_overview": (network_overview, "Structure of the faculty collaboration network (components, clustering, paths, communities) for all or one institute.", _schema({"scope": S_})),
    "resilience_summary": (resilience_summary, "Network resilience results: random vs targeted removal, critical brokers, with curve figure.", _schema({"scope": S_})),
    "simulate_node_removal": (simulate_node_removal, "Remove named faculty from the collaboration graph and report the structural effect.", _schema({"faculty_list": {"type": "array", "items": S_}}, ["faculty_list"])),
    "filter_network_by_weight": (filter_network_by_weight, "Keep only collaborations with at least N joint papers and report the resulting network.", _schema({"min_joint_papers": I_, "scope": S_})),
    "bridge_researchers": (bridge_researchers, "Faculty with the highest betweenness (brokers).", _schema({"scope": S_, "n": I_})),
    "strongest_pairs": (strongest_pairs, "Strongest faculty pairs by joint papers. kind: any | within_institute | cross_institute.", _schema({"kind": {"type": "string", "enum": ["any", "within_institute", "cross_institute"]}, "n": I_})),
    "interdisciplinary_communities": (interdisciplinary_communities, "Collaboration communities ordered by how mixed their departments are.", _schema({"n": I_})),
    "top_papers": (top_papers, "Top papers by citations / fwci / pagerank with optional institute, years, field, journal/conference filter.", _schema({"metric": S_, "institute": S_, "n": I_, "year_from": I_, "year_to": I_, "field": S_, "kind": S_})),
    "get_paper": (get_paper, "Details of one paper by title fragment, DOI or OpenAlex id.", _schema({"query": S_}, ["query"])),
    "citation_neighbourhood": (citation_neighbourhood, "Papers that cite / are cited by a paper inside the corpus, with a figure.", _schema({"paper": S_}, ["paper"])),
    "explain_paper_pagerank": (explain_paper_pagerank, "Why a paper has its within-corpus PageRank compared with its worldwide citations (self-citation share).", _schema({"paper": S_}, ["paper"])),
    "citation_flows": (citation_flows, "Citation flows between the three institutes (row = citing, column = cited) and with other Indian institutes.", _schema({"citing": S_, "cited": S_})),
    "review_analysis": (review_analysis, "Review vs non-review papers: share of papers and citations.", _schema({"institute": S_})),
    "fastest_growing_topics": (fastest_growing_topics, "Topics (subfields) whose share of publications grew most after a year.", _schema({"since": I_, "level": S_, "n": I_})),
    "partner_institutes": (partner_institutes, "Collaboration of the three institutes with one OUTSIDE institute (e.g. IIITH, Jadavpur University, NIT Hamirpur) or with a whole type (IIT, IIIT, NIT, CSIR, IISER, DRDO): joint papers, years, faculty involved, citations both ways. Use for questions like 'did any institute collaborate with IIITH' or 'who works with IITs'.", _schema({"query": S_, "institute": S_}, ["query"])),
    "find_experts": (find_experts, "Who to approach on a research TOPIC (e.g. blockchain, solar cells, NLP): finds the papers on the topic first (title, OpenAlex topic), then ranks the faculty who wrote them, optionally within one institute. ALWAYS pass `keywords` with synonyms and related terms (e.g. blockchain: ['blockchain','distributed ledger','smart contract']). Use for 'best faculty to collaborate with in X', 'who works on X'.", _schema({"topic": S_, "keywords": {"type": "array", "items": {"type": "string"}}, "institute": S_, "n": I_}, ["topic"])),
    "partner_place_impact": (partner_place_impact, "Does working with co-authors from some places (Indian states such as Delhi, or countries such as the US) go with higher or lower FWCI? Gives mean and median FWCI of the three institutes' papers per partner place against the institute's average. Use for 'which countries/states raise our impact'.", _schema({"institute": S_, "n": I_})),
    "citation_give_take": (citation_give_take, "Which institutes cite an institute more than it cites them, and do private universities, other universities, IIT/NIT/IIIT, labs or industry cite an institute more than it cites them. Use for 'who cites the institutes most', 'do private universities boost our citations', 'is citation reciprocal'.", _schema({"institute": S_, "n": I_})),
    "explain_output_difference": (explain_output_difference, "WHY does an institute publish more / differ in output? Returns measured drivers (headcount, papers per faculty, median, concentration, fractional credit, team size, seniority, like-for-like departments) AND papers per year per institute. Use for any 'why' or 'yearly' output question; do not add reasons the tool does not return.", _schema({"metric": S_})),
    "explain_metric": (explain_metric, "Plain-language definition of a network or bibliometric metric used in the dashboard.", _schema({"name": S_}, ["name"])),
}


# ============================================================================ links into the dashboard
TAB_LINK = {"institute_profile": ("overview", "Institute overview"), "compare_institutes": ("overview", "Institute comparison"),
            "top_faculty": ("faculty", "Faculty leaderboard"), "faculty_pattern": ("faculty", "Faculty table"),
            "network_overview": ("collab", "Collaboration network"), "strongest_pairs": ("collab", "Collaboration network"), "bridge_researchers": ("collab", "Collaboration network"),
            "interdisciplinary_communities": ("collab", "Collaboration network"), "filter_network_by_weight": ("collab", "Collaboration network"),
            "resilience_summary": ("resil", "Network resilience"), "simulate_node_removal": ("resil", "Network resilience"),
            "top_papers": ("papers", "Paper explorer"), "get_paper": ("papers", "Paper explorer"), "review_analysis": ("papers", "Papers"),
            "citation_neighbourhood": ("citnet", "Citation network"), "explain_paper_pagerank": ("citnet", "Citation network"),
            "citation_flows": ("flows", "Citation flows"), "citation_give_take": ("flows", "Citation flows"), "partner_place_impact": ("reach", "Reach and locality"), "fastest_growing_topics": ("pubs", "Publications"),
            "recommend_collaborators": ("potential", "Potential collaborations"), "find_experts": ("faculty", "Faculty table"), "explain_output_difference": ("overview", "Why institutes differ (Overview)"), "assess_collaboration": ("potential", "Potential collaborations"),
            "assess_institute_collaboration": ("reach", "Reach and locality")}


def _hash(tab, **params):
    q = "&".join(f"{k}={quote(str(v))}" for k, v in params.items() if v not in (None, ""))
    return tab + ("?" + q if q else "")


@lru_cache(maxsize=1)
def _dash_faculty_index():
    """Position of each faculty member in the dashboard's faculty list (same order and alias rule as build_dashboard.py)."""
    import movers
    alias, idx = movers.aliases(), {}
    for i in INSTS:
        df = pd.read_csv(ST / f"faculty_ranking_{i.replace(' ', '_')}.csv")
        for name in df.faculty_name:
            if (i, name) not in alias:
                idx[(i, name)] = len(idx)
    return idx


def _inst_index(args):
    for v in (args or {}).values():
        if isinstance(v, str):
            r = E.resolve_institute(v)
            if r.get("canonical") in INSTS:
                return INSTS.index(r["canonical"])
    return None


def _links(name, args, res):
    if not res.get("ok"):
        return []
    out, inst = [], _inst_index(args)
    if name == "partner_institutes":
        d = res["data"]
        if d.get("partner"):
            out.append({"label": f"{d['partner']}: partner profile in Reach", "hash": _hash("reach", i=d["partner"], inst=inst)})
        out.append({"label": "Reach and locality tab", "hash": _hash("reach", inst=inst)})
        out.append({"label": "Citation flows with Indian institutes", "hash": _hash("flows", inst=inst)})
        return out
    ids = [e["id"] for e in res.get("evidence", []) if isinstance(e, dict) and e.get("type") == "faculty"]
    fi = _dash_faculty_index()
    if name == "compare_faculty" and len(set(ids)) >= 2:
        a, b = [tuple(x.split("|", 1)) for x in list(dict.fromkeys(ids))[:2]]
        if a in fi and b in fi:
            out.append({"label": "Compare them side by side in the dashboard", "hash": _hash("faculty", cmpA=fi[a], cmpB=fi[b])})
    for k, fid_ in enumerate(dict.fromkeys(ids)):
        i, n = fid_.split("|", 1)
        if (i, n) in fi and k < 2:
            out.append({"label": f"{n}: profile and network", "hash": _hash("collab", f=fi[(i, n)])})
    if name in TAB_LINK:
        tab, label = TAB_LINK[name]
        out.append({"label": f"{label} tab" + (f" ({SHORT[INSTS[inst]]})" if inst is not None else ""), "hash": _hash(tab, inst=inst)})
    return out


def run_tool(name, args):
    """Safe dispatcher: only allowlisted names, arguments filtered to the declared schema, exceptions turned into a result."""
    if name not in TOOLS:
        return _res(name, f"Unknown tool '{name}'", ok=False)
    fn, _, schema = TOOLS[name]
    allowed = set(schema["properties"])
    clean = {k: v for k, v in (args or {}).items() if k in allowed and v not in (None, "")}
    try:
        res = fn(**clean)
        try:
            res["links"] = _links(name, clean, res)
        except Exception:
            res["links"] = []
        return res
    except TypeError as e:
        return _res(name, f"Bad arguments for {name}: {e}", ok=False)
    except Exception as e:      # never let a tool crash the chat
        return _res(name, f"{name} failed: {type(e).__name__}: {e}", ok=False)
