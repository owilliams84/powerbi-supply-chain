"""Answer key for the Calendar page, from the CSVs, and the diff against the live model.

    python etl/calendar_check.py --queries calendar_queries.json
    powershell -File etl/calendar_verify.ps1 -QueriesFile calendar_queries.json > calendar_dump.txt
    python etl/calendar_check.py --compare calendar_dump.txt

Late orders per order date, with no DAX involved: distinct orders that were not cancelled and are
flagged late. Every cell of all four views is checked for its value and its 1-5 shade band.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import milestone_calendar
from calendar_config import CALENDAR

DATA = Path(__file__).resolve().parents[1] / "data"


def daily() -> dict[date, float]:
    with (DATA / "dim_outcome.csv").open(encoding="utf-8", newline="") as fh:
        shipped = {r["OutcomeKey"] for r in csv.DictReader(fh) if r["IsCancelled"] == "No"}
    orders: dict[date, set[str]] = defaultdict(set)
    for path in sorted(DATA.glob("fact_order_line_*.csv")):
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["OutcomeKey"] in shipped and r["IsLate"] == "Yes":
                    orders[date.fromisoformat(r["Date"])].add(r["OrderID"])
    return {d: float(len(ids)) for d, ids in orders.items()}


def bounds() -> tuple[date, date]:
    with (DATA / "dim_date.csv").open(encoding="utf-8", newline="") as fh:
        days = [date.fromisoformat(r["Date"]) for r in csv.DictReader(fh)]
    return min(days), max(days)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries")
    ap.add_argument("--compare")
    args = ap.parse_args()
    first, last = bounds()
    if args.queries:
        pairs = milestone_calendar.verify_queries(CALENDAR, list(range(first.year, last.year + 1)))
        Path(args.queries).write_text(json.dumps([{"view": v, "dax": q} for v, q in pairs]), encoding="utf-8")
        print(f"{len(pairs)} queries -> {args.queries}")
    if args.compare:
        key = milestone_calendar.expected(daily(), first, last)
        sys.exit(1 if milestone_calendar.compare(key, Path(args.compare)) else 0)


if __name__ == "__main__":
    main()
