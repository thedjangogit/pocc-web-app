"""
Pure rendering helpers -- comparison table, status/score chips, value
formatting, tranche-list parsing. No file I/O lives here.

Colors reference the CSS custom properties set up in theme.py's injected
stylesheet (--bbg-green/red/yellow/grey/amber/cyan) rather than literal
hex values, so the two stay in sync from one place.
"""

import html
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from config import Field, SOURCE_LABELS

# Plain-text labels for contexts that can't render HTML (selectbox options).
STATUS_LABELS = {
    "dup_left": "Duplicate, keep left",
    "dup_right": "Duplicate, keep right",
    "not_dup": "Not a duplicate",
    "unsure": "Unsure",
    None: "Not reviewed",
}
_STATUS_TAG_TEXT = {
    "dup_left": "DUP · KEEP LEFT",
    "dup_right": "DUP · KEEP RIGHT",
    "not_dup": "NOT DUPLICATE",
    "unsure": "UNSURE",
    None: "NOT REVIEWED",
}
_STATUS_COLORS = {
    "dup_left": "var(--bbg-red)",
    "dup_right": "var(--bbg-red)",
    "not_dup": "var(--bbg-green)",
    "unsure": "var(--bbg-yellow)",
    None: "var(--bbg-grey)",
}

# Text fields where any difference is a real red flag; other text fields
# (company names) routinely differ in formatting across vendors.
_STRICT_TEXT = {"company_group_id", "isin", "cusip", "currency"}


def is_blank(value) -> bool:
    return value is None or value == "" or (isinstance(value, float) and pd.isna(value))


def side_label(side: str) -> str:
    return SOURCE_LABELS.get(side, side.upper())


def _tag(text: str, color: str) -> str:
    return (
        f'<span style="color:{color};border:1px solid {color};padding:1px 7px;'
        f'border-radius:2px;font-weight:700;font-size:0.78rem;letter-spacing:0.03em;'
        f'white-space:nowrap;">{html.escape(text)}</span>'
    )


def status_chip(status) -> str:
    return _tag(_STATUS_TAG_TEXT.get(status, "NOT REVIEWED"), _STATUS_COLORS.get(status, "var(--bbg-grey)"))


def score_chip(score) -> str:
    """2 is a strict rule; 0-1 is the fuzzy multi_criteria rule (pipeline README)."""
    if is_blank(score):
        return _tag("SCORE —", "var(--bbg-grey)")
    if score >= 1.5:
        color = "var(--bbg-green)"
    elif score >= 0.75:
        color = "var(--bbg-yellow)"
    else:
        color = "var(--bbg-red)"
    return _tag(f"SCORE {score:g}", color)


def warn_chip(text: str) -> str:
    return _tag(text, "var(--bbg-yellow)")


def fmt(value, kind: str = "text") -> str:
    if is_blank(value):
        return "—"
    if kind == "date" and isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if kind == "num" and isinstance(value, (int, float)):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if kind == "pct" and isinstance(value, (int, float)):
        return f"{value * 100:.2f}%"
    return str(value)


def _cell(value, kind: str) -> str:
    text = html.escape(fmt(value, kind))
    return text.replace("\n", "<br>") if kind == "multiline" else text


def _compare(f: Field, left, right) -> tuple[str, str]:
    """(row css class, marker html) for one field."""
    if not f.compare:
        return "", ""
    if is_blank(left) or is_blank(right):
        return "", '<span style="color:var(--bbg-grey)">—</span>'
    ok = '<span style="color:var(--bbg-green)">=</span>'
    if f.fmt == "date" and isinstance(left, datetime) and isinstance(right, datetime):
        days = abs((left - right).days)
        if days == 0:
            return "", ok
        cls = "near" if days <= 7 else "diff"
        color = "var(--bbg-yellow)" if cls == "near" else "var(--bbg-red)"
        return cls, f'<span style="color:{color}">Δ {days}d</span>'
    if f.fmt == "num" and isinstance(left, (int, float)) and isinstance(right, (int, float)):
        denom = max(abs(left), abs(right))
        rel = abs(left - right) / denom if denom else 0.0
        if rel <= 0.005:
            return "", ok
        return "diff", f'<span style="color:var(--bbg-red)">Δ {rel * 100:.1f}%</span>'
    if str(left).strip().casefold() == str(right).strip().casefold():
        return "", ok
    if f.column in _STRICT_TEXT:
        return "diff", '<span style="color:var(--bbg-red)">≠</span>'
    return "near", '<span style="color:var(--bbg-yellow)">≠</span>'


def comparison_table(fields, row: dict, left_side: str, right_side: str) -> None:
    head = (
        f"<tr><th></th><th>{html.escape(side_label(left_side))} (left)</th>"
        f"<th>{html.escape(side_label(right_side))} (right)</th><th></th></tr>"
    )
    body = []
    for f in fields:
        left = row.get(f"{left_side}_{f.column}")
        right = row.get(f"{right_side}_{f.column}")
        cls, marker = _compare(f, left, right)
        body.append(
            f'<tr class="{cls}"><td class="lbl">{html.escape(f.label)}</td>'
            f'<td class="val">{_cell(left, f.fmt)}</td><td class="val">{_cell(right, f.fmt)}</td>'
            f'<td class="mk">{marker}</td></tr>'
        )
    st.markdown(f'<table class="cmp">{head}{"".join(body)}</table>', unsafe_allow_html=True)


def bank_overlap_caption(value, left_side: str, right_side: str) -> str | None:
    """banks_dlg_shared_bbg is 'left named, shared, right named' (pipeline README)."""
    if is_blank(value):
        return None
    parts = [p.strip() for p in str(value).split(",")]
    if len(parts) != 3:
        return f"Parent-bank overlap: {value}"
    left_n, shared, right_n = parts
    text = (
        f"Parent banks — {side_label(left_side)} names {left_n}, "
        f"{side_label(right_side)} names {right_n}, shared {shared}."
    )
    if left_n == "0" or right_n == "0":
        text += " (0 = source names no lender, which is common.)"
    return text


_TRANCHE_RE = re.compile(r"^(?P<id>\S+) - (?P<amount>[\d.,]+) M (?P<ccy>\S+), (?P<start>\S+) -> (?P<end>\S+)$")


def tranche_table(text) -> pd.DataFrame:
    rows = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = _TRANCHE_RE.match(line)
        if m:
            rows.append(
                {
                    "Tranche": m["id"],
                    "Amount (M)": m["amount"],
                    "Ccy": m["ccy"],
                    "Start": m["start"],
                    "Maturity": m["end"],
                }
            )
        else:
            rows.append({"Tranche": line})
    return pd.DataFrame(rows)
