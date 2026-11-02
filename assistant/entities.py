"""Entity resolution: faculty, institutes, papers, departments, fields.

A name is never silently resolved when it is ambiguous: resolve_faculty returns every plausible candidate and a flag, and the
assistant asks the user to choose. Institute resolution uses an alias table (OpenAlex / official names, abbreviations, and the
IIIT naming trap: "International Institute of Information Technology, Hyderabad" is IIIT Hyderabad) over the three institutes and
every partner institute found in the data.
"""
import re
import unicodedata

from rapidfuzz import fuzz, process

from .data import INSTS, SHORT, store

TITLES = {"dr", "prof", "professor", "mr", "mrs", "ms", "shri", "smt", "er", "ar", "sir"}
INST_ALIASES = {
    "MANIT Bhopal": ["manit", "manit bhopal", "maulana azad national institute of technology", "nit bhopal", "mnit bhopal"],
    "NIT Jamshedpur": ["nitj", "nit jamshedpur", "national institute of technology jamshedpur", "nit jsr"],
    "NIT Silchar": ["nits", "nit silchar", "national institute of technology silchar", "nit silchar assam"],
    # partner names that people write differently
    "International Institute of Information Technology, Hyderabad": ["iiit hyderabad", "iiit-h", "iiith", "iiit h", "international institute of information technology hyderabad"],
    "Indian Institute of Technology Delhi": ["iit delhi", "iitd"], "Indian Institute of Technology Bombay": ["iit bombay", "iitb"],
    "Indian Institute of Technology Kharagpur": ["iit kharagpur", "iit kgp", "iitkgp"], "Indian Institute of Technology Guwahati": ["iit guwahati", "iitg"],
    "Indian Institute of Technology Roorkee": ["iit roorkee", "iitr"], "Indian Institute of Technology Madras": ["iit madras", "iitm"],
    "Indian Institute of Technology Kanpur": ["iit kanpur", "iitk"], "Indian Institute of Science Bangalore": ["iisc", "iisc bangalore", "indian institute of science"],
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z ]", " ", s.replace(".", " "))
    return " ".join(t for t in s.split() if t not in TITLES)


def _tokens(s):
    return norm(s).split()


def name_score(query, cand):
    """0-100. Handles reordered names and initials ('R. Purohit' vs 'Rajesh Purohit')."""
    q, c = _tokens(query), _tokens(cand)
    if not q or not c:
        return 0
    if q == c:
        return 100
    s = max(fuzz.token_sort_ratio(" ".join(q), " ".join(c)), fuzz.token_set_ratio(" ".join(q), " ".join(c)) - 6)
    # initials: every query token must match a candidate token in full or as an initial, surname must match
    ok = all(any(t == u or (len(t) == 1 and u.startswith(t)) or (len(u) == 1 and t.startswith(u)) for u in c) for t in q)
    if ok and c[-1] in q or ok and q[-1] in c:
        s = max(s, 92 if len(q) >= 2 else 70)
    return s


def resolve_faculty(query, institute=None, limit=6):
    """Returns {"candidates": [...], "ambiguous": bool, "best": id | None}. Candidates are sorted by score."""
    S = store()
    f = S.faculty
    if institute:
        inst = resolve_institute(institute)["canonical"]
        if inst in INSTS:
            f = f[f.institution == inst]
    q = query.strip()
    # "Name, MANIT" / "Name (NIT Silchar)" / "Name of NITJ": peel an institute mention off the name
    if not institute:
        low = " " + re.sub(r"[(),]", " ", q.lower()) + " "
        for canon in INSTS:
            for al in sorted(INST_ALIASES[canon], key=len, reverse=True):
                if f" {al} " in low:
                    institute = canon
                    q = re.sub(r"\b(of|at|from|in)\b", " ", re.sub(re.escape(al), " ", re.sub(r"[(),]", " ", q), flags=re.I), flags=re.I)
                    q = " ".join(q.split())
                    f = S.faculty[S.faculty.institution == canon]
                    break
            if institute:
                break
    # exact id
    if q in S.faculty.index:
        r = S.faculty.loc[q]
        return {"candidates": [_cand(r, 100)], "ambiguous": False, "best": q}
    scores = [(name_score(q, n), i) for i, n in zip(f.index, f.faculty_name)]
    scores = sorted([x for x in scores if x[0] >= 70], key=lambda x: -x[0])[:limit]
    cands = [_cand(S.faculty.loc[i], s) for s, i in scores]
    if not cands:
        return {"candidates": [], "ambiguous": False, "best": None}
    top = cands[0]["score"]
    cands = [c for c in cands if c["score"] >= top - 10] if top >= 90 else cands
    near = [c for c in cands if c["score"] >= top - 4]
    ambiguous = len(near) > 1 and not (top == 100 and len([c for c in cands if c["score"] == 100]) == 1)
    return {"candidates": cands, "ambiguous": ambiguous, "best": None if ambiguous else cands[0]["id"]}


