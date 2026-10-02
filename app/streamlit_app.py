"""
Streamlit GUI for reviewing the POCC pipeline's duplicate suggestions
(Dealogic vs. Bloomberg bond tranches and loan packages, 1-1 and 1-N).

Run with (from the repo root):
    .venv/bin/streamlit run app/streamlit_app.py

Reads the suggestion exports in input/ and writes each decision straight
into the validated workbooks in output/ -- one row per (left id, right
id) pair, in the format the pipeline README specifies (is_duplicate Y/N,
keep blank or "right"). See README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st

import config
import data as app_data
import state as app_state
import theme
import ui
import workbook

st.set_page_config(page_title="POCC Duplicate Review", layout="wide", page_icon="🖥️")
theme.inject()

STATUS_FILTERS = {
    "Not reviewed": [None],
    "Duplicate": ["dup_left", "dup_right"],
    "Not a duplicate": ["not_dup"],
    "Unsure": ["unsure"],
}


# ---------------------------------------------------------------- loading


def render_file_pickers() -> tuple[str, str, list[tuple[config.ReviewType, str]]]:
    with st.sidebar.expander("Advanced: files & folders"):
        input_dir = st.text_input("Input folder (pipeline exports)", value=config.DEFAULT_INPUT_DIR)
        output_dir = st.text_input("Output folder (validated workbooks)", value=config.DEFAULT_OUTPUT_DIR)
        sources = []
        for rtype in config.REVIEW_TYPES:
            paths = app_data.list_input_files(input_dir, rtype.file_pattern)
            if not paths:
                st.caption(f"{rtype.label}: no file matching `{rtype.file_pattern}`")
                continue
            labels = [os.path.basename(p) for p in paths]
            choice = st.selectbox(rtype.label, labels, index=0, key=f"file__{rtype.key}")
            sources.append((rtype, paths[labels.index(choice)]))
    return input_dir, output_dir, sources


def load_all(sources) -> list[app_data.Item]:
    items = []
    for rtype, path in sources:
        items.extend(app_data.load_items(rtype, path, app_data.mtime(path)))
    return items


def load_decisions(output_dir: str):
    by_workbook = {}
    for name in {rt.workbook for rt in config.REVIEW_TYPES}:
        path = os.path.join(output_dir, name)
        by_workbook[name] = workbook.read_decisions(path, app_data.mtime(path))
    unsure_path = os.path.join(output_dir, config.UNSURE_LOG)
    unsure = workbook.read_unsure(unsure_path, app_data.mtime(unsure_path))
    return by_workbook, unsure


class Status:
    """Per-item status and saved comment, from the workbooks + unsure log."""

    def __init__(self, decisions_by_workbook, unsure):
        self.decisions = decisions_by_workbook
        self.unsure = unsure

    def _found(self, item):
        sheet = self.decisions.get(item.rtype.workbook, {}).get(item.rtype.sheet, {})
        return [sheet[p] for p in item.pairs if p in sheet]

    def __call__(self, item):
        found = self._found(item)
        if found:
            d = found[0]
            if d["is_duplicate"] == "Y":
                return "dup_right" if d["keep"] == config.KEEP_RIGHT_VALUE else "dup_left"
            if d["is_duplicate"] == "N":
                return "not_dup"
        if item.key in self.unsure:
            return "unsure"
        return None

    def comment(self, item) -> str:
        found = self._found(item)
        if found:
            return found[0]["comment"]
        return self.unsure.get(item.key, {}).get("comment", "")


def build_related_index(items):
    """(sheet, side, id) -> item keys, to find other suggestions that touch
    the same deal -- e.g. a tranche that is both in a 1-1 pair and a 1-N
    group, or the 'close competitor' a has_close_competitor flag means."""
    index = {}
    for item in items:
        for side, deal_id in item.deals:
            index.setdefault((item.rtype.workbook, item.rtype.sheet, side, deal_id), set()).add(item.key)
    return index


def related_keys(item, index) -> list[str]:
    keys = set()
    for side, deal_id in item.deals:
        keys |= index.get((item.rtype.workbook, item.rtype.sheet, side, deal_id), set())
    keys.discard(item.key)
    return sorted(keys)


# ---------------------------------------------------------------- sidebar


def render_reviewer(items) -> str:
    assignees = sorted({i.assignee for i in items if i.assignee})
    if st.session_state["reviewer_name"] not in assignees:
        assignees.append(st.session_state["reviewer_name"])
    st.sidebar.selectbox("You are", assignees, key="reviewer_name")
    st.sidebar.checkbox("Only pairs assigned to me", key="only_mine")
    return st.session_state["reviewer_name"]


def render_progress(my_items, status) -> None:
    statuses = [status(i) for i in my_items]
    total = len(statuses)
    reviewed = sum(1 for s in statuses if s is not None and s != "unsure")
    st.sidebar.divider()
    st.sidebar.progress(reviewed / total if total else 0.0)
    st.sidebar.caption(f"{reviewed} of {total} decided (Y/N)")
    counts = {
        "Duplicate": sum(s in ("dup_left", "dup_right") for s in statuses),
        "Not duplicate": statuses.count("not_dup"),
        "Unsure": statuses.count("unsure"),
        "Not reviewed": statuses.count(None),
    }
    cols = st.sidebar.columns(2)
    for i, (label, n) in enumerate(counts.items()):
        cols[i % 2].metric(label, n)


def render_filters(my_items) -> None:
    st.sidebar.divider()
    present_keys = {i.rtype.key for i in my_items}
    present = [rt.label for rt in config.REVIEW_TYPES if rt.key in present_keys]
    st.session_state["filter_types"] = [t for t in st.session_state["filter_types"] if t in present]
    st.sidebar.multiselect("Suggestion table", present, key="filter_types", placeholder="All tables")
    st.sidebar.selectbox("Status", ["All"] + list(STATUS_FILTERS), key="filter_status")
    st.sidebar.checkbox("Only flagged (close competitor / deal in another suggestion)", key="filter_flagged")
    if st.sidebar.button("Reload from disk", width="stretch"):
        st.rerun()
    st.sidebar.caption("Picks up decisions other reviewers have saved since your last click.")


def filter_queue(my_items, status, related_index):
    types = st.session_state["filter_types"]
    wanted = STATUS_FILTERS.get(st.session_state["filter_status"])
    flagged_only = st.session_state["filter_flagged"]
    result = []
    for item in my_items:
        if types and item.rtype.label not in types:
            continue
        if wanted is not None and status(item) not in wanted:
            continue
        if flagged_only and not (item.has_competitor or related_keys(item, related_index)):
            continue
        result.append(item)
    return result


def render_jump(queue, status) -> None:
    if not queue:
        return
    keys = [i.key for i in queue]
    labels = [f"{i.rtype.label} · {i.title} ({ui.STATUS_LABELS[status(i)]})" for i in queue]
    current = st.session_state["current_key"]
    idx = keys.index(current) if current in keys else 0
    choice = st.sidebar.selectbox("Jump to", labels, index=idx)
    chosen = keys[labels.index(choice)]
    if chosen != current:
        app_state.go_to(chosen)
        st.rerun()


# ---------------------------------------------------------------- main panel


def render_nav_header(queue, item, status) -> None:
    keys = [i.key for i in queue]
    in_queue = item.key in keys
    pos = keys.index(item.key) + 1 if in_queue else None
    col_prev, col_mid, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("‹ Previous", width="stretch", shortcut="Left", disabled=not in_queue or pos <= 1):
            app_state.move_relative(keys, -1)
            st.rerun()
    with col_mid:
        where = f"Item {pos} of {len(keys)}" if in_queue else "Outside current filters"
        st.markdown(
            f"<div style='text-align:center'>{where} &nbsp;·&nbsp; {ui.status_chip(status(item))}</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("Next ›", width="stretch", shortcut="Right", disabled=in_queue and pos >= len(keys)):
            app_state.move_relative(keys, 1)
            st.rerun()


def render_item_header(item, related) -> None:
    chips = [ui.score_chip(item.score)]
    if item.has_competitor:
        chips.append(ui.warn_chip("CLOSE COMPETITOR"))
    if related:
        chips.append(ui.warn_chip(f"DEAL IN {len(related)} OTHER SUGGESTION{'S' if len(related) > 1 else ''}"))
    st.markdown(f"### {item.rtype.label} — {item.title}")
    st.markdown(
        " &nbsp; ".join(chips) + f" &nbsp; <span style='color:var(--bbg-grey)'>assigned to {item.assignee or '—'}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"**{item.reason_code}** — {item.reason}")
    if item.has_competitor:
        st.warning(
            "Another candidate for this deal scores within 0.1 of this one. Check both before deciding."
            + ("" if related else " (The competing candidate isn't in the loaded export files.)")
        )


def render_pair(item) -> None:
    rt, row = item.rtype, item.row
    c1, c2, c3 = st.columns(3)
    c1.metric("Date gap (days)", ui.fmt(row.get("date_gap_days"), "num"))
    c2.metric("USD amount diff", ui.fmt(row.get("amount_usd_diff_pct"), "pct"))
    with c3:
        overlap = ui.bank_overlap_caption(row.get(f"banks_{rt.left_side}_shared_{rt.right_side}"), rt.left_side, rt.right_side)
        if overlap:
            st.caption(overlap)

    ui.comparison_table(rt.fields, row, rt.left_side, rt.right_side)

    if rt.has_tranche_lists:
        st.markdown("#### Tranches (largest first)")
        left, right = st.columns(2)
        for col, side in ((left, rt.left_side), (right, rt.right_side)):
            with col:
                st.caption(ui.side_label(side))
                st.dataframe(ui.tranche_table(row.get(f"{side}_tranches")), hide_index=True, width="stretch")

    with st.expander("Raw bank lists"):
        left, right = st.columns(2)
        for col, side in ((left, rt.left_side), (right, rt.right_side)):
            with col:
                st.caption(ui.side_label(side))
                st.text(row.get(f"{side}_banks") or "— (source names no lender)")


def render_group(item) -> None:
    rt = item.rtype
    pivot, members = item.rows[0], list(item.rows[1:])
    pivot_side, member_side = pivot["side"], members[0]["side"] if members else "?"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Match type", pivot.get("match_type") or "—")
    c2.metric(f"Pivot amount ({pivot.get('currency') or '?'} M)", ui.fmt(pivot.get("pivot_amount"), "num"))
    c3.metric("Members sum", ui.fmt(pivot.get("group_sum"), "num"))
    c4.metric("Sum diff", ui.fmt(pivot.get("sum_diff_pct"), "pct"))

    def deal_rows(rows):
        return pd.DataFrame(
            {
                "Deal ID": [r["_id"] for r in rows],
                "Company": [r.get("company") for r in rows],
                "Amount (M)": [ui.fmt(r.get("amount"), "num") for r in rows],
                "Ccy": [r.get("currency") for r in rows],
                "Date": [ui.fmt(r.get("date"), "date") for r in rows],
                "Coupon": [ui.fmt(r.get("coupon"), "num") for r in rows],
                "Maturity": [ui.fmt(r.get("maturity"), "date") for r in rows],
                "Parent banks": [r.get("bank_parents") or "—" for r in rows],
            }
        )

    st.markdown(f"#### Pivot — {ui.side_label(pivot_side)}")
    st.dataframe(deal_rows([pivot]), hide_index=True, width="stretch")
    st.markdown(f"#### Members — {ui.side_label(member_side)} ({len(members)})")
    st.dataframe(deal_rows(members), hide_index=True, width="stretch")
    st.caption(
        f"Company group: {pivot.get('company_group_name') or '—'} ({pivot.get('company_group_id') or '—'}). "
        f"Competing options for this pivot: {ui.fmt(pivot.get('n_competing_options'), 'num')}."
    )


def render_related(item, related, items_by_key, status) -> None:
    if not related:
        return
    st.markdown("#### Other suggestions involving the same deal")
    for key in related:
        other = items_by_key[key]
        c1, c2 = st.columns([5, 1])
        c1.markdown(
            f"{other.rtype.label} · `{other.title}` &nbsp; {ui.score_chip(other.score)} &nbsp; "
            f"{ui.status_chip(status(other))} &nbsp; <span style='color:var(--bbg-grey)'>assigned to {other.assignee}</span>",
            unsafe_allow_html=True,
        )
        c2.button("Open", key=f"open__{item.key}__{key}", on_click=open_item, args=(key,), width="stretch")


def open_item(key: str) -> None:
    """on_click callback: runs before the script, so it may reset filter
    widgets that would otherwise hide the item being opened."""
    st.session_state["only_mine"] = False
    st.session_state["filter_types"] = []
    st.session_state["filter_status"] = "All"
    st.session_state["filter_flagged"] = False
    app_state.go_to(key)


def drop_caption(item) -> str:
    rt = item.rtype
    left_ids = list(dict.fromkeys(l for l, _ in item.pairs))
    right_ids = list(dict.fromkeys(r for _, r in item.pairs))
    unit = " (all tranches)" if rt.id_field == "package_id" else ""
    left, right = ui.side_label(rt.left_side), ui.side_label(rt.right_side)
    return (
        f"Keep **{left}** → drops {right} `{', '.join(right_ids)}`{unit} &nbsp;·&nbsp; "
        f"Keep **{right}** → drops {left} `{', '.join(left_ids)}`{unit} &nbsp;·&nbsp; "
        f"saves {len(item.pairs)} row{'s' if len(item.pairs) > 1 else ''}"
    )


def submit(item, choice, notes, queue, output_dir, reviewer, was_unsure) -> None:
    rt = item.rtype
    wb_path = os.path.join(output_dir, rt.workbook)
    unsure_path = os.path.join(output_dir, config.UNSURE_LOG)
    notes = (notes or "").strip()
    try:
        if choice == "clear":
            workbook.clear_decision(wb_path, rt.sheet, item.pairs)
        elif choice == "unsure":
            # Unsure isn't a valid is_duplicate value, so it lives only in
            # the side log; a previous Y/N for this item is removed.
            workbook.clear_decision(wb_path, rt.sheet, item.pairs)
        else:
            is_dup = "N" if choice == "not_dup" else "Y"
            keep = config.KEEP_RIGHT_VALUE if choice == "dup_right" else config.KEEP_LEFT_VALUE
            workbook.write_decision(wb_path, rt.sheet, item.pairs, is_dup, keep, notes)
        if choice == "unsure" or was_unsure:
            action = "unsure" if choice == "unsure" else "cleared"
            workbook.log_unsure(unsure_path, action, item.key, rt.workbook, rt.sheet, item.pairs, reviewer, notes)
    except (workbook.WorkbookBusy, FileNotFoundError, KeyError, PermissionError, OSError) as e:
        st.error(f"Not saved: {e}")
        return

    workbook.read_decisions.clear()
    workbook.read_unsure.clear()
    app_state.clear_notes(item.key)
    st.toast("CLEARED" if choice == "clear" else f"SAVED: {ui.STATUS_LABELS[choice].upper()}")
    if choice != "clear":
        app_state.move_relative([i.key for i in queue], 1)
    st.rerun()


def render_decision(item, status, queue, output_dir, reviewer) -> None:
    """Pinned to the bottom of the viewport (theme.py styles the
    st-key-decision_bar class Streamlit gives this keyed container), so
    the comment box and buttons stay in reach while scrolling the evidence."""
    rt = item.rtype
    nk = app_state.notes_key(item.key)
    if nk not in st.session_state:
        st.session_state[nk] = status.comment(item)
    was_unsure = status(item) == "unsure"
    with st.container(key="decision_bar"):
        col_caption, col_clear = st.columns([5, 1], vertical_alignment="center")
        col_caption.markdown(drop_caption(item))
        if status(item) is not None and col_clear.button("Clear decision", type="tertiary"):
            submit(item, "clear", st.session_state[nk], queue, output_dir, reviewer, was_unsure)

        left, right = ui.side_label(rt.left_side), ui.side_label(rt.right_side)

        col_notes, col_buttons = st.columns([2, 3])
        with col_notes:
            notes = st.text_area(
                "Comment", key=nk, height=90, label_visibility="collapsed", placeholder="Comment (optional)"
            )
        with col_buttons:
            b1, b2 = st.columns(2)
            b3, b4 = st.columns(2)
            if b1.button(f"DUPLICATE — KEEP {left}", width="stretch", shortcut="1"):
                submit(item, "dup_left", notes, queue, output_dir, reviewer, was_unsure)
            if b2.button(f"DUPLICATE — KEEP {right}", width="stretch", shortcut="2"):
                submit(item, "dup_right", notes, queue, output_dir, reviewer, was_unsure)
            if b3.button("NOT A DUPLICATE", width="stretch", shortcut="3"):
                submit(item, "not_dup", notes, queue, output_dir, reviewer, was_unsure)
            if b4.button("UNSURE", width="stretch", shortcut="4"):
                submit(item, "unsure", notes, queue, output_dir, reviewer, was_unsure)


def render_how_to_guide() -> None:
    with st.expander("HOW TO USE THIS TOOL", expanded=False):
        st.markdown(
            """
