"""Step 4 (+ draft of Step 9): turn the raw OpenAlex JSON into clean tables.

Outputs in data/out/:
  papers.csv            one row per paper
  authorships.csv       one row per author per paper
  group15_data_draft.csv  one row per paper per author from OUR institutes,
                          with the 14 required columns (+ ids). Quartile and
                          the two Indian-citation columns are filled later
                          (Steps 6, 7), and faculty filtering in Step 5.
  build_report.txt      counts for the "data and method" slide
"""
import json
import re
from collections import Counter

import pandas as pd

import config


def short_id(url):
    return url.rsplit("/", 1)[-1] if url else None


# Only journal and conference papers are wanted. These OpenAlex types are not papers of either kind.
NOT_PAPERS = {"book", "book-chapter", "book-review", "book-section", "data-paper", "dataset", "dissertation", "editorial",
              "other", "reference-entry", "conference-abstract", "peer-review", "report", "standard"}


# DOI prefixes of repositories and preprint servers (Zenodo, figshare, arXiv, ResearchGate, SSRN, OSF, Research Square, Preprints.org)
REPOSITORY_DOIS = {"10.5281", "10.6084", "10.48550", "10.13140", "10.2139", "10.31219", "10.21203", "10.20944", "10.1101"}


def scopus_types():
    """doi -> 'conference' / 'journal' for works OpenAlex calls book-chapter but Scopus lists as a
    Conference Paper / Article (conference papers printed in book series). Built by scopus_compare.py."""
    p = config.ROOT / "data" / "ref" / "scopus_type_overrides.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p, dtype=str)
    return dict(zip(d.doi, d.venue_type))


SCOPUS = scopus_types()


def venue_types():
    """issn (digits only) -> Scopus source type: journal / tradejournal / conferenceproceeding / bookseries.
    Built by venue_types.py; data/ref/venue_type_overrides.csv (issn, type) wins for venues Scopus gets wrong."""
    ref = config.ROOT / "data" / "ref"
    out = {}
    if (ref / "venue_types.csv").exists():
        d = pd.read_csv(ref / "venue_types.csv", dtype=str, keep_default_na=False)
        out = {i: t for i, t in zip(d.issn, d.scopus_type) if t}
    if (ref / "venue_type_overrides.csv").exists():
        d = pd.read_csv(ref / "venue_type_overrides.csv", dtype=str, keep_default_na=False)
        out.update(dict(zip(d.issn.str.replace("-", ""), d.type)))
    return out


VENUE_TYPE = venue_types()


def venue_kind(src):
    """'journal' / 'conference' / 'series' from Scopus for the venue's ISSNs, or '' when Scopus does not know it."""
    for i in [src.get("issn_l")] + list(src.get("issn") or []):
        t = VENUE_TYPE.get((i or "").replace("-", ""))
        if t:
            return {"journal": "journal", "tradejournal": "journal", "conferenceproceeding": "conference", "bookseries": "series"}.get(t, "")
    return ""


def work_type(w):
    """journal / conference / other (Step 4 rule). 'other' is dropped.

    The venue decides (Scopus source type), not the words in its name: "Proceedings of the National Academy of
    Sciences", "Proceedings of the Royal Society A", "Proceedings of the Institution of Mechanical Engineers" and
    "Proceedings of the Institution of Civil Engineers" are journals; Materials Today: Proceedings and the AIP and
    IOP conference series are conference proceedings; Lecture Notes series are book series carrying conference papers."""
    doi = (w.get("doi") or "").lower().replace("https://doi.org/", "")
    if doi in SCOPUS:
        return SCOPUS[doi]
    src = (w.get("primary_location") or {}).get("source") or {}
    if w.get("type") in NOT_PAPERS:                                          # books, chapters, editorials, datasets
        return "other"
    if src.get("type") == "repository" and not (w.get("type") in ("article", "review", "conference-paper") and doi
                                                 and doi.split("/")[0] not in REPOSITORY_DOIS):
        return "other"       # preprint servers and copies in repositories; a journal / proceedings DOI keeps the paper
    kind = venue_kind(src)
    if kind == "journal":
        return "journal"
    if kind in ("conference", "series"):
        return "conference"
    # Scopus does not know the venue: fall back on OpenAlex. A "Proceedings" name only means a conference when the
    # paper itself is typed as a conference paper.
    name = (src.get("display_name") or "").lower()
    if (src.get("type") == "conference" or w.get("type") in ("conference-paper", "proceedings-article")
            or "conference" in name and w.get("type") != "article"):
        return "conference"
    if src.get("type") == "journal" or w.get("type") in ("article", "review", "letter"):
        return "journal"
    return "other"