def _cand(r, score):
    return {"id": r.id, "name": r.faculty_name, "institution": r.institution, "department": r.department, "papers": int(r.papers), "h_index": int(r.h_index),
            "status": r.faculty_status, "score": int(score)}


def resolve_institute(text):
    """The three institutes or any partner institute in the data. Returns canonical name, kind and candidates."""
    S = store()
    t = norm(text)
    for canon, aliases in INST_ALIASES.items():
        if t == norm(canon) or t in [norm(a) for a in aliases] or any(f" {norm(a)} " in f" {t} " for a in aliases if len(norm(a)) >= 4):
            kind = "ours" if canon in INSTS else "partner"
            return {"canonical": canon, "kind": kind, "candidates": [canon], "ambiguous": False}
    names = sorted(set(S.partners.partner_inst) | set(S.foreign.partner_inst))
    scored = process.extract(t, {n: norm(n) for n in names}, scorer=fuzz.token_set_ratio, limit=5)
    cands = [(n, s) for n, s, _ in [(x[2], x[1], 0) for x in scored] if s >= 85]
    if not cands:
        return {"canonical": None, "kind": "unknown", "candidates": [], "ambiguous": False}
    top = cands[0][1]
    near = [c for c, s in cands if s >= top - 3]
    return {"canonical": near[0] if len(near) == 1 else None, "kind": "partner", "candidates": near, "ambiguous": len(near) > 1}


def resolve_paper(query, limit=5):
    S = store()
    q = query.strip()
    m = re.search(r"10\.\d{4,9}/\S+", q)
    p = S.papers
    if m:
        doi = m.group(0).lower().rstrip(".,;)")
        hit = p[p.doi.str.lower().str.endswith(doi)]
        if len(hit):
            return {"candidates": [_pcand(hit.iloc[0], 100)], "ambiguous": False, "best": hit.iloc[0].openalex_work_id}
    if re.fullmatch(r"W\d+", q):
        if q in p.index:
            return {"candidates": [_pcand(p.loc[q], 100)], "ambiguous": False, "best": q}
    titles = {i: t for i, t in zip(p.index, p.title.map(norm))}
    res = process.extract(norm(q), titles, scorer=fuzz.token_set_ratio, limit=limit)
    cands = [_pcand(p.loc[i], s) for _, s, i in res if s >= 70]
    if not cands:
        return {"candidates": [], "ambiguous": False, "best": None}
    top = cands[0]["score"]
    near = [c for c in cands if c["score"] >= top - 3]
    return {"candidates": cands, "ambiguous": len(near) > 1 and top < 100, "best": cands[0]["id"] if len(near) == 1 or top == 100 else None}


def _pcand(r, score):
    return {"id": r.openalex_work_id, "title": r.title, "year": int(r.year), "journal": r.journal_name, "citations": int(r.citations), "score": int(score)}


def resolve_department(text, institute=None):
    f = store().faculty
    if institute:
        f = f[f.institution == institute]
    deps = sorted(set(f.department))
    t = norm(text)
    short = {"cse": "computer science", "cs": "computer science", "ece": "electronics communication", "eee": "electrical", "ee": "electrical",
             "me": "mechanical", "mech": "mechanical", "civil": "civil", "ce": "civil", "chem": "chemistry"}
    t = " ".join(short.get(w, w) for w in t.split())
    scored = process.extract(t, {d: norm(d) for d in deps}, scorer=fuzz.token_set_ratio, limit=3)
    best = [(x[2], x[1]) for x in scored if x[1] >= 70]
    return {"candidates": [b for b, _ in best], "ambiguous": len(best) > 1 and best[0][1] - best[1][1] < 5, "best": best[0][0] if best else None}


def resolve_field(text):
    p = store().papers
    fields = sorted(set(p.field.dropna()) | set(p.subfield.dropna()))
    scored = process.extract(norm(text), {f: norm(f) for f in fields}, scorer=fuzz.token_set_ratio, limit=3)
    best = [(x[2], x[1]) for x in scored if x[1] >= 75]
    return {"candidates": [b for b, _ in best], "best": best[0][0] if best else None}
