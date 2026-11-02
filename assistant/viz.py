"""Figures for assistant answers (Plotly). Every function returns a plotly Figure; the assistant stores them as JSON.

Institute colours are fixed across the whole project: MANIT blue, NITJ orange, NITS green.
"""
import networkx as nx
import numpy as np
import plotly.graph_objects as go

from .data import INSTS, SHORT, store

COL = {"MANIT Bhopal": "#2a78d6", "NIT Jamshedpur": "#eb6834", "NIT Silchar": "#1baf7a"}
INK = "#0b0b0b"
LAYOUT = dict(template="plotly_white", font=dict(family="Inter, Arial", size=12), margin=dict(l=10, r=10, t=44, b=10), height=520)


def network_figure(nodes, center=None, path=None, highlight=None, extra_edges=None, title="", max_nodes=120):
    """Collaboration subgraph of the verified-faculty network.

    nodes      faculty ids to draw (their mutual collaboration edges are drawn with the joint-paper counts as labels)
    center     ids drawn large with a dark outline and a label (e.g. the two researchers being compared)
    path       ordered list of ids; its edges are drawn thick and dark
    highlight  ids outlined in gold (e.g. common collaborators)
    extra_edges  [(id_a, id_b)] drawn dashed (e.g. a suggested collaboration that does not exist yet)
    """
    G = store().graph
    nodes = list(dict.fromkeys(list(nodes)))[:max_nodes]
    H = G.subgraph(nodes).copy()
    for a, b in extra_edges or []:
        H.add_node(a), H.add_node(b)
    center, highlight, path = list(center or []), set(highlight or []), list(path or [])
    pos = nx.spring_layout(H, seed=15, k=1.4 / max(np.sqrt(max(len(H), 1)), 1), weight=None, iterations=200)
    path_edges = {frozenset(p) for p in zip(path[:-1], path[1:])}
    fig = go.Figure()
    xs, ys = [], []
    for a, b in H.edges():
        if frozenset((a, b)) in path_edges:
            continue
        xs += [pos[a][0], pos[b][0], None]
        ys += [pos[a][1], pos[b][1], None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=1, color="#b8b6b0"), hoverinfo="skip", showlegend=False))
    if path_edges:
        px, py = [], []
        for a, b in zip(path[:-1], path[1:]):
            px += [pos[a][0], pos[b][0], None]
            py += [pos[a][1], pos[b][1], None]
        fig.add_trace(go.Scatter(x=px, y=py, mode="lines", line=dict(width=4, color=INK), hoverinfo="skip", name="shortest path"))
    if extra_edges:
        ex, ey = [], []
        for a, b in extra_edges:
            ex += [pos[a][0], pos[b][0], None]
            ey += [pos[a][1], pos[b][1], None]
        fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=3, color="#c0392b", dash="dash"), hoverinfo="skip", name="no joint paper yet"))
    # edge labels (joint papers) for the edges that matter: path, centre-centre, centre-neighbour
    lab = []
    for a, b, d in H.edges(data=True):
        if frozenset((a, b)) in path_edges or (a in center and b in center) or (len(H) <= 14):
            lab.append(((pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2, str(d["weight"])))
    if lab:
        fig.add_trace(go.Scatter(x=[l[0] for l in lab], y=[l[1] for l in lab], mode="text", text=[l[2] for l in lab], textfont=dict(size=11, color="#52514e"),
                                 hoverinfo="skip", showlegend=False))
    f = store().faculty
    for inst in INSTS:
        ids = [n for n in H.nodes if H.nodes[n].get("institution") == inst]
        if not ids:
            continue
        fig.add_trace(go.Scatter(
            x=[pos[n][0] for n in ids], y=[pos[n][1] for n in ids], mode="markers+text", name=SHORT[inst],
            text=[H.nodes[n]["name"] if (n in center or n in highlight or len(H) <= 16) else "" for n in ids], textposition="top center", textfont=dict(size=11),
            marker=dict(size=[26 if n in center else 18 if n in highlight else 11 for n in ids], color=COL[inst],
                        line=dict(width=[3 if n in center else 2.5 if n in highlight else 0.8 for n in ids], color=[INK if n in center else "#e0a800" if n in highlight else "white" for n in ids])),
            customdata=[[H.nodes[n]["name"], H.nodes[n].get("department", ""), int(f.at[n, "papers"]) if n in f.index else 0, int(f.at[n, "h_index"]) if n in f.index else 0, H.degree(n)] for n in ids],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>papers %{customdata[2]} · h-index %{customdata[3]} · collaborators here %{customdata[4]}<extra></extra>"))
    fig.update_layout(**LAYOUT, title=dict(text=title, x=0.01), xaxis=dict(visible=False), yaxis=dict(visible=False), legend=dict(orientation="h", y=-0.02))
    return fig


def bar_figure(labels, values, title="", xlabel="", color="#2a78d6", horizontal=True, text=None):
    fig = go.Figure(go.Bar(x=values if horizontal else labels, y=labels if horizontal else values, orientation="h" if horizontal else "v",
                           marker_color=color, text=text if text is not None else values, textposition="outside"))
    fig.update_layout(**{**LAYOUT, "height": max(320, 26 * len(labels) + 120) if horizontal else 420}, title=dict(text=title, x=0.01), xaxis_title=xlabel,
                      yaxis=dict(autorange="reversed") if horizontal else {})
    return fig


def grouped_bar(categories, series, title="", ylabel=""):
    """series: {name: [values per category]} ; colour by institute when the series name is an institute."""
    fig = go.Figure()
    for name, vals in series.items():
        fig.add_trace(go.Bar(x=categories, y=vals, name=SHORT.get(name, name), marker_color=COL.get(name)))
    fig.update_layout(**{**LAYOUT, "height": 420}, barmode="group", title=dict(text=title, x=0.01), yaxis_title=ylabel, legend=dict(orientation="h", y=-0.15))
    return fig


def scatter_figure(df, x, y, color="institution", size=None, hover="faculty_name", title="", logx=False, logy=False):
    fig = go.Figure()
    for inst in INSTS:
        d = df[df[color] == inst]
        if d.empty:
            continue
        fig.add_trace(go.Scatter(x=d[x], y=d[y], mode="markers", name=SHORT[inst], text=d[hover],
                                 marker=dict(color=COL[inst], size=8 if size is None else np.clip(d[size] ** 0.5 * 2, 6, 30), opacity=0.7, line=dict(width=0.5, color="white")),
                                 hovertemplate="<b>%{text}</b><br>" + x + " %{x}<br>" + y + " %{y}<extra></extra>"))
    fig.update_layout(**{**LAYOUT, "height": 460}, title=dict(text=title, x=0.01), xaxis=dict(title=x, type="log" if logx else "linear"), yaxis=dict(title=y, type="log" if logy else "linear"))
    return fig


def resilience_figure(scope="all", metric="lcc"):
    R = store().resilience
    s = R["scopes"][scope]
    fr = [f * 100 for f in R["fractions"]]
    names = {"random": ("random removal (mean, 95% band)", "#8795a8"), "degree": ("highest degree first", "#2a78d6"), "betweenness": ("highest betweenness first", "#eb6834"),
             "betweenness_adaptive": ("betweenness, recomputed each step", "#c0392b")}
    fig = go.Figure()
    key = "lcc" if metric == "lcc" else "eff"
    rnd = s["curves"]["random"]
    fig.add_trace(go.Scatter(x=fr + fr[::-1], y=rnd[key + "_hi"] + rnd[key + "_lo"][::-1], fill="toself", fillcolor="rgba(135,149,168,0.25)", line=dict(width=0), hoverinfo="skip", showlegend=False))
    for k, (label, col) in names.items():
        fig.add_trace(go.Scatter(x=fr, y=s["curves"][k][key], mode="lines+markers", name=label, line=dict(color=col, width=2.5 if k != "random" else 2), marker=dict(size=5)))
    for k, dash in (("degree", "dot"), ("betweenness", "dot")):
        if s.get("null_model", {}).get(k):
            fig.add_trace(go.Scatter(x=fr, y=s["null_model"][k][key], mode="lines", name=f"degree-preserving random network, {k} attack", line=dict(color="#555", width=1.4, dash=dash)))
    t = "Largest connected component (fraction of the original network)" if metric == "lcc" else "Global efficiency (relative to the intact network)"
    label = "all three institutes" if scope == "all" else scope
    fig.update_layout(**{**LAYOUT, "height": 460}, title=dict(text=f"{t} — {label}", x=0.01), xaxis_title="faculty removed (% of the original network)",
                      yaxis=dict(title="fraction", range=[0, 1.02]), legend=dict(orientation="h", y=-0.25))
    return fig


def lorenz_figure(conc):
    fig = go.Figure()
    q = np.linspace(0, 100, len(next(iter(conc.values()))["lorenz_faculty_full"]))
    fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color="#aaa", dash="dash"), name="equal"))
    for inst, v in conc.items():
        if inst in INSTS:
            fig.add_trace(go.Scatter(x=q, y=np.array(v["lorenz_faculty_full"]) * 100, mode="lines", name=f"{SHORT[inst]} (Gini {v['gini_full']})", line=dict(color=COL[inst], width=2.5)))
    fig.update_layout(**{**LAYOUT, "height": 420}, title=dict(text="Lorenz curve of faculty citations", x=0.01), xaxis_title="faculty, least to most cited (%)", yaxis_title="cumulative share of citations (%)")
    return fig
