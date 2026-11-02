"""Report figures R5-R16: static versions of the dashboard panels that had no figure yet.
Run after report_figures.py (it reuses its style):  python report/report_figures_extra.py
"""
import json
import math
from collections import Counter, defaultdict

import matplotlib.patheffects as pe_
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

from report_figures import CAT, COL, FIG, GRID, INK, INK2, INSTS, OTHER, OUT, ST, SURF, rd

LOCD = ST / "locality"
SHORT = {"MANIT Bhopal": "MANIT", "NIT Jamshedpur": "NITJ", "NIT Silchar": "NITS"}
QCOL = {"Q1": "#104281", "Q2": "#2a78d6", "Q3": "#6da7ec", "Q4": "#b7d3f6"}


def ab(s):
    return (s.replace("Indian Institute of Technology", "IIT").replace("National Institute of Technology", "NIT")
            .replace("Indian Institute of Information Technology", "IIIT").replace(" University", " Univ."))


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.png", dpi=150)
    plt.close(fig)
    print("saved", name)


def halo(w=2.5):
    return [pe_.withStroke(linewidth=w, foreground=SURF)]


papers = {}
for r in rd(OUT / "group15_data.csv"):
    p = papers.setdefault(r["openalex_work_id"], {**r, "insts": set()})
    p["insts"].add(r["institution"])
P = list(papers.values())

# R5 conference papers by venue rank -------------------------------------------------------------
CR = [("CORE B", lambda q: q == "B", "#eda100"), ("CORE C", lambda q: q == "C", "#e87ba4"),
      ("Scopus Q1", lambda q: q == "Q1", QCOL["Q1"]), ("Scopus Q2", lambda q: q == "Q2", QCOL["Q2"]),
      ("Scopus Q3", lambda q: q == "Q3", QCOL["Q3"]), ("Scopus Q4", lambda q: q == "Q4", QCOL["Q4"]),
      ("Not ranked", lambda q: q not in ("B", "C", "A", "A*", "Q1", "Q2", "Q3", "Q4"), OTHER)]
fig, ax = plt.subplots(figsize=(10, 3.4))
for k, i in enumerate(INSTS):
    cs = [p for p in P if i in p["insts"] and p["type"] == "conference"]
    left = 0
    for n, f, c in CR:
        v = 100 * sum(f(p["quartile"]) for p in cs) / len(cs)
        ax.barh(k, v, left=left, color=c, edgecolor=SURF, linewidth=1.2, label=n if k == 0 else None)
        if v >= 6:
            ax.text(left + v / 2, k, f"{v:.0f}%", ha="center", va="center", fontsize=8.5,
                    color="white" if n in ("Scopus Q1", "Scopus Q2") else INK)
        left += v
ax.set_yticks(range(3), [f"{SHORT[i]}\n({sum(1 for p in P if i in p['insts'] and p['type'] == 'conference'):,} papers)" for i in INSTS])
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.set_xlabel("share of the institute's conference papers (%)")
ax.legend(ncol=7, loc="upper center", bbox_to_anchor=(.5, -.3), fontsize=8.5)
ax.set_title("Conference papers by venue rank\n(CORE 2023 rank where listed, otherwise the Scopus quartile of the proceedings)")
save(fig, "R5_conference_rank")

# R6 top 5 journals per institute -----------------------------------------------------------------
fig, axs = plt.subplots(1, 3, figsize=(14, 3.8))
for ax, i in zip(axs, INSTS):
    js = rd(ST / f"top_journals_{i.replace(' ', '_')}.csv")[:5][::-1]
    ax.barh([j["journal_name"][:42] for j in js], [int(j["papers"]) for j in js],
            color=[QCOL.get(j["quartile"], OTHER) for j in js], edgecolor=SURF)
    for y, j in enumerate(js):
        ax.text(int(j["papers"]) + .5, y, f"{j['papers']} · {j['quartile']}", va="center", fontsize=8.5, color=INK2)
    ax.set_title(i)
    ax.set_xlabel("papers")
    ax.tick_params(axis="y", labelsize=8.5)
    ax.set_xlim(0, max(int(j["papers"]) for j in js) * 1.3)
fig.suptitle("Top 5 journals per institute (bar colour = SCImago quartile, darker = higher)", x=.01, ha="left", fontweight="bold")
save(fig, "R6_top_journals")

# R7 in-degree distribution -----------------------------------------------------------------------
cm = rd(ST / "citation_node_metrics.csv")
fig, ax = plt.subplots(figsize=(7, 4.2))
for i in INSTS:
    c = Counter(int(r["in_degree"]) for r in cm if i in r["institutes"] and int(r["in_degree"]) > 0)
    xs = sorted(c)
    ax.scatter(xs, [c[x] for x in xs], s=22, color=COL[i], label=i, alpha=.85, edgecolor=SURF, linewidth=.5)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("in-degree: times a paper is cited by other corpus papers (log)")
