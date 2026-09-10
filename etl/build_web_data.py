"""Emit the JSON the milestonebi.com case study reads.

The case study redraws the Power BI report for the web, so its numbers have to be the same
numbers. They are computed here from data/ - the same CSVs the model loads - rather than typed
into the page, and verify_measures.py has already proved that those CSVs and the model agree.

    python etl/build_web_data.py [--out <path>]

Writes web/supply-chain.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "web" / "supply-chain.json"


def r(v, dp=2):
    return None if pd.isna(v) else round(float(v), dp)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    f = pd.concat([pd.read_csv(p) for p in sorted(DATA.glob("fact_order_line_*.csv"))],
                  ignore_index=True)
    out = pd.read_csv(DATA / "dim_outcome.csv")
    mode = pd.read_csv(DATA / "dim_shipping_mode.csv")
    geo = pd.read_csv(DATA / "dim_geography.csv")
    prod = pd.read_csv(DATA / "dim_product.csv")
    date = pd.read_csv(DATA / "dim_date.csv")
    quality = json.loads((DATA / "quality_report.json").read_text(encoding="utf-8"))
    f = (f.merge(out[["OutcomeKey", "IsCancelled"]], on="OutcomeKey")
          .merge(mode[["ModeKey", "ShippingMode", "PromisedDays"]].rename(
              columns={"PromisedDays": "Promise"}), on="ModeKey")
          .merge(geo[["GeoKey", "Market"]], on="GeoKey")
          .merge(prod[["ProductKey", "Department", "Category"]], on="ProductKey"))
    f["Month"] = pd.to_datetime(f["Date"]).dt.strftime("%Y-%m")
    ship = f[f.IsCancelled == "No"]
    orders = ship.drop_duplicates("OrderID")

    out_json: dict = {}
    modes = []
    for k, g in orders.groupby("ModeKey"):
        dist = g.ActualDays.value_counts().sort_index()
        modes.append(dict(
            mode=g.ShippingMode.iloc[0], promised=int(g.Promise.iloc[0]), orders=int(len(g)),
            late_rate=r((g.IsLate == "Yes").mean(), 4), avg_days=r(g.ActualDays.mean(), 2),
            days={int(d): int(n) for d, n in dist.items()},
        ))
    out_json["by_mode"] = modes

    months = sorted(f.Month.unique())
    net_m = ship.groupby("Month").NetSales.sum()
    lpo = f.groupby("Month").size() / f.groupby("Month").OrderID.nunique()
    late_m = orders.groupby("Month").apply(lambda g: (g.IsLate == "Yes").mean(),
                                           include_groups=False)
    mk = f.drop_duplicates("OrderID").groupby(["Month", "Market"]).size().unstack(fill_value=0)
    mk = mk.div(mk.sum(axis=1), axis=0)
    series = date.assign(Month=pd.to_datetime(date.Date).dt.strftime("%Y-%m")) \
        .groupby("Month").Series.first()
    out_json["monthly"] = dict(
        months=months,
        net_sales=[r(net_m.get(m, 0), 0) for m in months],
        lines_per_order=[r(lpo[m], 3) for m in months],
        late_rate=[r(late_m.get(m), 4) for m in months],
        series=[series[m] for m in months],
        market_share={c: [r(mk.loc[m, c], 4) if m in mk.index else 0 for m in months]
                      for c in mk.columns},
    )

    depts = []
    for d, g in ship.groupby("Department"):
        depts.append(dict(department=d, net_sales=r(g.NetSales.sum(), 0),
                          margin=r(g.Profit.sum() / g.NetSales.sum(), 4),
                          loss_share=r((g.Profit < 0).mean(), 4)))
    out_json["by_department"] = sorted(depts, key=lambda x: -x["net_sales"])
    out_json["by_market"] = [dict(market=m, orders=int(g.OrderID.nunique()),
                                  net_sales=r(g.NetSales.sum(), 0),
                                  margin=r(g.Profit.sum() / g.NetSales.sum(), 4),
                                  late_rate=r((g.drop_duplicates("OrderID").IsLate == "Yes").mean(), 4))
                             for m, g in ship.groupby("Market")]

    out_json["totals"] = dict(
        orders=int(f.OrderID.nunique()), lines=int(len(f)),
        shipped=int(len(orders)), late=int((orders.IsLate == "Yes").sum()),
        net_sales=r(ship.NetSales.sum(), 0), profit=r(ship.Profit.sum(), 0),
        gross_source=r(f.GrossSales.sum(), 0),
        cancelled=int(f.loc[f.IsCancelled == "Yes", "OrderID"].nunique()),
        cancelled_value=r(f.loc[f.IsCancelled == "Yes", "NetSales"].sum(), 0),
        products=int(prod.shape[0]), countries=int(geo.Country.nunique()),
        first=str(pd.to_datetime(f.Date).min().date()), last=str(pd.to_datetime(f.Date).max().date()),
    )
    out_json["quality"] = {k: quality[k] for k in (
        "series_switch", "market_calendar", "cancelled", "payment_type_decides_status",
        "discount_rate_mismatch", "placeholder_names", "lines_per_order_distribution_before",
        "gross_vs_net",
    )}

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out_json, separators=(",", ":"), ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    print(f"{path} {path.stat().st_size / 1024:.1f} KB")
    for m in modes:
        print(f"  {m['mode']:15} promised {m['promised']}  late {m['late_rate']:.1%}  "
              f"days {m['days']}")


if __name__ == "__main__":
    main()
