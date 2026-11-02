"""Turns scholar_check_list.csv into scholar_check_list.xlsx: the name links to the Google Scholar
search, the OpenAlex and ORCID cells are links, 'verified' has a yes/no/unsure dropdown.
Answers already in the CSV are kept; ANSWERS fills rows decided while checking together.
Read it back with: pd.read_excel("scholar_check_list.xlsx")
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ANSWERS = {   # (institution, name): (verified, notes), decided row by row with the evidence shown
    ("MANIT Bhopal", "Ruchi Khare"): ("no", "OpenAlex record mixes two Ruchi Khares at MANIT. Most papers (hydrology, hydraulics, turbomachines) are the Civil Engg professor's. About 6 biology papers (oral cancer, SARS-CoV-2 inhibitors, silver nanoparticles, drug repurposing) belong to Ruchi Khare, Dept of Biological Science & Engg, MANIT (Scholar profile, verified email manit.ac.in)."),
    ("MANIT Bhopal", "Afzal Hussain"): ("unsure", "No Scholar profile (searched with MANIT and with bioinformatics) and no ORCID. Papers list Dept of Bioinformatics MANIT 2020-26 + Rajasthan Technical University; on no MANIT faculty page. Likely scholar, not confirmed."),
    ("MANIT Bhopal", "Ashish Kumar"): ("unsure", "None of the 3 Scholar profiles fits (Economics; CSE Ashish Kumar Sahu; image-processing scholar). Papers are Mechanical (aluminium alloys, welding), 2019-25, almost all with Prof. Rajesh Purohit (14) and Prof. R. S. Rana (13); on no MANIT Mechanical faculty page 2017-26. Likely their PhD scholar, not confirmed."),
    ("MANIT Bhopal", "Dhananjay Kumar"): ("unsure", "No Scholar profile, no ORCID. 19 MANIT papers 2017-25 in power electronics, mostly with Prof. Rajesh Kumar Nema (7) and Prof. Savita Nema (4); on no MANIT Electrical faculty page 2017-26. Likely their PhD scholar, not confirmed. OpenAlex record also has unrelated Lulea 1992-95 papers (mixed record)."),
    ("NIT Jamshedpur", "Kapil Dev Mahato"): ("unsure", "Scholar: Dept of Physics, NIT Jamshedpur, verified nitjsr.ac.in, no job title. All papers (2022-24) with Uday Kumar (Asst Prof, his co-author). Not on faculty pages. Likely PhD scholar of Dr Uday Kumar."),
    ("NIT Jamshedpur", "Tapan Kumar Sankar"): ("no", "Scholar: PhD at NIT Jamshedpur, now Assistant Professor at G H Raisoni University Amravati. Papers with Prof. Balram Ambade (supervisor). Former PhD scholar, not NITJ faculty."),
    ("NIT Silchar", "Anmol Singh"): ("unsure", "Scholar: NIT Silchar, verified che.nits.ac.in, no job title. Papers almost all with Prof. Pranjit Barman (NITS Chemistry). Not on any faculty list. Likely PhD scholar of Prof. Barman."),
    ("NIT Silchar", "Juri Kalita"): ("unsure", "Scholar: Dr., NIT Silchar, verified che.nits.ac.in, no job title. Papers mostly with Prof. Siddhartha S. Dhar (NITS Chemistry); lab co-authors now postdocs elsewhere. Not on faculty pages. Likely former PhD scholar of Prof. Dhar."),
}

c = pd.read_csv("scholar_check_list.csv", dtype=str).fillna("")
for (inst, name), (v, n) in ANSWERS.items():
    k = (c.institution == inst) & (c.name == name)
    c.loc[k & (c.verified == ""), "verified"] = v
    c.loc[k & (c.notes == ""), "notes"] = n

wb = Workbook()
ws = wb.active
ws.title = "check"
cols = list(c.columns)
ws.append(cols)
link = Font(color="0563C1", underline="single")
for r, row in enumerate(c.itertuples(index=False), start=2):
    for j, col in enumerate(cols, start=1):
        val = getattr(row, col)
        cell = ws.cell(row=r, column=j, value=val)
        cell.alignment = Alignment(wrap_text=col in ("notes", "page_research", "openalex_topics", "auto_evidence"),
                                   vertical="top")
        if col == "name" and row.google_scholar:
            cell.hyperlink, cell.font = row.google_scholar, link
        elif col in ("openalex", "orcid", "google_scholar") and val.startswith("http"):
            cell.hyperlink, cell.font = val, link
for cell in ws[1]:
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor="DDEBF7")
widths = {"name": 26, "google_scholar": 12, "verified": 10, "notes": 60, "institution": 15, "department": 24,
          "reasons": 18, "page_research": 40, "openalex_topics": 40, "papers": 7, "page_email": 24,
          "openalex": 14, "orcid": 14, "auto_evidence": 80}
for j, col in enumerate(cols, start=1):
    ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = widths.get(col, 15)
dv = DataValidation(type="list", formula1='"yes,no,unsure"', allow_blank=True)
ws.add_data_validation(dv)
vcol = ws.cell(row=1, column=cols.index("verified") + 1).column_letter
dv.add(f"{vcol}2:{vcol}{len(c) + 1}")
ws.freeze_panes = "B2"
wb.save("scholar_check_list.xlsx")
print(f"scholar_check_list.xlsx: {len(c)} rows, {int((c.verified != '').sum())} already answered")
