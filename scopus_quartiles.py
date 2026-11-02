"""Step 4b: fill the quartiles (and venue names / ISSNs) that enrich.py could not find.

enrich.py gives journals an approximate SJR quartile and conferences a CORE rank (A*/A/B/C), and leaves
the rest blank. Here, for every paper still without a quartile, Scopus is asked for the venue:
  1. papers with no venue name or no ISSN: Scopus Search by DOI -> venue name and ISSN
  2. every distinct ISSN: Scopus Serial Title API (view=CITESCORE) -> CiteScore percentile per year
     and subject area. The quartile follows Scopus's own rule on the best subject area:
     percentile >= 75 Q1, >= 50 Q2, >= 25 Q3, below Q4. The paper's own year is used when Scopus has it,
     else the nearest year.
3. venues Scopus has no CiteScore for: a quartile is ESTIMATED from the venue's OpenAlex statistics (h-index,
   2-year mean citedness, works, citations, research field) with a logistic regression trained on the venues
   that do have a real quartile (about 58% exact, 96% within one quartile in 5-fold cross-validation).
   These are marked quartile_source = estimated_openalex; use quartile_source to keep them out of any figure
   that must be exact. Papers whose venue OpenAlex does not know at all stay "Unranked".
Book series that carry conference papers (Lecture Notes in ..., AIP Conference Proceedings, Materials Today
Proceedings) have a CiteScore, so their conference papers get a quartile too. Venues Scopus has no
CiteScore for (e.g. IEEE conference proceedings with no ISSN and no CORE entry) become "Unranked"
(CORE uses the same word), so no cell stays empty.

Adds the column quartile_source to papers_enriched.csv and group15_data.csv:
  sjr_approx         journal quartile from enrich.py (SCImago SJR, recomputed)
  core               conference rank from CORE 2023
  scopus_citescore   filled here from Scopus CiteScore
  estimated_openalex quartile estimated from OpenAlex venue statistics (see 3.)
  estimated_publisher venue unknown to OpenAlex: most common quartile of the same publisher's other venues (weak guess)
  none               no rank exists for this venue ("Unranked")
Also fills blank journal_name / issn from Scopus (by DOI), then from Crossref (journal papers only; conference
papers have no ISSN unless the proceedings are a book series), and adds venue_h_index and venue_citedness
(OpenAlex source statistics) for every paper.

Key from the environment: ELSEVIER_API_KEY=... python scopus_quartiles.py
Responses are cached in data/raw/scopus_serials/ (git-ignored), so a rerun is free.
"""
import hashlib
import json
import os
import re
import sys
import time

import pandas as pd
import requests

import config

OUT = config.OUT_DIR
CACHE = config.RAW_DIR / "scopus_serials"
H = {"Accept": "application/json"}


