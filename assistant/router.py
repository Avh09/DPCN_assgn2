"""Deterministic question router: finds the entities in a question, picks allowlisted tools, remembers context.

Used when no LLM key is configured, and as the safety net when the LLM call fails. It covers the question types in the
project brief (collaboration compatibility, suggestions, paths, brokers, resilience, comparisons, papers and citations).
It never invents an entity: names are matched against the verified faculty list, the institutes and the paper titles, and an
ambiguous match is returned as a clarification request.
"""
import re

from rapidfuzz import fuzz, process

from . import entities as E
from .data import INSTS, store

STOP = {"professor", "prof", "dr", "can", "could", "collaborate", "with", "and", "or", "the", "of", "from", "between", "compare", "suggest", "show", "who", "what", "which",
        "why", "how", "is", "are", "does", "do", "in", "at", "for", "a", "an", "to", "their", "them", "his", "her", "mutual", "common", "shortest", "path", "network"}


def _fac_index():
    S = store()
    if not hasattr(S, "_fac_norm"):
        S._fac_norm = {i: E.norm(n) for i, n in zip(S.faculty.index, S.faculty.faculty_name)}
        S._fac_norm_rev = {}
        for i, n in S._fac_norm.items():
            S._fac_norm_rev.setdefault(n, []).append(i)
    return S._fac_norm, S._fac_norm_rev


def _trailing_institute(question, span):
    """' (MANIT)' / ', NIT Silchar' / ' of NITJ' right after a name, so the name is resolved within that institute."""
    m = re.search(re.escape(span) + r"\s*(?:\(|,|\bof\b|\bat\b|\bfrom\b)\s*((?:manit|nitj|nits|nit\s+\w+|mnit\s+\w+)(?:\s+(?:bhopal|jamshedpur|silchar))?)", question, re.I)
    return f" ({m.group(1)})" if m else ""


def extract_faculty(question):
    """[(span_text, resolution)] for faculty named in the question, longest spans first, non-overlapping."""
    norms, rev = _fac_index()
    words = re.findall(r"[A-Za-z][A-Za-z\.\-']*", question)
    used, found = [False] * len(words), []
    choices = list(set(norms.values()))
    for n in (4, 3, 2, 1):
        for s in range(len(words) - n + 1):
            if any(used[s:s + n]):
                continue
            span = words[s:s + n]
            low = [w.lower().strip(".") for w in span]
            if any(w in STOP for w in low):
                continue
            text = E.norm(" ".join(span))
            if len(text) < 4 or (n == 1 and not span[0][0].isupper()):
                continue
            if n == 1:
                hits = [i for nm, ids in rev.items() for i in ids if text in nm.split() and len(text) >= 5]
                if 1 <= len({store().faculty.at[i, "faculty_name"] for i in hits}) <= 2 and hits:
                    res = E.resolve_faculty(span[0])
                    if res["candidates"] and res["candidates"][0]["score"] >= 70:
                        found.append((s, " ".join(span), res))
                        for k in range(s, s + n):
                            used[k] = True
                continue
            m = process.extractOne(text, choices, scorer=fuzz.token_sort_ratio)
            if m and m[1] >= (92 if span[0][0].isupper() else 97):
                res = E.resolve_faculty(" ".join(span) + _trailing_institute(question, " ".join(span)))
                if res["candidates"]:
                    found.append((s, " ".join(span), res))
                    for k in range(s, s + n):
                        used[k] = True
    return [(t, r) for _, t, r in sorted(found)]


INST_PAT = re.compile(r"\b(manit|nitj|nits|nit\s+(?:bhopal|jamshedpur|silchar)|mnit\s+bhopal|iiit[\s\-]?\w*|iit[\s\-]?\w+|iisc|iiser[\s\-]?\w*|nit\s+\w+)\b", re.I)


