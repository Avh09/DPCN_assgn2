"""Extra OpenAlex fields for the corpus papers: field-weighted citation impact (fwci), citation percentile, citations by year.

fwci = citations / the average citations of works of the same type, year and subfield worldwide (1 = world average). This is a
proper field- and age-normalised impact; the corpus-only baseline would be circular. Needs the OpenAlex key (.openalex_key).
Writes data/raw/work_extras.jsonl (resumable) and data/out/work_extras.csv.
    python fetch_work_extras.py
"""
import json
import time

import pandas as pd
import requests

import config

RAW = config.RAW_DIR / "work_extras.jsonl"


def main():
    ids = sorted(pd.read_csv(config.OUT_DIR / "papers_enriched.csv", usecols=["openalex_work_id"], dtype=str).openalex_work_id)
    have = set()
    if RAW.exists():
        have = {json.loads(l)["id"].rsplit("/", 1)[-1] for l in RAW.read_text().splitlines()}
    todo = [i for i in ids if i not in have]
    print(len(ids), "papers,", len(todo), "to fetch", flush=True)
    with RAW.open("a") as out:
        for k in range(0, len(todo), 100):
            ch = todo[k:k + 100]
            for attempt in range(6):
                try:
                    r = requests.get("https://api.openalex.org/works", params={
                        "filter": "openalex_id:" + "|".join(ch), "per_page": 100, "api_key": config.API_KEY, "mailto": config.EMAIL,
                        "select": "id,fwci,citation_normalized_percentile,counts_by_year,cited_by_count,is_retracted"}, timeout=90)
                except requests.RequestException:
                    time.sleep(3 * (attempt + 1))
                    continue
                if r.status_code == 200:
                    for w in r.json()["results"]:
                        out.write(json.dumps(w) + "\n")
                    break
                if r.status_code == 429 and "budget" in r.text.lower():
                    raise SystemExit("OpenAlex budget used up, rerun later")
                time.sleep(2 ** attempt)
            if (k // 100) % 20 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    rows = []
    for l in RAW.read_text().splitlines():
        w = json.loads(l)
        pct = w.get("citation_normalized_percentile") or {}
        rows.append({"openalex_work_id": w["id"].rsplit("/", 1)[-1], "fwci": w.get("fwci"), "citation_percentile": pct.get("value"),
                     "is_top_1pct": pct.get("is_in_top_1_percent"), "is_top_10pct": pct.get("is_in_top_10_percent"),
                     "is_retracted": w.get("is_retracted"), "counts_by_year": json.dumps({c["year"]: c["cited_by_count"] for c in w.get("counts_by_year") or []})})
    pd.DataFrame(rows).drop_duplicates("openalex_work_id").to_csv(config.OUT_DIR / "work_extras.csv", index=False)
    print("work_extras.csv:", len(rows))


if __name__ == "__main__":
    main()
