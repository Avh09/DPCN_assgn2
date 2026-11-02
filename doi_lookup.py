"""Find DOIs for papers that OpenAlex lists without one (Crossref bibliographic search by title, year and venue).

Writes data/out/stats/no_doi_candidates.csv with every candidate and how well it matches, and data/ref/doi_overrides.csv with the
matches that are safe to apply automatically (title similarity >= 97, year within 1, venue similarity >= 70). build_tables.py
reads doi_overrides.csv, so a rerun keeps them. The rest are left for a manual check (column `status`).
Responses are cached in data/raw/crossref_doi/. No key is needed.
"""
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from rapidfuzz import fuzz

import config

OUT = config.OUT_DIR
CACHE = config.RAW_DIR / "crossref_doi"
H = {"User-Agent": "DPCN-Group15-research (mailto:madhuram.ind12@gmail.com)"}
norm = lambda s: re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def search(title, year):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.md5(f"{title}|{year}".encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    for a in range(4):
        try:
            r = requests.get("https://api.crossref.org/works", headers=H, timeout=40,
                             params={"query.bibliographic": title, "rows": 4, "select": "DOI,title,container-title,issued,type"})
        except requests.RequestException:
            time.sleep(5 * (a + 1))
            continue
        if r.status_code == 200:
            d = r.json()["message"]["items"]
            f.write_text(json.dumps(d))
            return d
        time.sleep(5 * (a + 1))
    return []


def main():
    p = pd.read_csv(OUT / "papers_enriched.csv", dtype=str, keep_default_na=False)
    nd = p[p.doi == ""]
    rows = []

    def work(r):
        out = []
        for it in search(r.title, r.year):
            t = (it.get("title") or [""])[0]
            cont = (it.get("container-title") or [""])[0]
            y = ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            out.append({"openalex_work_id": r.openalex_work_id, "title": r.title, "year": r.year, "venue": r.journal_name, "candidate_doi": it["DOI"],
                        "candidate_title": t, "candidate_venue": cont, "candidate_year": y,
                        "title_similarity": round(fuzz.ratio(norm(r.title), norm(t)), 1), "venue_similarity": round(fuzz.token_set_ratio(norm(r.journal_name), norm(cont)), 1)})
        return out
    with ThreadPoolExecutor(6) as ex:
        for res in ex.map(work, list(nd.itertuples())):
            rows += res
    c = pd.DataFrame(rows)
    c["year_ok"] = [bool(pd.notna(b) and abs(int(a) - int(b)) <= 1) for a, b in zip(c.year, c.candidate_year)]
    best = c.sort_values("title_similarity", ascending=False).drop_duplicates("openalex_work_id")
    best["status"] = ["apply" if (t >= 97 and y and v >= 70) or (t >= 99 and v >= 95) else "check manually" if t >= 85 else "no match" for t, y, v in zip(best.title_similarity, best.year_ok, best.venue_similarity)]
    best.to_csv(OUT / "stats" / "no_doi_candidates.csv", index=False)
    ok = best[best.status == "apply"]
    ok[["openalex_work_id", "candidate_doi"]].rename(columns={"candidate_doi": "doi"}).to_csv(config.ROOT / "data" / "ref" / "doi_overrides.csv", index=False)
    print(f"{len(nd)} papers without DOI | apply {len(ok)} | check manually {(best.status == 'check manually').sum()} | no match {(best.status == 'no match').sum()}")


if __name__ == "__main__":
    main()
