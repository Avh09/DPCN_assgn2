"""Resolve the real conference behind every conference paper, and rank it against CORE (ICORE / CORE 2023).

OpenAlex often records only the publisher's series (Lecture Notes in ..., AIP Conference Proceedings, Materials Today:
Proceedings) as the venue. Crossref knows the conference itself for most IEEE / AIP / ACM proceedings articles (the `event`
and `container-title` fields), but not for Springer series chapters, where the conference is simply not recorded in any open
source. So every conference paper ends up in one of
  named conference      a conference name is known (Crossref event or container title, or OpenAlex's own venue name)
  generic series        only the publisher's series is known (the conference cannot be identified)
and named conferences are matched to the CORE list:
  1. acronym in brackets in the name equals the CORE acronym AND the names are similar (>= 70)
  2. normalised name very similar to a CORE name (token-sort ratio >= 90)
Ranks kept: A*, A, B, C. "Unranked" in CORE and non-CS venues are reported separately as `not_in_core`, because CORE ranks
computer-science conferences only; most of our conference papers are engineering conferences.

Writes data/out/conference_resolved.csv, data/out/stats/conference_ranking.json (including how many A*/A papers exist in the
unfiltered corpus and who wrote them: faculty or non-faculty authors). Needs internet for Crossref (free, cached in
data/raw/crossref_events/).
    python conference_resolution.py
"""
import csv
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from rapidfuzz import fuzz

import config

CACHE = config.RAW_DIR / "crossref_events"
OUT = config.OUT_DIR
GENERIC = re.compile(r"^(lecture notes|advances in|studies in|communications in computer|smart innovation|algorithms for|springer (proceedings|tracts)|"
                     r"aip conference|materials today|iop conference|journal of physics: conference|procedia|ceur|"
                     r"springer proceedings|transactions on|signals and communication|energy systems in|green energy|"
                     r"innovations in|cognitive science|studies in|intelligent systems)", re.I)