def extract_institutes(question):
    out = []
    # "the three NITs", "other NITs", "across NITs" are the plural of NIT, not NIT Silchar (NITS)
    question = re.sub(r"\b(the|three|3|two|all|other|both|these|our|several|many|across|across the|among the|between the|of the)\s+nits\b", r"\1 NIT-institutes",
                      question, flags=re.I)
    for m in INST_PAT.finditer(question):
        r = E.resolve_institute(m.group(0))
        if r["canonical"] or r["candidates"]:
            out.append((m.group(0), r))
    for m in re.finditer(r"(International|Indian|National) Institute of [A-Za-z ,]+?(?=[\?\.,;]|$| and | with | at )", question):
        r = E.resolve_institute(m.group(0).strip())
        if r["canonical"] or r["candidates"]:
            out.append((m.group(0), r))
    for m in re.finditer(r"\b((?:[A-Z][A-Za-z\.]+\s+){1,4}(?:University|Institute|College|Laboratory|Academy|Vidyapeeth))\b", question):
        r = E.resolve_institute(m.group(1).strip())
        if r["canonical"] or r["candidates"]:
            out.append((m.group(1), r))
    for t_, r in out:                       # an exact name match is not ambiguous ("National Institute of Technology Raipur")
        if r["ambiguous"]:
            exact = [c for c in r["candidates"] if E.norm(c) == E.norm(t_)]
            if len(exact) == 1:
                r["canonical"], r["ambiguous"], r["candidates"] = exact[0], False, exact
    # a fragment inside a longer, resolved institute name ("National Institute" in "National Institute of Technology Raipur") is not a mention of its own
    whole = [t_ for t_, r in out if r["canonical"]]
    out = [(t_, r) for t_, r in out if r["canonical"] or not any(t_ != w and t_.lower() in w.lower() for w in whole)]
    seen, uniq = set(), []
    for t, r in out:
        k = r["canonical"] or tuple(r["candidates"])
        if k not in seen:
            seen.add(k)
            uniq.append((t, r))
    return uniq


NOT_NAMES = {"tell", "me", "about", "give", "list", "top", "papers", "paper", "network", "energy", "solar", "computer", "science", "engineering", "department",
             "mechanical", "civil", "electrical", "chemical", "bhopal", "jamshedpur", "silchar", "pagerank", "new", "delhi", "private", "indian", "states", "state",
             "faculty", "please", "hi", "hello", "thanks", "ai", "ml", "iot", "research", "assistant", "dashboard", "kindly", "sir", "madam", "nit", "nits", "nitj", "manit"}


def unknown_names(question, found_spans):
    """Runs of two or three capitalised words that look like a person but matched no verified faculty member."""
    covered = set(" ".join(found_spans).lower().split())
    # long institution names ("National Institute of Technology Raipur", "Indian Institute of Science") are not people
    question = re.sub(r"(?:[A-Z][\w\-]*\s+)*(?:Institute|University|College|Laboratory|Academy|Centre|Center)\s+(?:of\s+)?(?:[A-Z&][\w&\-]*\s*,?\s*)*", " ", question)
    runs, cur = [], []
    for w in re.findall(r"[A-Za-z][A-Za-z\.\-]*|[^\sA-Za-z]+", question):
        if re.fullmatch(r"[A-Z][a-z]+", w) and w.lower() not in STOP and w.lower() not in NOT_NAMES:
            cur.append(w)
        else:
            runs.append(cur)
            cur = []
    runs.append(cur)
    out = []
    for r in runs:
        span = " ".join(r)
        # at least two words must be unmatched: "Did Kumarasamy Sudhakar" is a known name after a capitalised verb, "John Smith" is not
        if not 2 <= len(r) <= 3 or sum(w.lower() not in covered for w in r) < 2:
            continue
        if INST_PAT.search(span) or re.search(r"Universit|Institut|College|Laborator|Academy|India|Malaysia|Pradesh|Bengal", span):
            continue
        out.append(span)
    return out


