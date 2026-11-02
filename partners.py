"""Indian partner institutes: exact type, research-topic similarity and citations both ways.
(run networks.py, outflow.py and inflow.py first)

1. Partner type. networks.cluster_of guesses from the name, which misses labs whose name does
   not say what they belong to (National Metallurgical Laboratory is a CSIR lab). Here every
   partner's parent organisation is looked up in OpenAlex (associated_institutions with
   relationship "parent") and decides CSIR / DAE / DRDO / ICAR / ICMR / ISRO; otherwise the name
   rule is kept.
2. Topic similarity. For our 3 institutes and the top TOP_N co-author partners of each, OpenAlex
   counts 2016-2026 papers per subfield (~250 subfields) in one call per institute.
     jaccard           = |A & B| / |A | B| over subfields with >= 1% of the institute's papers
     weighted_jaccard  = sum(min(a_s, b_s)) / sum(max(a_s, b_s)) over subfield shares
3. Citations per partner: cites_from_partner (they cite our papers, inflow.py) and
   cites_to_partner (our papers cite theirs, outflow.py).

Writes to data/out/:
  indian_connections_detailed.csv   + partner_id, partner_cluster (exact), cites_from_partner,
                                    cites_to_partner, jaccard_subfields, weighted_jaccard
  stats/partner_results.json        cross-cluster table, similarity vs collaboration
Caches OpenAlex answers in data/raw/links/institutions.json and subfields.json.
"""
import json
from collections import Counter, defaultdict

import pandas as pd
import requests
from scipy.stats import spearmanr

import config
from networks import cluster_of

OUT = config.OUT_DIR
LINKS = config.RAW_DIR / "links"
TOP_N = 25
PARENT_CLUSTER = {"council of scientific and industrial research": "CSIR",
                  "department of atomic energy": "DAE",
                  "defence research and development organisation": "DRDO",
                  "indian council of agricultural research": "ICAR",
                  "indian council of medical research": "ICMR",
                  "indian space research organisation": "ISRO", "department of space": "ISRO"}


def get(url, params):
    params = dict(params, api_key=config.API_KEY, mailto=config.EMAIL)
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=90)
            if r.ok:
                return r.json()
            print("HTTP", r.status_code, r.text[:120])
        except requests.RequestException as e:
            print("ERR", repr(e)[:100])
    raise SystemExit("OpenAlex not reachable; rerun later (answers so far are cached)")


def cached(path, keys, fetch):
    data = json.loads(path.read_text()) if path.exists() else {}
    todo = [k for k in keys if k not in data]
    for k, v in fetch(todo):
        data[k] = v
        path.write_text(json.dumps(data))
    return data


def fetch_institutions(ids):
    for i in range(0, len(ids), 50):
        b = ids[i:i + 50]
        d = get("https://api.openalex.org/institutions",
                {"filter": "openalex_id:" + "|".join(b), "per_page": 50,
                 "select": "id,display_name,type,associated_institutions"})
        got = {r["id"].rsplit("/", 1)[-1]: r for r in d["results"]}
        for k in b:
            parents = [a["display_name"] for a in (got.get(k) or {}).get("associated_institutions") or []
                       if a.get("relationship") == "parent"]
            yield k, {"parents": parents, "type": (got.get(k) or {}).get("type")}


def fetch_subfields(ids):
    for k in ids:
        d = get("https://api.openalex.org/works",
                {"filter": f"institutions.id:{k},publication_year:{config.YEAR_FROM}-{config.YEAR_TO}",
                 "group_by": "primary_topic.subfield.id"})
        yield k, {g["key_display_name"]: g["count"] for g in d["group_by"] if g["key_display_name"]}


