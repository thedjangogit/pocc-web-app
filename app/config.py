"""
One ReviewType per pipeline suggestion table. Each says where its input
file lives, how to read it ("pair" = one 1-1 row per suggestion,
"group" = 1-N rows sharing a match_group_id), and which tab of which
validated workbook its decisions go into -- the same mapping as the
pipeline README's suggestion-table table.

Adding a suggestion table the pipeline starts exporting (loan tranches,
IJGlobal, loan packages 1-N) should be a new entry here, not new code --
as long as its columns follow the same <side>_<field> naming.
"""

import os
from dataclasses import dataclass, field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INPUT_DIR = os.path.join(REPO_ROOT, "input")
DEFAULT_OUTPUT_DIR = os.path.join(REPO_ROOT, "output")

BOND_WORKBOOK = "validated_bond_duplicates.xlsx"
LOAN_WORKBOOK = "validated_loan_duplicates.xlsx"
UNSURE_LOG = "unsure_pairs.csv"

# Output-sheet columns other than the two id columns (which vary per tab).
IS_DUPLICATE_COL = "is_duplicate"
KEEP_COL = "keep (default left)"
COMMENT_COL = "comment"

# The pipeline accepts only "right" in the keep column; per its README
# "any other value stops the pipeline", so keep-left is a blank cell.
KEEP_LEFT_VALUE = ""
KEEP_RIGHT_VALUE = "right"

SOURCE_LABELS = {"dlg": "Dealogic", "bbg": "Bloomberg", "ijg": "IJGlobal", "dlgbbg": "Dealogic/Bloomberg"}


@dataclass(frozen=True)
class Field:
    """One comparison row. column is the suffix after '<side>_'."""

    label: str
    column: str
    fmt: str = "text"  # text | date | num | pct | multiline
    compare: bool = True


@dataclass(frozen=True)
class ReviewType:
    key: str
    label: str
    file_pattern: str
    kind: str  # "pair" | "group"
    workbook: str
    sheet: str
    left_side: str
    right_side: str
    id_field: str  # e.g. "deal_id" -> dlg_deal_id / bbg_deal_id
    fields: tuple[Field, ...] = field(default_factory=tuple)
    has_tranche_lists: bool = False

    @property
    def left_col(self) -> str:
        return f"{self.left_side}_{self.id_field}"

    @property
    def right_col(self) -> str:
        return f"{self.right_side}_{self.id_field}"


BOND_FIELDS = (
    Field("Company", "company"),
    Field("Company group", "company_group_name"),
    Field("Group ID", "company_group_id"),
    Field("Date", "date", "date"),
    Field("Maturity", "maturity", "date"),
    Field("Currency", "currency"),
    Field("Amount (local, M)", "amount_local", "num"),
    Field("Amount (USD, M)", "amount_usd", "num"),
    Field("Coupon", "coupon", "num"),
    Field("ISIN", "isin"),
    Field("CUSIP", "cusip"),
    Field("Package ID", "package_id", compare=False),
    Field("Parent banks", "bank_parents", "multiline", compare=False),
)

LOAN_PACKAGE_FIELDS = (
    Field("Company", "company"),
    Field("Company group", "company_group_name"),
    Field("Group ID", "company_group_id"),
    Field("Date (earliest tranche)", "date", "date"),
    Field("Amount (USD, M, sum)", "amount_usd", "num"),
    Field("# tranches", "nb_tranches", "num"),
    Field("Parent banks", "bank_parents", "multiline", compare=False),
)

REVIEW_TYPES = (
    ReviewType(
        key="bond_tranches_1_1",
        label="Bond tranches 1-1",
        file_pattern="pocc___bond_tranches_1_1_*.xlsx",
        kind="pair",
        workbook=BOND_WORKBOOK,
        sheet="tranches dlg v bbg",
        left_side="dlg",
        right_side="bbg",
        id_field="deal_id",
        fields=BOND_FIELDS,
    ),
    ReviewType(
        key="bond_tranches_1_n",
        label="Bond tranches 1-N",
        file_pattern="pocc___bond_tranches_1_n_*.xlsx",
        kind="group",
        workbook=BOND_WORKBOOK,
        sheet="tranches dlg v bbg",
        left_side="dlg",
        right_side="bbg",
        id_field="deal_id",
    ),
    ReviewType(
        key="loan_packages_1_1",
        label="Loan packages 1-1",
        file_pattern="pocc___loan_packages_1_1_*.xlsx",
        kind="pair",
        workbook=LOAN_WORKBOOK,
        sheet="packages dlg v bbg",
        left_side="dlg",
        right_side="bbg",
        id_field="package_id",
        fields=LOAN_PACKAGE_FIELDS,
        has_tranche_lists=True,
    ),
)

REVIEW_TYPES_BY_KEY = {rt.key: rt for rt in REVIEW_TYPES}
