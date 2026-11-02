# Networks, Indian connections and faculty: what I did

Branch: `networks`, on top of `dpcn first draft`. Last updated 19 Oct 2026 (status block below; the log underneath is kept as written).

> **Status, 19 Oct 2026. Read this first.** This file is the work log of how the networks, partner and faculty steps were built. Its numbers are
> from earlier runs and are **not** the final ones. The final numbers are in `AUDIT_SUMMARY.md` and the two Word reports in `report/`. What changed since this log was written:
> - The corpus is **journal and conference papers only** (books, chapters, editorials, preprint servers and datasets are dropped; conference papers that OpenAlex calls book chapters are kept when Scopus lists them as conference papers).
> - The dataset is **faculty only**: `corpus_filter.py` removes PhD scholars, staff and visitors after the faculty list is matched. Final: 17,906 papers, 22,286 rows, 823 faculty with papers (887 on the list).
> - The faculty list was fully verified by hand and web checks. The verification spreadsheets are gone; the decisions are in `faculty_final.csv` (column `verification`) and `data/faculty_overrides.csv`.
> - Quartiles come from several sources, recorded in `quartile_source` (SCImago, Scopus CiteScore, CORE, and estimates). See `scopus_quartiles.py`.
> - Step order is now: `build enrich quartiles faculty networks outflow inflow partners facstats report`, and `./run_all.sh` starts at `build`.
> - New steps and files: `corpus_filter.py`, `extras.py`, `deep_analysis.py`, `extra_metrics.py`, `audit_summary.py`; dashboards in `dashboard/` and `dashboard_lovable/`.
> - `REPORT.md`, `PROGRESS.md` and `PLAN.md` were removed; the Word reports replace them.

This covers my part of the project: everything except the dashboard. It builds on the dataset already in the repo (`fetch.py` to `networks.py`, `outflow.py`).

---

## 1. Summary

| # | Task | Status | Main output |
|---|------|--------|-------------|
| A1 | Incoming citations (who cites our papers) | ✅ Done | `cited_by_indian_inst` column filled, impact ratio, top 10 citing institutes |
| A2 | Match official faculty lists to OpenAlex authors | ✅ Done | `is_faculty`, `faculty_name`, `department`, `faculty_status` columns; faculty and department stats |
| A2b | Former faculty (people who left 2016–2025) | ✅ Done | Found automatically from old copies of the institute websites |
| A3 | Faculty co-authorship network | ✅ Done | Network on real faculty, Louvain + Leiden, communities vs departments |
| A4 | Indian partner institutes | ✅ Done | Exact partner type (CSIR, DAE, ...), topic similarity, citations both ways |
| – | Verification of uncertain matches | ✅ Done | 90-row medium sample: 44 confirmed, 8 wrong, 38 unverifiable (`faculty_to_verify_updated.csv`) |
| – | Rule fixes from the verification | ✅ Done | Name rules fixed; corrections recorded in `data/faculty_overrides.csv` |
| – | Validation script | ✅ Done | `validate.py`: 51 checks (+ corrections applied), all pass |
| – | One-command rerun | ✅ Done | `run_all.sh` runs everything in the right order, then validates |
| – | Data fixes | ✅ Done | 174 duplicate rows removed, network undercount fixed, 83 partner labels fixed |

All four required submission files exist and pass the checks: `group15_data.csv`, `citation_network.csv`, `authorship_network.csv`, `indian_connections.csv`.

---

## 2. What I did, step by step

### A1. Incoming citations
**Why:** the note asks which Indian institutes cite our work. Before this, only the outgoing side (which institutes we cite) was done, and `cited_by_indian_inst` was empty.

**How:**
- `links.py citing` downloaded every paper that cites one of our papers: 283,379 citing papers for 15,015 of our cited papers.
- New script `inflow.py` counts them. It uses the same rule as `outflow.py`: a citation counts as "from another Indian institute" if the citing paper has an author at an Indian institute other than the cited paper's own institute.

**Results:**

