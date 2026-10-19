"""Research Atlas on Streamlit: serves the static dashboard (index.html + app.js + data.js) as one page.

Streamlit cannot serve HTML/JS files directly, so the page, its scripts, styles, fonts and data are
inlined into a single HTML document and shown full-window in a component iframe.

Local run:   streamlit run dashboard/streamlit_app.py
Streamlit Community Cloud: main file path = dashboard/streamlit_app.py (requirements in dashboard/requirements.txt)
"""
import base64
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent

st.set_page_config(page_title="Research Atlas · Group 15", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")


@st.cache_resource(show_spinner="Loading the dashboard…")
def build_page() -> str:
    html = (HERE / "index.html").read_text(encoding="utf-8")

    def script(match):
        src = match.group(1)
        code = (HERE / src).read_text(encoding="utf-8").replace("</script", "<\\/script")
        return f"<script>{code}</script>"

    def style(match):
        href = match.group(1)
        css = (HERE / href).read_text(encoding="utf-8")
        base = (HERE / href).parent

        def font(m):  # inline fonts referenced from the stylesheet
            f = base / m.group(1)
            if not f.exists():
                return m.group(0)
            return "url(data:font/woff2;base64," + base64.b64encode(f.read_bytes()).decode() + ")"

        return "<style>" + re.sub(r"url\(([^)\"':]+\.woff2)\)", font, css) + "</style>"

    html = re.sub(r'<script src="([^"]+)"></script>', script, html)
    html = re.sub(r'<link rel="stylesheet" href="([^"]+)">', style, html)
    return html


# full-window dashboard: hide Streamlit chrome and let the component fill the viewport
st.markdown(
    """<style>
    header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
    .block-container, [data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
    [data-testid="stAppViewContainer"] > .main, section.main { padding: 0 !important; }
    iframe { position: fixed; inset: 0; display: block; width: 100vw !important; height: 100vh !important; border: 0; z-index: 1000; }
    </style>""",
    unsafe_allow_html=True,
)
components.html(build_page(), height=1000, scrolling=True)
