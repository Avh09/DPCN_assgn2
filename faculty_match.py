"""Step 5: match the official faculty lists (data/faculty/*.csv) to OpenAlex author ids.

Rules (a faculty member is only compared with authors who published with the SAME institute):
  - names are normalised: lowercase, titles (Dr, Prof...) and punctuation removed, and
    run-together capital initials split ("KK Singh" -> k k singh)
  - surnames must be equal (last token; also tried in reversed order for "Sudhakar K." style, full
    given names only). A surname written as an initial matches ("Prashanth J" = "Prashanth
    Janardhan") when the given names agree in full
  - the given names must be compatible in order: each given name of the shorter name matches
    a given name of the longer one, either in full or as an initial ("Krishna K" ~ "K. K." ~
    "Krishna"), and the FIRST given names must agree
  - spelling variants with one vowel more or less count as equal ("Mansi" = "Manasi"); first
    and last letters must agree, so "Manish" != "Manisha"
  - quality: exact = same normalised name, full = no initials needed, initials = needed initials
  - an author id compatible with two faculty is given to the better match; on a tie it is
    left unmatched and listed as ambiguous
  - one faculty member can get several author ids (OpenAlex splits people). Ids with different
    ORCIDs are split off only if the name is common (4+ author ids with it in all our data)
  - same-name colleagues are kept as "<name> (<department>)" and only get records from
    data/faculty_overrides.csv, which also holds every other correction found by checking

Writes to data/out/:
  faculty_matched.csv       one row per faculty member: ids, papers, citations, corpus h-index, status
  author_faculty_map.csv    author_id -> faculty name, department, match quality
  faculty_match_audit.csv   50 random matches to check by hand (column correct = Y/N to fill)
  group15_data.csv          is_faculty, faculty_name, department columns added
"""
import re
from collections import defaultdict

import pandas as pd

import config

OUT = config.OUT_DIR
TITLES = {"dr", "prof", "professor", "essor", "mr", "mrs", "ms", "er", "ar", "shri", "smt", "sri"}


def tokens(name):
    name = str(name or "")
    # split run-together capital initials (KK, RK) but not all-caps full names (BINOD)
    name = re.sub(r"\b([A-Z]{2,3})\b", lambda m: " ".join(m.group(1)) if not name.isupper() else m.group(1), name)
    name = re.sub(r"(?<=[A-Z])\.(?=[A-Z])", ". ", name)
    t = re.sub(r"[^a-z ]", " ", name.lower()).split()
    return [x for x in t if x not in TITLES]


VOWELS = set("aeiouy")


def same_word(x, y):
    """equal, or the same name spelt with one vowel more or less inside it ("mansi" ~ "manasi").
    First and last letters and all consonants must agree, so "manish" !~ "manisha"."""
    if x == y:
        return True
    if min(len(x), len(y)) < 4 or abs(len(x) - len(y)) > 1 or x[0] != y[0] or x[-1] != y[-1]:
        return False
    skel = lambda w: "".join(c for c in w if c not in VOWELS)
    return skel(x) == skel(y)


def given_ok(g1, g2):
    """every given name of the shorter list matches one of the longer, in order; first ones agree"""
    if not g1 or not g2:
        return None
    a, b = (g1, g2) if len(g1) <= len(g2) else (g2, g1)
    comp = lambda x, y: same_word(x, y) or (len(x) == 1 and y[0] == x) or (len(y) == 1 and x[0] == y)
    if not comp(a[0], b[0]):
        return None
    j = 0
    for x in a:
        while j < len(b) and not comp(x, b[j]):
            j += 1
        if j == len(b):
            return None
        j += 1
    full = all(len(x) > 1 for x in a) and all(len(x) > 1 for x in b[:len(a)])
    if not full and len(g1) != len(g2):     # "N. B." must not match "Navdeep"
        return None
    return "full" if full else "initials"


def match(f, a):
    """quality of matching faculty tokens f with author tokens a, or None"""
    if len(f) < 2 or len(a) < 2:
        return None
    if f == a:
        return "exact"
    if same_word(f[-1], a[-1]):
        return given_ok(f[:-1], a[:-1])
    # surname written as an initial ("Prashanth J" = "Prashanth Janardhan", South Indian style):
    # only with the given names agreeing in full
    for x, y in ((f, a), (a, f)):
        if len(x[-1]) == 1 and len(y[-1]) > 1 and y[-1][0] == x[-1] and given_ok(x[:-1], y[:-1]) == "full":
            return "initials"
    # reversed order ("Kumar Satish" vs "Satish Kumar") only with full given names: with
    # initials it is too loose ("Raju More" would match "M. Raju")
    if f[-1] == a[0] and len(f[-1]) > 1 and given_ok(f[:-1], a[1:]) == "full":
        return "full"
    if a[-1] == f[0] and len(a[-1]) > 1 and given_ok(f[1:], a[:-1]) == "full":
        return "full"
    return None


