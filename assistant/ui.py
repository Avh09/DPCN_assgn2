"""Streamlit page for the AI Research Assistant (chat, figures, tables, evidence, disambiguation, follow-ups).

Used by dashboard/streamlit_app.py as the "AI Research Assistant" page. The page never exposes the API key: it is read on the
server from st.secrets / environment (llm.py), and all analysis runs server-side through the allowlisted tools.
"""
import os

import plotly.io as pio
import streamlit as st

from .data import store
from .engine import Assistant

EXAMPLES = [
    "Can Rajesh Purohit (MANIT) collaborate with Samuel Lalthazuala Rokhum?",
    "Suggest five potential collaborators for Biplab Das in another NIT.",
    "Show the shortest path between Vijay Bhaskar Semwal (MANIT) and Biplab Das.",
    "Which faculty have high betweenness but relatively low degree?",
    "Compare MANIT and NIT Silchar. Why does MANIT have the higher h-index?",
    "How fragile is the NIT Jamshedpur collaboration network?",
    "What happens if Rajesh Purohit is removed from the collaboration graph?",
    "Can Rajesh Purohit collaborate with IIIT Hyderabad?",
    "Which communities span several departments?",
    "Why does the top PageRank paper have so few worldwide citations?",
    "Which partner countries and Indian states raise the institutes’ papers' impact the most?",
    "Do private universities cite MANIT more than MANIT cites them?",
    "Which institutes cite NIT Silchar far more than NIT Silchar cites them?",
    "What is betweenness?",
]


def _secrets():
    """Streamlit secrets -> environment, once (so llm.py sees ANTHROPIC_API_KEY without it ever reaching the browser)."""
    try:
        for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
            if k in st.secrets and not os.environ.get(k):
                os.environ[k] = st.secrets[k]
    except Exception:
        pass


@st.cache_resource(show_spinner="Loading the research network…")
def _warm():
    s = store()
    s.faculty, s.graph, s.papers          # build the heavy objects once per server process
    return True


def _render_message(m, idx):
    st.markdown(m["text"])
    for k, fj in enumerate(m.get("figures", [])):
        fig = pio.from_json(fj)
        ev = st.plotly_chart(fig, width="stretch", key=f"fig_{idx}_{k}", on_select="rerun", selection_mode="points")
        pts = (ev or {}).get("selection", {}).get("points", []) if isinstance(ev, dict) or hasattr(ev, "get") else []
        for p in pts[:1]:
            cd = p.get("customdata")
            if cd:
                st.info(f"**{cd[0]}**: {cd[1]} · {cd[2]} papers · h-index {cd[3]} · {cd[4]} collaborators in the faculty network")
                if st.button(f"Ask about {cd[0]}", key=f"ask_{idx}_{k}_{cd[0]}"):
                    st.session_state["queued"] = f"Who is {cd[0]}?"
                    st.rerun()
        st.download_button("Download figure (HTML)", pio.to_html(fig, include_plotlyjs="cdn"), file_name="figure.html", key=f"dl_{idx}_{k}")
    for name, df in m.get("tables", []):
        with st.expander(f"Table: {name}"):
            st.dataframe(df, width="stretch")
    if m.get("evidence"):
        with st.expander(f"References ({len(m['evidence'])})"):
            for e in m["evidence"]:
                st.markdown(f"- [{e['label']}]({e['url']})" if e.get("url") else f"- {e['label']}")
    if m.get("links"):
        st.caption("See more in the dashboard")
        cols = st.columns(min(len(m["links"]), 3))
        for k, l in enumerate(m["links"]):
            if cols[k % len(cols)].button(f"{l['label']} →", key=f"dash_{idx}_{k}", width="stretch"):
                st.session_state["dash_hash"] = l["hash"]
                st.switch_page(st.session_state["_pages"]["dashboard"])
    if m.get("tool_calls"):
        with st.expander("How this was computed"):
            st.json(m["tool_calls"])
            g = m.get("grounding") or {}
            if g.get("ungrounded"):
                st.warning("Numbers in the text that could not be traced to a tool result: " + ", ".join(str(x) for x in g["ungrounded"]))
            elif g.get("checked"):
                st.success(f"All {g['checked']} numbers in the answer were found in the tool results.")
            else:
                st.caption(g.get("note", ""))


def _respond(question):
    A = Assistant()
    state = st.session_state["assistant_state"]
    with st.spinner("Analysing the network…"):
        resp = A.ask(question, state)
    st.session_state["messages"].append({"role": "user", "text": question})
    st.session_state["messages"].append({
        "role": "assistant", "text": resp["text"], "figures": [f.to_json() for f in resp["figures"]], "tables": resp["tables"], "evidence": resp["evidence"], "links": resp.get("links", []),
        "tool_calls": resp["tool_calls"], "grounding": resp["grounding"], "needs_choice": resp["needs_choice"], "mode": resp["mode"], "question": question})


def render():
    _secrets()
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("assistant_state", {"history": [], "ctx": {}})
    _warm()
    from . import llm
    st.title("AI Research Assistant")
    st.caption(("Language-model mode: answers are written by the model from tool results and checked for ungrounded numbers." if llm.available() else
                "No API key configured: answering with the built-in analysis router (same tools, same data). Add GEMINI_API_KEY in the app secrets for free-form questions.")
               + " Every number comes from the verified-faculty dataset; links and papers are shown under **References**.")
    with st.sidebar:
        st.subheader("Try asking")
        for i, e in enumerate(EXAMPLES):
            if st.button(e, key=f"ex_{i}", width="stretch"):
                st.session_state["queued"] = e
        if st.button("Clear conversation", width="stretch"):
            st.session_state["messages"], st.session_state["assistant_state"] = [], {"history": [], "ctx": {}}
            st.rerun()
        ctx = st.session_state["assistant_state"].get("ctx", {})
        if ctx.get("faculty"):
            f = store().faculty
            st.caption("Conversation context: " + ", ".join(f.at[i, "faculty_name"] for i in ctx["faculty"] if i in f.index))
    for i, m in enumerate(st.session_state["messages"]):
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["text"])
            else:
                _render_message(m, i)
                nc = m.get("needs_choice")
                if nc and i == len(st.session_state["messages"]) - 1 and nc["entity"] == "faculty":
                    labels = [f"{c['name']} — {c['institution']}, {c['department']}" for c in nc["candidates"]]
                    pick = st.radio("Choose one:", labels, key=f"choice_{i}")
                    if st.button("Use this person", key=f"use_{i}"):
                        c = nc["candidates"][labels.index(pick)]
                        st.session_state["queued"] = m["question"].replace(nc["query"], f"{c['name']} ({c['institution']})")
                        st.rerun()
    q = st.session_state.pop("queued", None) or st.chat_input("Ask about faculty, collaborations, papers, citations or the network…")
    if q:
        _respond(q)
        st.rerun()
