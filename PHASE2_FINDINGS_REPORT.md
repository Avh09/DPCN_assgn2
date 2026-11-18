# Key Observations: MANIT Bhopal, NIT Jamshedpur and NIT Silchar

**DPCN Group 15** · Verified faculty, 2016–2026 (OpenAlex; 2026 partial) · 17,687 papers by 807 research-active faculty. All figures come from the project's final tables [1]; the 33 retracted or withdrawn papers are excluded [2].

## 1. Basic Statistics

| Measure | MANIT | NIT Jamshedpur | NIT Silchar |
|---|---|---|---|
| Papers (journal / conference) | 5,746 (3,580 / 2,166) | 3,587 (2,393 / 1,194) | **8,398** (5,454 / 2,944) |
| Papers per research-active faculty | 19.4 | 15.3 | **30.4** |
| Citations / per paper | 90,499 / **15.8** | 43,995 / 12.3 | **124,608** / 14.8 |
| Institute h-index | **118** | 84 | 112 |
| Median field-weighted impact (FWCI) | 0.73 | 0.67 | **0.82** |
| Journal Q1 share | 33.2% | 26.2% | **36.8%** |
| Q1 and IF > 5 (papers) | 636 | 288 | **971** |
| Q1 and IF > 10 (papers) | 73 | 18 | **141** |
| Papers with > 10 authors | 0.4% | 0.3% | 0.3% |
| Growth, 2016–20 to 2021–25 | +102% | **+174%** | +102% |

**Key observations**

- **No single leader.** NIT Silchar leads on volume, output per faculty and Q1 share; MANIT on citations per paper and h-index; NIT Jamshedpur on growth.
- **MANIT's h-index lead is not a size effect.** With an equal number of papers drawn from each institute, MANIT still ranks first (≈ 100 vs 87).
- **High-impact work is rare and concentrated.** Only 0.8–2.6% of journal papers are Q1 with IF > 10. The top 10% of faculty hold 30–39% of each institute's citations.
- **A few highly cited papers raise the averages.** Mean FWCI (1.7–2.0) is more than twice the median (0.67–0.82), so typical papers are cited below the world average for their field.
- **Large-team papers do not drive the results.** Removing papers with more than 10 authors changes citations per paper by at most 0.14 and the Q1 share by at most 0.3 points.
- **Each institute's top 30 papers are mostly Q1** (73–80%), with median citations of 367 (MANIT), 273 (NITS) and 204 (NITJ).

*Dashboard: Overview, Publications, Faculty and Papers tabs.*

## 2. Network Analysis

| Co-authorship network [1] | All | MANIT | NITJ | NITS |
|---|---|---|---|---|
| Faculty / links | 800 / 1,201 | 296 / 481 | 230 / 236 | 274 / 451 |
| Largest connected group | 76% | 79% | 61% | 82% |
| Communities / modularity | 36 / 0.87 | 16 / 0.75 | 19 / 0.71 | 10 / 0.74 |
| Removed before network breaks: random / most central | 24% / **4%** | 26% / 10% | 14% / **4%** | 30% / 12% |

- **Collaboration stays inside each institute.** Only 33 of 1,201 links join two of the three NITs, and communities largely follow departments (NMI 0.58–0.70).
- **The networks depend on a few brokers.** Removing the 4% most central faculty breaks the network apart, while random removal needs 24%. NIT Jamshedpur is the most fragile. *(Resilience tab)*
- **Better-connected faculty have higher impact** (number of collaborators vs FWCI, Spearman 0.32), but this falls to 0.08 once the number of papers is controlled for, so it largely reflects productivity.
- **Future collaborations can be predicted.** A model trained on collaborations up to 2019 (outcomes 2020–22) and tested on new outcomes in 2023–25 reaches ROC-AUC **0.95** for new collaborations (average precision 32× the base rate) and 0.56 average precision for repeat collaborations (base rate 0.33). Scores rank candidates rather than give probabilities, and each suggestion comes with its reasons. *(Potential tab)*
- **Within-corpus citations are mostly self-citations** (88%). In-corpus PageRank therefore reflects self-citation rather than influence. *(Citations tab)*
- **All three institutes cite other Indian institutes more than they are cited back** (received ÷ given: MANIT 0.79, NITJ 0.61, NITS 0.81). The institutions they cite most are IITs, while those that cite them most are private universities (VIT, Saveetha, LPU, SRM). *(Flows tab)*

## 3. Regional and International Collaboration (new)

- **Most collaboration is with other regions:** 63% (MANIT), 56% (NITJ) and 72% (NITS) of their links with Indian partner institutions [3].
- **Yet each institute prefers its own region**, 2.2–10.7× more than the baseline set by the other two institutes, and the preference is fading: NIT Silchar's own-region share fell from 35% to 17% of links with a known region between 2016–18 and 2022–25 [3].
- **Nearby institutions drive it:** CSIR-NML in Jamshedpur, IIT Guwahati in the North-East, and IIIT Bhopal on MANIT's campus [6].
- **The three NITs barely collaborate with each other:** 44 joint papers in total.
- **This matches the literature:** distance reduces collaboration [7], and in India institutional strength outweighs distance [8]. We found no earlier state-level study for India.
- **International links rest on individual professors.** International papers make up 10.5% (MANIT), 14.0% (NITJ) and 14.2% (NITS) of output, and each institute's largest foreign partners come almost entirely from one person [1]:

