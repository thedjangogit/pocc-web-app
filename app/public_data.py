"""
Public-data lookups for the "Search public data" button. Currently one
source: OpenFIGI (Bloomberg's open security-identifier service), which
maps an ISIN, CUSIP or Bloomberg id to a FIGI -- a permanent id for one
security -- plus the issuer name and a short description that usually
carries coupon and maturity ("DOW 5.2 02/15/32"). Two deals mapping to
the same FIGI are the same security.

What each source covers (measured on the 2026-09-30 exports):
- Dealogic side: only via ISIN/CUSIP (Dealogic ids are not public).
- Bloomberg side: the YR.../BL.../BF... deal ids resolve as ID_BB_8_CHR,
  so Bloomberg deals resolve even without an ISIN.
- Local-market bonds (CN, BR, KR, TH) often don't resolve at all.

No API key is needed (25 requests/min, 10 ids each). Set
OPENFIGI_API_KEY in the environment for higher limits.
"""

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

import streamlit as st

from config import SOURCE_LABELS

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
FIGI_PAGE_URL = "https://www.openfigi.com/id/{figi}"

_BBG_ID_RE = re.compile(r"^([A-Z]{2}\d{6})(?: \w+)?$")  # "YR657125 Corp", "BL501824", "BF501823"


class OpenFIGIError(Exception):
    pass


@dataclass(frozen=True)
class Job:
    side: str
    deal_id: str
    id_type: str
    id_value: str
    role: str = "deal"  # "deal" | "tranche" (a loan package's Bloomberg tranches)


def _bbg_id(value) -> str | None:
    m = _BBG_ID_RE.match(str(value or "").strip())
    return m.group(1) if m else None


def _deal_jobs(side: str, deal_id: str, isin, cusip) -> list[Job]:
    jobs = []
    if isin:
        jobs.append(Job(side, deal_id, "ID_ISIN", str(isin).strip()))
    if cusip:
        jobs.append(Job(side, deal_id, "ID_CUSIP", str(cusip).strip()))
    bbg = _bbg_id(deal_id) if side == "bbg" else None
    if bbg:
        jobs.append(Job(side, deal_id, "ID_BB_8_CHR", bbg))
    return jobs


def jobs_for_item(item) -> list[Job]:
    rt = item.rtype
    jobs = []
    if item.rtype.kind == "group":
        for r in item.rows:
            jobs += _deal_jobs(r["side"], r["_id"], r.get(f"{r['side']}_isin"), r.get(f"{r['side']}_cusip"))
        return jobs

    row = item.row
    for side in (rt.left_side, rt.right_side):
        deal_id = str(row[f"{side}_{rt.id_field}"])
        jobs += _deal_jobs(side, deal_id, row.get(f"{side}_isin"), row.get(f"{side}_cusip"))
        # Loan packages: also look up each Bloomberg tranche (BL... ids).
        for line in str(row.get(f"{side}_tranches") or "").splitlines():
            tranche = _bbg_id(line.split(" - ")[0]) if side == "bbg" else None
            if tranche:
                jobs.append(Job(side, deal_id, "ID_BB_8_CHR", tranche, role="tranche"))
    return jobs


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def _openfigi(jobs: tuple[tuple[str, str], ...]) -> list[dict | None]:
    """jobs: ((idType, idValue), ...). Returns the first match per job, or None."""
    api_key = os.environ.get("OPENFIGI_API_KEY")
    batch = 100 if api_key else 10
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key
    results = []
    for i in range(0, len(jobs), batch):
        body = json.dumps([{"idType": t, "idValue": v} for t, v in jobs[i : i + batch]]).encode()
        req = urllib.request.Request(OPENFIGI_URL, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise OpenFIGIError("OpenFIGI rate limit reached (25 lookups/min without a key). Wait a minute and retry.")
            raise OpenFIGIError(f"OpenFIGI returned HTTP {e.code}.")
        except (urllib.error.URLError, TimeoutError) as e:
            raise OpenFIGIError(f"Could not reach OpenFIGI: {e}")
        results += [(entry.get("data") or [None])[0] for entry in payload]
    return results


def lookup(item) -> list[tuple[Job, dict | None]]:
    jobs = jobs_for_item(item)
    if not jobs:
        return []
    results = _openfigi(tuple((j.id_type, j.id_value) for j in jobs))
    return list(zip(jobs, results))


def verdict(item, results) -> tuple[str, str]:
    """(level, message), level one of same | different | partial | none."""
    rt = item.rtype
    figis = {rt.left_side: set(), rt.right_side: set()}
    for job, hit in results:
        if hit and job.role == "deal":
            figis.setdefault(job.side, set()).add(hit["figi"])
    left, right = figis[rt.left_side], figis[rt.right_side]

    if item.rtype.kind == "group":
        found = sum(1 for _, hit in results if hit)
        if not found:
            return "none", "No deal in this group resolved in OpenFIGI."
        return "partial", (
            f"{found} of {len(results)} lookups resolved. Groups have no shared identifier to compare, "
            "so read the descriptions (coupon, maturity, perpetual) against the deal table."
        )
    if left and right:
        if left & right:
            return "same", f"Both sides map to the same security (FIGI {', '.join(sorted(left & right))})."
        return "different", (
            "The two sides map to different securities. That usually means different tranches, but one "
            "bond can carry several identifiers (144A and Reg S lines, or a tap), so compare the descriptions."
        )
    if left or right:
        known, other = (rt.left_side, rt.right_side) if left else (rt.right_side, rt.left_side)
        why = (
            "it has no public identifier in this export"
            if not any(j.side == other for j, _ in results)
            else "its identifiers didn't resolve"
        )
        return "partial", (
            f"Only the {SOURCE_LABELS.get(known, known)} side resolved; nothing to compare it against "
            f"because on the {SOURCE_LABELS.get(other, other)} side {why}."
        )
    if not results:
        return "none", "Neither side has a public identifier (ISIN, CUSIP or Bloomberg id) to look up."
    return "none", "None of this pair's identifiers resolved in OpenFIGI (common for local-market bonds)."


def summary_line(item, results) -> str:
    level, _ = verdict(item, results)
    descs = sorted({hit["securityDescription"] or hit["ticker"] for _, hit in results if hit})
    label = {"same": "same FIGI", "different": "different FIGIs", "partial": "partial", "none": "no match"}[level]
    return f"OpenFIGI: {label}" + (f" ({'; '.join(descs)})" if descs else "")
