"""Faculty who appear at two of our institutes under the same OpenAlex author id (they moved, or are on lien).

aliases() maps the secondary (institution, name) record to the canonical one so analyses count each person once:
the canonical record is the 'current' one; if both are current (lien), the alphabetically first institution is used.
"""
import pandas as pd

import config


def aliases():
    ff = pd.read_csv(config.DATA_DIR / "faculty_final.csv" if hasattr(config, "DATA_DIR") else config.OUT_DIR.parent / "faculty_final.csv")
    byid = {}
    for r in ff.itertuples():
        for a in str(r.openalex_author_ids).split(";"):
            if a.startswith("A"):
                byid.setdefault(a, {})[r.institution] = r
    out = {}
    for rows in byid.values():
        if len(rows) < 2:
            continue
        rs = sorted(rows.values(), key=lambda r: (r.faculty_status != "current", r.institution))
        canon = (rs[0].institution, rs[0].name)
        for r in rs[1:]:
            out[(r.institution, r.name)] = canon
    return out
