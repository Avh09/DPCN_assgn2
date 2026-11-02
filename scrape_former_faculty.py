"""Former faculty: people on the institutes' faculty pages in earlier years (2016-2025) who are
not on today's list (data/faculty/). Uses old copies of the pages saved by the Internet
Archive (Wayback Machine), one copy per department page per year.

  MANIT Bhopal    : the same department pages scrape_faculty.py reads today, 2017-2025
  NIT Jamshedpur  : old site, academics/departments/facultylist.php?deptid=..., 2016-2022,
                    and the 2024 copies of today's faculty API
  NIT Silchar     : old department pages departments/<dept>/<dept>.php, 2016-2024,
                    and the 2025 copy of today's faculty-list page

Names are taken from "Dr./Prof./Mr./Ms. <Name>" (and from the JSON of the API copies).
A name counts as current if it matches someone on today's list (same rule as faculty_match.py),
otherwise as former. Pages are cached in data/raw/wayback/ so this runs once.

Writes data/faculty_former/<institute>.csv:
  institution, name, department, designation, first_seen, last_seen, years_seen
"""
import hashlib
import json
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from html import unescape

import pandas as pd
import requests

import config
from faculty_match import match, page_name_forms, tokens
from scrape_faculty import MANIT_DEPTS, NITJ_CODES

HEAD = {"User-Agent": "Mozilla/5.0 (research project; former faculty list for a bibliometrics course)"}
CACHE = config.RAW_DIR / "wayback"
OUTDIR = config.ROOT / "data" / "faculty_former"

NITJ_OLD = {"CHEMISTRY": "Chemistry", "CIVIL": "Civil Engineering", "CSE": "Computer Science and Engineering",
            "ECE": "Electronics and Communication Engineering", "EEE": "Electrical Engineering",
            "HUMANITIES": "Humanities, Social Sciences and Management", "MATHS": "Mathematics",
            "MCA": "Computer Applications", "ME": "Mechanical Engineering",
            "META": "Metallurgical and Materials Engineering", "PHYSICS": "Physics",
            "PROD": "Production and Industrial Engineering"}
NITS_OLD = {"chem/chem.php": "Chemistry", "humanities/humanities.php": "Humanities and Social Sciences",
            "management/management.php": "Management Studies", "physics/physics.php": "Physics",
            "instru/eie.php": "Electronics and Instrumentation Engineering", "civil/civil.php": "Civil Engineering",
            "ece/ece.php": "Electronics and Communication Engineering", "electrical/electrical.php": "Electrical Engineering",
            "maths/maths.php": "Mathematics", "mech/mech.php": "Mechanical Engineering",
            "cse/cse.php": "Computer Science and Engineering"}

PAGES = (
    [("MANIT Bhopal", d, "www.manit.ac.in" + p, 2016, 2025) for d, p in MANIT_DEPTS.items()]
    + [("NIT Jamshedpur", d, f"nitjsr.ac.in/academics/departments/facultylist.php?deptid={c}", 2016, 2023)
       for c, d in NITJ_OLD.items()]
    + [("NIT Jamshedpur", "API", f"www.nitjsr.ac.in/backend/api/people/faculty?dept={q}", 2024, 2025)
       for q in ("cs", "ece", "ee", "civil", "mech", "meta", "prod", "chem", "maths", "phys", "humanities", "mca")]
    + [("NIT Silchar", d, f"nits.ac.in/departments/{p}", 2016, 2024) for p, d in NITS_OLD.items()]
    + [("NIT Silchar", "LIST", "www.nits.ac.in/more/faculty-list", 2025, 2025)]
)

TITLE_NAME = re.compile(r"\b(?:Dr|Prof|Mr|Mrs|Ms|Smt|Shri)\b\.?\s*((?:(?:[A-Z][a-zA-Z'\-]*|[A-Z]\.)\s*){1,5})")
DESIG = re.compile(r"\b(?:Professor|Lecturer|Faculty|Head\b|HOD\b|Dean\b)", re.I)
NOT_FACULTY = re.compile(r"Scholar|Ph\.?\s?D\b|Student|Fellow|Staff|Technical|M\.?\s?Tech|B\.?\s?Tech", re.I)
STOP = {"Professor", "Assistant", "Associate", "Head", "Department", "Designation", "Dean", "Director", "Phone",
        "Email", "Interests", "Research", "Area", "Qualification", "View", "Profile", "Close", "Faculty",
        "Adhoc", "AD", "HOC", "Mobile", "HOD", "Coordinator", "Visiting", "Emeritus", "Grade"}