def crossref(doi):
    f = CACHE / (hashlib.md5(doi.encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    out = {}
    for attempt in range(4):
        try:
            r = requests.get("https://api.crossref.org/works/" + doi.replace("https://doi.org/", ""), params={"mailto": config.EMAIL}, timeout=40)
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 200:
            m = r.json()["message"]
            ev = m.get("event") or {}
            out = {"event": ev.get("name", ""), "acronym": ev.get("acronym", ""), "container": (m.get("container-title") or [""])[0], "type": m.get("type", "")}
            break
        if r.status_code == 404:
            break
        time.sleep(2 * (attempt + 1))
    f.write_text(json.dumps(out))
    return out


def norm(s):
    s = re.sub(r"\b(19|20)\d\d\b", " ", str(s).lower())
    s = re.sub(r"\b\d+(st|nd|rd|th)\b|\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b", " ", s)
    s = re.sub(r"\b(proceedings|proceeding|of|the|in|on|and|for|annual|ieee|acm|international|intl|conference|conf|symposium|workshop|joint|asia|pacific|region)\b", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", s)).strip()


def acronym(name):
    m = re.findall(r"\(([A-Za-z][A-Za-z0-9\-& ]{1,14})\)", name)
    return [x.replace(" ", "").upper() for x in m if x.upper() == x or len(x) <= 8]


def load_core():
    rows = [r for r in csv.reader(open(config.ROOT / "data" / "ref" / "core.csv", encoding="utf-8")) if len(r) > 4]
    core = [{"name": r[1].strip(), "acronym": r[2].strip().upper(), "rank": r[4].strip(), "norm": norm(r[1])} for r in rows]
    return [c for c in core if c["norm"]]


def match(name, core):
    n = norm(name)
    if len(n) < 6:
        return None
    acr = set(acronym(name))
    best = (0, None)
    for c in core:
        s = fuzz.token_sort_ratio(n, c["norm"])
        if c["acronym"] in acr and s >= 70:
            s = max(s, 95)
        if s > best[0]:
            best = (s, c)
    return best[1] if best[0] >= 90 else None


def apply_to_tables(d):
    """Write venue_kind / resolved_conference / core_rank into the (faculty-filtered) tables and let a CORE rank override the
    Scopus proceedings quartile for conference papers. Journals get venue_kind 'journal'."""
    keep = d[["openalex_work_id", "venue_kind", "resolved_name", "core_rank"]].rename(columns={"resolved_name": "resolved_conference"})
    keep["core_rank"] = keep.core_rank.where(keep.core_rank.isin(["A*", "A", "B", "C"]), "")
    for f in ("papers_enriched.csv", "group15_data.csv"):
        t = pd.read_csv(OUT / f, dtype=str, keep_default_na=False)
        t = t.drop(columns=[c for c in ("venue_kind", "resolved_conference", "core_rank") if c in t.columns]).merge(keep, on="openalex_work_id", how="left").fillna("")
        t.loc[t.type == "journal", "venue_kind"] = "journal"
        hit = (t.type == "conference") & (t.core_rank != "")
        t.loc[hit, "quartile"] = t.loc[hit, "core_rank"]
        if "quartile_source" in t.columns:
            t.loc[hit, "quartile_source"] = "core"
        t.to_csv(OUT / f, index=False)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    allp = pd.read_csv(OUT / "all_authors" / "papers_enriched.csv", dtype=str, keep_default_na=False)
    c = allp[allp.type == "conference"].copy()
    todo = [d for d in c.doi if d]
    with ThreadPoolExecutor(8) as ex:
        res = dict(zip(todo, ex.map(crossref, todo)))
    core = load_core()
    rows = []
    for r in c.itertuples():
        x = res.get(r.doi, {})
        series = r.journal_name
        cand = x.get("event") or ""
        if not cand and x.get("container") and not GENERIC.search(x["container"]) and norm(x["container"]) != norm(series):
            cand = x["container"]
        if not cand and series and not GENERIC.search(series) and "proceedings" not in series.lower().split()[:1] + ["x"]:
            cand = series
        named = bool(cand) and not GENERIC.search(cand)
        m = match(cand, core) if named else None
        rows.append({"openalex_work_id": r.openalex_work_id, "doi": r.doi, "openalex_venue": series, "crossref_event": x.get("event", ""),
                     "crossref_container": x.get("container", ""), "resolved_name": cand if named else "", "venue_kind": "named conference" if named else "generic series",
                     "core_name": m["name"] if m else "", "core_acronym": m["acronym"] if m else "", "core_rank": m["rank"] if m else ""})
    d = pd.DataFrame(rows)
    # conferences ranked by hand where the name format defeats the matcher (data/ref/core_manual.csv: openalex_work_id, core_rank, core_name, evidence)
    mf = config.ROOT / "data" / "ref" / "core_manual.csv"
    if mf.exists():
        mm = pd.read_csv(mf, dtype=str).set_index("openalex_work_id")
        hit = d.openalex_work_id.isin(mm.index)
        d.loc[hit, "core_rank"] = d.loc[hit, "openalex_work_id"].map(mm.core_rank)
        d.loc[hit, "core_name"] = d.loc[hit, "openalex_work_id"].map(mm.core_name)
    d.to_csv(OUT / "conference_resolved.csv", index=False)

    # who wrote the A*/A papers? (unfiltered corpus: faculty and non-faculty authors)
    full = pd.read_csv(OUT / "all_authors" / "group15_data.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "institution", "author", "is_faculty", "author_role"])
    star = d[d.core_rank.isin(["A*", "A"])]
    authors = []
    for r in star.itertuples():
        a = full[full.openalex_work_id == r.openalex_work_id]
        authors.append({"openalex_work_id": r.openalex_work_id, "core_rank": r.core_rank, "conference": r.core_name, "venue": r.resolved_name,
                        "our_authors": len(a), "faculty_authors": int((a.is_faculty == "TRUE").sum()),
                        "non_faculty_authors": int((a.is_faculty != "TRUE").sum()), "author_roles": ", ".join(sorted(set(a.author_role)))})
    star_tbl = pd.DataFrame(authors)
    star_tbl.to_csv(OUT / "stats" / "core_a_star_a_papers.csv", index=False)
    summary = {"conference_papers_unfiltered": len(d), "named_conference": int((d.venue_kind == "named conference").sum()),
               "generic_series": int((d.venue_kind == "generic series").sum()),
               "core_ranked": d.core_rank.value_counts().to_dict(),
               "a_star_a_papers": len(star_tbl), "a_star_a_with_any_faculty_author": int((star_tbl.faculty_authors > 0).sum()) if len(star_tbl) else 0,
               "a_star_a_without_faculty": int((star_tbl.faculty_authors == 0).sum()) if len(star_tbl) else 0,
               "named_not_in_core": int(((d.venue_kind == "named conference") & (d.core_rank == "")).sum())}
    (OUT / "stats" / "conference_ranking.json").write_text(json.dumps(summary, indent=1))
    apply_to_tables(d)
    cur = pd.read_csv(OUT / "papers_enriched.csv", dtype=str, keep_default_na=False)
    cc = cur[cur.type == "conference"]
    summary["in_final_corpus"] = {"conference_papers": len(cc), "named_conference": int((cc.venue_kind == "named conference").sum()), "generic_series": int((cc.venue_kind == "generic series").sum()),
                                  "core_ranked": cc.core_rank.value_counts().drop("", errors="ignore").to_dict()}
    (OUT / "stats" / "conference_ranking.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