RANK = {"override": 4, "exact": 3, "full": 2, "initials": 1}

# words that can follow a name on a web page without being part of it
PAGE_JUNK = {"ph", "phd", "dr", "md", "prof", "hod", "sr", "jr", "mr", "ms", "ad", "hoc", "adhoc", "member",
             "head", "dean", "faculty", "guest", "visiting", "on", "lien", "leave", "retired", "emeritus",
             "temporary", "contractual", "contract", "regular", "inspire"}


def page_name_forms(cand):
    """forms of a name read from a web page, longest first. Page text sometimes sticks to the
    name ("Manish Pandey Soft Computing"), so shorter forms are allowed, but only if what is cut
    off is junk: two or more words, or known non-name words. A single cut-off word is a surname
    ("Ashok Kumar Mehta" is not "Ashok Kumar")."""
    out = []
    for k in range(len(cand), 1, -1):
        rest = cand[k:]
        # single letters cut off the end are junk too ("AD-HOC" becomes "a d h o c")
        if rest and len(rest) < 2 and not all(w in PAGE_JUNK or len(w) == 1 for w in rest):
            continue
        out.append(list(cand[:k]))
    return out


def match_page_name(cand, name):
    """match a name read from a web page (cand tokens) to a known name (see page_name_forms)"""
    for form in page_name_forms(cand):
        q = match(form, name)
        if q:
            return q
    return None


COMMON_NAME_IDS = 4    # a name is "common" from this many author ids with that exact name in all our data


def prune(amap, name_ids):
    """Drop author ids that are a different person with the same name.

    The id with most papers is the anchor. If the ids carry two or more different ORCIDs AND
    the name is common (4+ author ids with that exact name in all our data, e.g. "Deepak Kumar",
    "Pankaj Kumar"; or an initial-only name in the group), keep only ids with the anchor's ORCID. For a rare name
    two ORCIDs are one person with two ORCIDs (e.g. Awdhesh Kumar Choudhary), so all are kept.
    name_ids counts author ids per name among all authors in our data (co-authors included).
    If the faculty first name is only an initial, drop ids whose full first name differs from
    the anchor's ("S. Suresh": keep Sundaramurthy/Sundarmurti, drop Saumya).
    """
    from rapidfuzz.fuzz import ratio
    keep, drop = [], []
    for (inst, name), g in amap.groupby(["institution", "faculty_name"]):
        g = g.sort_values("papers", ascending=False)
        ft = tokens(name)
        if len(ft) >= 2 and len(ft[0]) == 1 and len(g) > 1:
            firsts = []
            for n in g.author:              # first given name = first token that is not the surname
                t = tokens(n)
                if ft[-1] in t:
                    t.remove(ft[-1])
                firsts.append(t[0] if t and len(t[0]) > 1 else None)
            a_first = next((f for f in firsts if f and f[0] == ft[0]), None)
            ok = pd.Series([not f or not a_first or ratio(f, a_first) >= 80 for f in firsts], index=g.index)
            drop.append(g[~ok].assign(reason="different full first name"))
            g = g[ok]
        # common = 4+ author ids with that exact name anywhere in our data, or an initial-only name
        # in the group ("S. Sharma" could be anyone)
        common = any(name_ids.get(frozenset(tokens(n)), 1) >= COMMON_NAME_IDS or
                     (len(tokens(n)) > 0 and len(tokens(n)[0]) == 1) for n in g.author)
        if g.orcid.dropna().nunique() >= 2 and common:
            a_orcid = g.orcid.dropna().iloc[0]      # ORCID of the id with most papers
            nameset = lambda n: frozenset(tokens(n))
            anchor_names = {nameset(n) for n in g[g.orcid == a_orcid].author}
            other_names = {nameset(n) for n in g[g.orcid.notna() & (g.orcid != a_orcid)].author}
            # an id without ORCID stays if it has the anchor's full name and nobody else has that name
            ok = (g.orcid == a_orcid) | (g.orcid.isna() & g.author.map(
                lambda n: nameset(n) in anchor_names and nameset(n) not in other_names))
            g = g.assign(common_name=True)
            drop.append(g[~ok].assign(reason="different ORCID or no ORCID (common name)"))
            g = g[ok]
        else:
            g = g.assign(common_name=False)
        keep.append(g)
    rej = pd.concat(drop) if drop else pd.DataFrame()
    return pd.concat(keep), rej


