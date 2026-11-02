"""Step 5b: keep faculty publications only (current and former faculty, verified list in data/faculty*).

The brief asks for the publications of the FACULTY of each institute. enrich.py keeps every author who lists
one of our institutes (PhD scholars, project staff, visitors, collaborators who print our name). After
faculty_match.py / author_resolution.py know who is faculty, this step narrows the corpus. Everything after it
(networks, citation flow, partners, statistics, dashboard files) is computed on the narrowed corpus.

  group15_data.csv     only rows of faculty authors; one row per faculty member per paper and institute
                       (two OpenAlex records of the same person on one paper are one row)
  papers_enriched.csv  our_institutes limited to the institutes where the paper has a faculty author;
                       papers with none are dropped
  authorships.csv      authors of OUR institutes who are not faculty are removed; faculty and all
                       external co-authors stay (so faculty - outside co-author edges remain)
  authors.csv          faculty author records only

The unfiltered tables are kept in data/out/all_authors/ (written once per run of enrich.py) so the
step can be repeated. To change a faculty decision, edit data/faculty*/ or faculty_overrides.csv and
rerun from `./run_all.sh build`.
"""
import shutil

import pandas as pd

import config

OUT = config.OUT_DIR
ALL = OUT / "all_authors"
FILES = ["group15_data.csv", "papers_enriched.csv", "authorships.csv", "authors.csv"]


def main():
    ALL.mkdir(exist_ok=True)
    cur = pd.read_csv(OUT / "group15_data.csv", usecols=["is_faculty"], dtype=str)
    if (cur.is_faculty != "TRUE").any() or not (ALL / "group15_data.csv").exists():
        for f in FILES:                   # tables as enrich.py / faculty_match.py left them: remember them
            shutil.copy2(OUT / f, ALL / f)
    # else: already narrowed, work from the remembered unfiltered tables
    m = pd.read_csv(ALL / "group15_data.csv", dtype=str, keep_default_na=False)
    fac = m[m.is_faculty == "TRUE"]
    # one row per faculty member, paper and institute
    fac = fac.drop_duplicates(["institution", "openalex_work_id", "faculty_name"])
    pairs = set(zip(fac.openalex_work_id, fac.institution))
    fac.to_csv(OUT / "group15_data.csv", index=False)

    p = pd.read_csv(ALL / "papers_enriched.csv", dtype={"issn": str, "issn_all": str}, keep_default_na=False)
    keep_inst = {}
    for w, i in pairs:
        keep_inst.setdefault(w, []).append(i)
    p = p[p.openalex_work_id.isin(keep_inst)].copy()
    order = {n: k for k, n in enumerate(config.INSTITUTES)}
    p["our_institutes"] = [";".join(sorted(keep_inst[w], key=order.get)) for w in p.openalex_work_id]
    p.to_csv(OUT / "papers_enriched.csv", index=False)

    amap = pd.read_csv(OUT / "author_faculty_map.csv", dtype=str)
    fids = set(zip(amap.institution, amap.author_id))
    a = pd.read_csv(ALL / "authorships.csv", dtype=str, keep_default_na=False)
    a = a[a.openalex_work_id.isin(keep_inst)]
    ours = a.our_inst != ""
    # an authorship of ours stays only if that author record is faculty of one of the institutes on the row
    is_fac = [any((i, aid) in fids for i in o.split(";")) for aid, o in zip(a.author_id, a.our_inst)]
    drop = ours & ~pd.Series(is_fac, index=a.index)
    a = a[~drop]
    a.to_csv(OUT / "authorships.csv", index=False)

    au = pd.read_csv(ALL / "authors.csv", dtype=str)
    au = au[[(i, x) in fids for i, x in zip(au.institution, au.author_id)]]
    au.to_csv(OUT / "authors.csv", index=False)

    print(f"faculty rows: {len(fac)} of {len(m)} | papers: {len(p)} | authorship rows kept {len(a)} (dropped {int(drop.sum())} non-faculty)")
    print(p.assign(n=1).groupby("type").n.sum().to_dict())
    for inst in config.INSTITUTES:
        n_all = m[m.institution == inst].openalex_work_id.nunique()
        n_fac = fac[fac.institution == inst].openalex_work_id.nunique()
        print(f"  {inst}: {n_fac} faculty papers of {n_all} affiliated papers ({n_fac / n_all:.0%})")


if __name__ == "__main__":
    main()
