"""Merges faculty_to_verify_web.csv (web research on the medium rows that verify_rest.py left unsure)
into faculty_to_verify_updated.csv.

Only rows that are still `unsure` with checked_by 'auto: no decisive evidence' are changed, so hand
answers are never overwritten. Sources: the institutes' own faculty pages, Vidwan, ORCID, ResearchGate,
found by web search restricted to those sites. verified is yes / no / partial / unsure:
  yes      a page says the person is faculty in that department and the paper topics fit
  partial  a faculty member whose OpenAlex record also contains papers of someone else (stray titles named)
  no       a source says this record is not that faculty member (scholar, other institute, other field)
  unsure   no page found, or temporary / ad-hoc staff, or the match could not be checked
"""
import pandas as pd

SHEET = "faculty_to_verify_updated.csv"
d = pd.read_csv(SHEET, dtype=str, keep_default_na=False)
w = pd.read_csv("faculty_to_verify_web.csv", dtype=str, keep_default_na=False)
pos = {tuple(x): i for i, x in enumerate(d[["institution", "name", "department", "reasons"]].itertuples(index=False))
       if d.verified[i] == "unsure" and d.checked_by[i] == "auto: no decisive evidence"}
n, skipped = {}, 0
for x in w.itertuples(index=False):
    i = pos.get((x.institution, x.name, x.department, x.reasons))
    if i is None:
        skipped += 1
        continue
    d.loc[i, ["verified", "notes", "checked_by"]] = [x.web_verdict, x.web_evidence, "web: institute page / Vidwan / ORCID"]
    n[x.web_verdict] = n.get(x.web_verdict, 0) + 1
d.to_csv(SHEET, index=False)
print("merged:", n, "| skipped (already answered by hand):", skipped)
print(d[d.priority == "medium"].verified.value_counts().to_dict())