This tool walks you through the pipeline's duplicate suggestions (Dealogic vs. Bloomberg) and writes your decision straight into the validated workbooks in `output/` — the same rows you would otherwise type by hand: the two ids, `is_duplicate` = **Y** or **N**, and `keep (default left)`.

**Decisions**
- **Duplicate — keep Dealogic**: writes `Y` with the keep column blank (the pipeline's default, keep left). The Bloomberg side is dropped on the next pipeline run.
- **Duplicate — keep Bloomberg**: writes `Y` with `right` in the keep column. The Dealogic side is dropped.
- **Not a duplicate**: writes `N`. Both are kept and the pair leaves the suggestions.
- **Unsure**: nothing goes into the workbook (the pipeline only accepts Y/N). The item is logged in `output/unsure_pairs.csv` with your comment so it can be discussed.
- **Clear decision**: removes the item's rows from the workbook, back to not reviewed.
- Every button saves immediately; there's nothing to export. The caption above the buttons spells out which ids the pipeline will drop.

**1-N groups**
One pivot deal on one side matches several deals on the other whose amounts add up to it. One decision covers the whole group and writes one row per pivot–member pair, all with the same keep value (mixed keep values in a group make the pipeline drop both sides). The group belongs to whoever is assigned its pivot row.

**Loan packages**
Confirming a package pair drops every tranche of the dropped package. If the tranches match one to one, they should be validated in the tranche tab instead — check the tranche lists.

**Reading the evidence**
- The comparison table marks each field: `=` matches, yellow `≠`/`Δ` is a small or cosmetic difference, red is a real conflict, `—` means one side is missing.
- Score 2 is a strict rule (e.g. same ISIN and amount); 0–1 is the fuzzy multi-criteria rule, and closer to 1 means closer amounts and dates. Scores are triage, not the answer.
- **Close competitor**: another candidate for the same deal scores within 0.1. **Deal in other suggestion**: the same deal id also appears in another pair or group — open it from the list and decide them together.
- Bank overlap `3, 2, 5` means left names 3 parent banks, 2 are shared, right names 5. A 0 usually means the source names no lender.

**Keyboard shortcuts**
- `1` duplicate, keep left · `2` duplicate, keep right · `3` not a duplicate · `4` unsure
- `←` / `→` previous / next item
- Shortcuts are ignored while you're typing in the comment box: click outside it (or press Tab) first, then press the key. Clear decision has no shortcut on purpose.

**Working alongside others**
The workbooks are shared. Each save re-reads the file first so others' decisions are kept, but click **Reload from disk** to see their latest work, and close the workbook in Excel while the app is saving (it refuses to write while Excel has it open). Decisions show up in the pipeline dashboard after its next run.
            """
        )


def main():
    app_state.init_state()
    st.sidebar.title("POCC Duplicate Review")
    _, output_dir, sources = render_file_pickers()
    if not sources:
        st.error("No suggestion exports found. Check the input folder under 'Advanced: files & folders'.")
        st.stop()

    items = load_all(sources)
    items_by_key = {i.key: i for i in items}
    decisions, unsure = load_decisions(output_dir)
    status = Status(decisions, unsure)
    related_index = build_related_index(items)

    reviewer = render_reviewer(items)
    my_items = [
        i for i in items if not st.session_state["only_mine"] or i.assignee.casefold() == reviewer.casefold()
    ]
    render_progress(my_items, status)
    render_filters(my_items)
    queue = filter_queue(my_items, status, related_index)
    render_jump(queue, status)

    st.title("POCC — Duplicate Review")
    render_how_to_guide()

    missing = [rt.workbook for rt in config.REVIEW_TYPES if not os.path.exists(os.path.join(output_dir, rt.workbook))]
    if missing:
        st.error(f"Validated workbook(s) not found in {output_dir}: {', '.join(sorted(set(missing)))}")

    if not queue:
        st.info("Nothing matches the current filters.")
        return
    current = st.session_state["current_key"]
    if current not in {i.key for i in queue}:
        current = queue[0].key
        app_state.go_to(current)

    item = items_by_key[current]
    related = related_keys(item, related_index)
    render_nav_header(queue, item, status)
    render_item_header(item, related)
    if item.rtype.kind == "group":
        render_group(item)
    else:
        render_pair(item)
    render_related(item, related, items_by_key, status)
    render_decision(item, status, queue, output_dir, reviewer)


if __name__ == "__main__":
    main()
