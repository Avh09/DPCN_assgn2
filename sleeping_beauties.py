"""Delayed recognition ("sleeping beauties"): which papers were barely cited at first and much more later, and does it hold up?
(stats/sleeping_beauties.csv, stats/sleeping_beauties.json)

The Phase-1 analysis (INSIGHTS.md section 8 of the earlier nit_project folder, no script kept) listed 13 papers with at most 3 citations in their first three years (publication year + 2) and at least 40
afterwards. The professor asked to check them carefully. This script reproduces that list from the yearly citation counts
(OpenAlex counts_by_year, work_extras.csv) and tests each paper four ways:

  1. Beauty coefficient B (Ke, Ferrara, Radicchi & Flammini 2015, PNAS 112(24):7426, Eq. 2): the summed gap between the
     citation curve and the straight line from (0, c0) to the peak year (tm, c_tm), each year divided by max(1, c_t).
     B = 0 for a steadily growing paper, negative for an early peak, large for a long low start and a late burst.
     Awakening age t_a = the year furthest from that line (their Eq. 3). B is ranked against all faculty papers of
     2016-2022 with at least one citation (later papers are too young to show a delay).
  2. Self-citations: yearly citations from later papers of the same verified faculty (citation_network_with_outside.csv) are
     removed and B and the 3/40 rule are recomputed. Self-citations by co-authors outside the faculty set are not visible.
  3. Publication date: OpenAlex gives one year; Crossref's online / print dates (data/ref/sleeping_beauty_dates.csv, looked
     up 2026-11-19) show whether the "first three years" are really three years. If the paper went online in November or
     December, or Crossref's issue year is later than the OpenAlex year, the rule is re-run from the next year.
  4. Verdict (fixed rules, no judgement per paper):
       holds up       still meets the rule without self-citations, B without self-citations in the top 1% of the corpus,
                      and no date problem
       not supported  B without self-citations below the corpus 90th percentile (no real delay: the curve just rises)
       weaker         everything in between, with the reason

For scale: Ke et al. find no natural threshold for B; the 1,000 strongest sleeping beauties in Web of Science (22 million
papers, over a century) have B >= 317.9. Papers here are at most ten years old, so B stays small: these are short delays.
Runs offline after corpus_filter.py / retractions.py.
"""
import json

import numpy as np
import pandas as pd

import config

OUT = config.OUT_DIR
STATS = OUT / "stats"
REF = config.ROOT / "data" / "ref" / "sleeping_beauty_dates.csv"
LAST_FULL_YEAR = 2025          # 2026 is partial: kept in the 'later citations' count, not in the curve used for B
EARLY_MAX, LATE_MIN, WINDOW = 3, 40, 3


def beauty(series):
    """Ke et al. (2015) Eq. 2 and Eq. 3. series[t] = citations at age t. Returns (B, t_m, t_a)."""
    c = np.asarray(series, float)
    if c.sum() == 0:
        return np.nan, None, None
    tm = int(c.argmax())
    if tm == 0:
        return 0.0, 0, 0
    t = np.arange(tm + 1)
    line = (c[tm] - c[0]) / tm * t + c[0]
    b = float(((line - c[: tm + 1]) / np.maximum(1, c[: tm + 1])).sum())
    a = c[tm] - c[0]
    dist = np.abs(a * t - tm * c[: tm + 1] + tm * c[0]) / np.hypot(a, tm)
    return b, tm, int(dist.argmax())


def nth(x):
    n = int(round(x))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def split(counts, start):
    early = sum(v for y, v in counts.items() if start <= y < start + WINDOW)
    late = sum(v for y, v in counts.items() if y >= start + WINDOW)
    return early, late