ax.set_ylabel("number of papers (log)")
ax.legend()
ax.set_title("In-degree distribution of the citation network")
save(fig, "R7_in_degree")

# R8 PageRank top 10 ------------------------------------------------------------------------------
net = json.loads((ST / "network_results.json").read_text(encoding="utf-8"))["citation_network"]
t10 = net["top10_pagerank"][::-1]
fig, ax = plt.subplots(figsize=(11, 4.6))
ax.barh([f"{t['title'][:70]}{'…' if len(t['title']) > 70 else ''} ({t['year']})" for t in t10],
        [t["pagerank"] for t in t10], color=[COL[t["inst"]] for t in t10], edgecolor=SURF)
for y, t in enumerate(t10):
    ax.text(t["pagerank"], y, f"  in-degree {t['in_degree_in_corpus']} · {t['citations_openalex']} cites", va="center", fontsize=8, color=INK2)
ax.set_xlim(0, max(t["pagerank"] for t in t10) * 1.45)
ax.tick_params(axis="y", labelsize=8)
ax.set_xlabel("PageRank in the citation network (damping 0.85)")
ax.legend(handles=[Line2D([], [], marker="s", ls="", color=COL[i], label=i) for i in INSTS], loc="lower right", fontsize=8.5)
ax.set_title("Top 10 papers by PageRank")
save(fig, "R8_pagerank_top10")

# R9 institute collaboration network --------------------------------------------------------------
pl = rd(LOCD / "partners_locality.csv")
TYPES = ["IIT", "NIT", "IIIT", "Central university", "Other university/college", "CSIR", "DAE", "Industry"]
TCOL = dict(zip(TYPES, CAT))
agg = defaultdict(lambda: {"w": Counter(), "cl": ""})
for r in pl:
    a = agg[r["partner_inst"]]
    a["w"][r["your_inst"]] += int(r["shared_papers"])
    a["cl"] = r["partner_cluster"]
MIN = 12
parts = {n: a for n, a in agg.items() if sum(a["w"].values()) >= MIN}
G = nx.Graph()
G.add_nodes_from(INSTS)
for n, a in parts.items():
    for i, w in a["w"].items():
        G.add_edge(i, n, weight=w)
loc = json.loads((ST / "locality_results.json").read_text(encoding="utf-8"))
J = loc["between_our_institutes"]["joint_papers"]
fixed = {INSTS[0]: (0, 1), INSTS[1]: (-.95, -.6), INSTS[2]: (.95, -.6)}
pos = nx.spring_layout(G, pos=fixed, fixed=INSTS, seed=4, k=.18, iterations=300, weight="weight")
fig, ax = plt.subplots(figsize=(12, 10.5))
ax.axis("off")
for u, v, d in G.edges(data=True):
    i = u if u in INSTS else v
    ax.plot(*zip(pos[u], pos[v]), color=COL[i], alpha=.22, lw=.4 + math.sqrt(d["weight"]) * .35, zorder=1)
for a, b in [(0, 1), (0, 2), (1, 2)]:
    w = J.get(f"{INSTS[a]} & {INSTS[b]}", 0)
    ax.plot(*zip(pos[INSTS[a]], pos[INSTS[b]]), color="#6250d6", ls="--", lw=1.5 + math.sqrt(w) * .5, zorder=2)
    mx, my = (pos[INSTS[a]][0] + pos[INSTS[b]][0]) / 2, (pos[INSTS[a]][1] + pos[INSTS[b]][1]) / 2
    ax.text(mx, my, f"{w} joint papers", color="#6250d6", fontsize=9, ha="center", fontweight="bold", path_effects=halo(3), zorder=6)
for n, a in parts.items():
    ax.scatter(*pos[n], s=12 + sum(a["w"].values()) * 2.2, color=TCOL.get(a["cl"], OTHER), edgecolor=SURF, linewidth=.6, zorder=3)
for i in INSTS:
    ax.scatter(*pos[i], s=1500, color=COL[i], edgecolor=SURF, linewidth=2, zorder=4)
    ax.text(*pos[i], SHORT[i], ha="center", va="center", color="white", fontweight="bold", fontsize=11, zorder=5)
for n in sorted(parts, key=lambda n: -sum(parts[n]["w"].values()))[:24]:
    ax.annotate(ab(n), pos[n], xytext=(5, 3), textcoords="offset points", fontsize=7.8, color=INK, path_effects=halo(), zorder=6)
shared = sum(1 for a in parts.values() if len(a["w"]) >= 2)
ax.legend(handles=[Line2D([], [], marker="o", ls="", color=TCOL[t], label=t) for t in TYPES] +
          [Line2D([], [], marker="o", ls="", color=OTHER, label="Other types")], loc="lower center", ncol=5, fontsize=8.5, bbox_to_anchor=(.5, -.02))
