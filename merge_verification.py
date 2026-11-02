"""Merges the medium-priority checks into one sheet: faculty_to_verify_updated.csv.

  faculty_to_verify.csv        original 661 rows (not changed)
  scholar_check_list.csv       57 rows checked by hand on Google Scholar
  faculty_to_verify_auto.csv   33 rows settled automatically (ORCID / faculty page)

Adds checked_by: 'manual: Google Scholar', 'auto: ORCID', 'auto: ORCID (name search)',
'auto: faculty page + topics' or 'not checked'.
Rules agreed while checking:
  - 'unsure' with the note 'PHD' = confirmed PhD scholar on Google Scholar -> 'no'
  - 'unsure' with no note = the Google Scholar search found no profile
"""
import pandas as pd

KEY = ["institution", "name", "department", "reasons"]

# notes agreed while checking that did not make it into the sheet (or were pasted wrongly)
NOTES = {
    ("NIT Silchar", "Prashanth Janardhan"): "Scholar: Assistant Professor, Civil Engg, NIT Silchar, verified civil.nits.ac.in. On current faculty list as 'Prashanth J' (initial for Janardhan); script missed the match.",
    ("NIT Silchar", "S. Dey"): "This 'S. Dey' record is Sudip Dey (NITS Mechanical): same topics (stochastic analysis, composites/FGM, graphene), same co-author R. R. Kumar, matches his Scholar profile (verified mech.nits.ac.in). Split record; merge with his main record A5101642629.",
    ("MANIT Bhopal", "Kamal Singh"): "MANIT Civil faculty page: Dr. Kamal Singh, Associate Professor, Transportation & Geotechnical Engg, singhk@manit.ac.in. Scholar profile (verified manit.ac.in) matches; our 5 MANIT papers are his. OpenAlex record also has a paleobotanist's non-MANIT papers (not in our data).",
    ("NIT Jamshedpur", "Ashok Kumar"): "No Scholar profile for the Civil Ashok Kumar. Nearly all NITJ 'Ashok Kumar' records are metallurgy (fatigue, creep, cold rolling) and belong to the Metallurgy professor (Scholar: NITJ, fatigue/fracture): A5016490586, A5101510323, A5100702973, NAME:ashok kumar, likely A5024966118. Only 'Ternary blended concrete...' (in A5122705785) fits Civil. A5100649127 (Tata Steel) and A5016204865 (Chitkara) are neither.",
    ("NIT Jamshedpur", "Kapil Dev Mahato"): "Scholar: Dept of Physics, NIT Jamshedpur, verified nitjsr.ac.in, no job title. All papers (2022-24) with Uday Kumar (Asst Prof, his co-author). Not on faculty pages. Likely PhD scholar of Dr Uday Kumar.",
}


def clean(s):
    return " ".join(str(s).replace("\\n", " ").replace("\n", " ").strip().strip('"').split())


def auto_source(ev):
    if "found by name+institute search" in ev:
        return "auto: ORCID (name search)"
    if "shared keywords" in ev and "ORCID job here" not in ev:
        return "auto: faculty page + topics"
    return "auto: ORCID"


def main():
    d = pd.read_csv("faculty_to_verify.csv", dtype=str).fillna("")
    d["checked_by"] = "not checked"
    keys = [tuple(r) for r in d[KEY].itertuples(index=False)]
    pos = {k: i for i, k in enumerate(keys)}

    # automatic verdicts (sampled rows the scripts settled)
    a = pd.read_csv("faculty_to_verify_auto.csv", dtype=str).fillna("")
    auto = a[(a.sampled == "yes") & (a.auto_verdict.isin(["yes", "no"]))]
    for r in auto.itertuples(index=False):
        i = pos[(r.institution, r.name, r.department, r.reasons)]
        src, ev = auto_source(r.auto_evidence), clean(r.auto_evidence)
        if src == "auto: faculty page + topics":       # lead with the evidence that decided it
            ev = ev[ev.find("faculty page:"):]
        elif src == "auto: ORCID (name search)":      # the ORCID job title decided it
            parts = [p.strip() for p in ev.split("|")]
            ev = " | ".join([p for p in parts if "name+institute search" in p] +
                            [p for p in parts if "name+institute search" not in p])
        ev = ev.replace("| no ORCID |", "| (no ORCID linked to the OpenAlex record) |")
        d.loc[i, ["verified", "notes", "checked_by"]] = [r.auto_verdict, ev[:500], src]

    # answers checked by hand on Google Scholar
    c = pd.read_csv("scholar_check_list.csv", dtype=str).fillna("")
    for r in c.itertuples(index=False):
        i = pos[(r.institution, r.name, r.department, r.reasons)]
        v, n = r.verified.strip().lower(), clean(r.notes)
        if n.upper() in ("PHD", "PH.D", "PH D"):
            v, n = "no", "PhD scholar, confirmed on Google Scholar."
        if (r.institution, r.name) in NOTES:
            n = NOTES[(r.institution, r.name)]
        if not n:
            n = "No Google Scholar profile found." if v == "unsure" else "Confirmed on Google Scholar."
        d.loc[i, ["verified", "notes", "checked_by"]] = [v, n, "manual: Google Scholar"]

    d.to_csv("faculty_to_verify_updated.csv", index=False)
    done = d[d.checked_by != "not checked"]
    print(f"faculty_to_verify_updated.csv: {len(d)} rows, {len(done)} checked")
    print(done.groupby(["checked_by", "verified"]).size().unstack(fill_value=0).to_string())
    print("\nby priority:", d.groupby(["priority", d.checked_by != "not checked"]).size().unstack(fill_value=0)
          .rename(columns={True: "checked", False: "not checked"}).to_dict("index"))


if __name__ == "__main__":
    main()
