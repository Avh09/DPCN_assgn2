"""Second round of evidence for the sampled rows that verify_auto.py left 'unsure'.

1. Faculty pages: the person's entry on the institute's own faculty pages (MANIT live pages
   plus all archived copies in data/raw/wayback/), with its research area and email.
2. OpenAlex: the person's MAIN author record (most papers; the sheet sometimes links a small,
   merged record), with its topics and affiliation years.
3. ORCID search by name + institute, for people without an ORCID in the sheet. Used only when
   exactly ONE profile matches both the name and the institute.

Suggests 'yes' only when
  (a) the person is on the institute's faculty page, the page's research area and the OpenAlex
      topics share at least 2 specific keywords, and the record has papers from the institute in
      at least 2 different years (or the research area shares 3+ keywords); or
  (b) a uniquely matching ORCID profile lists a faculty job at the institute AND the person
      appears on a faculty page (a name-only ORCID match is not enough on its own), and the
      page's research area does not contradict the record's topics (no shared keyword at all).
Suggests 'no' only when a uniquely matching ORCID profile lists the person at the institute as
scholar/student/fellow/postdoc. Everything else stays 'unsure', with the evidence shown.

Reads faculty_to_verify_auto.csv (from verify_auto.py), rewrites it with new columns
page_research, page_email, openalex_topics, and updates auto_verdict / auto_evidence.
Rewrites scholar_check_list.csv with the rows still unsure.
"""
import glob
import html
import json
import re
from collections import defaultdict

import pandas as pd
import requests
import urllib3

import config
from faculty_match import match, match_page_name, tokens
from scrape_faculty import MANIT_DEPTS
from scrape_former_faculty import TITLE_NAME
from verify_auto import CACHE, FACULTY, OURS, SCHOLAR, UNCLEAR, get_json, orcid_entries, span

urllib3.disable_warnings()
HEAD = {"User-Agent": "Mozilla/5.0 (research project; faculty check for a bibliometrics course)"}
GENERIC = set("""engineering analysis system systems application applications design study studies technology
technologies method methods based research science sciences property properties advanced using use
modeling modelling model models development process processes control management performance
optimization optimisation evaluation characterization characterisation material materials and of the in
for with on its their new novel various area areas field fields interest interests specialization theory
techniques technique approach approaches structure structures environmental energy mechanical electrical
electronics electronic chemistry chemical physics mathematics computer civil water power data network
networks""".split())
RESEARCH = re.compile(r"(?:Research\s*Area|Area\s*of\s*(?:Interest|specialization)[^:]*|Interests?|Specialization|"
                      r"Research\s*Interests?)\s*[:\-]+\s*(.{3,300}?)(?=\s*(?:E-?mail|Phone|Mobile|More Information|"
                      r"Experience|Date of|Qualification|Designation|Contact|View Profile|$))", re.I)
EMAIL = re.compile(r"([A-Za-z0-9._\-]+)\s*(?:@|\[at\]|\(at\))\s*([A-Za-z0-9.\-\[\]]+)", re.I)


