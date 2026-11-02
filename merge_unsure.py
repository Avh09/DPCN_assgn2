"""Copies the team's manual answers from faculty_to_verify_unsure.csv (column `verify`) into
faculty_to_verify_updated.csv, and adds the Scopus evidence columns (faculty_to_verify_scopus.csv).

An answer is applied to the row with the same (institution, name, department, reasons). verified becomes the
team's yes / no, the team note (your_notes) is appended to notes, checked_by = 'manual: team check'.
"""
import pandas as pd

d = pd.read_csv("faculty_to_verify_updated.csv", dtype=str, keep_default_na=False)
u = pd.read_csv("faculty_to_verify_unsure.csv", dtype=str, keep_default_na=False)
sc = pd.read_csv("faculty_to_verify_scopus.csv", dtype=str, keep_default_na=False)
key = ["institution", "name", "department", "reasons"]
pos = {tuple(x): i for i, x in enumerate(d[key].itertuples(index=False))}
n, miss = 0, []
for r in u[u.verify.isin(["yes", "no"])].itertuples(index=False):
    i = pos.get((r.institution, r.name, r.department, r.reasons))
    if i is None:
        miss.append((r.institution, r.name)); continue
    note = f"Team manual check: {r.verify}" + (f" ({r.your_notes})" if r.your_notes else "")
    d.loc[i, "verified"] = r.verify
    d.loc[i, "notes"] = (d.notes[i] + " | " if d.notes[i] else "") + note
    d.loc[i, "checked_by"] = "manual: team check"
    n += 1
d = d.drop(columns=[c for c in ("scopus_hint", "scopus_evidence") if c in d.columns])
d = d.merge(sc.drop_duplicates(key)[key + ["scopus_hint", "scopus_evidence"]], on=key, how="left").fillna("")
d.to_csv("faculty_to_verify_updated.csv", index=False)
print("applied:", n, "| not found:", miss)
print(d.verified.replace("", "BLANK").value_counts().to_dict())
print("scopus columns filled for", (d.scopus_hint != "").sum(), "rows")