def _norm(t):
    import re
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def merge_duplicate_works(works):
    """Merge records of the SAME paper registered twice (typically a temporary and a final DOI, as Inderscience does, or
    two DOI prefixes for one journal). Two works are the same paper when they have the same normalised title, publication
    years at most one apart, the same venue, and overlapping author lists (surname Jaccard >= 0.5, or one record has no
    authors). Same title with a different author list (e.g. Part 1 / Part 2 of a series) is NOT merged.
    The record with more citations is kept; citations are added (OpenAlex splits them between the copies) and the reference
    lists are united. Every decision is written to data/out/duplicate_audit.csv."""
    from collections import defaultdict
    groups = defaultdict(list)
    for w in works:
        t = _norm(w.get("title"))
        if t:
            groups[t].append(w)
    surnames = lambda w: {((a.get("author") or {}).get("display_name") or "").lower().split()[-1]
                          for a in w.get("authorships") or [] if (a.get("author") or {}).get("display_name")}
    venue = lambda w: _norm((((w.get("primary_location") or {}).get("source") or {}).get("display_name")))
    doi_of = lambda w: (w.get("doi") or "").replace("https://doi.org/", "").lower()
    last_num = lambda d: (re.findall(r"\d+", d) or [""])[-1]
    pairs_f = config.ROOT / "data" / "ref" / "duplicate_pairs.csv"      # pairs confirmed by hand: kept_id, other_id, reason
    manual = {frozenset((a, b)) for a, b in pd.read_csv(pairs_f, dtype=str)[["kept_id", "other_id"]].itertuples(index=False)} if pairs_f.exists() else set()
    drop, audit = set(), []
    for t, g in groups.items():
        if len(g) < 2:
            continue
        g = sorted(g, key=lambda w: -(w.get("cited_by_count") or 0))
        kept = []
        for w in g:
            target = None
            for k in kept:
                sa, sb = surnames(k), surnames(w)
                jac = len(sa & sb) / max(1, len(sa | sb))
                gap = abs((k.get("publication_year") or 0) - (w.get("publication_year") or 0))
                dk, dw = doi_of(k), doi_of(w)
                # Inderscience: a temporary early-access DOI (10.1504/xxx.2016.1000xxxx) and the final DOI of the issue, years apart
                temp = dk.startswith("10.1504/") and dw.startswith("10.1504/") and (re.search(r"\.\d{8}$", dk) or re.search(r"\.\d{8}$", dw))
                vk, vw = venue(k), venue(w)
                same_venue = vk == vw or (min(len(vk), len(vw)) >= 8 and (vk in vw or vw in vk))
                same_year = gap <= 1 or (temp and gap <= 4)
                # same publisher and the same article number at the end of the DOI (two DOI prefixes / mirrors of one paper)
                twin_doi = bool(dk and dw and dk.split("/")[0] == dw.split("/")[0] and last_num(dk) and
                                (last_num(dk) == last_num(dw)) and gap <= 1)
                by_hand = frozenset((short_id(k["id"]), short_id(w["id"]))) in manual
                ok = by_hand or (same_year and same_venue and (jac >= .5 or not sa or not sb)) or (twin_doi and (jac >= .5 or not sa or not sb))
                audit.append({"title": (w.get("title") or "")[:120], "kept_work_id": short_id(k["id"]), "kept_doi": k.get("doi"),
                              "other_work_id": short_id(w["id"]), "other_doi": w.get("doi"), "year_kept": k.get("publication_year"),
                              "year_other": w.get("publication_year"), "same_venue": same_venue, "author_jaccard": round(jac, 2),
                              "citations_kept": k.get("cited_by_count"), "citations_other": w.get("cited_by_count"),
                              "decision": "merged" if ok else "kept separate",
                              "reason": "confirmed by hand (data/ref/duplicate_pairs.csv)" if by_hand else "same title, publisher and article number" if ok and not same_venue else "same title, venue, years within 1 (4 for an Inderscience early-access DOI) and overlapping authors" if ok else
                                        "same title but " + ("different venue" if not same_venue else "different authors" if jac < .5 else "years differ by more than 1")})
                if ok:
                    target = k
                    break
            if target is None:
                kept.append(w)
            else:
                target["cited_by_count"] = (target.get("cited_by_count") or 0) + (w.get("cited_by_count") or 0)
                target["referenced_works"] = sorted(set(target.get("referenced_works") or []) | set(w.get("referenced_works") or []))
                if not target.get("authorships"):
                    target["authorships"] = w.get("authorships")
                drop.add(w["id"])
    pd.DataFrame(audit).to_csv(config.OUT_DIR / "duplicate_audit.csv", index=False)
    return [w for w in works if w["id"] not in drop], len(drop)


