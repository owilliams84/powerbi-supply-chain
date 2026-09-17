"""Generate the TMDL semantic model - tables, relationships, measures.

TMDL is indentation-sensitive (tabs) and forbids blank lines inside an object, and every object
needs a stable lineageTag. This owns the format and the tags (uuid5 of the object's path, so
re-running never churns them), and the table definitions below read as a schema.

    python etl/build_model.py            # partitions read the CSVs from GitHub over HTTPS
    python etl/build_model.py --local    # partitions read data/ on this machine (offline)

The fact is one file per year, loaded as one partition each.

Rewrites <model>/definition/ from scratch every run.
"""

from __future__ import annotations

import argparse
import shutil
import time
import uuid
from pathlib import Path

import milestone_calendar
from calendar_config import CALENDAR

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "Supply Chain.SemanticModel"
DEFN = MODEL / "definition"
DATA = ROOT / "data"

RAW = "https://raw.githubusercontent.com/owilliams84/powerbi-supply-chain/main/data/"
NS = uuid.UUID("6d2f8a41-9c37-4e1b-b5a0-2e7c4f9d1a83")
YEARS = ["2015", "2016", "2017", "2018"]


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "supplychain:" + ":".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL identifier when it needs it."""
    return name if name.replace("_", "").isalnum() else f"'{name}'"


def doc(text: str | None, indent: int) -> list[str]:
    if not text:
        return []
    pad = "\t" * indent
    return [f"{pad}/// {para}".rstrip() for para in text.strip("\n").split("\n")]


def col(name, source, dtype, **o):
    return dict(name=name, source=source, dtype=dtype, **o)


INT_T, TXT_T, NUM_T, DATE_T = "Int64.Type", "type text", "type number", "type date"

TABLES = {
    "Date": dict(
        file="dim_date.csv", date_table=True,
        doc="One row per day from 1 January 2015 to 31 January 2018, contiguous, and marked as\n"
            "the date table.\n"
            "\n"
            "'Series' marks the day the extract changes generator, early in October 2017. From\n"
            "then on every order has one line, orders arrive at an almost fixed rate, and most of\n"
            "the catalogue is replaced. The trend visuals stop before it; nothing else hides it.",
        columns=[
            col("Date", "Date", "dateTime", key=True, format="d mmm yyyy"),
            col("Year", "Year", "int64", format="0"),
            col("Quarter", "Quarter", "string"),
            col("Month No", "MonthNumber", "int64", hidden=True, format="0"),
            col("Month", "MonthName", "string", sortBy="Month No"),
            col("Month Short", "MonthShort", "string", sortBy="Month No"),
            col("Month Year", "MonthYear", "string", sortBy="Month Year Sort"),
            col("Month Year Sort", "MonthYearSort", "int64", hidden=True, format="0"),
            col("Month Start", "MonthStart", "dateTime", format="mmm yyyy"),
            col("Series", "Series", "string"),
            col("In Jan To Sep", "InJanToSep", "string",
                doc="Yes for January to September - the months every year's main series has."),
        ],
        types={"Date": DATE_T, "Year": INT_T, "Quarter": TXT_T, "MonthNumber": INT_T,
               "MonthName": TXT_T, "MonthShort": TXT_T, "MonthYear": TXT_T,
               "MonthYearSort": INT_T, "MonthStart": DATE_T, "Series": TXT_T,
               "InJanToSep": TXT_T},
    ),
    "Product": dict(
        file="dim_product.csv",
        doc="The 118 products ever sold, with category and department. 'Catalogue' separates the\n"
            "101 on sale from 2015 from the 17 that appear with the October 2017 switch - laptops,\n"
            "lawn mowers and CDs in a file that had been sports and outdoor kit. Only one product\n"
            "sells on both sides of the switch.",
        columns=[
            col("Product Key", "ProductKey", "int64", key=True, hidden=True, format="0"),
            col("Product", "Product", "string"),
            col("Category", "Category", "string"),
            col("Department", "Department", "string"),
            col("List Price", "ListPrice", "double", format="\\$#,0.00"),
            col("Catalogue", "Catalogue", "string"),
        ],
        types={"ProductKey": INT_T, "Product": TXT_T, "Category": TXT_T, "Department": TXT_T,
               "ListPrice": NUM_T, "Catalogue": TXT_T},
    ),
    "Customer": dict(
        file="dim_customer.csv",
        doc="One row per customer id, 20,652 of them. Segment and the store the order was placed\n"
            "through - which is all the customer columns honestly hold. The names are placeholders\n"
            "(65,150 order lines belong to a 'Mary', 64,104 to a 'Smith'), email and password are\n"
            "masked to XXXXXXXXX, and the street addresses are generated. All of that is dropped in\n"
            "the ETL.",
        columns=[
            col("Customer Key", "CustomerKey", "int64", key=True, hidden=True, format="0"),
            col("Segment", "Segment", "string"),
            col("Store City", "StoreCity", "string"),
            col("Store State", "StoreState", "string"),
            col("Store Country", "StoreCountry", "string",
                doc="United States or Puerto Rico. Every store is in one or the other; the\n"
                    "orders go to 164 countries."),
        ],
        types={"CustomerKey": INT_T, "Segment": TXT_T, "StoreCity": TXT_T, "StoreState": TXT_T,
               "StoreCountry": TXT_T},
    ),
    "Geography": dict(
        file="dim_geography.csv",
        doc="Where the order was delivered: market, region and country. The source writes the\n"
            "countries in Spanish; the ETL translates all 164 and fails on any it does not know.\n"
            "\n"
            "Read 'Market' with care. In most months every order goes to one market, so a split\n"
            "by market is mostly a split by month.",
        columns=[
            col("Geo Key", "GeoKey", "int64", key=True, hidden=True, format="0"),
            col("Market", "Market", "string"),
            col("Region", "Region", "string"),
            col("Country", "Country", "string", dataCategory="Country"),
        ],
        types={"GeoKey": INT_T, "Market": TXT_T, "Region": TXT_T, "Country": TXT_T},
    ),
    "Shipping Mode": dict(
        file="dim_shipping_mode.csv",
        doc="The four shipping modes and the lead time each one promises.",
        columns=[
            col("Mode Key", "ModeKey", "int64", key=True, hidden=True, format="0"),
            col("Shipping Mode", "ShippingMode", "string", sortBy="Mode Key"),
            col("Promised Days", "PromisedDays", "int64", format="0"),
        ],
        types={"ModeKey": INT_T, "ShippingMode": TXT_T, "PromisedDays": INT_T},
    ),
    "Outcome": dict(
        file="dim_outcome.csv",
        doc="What happened to the order: how it was paid, its order status and its delivery\n"
            "status, one row per combination that occurs.\n"
            "\n"
            "Payment type decides order status outright: cash is always Closed, debit always\n"
            "Complete or On hold, and every suspected fraud is a bank transfer. Useful to know\n"
            "before reading a fraud pattern into it.",
        columns=[
            col("Outcome Key", "OutcomeKey", "int64", key=True, hidden=True, format="0"),
            col("Payment Type", "PaymentType", "string"),
            col("Order Status", "OrderStatus", "string"),
            col("Delivery Status", "DeliveryStatus", "string", sortBy="Delivery Sort"),
            col("Delivery Sort", "DeliverySort", "int64", hidden=True, format="0"),
            col("Is Cancelled", "IsCancelled", "string",
                doc="Yes for cancelled and suspected-fraud orders: they did not ship."),
            col("Is Suspected Fraud", "IsSuspectedFraud", "string"),
        ],
        types={"OutcomeKey": INT_T, "PaymentType": TXT_T, "OrderStatus": TXT_T,
               "DeliveryStatus": TXT_T, "DeliverySort": INT_T, "IsCancelled": TXT_T,
               "IsSuspectedFraud": TXT_T},
    ),
    "Order Lines": dict(
        files=[f"fact_order_line_{y}.csv" for y in YEARS],
        partition_names=YEARS,
        doc="One row per order line - 180,519 lines on 65,752 orders. Order-level fields (mode,\n"
            "status, delivery days) repeat on every line of an order; the ETL proves they never\n"
            "vary within one, which is what lets the order-level measures count distinct orders\n"
            "straight off this table.\n"
            "\n"
            "Gross Sales is the source's 'Sales' column: price times quantity, before discount.\n"
            "Net Sales is 'Order Item Total', the money that changed hands. Profit is the source's\n"
            "'Order Profit Per Order', which despite the name is per line.",
        columns=[
            col("Line ID", "LineID", "int64", hidden=True, format="0"),
            col("Order ID", "OrderID", "int64", hidden=True, format="0"),
            col("Date", "Date", "dateTime", hidden=True, format="yyyy-mm-dd"),
            col("Ship Date", "ShipDate", "dateTime", hidden=True, format="yyyy-mm-dd"),
            col("Customer Key", "CustomerKey", "int64", hidden=True, format="0"),
            col("Product Key", "ProductKey", "int64", hidden=True, format="0"),
            col("Geo Key", "GeoKey", "int64", hidden=True, format="0"),
            col("Mode Key", "ModeKey", "int64", hidden=True, format="0"),
            col("Outcome Key", "OutcomeKey", "int64", hidden=True, format="0"),
            col("Promised Days", "PromisedDays", "int64", hidden=True, format="0"),
            col("Actual Days", "ActualDays", "int64", format="0",
                doc="Days from order to shipment. Uniform from 2 to 6 for both Second Class and\n"
                    "Standard Class - the two modes promise different things and deliver the same."),
            col("Days Late", "DaysLate", "int64", format="0",
                doc="Actual less promised. Negative is early."),
            col("Is Late", "IsLate", "string",
                doc="The source's delivery status says late. Never Yes for a cancelled order."),
            col("Quantity", "Quantity", "int64", hidden=True, format="0"),
            col("Unit Price", "UnitPrice", "double", hidden=True, format="\\$#,0.00"),
            col("Gross Sales", "GrossSales", "double", hidden=True, format="\\$#,0.00"),
            col("Discount Rate", "DiscountRate", "double", hidden=True, format="0.0%"),
            col("Discount", "Discount", "double", hidden=True, format="\\$#,0.00"),
            col("Net Sales", "NetSales", "double", hidden=True, format="\\$#,0.00"),
            col("Profit", "Profit", "double", hidden=True, format="\\$#,0.00"),
        ],
        types={"LineID": INT_T, "OrderID": INT_T, "Date": DATE_T, "ShipDate": DATE_T,
               "CustomerKey": INT_T, "ProductKey": INT_T, "GeoKey": INT_T, "ModeKey": INT_T,
               "OutcomeKey": INT_T, "PromisedDays": INT_T, "ActualDays": INT_T,
               "DaysLate": INT_T, "IsLate": TXT_T, "Quantity": INT_T, "UnitPrice": NUM_T,
               "GrossSales": NUM_T, "DiscountRate": NUM_T, "Discount": NUM_T,
               "NetSales": NUM_T, "Profit": NUM_T},
    ),
}

RELATIONSHIPS = [
    ("Date to Order Lines", "'Order Lines'.Date", "Date.Date"),
    ("Product to Order Lines", "'Order Lines'.'Product Key'", "Product.'Product Key'"),
    ("Customer to Order Lines", "'Order Lines'.'Customer Key'", "Customer.'Customer Key'"),
    ("Geography to Order Lines", "'Order Lines'.'Geo Key'", "Geography.'Geo Key'"),
    ("Mode to Order Lines", "'Order Lines'.'Mode Key'", "'Shipping Mode'.'Mode Key'"),
    ("Outcome to Order Lines", "'Order Lines'.'Outcome Key'", "Outcome.'Outcome Key'"),
]

USD, USD2, INT, PCT, PCT2, DEC1, DEC2 = "\\$#,0", "\\$#,0.00", "#,0", "0.0%", "0.00%", "0.0", "0.00"

SHIPPED = "KEEPFILTERS('Outcome'[Is Cancelled] = \"No\")"
CANCELLED = "KEEPFILTERS('Outcome'[Is Cancelled] = \"Yes\")"
LATE = "KEEPFILTERS('Order Lines'[Is Late] = \"Yes\")"


def per_order_avg(column: str, *filters: str) -> str:
    """Average an order-level field over orders, not lines. The field repeats on every line of
    an order, so averaging the column directly weights a five-line order five times."""
    f = "".join(f", {x}" for x in filters)
    return ("AVERAGEX(\n"
            "    CALCULATETABLE(\n"
            f"        SUMMARIZE('Order Lines', 'Order Lines'[Order ID], 'Order Lines'[{column}]){f}\n"
            "    ),\n"
            f"    'Order Lines'[{column}]\n"
            ")")


MEASURES = [
    # ---- volume
    ("Order Lines", "COUNTROWS('Order Lines')", INT, None),
    ("Orders", "DISTINCTCOUNT('Order Lines'[Order ID])", INT,
     "Every order, shipped or cancelled."),
    ("Units", "SUM('Order Lines'[Quantity])", INT, None),
    ("Lines per Order", "DIVIDE([Order Lines], [Orders])", DEC2,
     "About three until October 2017, then exactly one - the clearest sign of the switch."),
    ("Products Sold", "DISTINCTCOUNT('Order Lines'[Product Key])", INT, None),
    ("Customers", "DISTINCTCOUNT('Order Lines'[Customer Key])", INT, None),

    # ---- money
    ("Net Sales", f"CALCULATE(SUM('Order Lines'[Net Sales]), {SHIPPED})", USD,
     "The line total after discount, on orders that shipped. This is revenue."),
    ("Gross Sales (source column)", "SUM('Order Lines'[Gross Sales])", USD,
     "What summing the source's 'Sales' column gives: price times quantity before discount, on\n"
     "every order including the cancelled ones. Kept to show how far it overstates."),
    ("Overstatement", "[Gross Sales (source column)] - [Net Sales]", USD, None),
    ("Overstatement %", "DIVIDE([Overstatement], [Net Sales])", PCT, None),
    ("Discount", f"CALCULATE(SUM('Order Lines'[Discount]), {SHIPPED})", USD, None),
    ("Discount Rate %",
     "DIVIDE(\n"
     "    [Discount],\n"
     f"    CALCULATE(SUM('Order Lines'[Gross Sales]), {SHIPPED})\n"
     ")", PCT,
     "Discount over gross value, shipped orders. Computed from the amounts, not averaged from\n"
     "the source's rate column, which disagrees with its own amounts on 10,029 lines."),
    ("Profit", f"CALCULATE(SUM('Order Lines'[Profit]), {SHIPPED})", USD, None),
    ("Margin %", "DIVIDE([Profit], [Net Sales])", PCT, None),
    ("Average Order Value", f"DIVIDE([Net Sales], CALCULATE([Orders], {SHIPPED}))", USD2, None),
    ("Loss-Making Lines",
     f"CALCULATE([Order Lines], {SHIPPED}, KEEPFILTERS('Order Lines'[Profit] < 0))", INT, None),
    ("Loss-Making Line Share %",
     f"DIVIDE([Loss-Making Lines], CALCULATE([Order Lines], {SHIPPED}))", PCT,
     "About 19% in every department, discount band, mode and market - flat enough to say the\n"
     "profit column was generated independently of everything the report can slice it by."),

    # ---- cancellations
    ("Cancelled Orders", f"CALCULATE([Orders], {CANCELLED})", INT,
     "Cancelled and suspected-fraud orders. They carry shipping dates anyway."),
    ("Cancelled Value", f"CALCULATE(SUM('Order Lines'[Net Sales]), {CANCELLED})", USD, None),
    ("Cancellation Rate %", "DIVIDE([Cancelled Orders], [Orders])", PCT, None),
    ("Suspected Fraud Orders",
     "CALCULATE([Orders], KEEPFILTERS('Outcome'[Is Suspected Fraud] = \"Yes\"))", INT, None),

    # ---- delivery, counted in orders
    ("Shipped Orders", f"CALCULATE([Orders], {SHIPPED})", INT, None),
    ("Late Orders", f"CALCULATE([Orders], {SHIPPED}, {LATE})", INT, None),
    ("Late Rate %", "DIVIDE([Late Orders], [Shipped Orders])", PCT,
     "Late orders over shipped orders. 57% overall - and 100% for First Class, which promises\n"
     "one day and takes two on every one of its 9,602 shipped orders."),
    ("On-Time Rate %", "IF(NOT ISBLANK([Shipped Orders]), 1 - [Late Rate %])", PCT,
     "On time or early, as a share of shipped orders."),
    ("Early Orders",
     f"CALCULATE([Orders], {SHIPPED}, KEEPFILTERS('Order Lines'[Days Late] < 0))", INT, None),
    ("Late by Days, All Orders",
     "CALCULATE([Orders], KEEPFILTERS('Order Lines'[Days Late] > 0))", INT,
     "Orders whose own dates say late, cancelled ones included - what a late rate built from\n"
     "the day columns instead of the status returns."),
    ("Late Rate % (by days, all orders)", "DIVIDE([Late by Days, All Orders], [Orders])", PCT,
     "The naive rate: every order's days, cancellations counted in. Shown beside the real one."),
    ("Cancelled but Late by Their Dates",
     f"CALCULATE([Orders], {CANCELLED}, KEEPFILTERS('Order Lines'[Days Late] > 0))", INT, None),
    ("Average Actual Days", per_order_avg("Actual Days", SHIPPED), DEC2,
     "Mean days to ship per order, shipped orders."),
    ("Average Promised Days", per_order_avg("Promised Days", SHIPPED), DEC2, None),
    ("Average Days Late", per_order_avg("Days Late", SHIPPED, LATE), DEC2,
     "How late the late orders were, on average."),
    ("Order Share of Month %",
     "DIVIDE([Orders], CALCULATE([Orders], REMOVEFILTERS('Geography')))", PCT,
     "This market's share of the month's orders - the measure behind the market calendar."),

    # ---- time
    ("Net Sales Jan-Sep",
     "CALCULATE([Net Sales], KEEPFILTERS('Date'[In Jan To Sep] = \"Yes\"))", USD,
     "January to September only: the window every year's main series covers."),
    ("Net Sales Jan-Sep PY", "CALCULATE([Net Sales Jan-Sep], DATEADD('Date'[Date], -1, YEAR))",
     USD, None),
    ("Net Sales Jan-Sep YoY %",
     "DIVIDE([Net Sales Jan-Sep] - [Net Sales Jan-Sep PY], [Net Sales Jan-Sep PY])", PCT,
     "Like for like. 2017's last quarter and 2018's January belong to the new series."),

    # ---- labels
    ("Report Period",
     "VAR First = MIN('Date'[Date])\n"
     "VAR Last = MAX('Date'[Date])\n"
     "VAR WholeYears = MONTH(First) = 1 && DAY(First) = 1 && MONTH(Last) = 12 && DAY(Last) = 31\n"
     "RETURN\n"
     "    SWITCH(\n"
     "        TRUE(),\n"
     "        WholeYears && YEAR(First) = YEAR(Last), FORMAT(Last, \"yyyy\"),\n"
     "        FORMAT(First, \"mmm yyyy\") & \" to \" & FORMAT(Last, \"mmm yyyy\")\n"
     "    )", None,
     "A label for the period on screen: '2016', or 'Jan 2015 to Jan 2018'."),
]


def m_partition(name: str, file: str, spec: dict, local: bool) -> list[str]:
    if local:
        path = str((DATA / file).resolve()).replace("\\", "\\\\")
        src = f'File.Contents("{path}")'
    else:
        src = f'Web.Contents("{RAW}{file}")'
    n = len(spec["types"])
    types = ", ".join(f'{{"{c}", {t}}}' for c, t in spec["types"].items())
    return [
        f"\tpartition {q(name)} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document({src}, [Delimiter=",", Columns={n}, '
        f'Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        '\t\t\t\t    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'\t\t\t\t    #"Applied Types" = Table.TransformColumnTypes(#"Promoted Headers", {{{types}}})',
        "\t\t\t\tin",
        '\t\t\t\t    #"Applied Types"',
    ]


def write_table(name: str, spec: dict, local: bool) -> None:
    lines: list[str] = []
    lines += doc(spec.get("doc"), 0)
    lines.append(f"table {q(name)}")
    lines.append(f"\tlineageTag: {tag('table', name)}")
    if spec.get("date_table"):
        lines.append("\tdataCategory: Time")
    for c in spec["columns"]:
        lines.append("")
        lines += doc(c.get("doc"), 1)
        lines.append(f"\tcolumn {q(c['name'])}")
        lines.append(f"\t\tdataType: {c['dtype']}")
        if c.get("hidden"):
            lines.append("\t\tisHidden")
        if c.get("key"):
            lines.append("\t\tisKey")
        if c.get("format"):
            lines.append(f"\t\tformatString: {c['format']}")
        if c.get("dataCategory"):
            lines.append(f"\t\tdataCategory: {c['dataCategory']}")
        lines.append(f"\t\tlineageTag: {tag('column', name, c['name'])}")
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {c['source']}")
        if c.get("sortBy"):
            lines.append(f"\t\tsortByColumn: {q(c['sortBy'])}")
    if "files" in spec:
        for pname, f in zip(spec["partition_names"], spec["files"]):
            lines.append("")
            lines += m_partition(f"{name} {pname}", f, spec, local)
    else:
        lines.append("")
        lines += m_partition(name, spec["file"], spec, local)
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    write(DEFN / "tables" / f"{name}.tmdl", lines)


def write_metrics() -> None:
    lines: list[str] = []
    lines += doc("Measure-only table. Nothing here stores data; the hidden column exists because\n"
                 "a table needs one. Every number on the report comes from here.", 0)
    lines.append("table Metrics")
    lines.append(f"\tlineageTag: {tag('table', 'Metrics')}")
    for name, dax, fmt, d in MEASURES:
        lines.append("")
        lines += doc(d, 1)
        body = dax.split("\n")
        if len(body) == 1:
            lines.append(f"\tmeasure {q(name)} = {body[0]}")
        else:
            lines.append(f"\tmeasure {q(name)} =")
            for b in body:
                lines.append(("\t\t\t" + b) if b.strip() else "\t\t\t")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tlineageTag: {tag('measure', name)}")
    lines.append("")
    lines.append("\tcolumn Column")
    lines.append("\t\tdataType: string")
    lines.append("\t\tisHidden")
    lines.append(f"\t\tlineageTag: {tag('column', 'Metrics', 'Column')}")
    lines.append("\t\tsummarizeBy: none")
    lines.append("\t\tsourceColumn: Column")
    lines.append("")
    lines.append("\tpartition Metrics = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append("\t\t\t\tlet")
    lines.append('\t\t\t\t    Source = #table(type table [Column = text], {})')
    lines.append("\t\t\t\tin")
    lines.append("\t\t\t\t    Source")
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    write(DEFN / "tables" / "Metrics.tmdl", lines)


def write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_json(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip("\n") + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="read data/ from disk, not GitHub")
    args = ap.parse_args()

    if DEFN.exists():
        for attempt in range(5):
            try:
                shutil.rmtree(DEFN)
                break
            except PermissionError:
                if attempt == 4:
                    shutil.rmtree(DEFN, ignore_errors=True)
                else:
                    time.sleep(0.5)

    for name, spec in TABLES.items():
        write_table(name, spec, args.local)
    write_metrics()

    write(DEFN / "database.tmdl", ["database", "\tcompatibilityLevel: 1606"])

    order = ", ".join(f'"{t}"' for t in TABLES)
    write(DEFN / "model.tmdl", [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "",
        f"annotation PBI_QueryOrder = [{order}]",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        'annotation PBI_ProTooling = ["DevMode"]',
        "",
    ] + [f"ref table {q(t)}" for t in list(TABLES) + ["Metrics"]])

    rel_lines: list[str] = []
    for i, (name, frm, to) in enumerate(RELATIONSHIPS):
        if i:
            rel_lines.append("")
        rel_lines += [f"relationship {q(name)}", f"\tfromColumn: {frm}", f"\ttoColumn: {to}"]
    write(DEFN / "relationships.tmdl", rel_lines)

    write_json(MODEL / "definition.pbism", """
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
  "version": "4.2",
  "settings": {
    "qnaEnabled": true
  }
}""")
    write_json(MODEL / ".platform", f"""
{{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
  "metadata": {{
    "type": "SemanticModel",
    "displayName": "Supply Chain"
  }},
  "config": {{
    "version": "2.0",
    "logicalId": "{tag('platform', 'model')}"
  }}
}}""")

    # The Calendar page: 'Cal ...' columns on the date table and its own measure table.
    milestone_calendar.install_model(DEFN, CALENDAR, lambda *p: tag("calendar", *p))
    n_calendar = len(milestone_calendar.measures(CALENDAR))
    print(f"  + Calendar Metrics: {n_calendar} measures, "
          f"{len(milestone_calendar.date_columns(CALENDAR))} calculated date columns")

    n_cols = sum(len(s["columns"]) for s in TABLES.values())
    print(f"{len(TABLES) + 1} tables, {n_cols} columns, {len(MEASURES)} measures, "
          f"{len(RELATIONSHIPS)} relationships -> {MODEL.name} "
          f"({'local files' if args.local else 'GitHub raw'})")


if __name__ == "__main__":
    main()