| | MANIT | NIT Jamshedpur | NIT Silchar |
|---|---|---|---|
| Citations found / OpenAlex total | 99.4% | 99.4% | 99.5% |
| Citations from other Indian institutes (in) | 31,097 | 16,699 | 45,898 |
| Citations to other Indian institutes (out) | 41,084 | 29,324 | 59,326 |
| **Impact ratio (in ÷ out)** | **0.76** | **0.57** | **0.77** |
| Papers cited by another Indian institute | 56% | 57% | 64% |
| Citations from the same institute (self) | 7.7% | 10.0% | 15.4% |

- All three cite India more than India cites them (ratio below 1).
- Don't read the yearly ratio as a trend. It rises from about 0.05 (2016) to 0.8-1.1 (2025), but mostly because of how it is counted: citations received in an early year can only go to the few papers published since 2016. Compare only the overall ratio.
- Who cites us is not who we cite. We cite mostly IITs. We are cited mostly by private universities (VIT, Saveetha, LPU, SRM, Chandigarh University), which make up about 75% of incoming Indian citations. IITs are about 8%.
- Saveetha University is a top-2 citer for all three. Saveetha has been reported in the press (e.g. *Science*, 2024) for unusual citation practices. Mention it neutrally if at all.

### A2. Faculty matching (current faculty)
**Why:** the note wants results at faculty and department level. Before this, "core authors" (10+ papers over 3+ years) stood in for faculty. That guess gave NIT Silchar 447 "faculty" against 251 real ones, and there were no departments.

**How:** `faculty_match.py` matches each name on the official lists (`data/faculty/*.csv`) to OpenAlex author IDs:
- A name is only compared with authors who published from the same institute.
- Names are cleaned: case, "Dr."/"Prof.", dots, and joined initials ("RK" becomes "R K").
- The surname must match, and the given names must agree in full or as initials. "Krishna K Dhote" matches "K. K. Dhote" but not "Rahul Dhote".
- One person can have several OpenAlex IDs. All of them are kept and merged.
- Safety rules against wrong matches:
  - **Common names** (e.g. "Deepak Kumar"): if the IDs carry different ORCIDs, only the IDs with the main profile's ORCID are kept.
  - **Initial-only names** (e.g. "S. Suresh"): IDs with a different full first name are dropped ("Saumya Suresh" is removed).
  - **Reversed names** ("Kumar Satish" = "Satish Kumar"): only allowed with full names, not initials.
  - **Same name, different people on the list** (two "Deepak Kumar"s at MANIT, in Mechanical and Humanities): left unmatched. This affects 9 people.
  - **Same person listed twice**: MANIT lists its Mathematics faculty again under Bioinformatics / Computer Applications. These are merged into one person.

**Accuracy:** I checked 50 random matches by hand (`faculty_match_audit_checked.csv`): 45 correct, 2 wrong (the rule that caused them was then fixed), 3 unsure. That is **about 90% precision**.

### A2b. Former faculty
**Why:** today's faculty lists miss people who left during 2016–2025. Their papers were counted as "not faculty".

**How:** `scrape_former_faculty.py`, fully automatic, no manual checking.
- **Source:** old copies of the institutes' own faculty pages from the Internet Archive (Wayback Machine). That is 276 page copies:

  | Institute | Pages used | Years |
  |---|---|---|
  | MANIT | Department pages | 2017–2025 |
  | NIT Jamshedpur | Old per-department faculty lists | 2016–2022, plus 2024 |
  | NIT Silchar | Department pages | 2016–2024, plus the 2025 list |

- **Faculty only:** a name counts only when a designation ("Professor", "Lecturer", "Faculty", "Head") follows it, and not when "Scholar", "PhD" or "Student" does. This keeps out PhD scholars and staff, who are also listed on these pages.
- **Name cleaning:** page text sometimes sticks to a name ("Manish Pandey Soft Computing"), so names are compared through their shorter forms:
  - If a shorter form matches today's list, the person is current.
  - Otherwise the person is former, kept under the name form that matches an author who published from that institute.
