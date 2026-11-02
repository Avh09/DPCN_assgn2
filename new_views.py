"""Step 15c: extra views for the dashboard (data/out/stats/insights/new_views.json)

  countries     papers with a co-author from each foreign country, per institute and overall (India excluded: it is the home country)
  coauthors     outside co-authors (not our faculty, not authors of our own institutes): papers, citations of those papers, institute
  pairs         per (our institute, outside institute): distinct co-authors and mean FWCI of the joint papers (for the Partner explorer)
  fwci_places   mean/median FWCI of the three institutes' papers that have a co-author in each place (Indian state or foreign country) vs the institute's baseline
  give_take     per partner institute: citations it gives us vs citations we give it (+ private-university tag, approximate)

Everything is computed from the complete co-author list (all_authors/authorships.csv) restricted to papers of the final corpus.
"""
import json
from collections import Counter, defaultdict

import pandas as pd

import config
from locality_reach import OUR_NAMES, cluster_of, state_of

# Non-government (private) universities, matched by name. Approximate: the data carries no public/private flag.
PRIVATE_KEYS = ["vellore institute", "vit bhopal", "vit university", "saveetha", "lovely professional", "srm ", "manipal", "chandigarh university", "amity", "chitkara", "petroleum and energy studies",
                "koneru lakshmaiah", "graphic era", "amrita", "gla university", "vel tech", "kiit", "new horizon", "sharda", "galgotias", "bennett", "shiv nadar", "ashoka", "o.p. jindal", "jain university",
                "christ university", "bits pilani", "birla institute of technology and science", "thapar", "narsee", "symbiosis", "mit world peace", "dy patil", "d. y. patil", "sathyabama", "bharath institute",
                "hindustan institute", "kalasalingam", "karunya", "sastra", "siksha 'o' anusandhan", "lpu", "uttaranchal", "dit university", "geeta", "noida international", "gd goenka", "g.d. goenka",
                "rayat bahra", "lingaya", "maharishi markandeshwar", "mody", "pandit deendayal energy", "nirma", "ganpat", "charusat", "marwadi", "parul", "silver oak", "rai university", "manav rachna",
                "k l university", "kl university", "srm institute", "reva university", "presidency university, bangalore", "dayananda sagar", "rv college", "b.m.s. college", "pes university", "mvj", "kongu",
                "bannari", "sri krishna", "psg college", "vignan", "gitam", "aditya", "gayatri", "raghu", "vasavi", "cmr", "mahindra", "woxsen", "sreenidhi", "anurag", "mohan babu", "sri venkateswara college of engineering and technology"]


def is_private(name):
    n = (name or "").lower()
    return any(k in n for k in PRIVATE_KEYS)

OUT, STATS = config.OUT_DIR, config.OUT_DIR / "stats"
INSTS = list(config.INSTITUTES)
SHORT = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}


def country_name(code):
    try:
        from babel import Locale
        return Locale("en").territories.get(code, code)
    except Exception:
        return code


