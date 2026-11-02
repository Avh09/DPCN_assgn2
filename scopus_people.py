"""Scopus check of the people in faculty_to_verify_unsure.csv.

For each row (person, institute):
  1. Scopus Author Search at the institute's affiliation id: surname + first name (also surname-first and
     initial-only spellings) -> candidate Scopus author profiles
  2. Scopus Search for the best candidate's papers at that institute, 2016-2026
  3. Compare those papers (by DOI) with the papers we hold for this person: the faculty member's papers in
     group15_data.csv (matched people) or the OpenAlex author record linked in the sheet (others)

Reading the result (scopus_overlap = share of OUR papers for this person that Scopus also lists under
that one profile at the institute):
  >= 70% with >= 3 papers   same person: Scopus independently agrees with our record  -> scopus_hint 'confirms'
  <= 20% with a profile that has papers at the institute   our record and the profile differ -> 'mismatch'
  profile found, no papers of ours to compare                -> 'profile'   (the person has Scopus papers at the institute)
  no profile at the institute                                -> 'none'

Key from the environment: ELSEVIER_API_KEY=... python scopus_people.py
Writes faculty_to_verify_scopus.csv. Pages are cached in data/raw/scopus_people/ (git-ignored).
"""
import hashlib
import json
import os
import re
import time

import pandas as pd
import requests

import config
from faculty_match import match, tokens

AFID = {"MANIT Bhopal": "60021318", "NIT Jamshedpur": "60029849", "NIT Silchar": "60097223"}
CACHE = config.RAW_DIR / "scopus_people"
HEAD = {"Accept": "application/json"}
TITLES = re.compile(r"^(?:dr|prof|mr|mrs|ms|ar|shri|smt)\.?\s+", re.I)
norm_doi = lambda d: re.sub(r"^https?://(dx\.)?doi\.org/", "", str(d or "").strip().lower())