- Former faculty then go through the same matching as current faculty. They are marked `faculty_status = former`, with `first_seen` and `last_seen` years.
- **Automatic check:** if the matches are right, former faculty's papers should mostly date from their years on the faculty pages. **85% of their papers fall within those years (±2)**, and 110 of 129 people fit. That is good evidence the matches are right.

**Results:**

| | MANIT | NIT Jamshedpur | NIT Silchar |
|---|---|---|---|
| Former faculty with papers in our data | 18 | 70 (many ad-hoc/temporary) | 50 |
| Papers with a faculty author (current + former) | 77% | **79%** | 90% |

- NIT Jamshedpur has the highest turnover, which fits its many ad-hoc posts.
- **K. Sudhakar (update, Oct 2026):** he is not on the scraped MANIT faculty pages 2017–2025, but he **holds a permanent position at MANIT** (Energy Centre) and is currently Associate Professor at Universiti Malaysia Pahang (confirmed by the team). He is kept as MANIT faculty under Energy Science and Engineering (`fix_departments.py`). His UMP work explains why UMP is MANIT's largest foreign partner.

### Faculty statistics (current + former)
`faculty_stats.py`:

| | MANIT | NIT Jamshedpur | NIT Silchar |
|---|---|---|---|
| Faculty matched: current + former | 271 + 18 | 171 + 68 | 235 + 48 |
| Current faculty not found in OpenAlex | 51 | 16 | 16 |
| Median h-index (2016–26, current faculty) | 5 | 5 | 7 |
| Faculty with h-index ≥ 20 | 9 | 3 | 35 |

- The real median h-index is lower than the old "core author" figure (7), because the core-author rule only picked prolific people.
- Department highlights (`department_stats.csv`):
  - NIT Silchar Chemistry: about 70 papers per faculty member, over 50% of journal papers in Q1.
  - MANIT Energy Science: 62% Q1.
  - NIT Jamshedpur Physics and ECE have the lowest Q1 shares.

### A3. Faculty co-authorship network
**Why:**
- In the old network, one person split across several OpenAlex IDs counted as several nodes.
- The old network used guessed "core authors".
- It only used Louvain.

**How:** `faculty_network.py`. Nodes are faculty members (current + former, all their IDs merged) and carry a department and a status. An edge means the two co-authored at least one paper; its weight is the number of joint papers. Papers with more than 30 authors are left out, as in `networks.py`.

**Results:**
- 811 faculty, 1,147 links, average 2.8 collaborators. 164 faculty (20%) have no faculty co-author.
- Only **20 links between our three institutes**: they hardly collaborate.
- 25% of links cross departments.
- Louvain and Leiden agree: 39 vs 38 communities, modularity 0.871 vs 0.869, and no broken Louvain communities.
- **Do research groups follow departments?** We measure this with NMI (0 = unrelated, 1 = identical):
  - MANIT 0.63
  - NIT Silchar 0.62
  - NIT Jamshedpur **0.54**, the most interdisciplinary. Its largest group spans CSE, ECE and Mechanical.
- Brokers (highest betweenness):

  | Institute | Brokers |
  |---|---|
  | MANIT | Vijay Bhaskar Semwal, Rajesh Purohit, Suresh Kumar Gawre |
  | NIT Jamshedpur | Akhilesh Kumar, Kunal Singh, Satish Kumar |
  | NIT Silchar | Ashish B. Deoghare, Krishna Murari Pandey, Kavicharan Mummaneni |

### A4. Indian partner institutes
**Why:** the note asks to flag cross-cluster links (e.g. NIT ↔ CSIR) and to compute Jaccard similarity of research topics with partners.

**How:** `partners.py`
- **Partner type:** the old rule guessed from the name and missed labs like National Metallurgical Laboratory (a CSIR lab). The type now comes from each institute's parent organisation in OpenAlex: CSIR, DAE, DRDO, ICAR, ICMR or ISRO. 83 partner labels changed.
- **Topic similarity:** for our 3 institutes and the top 25 partners of each, OpenAlex gives paper counts per subfield (about 250 subfields). We report two measures:
  - **Jaccard:** overlap of subfields with at least 1% share.
  - **Weighted Jaccard:** overlap of the subfield shares.
