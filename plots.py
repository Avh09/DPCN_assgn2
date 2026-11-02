"""Static charts for the Group 15 results.

    .venv/bin/python plots.py            # opens each figure in a window, one after another
    .venv/bin/python plots.py --no-show  # only saves PNGs to data/out/figures/

Colours: one fixed colour per institute in every chart (validated categorical palette,
first three slots). Quartiles use a one-hue sequential ramp (dark = Q1).
"""
import json
import sys

import matplotlib
import matplotlib.patheffects as pe_

SHOW = "--no-show" not in sys.argv
if not SHOW:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

import config

OUT = config.OUT_DIR
FIG = OUT / "figures"
FIG.mkdir(exist_ok=True)
INSTS = list(config.INSTITUTES)
COL = {"MANIT Bhopal": "#2a78d6", "NIT Jamshedpur": "#eb6834", "NIT Silchar": "#1baf7a"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
QCOL = {"Q1": "#1c4f96", "Q2": "#2a78d6", "Q3": "#86b5ee", "Q4": "#cfe0f7"}
TYPE_COL = {"journal": "#3d4a5c", "conference": "#8795a8", "other": "#cdd3db"}

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "lines.linewidth": 2,
})


def finish(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.png", dpi=150)
    print("saved", FIG / f"{name}.png")
    if SHOW:
        plt.show()
    plt.close(fig)


def short(i):
    return i.replace(" ", "_")


pub = json.load(open(OUT / "stats" / "publication_results.json"))
net = json.load(open(OUT / "stats" / "network_results.json"))
papers = pd.read_csv(OUT / "papers_enriched.csv", dtype={"issn": str})
authors = pd.read_csv(OUT / "authors.csv")


def of(i):
    return papers[papers.our_institutes.fillna("").str.contains(i, regex=False)]


# 1 ---------------------------------------------------------------- papers per year
def fig_papers_per_year():
    yr = pd.read_csv(OUT / "stats" / "papers_per_year.csv", index_col=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    for i in INSTS:
        ax.plot(yr.index[:-1], yr[i][:-1], color=COL[i], marker="o", ms=5, label=i)
        ax.plot(yr.index[-2:], yr[i][-2:], color=COL[i], ls=":", marker="o", ms=5, mfc="none")
        ax.annotate(i, (2026, yr[i].iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    color=INK2, va="center", fontsize=9)
    ax.set_xlim(2015.6, 2028.2)
    ax.set_xticks(range(2016, 2027))
    ax.set_ylabel("papers per year")
    ax.set_title("Papers per year, 2016-2026")
    ax.text(0.01, 0.97, "dotted = 2026 is a partial year (data to October)", transform=ax.transAxes,
            color=INK2, fontsize=9, va="top")
    ax.legend(loc="upper left", bbox_to_anchor=(0.01, 0.9))
    finish(fig, "01_papers_per_year")


# 2 ------------------------------------------------------------------ paper types
def fig_types():
    ts = pd.DataFrame(pub["type_split"]).T[["journal", "conference"]]
    share = ts.div(ts.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(9, 3.6))
    left = np.zeros(len(share))
    for t in share.columns:
        ax.barh(share.index, share[t], left=left, color=TYPE_COL[t], edgecolor=SURF, linewidth=2, label=t, height=0.6)
        for y, (l, v) in enumerate(zip(left, share[t])):
            ax.text(l + v / 2, y, f"{v:.0f}%", ha="center", va="center", fontsize=9,
                    color="white" if t == "journal" else INK)
        left += share[t].values
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of papers (%)")
    ax.set_title("Journal papers vs conference papers")
    ax.grid(axis="y", visible=False)
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.25))
    finish(fig, "02_paper_types")


# 3 ------------------------------------------------------------- quartiles
def fig_quartiles():
    q = pub["quartiles"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1, 1.25]})
    left = np.zeros(3)
    for k in ["Q1", "Q2", "Q3", "Q4"]:
        vals = np.array([q[i]["shares_%"][k] for i in INSTS])
        a1.barh(INSTS, vals, left=left, color=QCOL[k], edgecolor=SURF, linewidth=2, label=k, height=0.6)
        for y, (l, v) in enumerate(zip(left, vals)):
            a1.text(l + v / 2, y, f"{v:.0f}%", ha="center", va="center", fontsize=9,
                    color="white" if k in ("Q1", "Q2") else INK)
        left += vals
    a1.invert_yaxis()
    a1.set_xlim(0, 100)
    a1.grid(axis="y", visible=False)
    a1.set_xlabel("share of journal papers with a known quartile (%)")
    a1.set_title("Journal quartile mix (Q1 = top 25% of journals)")
    a1.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    for i in INSTS:
        s = q[i]["Q1_fraction_by_year_%"]
        yrs = [int(y) for y in s]
        a2.plot(yrs, list(s.values()), color=COL[i], marker="o", ms=5, label=i)
        a2.annotate(i, (yrs[-1], list(s.values())[-1]), xytext=(6, 0), textcoords="offset points",
                    color=INK2, fontsize=9, va="center")
    a2.set_xlim(2015.6, 2028.5)
    a2.set_xticks(range(2016, 2027))
    a2.set_ylabel("Q1 share of journal papers (%)")
    a2.set_title("Q1 share by year")
    finish(fig, "03_quartiles")


