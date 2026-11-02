"""Scopus vs OpenAlex coverage for our three institutes, 2016-2026.

Downloads Scopus's own list of papers per institute (Scopus Search API, affiliation profile ids below),
then compares it with our dataset (papers_enriched.csv) by DOI, falling back to title for records
without a DOI.

The Elsevier API key is read from the environment variable ELSEVIER_API_KEY (never stored in the repo):
    ELSEVIER_API_KEY=... python scopus_compare.py

Needs: nothing but the key. Scopus pages are cached in data/raw/scopus/ (git-ignored), so a rerun is free.

Writes to data/out/:
  scopus_comparison.csv       institute, year, scopus_docs, openalex_docs, in_both, scopus_only, openalex_only
  scopus_only_papers.csv      Scopus papers (2016-26) that are not in our dataset: DOI, title, year, type, journal, citations
  stats/scopus_results.json   totals and shares
"""
import json
import os
import re
import time

import pandas as pd
import requests

import config

AFID = {"MANIT Bhopal": "60021318", "NIT Jamshedpur": "60029849", "NIT Silchar": "60097223"}
API = "https://api.elsevier.com/content/search/scopus"
CACHE = config.RAW_DIR / "scopus"
OUT = config.OUT_DIR
FIELDS = "dc:identifier,prism:doi,dc:title,prism:coverDate,citedby-count,subtype,subtypeDescription,prism:publicationName,prism:aggregationType"


def norm_doi(d):
    d = str(d or "").strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", d)


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def harvest(inst):
    f = CACHE / f"{inst.replace(' ', '_')}.jsonl"
    if f.exists() and f.stat().st_size > 100:
        return [json.loads(l) for l in f.read_text().splitlines()]
    key = os.environ["ELSEVIER_API_KEY"]
    q = f"AF-ID({AFID[inst]}) AND PUBYEAR > 2015 AND PUBYEAR < 2027"
    cursor, rows = "*", []
    while True:
        for attempt in range(5):
            r = requests.get(API, params={"query": q, "count": 200, "cursor": cursor, "field": FIELDS},
                             headers={"X-ELS-APIKey": key, "Accept": "application/json"}, timeout=90)
            if r.status_code == 200:
                break
            time.sleep(3 * (attempt + 1))
        else:
            raise SystemExit(f"Scopus failed for {inst}: HTTP {r.status_code} {r.text[:200]}")
        d = r.json()["search-results"]
        ents = [e for e in d.get("entry", []) if "error" not in e]
        rows += ents
        total = int(d["opensearch:totalResults"])
        print(f"  {inst}: {len(rows)}/{total}", flush=True)
        nxt = (d.get("cursor") or {}).get("@next")
        if not ents or not nxt or len(rows) >= total:
            break
        cursor = nxt
        time.sleep(0.2)
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(json.dumps(x) for x in rows))
    return rows


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    ours = pd.read_csv(OUT / "papers_enriched.csv", usecols=["openalex_work_id", "doi", "title", "year", "type", "our_institutes"])
    ours = ours[ours.our_institutes.notna()]
    ours["d"] = ours.doi.map(norm_doi)
    ours["t"] = ours.title.map(norm_title)
    comp, only, res = [], [], {}
    for inst in AFID:
        sc = pd.DataFrame(harvest(inst))
        sc["doi"] = sc["prism:doi"].map(norm_doi) if "prism:doi" in sc else ""
        sc["year"] = pd.to_numeric(sc["prism:coverDate"].str[:4])
        sc["t"] = sc["dc:title"].map(norm_title)
        o = ours[ours.our_institutes.str.contains(inst, regex=False)]
        o = o[o.year.between(2016, 2026)]
        odoi, otit = set(o.d[o.d != ""]), set(o.t)
        sc["in_ours"] = [(d != "" and d in odoi) or (d == "" and t in otit) or (t in otit) for d, t in zip(sc.doi, sc.t)]
        sdoi, stit = set(sc.doi[sc.doi != ""]), set(sc.t)
        o = o.assign(in_scopus=[(d != "" and d in sdoi) or (t in stit) for d, t in zip(o.d, o.t)])
        for y in range(2016, 2027):
            a, b = sc[sc.year == y], o[o.year == y]
            comp.append({"institution": inst, "year": y, "scopus_docs": len(a), "openalex_docs": len(b),
                         "in_both": int(a.in_ours.sum()), "scopus_only": int((~a.in_ours).sum()),
                         "openalex_only": int((~b.in_scopus).sum())})
        miss = sc[~sc.in_ours]
        only.append(miss.assign(institution=inst)[["institution", "prism:doi", "dc:title", "year", "subtypeDescription",
                                                    "prism:publicationName", "citedby-count"]])
        res[inst] = {"scopus_docs": len(sc), "openalex_docs": len(o), "scopus_found_in_ours_%": round(sc.in_ours.mean() * 100, 1),
                     "openalex_found_in_scopus_%": round(o.in_scopus.mean() * 100, 1), "scopus_only": len(miss),
                     "scopus_only_by_type": miss.subtypeDescription.value_counts().to_dict(),
                     "scopus_only_citations": int(pd.to_numeric(miss["citedby-count"], errors="coerce").sum())}
        print(inst, res[inst], flush=True)
    pd.DataFrame(comp).to_csv(OUT / "scopus_comparison.csv", index=False)
    pd.concat(only).rename(columns={"prism:doi": "doi", "dc:title": "title", "subtypeDescription": "type",
                                    "prism:publicationName": "journal", "citedby-count": "citations"}
                           ).to_csv(OUT / "scopus_only_papers.csv", index=False)
    (OUT / "stats" / "scopus_results.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
