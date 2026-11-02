"""Merges faculty_to_verify_low_web.csv (web research on the 91 low-priority rows: people on a current
faculty page with no OpenAlex author id matched) into faculty_to_verify_updated.csv.

Only rows with priority 'low' and a blank `verified` are changed. Values used here:
  found      the person has papers (OpenAlex / ResearchGate / institute page); most are recent joiners whose
             papers carry an earlier institute's address, a few have papers already in our data under another
             name spelling (see suggested_action in faculty_to_verify_low_web.csv)
  no papers  faculty confirmed, no indexed publications found (not proof)
  no         not faculty: technical / lab staff, visiting professor, or a table heading scraped by mistake
  duplicate  the page name is a truncated copy of a faculty member who is already matched
  unsure     could not be settled from public pages
"""
import pandas as pd

SHEET = "faculty_to_verify_updated.csv"
d = pd.read_csv(SHEET, dtype=str, keep_default_na=False)
w = pd.read_csv("faculty_to_verify_low_web.csv", dtype=str, keep_default_na=False)
pos = {tuple(x): i for i, x in enumerate(d[["institution", "name", "department"]].itertuples(index=False))
       if d.priority[i] == "low" and d.verified[i] == ""}
n, skipped = {}, 0
for x in w.itertuples(index=False):
    i = pos.get((x.institution, x.name, x.department))
    if i is None:
        skipped += 1
        continue
    d.loc[i, ["verified", "notes", "checked_by"]] = [x.web_verdict, x.web_evidence, "web: institute page / OpenAlex / ORCID"]
    n[x.web_verdict] = n.get(x.web_verdict, 0) + 1
d.to_csv(SHEET, index=False)
print("merged:", n, "| skipped:", skipped)
print(d[d.priority == "low"].verified.value_counts().to_dict())