# 4 ---------------------------------------------------------------- h-index
def fig_hindex():
    fp = pd.read_csv(OUT / "stats" / "faculty_performance.csv")
    bins = np.arange(0, 60, 2)
    fig, axs = plt.subplots(1, 3, figsize=(13, 4), sharey=True, sharex=True)
    for ax, i in zip(axs, INSTS):
        h = fp[fp.institution == i].h_index
        ax.hist(h, bins=bins, color=COL[i], edgecolor=SURF, linewidth=1.5)
        ax.axvline(h.median(), color=INK2, ls="--", lw=1.2)
        ax.text(h.median() + 0.8, ax.get_ylim()[1] * 0.92, f"median {h.median():.0f}", color=INK2, fontsize=9)
        ax.set_title(f"{i} ({len(h)} faculty)")
        ax.set_xlabel("h-index (2016-2026 papers)")
    axs[0].set_ylabel("number of faculty")
    fig.suptitle("h-index of verified faculty (current and former)", x=0.01, ha="left", fontweight="bold")
    finish(fig, "04_h_index")


# 5 ---------------------------------------------------------------- citations
def fig_citations():
    fig, axs = plt.subplots(1, 3, figsize=(13, 4), sharey=True, sharex=True)
    bins = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 100000]
    labels = ["0", "1", "2-3", "4-7", "8-15", "16-31", "32-63", "64-127", "128-255", "256+"]
    for ax, i in zip(axs, INSTS):
        c = of(i).citations
        cnt = pd.cut(c, bins, right=False).value_counts(sort=False).values / len(c) * 100
        ax.bar(range(len(cnt)), cnt, color=COL[i], edgecolor=SURF, linewidth=1.5)
        ax.set_xticks(range(len(cnt)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_title(f"{i}")
        ax.set_xlabel("citations per paper")
    axs[0].set_ylabel("% of papers")
    fig.suptitle("Most papers get few citations, a few get very many", x=0.01, ha="left", fontweight="bold")
    finish(fig, "05_citations")


# 6 ---------------------------------------------------------------- research areas
def fig_fields():
    fields = (papers.field.value_counts().head(8).index).tolist()
    data = pd.DataFrame({i: of(i).field.value_counts(normalize=True).reindex(fields).fillna(0) * 100
                         for i in INSTS})
    fig, ax = plt.subplots(figsize=(10, 6))
    y = np.arange(len(fields))
    h = 0.26
    for k, i in enumerate(INSTS):
        ax.barh(y + (k - 1) * h, data[i], height=h - 0.03, color=COL[i], label=i)
        for yy, v in zip(y + (k - 1) * h, data[i]):
            ax.text(v + 0.5, yy, f"{v:.0f}%", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(fields)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("share of the institute's papers (%)")
    ax.set_title("Research areas (OpenAlex field), top 8")
    ax.legend(loc="lower right")
    finish(fig, "06_research_areas")


# 7 ---------------------------------------------------------------- citation flow
def fig_flow():
    f = pd.DataFrame(net["citation_network"]["flow_matrix_source_rows_target_cols"]).T.loc[INSTS, INSTS]
    cross = f.astype(float)
    arr = cross.values.copy()
    np.fill_diagonal(arr, np.nan)
    fig, ax = plt.subplots(figsize=(6.6, 5))
    ax.imshow(arr, cmap="Blues", vmin=0, vmax=np.nanmax(arr) * 1.3)
    ax.set_xticks(range(3)); ax.set_xticklabels(INSTS)
    ax.set_yticks(range(3)); ax.set_yticklabels(INSTS)
    ax.set_xlabel("cited institute"); ax.set_ylabel("citing institute")
    ax.grid(False)
    for a in range(3):
        for b in range(3):
            if a == b:
                ax.text(b, a, f"within\n{int(f.iloc[a, b]):,}", ha="center", va="center", color=INK2, fontsize=9)
            else:
                ax.text(b, a, f"{int(f.iloc[a, b])}", ha="center", va="center", fontsize=12, fontweight="bold")
    ax.set_title("Citations between our institutes\n(papers in our dataset only)")
    finish(fig, "07_citation_flow")


# 8 ---------------------------------------------------------------- citation network
def fig_citation_network():
    ids = set(papers.openalex_work_id)
    G = nx.DiGraph()
    for wid, refs in zip(papers.openalex_work_id, papers.referenced_works):
        if isinstance(refs, str):
            G.add_edges_from((wid, r) for r in refs.split(";") if r in ids and r != wid)
    pr = nx.pagerank(G)
    # a readable picture: the 110 best-connected papers of EACH institute, so all three show up
    P0 = papers.set_index("openalex_work_id")
    und = G.to_undirected()
    keep = []
    for i in INSTS:
        cand = [n for n in und if (P0.at[n, "our_institutes"] or "").split(";")[0] == i]
        keep += sorted(cand, key=lambda n: und.degree(n), reverse=True)[:110]
    H = G.subgraph(keep).copy()
    H.remove_nodes_from([n for n in list(H) if H.degree(n) == 0])
    P = papers.set_index("openalex_work_id")
    inst = {n: (P.at[n, "our_institutes"] or "").split(";")[0] for n in H}
    pos = nx.spring_layout(H.to_undirected(), seed=3, k=0.3, iterations=200)
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.axis("off")
    nx.draw_networkx_edges(H, pos, ax=ax, edge_color="#b8b6b0", width=0.5, alpha=0.7, arrows=False)
    sizes = [20 + 900 * pr[n] * 20 for n in H]
    nx.draw_networkx_nodes(H, pos, ax=ax, node_size=sizes, linewidths=0.8, edgecolors=SURF,
                           node_color=[COL.get(inst[n], "#999") for n in H])
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=COL[i], label=i) for i in INSTS],
              loc="lower left")
    ax.set_title(f"Citation network: the best-connected papers of each institute ({H.number_of_nodes()} papers), "
                 f"{H.number_of_edges()} links\nnode size = PageRank, colour = institute", loc="left")
    finish(fig, "08_citation_network")


