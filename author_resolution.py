"""Who is each author? Role, canonical name and tenure for every row of group15_data.csv.

Runs after faculty_match.py. Combines three kinds of evidence:

  Tier 1  OpenAlex affiliation on the paper: the row exists because the author is listed at one
          of our institutes (fetch.py filter). Per author we keep papers, first/last year.
  Tier 2  Official pages: current faculty (data/faculty/) and former faculty from archived pages
          (data/faculty_former/), already matched to author ids in author_faculty_map.csv.
          Gives is_faculty plus the years the person was seen on the pages.
  Tier 3  OpenAlex author objects (cached in data/raw/authors/): all name variants of an author
          id, and the author's affiliation history (which years at which institute). Used to
          (a) pick one canonical name and (b) judge people the pages never listed.

is_faculty stays strictly "found on a faculty page" (Tier 2). Everything inferred is kept in
separate columns, so nothing guessed is passed off as official.

Adds to group15_data.csv:
  author_canonical   faculty name from the page if matched, else OpenAlex display name
  author_role        faculty | probable_faculty | probable_scholar_or_visitor | unclear
  role_source        web_current | web_archive | openalex_inferred
  faculty_window     years on the faculty pages, e.g. "2017-2022" (former faculty only)
  paper_in_window    TRUE/FALSE if the paper year is within the window +-2 (former faculty only)
  affiliation_note   mostly_elsewhere when OpenAlex puts the person mostly at other institutes

Also writes data/out/author_roles.csv (one row per institute + author id, with the evidence).

Rules for people not on any page (Tier 3):
  probable_faculty              >= 8 papers over >= 5 distinct years at the institute AND
                                (>= 50% of their OpenAlex affiliation years are at the institute
                                 or the institute is their last known one)
  probable_scholar_or_visitor   <= 4 years between first and last paper at the institute
  unclear                       everything else
These are heuristics (a PhD scholar who stays on as staff looks like faculty). Check a sample.
"""
import json
import re
import time

import pandas as pd
import requests

import config

OUT = config.OUT_DIR
CACHE = config.RAW_DIR / "authors" / "authors.jsonl"
API = "https://api.openalex.org/authors"
BATCH = 50
WINDOW_SLACK = 2


# ---------------------------------------------------------------- Tier 3: OpenAlex author objects
def fetch_author_objects(ids):
    """OpenAlex author objects for the given ids, cached on disk so this downloads once."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    have = {}
    if CACHE.exists():
        for line in CACHE.read_text().splitlines():
            o = json.loads(line)
            have[o["id"].rsplit("/", 1)[-1]] = o
    # enrich.py gives name-matched authors a placeholder id "NAME:..."; OpenAlex has no object for them
    todo = [i for i in ids if i not in have and re.fullmatch(r"A\d+", i)]
    print(f"author objects: {len(have)} cached, {len(todo)} to download")
    sess = requests.Session()
    with CACHE.open("a") as f:
        for k in range(0, len(todo), BATCH):
            chunk = todo[k:k + BATCH]
            params = {"filter": "openalex_id:" + "|".join(chunk), "per_page": BATCH, "mailto": config.EMAIL,
                      "select": "id,display_name,display_name_alternatives,orcid,works_count,"
                                "affiliations,last_known_institutions"}
            if config.API_KEY:
                params["api_key"] = config.API_KEY
            for attempt in range(5):
                r = sess.get(API, params=params, timeout=60)
                if r.status_code == 200:
                    break
                time.sleep(2 ** attempt)
            else:
                # e.g. the daily OpenAlex budget is used up: carry on without these authors (role "unclear"), rerun later
                print(f"WARNING: OpenAlex failed ({r.status_code}) at batch {k}; {len(todo) - k} author objects missing, rerun later to fill them")
                return have
            for o in r.json()["results"]:
                f.write(json.dumps(o) + "\n")
                have[o["id"].rsplit("/", 1)[-1]] = o
            if (k // BATCH) % 20 == 0:
                print(f"  {k + len(chunk)}/{len(todo)}")
    return have


def affiliation_years(obj, inst_oa_id):
    """(years at this institute, years in total) from the author's OpenAlex affiliation history."""
    at, total = set(), set()
    for a in obj.get("affiliations") or []:
        yrs = set(a.get("years") or [])
        total |= yrs
        inst = a["institution"]
        if inst["id"].endswith(inst_oa_id) or any(x.endswith(inst_oa_id) for x in inst.get("lineage") or []):
            at |= yrs
    return at, total


def last_known_here(obj, inst_oa_id):
    return any(i["id"].endswith(inst_oa_id) for i in obj.get("last_known_institutions") or [])


# ---------------------------------------------------------------- roles
def tidy_name(n):
    """Page names come as 'ANJALI DHENGLE' or 'Dr. x'; display them in normal case."""
    n = re.sub(r"^(?:Dr|Prof|Mr|Mrs|Ms)\.?\s+", "", str(n).strip())
    return n.title() if n.isupper() else n


