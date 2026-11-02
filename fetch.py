"""Step 3: download all 2016-2026 works of our 3 institutes from OpenAlex.

Pages are saved as data/raw/works_0001.json, ... and the run is resumable:
re-running continues from the last saved page's next_cursor.
"""
import json
import time
from datetime import date

import requests

import config

API = "https://api.openalex.org/works"
SELECT = ",".join([
    "id", "doi", "title", "publication_year", "type", "cited_by_count",
    "primary_location", "authorships", "referenced_works", "primary_topic",
])


def get(params, retries=5):
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            print(f"HTTP {r.status_code}, retrying ({attempt + 1}/{retries})")
        except requests.RequestException as e:
            print(f"{e!r}, retrying ({attempt + 1}/{retries})")
        time.sleep(2 ** attempt)
    raise RuntimeError("OpenAlex request kept failing")


def main():
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    ids = "|".join(config.ID_TO_NAME)
    flt = (f"authorships.institutions.lineage:{ids},"
           f"publication_year:{config.YEAR_FROM}-{config.YEAR_TO}")

    pages = sorted(config.RAW_DIR.glob("works_*.json"))
    cursor, n = "*", 0
    if pages:
        last = json.loads(pages[-1].read_text())
        cursor, n = last["meta"].get("next_cursor"), len(pages)
        print(f"Resuming after page {n}")

    while cursor:
        params = {"filter": flt, "per_page": 200, "cursor": cursor,
                  "select": SELECT, "mailto": config.EMAIL}
        if config.API_KEY:
            params["api_key"] = config.API_KEY
        data = get(params)
        n += 1
        (config.RAW_DIR / f"works_{n:04d}.json").write_text(json.dumps(data))
        cursor = data["meta"].get("next_cursor")
        print(f"page {n}: {len(data['results'])} works (total count {data['meta']['count']})")
        time.sleep(0.2)

    manifest = {
        "downloaded_on": date.today().isoformat(),
        "endpoint": API,
        "filter": flt,
        "select": SELECT,
        "institutes": config.INSTITUTES,
        "pages": n,
    }
    (config.RAW_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print("done", manifest["downloaded_on"])


if __name__ == "__main__":
    main()