def our_insts_of(inst_list):
    """Names of our institutes that appear in one authorship's institutions."""
    found = []
    for inst in inst_list:
        ids = {short_id(inst.get("id"))} | {short_id(x) for x in inst.get("lineage") or []}
        for oid in ids & config.ID_TO_NAME.keys():
            if config.ID_TO_NAME[oid] not in found:
                found.append(config.ID_TO_NAME[oid])
    return found


def load_works():
    works = {}
    for f in sorted(config.RAW_DIR.glob("works_*.json")):
        for w in json.loads(f.read_text())["results"]:
            works[w["id"]] = w  # dedupe on OpenAlex id
    # DOIs found for works OpenAlex lists without one (doi_lookup.py, checked): data/ref/doi_overrides.csv
    f = config.ROOT / "data" / "ref" / "doi_overrides.csv"
    if f.exists():
        for r in pd.read_csv(f, dtype=str).itertuples():
            w = works.get("https://openalex.org/" + r.openalex_work_id)
            if w is not None and not w.get("doi"):
                w["doi"] = "https://doi.org/" + r.doi
    return list(works.values())


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_works()
    report = [f"Unique works downloaded: {len(raw)}"]
    report.append(f"Types before cleaning: {dict(Counter(w.get('type') for w in raw))}")

    works = [w for w in raw if w.get("type") not in config.DROP_TYPES]
    report.append(f"Dropped {len(raw) - len(works)} non-research items ({sorted(config.DROP_TYPES)})")

    # DOI dedupe (keep the first copy with the same DOI)
    seen, deduped = set(), []
    for w in works:
        d = (w.get("doi") or "").lower()
        if d and d in seen:
            continue
        seen.add(d)
        deduped.append(w)
    report.append(f"Dropped {len(works) - len(deduped)} duplicate DOIs")
    works = deduped

    # only journal and conference papers are wanted (book chapters, preprints, books,
    # datasets, ... are removed)
    dropped = Counter(w.get("type") for w in works if work_type(w) == "other")
    works = [w for w in works if work_type(w) != "other"]
    report.append(f"Dropped {sum(dropped.values())} non journal/conference items: {dict(dropped.most_common())}")
    works, n_merged = merge_duplicate_works(works)
    report.append(f"Merged {n_merged} duplicate records of the same paper (see data/out/duplicate_audit.csv)")

    paper_rows, auth_rows = [], []
    no_inst_papers = 0
    for w in works:
        wid = short_id(w["id"])
        src = (w.get("primary_location") or {}).get("source") or {}
        topic = w.get("primary_topic") or {}
        co_insts, co_indian, our_on_paper = [], [], []

        for a in w.get("authorships") or []:
            insts = a.get("institutions") or []
            ours = our_insts_of(insts)
            for n in ours:
                if n not in our_on_paper:
                    our_on_paper.append(n)
            for i in insts:
                nm = i.get("display_name")
                if nm and not our_insts_of([i]) and nm not in co_insts:
                    co_insts.append(nm)
                    if i.get("country_code") == "IN":
                        co_indian.append(nm)
            author = a.get("author") or {}
            auth_rows.append({
                "openalex_work_id": wid,
                "author_id": short_id(author.get("id")),
                "author_name": author.get("display_name"),
                "orcid": author.get("orcid"),
                "institution_names": ";".join(i.get("display_name") or "" for i in insts),
                "country_codes": ";".join(sorted({i.get("country_code") or "" for i in insts if i.get("country_code")})),
                "institutions_detail": ";".join(
                    f"{i.get('display_name')}|{i.get('country_code') or ''}|{i.get('type') or ''}" for i in insts),
                "is_our_inst": bool(ours),
                "our_inst": ";".join(ours),
            })

        if not our_on_paper:
            no_inst_papers += 1
        paper_rows.append({
            "openalex_work_id": wid,
            "doi": w.get("doi"),
            "title": w.get("title"),
            "year": w.get("publication_year"),
            "type": work_type(w),
            "openalex_type": w.get("type"),
            "journal_name": src.get("display_name"),
            "issn": src.get("issn_l"),
            "issn_all": ";".join(src.get("issn") or []),
            "citations": w.get("cited_by_count"),
            "field": (topic.get("field") or {}).get("display_name"),
            "domain": (topic.get("domain") or {}).get("display_name"),
            "our_institutes": ";".join(our_on_paper),
            "coauthor_institutes": ";".join(co_insts),
            "coauthor_indian_institutes": ";".join(co_indian),
            "n_authors": len(w.get("authorships") or []),
            "referenced_works": ";".join(short_id(r) for r in w.get("referenced_works") or []),
        })

    papers = pd.DataFrame(paper_rows)
    auth = pd.DataFrame(auth_rows)
    papers.to_csv(config.OUT_DIR / "papers.csv", index=False)
    auth.to_csv(config.OUT_DIR / "authorships.csv", index=False)

    # --- draft main file: one row per paper per author from our institutes ---
    ours = auth[auth.is_our_inst].copy()
    ours["our_inst"] = ours["our_inst"].str.split(";")
    ours = ours.explode("our_inst")  # an author on 2 of our institutes -> 2 rows
    draft = ours.merge(papers, on="openalex_work_id", how="left")
    draft = draft.rename(columns={"our_inst": "institution", "author_name": "author"})
    draft["group"] = config.GROUP
    draft["quartile"] = ""  # Step 6
    draft["cites_indian_inst"] = ""  # Step 7
    draft["cited_by_indian_inst"] = ""  # Step 7
    cols = ["group", "institution", "author", "title", "year", "type", "journal_name",
            "issn", "doi", "citations", "quartile", "coauthor_institutes",
            "cites_indian_inst", "cited_by_indian_inst",
            "openalex_work_id", "author_id", "orcid", "field", "domain"]
    draft = draft[cols].sort_values(["institution", "year", "openalex_work_id"])
    draft.to_csv(config.OUT_DIR / "group15_data_draft.csv", index=False)

    # --- report ---
    report += [
        f"Papers kept: {len(papers)}",
        f"Papers with no author matched to our institutes (lineage mismatch): {no_inst_papers}",
        f"Papers per type: {papers.type.value_counts().to_dict()}",
        f"OpenAlex types of papers labelled 'other': {papers[papers.type == 'other'].openalex_type.value_counts().to_dict()}",
        f"Papers without DOI: {int(papers.doi.isna().sum())}",
        f"Papers without journal/source: {int(papers.journal_name.isna().sum())}",
        f"Papers per year: {papers.year.value_counts().sort_index().to_dict()}",
        f"Authorship rows: {len(auth)}; rows from our institutes: {int(auth.is_our_inst.sum())}",
        "Papers per institute (a paper counts for each of our institutes on it):",
    ]
    for name in config.INSTITUTES:
        n = papers.our_institutes.str.contains(name, regex=False).sum()
        report.append(f"  {name}: {n}")
    report.append(f"Distinct our-institute author IDs: {ours.author_id.nunique()}")
    report.append(f"Draft rows (paper x author x institute): {len(draft)}")
    text = "\n".join(report)
    (config.OUT_DIR / "build_report.txt").write_text(text)
    print(text)


def forget_filtered_snapshot():
    """A fresh build makes the remembered unfiltered tables of corpus_filter.py stale (enrich.py's guard compares against them)."""
    import shutil
    shutil.rmtree(config.OUT_DIR / "all_authors", ignore_errors=True)


if __name__ == "__main__":
    main()
    forget_filtered_snapshot()