def main():
    g = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    g = g[g.is_faculty.str.lower() == "true"]
    fac_by_doi = g.groupby("doi").faculty_name.apply(set).to_dict()
    papers = g.drop_duplicates("openalex_work_id").copy()
    papers["year"] = papers.year.astype(int)
    papers["faculty"] = papers.openalex_work_id.map(g.groupby("openalex_work_id").faculty_name.apply(lambda s: "; ".join(sorted(set(s)))))
    w = pd.read_csv(OUT / "work_extras.csv", dtype=str, keep_default_na=False)[["openalex_work_id", "counts_by_year"]]
    papers = papers.merge(w, on="openalex_work_id", how="left")
    papers["counts"] = papers.counts_by_year.map(lambda s: {int(k): int(v) for k, v in json.loads(s).items()} if isinstance(s, str) and s else {})

    # self-citations per cited paper and year: the citing paper shares a verified faculty author with the cited one
    cn = pd.read_csv(OUT / "citation_network_with_outside.csv", dtype=str, keep_default_na=False)
    cn = cn[cn.target_doi.isin(papers.doi) & (cn.target_doi != "")]
    is_self = [bool(fac_by_doi.get(s, set()) & fac_by_doi.get(t, set())) for s, t in zip(cn.source_doi, cn.target_doi)]
    selfc = cn[np.array(is_self, dtype=bool)].groupby(["target_doi", "year"]).size()
    self_by_doi = {}
    for (doi, y), n in selfc.items():
        self_by_doi.setdefault(doi, {})[int(y)] = int(n)

    rows = []
    for p in papers[papers.year <= 2022].itertuples(index=False):
        c, s = p.counts, self_by_doi.get(p.doi, {})
        ns = {y: max(0, v - s.get(y, 0)) for y, v in c.items()}
        ser = [c.get(y, 0) for y in range(p.year, LAST_FULL_YEAR + 1)]
        ser_ns = [ns.get(y, 0) for y in range(p.year, LAST_FULL_YEAR + 1)]
        b, tm, ta = beauty(ser)
        b_ns, _, _ = beauty(ser_ns)
        e, l = split(c, p.year)
        e_ns, l_ns = split(ns, p.year)
        rows.append({"openalex_work_id": p.openalex_work_id, "doi": p.doi, "title": p.title, "institution": p.institution, "year": p.year,
                     "venue": p.journal_name, "faculty": p.faculty, "citations": int(p.citations or 0), "early_3y": e, "later": l,
                     "self_citations": sum(s.values()), "early_3y_without_self": e_ns, "later_without_self": l_ns,
                     "B": b, "B_without_self": b_ns, "peak_age": tm, "awakening_age": ta,
                     "yearly": [c.get(y, 0) for y in range(p.year, 2027)]})
    allp = pd.DataFrame(rows)
    dist = allp.B.dropna().to_numpy()
    pct = lambda b: round(float(100 * (dist < b).mean()), 1) if pd.notna(b) else None
    allp["B_percentile"] = allp.B.map(pct)
    allp["B_without_self_percentile"] = allp.B_without_self.map(pct)

    cand = allp[(allp.early_3y <= EARLY_MAX) & (allp.later >= LATE_MIN)].copy()
    dates = pd.read_csv(REF, dtype=str, keep_default_na=False).set_index("openalex_work_id") if REF.exists() else pd.DataFrame()
    out = []
    for r in cand.itertuples(index=False):
        d = dates.loc[r.openalex_work_id] if r.openalex_work_id in dates.index else None
        online = (d.published_online or d.issued) if d is not None else ""
        late_in_year = bool(online) and int(online.split("-")[0]) == r.year and len(online.split("-")) > 1 and int(online.split("-")[1]) >= 11
        issue_later = d is not None and bool(d.issued) and int(d.issued.split("-")[0]) > r.year
        date_note, date_problem = "", False
        if late_in_year or issue_later:
            counts = dict(zip(range(r.year, 2027), r.yearly))
            e2, l2 = split(counts, r.year + 1)
            date_problem = not (e2 <= EARLY_MAX and l2 >= LATE_MIN)
            date_note = (f"online {online}" if late_in_year else f"Crossref issue date {d.issued}") + \
                        (f"; counted from the next year it has {e2} early citations, so the rule no longer holds" if date_problem
                         else "; the rule still holds when counted from the next year")
        rule_ns = r.early_3y_without_self <= EARLY_MAX and r.later_without_self >= LATE_MIN
        p_ns = r.B_without_self_percentile or 0
        why = []
        if p_ns < 90:
            verdict = "not supported"
            why.append(f"beauty coefficient without self-citations only at the {nth(p_ns)} percentile: citations rise steadily, no real delay")
        elif rule_ns and p_ns >= 99 and not date_problem:
            verdict = "holds up"
            why.append(f"beauty coefficient in the top {max(0.1, round(100 - p_ns, 1))}% of the corpus even without self-citations")
        else:
            verdict = "weaker"
            if p_ns < 99:
                why.append(f"beauty coefficient without self-citations at the {nth(p_ns)} percentile (below the top 1%)")
            if not rule_ns:
                why.append(f"without self-citations it has {r.later_without_self} later citations, below the {LATE_MIN} of the rule")
        if date_problem:
            why.append(date_note)
            if verdict == "holds up":
                verdict = "weaker"
        elif date_note:
            why.append(date_note)
        out.append({**r._asdict(), "verdict": verdict, "reason": "; ".join(why), "online_date": online})
    res = pd.DataFrame(out).sort_values(["verdict", "B_without_self"], key=lambda s: s.map({"holds up": 0, "weaker": 1, "not supported": 2}) if s.name == "verdict" else -s)
    res.drop(columns=["yearly"]).to_csv(STATS / "sleeping_beauties.csv", index=False)
    summary = {
        "rule": f"at most {EARLY_MAX} citations in the publication year and the next two, at least {LATE_MIN} afterwards; papers 2016-2022",
        "method": "Ke, Ferrara, Radicchi & Flammini (2015) PNAS 112(24):7426, beauty coefficient (Eq. 2) and awakening time (Eq. 3)",
        "papers_scored": int(allp.B.notna().sum()),
        "share_with_at_most_3_early_%": round(float(100 * (allp.early_3y <= EARLY_MAX).mean()), 1),
        "B_quantiles": {k: round(float(np.quantile(dist, q)), 1) for k, q in (("p50", .5), ("p90", .9), ("p99", .99), ("max", 1))},
        "wos_top_1000_threshold": 317.9,
        "candidates": len(res), "verdicts": res.verdict.value_counts().to_dict(),
        "papers": [{k: (None if isinstance(v, float) and np.isnan(v) else (round(v, 1) if isinstance(v, float) else v)) for k, v in x.items()} for x in res.to_dict("records")],
    }
    (STATS / "sleeping_beauties.json").write_text(json.dumps(summary, indent=1, default=int), encoding="utf-8")
    print(f"sleeping_beauties: {len(res)} candidates -> {summary['verdicts']}; corpus B p99 {summary['B_quantiles']['p99']}")


if __name__ == "__main__":
    main()