- **Citations per partner:** `cites_from_partner` (they cite us) and `cites_to_partner` (we cite them).

**Results:**
- NIT Jamshedpur has 172 joint papers with CSIR labs. National Metallurgical Laboratory is its #1 partner.
- Topic similarity does not predict collaboration (Spearman about 0, not significant). Partners are mostly regional: NIT Silchar's top partners Mizoram University and Assam University have quite different research profiles (similarity about 0.2).
- We cite IITs 3–4 times more than they cite us (e.g. MANIT → IIT Roorkee 2,758; IIT Roorkee → MANIT 574).

### Validation and fixes
`validate.py` runs 51 checks:
- **Structure:** required columns, years 2016–2026, all institutes present, no duplicates.
- **Consistency:** `cited_by_indian_inst` is recomputed from the raw download with separate code, with 0 differences. Totals agree across files.
- **Maths:** h-index, NMI, ARI and Jaccard give the known answers on test cases.
- **Faculty:** each author ID belongs to at most one person, and the faculty table is recounted. Former faculty pass the years check.
- **Live OpenAlex re-checks** (`--live`):
  - 12/12 papers have the correct citation flag.
  - Faculty paper counts match (e.g. 276 vs 276, 14 vs 14).
  - 4/4 CSIR labels are correct.

