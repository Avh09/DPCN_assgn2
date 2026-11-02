"""Low-priority rows of faculty_to_verify_updated.csv: faculty on a current faculty page for whom no
OpenAlex author id was matched (reason no_openalex_match). Finds their papers anyway.

For each person:
  1. OpenAlex author search by name (several spellings: as written, surname first, initials)
  2. keeps candidates whose name matches (faculty_match.match, same rule as the pipeline)
  3. downloads the candidate's works 2016-2026 and looks at the RAW affiliation text of the paper
     (the address line as printed). If it names the institute, the person published there even though
     OpenAlex did not link the institute (which is why the paper is not in group15_data.csv).
  4. counts how many of those papers are not in group15_data.csv

Writes faculty_to_verify_low.csv: one row per person with candidate ids, paper counts, example titles.
"""
import json
import re
import time

import pandas as pd
import requests

import config
from faculty_match import match, tokens
from verify_auto import CACHE, OURS, get_json

API = "https://api.openalex.org"
PARAMS = {"api_key": config.API_KEY, "mailto": config.EMAIL}
TITLES = re.compile(r"^(?:ar|dr|prof|mr|mrs|ms)\.?\s+", re.I)


def variants(name):
    n = TITLES.sub("", name).replace(".", ". ").strip()
    n = re.sub(r"\s+", " ", n)
    t = n.split()
    out = {n}
    if len(t) >= 2:
        out.add(" ".join(t[1:] + t[:1]))                    # surname first -> last
        out.add(f"{t[0][0]} {t[-1]}")                         # initial + last word
        out.add(f"{t[-1][0]} {t[0]}")                         # initial of last word + first word
    return list(out)


def candidates(name, inst):
    nt = tokens(name)
    found = {}
    for v in variants(name):
        d = get_json(f"{API}/authors", "lowsearch_" + re.sub(r"\W", "_", v), params={
            **PARAMS, "search": v, "per_page": 25, "select": "id,display_name,works_count,affiliations,last_known_institutions,orcid"})
        for a in (d or {}).get("results") or []:
            an = tokens(a["display_name"])
            if match(nt, an) or match(an, nt) or match(list(reversed(nt)), an):
                found[a["id"].rsplit("/", 1)[-1]] = a
    return found


def works_of(aid):
    out, page = [], 1
    while page <= 3:
        d = get_json(f"{API}/works", f"lowworks_{aid}_{page}", params={
            **PARAMS, "filter": f"author.id:{aid},publication_year:2016-2026", "per_page": 200, "page": page,
            "select": "id,title,publication_year,authorships"})
        res = (d or {}).get("results") or []
        out += res
        if len(res) < 200:
            break
        page += 1
    return out


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    sheet = pd.read_csv("faculty_to_verify_updated.csv", dtype=str, keep_default_na=False)
    low = sheet[sheet.priority == "low"]
    ours = set(pd.read_csv(config.OUT_DIR / "group15_data.csv", dtype=str, usecols=["openalex_work_id"]).openalex_work_id)
    rows = []
    for k, (i, r) in enumerate(low.iterrows(), 1):
        cands = candidates(r["name"], r.institution)
        best = []
        for aid, a in cands.items():
            ws = works_of(aid)
            inst_hits = []
            for w in ws:
                for au in w["authorships"]:
                    if ((au.get("author") or {}).get("id") or "").endswith(aid):
                        raw = " ".join(au.get("raw_affiliation_strings") or [])
                        if OURS[r.institution].search(raw) or any(
                                (ins.get("id") or "").endswith(config.INSTITUTES[r.institution]["openalex_id"])
                                for ins in au.get("institutions") or []):
                            inst_hits.append(w)
            wid = lambda w: w["id"].rsplit("/", 1)[-1]
            best.append({"id": aid, "name": a["display_name"], "works_total": a["works_count"], "works_16_26": len(ws),
                         "at_inst": len(inst_hits), "missing_from_dataset": sum(1 for w in inst_hits if wid(w) not in ours),
                         "examples": " || ".join(f"{w['publication_year']} {w['title'][:70]}" for w in inst_hits[:3]),
                         "last_known": "; ".join((x.get("display_name") or "") for x in a.get("last_known_institutions") or [])[:80]})
        best.sort(key=lambda x: (-x["at_inst"], -x["works_16_26"]))
        rows.append({"institution": r.institution, "name": r["name"], "department": r.department,
                     "n_candidates": len(best), "candidates": json.dumps(best[:4])})
        top = best[0] if best else None
        print(f"[{k}/{len(low)}] {r.institution[:6]} | {r['name']} | cands {len(best)} | "
              f"{'top ' + top['id'] + ' at_inst=' + str(top['at_inst']) + ' of ' + str(top['works_16_26']) if top else '-'}", flush=True)
    pd.DataFrame(rows).to_csv("faculty_to_verify_low.csv", index=False)


if __name__ == "__main__":
    main()