| Top foreign partner | Joint papers | By one professor |
|---|---|---|
| Universiti Malaysia Pahang (MANIT) | 132 | 131, K. Sudhakar |
| King Saud University, Saudi Arabia (NITJ) | 53 | 35, Sunil Kumar |
| Ajman University, UAE (NITJ) | 43 | 43, Sunil Kumar |
| Zhejiang University, China (NITS) | 69 | 68, Ashish Paramane |
| New Jersey Institute of Technology, US (NITS) | 46 | 46, Trupti Ranjan Lenka |

- **Malaysia is MANIT's top partner country only because of Prof. Sudhakar.** 131 of MANIT's 147 Malaysian papers are his and list both of his own affiliations, so they reflect one person's dual affiliation rather than collaboration between the two institutions. Without him, Malaysia accounts for only 16 MANIT papers.

*Dashboard: Reach tab, AI Research Assistant.*

## 4. Data Quality Follow-up

- **Retracted papers.** All 33 were verified against Crossref, Retraction Watch and the publishers' notices [4], and are excluded from every metric [2]. Institute h-indexes are unchanged. *(Overview and Methodology tabs)*

| Reason for retraction [4] | MANIT | NITJ | NITS | Total |
|---|---|---|---|---|
| Compromised peer review or editorial misconduct | 6 | 2 | 6 | 14 |
| Garbled wording, generated text or image problems | 2 | 3 | 5 | 10 |
| Plagiarism, duplication or data problems | 4 | 1 | 1 | 6 |
| Other or no reason given | 1 | 1 | 1 | 3 |

- **Prof. Kumarasamy Sudhakar.** His ORCID record shows MANIT until February 2017 and Universiti Malaysia Pahang since March 2017 [5], yet 114 of his 118 later papers still list MANIT. He holds 2.5% of MANIT's papers but **12.9% of its citations**. MANIT's h-index is **118** with all his papers, **113** with only his pre-2017 papers, and **109** without them [3]. *(Faculty tab)*

- **Delayed recognition ("sleeping beauties").** The 13 papers with at most 3 citations in their first three years and at least 40 later were re-checked with the beauty coefficient of Ke et al. [10], after removing self-citations and checking publication dates in Crossref [11]. **6 hold up** (in the top 1% of the corpus), for example a 2019 MANIT paper on image-based anemia detection (3 citations, then 64); 6 are weaker; and 1 was an artefact of a 30 December publication date. These are short delays rather than classic sleeping beauties, as the papers are at most ten years old. *(Papers tab)*

## 5. AI Research Assistant

The assistant answers questions about faculty, collaborations, papers and the network, using only the project's analysis tools, so it cannot invent data.

- **Checked answers:** every number in an AI-written answer is checked against the data, and unknown names are reported as not found.
- **Explained suggestions:** each suggested collaborator comes with a reason (shared co-authors, network distance, shared topics).
- **Robust input:** it handles spelling mistakes openly, and answers questions on retractions, departments, regions and year ranges.
- **Tested:** it answered **71/71** test questions correctly, **139/140** numbers in AI answers were traced to the data (the one untraced number was flagged to the user), and **100/100** automated tests pass [9].

*(AI Research Assistant page)*

## 6. Main Takeaways

1. **Rankings depend on the metric:** NIT Silchar leads on output and Q1, MANIT on citation impact, NIT Jamshedpur on growth.
2. **Impact is concentrated:** one researcher who moved abroad accounts for 12.9% of MANIT's citations.
3. **Networks are department-based and institute-bound,** and depend on a few brokers.
4. **Collaboration reaches nationally,** with a fading regional preference; international links depend on a few individual professors.

## References

1. Project tables: `institution_summary.csv`, `institute_comparison.csv`, `multi_author_reanalysis.csv`, `faculty_network_results.json`, `resilience_results.json`, `link_prediction_results.json`, `citation_sources.json`, `authorships.csv`, `locality/foreign_partners.csv` (github.com/Avh09/DPCN_assgn2)
2. `retractions.py` → `stats/retractions.json`
3. `affiliation_checks.py`; `locality_reach.py` → `locality/partners_locality.csv`
4. Crossref API; Retraction Watch Database; publishers' retraction notices
5. ORCID 0000-0002-4867-2362; CV of Dr. K. Sudhakar, UMPSA (2021)
6. CSIR-NML (nmlindia.org); President of India press release on IIT Guwahati (2022); IIIT Bhopal
7. Katz, J. S. (1994). Geographical proximity and scientific collaboration. *Scientometrics*, 31(1), 31–43
8. Measuring and characterizing international collaboration patterns in Indian scientific research (2023). *Scientometrics*, 128, 5081–5116
9. `tests/evaluate_assistant.py` → `ASSISTANT_EVALUATION.md`
10. Ke, Q., Ferrara, E., Radicchi, F. & Flammini, A. (2015). Defining and identifying Sleeping Beauties in science. *PNAS*, 112(24), 7426–7431
11. `sleeping_beauties.py` → `stats/sleeping_beauties.csv`; publication dates from the Crossref API