# 9 ---------------------------------------------------------------- co-author network
def fig_coauthor_network():
    e = pd.read_csv(OUT / "faculty_network_edges.csv")
    G = nx.Graph()
    G.add_weighted_edges_from([((r.inst_a, r.faculty_a), (r.inst_b, r.faculty_b), r.joint_papers) for r in e.itertuples()])
    pos = nx.spring_layout(G, seed=5, k=0.12, iterations=150, weight=None)
    deg = dict(G.degree())
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.axis("off")
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color="#b8b6b0", width=0.4, alpha=0.6)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=[12 + 7 * deg[n] for n in G], linewidths=0.6,
                           edgecolors=SURF, node_color=[COL.get(n[0], "#999") for n in G])
    for n in sorted(deg, key=deg.get, reverse=True)[:7]:
        ax.annotate(n[1], pos[n], xytext=(6, 6), textcoords="offset points", fontsize=8.5, color=INK,
                    path_effects=[pe_.withStroke(linewidth=3, foreground=SURF)])
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=COL[i], label=i) for i in INSTS], loc="lower left")
    ax.set_title(f"Faculty co-authorship network: {G.number_of_nodes()} faculty, "
                 f"{G.number_of_edges()} collaborations\nnode size = number of collaborators, colour = institute",
                 loc="left")
    finish(fig, "09_coauthor_network")