STOP_LOWER = {w.lower() for w in STOP} | {"designation", "qualification", "qualifications", "adhoc", "specialization",
                                          "interests", "email", "phone", "mobile", "profile", "more",
                                          "temporary", "contractual", "regular", "inspire"}


def wb(params):
    f = CACHE / ("cdx_" + hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    rows = _wb(params)
    if rows is None:      # the archive did not answer: stop rather than treat the page as having no copies
        raise SystemExit(f"Wayback index did not answer for {params.get('url')}; rerun later "
                         "(answers so far are cached)")
    f.write_text(json.dumps(rows))
    return rows


def _wb(params):
    for attempt in range(5):
        try:
            r = requests.get("http://web.archive.org/cdx/search/cdx", params=params, headers=HEAD, timeout=120)
            if r.ok:
                return r.json()[1:] if r.text.strip() else []
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (attempt + 1))
    return None           # failed (different from "no copies", which is an empty list)


def fetch(ts, url):
    f = CACHE / (hashlib.md5(f"{ts}{url}".encode()).hexdigest() + ".html")
    if f.exists():
        return f.read_text(errors="ignore")
    for attempt in range(5):
        try:
            r = requests.get(f"http://web.archive.org/web/{ts}id_/{url}", headers=HEAD, timeout=120)
            if r.ok:
                f.write_text(r.text)
                time.sleep(1)
                return r.text
        except requests.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    return ""


