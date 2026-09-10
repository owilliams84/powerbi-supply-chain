"""Turn the DataCo supply chain extract into a star schema, and say what was wrong with it.

Source: Constante, Silva & Pereira (2019), "DataCo SMART SUPPLY CHAIN FOR BIG DATA ANALYSIS",
Mendeley Data, V5, doi:10.17632/8gx2fvg2k6.5 - CC BY 4.0. 180,519 order lines, January 2015 to
January 2018, from a sports and outdoor retailer shipping to 164 countries.

    python etl/build_star_schema.py --source <folder holding DataCoSupplyChainDataset.csv>

The 96 MB source is not committed. The build checks its SHA-256 against the published file
before reading it, then writes data/ and data/quality_report.json.

What the build has to decide, because the file will not say:

1.  **Revenue is not the column called Sales.** Sales is price x quantity before discount. The
    money that changed hands is Order Item Total, and cancelled and suspected-fraud orders did
    not ship at all. The model reports net sales on shipped orders and keeps the gross figure
    beside it.

2.  **The late flag is the delivery status, not a risk score.** Late_delivery_risk is 1 exactly
    when Delivery Status is "Late delivery". Cancelled orders carry shipping days too, and 4,423
    of them would be late by those days; they are cancellations, not late deliveries, and every
    delivery measure excludes them.

3.  **The last four months come from a different generator.** From 3 October 2017 every order
    has one line instead of one to five, orders arrive at 68 or 69 a day with almost no
    variation, and 100 of the 101 products on sale disappear while 17 new ones appear. The date
    table flags the switch, and the report says so wherever a trend crosses it.

4.  **Market is a calendar.** In most months every order goes to a single market - LATAM for
    the first five months, then Europe, then Pacific Asia, then the US. A chart of sales by
    market is a chart of which months each market was given. The report shows that instead of
    comparing the markets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from country_names import english

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LF = "\n"
SOURCE = "DataCoSupplyChainDataset.csv"
SHA256 = "fa6d022ed437155e1a2f0378710602848703c8a7f203f7ff5d77805bf8480aa6"


def write_csv(df: pd.DataFrame, name: str) -> None:
    path = DATA / name
    df.to_csv(path, index=False, lineterminator=LF)
    print("  %-28s %8d rows  %8.1f KB" % (name, len(df), path.stat().st_size / 1024))


def tidy(s: pd.Series) -> pd.Series:
    """Trim and collapse internal runs of spaces: 'South of  USA ' is 'South of USA'."""
    return s.astype(str).str.split().str.join(" ")


def require(ok: bool, what: str) -> None:
    if not ok:
        raise SystemExit(f"source check failed: {what}")


def title(status: str) -> str:
    return status.replace("_", " ").capitalize()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    args = ap.parse_args()
    src = Path(args.source) / SOURCE
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    require(digest == SHA256, f"{SOURCE} SHA-256 is {digest}, not the published {SHA256}")
    DATA.mkdir(exist_ok=True)
    q: dict[str, object] = {"source_sha256": digest}

    # Latin-1, not UTF-8: the Spanish place names are single-byte, and a UTF-8 read stops at the
    # first accented character.
    f = pd.read_csv(src, encoding="latin-1")
    q["rows"] = int(len(f))
    # Every text column, tested as "not numeric": pandas 3 reads text as the str dtype, and a
    # `dtype == object` test silently skips all of it - which is how 'South of  USA ' first
    # survived this step.
    for c in f.columns:
        if not pd.api.types.is_numeric_dtype(f[c]):
            f[c] = f[c].where(f[c].isna(), tidy(f[c]))
    require(not f["Order Region"].str.contains(r"^\s|\s$|\s\s").any(), "whitespace survived tidy")
    f["OrderDate"] = pd.to_datetime(f["order date (DateOrders)"], format="%m/%d/%Y %H:%M")
    f["ShipDate"] = pd.to_datetime(f["shipping date (DateOrders)"], format="%m/%d/%Y %H:%M")

    # ------------------------------------------------------------------ structural checks
    require(f["Order Item Id"].is_unique, "Order Item Id is not unique")
    require((f["Customer Id"] == f["Order Customer Id"]).all(), "two customer ids disagree")
    require((f["Order Item Cardprod Id"] == f["Product Card Id"]).all(), "two product ids disagree")
    order_level = ["Shipping Mode", "Order Status", "Delivery Status", "Days for shipping (real)",
                   "Market", "Order Region", "Order Country", "Type", "OrderDate", "Customer Id"]
    per_order = f.groupby("Order Id")[order_level].nunique()
    require((per_order <= 1).all().all(), "an order-level field varies within an order")
    require((f.groupby("Product Card Id")[["Product Name", "Product Price", "Category Id"]]
             .nunique() <= 1).all().all(), "a product changes name, price or category")
    require((f.groupby("Category Id")["Department Id"].nunique() <= 1).all(),
            "a category sits in two departments")
    require((f.groupby("Shipping Mode")["Days for shipment (scheduled)"].nunique() == 1).all(),
            "a shipping mode has two promised lead times")
    require(np.allclose(f["Sales"], f["Order Item Product Price"] * f["Order Item Quantity"],
                        atol=0.011), "Sales is not price x quantity")
    require(np.allclose(f["Order Item Total"], f["Sales"] - f["Order Item Discount"], atol=0.011),
            "Order Item Total is not Sales less discount")
    require(np.allclose(f["Benefit per order"], f["Order Profit Per Order"]),
            "the two profit columns differ")
    late = f["Delivery Status"] == "Late delivery"
    require((f["Late_delivery_risk"] == late.astype(int)).all(),
            "the late flag is not the delivery status")

    # The columns whose names say something else.
    q["misnamed_columns"] = {
        "Sales": "price x quantity before discount - gross, not revenue",
        "Order Item Total": "the net line value; this is revenue",
        "Order Profit Per Order": "per line, not per order: it varies within 69.8% of orders",
        "Benefit per order": "an exact duplicate of Order Profit Per Order",
        "Sales per customer": "an exact duplicate of Order Item Total, per line",
        "Late_delivery_risk": "not a risk score: 1 exactly when Delivery Status is Late delivery",
    }
    disc = (f["Order Item Discount"] - f["Sales"] * f["Order Item Discount Rate"]).abs()
    q["discount_rate_mismatch"] = {"lines_over_1_cent": int((disc > 0.01).sum()),
                                   "max_difference": round(float(disc.max()), 2),
                                   "note": "the discount amount reconciles to the line total; "
                                           "the stated rate does not always reconcile to it"}
    q["gross_vs_net"] = {"sales_column": round(float(f["Sales"].sum()), 2),
                         "order_item_total": round(float(f["Order Item Total"].sum()), 2)}

    # ------------------------------------------------------------------ the October 2017 switch
    day = f.groupby(f["OrderDate"].dt.normalize()).agg(lines=("Order Item Id", "size"),
                                                         orders=("Order Id", "nunique"))
    single = day["lines"] == day["orders"]
    # The first day from which every later day has one line per order.
    tail_ok = single[::-1].cummin()[::-1]
    cut = tail_ok[tail_ok].index.min()
    before, after = f[f["OrderDate"] < cut], f[f["OrderDate"] >= cut]
    pb, pa = set(before["Product Card Id"]), set(after["Product Card Id"])
    q["series_switch"] = {
        "first_day_of_new_series": str(cut.date()),
        "lines_per_order_before": round(len(before) / before["Order Id"].nunique(), 3),
        "lines_per_order_after": round(len(after) / after["Order Id"].nunique(), 3),
        "orders_per_day_before": {"mean": round(float(day.loc[day.index < cut, "orders"].mean()), 1),
                                  "std": round(float(day.loc[day.index < cut, "orders"].std()), 2)},
        "orders_per_day_after": {"mean": round(float(day.loc[day.index >= cut, "orders"].mean()), 1),
                                 "std": round(float(day.loc[day.index >= cut, "orders"].std()), 2)},
        "products_before": len(pb), "products_after": len(pa),
        "products_dropped": len(pb - pa), "products_added": len(pa - pb),
    }
    lpo = before.groupby("Order Id").size().value_counts().sort_index()
    q["lines_per_order_distribution_before"] = {int(k): int(v) for k, v in lpo.items()}

    # ------------------------------------------------------------------ market is a calendar
    mm = f.groupby([f["OrderDate"].dt.to_period("M"), "Market"])["Order Id"].nunique() \
        .unstack(fill_value=0)
    top_share = mm.max(axis=1) / mm.sum(axis=1)
    q["market_calendar"] = {"months": int(len(mm)),
                            "months_with_one_market": int((mm.gt(0).sum(axis=1) == 1).sum()),
                            "months_where_one_market_has_90pct": int((top_share >= 0.9).sum())}

    # ------------------------------------------------------------------ payment decides status
    ts = pd.crosstab(f["Type"], f["Order Status"])
    q["payment_type_decides_status"] = {t: sorted(ts.columns[ts.loc[t] > 0].tolist())
                                        for t in ts.index}

    # ------------------------------------------------------------------ delivery
    cancelled = f["Delivery Status"] == "Shipping canceled"
    days_late = f["Days for shipping (real)"] - f["Days for shipment (scheduled)"]
    ords = f.drop_duplicates("Order Id")
    oc = ords["Delivery Status"] == "Shipping canceled"
    q["cancelled"] = {"orders": int(oc.sum()), "lines": int(cancelled.sum()),
                      "net_value": round(float(f.loc[cancelled, "Order Item Total"].sum()), 2),
                      "orders_late_by_their_own_dates": int((oc & (ords["Days for shipping (real)"]
                                                               > ords["Days for shipment (scheduled)"])).sum())}
    shipped = ords[~oc]
    q["late_rate_shipped_orders"] = round(float((shipped["Delivery Status"] == "Late delivery").mean()), 4)
    q["by_mode"] = {m: {"promised_days": int(g["Days for shipment (scheduled)"].iloc[0]),
                        "actual_days": sorted(g["Days for shipping (real)"].unique().tolist()),
                        "late_rate": round(float((g["Delivery Status"] == "Late delivery").mean()), 4),
                        "orders": int(len(g))}
                    for m, g in shipped.groupby("Shipping Mode")}

    # ------------------------------------------------------------------ placeholders and PII
    q["placeholder_names"] = {"Mary": int((f["Customer Fname"] == "Mary").sum()),
                              "Smith": int((f["Customer Lname"] == "Smith").sum()),
                              "email_masked": bool((f["Customer Email"] == "XXXXXXXXX").all()),
                              "password_masked": bool((f["Customer Password"] == "XXXXXXXXX").all())}
    q["empty_columns"] = ["Product Description (all null)", "Product Status (always 0)"]
    q["order_zipcode_null_share"] = round(float(f["Order Zipcode"].isna().mean()), 3)
    q["dropped_columns"] = ["Customer Fname", "Customer Lname", "Customer Email",
                            "Customer Password", "Customer Street", "Customer Zipcode",
                            "Latitude", "Longitude", "Order Zipcode", "Order City", "Order State",
                            "Product Description", "Product Status", "Product Image",
                            "Benefit per order", "Sales per customer", "Late_delivery_risk"]

    # ------------------------------------------------------------------ dimensions
    first_seen = f.groupby("Product Card Id")["OrderDate"].min()
    prod = f.drop_duplicates("Product Card Id").sort_values("Product Card Id")
    dim_product = pd.DataFrame({
        "ProductKey": prod["Product Card Id"].astype(int),
        "Product": prod["Product Name"], "Category": prod["Category Name"],
        "Department": prod["Department Name"], "ListPrice": prod["Product Price"].round(2),
        "Catalogue": np.where(prod["Product Card Id"].map(first_seen) >= cut,
                              "Added Oct 2017", "On sale 2015-17"),
    })

    cust = f.drop_duplicates("Customer Id").sort_values("Customer Id")
    dim_customer = pd.DataFrame({
        "CustomerKey": cust["Customer Id"].astype(int), "Segment": cust["Customer Segment"],
        "StoreCity": cust["Customer City"], "StoreState": cust["Customer State"],
        "StoreCountry": cust["Customer Country"].map(english),
    })

    f["Country"] = f["Order Country"].map(english)
    geo = f[["Market", "Order Region", "Country"]].drop_duplicates() \
        .sort_values(["Market", "Order Region", "Country"]).reset_index(drop=True)
    geo["GeoKey"] = range(1, len(geo) + 1)
    q["countries_in_more_than_one_region"] = int((geo.groupby("Country").size() > 1).sum())
    dim_geography = geo.rename(columns={"Order Region": "Region"})[
        ["GeoKey", "Market", "Region", "Country"]]

    mode_order = {"Same Day": 1, "First Class": 2, "Second Class": 3, "Standard Class": 4}
    modes = f.drop_duplicates("Shipping Mode")
    dim_mode = pd.DataFrame({
        "ModeKey": modes["Shipping Mode"].map(mode_order).astype(int),
        "ShippingMode": modes["Shipping Mode"],
        "PromisedDays": modes["Days for shipment (scheduled)"].astype(int),
    }).sort_values("ModeKey")

    out = f[["Type", "Order Status", "Delivery Status"]].drop_duplicates() \
        .sort_values(["Delivery Status", "Order Status", "Type"]).reset_index(drop=True)
    out["OutcomeKey"] = range(1, len(out) + 1)
    delivery_sort = {"Advance shipping": 1, "Shipping on time": 2, "Late delivery": 3,
                     "Shipping canceled": 4}
    dim_outcome = pd.DataFrame({
        "OutcomeKey": out["OutcomeKey"],
        "PaymentType": out["Type"].str.capitalize(),
        "OrderStatus": out["Order Status"].map(title),
        "DeliveryStatus": out["Delivery Status"].replace({"Shipping canceled": "Cancelled"}),
        "DeliverySort": out["Delivery Status"].map(delivery_sort),
        "IsCancelled": np.where(out["Delivery Status"] == "Shipping canceled", "Yes", "No"),
        "IsSuspectedFraud": np.where(out["Order Status"] == "SUSPECTED_FRAUD", "Yes", "No"),
    })

    start, end = f["OrderDate"].min().normalize(), f["OrderDate"].max().normalize()
    days = pd.date_range(start, end, freq="D")
    dd = pd.DataFrame({"Date": days})
    d = dd["Date"]
    dd["Year"] = d.dt.year
    dd["Quarter"] = "Q" + d.dt.quarter.astype(str)
    dd["MonthNumber"] = d.dt.month
    dd["MonthName"] = d.dt.strftime("%B")
    dd["MonthShort"] = d.dt.strftime("%b")
    dd["MonthYear"] = d.dt.strftime("%b %Y")
    dd["MonthYearSort"] = d.dt.year * 100 + d.dt.month
    dd["MonthStart"] = d.dt.to_period("M").dt.start_time.dt.date
    dd["Series"] = np.where(d < cut, "Jan 2015 to Sep 2017", "Oct 2017 to Jan 2018")
    dd["InJanToSep"] = np.where(d.dt.month <= 9, "Yes", "No")
    dd["Date"] = d.dt.date

    # ------------------------------------------------------------------ fact
    key = lambda cols: f[cols].apply(tuple, axis=1)
    geo_key = dict(zip(zip(geo["Market"], geo["Order Region"], geo["Country"]), geo["GeoKey"]))
    out_key = dict(zip(zip(out["Type"], out["Order Status"], out["Delivery Status"]),
                       out["OutcomeKey"]))
    fact = pd.DataFrame({
        "LineID": f["Order Item Id"].astype(int),
        "OrderID": f["Order Id"].astype(int),
        "Date": f["OrderDate"].dt.date.astype(str),
        "ShipDate": f["ShipDate"].dt.date.astype(str),
        "CustomerKey": f["Customer Id"].astype(int),
        "ProductKey": f["Product Card Id"].astype(int),
        "GeoKey": key(["Market", "Order Region", "Country"]).map(geo_key),
        "ModeKey": f["Shipping Mode"].map(mode_order).astype(int),
        "OutcomeKey": key(["Type", "Order Status", "Delivery Status"]).map(out_key),
        "PromisedDays": f["Days for shipment (scheduled)"].astype(int),
        "ActualDays": f["Days for shipping (real)"].astype(int),
        "DaysLate": days_late.astype(int),
        "IsLate": np.where(late, "Yes", "No"),
        "Quantity": f["Order Item Quantity"].astype(int),
        "UnitPrice": f["Order Item Product Price"].round(2),
        "GrossSales": f["Sales"].round(2),
        "DiscountRate": f["Order Item Discount Rate"].round(4),
        "Discount": f["Order Item Discount"].round(2),
        "NetSales": f["Order Item Total"].round(2),
        "Profit": f["Order Profit Per Order"].round(2),
    }).sort_values("LineID")
    require(fact[["GeoKey", "OutcomeKey"]].notna().all().all(), "a fact row lost its key")

    ok = ~cancelled
    q["headline"] = {
        "orders": int(f["Order Id"].nunique()), "lines": int(len(f)),
        "net_sales_shipped": round(float(f.loc[ok, "Order Item Total"].sum()), 2),
        "profit_shipped": round(float(f.loc[ok, "Order Profit Per Order"].sum()), 2),
        "margin_shipped": round(float(f.loc[ok, "Order Profit Per Order"].sum()
                                      / f.loc[ok, "Order Item Total"].sum()), 4),
        "loss_making_line_share": round(float((f["Order Profit Per Order"] < 0).mean()), 4),
    }

    print("data/")
    write_csv(dd, "dim_date.csv")
    write_csv(dim_product, "dim_product.csv")
    write_csv(dim_customer, "dim_customer.csv")
    write_csv(dim_geography, "dim_geography.csv")
    write_csv(dim_mode, "dim_shipping_mode.csv")
    write_csv(dim_outcome, "dim_outcome.csv")
    years = pd.to_datetime(fact["Date"]).dt.year
    for y in sorted(years.unique()):
        write_csv(fact[years == y], f"fact_order_line_{y}.csv")

    (DATA / "quality_report.json").write_text(json.dumps(q, indent=2, ensure_ascii=False) + LF,
                                              encoding="utf-8", newline=LF)
    print("\ndata/quality_report.json")
    for k in ("headline", "series_switch", "market_calendar", "cancelled",
              "late_rate_shipped_orders", "by_mode", "discount_rate_mismatch", "gross_vs_net",
              "countries_in_more_than_one_region", "payment_type_decides_status"):
        print("  %-36s %s" % (k, q[k]))


if __name__ == "__main__":
    main()