# 10 --------------------------------------------------------------- Indian partners
def fig_partners():
    d = pd.read_csv(OUT / "indian_connections_detailed.csv")
    fig, axs = plt.subplots(1, 3, figsize=(15, 5), sharex=False)
    for ax, i in zip(axs, INSTS):
        t = d[d.your_inst == i].nlargest(10, "shared_papers").iloc[::-1]
        ax.barh(t.partner_inst.str.replace("Indian Institute of Technology", "IIT")
                .str.replace("National Institute of Technology", "NIT")
                .str.replace("Indian Institute of Information Technology", "IIIT"),
                t.shared_papers, color=COL[i], height=0.65)
        for y, v in enumerate(t.shared_papers):
            ax.text(v + 1, y, str(v), va="center", fontsize=8, color=INK2)
        ax.set_title(i)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("shared papers")
    fig.suptitle("Top 10 Indian partner institutes by number of shared papers", x=0.01, ha="left", fontweight="bold")
    finish(fig, "10_indian_partners")


def fig_partner_types():
    d = pd.read_csv(OUT / "indian_connections_detailed.csv")
    g = d.groupby(["your_inst", "partner_cluster"]).shared_papers.sum().unstack(fill_value=0).loc[INSTS]
    share = g.div(g.sum(axis=1), axis=0) * 100
    order = share.mean().sort_values(ascending=False).index[:8]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    y = np.arange(len(order))
    h = 0.26
    for k, i in enumerate(INSTS):
        ax.barh(y + (k - 1) * h, share.loc[i, order], height=h - 0.03, color=COL[i], label=i)
        for yy, v in zip(y + (k - 1) * h, share.loc[i, order]):
            ax.text(v + 0.5, yy, f"{v:.0f}%", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels(order)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("share of the institute's Indian co-authorship links (%)")
    ax.set_title("Who do they collaborate with? Type of Indian partner institute")
    ax.legend(loc="lower right")
    finish(fig, "11_partner_types")

# 12 ------------------------------------------------------------ papers with more than 10 authors
def fig_multi_author():
    r = pd.read_csv(OUT / "stats" / "multi_author_reanalysis.csv")
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.6))
    x = np.arange(len(INSTS))
    a = r[r.scope == "all papers"].set_index("institution").loc[INSTS]
    b = r[r.scope != "all papers"].set_index("institution").loc[INSTS]
    share = a.papers_with_10plus_authors / a.papers * 100
    axs[0].bar(x, share, color=[COL[i] for i in INSTS])
    for k, v in enumerate(share):
        axs[0].text(k, v + 0.02, f"{v:.1f}%\n({int(a.papers_with_10plus_authors.iloc[k])} papers)", ha="center", fontsize=9)
    axs[0].set_xticks(x, [short(i).replace("_", "\n") for i in INSTS]); axs[0].set_ylim(0, share.max() * 1.5)
    axs[0].set_title("Papers with more than 10 authors")
    axs[0].set_ylabel("share of faculty papers (%)")
    w = 0.38
    axs[1].bar(x - w / 2, a["journal_Q1_share_%"], w, color="#3d4a5c", label="all papers")
    axs[1].bar(x + w / 2, b["journal_Q1_share_%"], w, color="#8795a8", label="without >10-author papers")
    axs[1].set_xticks(x, [short(i).replace("_", "\n") for i in INSTS]); axs[1].set_title("Journal Q1 share")
    axs[1].set_ylabel("%"); axs[1].set_ylim(0, 46); axs[1].legend(loc="upper center", fontsize=8)
    axs[2].bar(x - w / 2, a.faculty_h_20_plus, w, color="#3d4a5c", label="all papers")
    axs[2].bar(x + w / 2, b.faculty_h_20_plus, w, color="#8795a8", label="without >10-author papers")
    axs[2].set_xticks(x, [short(i).replace("_", "\n") for i in INSTS]); axs[2].set_title("Faculty with h-index 20+")
    finish(fig, "12_multi_author_10plus")