def names_in(page, dept):
    """(name, department, designation) found on one archived page"""
    if page.lstrip().startswith("{"):               # NIT Jamshedpur API copy
        try:
            data = json.loads(page).get("data") or []
        except ValueError:
            return []
        return [(f"{f.get('fname') or ''} {f.get('lname') or ''}".strip(),
                 NITJ_CODES.get((f.get("department") or "").upper(), dept), (f.get("designation") or "").strip())
                for f in data if f]
    if dept == "LIST":                              # NIT Silchar faculty-list copy: name cards
        out = []
        for card in page.split('class="our-team"')[1:]:
            n = re.search(r'class="team-title">\s*(.*?)\s*</h3>', card, re.S)
            if n:
                out.append((unescape(re.sub(r"<[^>]+>", "", n.group(1))).strip(), "", ""))
        return out
    h = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", page, flags=re.S)
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", h)))
    out = []
    for m in TITLE_NAME.finditer(text):
        words = []
        for w in m.group(1).split():
            # compare without punctuation and case: "Designation-", "AD-HOC", "Designation:" all stop
            if re.sub(r"[^a-z]", "", w.lower()) in STOP_LOWER:
                break
            words.append(w)
        name = " ".join(words).strip()
        # faculty only: a designation must follow the name closely (scholars, staff and
        # people mentioned in news text have none, or are marked as scholars/students)
        after = text[m.start(1) + len(name):m.start(1) + len(name) + 90]
        d = DESIG.search(after)
        if len(tokens(name)) < 2 or not d or NOT_FACULTY.search(after[:d.start()]):
            continue
        ad_hoc = "ad-hoc" if re.search(r"ad[- ]?hoc", after, re.I) else ""
        out.append((name, dept, ad_hoc))
    return out


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # 1. which yearly copies exist (one index query per page), 2. download them 4 at a time
    snaps_of = {}
    for n, (inst, dept, url, y0, y1) in enumerate(PAGES, 1):
        snaps_of[url] = wb({"url": url, "output": "json", "fl": "timestamp,original", "filter": "statuscode:200",
                            "from": str(y0), "to": str(y1), "collapse": "timestamp:4"})
        print(f"index {n}/{len(PAGES)}: {inst} {dept[:30]} -> {len(snaps_of[url])} copies", flush=True)
    todo = [s for v in snaps_of.values() for s in v]
    with ThreadPoolExecutor(4) as ex:
        for k, _ in enumerate(ex.map(lambda s: fetch(*s), todo), 1):
            if k % 20 == 0:
                print(f"downloaded {k}/{len(todo)} pages", flush=True)

    # 3. read the names
    seen = defaultdict(lambda: {"years": set(), "dept": "", "desig": set()})   # (inst, name tokens) -> info
    shown = {}
    for n, (inst, dept, url, y0, y1) in enumerate(PAGES, 1):
        snaps = snaps_of[url]
        found = 0
        for ts, orig in snaps:
            for name, d, desig in names_in(fetch(ts, orig), dept):
                k = (inst, tuple(tokens(name)))
                seen[k]["years"].add(int(ts[:4]))
                if d not in ("API", "LIST", ""):
                    seen[k]["dept"] = d
                if desig:
                    seen[k]["desig"].add(desig)
                shown.setdefault(k, name)
                found += 1
        print(f"[{n}/{len(PAGES)}] {inst} | {dept[:30]:30s} | {len(snaps)} yearly copies | {found} names", flush=True)

    current = pd.concat([pd.read_csv(p) for p in sorted(config.FACULTY_DIR.glob("*.csv"))])
    cur_tok = defaultdict(list)
    for i, nm in zip(current.institution, current.name):
        cur_tok[i].append(tokens(nm))
    # text after a name sometimes sticks to it ("Manish Pandey Soft Computing"), so names are
    # compared through shorter forms (faculty_match.page_name_forms: never by cutting off a single
    # word, which would make "Ashok Kumar Mehta" match "Ashok Kumar"): current if a form matches
    # today's list (spelling variants like Mansi/Manasi included); a former
    # person is kept under the longest prefix that matches an author who published from the
    # institute (people without papers in our data do not matter for the statistics)
    authors = pd.read_csv(config.OUT_DIR / "authors.csv")
    auth_by_surname = defaultdict(list)
    for i, a in zip(authors.institution, authors.author):
        t = tokens(a)
        if len(t) >= 2:
            auth_by_surname[(i, t[-1])].append(t)
            auth_by_surname[(i, t[0])].append(t)
    prefixes = page_name_forms     # shorter forms only when what is cut off is junk, not a surname
    for inst in config.INSTITUTES:
        people = defaultdict(lambda: {"years": set(), "dept": "", "desig": set()})
        n_cur = n_none = 0
        for (i, tk), v in seen.items():
            if i != inst or len(tk) < 2:
                continue
            # current if a form matches today's list, or if the page name was visibly cut off
            # (ends in an initial) and is the beginning of a current name ("Ashish B" from "Ashish B.
            # Deoghare"); a complete name like "Anil Kumar" is NOT the start of "Anil Kumar Sharma"
            if any(match(p, c) or (len(p[-1]) == 1 and len(c) > len(p) and match(p, c[:len(p)]) == "exact")
                   for p in prefixes(tk) for c in cur_tok[i]):
                n_cur += 1
                continue
            name = next((p for p in prefixes(tk)
                         if any(match(p, a) for a in auth_by_surname[(i, p[-1])] + auth_by_surname[(i, p[0])])), None)
            if not name:
                n_none += 1
                continue
            q = people[tuple(name)]
            q["years"] |= v["years"]
            q["dept"] = q["dept"] or v["dept"]
            q["desig"] |= v["desig"]
        rows = []
        for tk, v in people.items():
            ys = sorted(v["years"])
            rows.append({"institution": inst, "name": " ".join(w.capitalize() if len(w) > 1 else w.upper() for w in tk),
                         "department": v["dept"], "designation": "; ".join(sorted(v["desig"])),
                         "first_seen": ys[0], "last_seen": ys[-1], "years_seen": " ".join(map(str, ys))})
        df = pd.DataFrame(rows).sort_values(["department", "name"]) if rows else pd.DataFrame()
        df.to_csv(OUTDIR / f"{inst.replace(' ', '_')}.csv", index=False)
        print(f"\n{inst}: {sum(1 for (i, _) in seen if i == inst)} faculty name forms on old pages -> "
              f"{n_cur} current, {len(df)} former with papers in our data, {n_none} former without papers here")


if __name__ == "__main__":
    main()
