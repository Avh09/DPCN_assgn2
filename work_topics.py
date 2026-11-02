"""Topic hierarchy of every downloaded work (OpenAlex primary topic): domain > field > subfield > topic.

OpenAlex classifies each work into 4 domains, 26 fields, about 250 subfields and about 4,500 topics. The dashboard uses fields
(drill-down to subfield and topic), and research-topic similarity / link prediction use subfields. Reads data/raw/works_*.json
once and writes data/out/work_topics.csv (openalex_work_id, domain, field, subfield, topic, ids). Local data only.
"""
import json

import pandas as pd

import config


def main():
    rows = {}
    for f in sorted(config.RAW_DIR.glob("works_*.json")):
        for w in json.loads(f.read_text())["results"]:
            t = w.get("primary_topic") or {}
            g = lambda k: (t.get(k) or {})
            rows[w["id"].rsplit("/", 1)[-1]] = {
                "openalex_work_id": w["id"].rsplit("/", 1)[-1], "domain": g("domain").get("display_name", ""),
                "field": g("field").get("display_name", ""), "field_id": (g("field").get("id") or "").rsplit("/", 1)[-1],
                "subfield": g("subfield").get("display_name", ""), "subfield_id": (g("subfield").get("id") or "").rsplit("/", 1)[-1],
                "topic": t.get("display_name", ""), "topic_id": (t.get("id") or "").rsplit("/", 1)[-1], "topic_score": t.get("score", "")}
    d = pd.DataFrame(rows.values())
    d.to_csv(config.OUT_DIR / "work_topics.csv", index=False)
    print(len(d), "works;", d.subfield.nunique(), "subfields;", d.topic.nunique(), "topics")


if __name__ == "__main__":
    main()