Fixes made along the way:
1. **Duplicate rows:** 174 rows were the same author listed twice on one paper by OpenAlex. They are removed from `group15_data.csv`, and `enrich.py` now drops them.
2. **Network undercount:** the faculty network missed collaborations of authors that `enrich.py` matched by name. It is now built from `group15_data.csv`, like the faculty stats.
3. **Partner labels:** 83 partner labs were mislabelled. Fixed as described in A4.
4. **`plots.py` seemed to hang:** it opens a chart window and waits for it to be closed. `run_all.sh` runs it with `--no-show`.
5. **Reruns gave slightly different files** (row order of ties, set by Python's random hash order). `run_all.sh` fixes the order (`PYTHONHASHSEED=0`), so reruns are identical.
6. **The archive scraper treated a failed lookup as "no copies".** That would silently drop a department's former faculty. It now stops with an error instead, and resumes from its cache.

### Verification of uncertain matches and rule fixes
**Checking:** the 90-row medium sample of `faculty_to_verify.csv` (the guide from our teammate):
- 33 rows were settled automatically from ORCID records and the faculty pages (`verify_auto.py`, `verify_pages.py`).
- 57 were checked by hand on Google Scholar.
- Result: 44 confirmed, 8 wrong, 38 not verifiable.
- (Historical) Everything was in `faculty_to_verify_updated.csv` (661 rows); that sheet has since been replaced by `faculty_final.csv`.

**Rule errors found and fixed** (in `faculty_match.py` and `scrape_former_faculty.py`; they apply to all rows, checked or not):

| Rule error | Example | Fix |
|---|---|---|
| Surname written as an initial not recognised | "Prashanth J" = Prashanth Janardhan | Matches when the given names agree in full |
| Spelling variants not recognised | Mansi/Manasi, Agrawal/Agarwal, Behari/Bihari | One vowel more or less counts as the same name ("Manish" ≠ "Manisha") |
| A shorter name matched a longer one | "Ashok Kumar" took "Ashok Kumar Mehta" | A shorter form only when the cut-off part is junk ("Designation-", "AD-HOC", "Temporary") |
| Different ORCIDs always meant different people | Awdhesh K Choudhary lost a record | Only for names common in our data (4+ author records) or initial-only names |
| Same-name colleagues dropped entirely; capitalisation not normalised | "Dinesh Kumar" vs "DINESH KUMAR" | Normalised names. Each same-name colleague kept as "Name (Department)", with records only from checked evidence |
| No place for checked corrections | Ruchi Khare's biology papers, Munendra Singh's geologist record | `data/faculty_overrides.csv`: 29 corrections (assign / unassign / per paper), each with its evidence. `validate.py` checks they are all applied |

**Effect:**
- 1,150 → 1,326 author records matched.
- Former-faculty lists corrected:
  - 6 removed: spelling variants of current faculty, and one created by the old bug.
  - 11 added: people the old rule had folded into current faculty.
- A duplicate person fixed: Dheeraj Agrawal (former) = Dheeraj K. Agarwal (current HOD, ECE).

---

## 3. Files

### New scripts
| Script | What it does |
|---|---|
| `inflow.py` | Incoming citations, `cited_by_indian_inst`, impact ratio, year-wise flow |
| `faculty_match.py` | Faculty lists (current + former) → OpenAlex IDs; adds `is_faculty`, `faculty_name`, `department`, `faculty_status` |
| `scrape_former_faculty.py` | Former faculty from archived institute pages → `data/faculty_former/*.csv` |
| `faculty_stats.py` | Faculty performance table, department table, h-index distribution |
| `faculty_network.py` | Faculty co-authorship network and its analysis |
| `partners.py` | Partner type, topic similarity, citations per partner |
| `validate.py` | All checks (`--live` adds OpenAlex spot checks); also checks every correction is applied |
| `verify_auto.py`, `verify_pages.py` | Evidence for uncertain matches from ORCID, OpenAlex and the faculty pages |
| `merge_verification.py` | Builds `faculty_to_verify_updated.csv` from the automatic and manual checks |
| `data/faculty_overrides.csv` | Corrections found by checking, each with its evidence (read by `faculty_match.py`) |
| `run_all.sh` | Runs the pipeline in the right order, then `validate.py` |

Changed: `enrich.py` (one line, drops duplicate author rows).

### New outputs
| File | Use |
|---|---|
| `data/out/group15_data.csv` | Main file. `cited_by_indian_inst` is now filled; new columns `is_faculty`, `faculty_name`, `department`, `faculty_status` |
| `data/faculty_former/*.csv` | Former faculty: name, department, years seen on the institute pages |
| `data/out/incoming_citations_by_institute.csv` | Every Indian institute citing us, with counts |
| `data/out/incoming_citations_by_year.csv` | Yearly incoming citations |
| `data/out/citation_flow_by_year.csv` | **Dashboard:** in-flow vs out-flow chart (`your_inst, year, in_cites, out_cites`) |
| `data/out/faculty_matched.csv` | Every listed faculty member: status, IDs, papers, h-index |
| `data/out/author_faculty_map.csv` | OpenAlex author ID → faculty member, department, status |
| `data/out/faculty_match_audit_checked.csv` | The 50 hand-checked matches |
| `data/out/faculty_match_rejected.csv` | IDs rejected by the safety rules, with the reason |
| `data/out/stats/faculty_performance.csv` | **Dashboard:** sortable faculty table (papers, citations, h-index, top journal, Q1 share, current/former) |
| `data/out/stats/department_stats.csv` | **Dashboard / report:** one row per department |
| `data/out/faculty_network_nodes.csv` | **Dashboard:** network nodes (department, status, collaborators, betweenness, community) |
| `data/out/faculty_network_edges.csv` | **Dashboard:** network edges (who with whom, joint papers, years) |
| `data/out/indian_connections_detailed.csv` | Partner type, citations both ways, Jaccard |
| `data/out/stats/*.json` | All the numbers above (`inflow_results`, `faculty_results`, `faculty_network_results`, `partner_results`) |

---

## 4. How to run

Setup, once per machine:
```bash
python3 -m venv .venv
.venv/bin/pip install pandas requests networkx python-louvain igraph leidenalg rapidfuzz matplotlib scipy powerlaw
echo "YOUR_OPENALEX_KEY" > .openalex_key     # free key from openalex.org, git-ignored
```

Rerun everything with one command:
```bash
./run_all.sh              # rerun our part: inflow -> faculty -> partners -> report charts, then checks
./run_all.sh enrich       # start at a given step and run everything after it
./run_all.sh --list       # show the steps
```

Why use it rather than running scripts by hand:
- **The order matters.** Several scripts write `group15_data.csv` in turn, and `enrich.py` rebuilds it and empties the citation columns. `networks.py` also rewrites `indian_connections_detailed.csv`, so `partners.py` must run after it.
- **It checks inputs before changing anything.** If an input is missing (e.g. the raw downloads in `data/raw/`), it stops without touching any file and says how to get it.
- **It always ends with `validate.py`.**

Full order: `fetch → build_tables → enrich → networks → outflow → inflow → faculty (match, stats, network) → partners → report (stats.py, plots.py) → validate`

Check only:
```bash
.venv/bin/python validate.py          # about 1 minute, local checks
.venv/bin/python validate.py --live   # also asks OpenAlex for spot checks
```

Notes:
- **`data/raw/` (the OpenAlex and archive downloads) is git-ignored.** The outputs in `data/out/` are in git, so the dashboard does not need it.
- **Rerunning from `inflow` needs `data/raw/links/citing.jsonl`.** Get it with `links.py citing` (about 1 hour), or copy it from me.
- **Rerunning from `enrich` or `outflow` needs `data/raw/links/referenced.jsonl`.** That is the outgoing-citation download, which I do not have; whoever ran `outflow.py` has it. `run_all.sh` refuses to start without it, because `enrich.py` would empty `cites_indian_inst` with no way to refill it.
- **`scrape_former_faculty.py` takes about 30 minutes the first time** (276 archived pages). After that it uses the cached copies in `data/raw/wayback/`.

---

## 5. What is left

### For the team
- [ ] **Merge `networks` into `main`.** `group15_data.csv` changed on both sides, so after merging, run `./run_all.sh` rather than merging that file by hand.
- [ ] **Dashboard:** use the files marked "Dashboard" above. Agree the format with the dashboard teammate.
  - The network may need trimming to the top ~300 nodes for the browser; the node file has betweenness and degree to sort by.
  - Use `faculty_status` to show current faculty only, or everyone.
- [x] (Historical) `REPORT.md` was updated at the time; it has since been replaced by the Word reports.
- [ ] **High-priority verification rows:** Tejasvini is checking them. Add confirmed corrections to `data/faculty_overrides.csv` (one row each, with evidence), then run `./run_all.sh faculty`.
- [ ] **Cut the report to 10 slides or 5 pages.**
- [ ] **Say in the report how the networks treat large papers.** `authorship_network.csv` still contains pairs from papers with 100+ authors. They are kept in the raw file, and the analysis excludes papers with more than 30 authors.

### Optional extras (to impress)
- [ ] Degree distribution: power law or not, compared with a random network.
- [ ] Network growth year by year, and whether well-connected faculty gain collaborators faster.
- [ ] Robustness: remove the top brokers and watch the network split.
- [ ] Predict 2023–26 collaborations from 2016–22 data.
- [ ] Self-citation and "elite core" (k-core / rich-club) analysis.
- [ ] Faculty mobility: former faculty who moved between our three institutes.

### Known limitations (for the report)
- **Quartiles** are approximate: recomputed from SJR values, because SCImago's site was blocked.
- **Coverage:** OpenAlex holds about two-thirds of the journal papers the institutes report themselves. Not checked against Scopus or Web of Science (no access).
- **Faculty matching** is about 90% precise (50-match audit; 90-row verification sample: 44 confirmed, 8 wrong and corrected, 38 unverifiable). 83 current faculty (11%) were not found, mostly in Architecture or recent joiners. 4 same-name faculty could not be told apart and are left out.
- **Former faculty depend on what the Internet Archive saved.** Gaps:
  - NIT Jamshedpur has no copies for 2023.
  - MANIT has none of its Humanities page.
  - NIT Silchar's CSE page has only 5 copies.

  People who joined and left between two saved copies are missed.
- **Affiliation-based counting credits external collaborators.** Authors who list an institute as an affiliation without being its faculty count for the institute, but not as faculty papers. Faculty on leave or deputation (e.g. K. Sudhakar at UMP) can be missing from the institute's web pages and need a manual check.
- **2026 is a partial year**, and recent papers have had little time to be cited.