# words the routing rules and tools look for; misspellings of them are corrected (titles of the corpus papers are added at run time)
KEYWORDS = """collaborate collaborator collaborators collaboration collaborations together coauthor coauthors suggest suggestions recommend potential
shortest path between mutual common compare versus difference remove removed removal happens fragile resilience robust robustness fragment disrupt
betweenness degree closeness eigenvector clustering coefficient pagerank modularity louvain leiden jaccard participation citations citation cited
cites citing whom flows private universities reciprocal impact countries country states places highest lowest most cited papers paper journals
publish published publications output productivity institute institutes faculty professor professors researchers experts expert working research
retracted retraction retractions withdrawn withdrawal communities community departments interdisciplinary strongest pairs bridge brokers broker
network connected review reviews topics fastest growing grown affiliation affiliated leave left malaysia definition meaning explain""".split()


COMMON = """since works worked raise raises raised relatively across today weather please thanks tell show give list find which whose where when
about their them they this that these those would could should might also very more most much many some any each every other others another
able like likely really quite rather already still even only just first second third last next good best better high higher low lower""".split()


def _vocab():
    """(targets, frequency, known words, faculty-name tokens). Targets are what a typo may be corrected to; known words are never corrected."""
    S = store()
    if not hasattr(S, "_vocab"):
        from collections import Counter
        from pathlib import Path
        c = Counter(w for t_ in S.papers.title.astype(str).str.lower() for w in re.findall(r"[a-z]{3,}", t_))
        targets = {w for w, n in c.items() if n >= 3} | set(KEYWORDS)
        known = set(c) | set(KEYWORDS) | set(COMMON)
        for d in ("/usr/share/dict/words", "/usr/share/dict/american-english", "/usr/share/dict/british-english"):
            if Path(d).exists():             # an English word list when the machine has one (not needed on Streamlit Cloud)
                known |= {w.strip().lower() for w in open(d, encoding="utf-8", errors="ignore") if w.strip().isalpha()}
                break
        names = {w for n in S.faculty.faculty_name for w in E.norm(n).split() if len(w) >= 4}
        S._vocab = (sorted(targets), c, known, names)
    return S._vocab


def spellfix(question):
    """Correct clearly misspelled ordinary words ('colaborate', 'betweeness', 'enrgy'). A word that is in the English word list,
    in any paper title, a keyword, or close to a faculty name is never changed. Returns (corrected question, [(wrong, right)])."""
    targets, freq, known, names = _vocab()
    fixes = []

    def fix(m):
        w = m.group(0)
        lw = w.lower()
        if len(lw) < 5 or lw in known or lw in STOP or lw in names or process.extractOne(lw, names, scorer=fuzz.ratio, score_cutoff=85):
            return w
        best = process.extract(lw, targets, scorer=fuzz.ratio, score_cutoff=86 if len(lw) >= 7 else 88, limit=3)
        if not best:
            return w
        right = max(best, key=lambda b: (b[1], b[0] in KEYWORDS, freq.get(b[0], 0)))[0]
        fixes.append((w, right))
        return right
    return re.sub(r"[A-Za-z]+", fix, question), fixes


DEPT_WORDS = {"mechanical": "Mechanical Engineering", "civil": "Civil Engineering", "electrical": "Electrical Engineering", "electronics": "Electronics",
              "computer": "Computer Science and Engineering", "cse": "Computer Science and Engineering", "chemistry": "Chemistry", "chemical": "Chemical Engineering",
              "physics": "Physics", "mathematics": "Mathematics", "maths": "Mathematics", "energy": "Energy Science and Engineering", "metallurg": "Metallurgical",
              "materials": "Materials", "architecture": "Architecture and Planning", "management": "Management", "humanities": "Humanities",
              "production": "Production and Industrial Engineering", "biolog": "Biological Science", "bioinformatics": "Bioinformatics", "applications": "Computer Applications"}


def _department_in(ql):
    for k, v in DEPT_WORDS.items():
        if re.search(r"\b" + k, ql):
            return v
    return None


