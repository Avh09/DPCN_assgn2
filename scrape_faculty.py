"""Step 2: collect the faculty list (name, department, designation) of each institute
from the institute's own public website. Writes data/faculty/<institute>.csv.

  MANIT Bhopal    : one page per department on manit.ac.in
  NIT Jamshedpur  : the public JSON that its faculty pages load (nitjsr.ac.in/backend/api)
  NIT Silchar     : the single list page nits.ac.in/more/faculty-list
Only name, department and designation are kept (no emails or phone numbers).
"""
import html
import re
import time

import pandas as pd
import requests

import config

HEAD = {"User-Agent": "Mozilla/5.0 (research project; faculty list for bibliometrics course)"}
config.FACULTY_DIR.mkdir(parents=True, exist_ok=True)


def get(url, **kw):
    for a in range(3):
        try:
            r = requests.get(url, headers=HEAD, timeout=40, verify=False, **kw)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"could not fetch {url}")


def clean_name(s):
    s = html.unescape(s)
    s = re.sub(r"\(.*?\)", "", s)                      # (on Lien) etc.
    s = re.sub(r"^name\s*:\s*", "", s.strip(), flags=re.I)
    s = re.sub(r"^(prof\.?|dr\.?|mr\.?|ms\.?|mrs\.?|er\.?)\s*", "", s.strip(), flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" .,-")


# ------------------------------------------------------------------ MANIT
MANIT_DEPTS = {
    "Architecture and Planning": "/architecture-planning",
    "Biological Science and Engineering": "/content/biological-science-engineering",
    "Civil Engineering": "/civil-engineering-department",
    "Chemical Engineering": "/content/chemical-engineering-0",
    "Computer Science and Engineering": "/computer-science-engineering-department-0",
    "Electrical Engineering": "/content/electrical-engineering",
    "Electronics and Communication Engineering": "/content/electronics-communication-engineering",
    "Materials and Metallurgical Engineering": "/content/materials-metallurgical-engineering",
    "Mechanical Engineering": "/content/mechanical-engineering",
    "Chemistry": "/content/chemistry-department",
    "Mathematics": "/content/mathematics-0",
    "Bioinformatics": "/content/bioinformatics",
    "Computer Applications": "/content/computer-applications-department",
    "Physics": "/content/physics-department",
    "Humanities and Social Sciences": "/content/humanities-and-social-sciences-hss",
    "Management Studies": "/content/department-management-studies-dms",
    "Energy Science and Engineering": "/content/energy",
}


def manit():
    rows = []
    for dept, path in MANIT_DEPTS.items():
        h = get("https://www.manit.ac.in" + path).text
        h = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", h, flags=re.S)
        lines = [html.unescape(re.sub(r"<[^>]+>", "\n", h)).split("\n")][0]
        lines = [re.sub(r"\s+", " ", l).strip() for l in lines]
        lines = [l for l in lines if l and l != "-->"]
        for i, l in enumerate(lines):
            m = re.match(r"^designation\s*:?\s*(.*)$", l, re.I)
            if m and i > 0:
                desig = m.group(1).strip() or (lines[i + 1] if i + 1 < len(lines) else "")
                rows.append({"institution": "MANIT Bhopal", "name": clean_name(lines[i - 1]),
                             "department": dept, "designation": desig.strip(" -,")})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ NIT Jamshedpur
NITJ_CODES = {"CS": "Computer Science and Engineering", "EC": "Electronics and Communication Engineering",
              "EE": "Electrical Engineering", "CE": "Civil Engineering", "ME": "Mechanical Engineering",
              "MM": "Metallurgical and Materials Engineering", "PI": "Production and Industrial Engineering",
              "CH": "Chemistry", "MA": "Mathematics", "PH": "Physics",
              "HU": "Humanities, Social Sciences and Management", "CA": "Computer Applications"}


def nitj():
    # NB: some dept= values (e.g. ee, design) return the whole faculty, so fetch a few
    # queries, de-duplicate on faculty_id and use each record's own department code.
    seen, rows = {}, []
    for q in ("cs", "ece", "ee", "civil", "mech", "meta", "prod", "chem", "maths", "phys", "humanities", "mca"):
        for f in get(f"https://www.nitjsr.ac.in/backend/api/people/faculty?dept={q}").json().get("data") or []:
            if f and f.get("faculty_id"):
                seen[f["faculty_id"]] = f
    for fid, f in seen.items():
        name = clean_name(f"{f.get('fname') or ''} {f.get('lname') or ''}")
        code = (f.get("department") or "").upper()
        rows.append({"institution": "NIT Jamshedpur", "name": name,
                     "department": NITJ_CODES.get(code, code or "unknown"),
                     "designation": (f.get("designation") or "").strip()})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ NIT Silchar
NITS_SUB = {"civil": "Civil Engineering", "mech": "Mechanical Engineering", "ee": "Electrical Engineering",
            "ece": "Electronics and Communication Engineering", "cse": "Computer Science and Engineering",
            "eie": "Electronics and Instrumentation Engineering", "maths": "Mathematics", "math": "Mathematics",
            "physics": "Physics", "chemistry": "Chemistry", "chem": "Chemistry", "doms": "Management Studies",
            "ce": "Civil Engineering", "me": "Mechanical Engineering", "ec": "Electronics and Communication Engineering",
            "eed": "Electrical Engineering", "cs": "Computer Science and Engineering", "hss": "Humanities and Social Sciences", "humanities": "Humanities and Social Sciences",
            "dhss": "Humanities and Social Sciences", "dos": "Sciences"}


def nits():
    h = get("https://www.nits.ac.in/more/faculty-list").text
    rows = []
    for card in h.split('class="our-team"')[1:]:
        n = re.search(r'class="team-title">\s*(.*?)\s*</h3>', card, re.S)
        p = re.search(r'class="post">\s*(.*?)\s*</span>', card, re.S)
        link = re.search(r'href="https?://([a-z0-9-]+)\.nits\.ac\.in/', card)
        if not n:
            continue
        sub = link.group(1) if link else ""
        rows.append({"institution": "NIT Silchar", "name": clean_name(re.sub(r"<[^>]+>", "", n.group(1))),
                     "department": NITS_SUB.get(sub, sub or "unknown"),
                     "designation": html.unescape(re.sub(r"<[^>]+>", "", p.group(1))).strip() if p else ""})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    for name, fn in (("MANIT_Bhopal", manit), ("NIT_Jamshedpur", nitj), ("NIT_Silchar", nits)):
        df = fn()
        df = df[df.name.str.len() > 2].drop_duplicates(["name", "department"])
        df.to_csv(config.FACULTY_DIR / f"{name}.csv", index=False)
        print(f"\n{name}: {len(df)} faculty")
        print(df.department.value_counts().to_string())
