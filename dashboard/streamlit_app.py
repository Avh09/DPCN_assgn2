"""Research Atlas on Streamlit: the static dashboard (index.html + app.js + data.js) plus the AI Research Assistant page.

Streamlit cannot serve HTML/JS files directly, so the page, its scripts, styles, fonts and data are
inlined into a single HTML document and shown full-window in a component iframe.

Local run:   streamlit run dashboard/streamlit_app.py
Streamlit Community Cloud: main file path = dashboard/streamlit_app.py (requirements in dashboard/requirements.txt)
"""
import base64
import hmac
import json
import re
from pathlib import Path

import sys

import streamlit as st
import streamlit.components.v1 as components


def check_password() -> bool:
    """Shared-password gate for both pages. The password is the APP_PASSWORD secret
    (Streamlit Cloud: App -> Settings -> Secrets; locally: .streamlit/secrets.toml, not committed)."""
    if st.session_state.get("authenticated", False):
        return True
    try:
        expected = st.secrets["APP_PASSWORD"]
    except Exception:          # no secrets file / key missing (the exception type differs between Streamlit versions)
        expected = ""
    if not expected:          # fail closed: no password configured means nobody gets in
        st.error("APP_PASSWORD is not set in the app's secrets, so the Research Atlas is locked.")
        return False
    st.title("Research Atlas – Login")
    st.write("Enter the password to access the Research Atlas.")
    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        if hmac.compare_digest(password.encode(), str(expected).encode()):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))          # the assistant package, config.py and collab_model.py live in the repository root

st.set_page_config(page_title="Research Atlas · Group 15", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
if not check_password():          # neither page loads until the visitor has logged in
    st.stop()


def _stamp() -> float:
    """Newest modification time of the dashboard files, so edits show up without restarting Streamlit."""
    return max(p.stat().st_mtime for p in HERE.glob("*") if p.suffix in {".html", ".js", ".css"})


@st.cache_resource(show_spinner="Loading the dashboard…", max_entries=32)
def _build_page(stamp: float, start_hash: str = "") -> str:
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
    if start_hash:      # open on a given tab/filter, e.g. "reach?i=Jadavpur University&inst=1" (links from the assistant)
        html = html.replace("window.__startHash = location.hash.slice(1);", "window.__startHash = " + json.dumps(start_hash) + ";", 1)
    return html


def build_page(start_hash: str = "") -> str:
    return _build_page(_stamp(), start_hash)


def dashboard_page():
    """Full-window dashboard below the top navigation bar."""
    st.markdown(
        """<style>
        footer, #MainMenu, [data-testid="stDecoration"], .stAppDeployButton { display: none !important; }
        .block-container, [data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
        iframe { position: fixed; top: 3.75rem; left: 0; display: block; width: 100vw !important; height: calc(100vh - 3.75rem) !important; border: 0; z-index: 1000; }
        </style>""",
        unsafe_allow_html=True,
    )
    html = build_page(st.session_state.pop("dash_hash", ""))
    if st.session_state.get("messages"):          # the visitor came from (or has used) the assistant: offer the way back, conversation kept
        st.markdown("<style>.st-key-backbtn { position: fixed; left: 1rem; bottom: 1rem; z-index: 2000; width: auto; }</style>", unsafe_allow_html=True)
        with st.container(key="backbtn"):
            if st.button("← Back to AI Assistant"):
                st.switch_page(st.session_state["_pages"]["assistant"])
    if hasattr(st, "iframe"):          # st.components.v1.html is removed in current Streamlit
        st.iframe(html, height=1000)
    else:
        components.html(html, height=1000, scrolling=True)


def assistant_page():
    from assistant import ui
    ui.render()


pages = [st.Page(dashboard_page, title="Dashboard", icon="📊", url_path="dashboard", default=True),
         st.Page(assistant_page, title="AI Research Assistant", icon="🤖", url_path="assistant")]
st.session_state["_pages"] = {"dashboard": pages[0], "assistant": pages[1]}      # for st.switch_page from either page
try:
    nav = st.navigation(pages, position="top")          # Streamlit >= 1.46
except TypeError:
    nav = st.navigation(pages)
nav.run()
