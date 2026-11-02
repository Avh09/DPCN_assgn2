"""Evidence pass over ALL blank medium-priority rows of faculty_to_verify_updated.csv.

verify_auto.py and verify_pages.py only looked at a sample. This applies exactly their rules
(same functions, same conservative thresholds) to every medium row whose `verified` is still blank:

  1. ORCID job at the institute: faculty title -> yes, scholar/student/fellow -> no
  2. faculty page entry (MANIT live pages + any archived copies on disk) whose research area shares
     keywords with the OpenAlex topics of the author record -> yes
  3. ORCID found by name + institute (only if the profile is unique) -> yes / no as in 1
  anything else -> unsure (needs a person)

Writes faculty_to_verify_rest.csv (blank rows only: verdict, source, evidence). Nothing in
faculty_to_verify_updated.csv is changed here; merge_rest.py does that after a check.
"""
import pandas as pd

import config
import verify_auto as va
import verify_pages as vp

SHEET = "faculty_to_verify_updated.csv"


def source(ev):
    if "found by name+institute search" in ev:
        return "auto: ORCID (name search)"
    if "faculty page: found" in ev and "ORCID job here" not in ev:
        return "auto: faculty page + topics"
    return "auto: ORCID"


def main():
    va.CACHE.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(SHEET)                       # NaN for empty cells, which the helper functions expect
    todo = d[(d.priority == "medium") & d.verified.isna()]
    fm = pd.read_csv(config.OUT_DIR / "faculty_matched.csv")
    authors = pd.read_csv(config.OUT_DIR / "authors.csv")
    amap = pd.read_csv(config.OUT_DIR / "author_faculty_map.csv")
    docs = vp.page_texts()
    print("page texts:", {k: len(v) for k, v in docs.items()}, "| rows to check:", len(todo), flush=True)

    rows = []
    for k, (i, row) in enumerate(todo.iterrows(), 1):
        if row.reasons == "ambiguous_match":
            v, ev = va.ambiguous_evidence(row, fm, authors)
            rows.append((i, v, "", ev, "", "", ""))
            print(f"[{k}/{len(todo)}] {row.institution} | {row['name']} | ambiguous -> {v}", flush=True)
            continue
        v, ev = va.judge(row)
        evs = [ev]
        research, emails, topics = set(), set(), []
        if v == "unsure":
            found, research, emails = vp.find_entry(docs.get(row.institution, []), row["name"])
            main_id, topics, here, here_yrs = vp.openalex_main(row, amap)
            shared = vp.shared_keywords(vp.keywords(" ".join(research)), vp.keywords(" ".join(topics)))
            conflict = bool(found and research and topics and not shared)
            if found:
                evs.append(f"faculty page: found ({found} entries); research '{' / '.join(sorted(research))[:120]}'")
                evs.append(f"main OpenAlex record {main_id}: at institute {here_yrs or 'no'}; topics {topics[:4]}")
                evs.append(f"shared keywords: {sorted(shared) or 'none'}")
                n_years = (int(here_yrs.split('-')[1]) - int(here_yrs.split('-')[0]) + 1) if here_yrs else 0
                if len(shared) >= 2 and here and row.page_status != "not listed" and (n_years >= 2 or len(shared) >= 3):
                    v = "yes"
            else:
                evs.append("faculty page: no entry found")
            if v == "unsure" and not isinstance(row.orcid, str):
                oid, n = vp.orcid_search(row["name"], row.institution)
                if oid:
                    here_emp = [e for e in va.orcid_entries(oid, "employments") if va.OURS[row.institution].search(e[0])]
                    for o, r, s, e in here_emp:
                        evs.append(f"ORCID {oid} (found by name+institute search) job here: '{r or 'no title'}', {va.span(s, e)}")
                    if any(va.SCHOLAR.search(r) for o, r, s, e in here_emp):
                        v = "no"
                    elif any(va.FACULTY.search(r) and not va.UNCLEAR.search(r) for o, r, s, e in here_emp):
                        if conflict:
                            evs.append("ORCID says faculty, but the record's topics share nothing with the page's research area: check")
                        elif found or row.page_status != "not listed":
                            v = "yes"
                        else:
                            evs.append("ORCID found by name says faculty, but the person is on no faculty page: check")
                    elif not here_emp:
                        evs.append(f"ORCID {oid} (name+institute search) lists no job here")
                else:
                    evs.append(f"ORCID search: {n} matching profiles" + (" (not unique, not used)" if n > 1 else ""))
        ev_all = " | ".join(x for x in evs if x)
        rows.append((i, v, source(ev_all) if v != "unsure" else "", ev_all, " / ".join(sorted(research))[:300],
                     ", ".join(sorted(emails))[:100], "; ".join(topics)))
        print(f"[{k}/{len(todo)}] {row.institution} | {row['name']} | {row.reasons} -> {v}", flush=True)

    out = todo[["institution", "name", "department", "reasons", "papers", "google_scholar", "openalex", "orcid"]].copy()
    r = pd.DataFrame(rows, columns=["i", "auto_verdict", "auto_source", "auto_evidence", "page_research",
                                    "page_email", "openalex_topics"]).set_index("i")
    out = out.join(r)
    out.to_csv("faculty_to_verify_rest.csv", index=False)
    print("\n", out.groupby(["reasons", "auto_verdict"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