def classify(row, has_obj):
    if row.web_source:
        return "faculty", row.web_source
    if not has_obj:
        return "unclear", "openalex_inferred"
    if row.papers >= 8 and row.distinct_years >= 5 and (row.share_at_inst >= 0.5 or row.last_known_here):
        return "probable_faculty", "openalex_inferred"
    if row.last_year - row.first_year <= 4:
        return "probable_scholar_or_visitor", "openalex_inferred"
    return "unclear", "openalex_inferred"


def main():
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str)
    amap = pd.read_csv(OUT / "author_faculty_map.csv")
    fm = pd.read_csv(OUT / "faculty_matched.csv")

    ev = (m.assign(y=pd.to_numeric(m.year))
          .groupby(["institution", "author_id"])
          .agg(author=("author", "first"), papers=("openalex_work_id", "nunique"),
               distinct_years=("y", "nunique"), first_year=("y", "min"), last_year=("y", "max"))
          .reset_index())
    objs = fetch_author_objects(sorted(ev.author_id.unique()))

    # Tier 2 evidence: page status and window per author id
    win = fm[["institution", "faculty_name", "first_seen", "last_seen"]].drop_duplicates(["institution", "faculty_name"])
    amap = amap.merge(win, on=["institution", "faculty_name"], how="left")
    amap["web_source"] = amap.faculty_status.map({"current": "web_current", "former": "web_archive"})
    ev = ev.merge(amap[["institution", "author_id", "faculty_name", "department", "web_source",
                        "first_seen", "last_seen"]], on=["institution", "author_id"], how="left")
    ev["web_source"] = ev.web_source.where(ev.web_source.notna(), "")

    # Tier 3 evidence: affiliation history
    share, lkh, names = [], [], []
    for r in ev.itertuples():
        o = objs.get(r.author_id)
        if o is None:
            share.append(float("nan")); lkh.append(False); names.append(r.author)
            continue
        oa = config.INSTITUTES[r.institution]["openalex_id"]
        at, total = affiliation_years(o, oa)
        share.append(len(at) / len(total) if total else float("nan"))
        lkh.append(last_known_here(o, oa))
        names.append(o["display_name"])
    ev["share_at_inst"], ev["last_known_here"], ev["oa_display_name"] = share, lkh, names

    roles = [classify(r, r.author_id in objs) for r in ev.itertuples()]
    ev["author_role"], ev["role_source"] = zip(*roles)
    ev["author_canonical"] = [tidy_name(f) if isinstance(f, str) and f else n
                              for f, n in zip(ev.faculty_name, ev.oa_display_name)]
    ev["faculty_window"] = [f"{int(a)}-{int(b)}" if r == "web_archive" and pd.notna(a) and pd.notna(b) else ""
                            for r, a, b in zip(ev.web_source, ev.first_seen, ev.last_seen)]
    ev["affiliation_note"] = ["mostly_elsewhere" if s < 0.3 and not l else ""
                              for s, l in zip(ev.share_at_inst.fillna(1), ev.last_known_here)]
    ev.to_csv(OUT / "author_roles.csv", index=False)

    # back onto the rows
    cols = ["author_canonical", "author_role", "role_source", "faculty_window", "affiliation_note",
            "first_seen", "last_seen"]
    m = m.drop(columns=[c for c in cols + ["paper_in_window"] if c in m.columns])
    m = m.merge(ev[["institution", "author_id"] + cols], on=["institution", "author_id"], how="left")
    y = pd.to_numeric(m.year)
    inwin = (y >= pd.to_numeric(m.first_seen) - WINDOW_SLACK) & (y <= pd.to_numeric(m.last_seen) + WINDOW_SLACK)
    m["paper_in_window"] = ["" if not w else ("TRUE" if i else "FALSE") for w, i in zip(m.faculty_window, inwin)]
    m = m.drop(columns=["first_seen", "last_seen"])
    m.to_csv(OUT / "group15_data.csv", index=False)

    # summary
    print("\nauthor ids by role:")
    print(ev.groupby(["institution", "author_role"]).size().unstack(fill_value=0).to_string())
    print("\nrows by role:")
    print(m.groupby(["institution", "author_role"]).size().unstack(fill_value=0).to_string())
    fac = ev[ev.author_role == "faculty"]
    print(f"\nfaculty ids flagged mostly_elsewhere: {(fac.affiliation_note != '').sum()} of {len(fac)}")
    fw = m[m.faculty_window != ""]
    print(f"former-faculty rows inside their page window (+-{WINDOW_SLACK}y): "
          f"{(fw.paper_in_window == 'TRUE').mean():.0%} of {len(fw)}")


if __name__ == "__main__":
    main()