def apply_overrides(amap, rejected, fac, authors):
    """Corrections found by checking (data/faculty_overrides.csv, one row each with its evidence):
      assign         author record -> faculty member (replaces any automatic match)
      unassign       author record is not this faculty member / not faculty at all
      work_assign    one paper of a record -> faculty member   (applied to group15_data.csv)
      work_unassign  one paper of a record is not that faculty member's
    """
    p = config.ROOT / "data" / "faculty_overrides.csv"
    if not p.exists():
        return amap, rejected, pd.DataFrame(columns=["action", "institution", "faculty_name", "author_id", "work_id"])
    o = pd.read_csv(p, dtype=str).fillna("")
    known = set(zip(fac.institution, fac.name))
    bad = [r.faculty_name for r in o.itertuples() if r.faculty_name and (r.institution, r.faculty_name) not in known]
    if bad:
        raise SystemExit(f"faculty_overrides.csv names faculty not on any list: {bad}")
    info = fac.drop_duplicates(["institution", "name"]).set_index(["institution", "name"])
    au = authors.set_index(["institution", "author_id"])
    for r in o[o.action.isin(["unassign", "assign"])].itertuples(index=False):
        hit = (amap.institution == r.institution) & (amap.author_id == r.author_id)
        if r.action == "unassign":
            rejected = pd.concat([rejected, amap[hit].assign(reason="override: " + r.evidence)])
        amap = amap[~hit]
    new = []
    for r in o[o.action == "assign"].itertuples(index=False):
        f = info.loc[(r.institution, r.faculty_name)]
        a = au.loc[(r.institution, r.author_id)] if (r.institution, r.author_id) in au.index else None
        new.append({"institution": r.institution, "author_id": r.author_id, "faculty_name": r.faculty_name,
                    "department": f.department, "designation": f.designation, "faculty_status": f.faculty_status,
                    "match_quality": "override", "author": a.author if a is not None else "",
                    "orcid": a.orcid if a is not None else None, "papers": a.papers if a is not None else 0,
                    "first_year": a.first_year if a is not None else None,
                    "last_year": a.last_year if a is not None else None, "common_name": False})
    amap = pd.concat([amap, pd.DataFrame(new)], ignore_index=True)
    print(f"overrides: {len(new)} assigned, {(o.action == 'unassign').sum()} unassigned, "
          f"{o.action.str.startswith('work').sum()} paper-level")
    return amap, rejected, o[o.action.isin(["work_assign", "work_unassign"])]


