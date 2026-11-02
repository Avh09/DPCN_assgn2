"""Venue type (journal / conference proceeding / book series) for every ISSN in the corpus, from Scopus.

Why: build_tables.py used to call any venue with "proceedings" in its name a conference. That is wrong for journals
such as Proceedings of the National Academy of Sciences, Proceedings of the Royal Society A, the Proceedings of the
Institution of Mechanical Engineers (Parts A-O) and the Proceedings of the Institution of Civil Engineers. Scopus lists
the type of every source (prism:aggregationType: journal, tradejournal, conferenceproceeding, bookseries, ...), so the
type is taken from there; a few venues the other way round are fixed by data/ref/venue_type_overrides.csv.

Writes data/ref/venue_types.csv (issn, scopus_type, scopus_source_id, scopus_title). Needs ELSEVIER_API_KEY in the
environment (never stored in the repo). Responses are cached in data/raw/scopus_serials/, so reruns are free.
    ELSEVIER_API_KEY=... python venue_types.py
"""
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

import config

REF = config.ROOT / "data" / "ref"
CACHE = config.RAW_DIR / "scopus_serials"


def lookup(issn):
    f = CACHE / ("vt_" + hashlib.md5(issn.encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    out = {}
    for attempt in range(6):
        try:
            r = requests.get(f"https://api.elsevier.com/content/serial/title/issn/{issn}", params={"view": "STANDARD"},
                             headers={"Accept": "application/json", "X-ELS-APIKey": os.environ["ELSEVIER_API_KEY"]}, timeout=60)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 200:
            e = ((r.json().get("serial-metadata-response") or {}).get("entry") or [{}])[0]
            out = {"scopus_type": e.get("prism:aggregationType", ""), "scopus_source_id": e.get("source-id", ""), "scopus_title": e.get("dc:title", "")}
            break
        if r.status_code == 404:
            break
        time.sleep(4 * (attempt + 1) if r.status_code == 429 else 2)
    f.write_text(json.dumps(out))
    time.sleep(0.1)
    return out


def main():
    if not os.environ.get("ELSEVIER_API_KEY"):
        sys.exit("ELSEVIER_API_KEY not set")
    CACHE.mkdir(parents=True, exist_ok=True)
    p = pd.read_csv(config.OUT_DIR / "papers.csv", usecols=["issn", "issn_all"], dtype=str, keep_default_na=False)
    issns = set()
    for a, b in zip(p.issn, p.issn_all):
        issns |= {x.replace("-", "") for x in ([a] + b.split(";")) if x}
    old = pd.read_csv(REF / "venue_types.csv", dtype=str, keep_default_na=False) if (REF / "venue_types.csv").exists() else pd.DataFrame(columns=["issn"])
    have = set(old.issn)
    todo = sorted(issns - have)
    print(f"{len(issns)} ISSNs in the corpus, {len(have)} already typed, {len(todo)} to look up", flush=True)
    rows = old.to_dict("records")
    with ThreadPoolExecutor(6) as ex:                       # the Scopus limit is about 9 requests a second
        for k, (i, r) in enumerate(zip(todo, ex.map(lookup, todo)), 1):
            rows.append({"issn": i, **{c: r.get(c, "") for c in ("scopus_type", "scopus_source_id", "scopus_title")}})
            if k % 250 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    d = pd.DataFrame(rows).drop_duplicates("issn")
    d.to_csv(REF / "venue_types.csv", index=False)
    print(d.scopus_type.replace("", "(not in Scopus)").value_counts().to_string())


if __name__ == "__main__":
    main()
