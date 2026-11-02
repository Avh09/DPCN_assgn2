"""Evidence for the medium-priority rows of faculty_to_verify.csv (the sample its instructions ask
for), from public sources only. Suggests a verdict ONLY when a source states it explicitly.

Sample (as in the checking instructions):
  not_on_any_page      the 30 with the most papers
  identity_risk        30 at random
  mostly_elsewhere     10 at random
  outside_page_window  10 at random
  ambiguous_match      10 at random
(random = fixed seed, so the same rows every run)

Sources:
  ORCID public API      employments and educations (job title, organisation, years), and the name
  OpenAlex author API   affiliation years per institution (context only: shows WHERE someone
                        published, not whether they are faculty)
  faculty_matched.csv   for ambiguous_match: the candidate author records with their topics

Verdict rules (auto_verdict):
  yes     ORCID lists a job at the institute with a faculty title (Professor, Lecturer, Faculty, ...);
          titles with teaching / guest / visiting / adjunct / contract do not count
  no      ORCID lists the person at the institute as scholar / student / fellow / postdoc, or
          (people on no faculty page) lists study at the institute and no job there
  unsure  anything else: no ORCID, empty ORCID, job without a title, other employers only,
          ORCID name does not fit the row's name -> check on Google Scholar
Nothing is written into the sheet's own verified/notes columns.

Writes:
  faculty_to_verify_auto.csv   all 661 rows + sampled, auto_verdict, auto_evidence
  scholar_check_list.csv       sampled rows still unsure, with their Google Scholar link
"""
import json
import re
import time

import pandas as pd
import requests

import config
from faculty_match import match, tokens

SEED = 15
CACHE = config.RAW_DIR / "verify"
OURS = {
    "MANIT Bhopal": re.compile(r"maulana azad national institute|\bmanit\b|national institute of technology,?\s*bhopal|nit,?\s*bhopal", re.I),
    "NIT Jamshedpur": re.compile(r"national institute of technology,?\s*jamshedpur|nit,?\s*jamshedpur|\bnitjsr\b", re.I),
    "NIT Silchar": re.compile(r"national institute of technology,?\s*silchar|nit,?\s*silchar", re.I),
}
SCHOLAR = re.compile(r"scholar|student|ph\.?\s?d|doctoral|fellow|\bjrf\b|\bsrf\b|research assistant|project assistant|"
                     r"teaching assistant|intern|post-?doc|trainee|m\.?\s?tech|b\.?\s?tech", re.I)
# non-regular or unclear posts: never counted as evidence for "yes"
UNCLEAR = re.compile(r"teaching|guest|visiting|adjunct|contract|honorary|emeritus", re.I)
FACULTY = re.compile(r"professor|lecturer|faculty|\bhead\b|\bhod\b|\bdean\b|director|\breader\b", re.I)


def get_json(url, key, headers=None, params=None):
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text())
    for attempt in range(4):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=60)
            if r.status_code == 200:
                f.write_text(r.text)
                time.sleep(0.3)
                return r.json()
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def year(d):
    try:
        return int(d["year"]["value"])
    except (TypeError, KeyError, ValueError):
        return None


def orcid_entries(oid, kind):
    """[(organisation, role, start, end)] from ORCID employments / educations"""
    d = get_json(f"https://pub.orcid.org/v3.0/{oid}/{kind}", f"orcid_{oid}_{kind}", {"Accept": "application/json"})
    out = []
    for g in (d or {}).get("affiliation-group") or []:
        for s in g.get("summaries") or []:
            e = s.get("employment-summary") or s.get("education-summary") or {}
            out.append(((e.get("organization") or {}).get("name") or "", e.get("role-title") or "",
                        year(e.get("start-date")), year(e.get("end-date"))))
    return out


def orcid_name(oid):
    d = get_json(f"https://pub.orcid.org/v3.0/{oid}/person", f"orcid_{oid}_person", {"Accept": "application/json"})
    n = (d or {}).get("name") or {}
    g = ((n.get("given-names") or {}).get("value") or "")
    f = ((n.get("family-name") or {}).get("value") or "")
    return f"{g} {f}".strip()


def span(s, e):
    return f"{s or '?'}-{e or 'present'}"


def openalex_context(aid, inst):
    if not isinstance(aid, str):
        return ""
    a = get_json(f"https://api.openalex.org/authors/{aid.rsplit('/', 1)[-1]}", f"oa_{aid.rsplit('/', 1)[-1]}",
                 params={"api_key": config.API_KEY, "mailto": config.EMAIL,
                         "select": "affiliations,last_known_institutions"})
    if not a:
        return ""
    our_id = config.INSTITUTES[inst]["openalex_id"]
    parts = []
    for af in (a.get("affiliations") or [])[:4]:
        i = af.get("institution") or {}
        ys = sorted(af.get("years") or [])
        tag = " (ours)" if i.get("id", "").endswith(our_id) else ""
        if ys:
            parts.append(f"{i.get('display_name')}{tag} {ys[0]}-{ys[-1]}")
    return "OpenAlex affiliations: " + "; ".join(parts) if parts else ""


