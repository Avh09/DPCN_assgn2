"""Step 7: find which Indian institutes cite our papers (incoming) and which
Indian institutes our papers cite (outgoing).

Writes compact jsonl files to data/raw/links/ (resumable, one line per work):
  citing.jsonl      works that cite our papers: id, year, our papers they cite,
                    and every institution on them (id, name, country, our-name)
  referenced.jsonl  works our papers cite (outside our corpus): same institutions

Budget note: OpenAlex free key = USD 1/day, a list call costs 0.0001.
  incoming  ~ 2,000 calls, outgoing ~ 5,200 calls (100 ids per call).
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

import config

API = "https://api.openalex.org/works"
LINKS = config.RAW_DIR / "links"
LINKS.mkdir(parents=True, exist_ok=True)
lock = threading.Lock()
stop = threading.Event()


def short(u):
    return u.rsplit("/", 1)[-1] if u else None


def insts_of(w):
    seen, out = set(), []
    for a in w.get("authorships") or []:
        for i in a.get("institutions") or []:
            iid = short(i.get("id"))
            if not iid or iid in seen:
                continue
            seen.add(iid)
            lin = {short(x) for x in i.get("lineage") or []} | {iid}
            ours = next((config.ID_TO_NAME[x] for x in lin if x in config.ID_TO_NAME), "")
            out.append([iid, i.get("display_name"), i.get("country_code"), ours, i.get("type")])
    return out


def get(params):
    params = dict(params, mailto=config.EMAIL, api_key=config.API_KEY)
    for attempt in range(6):
        if stop.is_set():
            return None
        try:
            r = requests.get(API, params=params, timeout=90)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (402, 429) and "budget" in r.text.lower():
                print("BUDGET EXHAUSTED:", r.text[:200], flush=True)
                stop.set()
                return None
            print("HTTP", r.status_code, r.text[:120], flush=True)
        except requests.RequestException as e:
            print("ERR", repr(e)[:100], flush=True)
        time.sleep(2 ** attempt)
    return None


def done_batches(path):
    p = path.with_suffix(".done")
    return set(p.read_text().split()) if p.exists() else set()


def mark_done(path, key):
    with lock, open(path.with_suffix(".done"), "a") as f:
        f.write(key + "\n")


def checked_ids(path):
    """Works whose citing papers were fetched completely (one id per line). Keeps a corpus change from re-fetching everything:
    the batch keys in .done shift whenever works are added or removed, this per-work list does not."""
    p = path.with_suffix(".checked")
    return set(p.read_text().split()) if p.exists() else set()


def mark_checked(path, ids):
    with lock, open(path.with_suffix(".checked"), "a") as f:
        f.write("\n".join(ids) + "\n")


def do_citing(batch_ids, out):
    key = batch_ids[0]
    ids = set(batch_ids)
    cursor = "*"
    rows = []
    while cursor and not stop.is_set():
        d = get({"filter": "cites:" + "|".join(batch_ids), "per_page": 200, "cursor": cursor,
                 "select": "id,publication_year,authorships,referenced_works"})
        if d is None:
            return
        for w in d["results"]:
            cited = [short(x) for x in w.get("referenced_works") or [] if short(x) in ids]
            rows.append({"id": short(w["id"]), "year": w.get("publication_year"),
                         "cites_our": cited, "insts": insts_of(w)})
        cursor = d["meta"].get("next_cursor")
    with lock, open(out, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    mark_done(out, key)
    mark_checked(out, batch_ids)


def do_refs(batch_ids, out):
    key = batch_ids[0]
    d = get({"filter": "openalex_id:" + "|".join(batch_ids), "per_page": 100,
             "select": "id,publication_year,authorships"})
    if d is None:
        return
    with lock, open(out, "a") as f:
        for w in d["results"]:
            f.write(json.dumps({"id": short(w["id"]), "year": w.get("publication_year"),
                                "insts": insts_of(w)}) + "\n")
    mark_done(out, key)


def run(fn, batches, out, workers=6):
    done = done_batches(out)
    todo = [b for b in batches if b[0] not in done]
    print(f"{out.name}: {len(todo)} batches to do ({len(batches) - len(todo)} done)", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        for n, _ in enumerate(ex.map(lambda b: fn(b, out), todo), 1):
            if n % 50 == 0:
                print(f"  {out.name}: {n}/{len(todo)}", flush=True)
            if stop.is_set():
                break


def main():
    p = pd.read_csv(config.OUT_DIR / "papers.csv",
                    usecols=["openalex_work_id", "citations", "referenced_works"])
    cited_ids = p[p.citations > 0].openalex_work_id.tolist()
    ours = set(p.openalex_work_id)
    refs = set()
    for s in p.referenced_works.dropna():
        refs.update(s.split(";"))
    refs = sorted(refs - ours)

    chunks = lambda xs, n: [xs[i:i + n] for i in range(0, len(xs), n)]
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "citing"):
        have = checked_ids(LINKS / "citing.jsonl")
        todo_ids = [w for w in cited_ids if w not in have]            # only works not fetched before
        print(f"citing: {len(todo_ids)} of {len(cited_ids)} cited works still to fetch", flush=True)
        run(do_citing, chunks(todo_ids, 50), LINKS / "citing.jsonl")
    if which in ("both", "refs"):
        run(do_refs, chunks(refs, 100), LINKS / "referenced.jsonl")
    print("finished", "(stopped early: budget)" if stop.is_set() else "", flush=True)


if __name__ == "__main__":
    main()