def stem(w):
    for suf in ("ations", "ation", "ings", "ing", "ies", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def keywords(text):
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", "", (text or "").lower())    # "turbo-machines" -> "turbomachines"
    return {stem(w) for w in re.findall(r"[a-z]+", text) if len(w) >= 4 and w not in GENERIC}


def shared_keywords(a, b):
    """keywords of a that also occur in b; long words count as shared when they start the same
    ("turbomachin|es" ~ "turbomachin|ery")"""
    return {x for x in a if x in b or (len(x) >= 7 and any(len(y) >= 7 and x[:7] == y[:7] for y in b))}


def page_texts():
    """{institution: [page text, ...]} from MANIT live pages and all archived copies"""
    docs = defaultdict(list)
    for dept, path in MANIT_DEPTS.items():
        f = CACHE / f"live_manit_{path.strip('/').replace('/', '_')}.html"
        if not f.exists():
            try:
                f.write_text(requests.get("https://www.manit.ac.in" + path, headers=HEAD, timeout=60, verify=False).text)
            except requests.RequestException:
                continue
        docs["MANIT Bhopal"].append(f.read_text(errors="ignore"))
    wb = config.RAW_DIR / "wayback"
    for f in glob.glob(str(wb / "*.html")):
        h = open(f, errors="ignore").read()
        # by web address, not by words in the text ("humanities" contains "manit")
        low = h.lower()
        hits = {i: low.count(dom) for i, dom in (("MANIT Bhopal", "manit.ac.in"), ("NIT Jamshedpur", "nitjsr.ac.in"),
                                                  ("NIT Silchar", "nits.ac.in"))}
        inst = max(hits, key=hits.get) if max(hits.values()) else None
        if inst:
            docs[inst].append(h)
    clean = lambda h: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(
        r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", h, flags=re.S))))
    return {i: [clean(h) for h in hs] for i, hs in docs.items()}


def find_entry(texts, name):
    """research areas and emails in the person's entries on the pages"""
    nt = tokens(name)
    research, emails, found = set(), set(), 0
    for t in texts:
        for m in TITLE_NAME.finditer(t):
            if not match_page_name(tokens(m.group(1)), nt):     # "Ashish Kumar Sahu" is not "Ashish Kumar"
                continue
            found += 1
            # the entry ends where the next DIFFERENT person starts
            end = min(len(t), m.end() + 900)
            for n2 in TITLE_NAME.finditer(t, m.end(), end):
                if not match_page_name(tokens(n2.group(1)), nt):
                    end = n2.start()
                    break
            seg = t[m.end():end]
            research |= {r.strip(" ,.;") for r in RESEARCH.findall(seg)}
            emails |= {f"{a}@{b}".replace("[dot]", ".") for a, b in EMAIL.findall(seg)}
    return found, research, emails


def openalex_main(row, amap):
    ids = list(amap[(amap.institution == row.institution) & (amap.faculty_name == row["name"])]
               .sort_values("papers", ascending=False).author_id)
    if not ids and isinstance(row.openalex, str):
        ids = [row.openalex.rsplit("/", 1)[-1]]
    ids = [i for i in ids if str(i).startswith("A")]
    if not ids:
        return None, [], False, ""
    main = ids[0]
    a = get_json(f"https://api.openalex.org/authors/{main}", f"oa2_{main}",
                 params={"api_key": config.API_KEY, "mailto": config.EMAIL,
                         "select": "display_name,topics,affiliations,works_count"}) or {}
    topics = [t["display_name"] for t in (a.get("topics") or [])[:8]]
    our = config.INSTITUTES[row.institution]["openalex_id"]
    yrs = [y for af in a.get("affiliations") or [] if (af.get("institution") or {}).get("id", "").endswith(our)
           for y in af.get("years") or []]
    here = f"{min(yrs)}-{max(yrs)}" if yrs else ""
    return main, topics, bool(yrs), here


def orcid_search(name, inst):
    """the ORCID iD of the ONE public profile matching name + institute, else None"""
    nt = tokens(name)
    if len(nt) < 2:
        return None, 0
    org = {"MANIT Bhopal": '"Maulana Azad National Institute of Technology" OR MANIT',
           "NIT Jamshedpur": '"National Institute of Technology Jamshedpur"',
           "NIT Silchar": '"National Institute of Technology Silchar"'}[inst]
    q = f'family-name:{nt[-1]} AND affiliation-org-name:({org})'
    d = get_json("https://pub.orcid.org/v3.0/expanded-search/", "osearch_" + re.sub(r"\W", "_", f"{name}_{inst}"),
                 {"Accept": "application/json"}, {"q": q, "rows": 50}) or {}
    hits = []
    for r in d.get("expanded-result") or []:
        full = f"{r.get('given-names') or ''} {r.get('family-names') or ''}"
        if match(tokens(full), nt) and any(OURS[inst].search(x or "") for x in r.get("institution-name") or []):
            hits.append(r["orcid-id"])
    return (hits[0] if len(hits) == 1 else None), len(hits)


def main():
    d = pd.read_csv("faculty_to_verify_auto.csv")
    amap = pd.read_csv(config.OUT_DIR / "author_faculty_map.csv")
    docs = page_texts()
    print("page texts:", {k: len(v) for k, v in docs.items()})
    for c in ("page_research", "page_email", "openalex_topics"):
        d[c] = d.get(c, "")
        d[c] = d[c].fillna("").astype(str)
    todo = d[(d.sampled == "yes") & (d.auto_verdict == "unsure") & (d.reasons != "ambiguous_match")].index
    for k, i in enumerate(todo, 1):
        row = d.loc[i]
        ev = [row.auto_evidence]
        verdict = "unsure"
        found, research, emails = find_entry(docs.get(row.institution, []), row["name"])
        main_id, topics, here, here_yrs = openalex_main(row, amap)
        d.loc[i, "page_research"] = " / ".join(sorted(research))[:400]
        d.loc[i, "page_email"] = ", ".join(sorted(emails))[:150]
        d.loc[i, "openalex_topics"] = "; ".join(topics)
        shared = shared_keywords(keywords(" ".join(research)), keywords(" ".join(topics)))
        conflict = bool(found and research and topics and not shared)   # page research and record topics share nothing
        if found:
            ev.append(f"faculty page: found ({found} entries); research '{d.loc[i, 'page_research'][:120]}'")
            ev.append(f"main OpenAlex record {main_id}: at institute {here_yrs or 'no'}; topics {topics[:4]}")
            ev.append(f"shared keywords: {sorted(shared) or 'none'}")
            n_years = len(set(range(int(here_yrs.split("-")[0]), int(here_yrs.split("-")[1]) + 1))) if here_yrs else 0
            if len(shared) >= 2 and here and row.page_status != "not listed" and (n_years >= 2 or len(shared) >= 3):
                verdict = "yes"
        else:
            ev.append("faculty page: no entry found")
        if verdict == "unsure" and not isinstance(row.orcid, str):
            oid, n = orcid_search(row["name"], row.institution)
            if oid:
                here_emp = [e for e in orcid_entries(oid, "employments") if OURS[row.institution].search(e[0])]
                for o, r, s, e in here_emp:
                    ev.append(f"ORCID {oid} (found by name+institute search) job here: '{r or 'no title'}', {span(s, e)}")
                if any(SCHOLAR.search(r) for o, r, s, e in here_emp):
                    verdict = "no"
                elif any(FACULTY.search(r) and not UNCLEAR.search(r) for o, r, s, e in here_emp):
                    # a profile found by NAME only counts if the person is also on a faculty page
                    if conflict:
                        ev.append("ORCID says faculty, but the record's topics share nothing with the page's research "
                                  "area (record may mix two people): check")
                    elif found or row.page_status != "not listed":
                        verdict = "yes"
                    else:
                        ev.append("ORCID found by name says faculty, but the person is on no faculty page: check")
                elif not here_emp:
                    ev.append(f"ORCID {oid} (name+institute search) lists no job here")
            else:
                ev.append(f"ORCID search: {n} matching profiles" + (" (not unique, not used)" if n > 1 else ""))
        d.loc[i, "auto_verdict"] = verdict
        d.loc[i, "auto_evidence"] = " | ".join(x for x in ev if x)
        print(f"[{k}/{len(todo)}] {row.institution} | {row['name']} | {row.reasons} -> {verdict}", flush=True)
    d.to_csv("faculty_to_verify_auto.csv", index=False)
    s = d[d.sampled == "yes"]
    # name and the Scholar link first, then the two columns to fill in, then the evidence
    order = {"not_on_any_page": 0, "identity_risk": 1, "mostly_elsewhere": 2, "outside_page_window": 3, "ambiguous_match": 4}
    out = s[s.auto_verdict == "unsure"].assign(verified="", notes="")
    out = out.assign(_o=out.reasons.map(order)).sort_values(["_o", "institution", "name"])
    out[["name", "google_scholar", "verified", "notes", "institution", "department", "reasons", "page_research",
         "openalex_topics", "papers", "page_email", "openalex", "orcid", "auto_evidence"]].to_csv(
        "scholar_check_list.csv", index=False)
    print("\n", s.groupby(["reasons", "auto_verdict"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
