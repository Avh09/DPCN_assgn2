"""Merges faculty_to_verify_rest.csv (verify_rest.py) into faculty_to_verify_updated.csv.

Only rows whose `verified` is still blank are touched. yes / no come from the evidence rules;
everything else is written as `unsure` so a person checks it. One safety rule: a person who is
on a faculty page is never turned into `no` by a job title alone (e.g. ORCID title 'PhD'); that
stays `unsure`.
"""
import pandas as pd

SHEET = "faculty_to_verify_updated.csv"
d = pd.read_csv(SHEET, dtype=str, keep_default_na=False)
r = pd.read_csv("faculty_to_verify_rest.csv", dtype=str, keep_default_na=False)
key = ["institution", "name", "department", "reasons"]
pos = {tuple(x): i for i, x in enumerate(d[key].itertuples(index=False)) if d.verified[i] == ""}
n = {"yes": 0, "no": 0, "unsure": 0}
for x in r.itertuples(index=False):
    i = pos[(x.institution, x.name, x.department, x.reasons)]
    v, src, ev = x.auto_verdict, x.auto_source, " ".join(x.auto_evidence.split())
    if v == "no" and d.page_status[i] != "not listed":
        v, src, ev = "unsure", "", "Auto verdict was 'no' from a job title, but the person is on a faculty page: check. " + ev
    if v == "unsure":
        src = "auto: no decisive evidence"
    d.loc[i, ["verified", "notes", "checked_by"]] = [v, ev[:500], src]
    n[v] += 1
d.to_csv(SHEET, index=False)
print(n)
print(d[d.priority == "medium"].verified.value_counts().to_dict())
