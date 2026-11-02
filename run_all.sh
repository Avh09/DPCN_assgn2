#!/usr/bin/env bash
# Runs the pipeline in the right order, starting at a chosen step, then validate.py.
#
#   ./run_all.sh              rebuild from build_tables.py onwards (default; needs ELSEVIER_API_KEY for quartiles)
#   ./run_all.sh networks     start at networks.py (only if the faculty step has been run on the current tables)
#   ./run_all.sh --list       show the steps
#
# Steps: fetch build enrich quartiles faculty networks outflow inflow partners facstats report dashboard
# The faculty step narrows the corpus to faculty publications (corpus_filter.py); to change a faculty
# decision, edit data/faculty*/ or data/faculty_overrides.csv and rerun from `build`.
# Why the order matters: several scripts write group15_data.csv in turn; enrich.py rebuilds it
# and empties the citation columns, and networks.py rewrites indian_connections_detailed.csv.
#
# Before running anything, every input the chosen steps need is checked. If one is missing,
# the script stops WITHOUT changing any file and says how to get it.
set -euo pipefail
cd "$(dirname "$0")"
# fixed hash order: same set/dict iteration order on every run, so ties and the network
# communities come out identical each time
export PYTHONHASHSEED=0

STEPS=(fetch build enrich quartiles faculty networks outflow inflow partners facstats report dashboard)
START="${1:-build}"

if [[ "$START" == "--list" || "$START" == "-h" || "$START" == "--help" ]]; then
    sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
fi
if [[ ! " ${STEPS[*]} " =~ " $START " ]]; then
    echo "Unknown step '$START'. Steps: ${STEPS[*]}"; exit 1
fi

PY=.venv/bin/python
[[ -x $PY ]] || { echo "No .venv found. Set it up first (see NETWORKS_WORK.md, section 4)."; exit 1; }

# steps from START onwards
RUN=()
on=0
for s in "${STEPS[@]}"; do
    [[ $s == "$START" ]] && on=1
    [[ $on == 1 ]] && RUN+=("$s")
done
runs() { [[ " ${RUN[*]} " =~ " $1 " ]]; }

# ---------------------------------------------------------------- pre-flight checks
missing=()
need() {   # need <path> <how to get it>
    compgen -G "$1" > /dev/null || missing+=("$1  ->  $2")
}
has_key() { [[ -n "${OPENALEX_API_KEY:-}" || -s .openalex_key ]]; }

runs fetch    && { has_key || missing+=("OpenAlex API key  ->  echo KEY > .openalex_key"); }
runs build    && ! runs fetch && need "data/raw/works_*.json" "run ./run_all.sh fetch, or copy data/raw/ from a teammate"
runs enrich   && need "data/ref/sjr_all.csv" "in the repo (data/ref/)"
runs build    && need "data/ref/venue_types.csv" "ELSEVIER_API_KEY=... python venue_types.py (about 25 min, cached; the file is in the repo)"
runs outflow  && need "data/raw/links/referenced.jsonl" "run: $PY links.py refs (about 1-2 h), or copy from a teammate"
runs inflow   && need "data/raw/links/citing.jsonl" "run: $PY links.py citing (about 1 h), or copy from a teammate"
runs faculty  && need "data/faculty/*.csv" "in the repo (data/faculty/)"
if runs partners; then
    need "data/raw/links/citing.jsonl" "run: $PY links.py citing (about 1 h), or copy from a teammate"
    [[ -s data/raw/links/subfields.json ]] || has_key || missing+=("OpenAlex API key (partners.py looks up ~70 institutes)  ->  echo KEY > .openalex_key")
fi
if (( ${#missing[@]} )); then
    echo "Not starting: these inputs are missing (no file has been changed):"
    printf '  - %s\n' "${missing[@]}"
    exit 1
fi

# ---------------------------------------------------------------- run
step() { echo; echo "=== $*"; "$PY" "$@"; }
echo "Running: ${RUN[*]} -> validate"
for s in "${RUN[@]}"; do
    case $s in
        fetch)    step fetch.py ;;
        build)    step build_tables.py; step work_topics.py ;;
        enrich)   step enrich.py ;;
        quartiles) step scopus_quartiles.py ;;
        networks) step networks.py ;;
        outflow)  step outflow.py ;;
        inflow)   step inflow.py ;;
        faculty)  step faculty_match.py; step author_resolution.py; step corpus_filter.py; step conference_resolution.py ;;
        facstats) step faculty_stats.py; step faculty_network.py; step extras.py; step deep_analysis.py; step extra_metrics.py; step resilience.py; step link_prediction.py; step deep_insights.py; step output_drivers.py; step new_views.py ;;
        partners) step partners.py ;;
        report)   step stats.py; step plots.py --no-show; step audit_summary.py ;;
        dashboard) step locality_reach.py; step key_findings.py; step build_dashboard.py ;;
    esac
done

echo; echo "=== validate.py"
"$PY" validate.py