def main():
    g15 = pd.read_csv(OUT / "group15_data.csv", dtype=str, keep_default_na=False, usecols=["openalex_work_id", "institution", "citations", "is_faculty"])
    g15["cit"] = pd.to_numeric(g15.citations, errors="coerce").fillna(0)
    insts_of = g15.groupby("openalex_work_id").institution.agg(lambda s: sorted(set(s))).to_dict()
    cites = g15.drop_duplicates("openalex_work_id").set_index("openalex_work_id").cit.to_dict()
    fw = pd.read_csv(OUT / "work_extras.csv", dtype=str, usecols=["openalex_work_id", "fwci"]) if (OUT / "work_extras.csv").exists() else pd.DataFrame(columns=["openalex_work_id", "fwci"])
    fwci = dict(zip(fw.openalex_work_id, pd.to_numeric(fw.fwci, errors="coerce")))
    ff = pd.read_csv(config.OUT_DIR.parent / "faculty_final.csv", dtype=str, keep_default_na=False)
    fac_ids = {x for v in ff.openalex_author_ids for x in v.split(";")}
    a = pd.read_csv(OUT / "all_authors" / "authorships.csv", dtype=str, keep_default_na=False,
                    usecols=["openalex_work_id", "author_id", "author_name", "country_codes", "institutions_detail", "is_our_inst"])
    a = a[a.openalex_work_id.isin(insts_of)]
    country_papers = {k: defaultdict(set) for k in ["all"] + INSTS}
    co = defaultdict(lambda: {"works": set(), "inst": Counter(), "ours": set(), "name": ""})
    pair = defaultdict(lambda: {"works": set(), "authors": set()})
    for w, aid, nm, ccs, det, our in zip(a.openalex_work_id, a.author_id, a.author_name, a.country_codes, a.institutions_detail, a.is_our_inst):
        ours = insts_of[w]
        for c in {c for c in ccs.split(";") if c and c != "IN"}:
            country_papers["all"][c].add(w)
            for i in ours:
                country_papers[i][c].add(w)
        if our == "True" or aid in fac_ids:
            continue
        names = []
        for p in filter(None, det.split(";")):
            bits = p.split("|")
            n = bits[0].strip()
            if n and n.lower() not in OUR_NAMES:
                names.append((n, bits[1].strip() if len(bits) > 1 else ""))
        for n, cc in names:
            for i in ours:
                P = pair[(i, n)]
                P["works"].add(w); P["authors"].add(aid)
        e = co[aid]
        e["works"].add(w); e["name"] = nm.strip(); e["ours"].update(ours)
        for n, _ in names[:1]:
            e["inst"][n] += 1
    countries = {k: [{"code": c, "name": country_name(c), "papers": len(ws)} for c, ws in sorted(v.items(), key=lambda kv: -len(kv[1]))[:15]] for k, v in country_papers.items()}
    coauthors = sorted(({"name": e["name"], "institute": (e["inst"].most_common(1)[0][0] if e["inst"] else "(no affiliation)"), "papers": len(e["works"]),
                         "citations": int(sum(cites.get(w, 0) for w in e["works"])), "ours": sorted(SHORT[i] for i in e["ours"])} for e in co.values() if e["name"]),
                       key=lambda r: (-r["papers"], -r["citations"]))[:400]
    pairs = [[INSTS.index(i), n, len(P["authors"]), round(float(pd.Series([fwci.get(w) for w in P["works"]]).mean()), 2)] for (i, n), P in pair.items()]
    # FWCI by partner place: a paper counts for a place if any outside co-author is affiliated there (Indian state or foreign country)
    place_works = defaultdict(set)
    for w, ccs, det in zip(a.openalex_work_id, a.country_codes, a.institutions_detail):
        for p in filter(None, det.split(";")):
            bits = p.split("|")
            n, cc = bits[0].strip(), (bits[1].strip() if len(bits) > 1 else "")
            if not n or n.lower() in OUR_NAMES:
                continue
            if cc == "IN":
                st = state_of(n)
                if st not in ("Unknown", "National (multi-site)"):
                    place_works["India: " + st].add(w)
            elif cc:
                place_works[country_name(cc)].add(w)
    fw_all = {w: v for w, v in fwci.items() if w in insts_of and v == v}
    def stat(ws):
        v = pd.Series([fw_all[w] for w in ws if w in fw_all])
        return None if len(v) < 1 else {"n": int(len(v)), "mean": round(float(v.mean()), 2), "median": round(float(v.median()), 2)}
    fwci_places = {}
    for scope in ["all"] + INSTS:
        base_ws = {w for w in fw_all if scope == "all" or scope in insts_of[w]}
        base = stat(base_ws)
        rows = []
        for place, ws in place_works.items():
            st = stat(ws & base_ws)
            if st and st["n"] >= 25:
                rows.append({"place": place, **st, "lift": round(st["mean"] - base["mean"], 2), "lift_median": round(st["median"] - base["median"], 2)})
        fwci_places[scope] = {"baseline": base, "rows": sorted(rows, key=lambda r: -r["n"])[:40]}

    # Citation give-and-take with every partner institute
    inc = pd.read_csv(OUT / "incoming_citations_by_institute.csv"); outg = pd.read_csv(OUT / "outgoing_citations_by_institute.csv")
    give_take = {}
    for i in INSTS:
        a_in = inc[inc.your_inst == i].set_index("citing_inst"); a_out = outg[outg.your_inst == i].set_index("cited_inst")
        rows = []
        for n in set(a_in.index) | set(a_out.index):
            ci = int(a_in.citations.get(n, 0)) if n in a_in.index else 0
            co_ = int(a_out.citations.get(n, 0)) if n in a_out.index else 0
            cl = (a_in.cluster.get(n) if n in a_in.index else a_out.cluster.get(n)) or "Other"
            rows.append({"name": n, "cluster": cl, "private": is_private(n), "cites_us": ci, "we_cite": co_})
        rows.sort(key=lambda r: -(r["cites_us"] + r["we_cite"]))
        tot_in, tot_out = sum(r["cites_us"] for r in rows), sum(r["we_cite"] for r in rows)
        def bucket(f):
            x = [r for r in rows if f(r)]
            return {"cites_us": sum(r["cites_us"] for r in x), "we_cite": sum(r["we_cite"] for r in x), "institutes": len(x)}
        give_take[i] = {"rows": rows[:60], "total_in": tot_in, "total_out": tot_out,
                        "private_univ": bucket(lambda r: r["private"]), "other_univ": bucket(lambda r: r["cluster"] == "University/college" and not r["private"]),
                        "premier": bucket(lambda r: r["cluster"] in ("IIT", "NIT", "IIIT", "IISER", "Premier science inst.")),
                        "industry": bucket(lambda r: r["cluster"] == "Industry"), "govt_lab": bucket(lambda r: r["cluster"] in ("CSIR", "DAE", "Government lab/agency"))}
    out = {"fwci_places": fwci_places, "give_take": give_take, "countries": countries, "coauthors": coauthors, "pairs": pairs,
           "note": "Outside co-authors only: the verified faculty and authors affiliated with MANIT, NIT Jamshedpur or NIT Silchar are excluded. India is left out of the country chart."}
    (STATS / "insights" / "new_views.json").write_text(json.dumps(out, indent=1))
    print("countries", len(countries["all"]), "| coauthors", len(coauthors), "| institute pairs", len(pairs))
    print("fwci places (all):", [(r["place"], r["n"], r["mean"], r["lift"]) for r in fwci_places["all"]["rows"][:12]], fwci_places["all"]["baseline"])
    g = give_take["MANIT Bhopal"]; print("MANIT private univ", g["private_univ"], "total", g["total_in"], g["total_out"])
    print("top countries:", [(c["name"], c["papers"]) for c in countries["all"][:5]])


if __name__ == "__main__":
    main()
