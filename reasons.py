"""Turn a tree model's feature contributions into plain-language reasons for one suggested pair.

Each feature belongs to a theme; a pair's theme score is the sum of the model's (log-odds) contributions of its features, so the reasons are the signals
that actually pushed this pair's score up, not a separate heuristic. `phrase` then words a theme with the pair's real values.
"""
import numpy as np

THEMES = {
    "network": ["common_neighbours", "jaccard_neighbours", "adamic_adar", "resource_allocation", "hop_distance", "same_community", "coauth_shared", "coauth_aa",
                "coauth_cosine", "paths3", "katz", "spectral_cos", "spectral_dot", "big_cn", "big_aa", "big_ra", "big_jac", "big_paths3"],
    "topics": ["topic_cosine", "topic_weighted_jaccard", "shared_subfields", "field_cosine", "topic_fine_cosine", "title_cosine", "topic_cos_r"],
    "literature": ["refs_cosine", "refs_cos_r", "cite_min", "cite_max", "cite_r_min", "cite_r_max"],
    "venues": ["venue_cosine", "venue_cos_r"],
    "place": ["same_department", "same_institute", "institute_pair_joint_papers_hist", "dept_pair_joint_hist"],
    "activity": ["log_papers_min", "log_papers_max", "recent_papers_min", "recent_papers_max", "recent_trend_min", "recent_trend_max", "deg_min", "deg_max",
                 "pref_attachment", "log_cites_min", "log_cites_max", "big_pa", "big_deg_min", "big_deg_max", "big_pap_min", "big_pap_max", "big_rec_min", "big_rec_max"],
    "career": ["first_year_min", "first_year_max", "big_age_min", "big_age_max"],
    "history": ["joint_papers_hist", "years_since_last_joint"],
}
THEME_OF = {f: t for t, fs in THEMES.items() for f in fs}


def theme_drivers(contrib, feats, k=3, min_gain=0.05):
    """contrib: (n_pairs, n_feats) matrix of log-odds contributions -> per pair the top-k positive themes [(theme, score), ...]."""
    th = sorted(THEMES)
    idx = {t: [i for i, f in enumerate(feats) if THEME_OF.get(f) == t] for t in th}
    S = np.stack([contrib[:, idx[t]].sum(1) if idx[t] else np.zeros(len(contrib)) for t in th], 1)
    out = []
    for row in S:
        order = np.argsort(-row)[:k]
        out.append([(th[i], round(float(row[i]), 3)) for i in order if row[i] > min_gain])
    return out


def phrase(theme, f):
    """f: facts about the pair (hops, common, shared_other, subfields, topic, refs, venue, same_dept, same_inst, dept, inst, joint, last_year)."""
    if theme == "network":
        bits = []
        if f.get("common"):
            n = len(f["common"])
            bits.append(f"share {n} collaborator{'s' if n > 1 else ''} among the faculty ({', '.join(f['common'][:2])}{'…' if n > 2 else ''})")
        elif f.get("shared_other"):
            bits.append(f"share {int(f['shared_other'])} co-author{'s' if f['shared_other'] > 1 else ''} outside the faculty")
        if f.get("hops"):
            bits.append(f"{f['hops']} co-author steps apart")
        return ("are close in the co-author network: " + ", ".join(bits)) if bits else "sit in neighbouring parts of the co-author network"
    if theme == "topics":
        s = "work on similar topics" + (f" ({'; '.join(f['subfields'][:2])})" if f.get("subfields") else "")
        return s + (f", topic similarity {f['topic']:.2f}" if f.get("topic") else "")
    if theme == "literature":
        return "cite many of the same papers" if (f.get("refs") or 0) > 0.03 else "cite each other's work"
    if theme == "venues":
        return "publish in the same journals and conferences"
    if theme == "place":
        if f.get("same_dept"):
            return f"are in the same department ({f.get('dept')}) at {f.get('inst')}"
        if f.get("same_inst"):
            return f"are at the same institute ({f.get('inst')})"
        return "come from departments that already collaborate often"
    if theme == "activity":
        return "are both actively publishing and well connected"
    if theme == "career":
        return "are at a similar career stage"
    if theme == "history":
        j = f.get("joint")
        return f"have {j} joint paper{'s' if j != 1 else ''} already" + (f", the latest in {f['last_year']}" if f.get("last_year") else "") if j else "have worked together before"
    return None
