"""Collaboration locality and reach: who our faculty work with outside their own institute, where those
partners are, and which nodes matter most inside versus outside each institute.

Runs offline on the final tables in data/out/ (no OpenAlex calls). Needs networkx only:
    python locality_reach.py

1. Partner type. Improves the name rule in networks.cluster_of with known CSIR / DAE / DRDO / ICAR / ISRO /
   ICMR labs and central universities (the name rule put e.g. National Metallurgical Laboratory under "Other").
2. Locality. Each Indian partner gets a state (from a curated list of place names and well-known institutes)
   and a region; a link is same-state, same-region, other-region, national body (multi-site, e.g. CSIR HQ)
   or unknown. Home states: MANIT = Madhya Pradesh, NIT Jamshedpur = Jharkhand, NIT Silchar = Assam.
3. Peer institutes. Joint papers with NITs, IITs, IIITs, IISERs and IISc outside our group, by year,
   with the faculty behind each link; and links between our own three institutes.
4. Within vs outside. Per faculty: distinct co-authors at the same institute, at our other two institutes,
   elsewhere in India and abroad. Full author network (all co-authors as nodes): degree and approximate
   betweenness; top external authors and institutes by how many of our faculty they connect.
   Per paper: citations from the same institute, from our other two institutes, and from outside the corpus.

Writes data/out/stats/locality/*.csv and data/out/stats/locality_results.json.
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
from networkx.algorithms import community as nxc

import movers

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "out"
ST = OUT / "stats"
LOC = ST / "locality"
INSTS = ["MANIT Bhopal", "NIT Jamshedpur", "NIT Silchar"]
HOME = {"MANIT Bhopal": "Madhya Pradesh", "NIT Jamshedpur": "Jharkhand", "NIT Silchar": "Assam"}
OUR_NAMES = {"maulana azad national institute of technology": "MANIT Bhopal",
             "national institute of technology jamshedpur": "NIT Jamshedpur",
             "national institute of technology silchar": "NIT Silchar"}


def rd(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def wr(name, rows, cols=None):
    LOC.mkdir(parents=True, exist_ok=True)
    cols = cols or (list(rows[0].keys()) if rows else [])
    with open(LOC / name, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ 1. partner type
LABS = [
    ("DAE", ["national institute of science education and research", "bhabha atomic", "atomic", "homi bhabha",
             "saha institute of nuclear", "institute of physics, bhubaneswar", "raja ramanna", "variable energy cyclotron",
             "tata institute of fundamental", "institute for plasma research", "harish-chandra", "institute of mathematical sciences",
             "tata memorial", "nuclear power corporation"]),
    ("CSIR", ["council of scientific and industrial research", "csir", "national metallurgical laboratory",
              "north east institute of science and technology", "central mechanical engineering research",
              "advanced materials and processes research", "central electronics engineering research", "central building research",
              "institute of minerals and materials technology", "national chemical laboratory", "central institute of mining and fuel",
              "indian institute of integrative medicine", "academy of scientific and innovative research",
              "national environmental engineering research", "central glass and ceramic", "indian institute of chemical technology",
              "central salt", "central leather", "central scientific instruments", "national physical laboratory", "central road research",
              "structural engineering research", "national institute for interdisciplinary science", "central food technological",
              "central electrochemical", "national botanical", "central drug research", "institute of genomics",
              "centre for cellular and molecular", "institute of microbial technology", "national geophysical research",
              "national institute of oceanography", "indian institute of petroleum", "indian institute of toxicology",
              "national aerospace laboratories", "central institute of medicinal", "institute of himalayan bioresource"]),
    ("DRDO", ["defence research", "drdo", "defence institute of advanced technology", "integrated test range", "defence metallurgical",
              "research centre imarat", "armament research", "naval science", "solid state physics laboratory"]),
    ("ICAR", ["agricultural research", "icar", "central institute of agricultural engineering", "national dairy research",
              "central rice research", "indian veterinary"]),
    ("ISRO", ["indian space research", "isro", "vikram sarabhai space", "space applications centre", "national remote sensing",
                      "indian institute of remote sensing", "physical research laboratory", "department of space",
                      "north eastern space applications", "aryabhatta research institute"]),
    ("ICMR", ["indian council of medical research", "icmr", "national institute of virology"]),
]
CENTRAL_UNIV = ["jawaharlal nehru university", "university of delhi", "banaras hindu university", "jamia millia", "aligarh muslim",
                "university of hyderabad", "tezpur university", "assam university", "mizoram university", "north eastern hill university",
                "tripura university", "manipur university", "nagaland university", "sikkim university", "central university",
                "guru ghasidas", "indira gandhi national tribal", "harisingh gour", "pondicherry university", "visva-bharati",
                "babasaheb bhimrao ambedkar university", "university of allahabad", "rajiv gandhi university", "english and foreign languages"]


def cluster_of(name, typ):
    n = (name or "").lower()
    for cl, keys in LABS[:1]:  # NISER etc. before the IISER rule below
        if any(k in n for k in keys):
            return cl
    if "indian institute of technology" in n or re.search(r"\biit\b", n):
        return "IIT"
    if "national institute of technology" in n or re.search(r"\bnit\b", n):
        return "NIT"
    if "indian institute of information technology" in n or "international institute of information technology" in n or "iiit" in n or "information technology design and manufacturing" in n:
        return "IIIT"
    if "iiser" in n or "science education and research" in n:
        return "IISER"
    if "indian institute of science" in n:
        return "IISc"
    for cl, keys in LABS[1:]:
        if any(k in n for k in keys):
            return cl
    if "indian statistical" in n or "s.n. bose" in n or "indian association for the cultivation" in n or "jawaharlal nehru centre" in n \
            or "bose institute" in n or "raman research" in n:
        return "Premier science inst."
    if typ == "company":
        return "Industry"
    if typ == "healthcare" or "medical" in n or "aiims" in n or "hospital" in n:
        return "Medical/health"
    if any(k in n for k in CENTRAL_UNIV):
        return "Central university"
    if "universit" in n or "vidyapeeth" in n or "vishwavidyalaya" in n or typ == "education":
        return "Other university/college"
    if typ == "government":
        return "Government lab/agency"
    return "Other"


# ------------------------------------------------------------------ 2. locality
NATIONAL = ["council of scientific and industrial research", "academy of scientific and innovative research", "defence research and development",
            "indian council of agricultural research", "department of atomic energy", "government of india", "india meteorological department",
            "power grid corporation", "bharat heavy electricals", "indian space research organisation", "all india council for technical",
            "tata consultancy", "oracle", "tata motors", "national institute of technical teachers", "indian council of medical research",
            "steel authority of india", "oil and natural gas", "indian oil", "ntpc", "coal india", "larsen", "infosys", "wipro",
            "centre for development of advanced computing", "government of"]
# ordered: first match wins (specific names before generic place names)
STATE_KEYS = [
    ("amity university", "Uttar Pradesh"), ("rajiv gandhi university", "Arunachal Pradesh"), ("guru nanak dev", "Punjab"),
    ("indian institute of petroleum", "Uttarakhand"), ("rcc institute", "West Bengal"), ("parala maharaja", "Odisha"), ("chameli devi", "Madhya Pradesh"),
    ("bundelkhand", "Uttar Pradesh"), ("makhanlal chaturvedi", "Madhya Pradesh"), ("hari singh gour", "Madhya Pradesh"), ("harisingh gour", "Madhya Pradesh"),
    ("chaudhary charan singh", "Uttar Pradesh"), ("yeshwantrao chavan", "Maharashtra"), ("babu banarasi das", "Uttar Pradesh"),
    ("central road research", "Delhi"), ("ymca", "Haryana"), ("vaishno devi", "Jammu & Kashmir"), ("gaya college", "Bihar"), ("vaagdevi", "Telangana"),
    ("dharwad", "Karnataka"), ("raja ramanna", "Madhya Pradesh"), ("indian institute of water management", "Odisha"), ("central glass and ceramic", "West Bengal"),
    ("sonepat", "Haryana"), ("sambalpur", "Odisha"), ("teerthanker mahaveer", "Uttar Pradesh"), ("acharya institute of technology", "Karnataka"),
    ("islamic university of science and technology", "Jammu & Kashmir"), ("banda", "Uttar Pradesh"), ("high security animal", "Madhya Pradesh"),
    ("siddhartha institute of technology", "Andhra Pradesh"), ("indus university", "Gujarat"), ("shri vishwakarma skill", "Haryana"),
    ("srm university, andhra pradesh", "Andhra Pradesh"), ("amity university madhya pradesh", "Madhya Pradesh"), ("sikkim manipal", "Sikkim"),
    ("jaypee university of information technology", "Himachal Pradesh"), ("vit bhopal", "Madhya Pradesh"), ("amity university gurugram", "Haryana"),
    ("amity university jaipur", "Rajasthan"), ("bits hyderabad", "Telangana"), ("hyderabad campus", "Telangana"),
    ("government of west bengal", "West Bengal"), ("government of uttar pradesh", "Uttar Pradesh"), ("icfai university, tripura", "Tripura"),
    ("indian institute of science bangalore", "Karnataka"), ("indian institute of science education and research, bhopal", "Madhya Pradesh"),
    ("national metallurgical laboratory", "Jharkhand"), ("tata steel", "Jharkhand"), ("north east institute of science and technology", "Assam"),
    ("central mechanical engineering research", "West Bengal"), ("advanced materials and processes research", "Madhya Pradesh"),
    ("central electronics engineering research", "Rajasthan"), ("central building research", "Uttarakhand"), ("national institute of hydrology", "Uttarakhand"),
    ("institute of minerals and materials technology", "Odisha"), ("national chemical laboratory", "Maharashtra"),
    ("central institute of mining and fuel", "Jharkhand"), ("indian institute of integrative medicine", "Jammu & Kashmir"),
    ("central institute of agricultural engineering", "Madhya Pradesh"), ("bhabha atomic", "Maharashtra"), ("homi bhabha national", "Maharashtra"),
    ("atomic minerals directorate", "Telangana"), ("saha institute of nuclear", "West Bengal"), ("s.n. bose", "West Bengal"),
    ("indian association for the cultivation", "West Bengal"), ("indian statistical institute", "West Bengal"), ("jawaharlal nehru centre", "Karnataka"),
    ("physical research laboratory", "Gujarat"), ("indian institute of tropical meteorology", "Maharashtra"), ("aryabhatta research", "Uttarakhand"),
    ("central power research", "Karnataka"), ("integrated test range", "Odisha"), ("food technology entrepreneurship", "Haryana"),
    ("rajiv gandhi institute of petroleum", "Uttar Pradesh"), ("institute of infrastructure technology research", "Gujarat"),
    ("motilal nehru", "Uttar Pradesh"), ("malaviya national", "Rajasthan"), ("visvesvaraya national", "Maharashtra"),
    ("sardar vallabhbhai national", "Gujarat"), ("dr. b. r. ambedkar national", "Punjab"), ("national institute of technology karnataka", "Karnataka"),
    ("national institute of technology andhra pradesh", "Andhra Pradesh"), ("national institute of technology delhi", "Delhi"),
    ("national institute of science and technology", "Odisha"), ("indian institute of technology bhu", "Uttar Pradesh"),
    ("indian institute of engineering science and technology", "West Bengal"), ("north eastern regional institute", "Arunachal Pradesh"),
    ("north eastern hill", "Meghalaya"), ("st. anthony's college", "Meghalaya"), ("central institute of technology kokrajhar", "Assam"),
    ("vellore institute of technology", "Tamil Nadu"), ("koneru lakshmaiah", "Andhra Pradesh"), ("kiit", "Odisha"), ("kalinga institute", "Odisha"),
    ("university of petroleum and energy studies", "Uttarakhand"), ("amrita vishwa", "Tamil Nadu"), ("manipal", "Karnataka"),
    ("chandigarh university", "Punjab"), ("thapar", "Punjab"), ("siksha o anusandhan", "Odisha"), ("rajiv gandhi technical university", "Madhya Pradesh"),
    ("rajiv gandhi proudyogiki", "Madhya Pradesh"), ("srm", "Tamil Nadu"), ("mesra", "Jharkhand"), ("gla university", "Uttar Pradesh"),
    ("lovely professional", "Punjab"), ("sr university", "Telangana"), ("graphic era", "Uttarakhand"), ("lnm institute", "Rajasthan"),
    ("parul university", "Gujarat"), ("banaras hindu", "Uttar Pradesh"), ("delhi technological", "Delhi"), ("barkatullah", "Madhya Pradesh"),
    ("siddaganga", "Karnataka"), ("reva university", "Karnataka"), ("bennett university", "Uttar Pradesh"), ("pilani", "Rajasthan"),
    ("birla institute of technology and science", "Rajasthan"), ("vel tech", "Tamil Nadu"), ("guru ghasidas", "Chhattisgarh"),
    ("aditya university", "Andhra Pradesh"), ("veer surendra sai", "Odisha"), ("bansal institute", "Madhya Pradesh"),
    ("pandit deendayal", "Gujarat"), ("psg ", "Tamil Nadu"), ("saveetha", "Tamil Nadu"), ("nirma university", "Gujarat"),
    ("gour mahavidyalaya", "West Bengal"), ("gmr institute", "Andhra Pradesh"), ("haldia", "West Bengal"), ("sant longowal", "Punjab"),
    ("bodoland", "Assam"), ("gitam", "Andhra Pradesh"), ("university of engineering & management", "West Bengal"), ("gurucharan", "Assam"),
    ("visvesvaraya technological", "Karnataka"), ("aligarh", "Uttar Pradesh"), ("chitkara", "Punjab"), ("jawaharlal nehru university", "Delhi"),
    ("galgotias", "Uttar Pradesh"), ("gandhi institute for technological advancement", "Odisha"), ("jain university", "Karnataka"),
    ("jaypee institute of information technology", "Uttar Pradesh"), ("rvs college", "Jharkhand"), ("shri govindram seksaria", "Madhya Pradesh"),
    ("st. joseph", "Tamil Nadu"), ("sathyabama", "Tamil Nadu"), ("netaji subhas", "Delhi"), ("karunya", "Tamil Nadu"),
    ("maulana abul kalam azad university", "West Bengal"), ("kaziranga", "Assam"), ("north bengal", "West Bengal"), ("centurion university", "Odisha"),
    ("brainware", "West Bengal"), ("banasthali", "Rajasthan"), ("madan mohan malaviya", "Uttar Pradesh"), ("sharda university", "Uttar Pradesh"),
    ("aisect", "Madhya Pradesh"), ("ips academy", "Madhya Pradesh"), ("atal bihari vajpayee", "Madhya Pradesh"), ("jecrc", "Rajasthan"),
    ("vignan", "Andhra Pradesh"), ("don bosco", "Assam"), ("down town university", "Assam"), ("gautam buddha", "Uttar Pradesh"),
    ("sri sivasubramaniya nadar", "Tamil Nadu"), ("alliance university", "Karnataka"), ("symbiosis", "Maharashtra"), ("dayananda sagar", "Karnataka"),
    ("gour banga", "West Bengal"), ("dharmsinh desai", "Gujarat"), ("jamia millia", "Delhi"), ("raisoni", "Maharashtra"), ("coer university", "Uttarakhand"),
    ("uttaranchal", "Uttarakhand"), ("panjab university", "Chandigarh"), ("narsee monjee", "Maharashtra"), ("anna university", "Tamil Nadu"),
    ("d.y. patil", "Maharashtra"), ("hindustan institute of technology", "Tamil Nadu"), ("siddhartha academy", "Andhra Pradesh"), ("jspm", "Maharashtra"),
    ("deenbandhu chhotu ram", "Haryana"), ("christ university", "Karnataka"), ("shiv nadar", "Uttar Pradesh"), ("techno india", "West Bengal"),
    ("bml munjal", "Haryana"), ("b.c. roy", "West Bengal"), ("rkdf", "Madhya Pradesh"), ("babasaheb bhimrao ambedkar university", "Uttar Pradesh"),
    ("babasaheb bhimrao ambedkar bihar", "Bihar"), ("sam higginbottom", "Uttar Pradesh"), ("integral university", "Uttar Pradesh"),
    ("giet university", "Odisha"), ("mohan babu", "Andhra Pradesh"), ("jis university", "West Bengal"), ("cmr university", "Karnataka"),
    ("thiagarajar", "Tamil Nadu"), ("devi ahilya", "Madhya Pradesh"), ("abdul kalam technical university", "Uttar Pradesh"),
    ("harcourt butler", "Uttar Pradesh"), ("punjabi university", "Punjab"), ("kr mangalam", "Haryana"), ("garhwal", "Uttarakhand"),
    ("nitte", "Karnataka"), ("ceramic technology", "West Bengal"), ("kolhan", "Jharkhand"), ("meghnad saha", "West Bengal"), ("burdwan", "West Bengal"),
    ("alipurduar", "West Bengal"), ("coep", "Maharashtra"), ("cotton university", "Assam"), ("karimganj", "Assam"), ("malla reddy", "Telangana"),
    ("royal global", "Assam"), ("career point", "Rajasthan"), ("jagran lakecity", "Madhya Pradesh"), ("poornima", "Rajasthan"),
    ("indira gandhi national tribal", "Madhya Pradesh"), ("kpr institute", "Tamil Nadu"), ("mit world peace", "Maharashtra"), ("vikram university", "Madhya Pradesh"),
    ("indira gandhi delhi", "Delhi"), ("chettinad", "Tamil Nadu"), ("kamla nehru institute", "Uttar Pradesh"), ("ramaiah", "Karnataka"),
    ("bidhannagar", "West Bengal"), ("adamas", "West Bengal"), ("rohilkhand", "Uttar Pradesh"), ("sam global", "Madhya Pradesh"), ("woxsen", "Telangana"),
    ("osmania", "Telangana"), ("gayatri vidya parishad", "Andhra Pradesh"), ("acharya nagarjuna", "Andhra Pradesh"), ("swami vivekananda university", "West Bengal"),
    ("glocal university", "Uttar Pradesh"), ("rajagiri", "Kerala"), ("shroff", "Gujarat"), ("chhatrapati shahu", "Uttar Pradesh"),
    ("institute of chemical technology", "Maharashtra"), ("marwadi", "Gujarat"), ("sastra", "Tamil Nadu"), ("apj abdul kalam technological", "Kerala"),
    ("bharath university", "Tamil Nadu"), ("icfai foundation", "Telangana"), ("mahindra university", "Telangana"), ("elitte college", "West Bengal"),
    ("tilka manjhi", "Bihar"), ("dehradun", "Uttarakhand"), ("noida", "Uttar Pradesh"), ("ghaziabad", "Uttar Pradesh"), ("gurugram", "Haryana"),
    ("gurgaon", "Haryana"), ("greater noida", "Uttar Pradesh"), ("lucknow", "Uttar Pradesh"), ("gorakhpur", "Uttar Pradesh"), ("azamgarh", "Uttar Pradesh"),
    ("kanpur", "Uttar Pradesh"), ("allahabad", "Uttar Pradesh"), ("prayagraj", "Uttar Pradesh"), ("varanasi", "Uttar Pradesh"),
    ("roorkee", "Uttarakhand"), ("guwahati", "Assam"), ("gauhati", "Assam"), ("silchar", "Assam"), ("jorhat", "Assam"), ("dibrugarh", "Assam"),
    ("tezpur", "Assam"), ("kokrajhar", "Assam"), ("assam", "Assam"), ("kharagpur", "West Bengal"), ("durgapur", "West Bengal"), ("jadavpur", "West Bengal"),
    ("kolkata", "West Bengal"), ("calcutta", "West Bengal"), ("shibpur", "West Bengal"), ("kalyani", "West Bengal"), ("howrah", "West Bengal"),
    ("west bengal", "West Bengal"), ("bengal", "West Bengal"), ("dhanbad", "Jharkhand"), ("ranchi", "Jharkhand"), ("jamshedpur", "Jharkhand"),
    ("jharkhand", "Jharkhand"), ("rourkela", "Odisha"), ("bhubaneswar", "Odisha"), ("kalahandi", "Odisha"), ("berhampur", "Odisha"), ("odisha", "Odisha"),
    ("orissa", "Odisha"), ("raipur", "Chhattisgarh"), ("bhilai", "Chhattisgarh"), ("chhattisgarh", "Chhattisgarh"), ("bilaspur", "Chhattisgarh"),
    ("bhopal", "Madhya Pradesh"), ("indore", "Madhya Pradesh"), ("jabalpur", "Madhya Pradesh"), ("gwalior", "Madhya Pradesh"), ("ujjain", "Madhya Pradesh"),
    ("sagar", "Madhya Pradesh"), ("madhya pradesh", "Madhya Pradesh"), ("patna", "Bihar"), ("bhagalpur", "Bihar"), ("bihar", "Bihar"),
    ("agartala", "Tripura"), ("tripura", "Tripura"), ("manipur", "Manipur"), ("imphal", "Manipur"), ("meghalaya", "Meghalaya"), ("shillong", "Meghalaya"),
    ("mizoram", "Mizoram"), ("aizawl", "Mizoram"), ("nagaland", "Nagaland"), ("arunachal", "Arunachal Pradesh"), ("sikkim", "Sikkim"),
    ("delhi", "Delhi"), ("jaipur", "Rajasthan"), ("jodhpur", "Rajasthan"), ("ajmer", "Rajasthan"), ("rajasthan", "Rajasthan"), ("kota", "Rajasthan"),
    ("jalandhar", "Punjab"), ("ropar", "Punjab"), ("patiala", "Punjab"), ("punjab", "Punjab"), ("chandigarh", "Chandigarh"), ("kurukshetra", "Haryana"),
    ("haryana", "Haryana"), ("hamirpur", "Himachal Pradesh"), ("mandi", "Himachal Pradesh"), ("himachal", "Himachal Pradesh"), ("srinagar", "Jammu & Kashmir"),
    ("jammu", "Jammu & Kashmir"), ("kashmir", "Jammu & Kashmir"), ("uttarakhand", "Uttarakhand"), ("uttar pradesh", "Uttar Pradesh"),
    ("bombay", "Maharashtra"), ("mumbai", "Maharashtra"), ("pune", "Maharashtra"), ("nagpur", "Maharashtra"), ("maharashtra", "Maharashtra"),
    ("goa", "Goa"), ("surat", "Gujarat"), ("gandhinagar", "Gujarat"), ("ahmedabad", "Gujarat"), ("vadodara", "Gujarat"), ("baroda", "Gujarat"),
    ("gujarat", "Gujarat"), ("madras", "Tamil Nadu"), ("chennai", "Tamil Nadu"), ("tiruchirappalli", "Tamil Nadu"), ("trichy", "Tamil Nadu"),
    ("coimbatore", "Tamil Nadu"), ("madurai", "Tamil Nadu"), ("kancheepuram", "Tamil Nadu"), ("tamil nadu", "Tamil Nadu"), ("bangalore", "Karnataka"),
    ("bengaluru", "Karnataka"), ("mysore", "Karnataka"), ("surathkal", "Karnataka"), ("karnataka", "Karnataka"), ("calicut", "Kerala"), ("kozhikode", "Kerala"),
    ("palakkad", "Kerala"), ("thiruvananthapuram", "Kerala"), ("kerala", "Kerala"), ("hyderabad", "Telangana"), ("warangal", "Telangana"),
    ("telangana", "Telangana"), ("tirupati", "Andhra Pradesh"), ("visakhapatnam", "Andhra Pradesh"), ("andhra pradesh", "Andhra Pradesh"),
    ("puducherry", "Puducherry"), ("pondicherry", "Puducherry"),
    ("all india institute of medical sciences", "Delhi"), ("indian institute of science", "Karnataka"),
]
REGION = {"Madhya Pradesh": "Central", "Chhattisgarh": "Central",
          "Jharkhand": "East", "West Bengal": "East", "Odisha": "East", "Bihar": "East",
          "Assam": "North-East", "Mizoram": "North-East", "Meghalaya": "North-East", "Manipur": "North-East", "Tripura": "North-East",
          "Nagaland": "North-East", "Arunachal Pradesh": "North-East", "Sikkim": "North-East",
          "Delhi": "North", "Uttar Pradesh": "North", "Uttarakhand": "North", "Punjab": "North", "Haryana": "North", "Chandigarh": "North",
          "Himachal Pradesh": "North", "Jammu & Kashmir": "North", "Rajasthan": "North",
          "Maharashtra": "West", "Gujarat": "West", "Goa": "West",
          "Karnataka": "South", "Tamil Nadu": "South", "Kerala": "South", "Telangana": "South", "Andhra Pradesh": "South", "Puducherry": "South"}


INDIAN_CLUSTERS = {"IIT", "NIT", "IIIT", "IISER", "IISc", "CSIR", "DAE", "DRDO", "ICAR", "ISRO", "ICMR"}


def state_of(name):
    n = (name or "").lower()
    if any(k in n for k in NATIONAL) and not any(k in n for k in ("government of west bengal", "government of uttar pradesh")):
        return "National (multi-site)"
    for k, s in STATE_KEYS:
        if k in n:
            return s
    return "Unknown"


def locality(our, state):
    if state in ("Unknown", "National (multi-site)"):
        return "National body" if state != "Unknown" else "Unknown"
    if state == HOME[our]:
        return "Same state"
    if REGION.get(state) == REGION[HOME[our]]:
        return "Same region"
    return "Other region"


def main():
    g15 = rd(OUT / "group15_data.csv")
    paper_insts, paper_year, paper_cites, doi_of = defaultdict(set), {}, {}, {}
    fac_of_paper = defaultdict(set)
    for r in g15:
        w = r["openalex_work_id"]
        paper_insts[w].add(r["institution"])
        paper_year[w] = int(r["year"])
        paper_cites[w] = int(r["citations"] or 0)
        doi_of[w] = r["doi"]
        fac_of_paper[w].add((r["institution"], r["faculty_name"]))
    title_of = {r["openalex_work_id"]: r["title"] for r in g15}

    # partner institutes per paper, from every co-author's affiliations
    ptype = {}
    fcountry = {}
    partners_of = defaultdict(set)          # work -> Indian partner names
    foreign_of = defaultdict(set)           # work -> foreign institution names
    for a in rd(OUT / "all_authors" / "authorships.csv"):      # complete co-author list (data/out/authorships.csv misses partner affiliations on many papers)
        w = a["openalex_work_id"]
        if w not in paper_insts:
            continue
        for part in filter(None, a["institutions_detail"].split(";")):
            bits = part.split("|")
            if len(bits) < 3:
                continue
            name, cc, typ = bits[0].strip(), bits[1].strip(), bits[2].strip()
            if name.lower() in OUR_NAMES:
                continue
            ptype.setdefault(name, typ)
            if not cc:  # OpenAlex sometimes has no country: Indian if the name maps to an Indian place
                cc = "IN" if state_of(name) not in ("Unknown",) else ""
            if cluster_of(name, typ) in INDIAN_CLUSTERS:  # fixes wrong codes, e.g. NIT Hamirpur listed as BD
                cc = "IN"
            if cc == "IN":
                partners_of[w].add(name)
            elif cc:
                foreign_of[w].add(name)
                fcountry.setdefault(name, cc)

    # ------------------------------------------------------------ partner table
    ic = {(r["your_inst"], r["partner_inst"]): r for r in rd(OUT / "indian_connections.csv")}
    # exact partner type (parent organisation lookup), citations both ways and topic similarity (partners.py)
    det_path = OUT / "indian_connections_detailed.csv"
    det = {(r["your_inst"], r["partner_inst"]): r for r in rd(det_path)} if det_path.exists() else {}
    exact_of = {}
    for (i, pn), r in det.items():
        exact_of.setdefault(pn, r.get("partner_cluster", ""))
    old = json.loads((ST / "partner_results.json").read_text(encoding="utf-8"))
    jac = {}
    for (i, pn), r in det.items():
        if r.get("weighted_jaccard"):
            jac[(i, pn)] = (r.get("jaccard_subfields"), r["weighted_jaccard"])
    for i in INSTS:
        for key in ("top_partners", "most_similar_partners", "least_similar_partners"):
            for q in old.get(i, {}).get(key, []):
                if q.get("weighted_jaccard") is not None:
                    jac.setdefault((i, q["partner_inst"]), (q.get("jaccard_subfields"), q["weighted_jaccard"]))

    SPECIFIC = {"IIT", "NIT", "IIIT", "IISER", "IISc", "CSIR", "DAE", "DRDO", "ICAR", "ISRO", "ICMR", "Premier science inst."}

    def final_cluster(name):
        mine = cluster_of(name, ptype.get(name, ""))
        exact = exact_of.get(name, "")
        if mine == "IISc":
            return "IISc"
        if exact in SPECIFIC:
            return exact
        if mine in SPECIFIC:
            return mine
        if exact == "University/college" or not exact:
            return mine
        return exact
    links = defaultdict(lambda: {"papers": set(), "years": Counter(), "faculty": Counter(), "cites": 0})
    for w, ps in partners_of.items():
        for i in paper_insts[w]:
            for p in ps:
                L = links[(i, p)]
                if w not in L["papers"]:
                    L["papers"].add(w)
                    L["years"][paper_year[w]] += 1
                    L["cites"] += paper_cites[w]
                for inst, fname in fac_of_paper[w]:
                    if inst == i:
                        L["faculty"][fname] += 1
    rows = []
    for (i, p), L in links.items():
        st = state_of(p)
        j = jac.get((i, p), (None, None))
        rows.append({"your_inst": i, "partner_inst": p, "shared_papers": len(L["papers"]), "total_citations": L["cites"],
                     "shared_papers_indian_connections_csv": ic.get((i, p), {}).get("shared_papers", ""),
                     "partner_type": ptype.get(p, ""), "partner_cluster": final_cluster(p), "state": st,
                     "region": REGION.get(st, st), "locality": locality(i, st), "first_year": min(L["years"]), "last_year": max(L["years"]),
                     "faculty_involved": len(L["faculty"]),
                     "top_faculty": "; ".join(f"{n} ({c})" for n, c in L["faculty"].most_common(3)),
                     "jaccard_subfields": j[0] if j[0] is not None else "", "weighted_jaccard": j[1] if j[1] is not None else "",
                     "cites_from_partner": det.get((i, p), {}).get("cites_from_partner", ""),
                     "cites_to_partner": det.get((i, p), {}).get("cites_to_partner", ""),
                     **{f"y{y}": L["years"].get(y, 0) for y in range(2016, 2027)}})
    rows.sort(key=lambda r: (r["your_inst"], -r["shared_papers"]))
    wr("partners_locality.csv", rows)
    fp = []
    for (i, p), L in links.items():
        for fname, c in L["faculty"].items():
            st = state_of(p)
            fp.append({"institution": i, "faculty_name": fname, "partner_inst": p, "joint_papers": c,
                       "partner_cluster": final_cluster(p), "locality": locality(i, st)})
    fp.sort(key=lambda r: (r["institution"], r["faculty_name"], -r["joint_papers"]))
    wr("faculty_partners.csv", fp)
    # foreign partners per institute (institute network)
    fl = defaultdict(set)
    for w, ps in foreign_of.items():
        for i in paper_insts[w]:
            for q in ps:
                fl[(i, q)].add(w)
    wr("foreign_partners.csv", sorted(({"your_inst": i, "partner_inst": q, "country": fcountry.get(q, ""), "shared_papers": len(ws),
                                        "total_citations": sum(paper_cites[w] for w in ws)} for (i, q), ws in fl.items()),
                                      key=lambda r: (r["your_inst"], -r["shared_papers"])))
    wr("foreign_partner_papers.csv", [{"your_inst": i, "partner_inst": q, "openalex_work_id": w} for (i, q), ws in fl.items() for w in sorted(ws)])
    wr("partner_papers.csv", [{"your_inst": i, "partner_inst": p, "openalex_work_id": w} for (i, p), L in links.items() for w in sorted(L["papers"])])
    match = sum(1 for r in rows if str(r["shared_papers"]) == str(r["shared_papers_indian_connections_csv"]))

    res = {"home_state": HOME, "partners_rebuilt_match_indian_connections_%": round(100 * match / max(1, len(rows)), 1)}

    # summaries by cluster and by locality
    def summarise(key):
        out = []
        for i in INSTS:
            rs = [r for r in rows if r["your_inst"] == i]
            tot_links = sum(r["shared_papers"] for r in rs)
            uniq = {w for (ii, p), L in links.items() if ii == i for w in L["papers"]}
            for k in sorted({r[key] for r in rs}):
                sub = [r for r in rs if r[key] == k]
                papers_k = {w for r in sub for w in links[(i, r["partner_inst"])]["papers"]}
                out.append({"your_inst": i, key: k, "partners": len(sub), "partner_links": sum(r["shared_papers"] for r in sub),
                            "share_of_links_%": round(100 * sum(r["shared_papers"] for r in sub) / tot_links, 1),
                            "distinct_papers": len(papers_k), "share_of_papers_with_indian_partner_%": round(100 * len(papers_k) / len(uniq), 1),
                            "top_partners": "; ".join(f"{r['partner_inst']} ({r['shared_papers']})" for r in sorted(sub, key=lambda r: -r["shared_papers"])[:4])})
        return out
    by_cluster, by_loc = summarise("partner_cluster"), summarise("locality")
    wr("by_cluster.csv", by_cluster)
    wr("by_locality.csv", by_loc)
    by_region = summarise("region")
    wr("by_region.csv", by_region)
    res["by_cluster"], res["by_locality"], res["by_region"] = by_cluster, by_loc, by_region
    mapped = sum(r["shared_papers"] for r in rows if r["state"] != "Unknown")
    res["state_mapping_coverage_%_of_links"] = round(100 * mapped / sum(r["shared_papers"] for r in rows), 1)

    # collaboration reach of each institute's papers
    reach = []
    for i in INSTS:
        ws = [w for w in paper_insts if i in paper_insts[w]]
        ind = sum(1 for w in ws if partners_of[w])
        fr = sum(1 for w in ws if foreign_of[w])
        ours = sum(1 for w in ws if len(paper_insts[w]) > 1)
        alone = sum(1 for w in ws if not partners_of[w] and not foreign_of[w] and len(paper_insts[w]) == 1)
        reach.append({"institution": i, "papers": len(ws), "with_other_indian_inst_%": round(100 * ind / len(ws), 1),
                      "with_foreign_inst_%": round(100 * fr / len(ws), 1), "with_our_other_two_%": round(100 * ours / len(ws), 1),
                      "own_institute_only_%": round(100 * alone / len(ws), 1),
                      "distinct_indian_partners": len({p for w in ws for p in partners_of[w]}),
                      "distinct_foreign_partners": len({p for w in ws for p in foreign_of[w]})})
    wr("collaboration_reach.csv", reach)
    res["collaboration_reach"] = reach

    # trend by cluster
    trend = []
    for i in INSTS:
        for y in range(2016, 2027):
            c = Counter()
            for (ii, p), L in links.items():
                if ii == i:
                    c[cluster_of(p, ptype.get(p, ""))] += L["years"].get(y, 0)
            for k, v in c.items():
                trend.append({"your_inst": i, "year": y, "partner_cluster": k, "partner_links": v})
    wr("trend_by_cluster.csv", trend)

    # ------------------------------------------------------------ 3. peer institutes
    PEER = {"NIT", "IIT", "IIIT", "IISER", "IISc"}
    peers = [r for r in rows if r["partner_cluster"] in PEER]
    wr("peer_institutes.csv", peers)
    res["peer_institutes"] = {i: {cl: {"partners": sum(1 for r in peers if r["your_inst"] == i and r["partner_cluster"] == cl),
                                       "partner_links": sum(r["shared_papers"] for r in peers if r["your_inst"] == i and r["partner_cluster"] == cl),
                                       "top": [(r["partner_inst"], r["shared_papers"], r["locality"]) for r in peers if r["your_inst"] == i and r["partner_cluster"] == cl][:5]}
                                  for cl in ["NIT", "IIT", "IIIT", "IISER", "IISc"]} for i in INSTS}
    # between our own three
    between = Counter()
    for w, s in paper_insts.items():
        if len(s) > 1:
            for a in s:
                for b in s:
                    if a < b:
                        between[(a, b)] += 1
    fe = rd(OUT / "faculty_network_edges.csv")
    cross_fac = [e for e in fe if e["inst_a"] != e["inst_b"]]
    res["between_our_institutes"] = {"joint_papers": {f"{a} & {b}": n for (a, b), n in between.items()},
                                     "papers_with_all_three": sum(1 for s in paper_insts.values() if len(s) == 3),
                                     "faculty_links": len(cross_fac),
                                     "faculty_pairs": sorted(({"a": e["faculty_a"], "inst_a": e["inst_a"], "b": e["faculty_b"], "inst_b": e["inst_b"],
                                                               "joint_papers": int(e["joint_papers"])} for e in cross_fac), key=lambda x: -x["joint_papers"])}

    # ------------------------------------------------------------ 4. within vs outside: faculty
    alias = movers.aliases()
    fmap = {r["author_id"]: alias.get((r["institution"], r["faculty_name"]), (r["institution"], r["faculty_name"])) for r in rd(OUT / "author_faculty_map.csv")}
    # students, scholars and staff of our own institutes are not faculty and not "outside" either: the analysis is faculty-only, so they are left out
    with open(OUT / "all_authors" / "authorships.csv", encoding="utf-8") as fh:
        own_nonfaculty = {r["author_id"] for r in csv.DictReader(fh) if r["is_our_inst"] == "True" and r["author_id"] not in fmap}
    nodes = {(r["institution"], r["faculty_name"]): r for r in rd(OUT / "faculty_network_nodes.csv")}
    E = rd(OUT / "authorship_network_ids.csv")
    G = nx.Graph()
    node_info = {}
    for e in E:
        for idk, nm, inst, cc in (("id_a", "author_a", "inst_a", "cc_a"), ("id_b", "author_b", "inst_b", "cc_b")):
            node_info.setdefault(e[idk], (e[nm], e[inst], e[cc]))
        a, b = e["id_a"], e["id_b"]
        if a == b:
            continue
        G.add_edge(a, b, weight=G[a][b]["weight"] + 1 if G.has_edge(a, b) else 1)
    # merge faculty IDs into one node per person
    mapping = {n: f"F::{fmap[n][0]}::{fmap[n][1]}" for n in G if n in fmap}
    G = nx.relabel_nodes(G, mapping, copy=True)
    G.remove_edges_from(nx.selfloop_edges(G))
    G.remove_nodes_from([n for n in own_nonfaculty if n in G])

    def kind(n):
        if n.startswith("F::"):
            return "faculty:" + n.split("::")[1]
        name, inst, cc = node_info.get(n, ("", "", ""))
        if not inst:
            return "unknown"
        if not cc:
            return "indian" if state_of(inst) != "Unknown" else "unknown"
        if cluster_of(inst, "") in INDIAN_CLUSTERS:
            return "indian"
        return "indian" if cc == "IN" else "foreign"

    scope = defaultdict(Counter)
    for n in G:
        if not n.startswith("F::"):
            continue
        my = n.split("::")[1]
        for m in G[n]:
            k = kind(m)
            if k == "faculty:" + my:
                scope[n]["same_institute"] += 1
            elif k.startswith("faculty:"):
                scope[n]["our_other_two"] += 1
            else:
                scope[n][k] += 1
    bc = nx.betweenness_centrality(G, k=min(1500, G.number_of_nodes()), seed=7, normalized=True)
    lcc = max(nx.connected_components(G), key=len)
    louv = nxc.louvain_communities(G, seed=7, weight="weight")
    res["full_author_network"] = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
                                  "faculty_nodes": sum(1 for n in G if n.startswith("F::")),
                                  "other_indian_nodes": sum(1 for n in G if kind(n) == "indian"),
                                  "foreign_nodes": sum(1 for n in G if kind(n) == "foreign"),
                                  "unknown_affiliation_nodes": sum(1 for n in G if kind(n) == "unknown"),
                                  "largest_component_%": round(100 * len(lcc) / G.number_of_nodes(), 1),
                                  "louvain_communities": len(louv),
                                  "louvain_modularity": round(nxc.modularity(G, louv, weight="weight"), 3),
                                  "betweenness": "approximate, 1500 sampled sources"}
    fac_rows = []
    for n in G:
        if not n.startswith("F::"):
            continue
        _, inst, name = n.split("::", 2)
        s = scope[n]
        outside = s["our_other_two"] + s["indian"] + s["foreign"]
        nd = nodes.get((inst, name), {})
        fac_rows.append({"institution": inst, "faculty_name": name, "department": nd.get("department", ""),
                         "coauthors_total": G.degree(n), "coauthors_same_institute": s["same_institute"],
                         "coauthors_our_other_two": s["our_other_two"], "coauthors_other_indian": s["indian"],
                         "coauthors_foreign": s["foreign"], "coauthors_unknown": s["unknown"], "coauthors_outside_institute": outside,
                         "outside_share_%": round(100 * outside / max(1, outside + s["same_institute"]), 1),
                         "betweenness_full_network": round(bc.get(n, 0), 5),
                         "betweenness_faculty_network": nd.get("betweenness", "")})
    fac_rows.sort(key=lambda r: (r["institution"], -r["coauthors_outside_institute"]))
    wr("faculty_within_outside.csv", fac_rows)
    top = {}
    for i in INSTS:
        fr = [r for r in fac_rows if r["institution"] == i]
        top[i] = {"within": sorted(fr, key=lambda r: -r["coauthors_same_institute"])[:10],
                  "outside": sorted(fr, key=lambda r: -r["coauthors_outside_institute"])[:10],
                  "full_network_betweenness": sorted(fr, key=lambda r: -r["betweenness_full_network"])[:10]}
    res["top_faculty_within_vs_outside"] = top
    # correlation between inward and outward collaboration
    def spearman(x, y):
        def rank(v):
            o = sorted(range(len(v)), key=lambda k: v[k]); r = [0] * len(v); k = 0
            while k < len(o):
                j = k
                while j + 1 < len(o) and v[o[j + 1]] == v[o[k]]:
                    j += 1
                for t in range(k, j + 1):
                    r[o[t]] = (k + j) / 2
                k = j + 1
            return r
        rx, ry = rank(x), rank(y); n = len(x); mx, my = sum(rx) / n, sum(ry) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry)); vx = sum((a - mx) ** 2 for a in rx); vy = sum((b - my) ** 2 for b in ry)
        return round(cov / (vx * vy) ** .5, 3) if vx and vy else None
    res["within_vs_outside_spearman"] = {i: spearman([r["coauthors_same_institute"] for r in fac_rows if r["institution"] == i],
                                                     [r["coauthors_outside_institute"] for r in fac_rows if r["institution"] == i]) for i in INSTS}

    # top outside nodes: external authors connected to the most of our faculty
    ext = []
    for n in G:
        if n.startswith("F::"):
            continue
        fs = [m for m in G[n] if m.startswith("F::")]
        if len(fs) < 2:
            continue
        name, inst, cc = node_info.get(n, ("", "", ""))
        ext.append({"author": name, "institution": inst or "(no affiliation)", "country": cc, "faculty_connected": len(fs),
                    "our_institutes": "; ".join(sorted({m.split("::")[1] for m in fs})), "coauthors_total": G.degree(n),
                    "betweenness_full_network": round(bc.get(n, 0), 5),
                    "faculty": "; ".join(sorted(m.split("::")[2] for m in fs)[:6])})
    ext.sort(key=lambda r: (-r["faculty_connected"], -r["betweenness_full_network"]))
    wr("top_external_authors.csv", ext[:200])
    res["top_external_authors"] = ext[:20]

    # institute-level co-authorship network: our institutes + every institution on our papers
    IG = nx.Graph()
    for w in paper_insts:
        members = set(paper_insts[w]) | partners_of[w] | foreign_of[w]
        members = list(members)
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                a, b = members[x], members[y]
                IG.add_edge(a, b, weight=IG[a][b]["weight"] + 1 if IG.has_edge(a, b) else 1)
    ibc = nx.betweenness_centrality(IG, k=min(1000, IG.number_of_nodes()), seed=7)
    inst_rows = []
    for n in IG:
        if n in INSTS:
            continue
        inst_rows.append({"institution": n, "country": "IN" if any(n in partners_of[w] for w in list(partners_of)[:0]) else "",
                          "type": ptype.get(n, ""), "cluster": cluster_of(n, ptype.get(n, "")),
                          "papers_with_us": sum(IG[n][o]["weight"] for o in INSTS if IG.has_edge(n, o)),
                          "linked_to": "; ".join(o for o in INSTS if IG.has_edge(n, o)),
                          "degree": IG.degree(n), "strength": IG.degree(n, weight="weight"), "betweenness": round(ibc.get(n, 0), 5)})
    indian = {p for s in partners_of.values() for p in s}
    for r in inst_rows:
        r["country"] = "IN" if r["institution"] in indian else "abroad"
        r["state"] = state_of(r["institution"]) if r["country"] == "IN" else ""
    inst_rows.sort(key=lambda r: -r["papers_with_us"])
    wr("institute_network_nodes.csv", inst_rows)
    res["institute_network"] = {"nodes": IG.number_of_nodes(), "edges": IG.number_of_edges(),
                                "our_institutes": {i: {"degree": IG.degree(i), "strength": IG.degree(i, weight="weight"),
                                                       "betweenness_rank": sorted(ibc, key=ibc.get, reverse=True).index(i) + 1} for i in INSTS},
                                "top_indian_by_papers": [r for r in inst_rows if r["country"] == "IN"][:15],
                                "top_foreign_by_papers": [r for r in inst_rows if r["country"] != "IN"][:10],
                                "top_by_betweenness": sorted(inst_rows, key=lambda r: -r["betweenness"])[:10]}

    # ------------------------------------------------------------ 4b. within vs outside: papers (citations)
    cn = rd(OUT / "citation_network.csv")
    wid_of_doi = {d.lower(): w for w, d in doi_of.items() if d}
    same, other = Counter(), Counter()
    for e in cn:
        t = wid_of_doi.get(e["target_doi"].lower())
        if not t:
            continue
        if e["source_inst"] == e["target_inst"]:
            same[t] += 1
        else:
            other[t] += 1
    prow = []
    for w in paper_insts:
        c = paper_cites[w]
        prow.append({"institution": "; ".join(sorted(paper_insts[w])), "title": title_of[w], "year": paper_year[w], "doi": doi_of[w],
                     "citations_total": c, "cited_by_same_institute": same[w], "cited_by_our_other_two": other[w],
                     "cited_from_outside_corpus": max(0, c - same[w] - other[w]),
                     "outside_share_%": round(100 * max(0, c - same[w] - other[w]) / c, 1) if c else ""})
    wr("paper_within_outside.csv", sorted(prow, key=lambda r: -r["citations_total"]))
    res["top_papers_within_vs_outside"] = {i: {"within": sorted([r for r in prow if i in r["institution"]], key=lambda r: -r["cited_by_same_institute"])[:10],
                                               "outside": sorted([r for r in prow if i in r["institution"]], key=lambda r: -r["cited_from_outside_corpus"])[:10]}
                                           for i in INSTS}
    tot = {i: [r for r in prow if i in r["institution"]] for i in INSTS}
    res["citation_origin"] = {i: {"citations": sum(r["citations_total"] for r in tot[i]),
                                  "from_same_institute_%": round(100 * sum(r["cited_by_same_institute"] for r in tot[i]) / sum(r["citations_total"] for r in tot[i]), 2),
                                  "from_our_other_two_%": round(100 * sum(r["cited_by_our_other_two"] for r in tot[i]) / sum(r["citations_total"] for r in tot[i]), 2)}
                              for i in INSTS}

    (ST / "locality_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print("partners rebuilt:", len(rows), "| match indian_connections.csv:", res["partners_rebuilt_match_indian_connections_%"], "%",
          "| state coverage:", res["state_mapping_coverage_%_of_links"], "%")
    print("full author network:", res["full_author_network"])
    for r in by_loc:
        print(r["your_inst"], r["locality"], r["partner_links"], r["share_of_links_%"])
    print("reach:", reach)


if __name__ == "__main__":
    main()