ax.set_title(f"Institute collaboration network: our three institutes and {len(parts)} Indian partners with {MIN}+ joint papers ({shared} shared by 2+ of ours)\n"
             f"node size = joint papers · colour = partner type · line colour = our institute · dashed = joint papers between our three",
             loc="left", fontsize=10.5)
save(fig, "R9_institute_network")

# R10 how connected are the three -----------------------------------------------------------------
mask = Counter(frozenset(a["w"]) for a in agg.values())
combos = [(INSTS[0],), (INSTS[1],), (INSTS[2],), (INSTS[0], INSTS[1]), (INSTS[0], INSTS[2]), (INSTS[1], INSTS[2]), tuple(INSTS)]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={"width_ratios": [1.2, 1]})
vals = [mask[frozenset(c)] for c in combos]
cols = [COL[c[0]] if len(c) == 1 else ("#e34948" if len(c) == 3 else "#6250d6") for c in combos]
a1.bar([" + ".join(SHORT[x] for x in c) + (" only" if len(c) == 1 else "") for c in combos], vals, color=cols, edgecolor=SURF)
for x, v in enumerate(vals):
    a1.text(x, v + 2, str(v), ha="center", fontsize=9, color=INK2)
a1.set_ylabel("Indian partner institutes")
a1.tick_params(axis="x", rotation=20, labelsize=8.5)
a1.set_title("Which of our institutes work with each partner")
fe = rd(OUT / "faculty_network_edges.csv")
flow = net["flow_matrix_source_rows_target_cols"]
pairs = [(0, 1), (0, 2), (1, 2)]
m1 = [J.get(f"{INSTS[a]} & {INSTS[b]}", 0) for a, b in pairs]
m2 = [sum(1 for e in fe if {e["inst_a"], e["inst_b"]} == {INSTS[a], INSTS[b]}) for a, b in pairs]
m3 = [flow[INSTS[a]][INSTS[b]] + flow[INSTS[b]][INSTS[a]] for a, b in pairs]
w = .27
for dx, vals2, col, lab in ((-w, m1, "#2a78d6", "joint papers"), (0, m2, "#1baf7a", "faculty co-author links"), (w, m3, "#eb6834", "citations (both ways)")):
    a2.bar([k + dx for k in range(3)], vals2, w, color=col, label=lab)
    for k, v in enumerate(vals2):
        a2.text(k + dx, v * 1.08, str(v), ha="center", fontsize=8, color=INK2)
a2.set_yscale("log")
a2.set_xticks(range(3), [f"{SHORT[INSTS[a]]}–{SHORT[INSTS[b]]}" for a, b in pairs])
a2.set_ylabel("count (log scale)")
a2.legend(fontsize=8.5)
a2.set_title("Direct links between each pair of our institutes")
save(fig, "R10_connectedness")

# R11 peer-institute links over time --------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 3.8))
for c, col in zip(["NIT", "IIT", "IIIT", "IISER", "IISc"], ["#eb6834", "#2a78d6", "#1baf7a", "#6250d6", "#e87ba4"]):
    ax.plot(range(2016, 2027), [sum(int(r[f"y{y}"]) for r in pl if r["partner_cluster"] == c) for y in range(2016, 2027)],
            marker="o", ms=4, color=col, label=c)
ax.axvspan(2025.5, 2026.5, color=GRID, alpha=.5, lw=0)
ax.text(2026, ax.get_ylim()[1] * .92, "partial", ha="center", fontsize=8, color=INK2)
ax.set_xticks(range(2016, 2027))
ax.set_xlabel("year")
ax.set_ylabel("joint papers (all three institutes)")
ax.legend(ncol=5)
ax.set_title("Joint papers with peer institutes outside our group, by year")
save(fig, "R11_peer_trend")

# R12 partner types: papers and citations both ways ----------------------------------------------
pr = json.loads((ST / "partner_results.json").read_text(encoding="utf-8"))
cc = defaultdict(Counter)
for i in INSTS:
    for r in pr[i]["cross_cluster"]:
        cc[r["partner_cluster"]].update({"sp": r["shared_papers"], "cf": r["cites_from_partner"], "ct": r["cites_to_partner"]})
cls = sorted(cc, key=lambda c: cc[c]["sp"])
fig, ax = plt.subplots(figsize=(10, 5.2))
h = .27
for dy, k, col, lab in ((h, "sp", "#2a78d6", "joint papers"), (0, "cf", "#1baf7a", "they cite our papers"), (-h, "ct", "#eb6834", "our papers cite them")):
    ax.barh([v + dy for v in range(len(cls))], [max(cc[c][k], .5) for c in cls], h, color=col, label=lab)