# 13 ------------------------------------------------------------ top 30 papers
def fig_top30():
    t = pd.read_csv(OUT / "stats" / "top30_summary.csv").set_index("institution").loc[INSTS]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    parts = [("Q1, IF > 10", t.Q1_and_IF_gt10, "#1c4f96"),
             ("Q1, IF 5-10", t.Q1_and_IF_gt5 - t.Q1_and_IF_gt10, "#2a78d6"),
             ("Q1, IF <= 5", t.Q1 - t.Q1_and_IF_gt5, "#86b5ee"),
             ("not Q1 (journal or conference)", t.papers - t.Q1, "#cdd3db")]
    left = np.zeros(len(INSTS))
    for name, v, c in parts:
        ax.barh(range(len(INSTS)), v, left=left, color=c, label=name)
        for k, (l, x) in enumerate(zip(left, v)):
            if x:
                ax.text(l + x / 2, k, int(x), ha="center", va="center", fontsize=9, color="white" if c in ("#1c4f96", "#2a78d6") else INK)
        left += v
    ax.set_yticks(range(len(INSTS)), INSTS); ax.invert_yaxis(); ax.set_xlabel("papers among the 30 most cited")
    ax.set_title("Top 30 papers: journal quality (IF = SCImago cites per document)", fontsize=11)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=2, fontsize=8)
    finish(fig, "13_top30_quality")


# 14 ------------------------------------------------------------ incoming / outgoing citations
def fig_ratio():
    r = pd.read_csv(OUT / "stats" / "citation_ratio.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [2.2, 1]})
    for i in INSTS:
        g = r[(r.your_inst == i) & (r.year != "2016-2026")]
        g = g[g.year.astype(int) <= 2025]
        a1.plot(g.year.astype(int), g.in_over_out, color=COL[i], marker="o", ms=4, label=i)
    a1.axhline(1, color=INK2, lw=1, ls="--")
    a1.text(2016.1, 1.02, "in = out", color=INK2, fontsize=8)
    a1.set_xlabel("year of the citing paper"); a1.set_ylabel("incoming / outgoing citations")
    a1.set_title("Citation ratio by year (other Indian institutes)"); a1.legend()
    tot = r[r.year == "2016-2026"].set_index("your_inst").loc[INSTS]
    a2.bar(range(len(INSTS)), tot.in_over_out, color=[COL[i] for i in INSTS])
    for k, v in enumerate(tot.in_over_out):
        a2.text(k, v + 0.01, f"{v:.2f}", ha="center", fontsize=10)
    a2.set_xticks(range(len(INSTS)), [short(i).replace("_", "\n") for i in INSTS]); a2.set_title("2016-2026")
    finish(fig, "14_citation_ratio")


# 15 ------------------------------------------------------------ author-based: ranking
def fig_authors():
    fig, axs = plt.subplots(1, 3, figsize=(15, 5.2))
    for ax, i in zip(axs, INSTS):
        g = pd.read_csv(OUT / "stats" / f"faculty_ranking_{short(i)}.csv").nlargest(10, "h_index").iloc[::-1]
        ax.barh(g.faculty_name, g.h_index, color=COL[i])
        for k, (h, p, c) in enumerate(zip(g.h_index, g.papers, g.citations)):
            ax.text(h + 0.3, k, f"{p} papers, {c:,} cit.", va="center", fontsize=7.5, color=INK2)
        ax.set_title(i); ax.set_xlabel("h-index (2016-2026 papers)"); ax.set_xlim(0, g.h_index.max() * 1.7)
    finish(fig, "15_top_faculty")


# 16 ------------------------------------------------------------ author-based: concentration
def fig_concentration():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.6))
    for i in INSTS:
        g = pd.read_csv(OUT / "stats" / f"faculty_ranking_{short(i)}.csv")
        for ax, c in ((a1, "papers"), (a2, "citations")):
            v = np.sort(g[c].values)
            cum = np.insert(np.cumsum(v) / v.sum(), 0, 0)
            ax.plot(np.linspace(0, 1, len(cum)) * 100, cum * 100, color=COL[i], label=i)
    for ax, t in ((a1, "papers"), (a2, "citations")):
        ax.plot([0, 100], [0, 100], color=INK2, lw=1, ls="--")
        ax.set_xlabel("faculty, least to most productive (%)"); ax.set_ylabel(f"cumulative share of {t} (%)")
        ax.set_title(f"How concentrated are {t}?")
    a1.legend(loc="upper left")
    finish(fig, "16_author_concentration")


