# DPCN Group 15 — Research Atlas

Bibliometric and network analysis of MANIT Bhopal, NIT Jamshedpur and NIT Silchar (OpenAlex, 2016–2026; 2026 is a partial year),
with a static dashboard, a Streamlit app that embeds it, and an AI Research Assistant that answers questions from the computed data.

## Run

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/streamlit_app.py      # Dashboard page + AI Research Assistant page
# or just open dashboard/index.html in a browser (no server needed; the assistant needs Streamlit)
```

Rebuild everything from the raw download (needs `data/raw/`, `OPENALEX_*`/`ELSEVIER_API_KEY` environment variables for the fetch steps; keys are never stored in the repo):

```bash
./run_all.sh                 # default: build → enrich → quartiles → faculty → networks → outflow → inflow → partners → facstats → report → dashboard
./run_all.sh dashboard       # only regenerate dashboard/data.js (runs locality_reach.py, key_findings.py, build_dashboard.py)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONHASHSEED=0 python -m pytest tests    # 37 tests
python validate.py           # 52 data checks
```

## AI Research Assistant

Page "AI Research Assistant" in the Streamlit app. Every question is answered from allowlisted analysis tools (`assistant/tools.py`)
that read the final tables and the faculty graph; the model never runs code, SQL or file access.

* **With a key** (`ANTHROPIC_API_KEY` in the environment or in Streamlit secrets; optional `ANTHROPIC_MODEL`): the model chooses tools, writes the answer from the tool results, and numbers not found in the results are flagged.
* **Without a key** (or if the API fails): a deterministic router uses the same tools and the same data (`assistant/router.py`, `answers.py`). Answers separate facts, statistics, predictions and interpretation, list limitations and show references.
* Ambiguous names (“Rajesh Purohit”) trigger a choice; follow-up questions keep context; figures highlight the pair, path or common collaborators.

### Deploy on Streamlit Community Cloud

1. Push the repository (including `data/out/`, `data/faculty_final.csv`, `dashboard/`; `data/raw/` is not needed) to GitHub.
2. New app → main file `dashboard/streamlit_app.py`, requirements `dashboard/requirements.txt`.
3. App settings → Secrets: `ANTHROPIC_API_KEY = "..."` (optional). Never commit keys.

## What was changed (audit fixes)

| Area | Change | Files |
|---|---|---|
| Citation heatmap | Row = citing, column = cited. The old matrix was transposed (`DataFrame.to_dict()` orientation). Joint papers count for every institute they belong to. Raw and row-% views. | `networks.py`, `dashboard/app.js` |
| DOI-less papers | Citation edges, in-degree, PageRank are keyed by OpenAlex work ID (DOI optional). | `extra_metrics.py`, `networks.py`, `build_dashboard.py` |
| Citation sources | In-corpus links split into author self-citation / same institute other author / between our institutes; per-year PageRank rank; “within-corpus” labelling. | `extra_metrics.py`, `dashboard/extras.js` |
| Venue types | Journal/conference decided by Scopus aggregation type (`venue_types.py`), not by the word “proceedings”. | `build_tables.py`, `venue_types.py` |
| Duplicates | Same title, year ±1, same venue, matching authors are merged; audit in `data/out/duplicate_audit.csv`. | `build_tables.py` |
| Q1 share | One definition: Q1 journal papers ÷ journal papers with a quartile; conference ranks (CORE) separate. | `metrics_defs.py`, `deep_analysis.py` |
| Conferences | Named vs generic series via Crossref; CORE matching. | `conference_resolution.py` |
| New analyses | Network resilience; temporal link prediction; institute comparison; concentration; review and team-size analyses; generated key findings. | `resilience.py`, `collab_model.py`, `link_prediction.py`, `deep_insights.py`, `key_findings.py` |
| Dashboard | Key findings per tab, comparison table, citation sources, degree CCDF, resilience page, potential-collaborations page, data-quality block. | `dashboard/extras.js`, `build_dashboard.py` |
| Assistant | New package and Streamlit page. | `assistant/`, `dashboard/streamlit_app.py` |
| Tests | 37 tests (flow direction, DOI-less metrics, venue typing, duplicates, no-leakage, resilience, assistant). | `tests/` |

## Limitations (not completed or not verifiable)

* LLM mode is implemented but was not exercised against the live API in development (no key available); the deterministic mode is tested.
* Faculty roster, departments and the 2016–2026 window limit all metrics; h-index here is not a career h-index. Some faculty still have an unknown department.
* Link-prediction scores for **new** collaborations are rankings, not probabilities (calibration slope 0.41). Repeat-collaboration probabilities pass the calibration check.
* CORE covers computer-science conferences; the only A* paper in the unfiltered corpus has no verified-faculty author. Many conference papers appear under publisher series only.
* Quartiles for some venues are estimated (see Methodology tab); OpenAlex omits ~27k referenced works, so in-corpus citation counts are lower bounds.
* The handwritten “GDP / climate analysis” note in the brief was ambiguous and has not been implemented.
* The dashboard Reach, Flows and Collaboration tabs keep their original layouts with added key findings; the larger redesign items in the brief (field→subfield drill-down, performance-vs-connectivity scatter, participation-coefficient views, Sankey and 100%-stacked partner types) are not built.
* The Elsevier API key used during development should be revoked.
