"""
st.session_state initialization and queue navigation.

current_key tracks the actual item key, not a list index -- filters
change the visible queue's length on every rerun, and a real key survives
that cleanly where a position would not.
"""

import streamlit as st

DEFAULT_REVIEWER = "Caleb"


def init_state() -> None:
    defaults = {
        "reviewer_name": DEFAULT_REVIEWER,
        "only_mine": True,
        "current_key": None,
        "filter_types": [],
        "filter_status": "All",
        "filter_flagged": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go_to(key: str) -> None:
    st.session_state["current_key"] = key


def move_relative(keys: list[str], delta: int) -> None:
    if not keys:
        return
    current = st.session_state["current_key"]
    if current not in keys:
        go_to(keys[0])
        return
    idx = keys.index(current)
    go_to(keys[max(0, min(len(keys) - 1, idx + delta))])


def notes_key(item_key: str) -> str:
    return f"notes__{item_key}"


def clear_notes(item_key: str) -> None:
    st.session_state.pop(notes_key(item_key), None)
