"""
Bloomberg-terminal-style CSS for the duplicate-review app: black
background, amber/monospace chrome, and bracket-tag status colors
(green/yellow/red/grey) that ui.py's chip helpers reference via the same
CSS custom properties defined here, so the two never drift apart.

.streamlit/config.toml sets the base theme (dark, black background,
amber primary, monospace font) that Streamlit's own built-in components
(st.dataframe's grid in particular, which renders on canvas and can't be
reached by CSS) read directly. This module layers finer-grained styling
on top via injected CSS for everything CSS *can* reach.
"""

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');

:root {
  --bbg-bg: #000000;
  --bbg-panel: #0d0d0d;
  --bbg-border: #262626;
  --bbg-amber: #FF9F1C;
  --bbg-green: #00E676;
  --bbg-red: #FF3B30;
  --bbg-yellow: #FFD60A;
  --bbg-grey: #8A8F98;
  --bbg-cyan: #00D9FF;
  --bbg-text: #E8E8E8;
}

html, body, [class*="css"], .stApp, .stMarkdown, p, span, div, input, textarea, button, li {
  font-family: 'IBM Plex Mono', 'Roboto Mono', monospace !important;
  font-variant-numeric: tabular-nums;
}

/* Streamlit's own icons (expander chevrons, sidebar collapse arrow, etc.)
   are font-ligature glyphs in Material Symbols -- the blanket monospace
   rule above breaks them into literal text like "keyboard_arrow_right"
   if not excluded here. */
[data-testid="stIconMaterial"] {
  font-family: 'Material Symbols Rounded' !important;
}

.stApp { background-color: var(--bbg-bg) !important; }
header[data-testid="stHeader"] { background-color: var(--bbg-bg) !important; }

h1, h2, h3, h4 {
  color: var(--bbg-amber) !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600 !important;
}
h1 { border-bottom: 2px solid var(--bbg-amber); padding-bottom: 8px; }

strong { color: var(--bbg-amber); }

[data-testid="stSidebar"] {
  background-color: var(--bbg-panel) !important;
  border-right: 1px solid var(--bbg-amber);
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: var(--bbg-amber) !important;
}

.stButton > button {
  background-color: #000 !important;
  color: var(--bbg-amber) !important;
  border: 1px solid var(--bbg-amber) !important;
  border-radius: 2px !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.stButton > button:hover:not(:disabled) {
  background-color: var(--bbg-amber) !important;
  color: #000 !important;
}
.stButton > button:disabled {
  color: var(--bbg-grey) !important;
  border-color: var(--bbg-grey) !important;
}

[data-testid="stMetric"] {
  background-color: var(--bbg-panel) !important;
  border: 1px solid var(--bbg-border) !important;
  border-radius: 2px !important;
  padding: 8px 10px !important;
}
[data-testid="stMetricLabel"] {
  color: var(--bbg-grey) !important;
  text-transform: uppercase;
  font-size: 0.72rem !important;
  letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] { color: var(--bbg-amber) !important; font-weight: 700 !important; }

.stProgress > div > div > div { background-color: var(--bbg-amber) !important; }
.stProgress > div > div { background-color: #1a1a1a !important; }

[data-testid="stAlert"] {
  background-color: var(--bbg-panel) !important;
  border-radius: 2px !important;
  border: 1px solid var(--bbg-border) !important;
  border-left: 3px solid var(--bbg-amber) !important;
}
[data-testid="stAlertContentInfo"] { border-left-color: var(--bbg-cyan) !important; }
[data-testid="stAlertContentWarning"] { border-left-color: var(--bbg-yellow) !important; }
[data-testid="stAlertContentError"] { border-left-color: var(--bbg-red) !important; }

[data-testid="stExpander"] {
  border: 1px solid var(--bbg-border) !important;
  border-radius: 2px !important;
  background-color: var(--bbg-panel) !important;
}
[data-testid="stExpander"] summary {
  color: var(--bbg-amber) !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

input, textarea, [data-baseweb="select"] > div, [data-baseweb="base-input"] {
  background-color: #0a0a0a !important;
  color: var(--bbg-text) !important;
  border: 1px solid var(--bbg-border) !important;
  border-radius: 2px !important;
}
input:focus, textarea:focus { border-color: var(--bbg-amber) !important; box-shadow: none !important; }

hr { border-color: var(--bbg-border) !important; }

code {
  background-color: #1a1a1a !important;
  color: var(--bbg-amber) !important;
  border-radius: 2px;
}

[data-testid="stCaptionContainer"] { color: var(--bbg-grey) !important; }

[data-testid="stToast"] {
  background-color: var(--bbg-panel) !important;
  border: 1px solid var(--bbg-amber) !important;
  color: var(--bbg-text) !important;
}

/* Side-by-side comparison table rendered by ui.comparison_table(). */
table.cmp { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
table.cmp th {
  color: var(--bbg-amber); text-align: left; text-transform: uppercase;
  font-size: 0.75rem; letter-spacing: 0.05em;
  border-bottom: 1px solid var(--bbg-amber); padding: 6px 8px;
}
table.cmp td { border-bottom: 1px solid var(--bbg-border); padding: 6px 8px; vertical-align: top; color: var(--bbg-text); }
table.cmp td.lbl { color: var(--bbg-grey); text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em; white-space: nowrap; }
table.cmp td.mk { white-space: nowrap; font-weight: 700; font-size: 0.78rem; }
table.cmp tr.diff td.val { color: var(--bbg-red); }
table.cmp tr.near td.val { color: var(--bbg-yellow); }
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