def get(url, params):
    f = CACHE / (hashlib.md5((url + json.dumps(params, sort_keys=True)).encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    for attempt in range(8):
        try:
            r = requests.get(url, params=params, headers={**H, "X-ELS-APIKey": os.environ["ELSEVIER_API_KEY"]}, timeout=90)
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code in (200, 404):
            d = r.json() if r.status_code == 200 else {}
            f.write_text(json.dumps(d))
            time.sleep(0.12)
            return d
        time.sleep(5 * (attempt + 1) if r.status_code == 429 else 2)
    return {}


def quartile_of(pct):
    return "Q1" if pct >= 75 else "Q2" if pct >= 50 else "Q3" if pct >= 25 else "Q4"


def serial_quartiles(issn):
    """{year: 'Q1'..'Q4'} for one ISSN from Scopus CiteScore percentiles (best subject area), or {}."""
    d = get(f"https://api.elsevier.com/content/serial/title/issn/{issn.replace('-', '')}", {"view": "CITESCORE"})
    ents = (d.get("serial-metadata-response") or {}).get("entry") or []
    if not ents:
        return {}
    done, other = {}, {}
    for yi in (ents[0].get("citeScoreYearInfoList") or {}).get("citeScoreYearInfo") or []:
        pcts = []
        for info in yi.get("citeScoreInformationList") or []:
            for ci in info.get("citeScoreInfo") or []:
                pcts += [float(s["percentile"]) for s in ci.get("citeScoreSubjectRank") or [] if s.get("percentile") not in (None, "")]
        if pcts:
            (done if yi.get("@status") == "Complete" else other)[int(yi["@year"])] = quartile_of(max(pcts))
    return done or other


def crossref_title(title, year):
    """(journal name, issn) for a paper without DOI: Crossref bibliographic search, accepted only when the title
    is near-identical (similarity >= 0.92) and the year is within 1. Also returns the DOI so a paper without one gets it."""
    from difflib import SequenceMatcher
    f = CACHE / ("crt2_" + hashlib.md5((title + str(year)).encode()).hexdigest() + ".json")
    if f.exists():
        d = json.loads(f.read_text())
    else:
        d = {}
        for attempt in range(3):
            try:
                r = requests.get("https://api.crossref.org/works", params={"query.bibliographic": title, "rows": 3,
                                 "select": "title,container-title,ISSN,issued,DOI", "mailto": config.EMAIL}, timeout=40)
                d = r.json().get("message", {}) if r.status_code == 200 else {}
                if r.status_code in (200, 404):
                    break
            except (requests.RequestException, ValueError):
                time.sleep(3)
        f.write_text(json.dumps(d))
        time.sleep(0.05)
    for it in d.get("items") or []:
        t = (it.get("title") or [""])[0]
        y = ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]
        if t and SequenceMatcher(None, t.lower(), title.lower()).ratio() >= 0.92 and (y is None or abs(int(y) - int(year)) <= 1):
            return (it.get("container-title") or [""])[0], (it.get("ISSN") or [""])[0], it.get("DOI") or ""
    return "", "", ""


def doi_lookup(doi):
    d = get("https://api.elsevier.com/content/search/scopus", {
        "query": f"DOI({doi.replace('https://doi.org/', '')})", "count": 1,
        "field": "prism:publicationName,prism:issn,prism:eIssn,prism:aggregationType"})
    e = ((d.get("search-results") or {}).get("entry") or [{}])[0]
    return None if "error" in e else e


def work_sources(ids):
    """work id -> OpenAlex source id (read from the raw download once, then cached)."""
    f = config.RAW_DIR / "sources" / "work_source.csv"
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        if set(ids) <= set(d.openalex_work_id):
            return dict(zip(d.openalex_work_id, d.source_id))
    rows = {}
    for fn in sorted(config.RAW_DIR.glob("works_*.json")):
        for w in json.loads(fn.read_text())["results"]:
            s = (w.get("primary_location") or {}).get("source") or {}
            rows[w["id"].rsplit("/", 1)[-1]] = (s.get("id") or "").rsplit("/", 1)[-1]
    pd.DataFrame({"openalex_work_id": list(rows), "source_id": list(rows.values())}).to_csv(f, index=False)
    return rows


def openalex_sources(ids):
    """OpenAlex source objects (statistics) for the given source ids, cached in data/raw/sources/sources.jsonl."""
    f = config.RAW_DIR / "sources" / "sources.jsonl"
    have = {}
    if f.exists():
        for line in f.read_text().splitlines():
            o = json.loads(line)
            have[o["id"].rsplit("/", 1)[-1]] = o
    todo = [i for i in ids if i and i not in have]
    with f.open("a") as out:
        for k in range(0, len(todo), 50):
            ch = todo[k:k + 50]
            for a in range(5):
                r = requests.get("https://api.openalex.org/sources", params={
                    "filter": "openalex_id:" + "|".join(ch), "per_page": 50, "api_key": config.API_KEY, "mailto": config.EMAIL,
                    "select": "id,display_name,type,issn_l,issn,works_count,cited_by_count,summary_stats"}, timeout=60)
                if r.status_code == 200:
                    break
                time.sleep(2 ** a)
            for o in r.json().get("results", []):
                out.write(json.dumps(o) + "\n")
                have[o["id"].rsplit("/", 1)[-1]] = o
    return have


def crossref(doi):
    """(journal name, issn) from Crossref for one DOI, or ('', '')."""
    f = CACHE / ("cr_" + hashlib.md5(doi.encode()).hexdigest() + ".json")
    if f.exists():
        d = json.loads(f.read_text())
    else:
        d = {}
        for attempt in range(3):
            try:
                r = requests.get("https://api.crossref.org/works/" + doi.replace("https://doi.org/", ""),
                                 params={"mailto": config.EMAIL}, timeout=40)
                d = r.json().get("message", {}) if r.status_code == 200 else {}
                if r.status_code in (200, 404):
                    break
            except (requests.RequestException, ValueError):
                time.sleep(3)
        f.write_text(json.dumps(d))
        time.sleep(0.05)
    issn = (d.get("ISSN") or [""])[0]
    return (d.get("container-title") or [""])[0], issn


def estimate_quartiles(p, src):
    """Estimated quartile for venues without a real one, from OpenAlex statistics. Returns (Series of 'Q1'..'Q4' or '' per row, cv accuracy)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict
    v = p.drop_duplicates("source_id")
    v = v[v.source_id != ""].copy()
    st = {}
    for sid in v.source_id:
        o = src.get(sid)
        if o:
            s = o.get("summary_stats") or {}
            st[sid] = [s.get("h_index"), s.get("2yr_mean_citedness"), s.get("i10_index"), o.get("works_count"),
                       o.get("cited_by_count"), 1.0 if o.get("type") == "conference" else 0.0]
    v = v[v.source_id.isin(st)]
    num = pd.DataFrame([st[s] for s in v.source_id], columns=["h", "cit", "i10", "w", "cb", "conf"], index=v.index).astype(float).fillna(0)
    X = pd.DataFrame({"lh": np.log1p(num.h), "lc": np.log(num.cit + 0.05), "li": np.log1p(num.i10), "lw": np.log1p(num.w),
                      "lcb": np.log1p(num.cb), "conf": num.conf}, index=v.index)
    X = pd.concat([X, pd.get_dummies(v.field, prefix="f").astype(float)], axis=1)
    known = v.quartile.str.startswith("Q") & (v.quartile_source != "estimated_openalex")
    model = LogisticRegression(max_iter=3000)
    y = v.quartile[known]
    cv = cross_val_predict(model, X[known], y, cv=5)
    n = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
    d = pd.Series(cv, index=y.index).map(n) - y.map(n)
    acc = (round(float((d == 0).mean()), 3), round(float((d.abs() <= 1).mean()), 3))
    model.fit(X[known], y)
    pred = pd.Series(model.predict(X[~known]), index=X[~known].index)
    est = dict(zip(v.loc[pred.index, "source_id"], pred))
    return est, acc, st


OWN = re.compile(r"maulana azad|manit|national institute of technology,? (silchar|jamshedpur|bhopal)|nit (silchar|jamshedpur)", re.I)


def fill_coauthor_institutes(m):
    """Rows whose paper lists no other institution although some author has NO affiliation in OpenAlex: ask Scopus
    (search by DOI, affiliation list) and use the institutions it names, minus our own. Changes m in place."""
    a = pd.read_csv(OUT / "authorships.csv", usecols=["openalex_work_id", "institution_names"], keep_default_na=False)
    unknown = set(a[a.institution_names == ""].openalex_work_id)
    rows = m[(m.coauthor_institutes == "") & m.openalex_work_id.isin(unknown) & (m.doi != "")]
    papers = rows.drop_duplicates("openalex_work_id")
    print("papers with an unknown co-author affiliation, looked up in Scopus:", len(papers), flush=True)
    names = {}
    for k, (wid, doi) in enumerate(zip(papers.openalex_work_id, papers.doi), 1):
        d = get("https://api.elsevier.com/content/search/scopus", {
            "query": f"DOI({doi.replace('https://doi.org/', '')})", "count": 1, "field": "affiliation"})
        e = ((d.get("search-results") or {}).get("entry") or [{}])[0]
        found = [x.get("affilname") for x in (e.get("affiliation") or []) if x.get("affilname") and not OWN.search(x["affilname"])]
        if found:
            names[wid] = ";".join(dict.fromkeys(found))
        if k % 300 == 0:
            print(f"  {k}/{len(papers)}", flush=True)
    idx = m.openalex_work_id.map(names)
    ok = (m.coauthor_institutes == "") & idx.notna()
    m.loc[ok, "coauthor_institutes"] = idx[ok]
    print("co-author institutions found in Scopus for", len(names), "papers (", int(ok.sum()), "rows )")


def main():
    if not os.environ.get("ELSEVIER_API_KEY"):
        print("ELSEVIER_API_KEY not set: skipping (quartiles stay as enrich.py left them)")
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str, "issn_all": str, "quartile": str}, keep_default_na=False)
    # idempotent: a rerun keeps real ranks (core / sjr_approx / scopus_citescore) and redoes "Unranked" and estimates
    prev = p.quartile_source if "quartile_source" in p.columns else None
    p = p.drop(columns=[c for c in ["quartile_source", "source_id", "venue_h_index", "venue_citedness"] if c in p.columns])
    if prev is not None:
        redo = prev.isin(["none", "estimated_openalex", "estimated_publisher"])
        p.loc[redo, "quartile"] = ""
        p["quartile_source"] = prev.where(~redo, "")
    else:
        p["quartile_source"] = ["sjr_approx" if q.startswith("Q") else "core" if q else "" for q in p.quartile]

    # 1. venue from the DOI where OpenAlex gave none
    need = p[((p.journal_name == "") | ((p.type == "journal") & (p.issn == ""))) & (p.doi != "")]
    print("DOI lookups:", len(need), flush=True)
    found = {}
    for k, (i, r) in enumerate(need.iterrows(), 1):
        e = doi_lookup(r.doi)
        if e:
            found[i] = e
        if k % 200 == 0:
            print(f"  {k}/{len(need)}", flush=True)
    for i, e in found.items():
        if p.at[i, "journal_name"] == "" and e.get("prism:publicationName"):
            p.at[i, "journal_name"] = e["prism:publicationName"]
        iss = [x for x in (e.get("prism:issn"), e.get("prism:eIssn")) if x]
        if iss and p.at[i, "issn"] == "":
            p.at[i, "issn"] = iss[0] if len(iss[0]) == 9 else f"{iss[0][:4]}-{iss[0][4:]}"
        if iss and p.at[i, "issn_all"] == "":
            p.at[i, "issn_all"] = ";".join(f"{x[:4]}-{x[4:]}" if len(x) == 8 else x for x in iss)
    print("venue found through DOI:", len(found), "of", len(need), flush=True)
    nod = p[(p.journal_name == "") & (p.doi == "")]
    k2 = 0
    for i, r in nod.iterrows():
        nm, iss, doi = crossref_title(r.title, r.year)
        if doi and p.at[i, "doi"] == "" and ("https://doi.org/" + doi.lower()) not in set(p.doi):   # never create a duplicate DOI
            p.at[i, "doi"] = "https://doi.org/" + doi.lower()
        if nm:
            p.at[i, "journal_name"] = nm
            k2 += 1
            if iss and p.at[i, "issn"] == "":
                p.at[i, "issn"] = iss if len(iss) == 9 else f"{iss[:4]}-{iss[4:]}"
                p.at[i, "issn_all"] = p.at[i, "issn"]
    print("venue found for papers without DOI (Crossref title search):", k2, "of", len(nod), flush=True)

    # 2. quartile per ISSN
    todo = p[p.quartile == ""]
    issns = {}
    for i, r in todo.iterrows():
        xs = [x for x in (r.issn_all.split(";") if r.issn_all else []) + ([r.issn] if r.issn else []) if x]
        issns[i] = list(dict.fromkeys(xs))
    distinct = sorted({x for v in issns.values() for x in v})
    print("papers without quartile:", len(todo), "| distinct ISSNs to look up:", len(distinct), flush=True)
    sq = {}
    for k, x in enumerate(distinct, 1):
        sq[x] = serial_quartiles(x)
        if k % 100 == 0:
            print(f"  {k}/{len(distinct)}", flush=True)
    filled = 0
    for i, xs in issns.items():
        y = int(p.at[i, "year"])
        for x in xs:
            yrs = sq.get(x)
            if yrs:
                p.at[i, "quartile"] = yrs[min(yrs, key=lambda k: abs(k - min(y, max(yrs))))]
                p.at[i, "quartile_source"] = "scopus_citescore"
                filled += 1
                break
    print(f"filled from Scopus CiteScore: {filled}", flush=True)

    # 3. venue statistics (every paper) and an estimated quartile where no real one exists
    ws = work_sources(set(p.openalex_work_id))
    p["source_id"] = p.openalex_work_id.map(ws).fillna("")
    src = openalex_sources(sorted(set(p.source_id) - {""}))
    unr = p.quartile == ""
    tmp = p.assign(quartile=p.quartile.where(~unr, ""))
    est, acc, st = estimate_quartiles(tmp, src)
    hit = unr & p.source_id.isin(est)
    p.loc[hit, "quartile"] = p.loc[hit, "source_id"].map(est)
    p.loc[hit, "quartile_source"] = "estimated_openalex"
    p["venue_h_index"] = p.source_id.map(lambda s: (st.get(s) or [None])[0])
    p["venue_citedness"] = p.source_id.map(lambda s: (st.get(s) or [None, None])[1])
    # venues OpenAlex does not know (mostly IEEE conference proceedings known only by name): the most common
    # quartile of the venues with the same DOI publisher prefix and paper type (needs >= 5 such venues)
    pref = p.doi.str.replace("https://doi.org/", "", regex=False).str.split("/").str[0]
    got = p.quartile.str.startswith("Q") & (p.source_id != "")
    base = p[got].assign(pref=pref[got]).drop_duplicates(["pref", "source_id"])
    mode = {}
    for (pr, t), g in base.groupby(["pref", "type"]):
        if pr and len(g) >= 5:
            mode[(pr, t)] = g.quartile.value_counts().idxmax()
    todo = (p.quartile == "") & (pref != "")
    guess = pd.Series([mode.get((a, t), "") for a, t in zip(pref, p.type)], index=p.index)
    h2 = todo & (guess != "")
    p.loc[h2, "quartile"] = guess[h2]
    p.loc[h2, "quartile_source"] = "estimated_publisher"
    print("estimated from the publisher's other venues:", int(h2.sum()), flush=True)
    left = p.quartile == ""
    p.loc[left, "quartile"] = "Unranked"
    p.loc[left, "quartile_source"] = "none"
    print(f"estimated from OpenAlex venue statistics: {int(hit.sum())} (cross-validated exact/within-one: {acc}) | "
          f"venue unknown, Unranked: {int(left.sum())}", flush=True)

    # 4. ISSN / venue name from Crossref for journal papers that still have none
    need = p[(p.type == "journal") & ((p.issn == "") | (p.journal_name == "")) & (p.doi != "")]
    got = 0
    for i, r in need.iterrows():
        nm, iss = crossref(r.doi)
        if nm and p.at[i, "journal_name"] == "":
            p.at[i, "journal_name"] = nm
            got += 1
        if iss and p.at[i, "issn"] == "":
            p.at[i, "issn"] = iss if len(iss) == 9 else f"{iss[:4]}-{iss[4:]}"
            got += 1
    print("journal ISSN / name filled from Crossref:", got, "of", len(need), "papers checked", flush=True)
    print(p.groupby(["type", "quartile_source"]).size().unstack(fill_value=0).to_string())
    p.to_csv(OUT / "papers_enriched.csv", index=False)

    # 3. onto the rows of group15_data.csv (one row per paper x author x institute)
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False)
    m = m.drop(columns=[c for c in ["quartile_source", "venue_h_index", "venue_citedness"] if c in m.columns])
    pp = p.set_index("openalex_work_id")
    for col in ["quartile", "quartile_source", "venue_h_index", "venue_citedness"]:
        m[col] = m.openalex_work_id.map(pp[col])
    for col in ["journal_name", "issn", "doi"]:
        fill = m.openalex_work_id.map(pp[col]).fillna("")
        m[col] = [a if a else b for a, b in zip(m[col], fill)]
    fill_coauthor_institutes(m)
    m.to_csv(OUT / "group15_data.csv", index=False)
    print("group15_data.csv blanks now: quartile", int((m.quartile == "").sum()), "| journal_name", int((m.journal_name == "").sum()),
          "| issn", int((m.issn == "").sum()))


if __name__ == "__main__":
    main()