def _years(ql):
    """(year_from, year_to) from 'since 2022', 'after 2020', 'in 2023', 'before 2019', 'between 2018 and 2021', '2018-2021'."""
    m = re.search(r"between\s+(20\d\d)\s+and\s+(20\d\d)|\b(20\d\d)\s*(?:-|\u2013|to)\s*(20\d\d)\b", ql)
    if m:
        a, b = [int(x) for x in m.groups() if x]
        return min(a, b), max(a, b)
    m = re.search(r"\b(since|from|after)\s+(20\d\d)\b", ql)
    if m:
        return int(m.group(2)) + (1 if m.group(1) == "after" else 0), None
    m = re.search(r"\b(before|until|till|up to)\s+(20\d\d)\b", ql)
    if m:
        return None, int(m.group(2)) - (1 if m.group(1) == "before" else 0)
    m = re.search(r"\b(?:in|during)\s+(20\d\d)\b", ql)
    if m:
        return int(m.group(1)), int(m.group(1))
    return None, None


def _num(question, default):
    m = re.search(r"\b(?:top|suggest|recommend|give me|list)?\s*(\d{1,2})\b", question)
    return int(m.group(1)) if m else default


def _ctx_update(ctx, fac_ids=None, inst=None):
    if fac_ids:
        ctx["faculty"] = fac_ids
    if inst:
        ctx["institute"] = inst
    return ctx


def _clean_topic(t):
    """'solar energy at nit silchar' -> 'solar energy'; 'blockchain technology' -> 'blockchain'."""
    t = re.sub(r"\s+(?:at|in|from|of|within)\s+(?:the\s+)?(?:manit|nitj|nits|mnit|nit|iit|iiit)\b.*$", "", t.strip())
    t = re.sub(r"\s+(?:technolog\w*|research|field|area|domain|topic)s?$", "", t)
    return t.strip() or t