def h_index(cites):
    c = sorted(cites, reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


def main():
    fac = pd.concat([pd.read_csv(p) for p in sorted(config.FACULTY_DIR.glob("*.csv"))], ignore_index=True)
    fac["faculty_status"] = "current"
    # former faculty (on the institutes' old faculty pages, not on today's list): scrape_former_faculty.py
    former_dir = config.ROOT / "data" / "faculty_former"
    former = [pd.read_csv(p) for p in sorted(former_dir.glob("*.csv")) if p.stat().st_size > 10]
    if former:
        former = pd.concat(former, ignore_index=True).assign(faculty_status="former")
        fac = pd.concat([fac, former[["institution", "name", "department", "designation", "faculty_status",
                                      "first_seen", "last_seen"]]], ignore_index=True)
    fac["designation"] = fac.designation.fillna("")
    fac["department"] = fac.department.fillna("")
    fac["name"] = (fac.name.str.replace("​", "", regex=False)
                   .str.replace(r"^(?:essor|Prof\.?|Dr\.?)\s+", "", regex=True).str.strip())
    # same name twice in one institute (compared after normalising, so "Dinesh Kumar" and
    # "DINESH KUMAR" are the same name): MANIT lists its Mathematics faculty again under
    # Bioinformatics / Computer Applications (one person -> merge). Any other repeat (e.g. two
    # "Deepak Kumar"s in Mechanical and Humanities) is different people who cannot be told apart
    # by name: they are not matched automatically, but each is kept as a person named
    # "<name> (<department>)" so verified records can be given to them in faculty_overrides.csv.
    joint = {"Mathematics", "Bioinformatics", "Computer Applications"}
    fac["_key"] = fac.name.map(lambda n: " ".join(tokens(n)))
    rows, homonyms = [], []
    for (inst, _), g in fac.groupby(["institution", "_key"], sort=False):
        first = g.iloc[0]
        extra = {"faculty_status": first.faculty_status, "first_seen": first.get("first_seen"),
                 "last_seen": first.get("last_seen")}
        if len(g) == 1 or set(g.department) <= joint:
            rows.append({"institution": inst, "name": first["name"], "department": "; ".join(g.department),
                         "designation": first.designation, **extra})
        else:
            for r in g.itertuples(index=False):
                homonyms.append({"institution": inst, "name": f"{r.name} ({r.department})", "plain_name": r.name,
                                 "department": r.department, "designation": r.designation,
                                 "faculty_status": r.faculty_status, "first_seen": getattr(r, "first_seen", None),
                                 "last_seen": getattr(r, "last_seen", None)})
            # kept for matching so their ids are not handed to someone else, removed afterwards
            rows.append({"institution": inst, "name": first["name"], "department": "", "designation": "",
                         "homonym": True, **extra})
    fac = pd.DataFrame(rows)
    fac["homonym"] = fac.get("homonym", False)
    fac["homonym"] = fac.homonym.fillna(False).astype(bool)
    homonyms = pd.DataFrame(homonyms)
    homonym_names = set(zip(fac[fac.homonym].institution, fac[fac.homonym].name))
    authors = pd.read_csv(OUT / "authors.csv")

    best = {}                     # (inst, author_id) -> list of (rank, faculty index, quality)
    for inst, fi in fac.groupby("institution"):
        ftok = {i: tokens(n) for i, n in zip(fi.index, fi.name)}
        by_surname = defaultdict(list)
        for i, t in ftok.items():
            if t:
                by_surname[t[-1]].append(i)
                by_surname[t[0]].append(i)
        for aid, an in zip(authors[authors.institution == inst].author_id, authors[authors.institution == inst].author):
            at = tokens(an)
            if len(at) < 2:
                continue
            cands = {i for s in (at[-1], at[0]) for i in by_surname.get(s, [])}
            hits = [(RANK[q], i, q) for i in cands if (q := match(ftok[i], at))]
            if hits:
                best[(inst, aid)] = sorted(hits, reverse=True)

    rows, ambiguous = [], []
    for (inst, aid), hits in best.items():
        if len(hits) > 1 and hits[0][0] == hits[1][0]:
            ambiguous.append((inst, aid, [fac.name[i] for _, i, _ in hits]))
            continue
        _, i, q = hits[0]
        rows.append({"institution": inst, "author_id": aid, "faculty_name": fac.name[i],
                     "department": fac.department[i], "designation": fac.designation[i],
                     "faculty_status": fac.faculty_status[i], "match_quality": q})
    amap = pd.DataFrame(rows)
    amap = amap.merge(authors[["institution", "author_id", "author", "orcid", "papers", "first_year", "last_year"]],
                      on=["institution", "author_id"], how="left")
    # how many different author ids carry each name among ALL authors in our data (all co-authors,
    # all institutes): "Pankaj Kumar" is common even if only two of them are at one institute
    allauth = pd.read_csv(OUT / "authorships.csv", usecols=["author_id", "author_name"]).dropna().drop_duplicates("author_id")
    name_ids = allauth.groupby(allauth.author_name.map(lambda n: frozenset(tokens(n)))).size().to_dict()
    amap, rejected = prune(amap, name_ids)
    is_hom = pd.Series([k in homonym_names for k in zip(amap.institution, amap.faculty_name)], index=amap.index)
    rejected = pd.concat([rejected, amap[is_hom].assign(reason="same name, different people on faculty list")])
    amap = amap[~is_hom]
    fac = fac[~fac.homonym].drop(columns="homonym")
    if len(homonyms):                              # each same-name colleague as their own person
        fac = pd.concat([fac, homonyms.drop(columns="plain_name")], ignore_index=True)
    amap, rejected, work_over = apply_overrides(amap, rejected, fac, authors)
    amap.to_csv(OUT / "author_faculty_map.csv", index=False)
    rejected.to_csv(OUT / "faculty_match_rejected.csv", index=False)

    # per faculty totals over all their ids (a paper counted once even if two of their ids are on it)
    m = pd.read_csv(OUT / "group15_data.csv", dtype=str)
    key = dict(zip(zip(amap.institution, amap.author_id), zip(amap.faculty_name, amap.department, amap.faculty_status)))
    hit = [key.get(k) for k in zip(m.institution, m.author_id)]
    m["is_faculty"] = ["TRUE" if h else "FALSE" for h in hit]
    m["faculty_name"] = [h[0] if h else "" for h in hit]
    m["department"] = [h[1] if h else "" for h in hit]
    m["faculty_status"] = [h[2] if h else "" for h in hit]
    # paper-level corrections (records that mix two people): faculty_overrides.csv
    finfo = fac.drop_duplicates(["institution", "name"]).set_index(["institution", "name"])
    for r in work_over.itertuples(index=False):
        k = (m.institution == r.institution) & (m.openalex_work_id == r.work_id) & (m.author_id == r.author_id)
        if r.action == "work_unassign":
            m.loc[k, ["is_faculty", "faculty_name", "department", "faculty_status"]] = ["FALSE", "", "", ""]
        else:
            f = finfo.loc[(r.institution, r.faculty_name)]
            m.loc[k, ["is_faculty", "faculty_name", "department", "faculty_status"]] = [
                "TRUE", r.faculty_name, f.department, f.faculty_status]
    m.to_csv(OUT / "group15_data.csv", index=False)

    fp = m[m.is_faculty == "TRUE"].drop_duplicates(["institution", "faculty_name", "openalex_work_id"]).copy()
    fp["citations"] = pd.to_numeric(fp.citations, errors="coerce").fillna(0).astype(int)
    stats = fp.groupby(["institution", "faculty_name"]).agg(
        papers=("openalex_work_id", "size"), citations=("citations", "sum"),
        h_index_2016_2026=("citations", h_index)).reset_index()
    ids = amap.groupby(["institution", "faculty_name"]).agg(
        author_ids=("author_id", ";".join), n_ids=("author_id", "size"), common_name=("common_name", "any"),
        match_quality=("match_quality", lambda s: max(s, key=RANK.get))).reset_index()
    amb_names = defaultdict(set)
    for inst, aid, names in ambiguous:
        for n in names:
            amb_names[(inst, n)].add(aid)
    out = (fac.rename(columns={"name": "faculty_name"})
           .merge(ids, on=["institution", "faculty_name"], how="left")
           .merge(stats, on=["institution", "faculty_name"], how="left"))
    out["ambiguous_ids"] = [";".join(sorted(amb_names.get((i, n), []))) for i, n in zip(out.institution, out.faculty_name)]
    hom_people = set(zip(homonyms.institution, homonyms.name)) if len(homonyms) else set()
    out["status"] = ["matched" if isinstance(a, str) else
                     ("same_name_different_people" if (i, n) in hom_people else
                      "ambiguous_only" if amb else "not_found")
                     for a, amb, i, n in zip(out.author_ids, out.ambiguous_ids, out.institution, out.faculty_name)]
    for c in ("n_ids", "papers", "citations", "h_index_2016_2026"):
        out[c] = out[c].fillna(0).astype(int)
    out.to_csv(OUT / "faculty_matched.csv", index=False)

    audit = amap.sample(min(50, len(amap)), random_state=15)[
        ["institution", "faculty_name", "department", "author", "author_id", "orcid", "papers", "match_quality"]]
    audit["correct"] = ""
    audit.to_csv(OUT / "faculty_match_audit.csv", index=False)

    print("faculty per institute:", fac.groupby(["institution", "faculty_status"]).size().to_dict())
    print(out.groupby(["institution", "faculty_status", "status"]).size().unstack(fill_value=0).to_string())
    print("\nauthor ids matched:", len(amap), "| by quality:", amap.match_quality.value_counts().to_dict())
    print("ambiguous author ids (left unmatched):", len(ambiguous))
    print("faculty with several ids:", int((out.n_ids > 1).sum()), "| max ids:", int(out.n_ids.max()))
    rows_f = (m.is_faculty == "TRUE").mean() * 100
    papers_f = m[m.is_faculty == "TRUE"].openalex_work_id.nunique() / m.openalex_work_id.nunique() * 100
    print(f"rows by faculty: {rows_f:.1f}% | papers with >=1 faculty author: {papers_f:.1f}%")


if __name__ == "__main__":
    main()
