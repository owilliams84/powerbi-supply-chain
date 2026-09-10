"""Recompute the headline measures in pandas and diff them against what the model returns.

The model is the thing being checked, so the check cannot use it. This reads data/ straight
from the CSVs, computes the same ten figures by year, shipping mode, market and department and
in total, and compares them to the CSV that etl/checks/verify.dax produced against the live model.

    powershell -File etl/query_model.ps1 -DaxFile etl/checks/verify.dax -Csv > etl/checks/dax_actual.csv
    python etl/verify_measures.py

Non-zero exit means a measure and its pandas equivalent disagree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ACTUAL = ROOT / "etl" / "checks" / "dax_actual.csv"

FIELDS = ["orders", "lines", "net", "profit", "gross", "shipped", "late", "late_rate",
          "cancelled", "days"]
TOL = {"net": 0.02, "profit": 0.02, "gross": 0.02, "late_rate": 1e-5, "days": 1e-5}


def load() -> pd.DataFrame:
    f = pd.concat([pd.read_csv(p) for p in sorted(DATA.glob("fact_order_line_*.csv"))],
                  ignore_index=True)
    out = pd.read_csv(DATA / "dim_outcome.csv")
    mode = pd.read_csv(DATA / "dim_shipping_mode.csv")
    geo = pd.read_csv(DATA / "dim_geography.csv")
    prod = pd.read_csv(DATA / "dim_product.csv")
    f = (f.merge(out[["OutcomeKey", "IsCancelled"]], on="OutcomeKey")
          .merge(mode[["ModeKey", "ShippingMode"]], on="ModeKey")
          .merge(geo[["GeoKey", "Market"]], on="GeoKey")
          .merge(prod[["ProductKey", "Department"]], on="ProductKey"))
    f["Year"] = pd.to_datetime(f["Date"]).dt.year
    return f


def figures(g: pd.DataFrame) -> dict:
    shipped = g[g.IsCancelled == "No"]
    orders_shipped = shipped.drop_duplicates("OrderID")
    late = int(orders_shipped[orders_shipped.IsLate == "Yes"].shape[0])
    n_shipped = int(len(orders_shipped))
    return dict(
        orders=int(g.OrderID.nunique()), lines=int(len(g)),
        net=round(float(shipped.NetSales.sum()), 2),
        profit=round(float(shipped.Profit.sum()), 2),
        gross=round(float(g.GrossSales.sum()), 2),
        shipped=n_shipped, late=late,
        late_rate=round(late / n_shipped, 6) if n_shipped else float("nan"),
        cancelled=int(g.loc[g.IsCancelled == "Yes", "OrderID"].nunique()),
        days=round(float(orders_shipped.ActualDays.mean()), 6) if n_shipped else float("nan"),
    )


def main() -> None:
    if not ACTUAL.exists():
        print(f"missing {ACTUAL} - run query_model.ps1 against the live model first")
        sys.exit(2)
    actual = pd.read_csv(ACTUAL)
    actual.columns = [c.strip("[]") for c in actual.columns]
    actual["key"] = actual["key"].astype(str)

    f = load()
    rows = [dict(grain="all", key="all", **figures(f))]
    for grain, col in (("year", "Year"), ("mode", "ShippingMode"), ("market", "Market"),
                       ("department", "Department")):
        for k, g in f.groupby(col):
            rows.append(dict(grain=grain, key=str(k), **figures(g)))
    expected = pd.DataFrame(rows)

    merged = expected.merge(actual, on=["grain", "key"], how="outer",
                            suffixes=("_pandas", "_dax"), indicator="side")
    problems = [f"{r.grain}/{r.key}: present in {r.side} only"
                for r in merged[merged["side"] != "both"].itertuples()]
    both = merged[merged["side"] == "both"]
    checks = 0
    for field in FIELDS:
        a = both[f"{field}_pandas"].astype(float)
        b = both[f"{field}_dax"].astype(float)
        # Both blank is agreement; one blank and one not is a mismatch. NaN > tol is False, so
        # the blank case has to be tested explicitly rather than let through as a pass.
        either = a.notna() | b.notna()
        diff = (a.fillna(0.0) - b.fillna(0.0)).abs()
        bad = either & ((a.isna() != b.isna()) | (diff > TOL.get(field, 0.5)))
        checks += int(either.sum())
        for r, av, bv in zip(both[bad].itertuples(), a[bad], b[bad]):
            problems.append(f"{r.grain}/{r.key} {field}: pandas={av} dax={bv}")

    print(f"{len(both)} rows compared, {checks} checks")
    if problems:
        print("\nMISMATCHES")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("every figure agrees")

    t = rows[0]
    print("\nheadline, recomputed from the CSVs:")
    print(f"  orders {t['orders']:,}  lines {t['lines']:,}")
    print(f"  net sales ${t['net']:,.2f}  profit ${t['profit']:,.2f}  margin {t['profit'] / t['net']:.2%}")
    print(f"  gross 'Sales' column ${t['gross']:,.2f}  ({t['gross'] / t['net'] - 1:.1%} over net)")
    print(f"  shipped {t['shipped']:,}  late {t['late']:,}  ({t['late_rate']:.1%})  "
          f"cancelled {t['cancelled']:,}")
    for r in expected[expected.grain == "mode"].itertuples():
        print(f"  {r.key:15} late {r.late_rate:.1%}  average days {r.days:.2f}")


if __name__ == "__main__":
    main()