def main():
    det = pd.read_csv(OUT / "indian_connections_detailed.csv")

    # partner name -> OpenAlex id, from the institutions on works that cite us (most common id per name)
    ids_by_name = defaultdict(Counter)
    for line in open(LINKS / "citing.jsonl"):
        for iid, name, cc, _, _ in json.loads(line)["insts"]:
            if cc == "IN" and name:
                ids_by_name[name][iid] += 1
    det["partner_id"] = det.partner_inst.map(lambda n: ids_by_name[n].most_common(1)[0][0] if n in ids_by_name else "")
    print(f"partner rows with an OpenAlex id: {(det.partner_id != '').mean():.1%}")

    # 1. exact partner type from the parent organisation
    pid = sorted({p for p in det.partner_id if p})
    inst = cached(LINKS / "institutions.json", pid, fetch_institutions)

    def exact_cluster(name, typ, p):
        for parent in inst.get(p, {}).get("parents", []):
            for key, c in PARENT_CLUSTER.items():
                if key in parent.lower():
                    return c
        return cluster_of(name, typ)
    old = det.partner_cluster.copy()
    det["partner_cluster"] = [exact_cluster(n, t, p) for n, t, p in zip(det.partner_inst, det.partner_type, det.partner_id)]
    changed = det[old != det.partner_cluster]
    print(f"partner type corrected for {len(changed)} rows:", Counter(zip(old[changed.index], changed.partner_cluster)).most_common(6))

    # 3. citations both ways
    inc = pd.read_csv(OUT / "incoming_citations_by_institute.csv")
    outg = pd.read_csv(OUT / "outgoing_citations_by_institute.csv")
    det = det.drop(columns=[c for c in ("cites_from_partner", "cites_to_partner", "jaccard_subfields",
                                        "weighted_jaccard") if c in det])
    det = det.merge(inc.rename(columns={"citing_inst": "partner_inst", "citations": "cites_from_partner"})
                    [["your_inst", "partner_inst", "cites_from_partner"]], on=["your_inst", "partner_inst"], how="left")
    det = det.merge(outg.rename(columns={"cited_inst": "partner_inst", "citations": "cites_to_partner"})
                    [["your_inst", "partner_inst", "cites_to_partner"]], on=["your_inst", "partner_inst"], how="left")
    det[["cites_from_partner", "cites_to_partner"]] = det[["cites_from_partner", "cites_to_partner"]].fillna(0).astype(int)

    # 2. topic similarity for our institutes and their top partners
    top = det.sort_values("shared_papers", ascending=False).groupby("your_inst").head(TOP_N)
    ours = {k: v["openalex_id"] for k, v in config.INSTITUTES.items()}
    want = sorted(set(ours.values()) | {p for p in top.partner_id if p})
    sub = cached(LINKS / "subfields.json", want, fetch_subfields)

    def shares(k):
        c = sub.get(k) or {}
        t = sum(c.values())
        return {s: v / t for s, v in c.items()} if t else {}

    def sims(a, b):
        sa, sb = shares(a), shares(b)
        if not sa or not sb:
            return None, None
        A, B = {s for s, v in sa.items() if v >= .01}, {s for s, v in sb.items() if v >= .01}
        keys = set(sa) | set(sb)
        wj = sum(min(sa.get(s, 0), sb.get(s, 0)) for s in keys) / sum(max(sa.get(s, 0), sb.get(s, 0)) for s in keys)
        return round(len(A & B) / len(A | B), 3), round(wj, 3)

    is_top = det.index.isin(top.index)
    sim = [sims(ours[y], p) if t and p else (None, None) for y, p, t in zip(det.your_inst, det.partner_id, is_top)]
    det["jaccard_subfields"] = [s[0] for s in sim]
    det["weighted_jaccard"] = [s[1] for s in sim]
    det.sort_values(["your_inst", "shared_papers"], ascending=[True, False]).to_csv(
        OUT / "indian_connections_detailed.csv", index=False)

    # ------------------------------------------------------------- summary
    res = {"between_our_institutes": {f"{a} vs {b}": dict(zip(("jaccard", "weighted_jaccard"), sims(ours[a], ours[b])))
                                      for i, a in enumerate(ours) for b in list(ours)[i + 1:]}}
    for y, g in det.groupby("your_inst"):
        t = g.dropna(subset=["weighted_jaccard"])
        rho, p = spearmanr(t.weighted_jaccard, t.shared_papers)
        cl = g.groupby("partner_cluster")[["shared_papers", "cites_from_partner", "cites_to_partner"]].sum()
        cl["partners"] = g.partner_cluster.value_counts()
        res[y] = {
            "cross_cluster": cl.sort_values("shared_papers", ascending=False).reset_index().to_dict("records"),
            "top_partners": g.head(10)[["partner_inst", "partner_cluster", "shared_papers", "cites_from_partner",
                                        "cites_to_partner", "jaccard_subfields", "weighted_jaccard"]].to_dict("records"),
            "most_similar_partners": t.sort_values("weighted_jaccard", ascending=False).head(5)[
                ["partner_inst", "weighted_jaccard", "shared_papers"]].to_dict("records"),
            "least_similar_partners": t.sort_values("weighted_jaccard").head(3)[
                ["partner_inst", "weighted_jaccard", "shared_papers"]].to_dict("records"),
            "similarity_vs_shared_papers_spearman": {"rho": round(rho, 3), "p": round(p, 3), "n": len(t)},
        }
    (OUT / "stats" / "partner_results.json").write_text(json.dumps(res, indent=1, default=str))

    print("\nsimilarity between our institutes:", res["between_our_institutes"])
    pd.set_option("display.width", 220)
    for y in config.INSTITUTES:
        r = res[y]
        print(f"\n== {y}  similarity vs collaboration: {r['similarity_vs_shared_papers_spearman']}")
        print(pd.DataFrame(r["cross_cluster"]).to_string(index=False))
        print(pd.DataFrame(r["top_partners"]).to_string(index=False))


if __name__ == "__main__":
    main()
