"""Faculty-based figures for the report (figures 04 and 09 in plots.py still use 'core authors').

Writes report/figures/R1_faculty_h_index.png and R2_faculty_network.png. Same style as plots.py.
Needs matplotlib and networkx only:  python report/report_figures.py
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D
import matplotlib.patheffects as pe_

ROOT = Path(__file__).resolve().parent.parent
OUT, ST = ROOT / "data" / "out", ROOT / "data" / "out" / "stats"
FIG = ROOT / "report" / "figures"
FIG.mkdir(exist_ok=True)
INSTS = ["MANIT Bhopal", "NIT Jamshedpur", "NIT Silchar"]
COL = {"MANIT Bhopal": "#2a78d6", "NIT Jamshedpur": "#eb6834", "NIT Silchar": "#1baf7a"}
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID, SURF, OTHER = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#c9c8c0"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "lines.linewidth": 2,
})


def rd(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# R1: faculty h-index distribution ---------------------------------------------------------
bands = ["0", "1-4", "5-9", "10-14", "15-19", "20-29", "30+"]
hd = rd(ST / "h_index_distribution.csv")
fres = json.loads((ST / "faculty_results.json").read_text(encoding="utf-8"))
fig, ax = plt.subplots(figsize=(10, 4.2))
w = 0.26
for k, i in enumerate(INSTS):
    tot = sum(int(r["faculty"]) for r in hd if r["institution"] == i)
    ys = [100 * int(next((r["faculty"] for r in hd if r["institution"] == i and r["h_index"] == b), 0)) / tot for b in bands]
    xs = [x + (k - 1) * w for x in range(len(bands))]
    ax.bar(xs, ys, width=w, color=COL[i], edgecolor=SURF, linewidth=1.5,
           label=f"{i} ({tot} faculty, median h {fres[i]['h_index']['median']:.0f})")
ax.set_xticks(range(len(bands)), bands)
ax.set_xlabel("h-index (2016-2026 papers)")
ax.set_ylabel("share of faculty (%)")
ax.legend(loc="upper right")
ax.set_title("h-index of verified faculty, by institute")
fig.tight_layout()
fig.savefig(FIG / "R1_faculty_h_index.png", dpi=150)

# R2: faculty co-authorship network, Louvain communities -------------------------------------
nodes = {(r["institution"], r["faculty_name"]): r for r in rd(OUT / "faculty_network_nodes.csv")}
G = nx.Graph()
for e in rd(OUT / "faculty_network_edges.csv"):
    G.add_edge((e["inst_a"], e["faculty_a"]), (e["inst_b"], e["faculty_b"]), weight=int(e["joint_papers"]))
sizes = {}
for n in G:
    sizes[nodes[n]["community_louvain"]] = sizes.get(nodes[n]["community_louvain"], 0) + 1
top = sorted(sizes, key=lambda c: (-sizes[c], int(c)))[:8]
colour = {c: CAT[k] for k, c in enumerate(top)}
pos = nx.spring_layout(G, seed=7, k=0.09, iterations=200, weight=None)
deg = dict(G.degree())
fig, ax = plt.subplots(figsize=(11, 9))
ax.axis("off")
nx.draw_networkx_edges(G, pos, ax=ax, edge_color="#b8b6b0", width=[0.3 + 0.25 * G[u][v]["weight"] ** 0.5 for u, v in G.edges()], alpha=0.6)
nx.draw_networkx_nodes(G, pos, ax=ax, node_size=[10 + 9 * deg[n] for n in G], linewidths=0.6, edgecolors=SURF,
                       node_color=[colour.get(nodes[n]["community_louvain"], OTHER) for n in G])
for n in sorted(deg, key=deg.get, reverse=True)[:9]:
    ax.annotate(n[1], pos[n], xytext=(6, 6), textcoords="offset points", fontsize=8.5, color=INK,
                path_effects=[pe_.withStroke(linewidth=3, foreground=SURF)])


def label(c):
    mem = [n for n in G if nodes[n]["community_louvain"] == c]
    inst = max(INSTS, key=lambda i: sum(n[0] == i for n in mem))
    depts = [nodes[n]["department"] for n in mem]
    d = max(set(depts), key=depts.count).replace(" Engineering", " Eng.").replace("Electronics and Communication", "ECE")
    return f"C{c}: {inst.split()[0] if inst.startswith('MANIT') else 'NIT' + inst.split()[1][0]} {d} ({len(mem)})"


handles = [Line2D([], [], marker="o", ls="", color=colour[c], label=label(c)) for c in top]
handles.append(Line2D([], [], marker="o", ls="", color=OTHER, label=f"{len(sizes) - 8} smaller communities"))
ax.legend(handles=handles, loc="lower left", fontsize=8.5)
ax.set_title(f"Faculty co-authorship network: {G.number_of_nodes()} faculty, {G.number_of_edges()} links "
             f"(isolated faculty not shown)\ncolour = Louvain community, node size = number of faculty collaborators", loc="left")
fig.tight_layout()
fig.savefig(FIG / "R2_faculty_network.png", dpi=150)
print("saved", FIG / "R1_faculty_h_index.png", FIG / "R2_faculty_network.png")

# R3: locality and partner type ------------------------------------------------------------------
LOCD = ST / "locality"
loc = rd(LOCD / "by_locality.csv")
LOCS = ["Same state", "Same region", "Other region", "National body", "Unknown"]
LCOL = {"Same state": "#104281", "Same region": "#2a78d6", "Other region": "#86b6ef", "National body": "#6250d6", "Unknown": OTHER}
clus = rd(LOCD / "by_cluster.csv")
CLS = ["IIT", "NIT", "IIIT", "Central university", "Other university/college", "CSIR", "DAE", "Industry"]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={"width_ratios": [1, 1.25]})
for k, i in enumerate(INSTS):
    left = 0
    for l in LOCS:
        v = float(next((r["share_of_links_%"] for r in loc if r["your_inst"] == i and r["locality"] == l), 0))
        a1.barh(k, v, left=left, color=LCOL[l], edgecolor=SURF, linewidth=1.5, label=l if k == 0 else None)
        if v >= 7:
            a1.text(left + v / 2, k, f"{v:.0f}%", ha="center", va="center", fontsize=8.5, color="white" if l in ("Same state", "Same region", "National body") else INK)
        left += v
a1.set_yticks(range(3), [i.replace(" ", "\n", 1) for i in INSTS]); a1.invert_yaxis(); a1.set_xlim(0, 100)
a1.set_xlabel("share of Indian partner links (%)"); a1.set_title("How local is collaboration?")
a1.legend(loc="upper center", bbox_to_anchor=(.5, -.18), ncol=3, fontsize=8.5)
w = 0.26
for k, i in enumerate(INSTS):
    ys = [float(next((r["share_of_links_%"] for r in clus if r["your_inst"] == i and r["partner_cluster"] == c), 0)) for c in CLS]
    a2.bar([x + (k - 1) * w for x in range(len(CLS))], ys, width=w, color=COL[i], edgecolor=SURF, linewidth=1, label=i)
a2.set_xticks(range(len(CLS)), [c.replace("Other university/college", "Other univ./\ncollege").replace("Central university", "Central\nuniv.") for c in CLS], fontsize=8.5)
a2.set_ylabel("share of partner links (%)"); a2.set_title("Type of Indian partner"); a2.legend(fontsize=8.5)
fig.tight_layout()
fig.savefig(FIG / "R3_locality_partner_type.png", dpi=150)

# R4: within vs outside co-authors ---------------------------------------------------------------
wo = rd(LOCD / "faculty_within_outside.csv")
fig, ax = plt.subplots(figsize=(8, 5))
for i in INSTS:
    rs = [r for r in wo if r["institution"] == i]
    ax.scatter([int(r["coauthors_same_institute"]) + 1 for r in rs], [int(r["coauthors_outside_institute"]) + 1 for r in rs],
               s=[8 + 2 * int(r["coauthors_total"]) ** .8 for r in rs], color=COL[i], alpha=.6, edgecolor=SURF, linewidth=.6, label=i)
top = sorted(wo, key=lambda r: -int(r["coauthors_outside_institute"]))[:4] + sorted(wo, key=lambda r: -int(r["coauthors_same_institute"]))[:2]
for k, r in enumerate(top):
    ax.annotate(r["faculty_name"], (int(r["coauthors_same_institute"]) + 1, int(r["coauthors_outside_institute"]) + 1), xytext=(6, 5 if k % 2 == 0 else -12),
                textcoords="offset points", fontsize=8, color=INK, path_effects=[pe_.withStroke(linewidth=3, foreground=SURF)])
ax.plot([1, 40], [1, 40], ls=":", color=INK2, lw=1)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("faculty co-authors at the same institute (+1)"); ax.set_ylabel("co-authors outside the institute (+1)")
ax.set_title("Within vs outside: every faculty member"); ax.legend(fontsize=8.5, loc="lower right")
fig.tight_layout()
fig.savefig(FIG / "R4_within_outside.png", dpi=150)
print("saved R3, R4")