def route(question, ctx=None):
    """Returns {"calls": [(tool, args)], "clarify": {...} | None, "ctx": ctx, "note": str}."""
    ctx = dict(ctx or {})
    q = re.sub(r"(\w)['’]s\b", r"\1", question.strip())          # "Sudhakar's h-index" -> "Sudhakar h-index"
    qfix, fixes = spellfix(q)
    ql = qfix.lower()
    # an all-lowercase question ("can rajesh purohit collaborate with samuel rokhum") is matched with capitalised words
    facs = extract_faculty(q if re.search(r"[A-Z]", q) else " ".join(w[:1].upper() + w[1:] for w in q.split()))
    insts = extract_institutes(q)
    # drop institute matches that are really part of a faculty span or just our own institute abbreviations used as filters
    clarify = None
    ids = []
    for text, r in facs:
        if r["ambiguous"]:
            clarify = {"entity": "faculty", "query": text, "candidates": r["candidates"]}
            break
        ids.append(r["best"])
    if clarify:
        return {"calls": [], "clarify": clarify, "ctx": ctx}
    # a pair question that names someone we cannot find: say so instead of answering about the other person only
    if len(ids) < 2 and re.search(r"collaborat|work together|co-?author|path|between|mutual|common|compare|\bvs\b|versus|\band\b", ql):
        unk = unknown_names(q, [t_ for t_, _ in facs])
        if unk:
            return {"calls": [], "clarify": {"entity": "faculty", "query": unk[0], "candidates": []}, "ctx": ctx}
    pronoun = bool(re.search(r"\b(they|them|their|those two|both|he|she|his|her|this person|that person|him)\b", ql))
    if not ids and pronoun and ctx.get("faculty"):
        ids = list(ctx["faculty"])
    inst_names = [(r["canonical"] or (r["candidates"][0] if r["candidates"] else None)) for _, r in insts]
    inst_amb = [r for _, r in insts if r["ambiguous"]]
    if inst_amb:
        return {"calls": [], "clarify": {"entity": "institute", "query": insts[0][0], "candidates": inst_amb[0]["candidates"]}, "ctx": ctx}
    # the institute of an earlier turn is reused only when the question points back to it ("there", "this institute")
    inst = inst_names[0] if inst_names else (ctx.get("institute") if re.search(r"\b(there|this institute|that institute|the same institute|same nit)\b", ql) else None)
    calls = []
    f1 = ids[0] if ids else None
    f2 = ids[1] if len(ids) > 1 else None

    ours = [n for n in inst_names if n in INSTS]
    if re.search(r"retract|retrac|withdrawn|withdrawal", ql):
        calls.append(("retracted_papers", {"faculty": f1} if f1 else {"institute": ours[0]} if ours else {}))
    elif not ids and re.search(r"\bregion|regional|same state|state[- ]level|within (?:the |their |its )?(?:own )?states?|nearby|\blocal\b|locality|geograph|proximity|distance|close by|neighbou?ring", ql) \
            and re.search(r"collab|partner|co-?author|work|link|connect|joint", ql):
        calls.append(("regional_collaboration", {"institute": ours[0]} if len(ours) == 1 else {}))
    elif not ids and re.search(r"\bdepartments?\b|\bdept\b", ql) and not re.search(r"communit|span|bridge|connect|interdisciplinar|different department|other department|another department|across departments", ql):
        dep = _department_in(ql)
        metric = ("papers_per_faculty" if re.search(r"per faculty|productiv|per person", ql) else "q1" if re.search(r"q1", ql) else
                  "citations" if re.search(r"citation|cited", ql) else "papers" if re.search(r"papers|output|publish", ql) else "median_h_index")
        if re.search(r"\b(faculty|professors?|researchers?|who)\b", ql) and dep:
            yf, yt = _years(ql)
            calls.append(("top_faculty", {"metric": "citations" if metric == "citations" else "h_index" if metric == "median_h_index" else "papers",
                                          "institute": ours[0] if ours else None, "department": dep, "n": _num(ql, 5) if re.search(r"top\s*\d+", ql) else 5,
                                          "year_from": yf, "year_to": yt}))
        else:
            calls.append(("department_stats", {"institute": ours[0] if len(ours) == 1 else None, "department": dep, "metric": metric}))
    elif not ids and re.search(r"\b(top|best|leading|most cited|highest)\b", ql) and re.search(r"\b(faculty|professors?|researchers?|people)\b", ql) \
            and _department_in(ql) and re.search(r"engineering|department|\bdept\b|chemistry|physics|mathematics|maths|management|humanities|architecture|applications|bioinformatics", ql):
        yf, yt = _years(ql)
        metric = "h_index" if re.search(r"h-?index", ql) else "papers" if re.search(r"papers|productiv", ql) else "citations"
        calls.append(("top_faculty", {"metric": metric, "institute": ours[0] if ours else None, "department": _department_in(ql),
                                      "n": _num(re.sub(r"20\d\d", "", ql), 5) if re.search(r"top\s*\d+", ql) else 5, "year_from": yf, "year_to": yt}))
    elif len(ours) >= 2 and re.search(r"cit", ql) and re.search(r"whom|between|flow|each other", ql) and not re.search(r"private", ql):
        calls.append(("citation_flows", {"citing": ours[0], "cited": ours[1]}))
    elif re.search(r"(top|highest|first|#\s*1|number one|most important)\W+(?:\w+\W+){0,2}pagerank|pagerank\W+(?:\w+\W+){0,2}(top|highest)", ql) and not ids:
        pp = store().papers.dropna(subset=["pagerank"])
        if ours:
            pp = pp[pp.our_institutes.str.contains(ours[0], regex=False)]
        calls.append(("explain_paper_pagerank", {"paper": pp.pagerank.idxmax()}))
    elif re.search(r"\b(what is|what does|what are|define|meaning of|explain)\b", ql) and re.search(r"betweenness|degree|closeness|eigenvector|clustering|k-?core|participation|pagerank|fwci|h-?index|modularity|louvain|leiden|jaccard|q1 share", ql) and not ids:
        m = re.search(r"betweenness|degree|closeness|eigenvector|clustering|k-?core|participation|pagerank|fwci|h-?index|modularity|louvain|leiden|jaccard|q1 share", ql)
        calls.append(("explain_metric", {"name": m.group(0)}))
    elif re.search(r"fwci|impact|citation", ql) and re.search(r"countr|\bus\b|\busa\b|united states|delhi|states?\b|places?|where|location|abroad|foreign|partner", ql) and re.search(r"rais|lift|boost|higher|lower|reduc|increase|best|highest|lowest|which|does|do ", ql) and not re.search(r"cites? us|cites? them|private|reciproc", ql):
        calls.append(("partner_place_impact", {"institute": next((n for n in inst_names if n in INSTS), None)}))
    elif re.search(r"private|non-?government|reciproc|cites? (us|them)|we cite|cited by|who cites|more than we cite|give.{0,6}take|boost.{0,20}cit", ql) and re.search(r"cit", ql):
        calls.append(("citation_give_take", {"institute": next((n for n in inst_names if n in INSTS), None)}))
    elif re.search(r"\bwhy\b|\bhow come\b|reason|explain|what makes|yearly|every year|each year|per year|by year", ql) and re.search(r"paper|publish|output|productiv|research", ql) and re.search(r"institute|nit|manit|all 3|three|which", ql) and not ids:
        calls.append(("explain_output_difference", {}))
    elif re.search(r"remov|delet|drop|leav", ql) and re.search(r"graph|network|collaborat|researcher|faculty|node|what happens", ql) and ids:
        calls.append(("simulate_node_removal", {"faculty_list": ids}))
    elif re.search(r"shortest\s+(collaboration\s+)?path|path between|how (are|is) .* connected", ql) and f1 and f2:
        calls.append(("get_shortest_collaboration_path", {"a": f1, "b": f2}))
    elif re.search(r"mutual|common (co-?authors|collaborators)|shared collaborators|mutual collaborators", ql) and f1 and f2:
        calls.append(("get_common_collaborators", {"a": f1, "b": f2}))
    elif re.search(r"collaborat|work together|co-?author|compatib|team up|joint", ql) and f1 and f2:
        calls.append(("assess_collaboration", {"a": f1, "b": f2}))
    elif re.search(r"suggest|recommend|potential collaborators|who should|find .*collaborators|collaborators for", ql) and f1:
        scope = "other_nits" if re.search(r"another nit|other nit|other two|different (nit|institute)|outside (my|their|the) institute", ql) else "same_institute" if re.search(r"same institute|within (the )?institute|same nit", ql) else "any"
        args = {"faculty": f1, "k": _num(ql, 5), "scope": scope, "different_department": bool(re.search(r"different department|other department|another department", ql))}
        m = re.search(r"(?:in|on|field of|working (?:in|on))\s+([a-z][a-z &\-]+?)(?:\s+(?:with|who|that)|[\?\.]|$)", ql)
        if m and re.search(r"field|topic|area|subfield|ai|machine|energy|materials|computer", m.group(1)):
            args["field"] = m.group(1)
        calls.append(("recommend_collaborators", args))
    elif not ids and (m_t := re.search(r"(?:working|work|works|research(?:ing)?|interested|specialis[ez]e?d?|expert(?:s|ise)?|experience|focus(?:ed|ing)?)\s+(?:in|on|with)\s+([a-z0-9][a-z0-9 \-/&]+?)(?:\s+(?:technolog\w*|research|field|area|domain|topic)s?)?(?=[,\.\?;]|\s+(?:who|whose|which|what|and|can|so|how|i\b)|$)", ql)) and re.search(
            r"faculty|professor|expert|researcher|collaborat|approach|contact|guide|supervis|mentor|who|best|suggest|recommend", ql):
        calls.append(("find_experts", {"topic": _clean_topic(m_t.group(1)), "institute": next((n for n in inst_names if n in INSTS), None)}))
    elif not ids and (m_t := re.search(r"(?:faculty|professors?|experts?|researchers?)\s+(?:who\s+(?:work|works|research|study)\s+)?(?:in|on|for|with|of)\s+([a-z0-9][a-z0-9 \-/&]+?)(?=[,\.\?;]|\s+(?:who|whose|which|at|in|from|and)|$)", ql)) and not re.search(r"highest|most cited|top \d|betweenness|degree", ql):
        calls.append(("find_experts", {"topic": _clean_topic(m_t.group(1)), "institute": next((n for n in inst_names if n in INSTS), None)}))
    elif not ids and re.search(r"collaborat|work(s|ed)? with|partner|joint|co-?author|link|tie|connect", ql) and (
            any(r["kind"] == "partner" for _, r in insts) or re.search(r"\b(iits?|iiits?|nits?|iisers?|csir|drdo|dae|icar|isro)\b(?!\s+(bhopal|jamshedpur|silchar))", ql)):
        part = next((t for t, r in insts if r["kind"] == "partner"), None)
        if part is None:
            part = re.search(r"\b(iits?|iiits?|nits?|iisers?|csir|drdo|dae|icar|isro)\b", ql).group(1).rstrip("s")
        mine = next((n for n in inst_names if n in INSTS), None)
        calls.append(("partner_institutes", {"query": part, "institute": mine}))
    elif re.search(r"collaborat|work with|partner", ql) and f1 and inst_names and inst_names[0] != store().faculty.at[f1, "institution"]:
        calls.append(("assess_institute_collaboration", {"faculty": f1, "institute": inst_names[0]}))
    elif re.search(r"\bcompare\b|\bvs\b|versus|difference between", ql) and f1 and f2:
        calls.append(("compare_faculty", {"a": f1, "b": f2}))
    elif re.search(r"resilien|fragment|robust|fragile|disrupt|targeted (attack|removal)", ql):
        calls.append(("resilience_summary", {"scope": inst or "all"}))
    elif re.search(r"(at least|min(imum)?|only keep|only .* with)\s*(\d+)\s*(shared|joint|co-?authored)?\s*papers", ql):
        n = int(re.search(r"(\d+)\s*(shared|joint|co-?authored)?\s*papers", ql).group(1))
        calls.append(("filter_network_by_weight", {"min_joint_papers": n, "scope": inst or "all"}))
    elif re.search(r"high(est)? betweenness", ql) and re.search(r"low(er)? degree|few(er)? collaborators|relatively low degree", ql):
        calls.append(("faculty_pattern", {"pattern": "high_betweenness_low_degree", "institute": inst}))
    elif re.search(r"high citations?|highly cited", ql) and re.search(r"few(er)? collaborators|low degree|not (highly )?connected", ql):
        calls.append(("faculty_pattern", {"pattern": "high_citations_few_collaborators", "institute": inst}))
    elif re.search(r"(highly|well) connected", ql) and re.search(r"not (highly )?cited|low citations?", ql):
        calls.append(("faculty_pattern", {"pattern": "connected_but_low_citations", "institute": inst}))
    elif re.search(r"bridge|broker|connect.*(department|computer science|mechanical)|interdisciplinary", ql) and not re.search(r"communit", ql):
        calls.append(("faculty_pattern", {"pattern": "interdisciplinary_bridges", "institute": inst}))
    elif re.search(r"communit", ql) and re.search(r"interdisciplinary|span|multiple departments|across departments|mixed", ql):
        calls.append(("interdisciplinary_communities", {"n": 5}))
    elif re.search(r"strongest.*pair|most joint papers|closest collaborat", ql):
        calls.append(("strongest_pairs", {"kind": "cross_institute" if re.search(r"cross|between institutes|different institutes", ql) else "any", "n": 8}))
    elif re.search(r"(connect|link).*(manit|nitj|nits|institutes)", ql) and re.search(r"faculty|who|which", ql) and len(inst_names) >= 2:
        calls.append(("strongest_pairs", {"kind": "cross_institute", "n": 10}))
    elif re.search(r"most important|important bridge|bridge researchers|highest betweenness|brokers", ql):
        calls.append(("top_faculty", {"metric": "betweenness", "institute": inst, "n": _num(ql, 8)}))
    elif re.search(r"clustering coefficient|fragmented|connected components|network (structure|summary)|how connected", ql):
        calls.append(("network_overview", {"scope": inst or "all"}))
    elif re.search(r"\bcompare\b|\bvs\b|versus|which institute|better|best|h-?index|growing|improving|higher|impact", ql) and (len(inst_names) >= 1 or re.search(r"institute", ql)) and not ids:
        calls.append(("compare_institutes", {"institutes": inst_names}))
    elif re.search(r"review", ql) and re.search(r"cited|citation|paper", ql):
        calls.append(("review_analysis", {"institute": inst}))
    elif re.search(r"fastest growing|grown fastest|grew fastest|topics? (grew|grown|growth)", ql):
        m = re.search(r"(20\d\d)", ql)
        calls.append(("fastest_growing_topics", {"since": int(m.group(1)) if m else 2020}))
    elif re.search(r"cit(es|ation flow|ing)|who cites", ql) and len(inst_names) >= 2:
        calls.append(("citation_flows", {"citing": inst_names[0], "cited": inst_names[1]}))
    elif re.search(r"citation flow|cites whom|who cites whom", ql):
        calls.append(("citation_flows", {}))
    elif re.search(r"pagerank", ql) and not ids:
        m = re.search(r"paper\s+['\"“]?(.+?)['\"”]?\s*(?:have|has|get|rank|\?|$)", q, re.I)
        calls.append(("explain_paper_pagerank", {"paper": m.group(1)}) if m else ("top_papers", {"metric": "pagerank", "n": 8, "institute": inst}))
    elif re.search(r"(highest|most|top|maximum|best).*(citation|cited|cites)", ql) and re.search(r"\b(faculty|faculties|professors?|researchers?|authors?|person|people|who)\b", ql) and not re.search(r"papers?", ql):
        yf, yt = _years(ql)
        calls.append(("top_faculty", {"metric": "citations", "institute": inst, "n": _num(re.sub(r"20\d\d", "", ql), 8) if re.search(r"top\s*\d+", ql) else 5,
                                      "year_from": yf, "year_to": yt}))
    elif re.search(r"highest .*citation|most cited|top .*papers", ql):
        yf, yt = _years(ql)
        calls.append(("top_papers", {"metric": "citations", "institute": inst, "n": _num(re.sub(r"20\d\d", "", ql), 8), "year_from": yf, "year_to": yt}))
    elif f1 and f2 is None and re.search(r"ego|around|neighbou?rhood|network (for|of)", ql):
        calls.append(("get_ego_network", {"faculty": f1, "radius": 1}))
    elif f1 and not f2:
        calls.append(("get_faculty_profile", {"faculty": f1}))
    elif inst and inst in INSTS:
        calls.append(("institute_profile", {"institute": inst}))
    elif len(q.split()) <= 3 and re.fullmatch(r"[A-Za-z\.\s]+", q or "-"):
        r = E.resolve_faculty(q)
        if not r["candidates"] and len(q.split()) == 1 and len(q) >= 5:       # "Sudhakr": compare with each surname / given name
            tok = process.extractOne(q.lower(), _vocab()[3], scorer=fuzz.ratio, score_cutoff=85)
            if tok:
                r = E.resolve_faculty(tok[0])
        if r["candidates"] and r["candidates"][0]["score"] >= 85:
            if r["ambiguous"]:
                return {"calls": [], "clarify": {"entity": "faculty", "query": q, "candidates": r["candidates"]}, "ctx": ctx}
            ids = [r["best"]]
            calls.append(("get_faculty_profile", {"faculty": r["best"]}))
    ctx = _ctx_update(ctx, ids if ids else None, inst if inst_names else None)
    return {"calls": calls, "clarify": None, "ctx": ctx, "fixes": fixes}


HELP = ("I can analyse the verified-faculty collaboration network and the paper and citation data of MANIT Bhopal, NIT Jamshedpur and NIT Silchar. Try:\n"
        "- *Can Rajesh Purohit collaborate with Samuel Lalthazuala Rokhum?*\n- *Suggest five potential collaborators for Biplab Das in another NIT.*\n"
        "- *Show the shortest path between Vijay Bhaskar Semwal (MANIT) and Biplab Das.*\n- *Which faculty have high betweenness but relatively low degree?*\n"
        "- *Compare MANIT and NIT Silchar.*  - *How fragile is the NIT Jamshedpur collaboration network?*\n- *Why does this paper have a high PageRank?*  - *What is betweenness?*")