ax.set_yticks(range(len(cls)), cls)
ax.set_xscale("log")
ax.set_xlabel("count, all three institutes (log scale)")
ax.legend(loc="lower right")
ax.set_title("Indian partners by exact type: collaboration and citations in both directions")
save(fig, "R12_partner_types_citations")

# R13 topic similarity vs collaboration ----------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 4.6))
for i in INSTS:
    rs = [r for r in pr[i]["top_partners"] if r.get("weighted_jaccard") is not None]
    rho = pr[i]["similarity_vs_shared_papers_spearman"]["rho"]
    ax.scatter([r["weighted_jaccard"] for r in rs], [r["shared_papers"] for r in rs], s=34, color=COL[i], alpha=.8, edgecolor=SURF,
               label=f"{SHORT[i]} (Spearman ρ = {rho})")
ax.set_yscale("log")
ax.set_xlabel("research-topic similarity (weighted Jaccard of subfields, 0–1)")
ax.set_ylabel("joint papers (log)")
ax.legend(fontsize=8.5)
ax.set_title("Topic similarity vs collaboration (top partners per institute)")
save(fig, "R13_similarity_vs_collab")

# R14 departments --------------------------------------------------------------------------------
dep = [r for r in rd(ST / "department_stats.csv") if r["department"] != "Unknown department" and int(r["papers"]) >= 40]
fig, ax = plt.subplots(figsize=(10, 5.4))
for i in INSTS:
    rs = [r for r in dep if r["institution"] == i]
    ax.scatter([float(r["papers_per_faculty"]) for r in rs], [float(r["q1_share_%"]) for r in rs], s=[int(r["papers"]) / 4 for r in rs],
               color=COL[i], alpha=.6, edgecolor=SURF, label=i)
for k, r in enumerate(sorted(dep, key=lambda r: -int(r["papers"]))[:9]):
    lab = r["department"].replace("Electronics and Communication Engineering", "ECE").replace("Computer Science and Engineering", "CSE").replace(" Engineering", " Eng.")
    ax.annotate(f"{lab} ({SHORT[r['institution']]})", (float(r["papers_per_faculty"]), float(r["q1_share_%"])), xytext=(7, 6 if k % 2 else -11),
                textcoords="offset points", fontsize=7.8, color=INK, path_effects=halo())
ax.set_xlabel("papers per faculty member")
ax.set_ylabel("journal Q1 share (%)")
ax.legend(markerscale=.4)
ax.set_title("Departments: productivity vs journal quality (bubble = papers; departments with 40+ papers)")
save(fig, "R14_departments")

# R15 field impact -------------------------------------------------------------------------------
agg_f = defaultdict(lambda: [0, 0])
for p in P:
    agg_f[p["field"]][0] += 1
    agg_f[p["field"]][1] += int(p["citations"] or 0)
fl = [(f, n, c / n) for f, (n, c) in agg_f.items() if n >= 40]
fig, ax = plt.subplots(figsize=(10, 5))
ax.scatter([x[1] for x in fl], [x[2] for x in fl], s=[math.sqrt(x[1] * x[2]) * 2 for x in fl], color="#6250d6", alpha=.55, edgecolor=SURF)
for f, n, m in fl:
    if n > 300 or m > 18:
        ax.annotate(f, (n, m), xytext=(9, -12 if f == "Energy" else 4), textcoords="offset points", fontsize=8, color=INK, path_effects=halo())
ax.set_xscale("log")
ax.set_xlabel("papers in the field (log scale)")
ax.set_ylabel("mean citations per paper")
ax.set_title("Research fields: size vs citation impact (all three institutes; fields with 40+ papers)")
save(fig, "R15_field_impact")

# R16 who cites us, whom we cite -----------------------------------------------------------------
fig, axs = plt.subplots(1, 2, figsize=(14, 5))
for ax, fn, key, title in ((axs[0], "incoming_citations_by_institute.csv", "citing_inst", "Who cites us most"),
                           (axs[1], "outgoing_citations_by_institute.csv", "cited_inst", "Whom we cite most")):
    tot = defaultdict(Counter)
    for r in rd(OUT / fn):
        tot[r[key]][r["your_inst"]] += int(r["citations"])
    top = sorted(tot, key=lambda n: -sum(tot[n].values()))[:12][::-1]
    left = [0] * len(top)
    for i in INSTS:
        v = [tot[n][i] for n in top]
        ax.barh([ab(n) for n in top], v, left=left, color=COL[i], edgecolor=SURF, label=i)
        left = [a + b for a, b in zip(left, v)]
    ax.set_xlabel("citations, 2016–2026")
    ax.set_title(title)
    ax.tick_params(axis="y", labelsize=8.5)
axs[0].legend(loc="lower right", fontsize=8.5)
fig.suptitle("Citations exchanged with other Indian institutes", x=.01, ha="left", fontweight="bold")
save(fig, "R16_citers_cited")
