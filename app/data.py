"""
Loads the pipeline's suggestion exports into a flat list of review items.
One item is one decision the reviewer makes: a 1-1 row, or a whole 1-N
group. Every item knows the (left_id, right_id) pairs its decision writes
to the validated workbook, so the rest of the app never has to care which
kind it is when saving or computing status.

Cache keys are (path, mtime) primitives, as in the SEA app: a new export
dropped into input/ shows up on the next rerun, with no manual
invalidation.
"""

import glob
import os
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from config import ReviewType


@dataclass(frozen=True)
class Item:
    key: str
    rtype: ReviewType
    assignee: str
    score: float | None
    reason_code: str
    reason: str
    has_competitor: bool
    pairs: tuple[tuple[str, str], ...]
    deals: frozenset[tuple[str, str]]  # (side, id) for every deal involved
    title: str
    row: dict | None = None  # pair kind
    rows: tuple[dict, ...] = ()  # group kind, pivot first


def list_input_files(input_dir: str, pattern: str) -> list[str]:
    """Not cached -- a cheap glob, so a fresh export appears without a restart."""
    paths = glob.glob(os.path.join(input_dir, pattern))
    return sorted(paths, key=os.path.getmtime, reverse=True)


def mtime(path: str) -> float:
    return os.path.getmtime(path) if path and os.path.exists(path) else 0.0


# No leading underscore on file_mtime: Streamlit skips hashing underscored
# args, which would leave the cache keyed on path alone.
@st.cache_data(show_spinner=False)
def _read_input(path: str, file_mtime: float) -> pd.DataFrame:
    df = pd.read_excel(path)
    # The assignee column is unnamed in some exports ("Assign to" in others).
    df = df.rename(columns={df.columns[0]: "assignee"})
    df["assignee"] = df["assignee"].fillna("").astype(str).str.strip().str.title()
    return df


def _clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in rec.items()} for rec in df.to_dict("records")]


def _float_or_none(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _pair_items(rtype: ReviewType, df: pd.DataFrame) -> list[Item]:
    items = []
    for row in _records(df):
        left, right = str(row[rtype.left_col]), str(row[rtype.right_col])
        company = row.get(f"{rtype.left_side}_company") or row.get(f"{rtype.right_side}_company") or ""
        items.append(
            Item(
                key=f"{rtype.key}:{left}|{right}",
                rtype=rtype,
                assignee=row["assignee"],
                score=_float_or_none(row.get("score")),
                reason_code=row.get("suggestion_reason_code") or "",
                reason=row.get("suggestion_reason") or "",
                has_competitor=bool(row.get("has_close_competitor")),
                pairs=((left, right),),
                deals=frozenset({(rtype.left_side, left), (rtype.right_side, right)}),
                title=f"{left} ↔ {right} — {company}",
                row=row,
            )
        )
    return items


def _group_items(rtype: ReviewType, df: pd.DataFrame) -> list[Item]:
    items = []
    for group_id, gdf in df.groupby("match_group_id", sort=False):
        rows = _records(gdf)
        pivots = [r for r in rows if r.get("is_pivot")]
        if len(pivots) != 1:
            st.warning(f"{rtype.label}: group {group_id} has {len(pivots)} pivot rows; skipped.")
            continue
        pivot = pivots[0]
        members = [r for r in rows if not r.get("is_pivot")]
        for r in rows:
            r["_id"] = str(r[f"{r['side']}_{rtype.id_field}"])

        if pivot["side"] == rtype.left_side:
            pairs = tuple((pivot["_id"], m["_id"]) for m in members)
        else:
            pairs = tuple((m["_id"], pivot["_id"]) for m in members)

        items.append(
            Item(
                key=f"{rtype.key}:{group_id}",
                rtype=rtype,
                # Exports assign each row of a group round-robin; the group
                # is one decision, so it belongs to whoever has the pivot.
                assignee=pivot["assignee"],
                score=_float_or_none(pivot.get("score")),
                reason_code=pivot.get("suggestion_reason_code") or "",
                reason=pivot.get("suggestion_reason") or "",
                has_competitor=(_float_or_none(pivot.get("n_competing_options")) or 1) > 1,
                pairs=pairs,
                deals=frozenset((r["side"], r["_id"]) for r in rows),
                title=f"{group_id} ({pivot.get('match_type', '')}, {len(members)} members) — {pivot.get('company', '')}",
                rows=tuple([pivot] + members),
            )
        )
    return items


@st.cache_data(show_spinner="Loading suggestions...")
def load_items(rtype: ReviewType, path: str, file_mtime: float) -> list[Item]:
    df = _read_input(path, file_mtime)
    return _group_items(rtype, df) if rtype.kind == "group" else _pair_items(rtype, df)
