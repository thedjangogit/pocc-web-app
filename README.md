# POCC duplicate review

A Streamlit app for manually reviewing the POCC pipeline's duplicate
suggestions (Dealogic vs. Bloomberg) and recording decisions in the
validated workbooks the pipeline reads.

## Setup

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

## Run

From the repo root:

```sh
.venv/bin/streamlit run app/streamlit_app.py
```

- `input/` holds the pipeline's suggestion exports:
  `pocc___bond_tranches_1_1_*`, `pocc___bond_tranches_1_n_*`,
  `pocc___loan_packages_1_1_*`, `pocc___loan_tranches_1_1_*` and
  `pocc___loan_tranches_1_n_*` (`.xlsx`). The newest file per table is
  picked by default; a table with no file is simply skipped.
- `output/` holds `validated_bond_duplicates.xlsx` and
  `validated_loan_duplicates.xlsx`. Both folders can be pointed elsewhere
  (e.g. the shared drive) under *Advanced: files & folders* in the sidebar.

## What gets written

Each decision is saved immediately into the matching tab, one row per
(left id, right id) pair, following the pipeline README:

| Button | `is_duplicate` | `keep (default left)` |
|---|---|---|
| Duplicate — keep Dealogic | `Y` | blank |
| Duplicate — keep Bloomberg | `Y` | `right` |
| Not a duplicate | `N` | blank |

A 1-N group writes one row per pivot–member pair, all with the same keep
value. **Unsure** writes nothing to the workbook (the pipeline accepts
only Y/N); it is logged to `output/unsure_pairs.csv` instead.

## Shared-drive caveat (pilot)

Every save re-reads the workbook from disk right before writing, so
decisions saved by other reviewers are preserved, and the app refuses to
write while Excel has the file open. Two saves landing at the same
moment, or a drive-sync conflict copy, can still lose a write. Merging
per-reviewer files into the validated workbook is deferred until after
the pilot.

## Adding a suggestion table

Add a `ReviewType` entry in `app/config.py` (file pattern, `pair` or
`group`, workbook, tab, id columns, fields to compare).