def judge(row):
    """(verdict, evidence) for one sampled row"""
    inst, name, reason = row.institution, row["name"], row.reasons
    on_page = row.page_status != "not listed"
    ev = []
    oid = row.orcid.rsplit("/", 1)[-1] if isinstance(row.orcid, str) else None
    verdict = "unsure"
    if oid:
        on = orcid_name(oid)
        name_ok = bool(on) and bool(match(tokens(name), tokens(on)))
        emp, edu = orcid_entries(oid, "employments"), orcid_entries(oid, "educations")
        here_emp = [e for e in emp if OURS[inst].search(e[0])]
        here_edu = [e for e in edu if OURS[inst].search(e[0])]
        ev.append(f"ORCID {oid} name '{on or 'not public'}'" + ("" if name_ok or not on else " (does NOT fit the row's name)"))
        for o, r, s, e in here_emp:
            ev.append(f"ORCID job here: '{r or 'no title'}', {span(s, e)}")
        for o, r, s, e in here_edu:
            ev.append(f"ORCID study here: '{r or 'no title'}', {span(s, e)}")
        others = [f"{o} '{r or 'no title'}' {span(s, e)}" for o, r, s, e in emp if not OURS[inst].search(o)]
        if others:
            ev.append("ORCID other jobs: " + "; ".join(others[:3]))
        if not emp and not edu:
            ev.append("ORCID has no public employment or education")
        if on and not name_ok:
            verdict = "unsure"
        elif any(SCHOLAR.search(r) for o, r, s, e in here_emp):
            verdict = "no"
        elif any(FACULTY.search(r) and not UNCLEAR.search(r) for o, r, s, e in here_emp):
            verdict = "yes"
        elif not on_page and here_edu and not here_emp:
            verdict = "no"
    else:
        ev.append("no ORCID")
    ctx = openalex_context(row.openalex, inst)
    if ctx:
        ev.append(ctx)
    return verdict, " | ".join(ev)


def ambiguous_evidence(row, fm, authors):
    """candidate author records for an ambiguous_match row (no verdict)"""
    r = fm[(fm.institution == row.institution) & (fm.faculty_name == row["name"])]
    ids = sorted({i for s in r.ambiguous_ids.dropna() for i in str(s).split(";") if i})
    if not ids:
        return "unsure", "no candidate author records listed"
    a = authors[(authors.institution == row.institution) & authors.author_id.isin(ids)]
    c = [f"{x.author} ({x.author_id}): {x.papers} papers {x.first_year}-{x.last_year}, main field {x.main_field}"
         for x in a.itertuples()]
    return "unsure", "candidate records (pick the one whose field fits the department): " + "; ".join(c)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv("faculty_to_verify.csv")
    med = d[d.priority == "medium"]
    pick = (list(med[med.reasons == "not_on_any_page"].sort_values("papers", ascending=False).head(30).index)
            + [i for r, n in (("identity_risk", 30), ("mostly_elsewhere", 10), ("outside_page_window", 10),
                              ("ambiguous_match", 10))
               for i in med[med.reasons == r].sample(min(n, (med.reasons == r).sum()), random_state=SEED).index])
    fm = pd.read_csv(config.OUT_DIR / "faculty_matched.csv")
    authors = pd.read_csv(config.OUT_DIR / "authors.csv")
    d["sampled"] = ""
    d["auto_verdict"] = ""
    d["auto_evidence"] = ""
    for k, i in enumerate(pick, 1):
        row = d.loc[i]
        v, e = ambiguous_evidence(row, fm, authors) if row.reasons == "ambiguous_match" else judge(row)
        d.loc[i, ["sampled", "auto_verdict", "auto_evidence"]] = ["yes", v, e]
        print(f"[{k}/{len(pick)}] {row.institution} | {row['name']} | {row.reasons} -> {v}", flush=True)
    d.to_csv("faculty_to_verify_auto.csv", index=False)
    s = d[d.sampled == "yes"]
    s[s.auto_verdict == "unsure"][["institution", "name", "department", "reasons", "papers", "google_scholar",
                                   "openalex", "orcid", "auto_evidence"]].to_csv("scholar_check_list.csv", index=False)
    print("\nsampled:", len(s))
    print(s.groupby(["reasons", "auto_verdict"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