def get(url, params):
    key = os.environ["ELSEVIER_API_KEY"]
    f = CACHE / (hashlib.md5((url + json.dumps(params, sort_keys=True)).encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    for attempt in range(5):
        r = requests.get(url, params=params, headers={**HEAD, "X-ELS-APIKey": key}, timeout=90)
        if r.status_code == 200:
            f.write_text(r.text)
            time.sleep(0.15)
            return r.json()
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
        else:
            time.sleep(2)
    return None


def name_variants(name):
    n = TITLES.sub("", name.replace(".", " ")).strip()
    t = [x for x in re.split(r"[\s,]+", n) if x]
    if not t:
        return []
    out = []
    if len(t) >= 2 and len(t[-1]) > 1:                       # "First [Middle] Last"
        out.append((t[-1], t[0]))
        out.append((t[0], t[-1]))                              # surname first, e.g. "Maurya Gyanprakash"
    if len(t) >= 2 and len(t[-1]) == 1:                       # "Rajput S P S": surname then initials
        out.append((t[0], t[1]))
    out.append((t[-1], t[0][0]))                               # initial only
    seen, res = set(), []
    for v in out:
        if v not in seen and len(v[0]) > 1:
            seen.add(v)
            res.append(v)
    return res


def candidates(name, inst):
    for last, first in name_variants(name):
        d = get("https://api.elsevier.com/content/search/author", {
            "query": f"AUTHLASTNAME({last}) AND AUTHFIRST({first}) AND AF-ID({AFID[inst]})", "count": 5})
        ents = [e for e in ((d or {}).get("search-results", {}).get("entry") or []) if "dc:identifier" in e]
        if ents:
            return ents
    return []


def papers_at(auid, inst):
    d = get("https://api.elsevier.com/content/search/scopus", {
        "query": f"AU-ID({auid}) AND AF-ID({AFID[inst]}) AND PUBYEAR > 2015 AND PUBYEAR < 2027", "count": 200,
        "field": "prism:doi,dc:title,prism:coverDate"})
    sr = (d or {}).get("search-results", {})
    ents = [e for e in sr.get("entry", []) if "error" not in e]
    return int(sr.get("opensearch:totalResults", 0) or 0), ents


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    sheet = pd.read_csv("faculty_to_verify_unsure.csv", dtype=str, keep_default_na=False)
    m = pd.read_csv(config.OUT_DIR / "group15_data.csv", dtype=str, usecols=["institution", "faculty_name", "author_id", "doi"])
    m["fn"] = m.faculty_name.str.replace(r" \(.*\)$", "", regex=True)
    m["d"] = m.doi.map(norm_doi)
    rows = []
    for k, r in enumerate(sheet.itertuples(index=False), 1):
        ours = set(m[(m.institution == r.institution) & (m.fn == r.name) & (m.d != "")].d)
        if not ours and r.openalex.startswith("http"):
            aid = r.openalex.rsplit("/", 1)[-1]
            ours = set(m[(m.institution == r.institution) & (m.author_id == aid) & (m.d != "")].d)
        cands = candidates(r.name, r.institution)
        best, info = None, []
        for e in cands[:3]:
            auid = e["dc:identifier"].split(":")[1]
            n, ents = papers_at(auid, r.institution)
            dois = {norm_doi(x.get("prism:doi")) for x in ents} - {""}
            pn = e.get("preferred-name") or {}
            info.append({"auid": auid, "name": f"{pn.get('surname', '')}, {pn.get('given-name', '')}", "docs_all": e.get("document-count"),
                         "docs_at_inst_16_26": n, "current": ((e.get("affiliation-current") or {}).get("affiliation-name") or "")[:60],
                         "overlap": len(ours & dois), "dois": dois})
        # a candidate counts only if its Scopus name is compatible with the sheet name (same surname, first names
        # equal or initials); otherwise a namesake with the same surname + first initial would be taken for the person
        nt = tokens(r.name)
        for x in info:
            sn, _, gn = x["name"].partition(", ")
            at = tokens(f"{gn} {sn}")
            x["name_ok"] = bool(match(nt, at) or match(at, nt) or match(list(reversed(nt)), at))
        info = [x for x in info if x["name_ok"]]
        info.sort(key=lambda x: (-x["overlap"], -x["docs_at_inst_16_26"]))
        best = info[0] if info else None
        if best is None:
            hint, share = "none", ""
        else:
            share = round(best["overlap"] / len(ours) * 100) if ours else ""
            if ours and len(ours) >= 3 and share >= 70:
                hint = "confirms"
            elif ours and best["docs_at_inst_16_26"] and share <= 20:
                hint = "mismatch"
            elif not ours and best["docs_at_inst_16_26"]:
                hint = "profile"
            else:
                hint = "partial"
        ev = ("no Scopus author profile at this institute" if best is None else
              f"Scopus AU-ID {best['auid']} '{best['name']}': {best['docs_all']} docs in all, {best['docs_at_inst_16_26']} at the institute 2016-26, "
              f"current affiliation '{best['current']}'; {best['overlap']} of our {len(ours)} papers for this person are in it ({share}%)")
        rows.append({"institution": r.institution, "name": r.name, "department": r.department, "reasons": r.reasons,
                     "scopus_hint": hint, "scopus_au_id": best["auid"] if best else "", "scopus_docs_at_inst": best["docs_at_inst_16_26"] if best else "",
                     "our_papers": len(ours), "scopus_overlap_pct": share, "scopus_evidence": ev,
                     "other_candidates": "; ".join(f"{x['auid']} {x['name']} ({x['docs_at_inst_16_26']} at inst)" for x in info[1:])})
        print(f"[{k}/{len(sheet)}] {r.institution[:6]} | {r.name} | {hint} | {ev[:110]}", flush=True)
    pd.DataFrame(rows).to_csv("faculty_to_verify_scopus.csv", index=False)


if __name__ == "__main__":
    main()