# 17 ------------------------------------------------------------ citation velocity
def fig_velocity():
    v = pd.read_csv(OUT / "stats" / "citation_velocity.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6))
    for i in INSTS:
        g = v[(v.institution == i) & v.table.str.startswith("citations received") & (v.year <= 2025)]
        a1.plot(g.year, g.value, color=COL[i], marker="o", ms=4, label=i)
        c = v[(v.institution == i) & v.table.str.startswith("publication-year") & (v.year <= 2025)]
        a2.plot(c.year, c.value, color=COL[i], marker="o", ms=4, label=i)
    a1.set_title("Citations received per year"); a1.set_xlabel("year of the citing paper"); a1.set_ylabel("citations"); a1.legend()
    a2.set_title("Citations per paper per year of age, by publication year"); a2.set_xlabel("publication year")
    finish(fig, "17_citation_velocity")


# 18 ------------------------------------------------------------ citation flow by cluster
def fig_flow_clusters():
    d = pd.read_csv(OUT / "stats" / "citation_flow_by_cluster.csv")
    top = d.groupby("cluster").citations.sum().nlargest(7).index.tolist()
    d["cluster"] = d.cluster.where(d.cluster.isin(top), "other")
    d = d.groupby(["your_inst", "direction", "cluster"])["share_%"].sum().reset_index()
    cols = dict(zip(top + ["other"], ["#1c4f96", "#2a78d6", "#1baf7a", "#eb6834", "#86b5ee", "#8795a8", "#c9a227", "#cdd3db"]))
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    for ax, direction in zip(axs, ["incoming", "outgoing"]):
        left = np.zeros(len(INSTS))
        for cl in cols:
            v = [d[(d.your_inst == i) & (d.direction == direction) & (d.cluster == cl)]["share_%"].sum() for i in INSTS]
            ax.barh(range(len(INSTS)), v, left=left, color=cols[cl], label=cl)
            left += np.array(v)
        ax.set_yticks(range(len(INSTS)), INSTS); ax.invert_yaxis()
        ax.set_title("Citations received from" if direction == "incoming" else "Citations given to"); ax.set_xlabel("share (%)")
    axs[1].legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8)
    finish(fig, "18_flow_by_cluster")


# 19 ------------------------------------------------------------ bridge authors
def fig_bridges():
    b = pd.read_csv(OUT / "stats" / "bridge_authors.csv")
    fig, axs = plt.subplots(1, 3, figsize=(15, 5))
    for ax, i in zip(axs, INSTS):
        g = b[b.institution == i].iloc[::-1]
        ax.barh(g.faculty_name, g.distinct_indian_partner_institutes, color=COL[i])
        for k, (n, e) in enumerate(zip(g.distinct_indian_partner_institutes, g.joint_papers)):
            ax.text(n + 0.5, k, f"{e} joint papers", va="center", fontsize=8, color=INK2)
        ax.set_title(i); ax.set_xlabel("different Indian institutes co-authored with"); ax.set_xlim(0, g.distinct_indian_partner_institutes.max() * 1.45)
    finish(fig, "19_bridge_authors")


if __name__ == "__main__":
    for f in (fig_papers_per_year, fig_types, fig_quartiles, fig_hindex, fig_citations, fig_fields,
              fig_flow, fig_citation_network, fig_coauthor_network, fig_partners, fig_partner_types,
              fig_multi_author, fig_top30, fig_ratio, fig_authors, fig_concentration,
              fig_velocity, fig_flow_clusters, fig_bridges):
        f()
