"""Generate the PBIR report definition - five pages, the Milestone theme and every visual.

PBIR stores one JSON file per visual and wraps every property in the same
{"expr": {"Literal": {"Value": ...}}} envelope. Hand-editing that is how typos get in, so the
report is generated from this file: the helpers own the envelope and the page functions read as
layout.

    python etl/build_report.py

Rewrites <report>/definition/pages from scratch every run. That matters - a renamed visual left
behind on disk still renders, as an empty box.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import milestone_icons
import milestone_calendar
import milestone_pbir
from calendar_config import CALENDAR

ROOT = Path(__file__).resolve().parents[1]
NAME = "Supply Chain"
REPORT = ROOT / f"{NAME}.Report"
PAGES = REPORT / "definition" / "pages"
RESOURCES = REPORT / "StaticResources" / "RegisteredResources"
ASSETS = ROOT / "etl" / "assets"

CANVAS_W, CANVAS_H = 1440, 900

# --------------------------------------------------------------------------------------------
# Palette: milestonebi.com's own tokens.
# --------------------------------------------------------------------------------------------
PAPER = "#F4F6FA"
CARD = "#FFFFFF"
RULE = "#E3E7EF"
INK = "#0A0917"
BODY = "#4A5768"
MUTED = "#667284"
GOLD = "#C9A227"
GOLD_TEXT = "#8A6D14"
NAVY = "#111F38"
SLATE = "#7C8598"
LIGHT = "#BCC1D2"
STEEL = "#3D5A80"
GOOD = "#1E7A4C"
BAD = "#B3261E"

THEME_NAME = "MilestoneTheme.json"
MARK_NAME = "MilestoneMark.svg"

# --------------------------------------------------------------------------------------------
# Expression envelope helpers
# --------------------------------------------------------------------------------------------


def lit(value) -> dict:
    """Wrap a literal in the expression envelope PBIR expects.

    The suffix is load-bearing: 'D' for a double, 'L' for an integer, quotes for text. Getting
    it wrong makes Desktop drop the property silently rather than complain.
    """
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, int):
        v = f"{value}L"
    elif isinstance(value, float):
        v = f"{value}D"
    else:
        v = f"'{value}'"
    return {"expr": {"Literal": {"Value": v}}}


def colour(hex_code: str) -> dict:
    return {"solid": {"color": lit(hex_code)}}


def obj(**props) -> list:
    return [{"properties": props}]


def obj_for(metadata: str, **props) -> dict:
    return {"properties": props, "selector": {"metadata": metadata}}


def obj_for_value(table: str, col: str, value, **props) -> dict:
    """A property block scoped to one category value."""
    return {"properties": props, "selector": {"data": [{"scopeId": {"Comparison": {
        "ComparisonKind": 0,
        "Left": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "Right": lit(value)["expr"],
    }}}]}}


def measure(table: str, name: str, display: str | None = None) -> dict:
    field = {
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }
    if display:
        field["displayName"] = display
    return field


def column(table: str, name: str, display: str | None = None, active: bool = True) -> dict:
    field = {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }
    if active:
        field["active"] = True
    if display:
        field["displayName"] = display
    return field


def m(name: str, display: str | None = None) -> dict:
    return measure("Metrics", name, display)


def sort_by(field: dict, direction: str = "Descending") -> dict:
    return {"sort": [{"field": field["field"], "direction": direction}], "isDefaultSort": True}


def categorical_filter(name: str, table: str, col: str, values: list, alias: str = "t") -> dict:
    """A visual-level 'this column is one of these values' filter."""
    return {
        "name": name,
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}},
                                            "Property": col}}],
                "Values": [[lit(v)["expr"]] for v in values],
            }}}],
        },
    }


def topn_filter(name: str, table: str, col: str, n: int, by: dict, alias: str = "t") -> dict:
    """A visual-level Top N on a column, ranked by a measure."""
    return {
        "name": name,
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [{"Name": "subquery", "Expression": {"Subquery": {"Query": {
                "Version": 2,
                "From": [{"Name": alias, "Entity": table, "Type": 0},
                         {"Name": "m", "Entity": "Metrics", "Type": 0}],
                "Select": [{"Column": {"Expression": {"SourceRef": {"Source": alias}},
                                       "Property": col}, "Name": "field"}],
                "OrderBy": [{"Direction": 2, "Expression": {"Measure": {
                    "Expression": {"SourceRef": {"Source": "m"}},
                    "Property": by["field"]["Measure"]["Property"]}}}],
                "Top": n,
            }}}, "Type": 2},
                {"Name": alias, "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}},
                                            "Property": col}}],
                "Table": {"SourceRef": {"Source": "subquery"}},
            }}}],
        },
    }


# --------------------------------------------------------------------------------------------
# Container chrome
# --------------------------------------------------------------------------------------------


def chrome(title: str | None = None, subtitle: str | None = None, *,
           transparent: bool = False) -> dict:
    """Card background, hairline border and the small bold title every panel shares.

    subtitle is the second positional parameter and transparent is keyword-only: with them the
    other way round, chrome("Title", "Subtitle") put the caption into transparent and dropped it.
    """
    show = not transparent
    out = {
        "padding": obj(top=lit(8.0), bottom=lit(8.0), left=lit(10.0), right=lit(10.0)),
        "dropShadow": obj(show=lit(False)),
        "background": obj(show=lit(show), color=colour(CARD), transparency=lit(0.0)),
        "border": obj(show=lit(show), color=colour(RULE), radius=lit(4)),
    }
    if title:
        out["title"] = obj(show=lit(True), text=lit(title), fontSize=lit(10.5), bold=lit(True),
                           fontColor=colour(INK), heading=lit("Heading3"))
        if subtitle:
            out["subTitle"] = obj(show=lit(True), text=lit(subtitle), fontSize=lit(8.5),
                                  fontColor=colour(MUTED))
    else:
        out["title"] = obj(show=lit(False))
    return out


def visual(name: str, vtype: str, x: int, y: int, w: int, h: int, z: int,
           query: dict | None = None, objects: dict | None = None,
           container: dict | None = None, filters: list | None = None) -> dict:
    node: dict = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
        "visual": {"visualType": vtype},
    }
    if query is not None:
        node["visual"]["query"] = query
    if objects:
        node["visual"]["objects"] = objects
    node["visual"]["visualContainerObjects"] = container or chrome()
    if filters:
        # filterConfig is a sibling of "visual" at the root, not a child of it.
        node["filterConfig"] = {"filters": filters}
    return node


# --------------------------------------------------------------------------------------------
# Reusable formatting blocks
# --------------------------------------------------------------------------------------------


def axis(show_title: bool = False, gridlines: bool = False, size: float = 8.5, **extra) -> list:
    return [{"properties": {
        "show": lit(True), "showAxisTitle": lit(show_title), "fontSize": lit(size),
        "labelColor": colour(MUTED), "gridlineShow": lit(gridlines),
        **({"gridlineColor": colour(RULE)} if gridlines else {}),
        **extra,
    }}]


def legend(show: bool = True, position: str = "Top") -> list:
    return [{"properties": {
        "show": lit(show), "position": lit(position), "showTitle": lit(False),
        "fontSize": lit(8.5), "labelColor": colour(MUTED),
    }}]


def no_labels() -> list:
    return [{"properties": {"show": lit(False)}}]


def data_labels(size: float = 8.5, units: str = "1", colour_hex: str = BODY) -> list:
    return [{"properties": {
        "show": lit(True), "fontSize": lit(size), "color": colour(colour_hex),
        "labelDisplayUnits": lit(units),
    }}]


def series_colour(mapping: dict[str, str]) -> list:
    return [obj_for(k, fill=colour(v)) for k, v in mapping.items()]


def value_colours(table: str, col: str, mapping: dict) -> list:
    return [obj_for_value(table, col, k, fill=colour(v)) for k, v in mapping.items()]


def line_style() -> list:
    return [{"properties": {
        "strokeWidth": lit(2), "lineStyle": lit("solid"), "showMarker": lit(False),
    }}]


def no_chrome() -> dict:
    return {
        "padding": obj(top=lit(0.0), bottom=lit(0.0), left=lit(0.0), right=lit(0.0)),
        "dropShadow": obj(show=lit(False)),
        "background": obj(show=lit(False)),
        "border": obj(show=lit(False)),
        "title": obj(show=lit(False)),
    }


def textbox(name: str, x: int, y: int, w: int, h: int, z: int, paragraphs: list,
            background: str | None = None) -> dict:
    """paragraphs: each is a list of runs, or a single run dict for a one-run paragraph."""
    out = []
    for para in paragraphs:
        runs = para if isinstance(para, list) else [para]
        text_runs = []
        for run in runs:
            style = {"fontSize": f"{run.get('size', 11)}pt", "color": run.get("color", BODY)}
            if run.get("bold"):
                style["fontWeight"] = "bold"
            if run.get("family"):
                style["fontFamily"] = run["family"]
            if run.get("spacing"):
                style["letterSpacing"] = run["spacing"]
            text_runs.append({"value": run["text"], "textStyle": style})
        node = {"textRuns": text_runs}
        if runs[0].get("align"):
            node["horizontalTextAlignment"] = runs[0]["align"]
        out.append(node)
    container = no_chrome()
    if background:
        container["background"] = obj(show=lit(True), color=colour(background),
                                      transparency=lit(0.0))
        container["padding"] = obj(top=lit(4.0), bottom=lit(4.0), left=lit(10.0),
                                   right=lit(10.0))
    node = visual(name, "textbox", x, y, w, h, z, container=container)
    node["visual"]["objects"] = {"general": [{"properties": {"paragraphs": out}}]}
    return node


def note(name: str, x: int, y: int, w: int, h: int, z: int, heading: str,
         lines: list[str]) -> dict:
    """A card of prose - used where the honest caveat needs more room than a subtitle."""
    paras: list = [[{"text": heading, "size": 10.5, "color": INK, "bold": True}]]
    for line in lines:
        paras.append([{"text": "", "size": 4, "color": BODY}])
        paras.append([{"text": line, "size": 9, "color": BODY}])
    node = textbox(name, x, y, w, h, z, paras)
    node["visual"]["visualContainerObjects"] = chrome()
    return node


def image(name: str, x: int, y: int, w: int, h: int, z: int, resource: str) -> dict:
    node = visual(name, "image", x, y, w, h, z, container=no_chrome())
    node["visual"]["objects"] = {
        "general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
            "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": resource}}}}}],
        "imageScaling": [{"properties": {"imageScalingType": lit("Fit")}}],
    }
    return node


# Icons the KPI strips ask for; main() registers exactly these as report resources.
USED_ICONS: set[str] = set()


def kpi_card(name: str, x: int, y: int, w: int, h: int, z: int, measures: list[dict],
             filters: list | None = None, value_size: float = 17.0, icons: list[str] | None = None) -> dict:
    node = visual(
        name, "cardVisual", x, y, w, h, z,
        query={"queryState": {"Data": {"projections": measures}}},
        objects={
            "general": [{"properties": {}}],
            "value": [{"properties": {
                "fontSize": lit(value_size), "bold": lit(True), "fontColor": colour(INK),
                "fontFamily": lit("Segoe UI"), "horizontalAlignment": lit("Left"),
                # Without this the auto units turn 31,644,665 into "32M".
                "labelDisplayUnits": lit("1"),
            }, "selector": {"id": "default"}}],
            "label": [{"properties": {
                "show": lit(True), "fontSize": lit(8.5), "fontColor": colour(MUTED),
                "bold": lit(False), "position": lit("belowValue"),
                "horizontalAlignment": lit("Left"),
            }, "selector": {"id": "default"}}],
            "accentBar": [{"properties": {
                "show": lit(True), "color": colour(GOLD), "width": lit(3),
            }, "selector": {"id": "default"}}],
        },
        filters=filters,
    )
    if icons:
        # One icon to the left of each value, from etl/milestone_icons.py.
        node["visual"]["objects"]["image"] = milestone_icons.card_images(measures, icons, w)
        USED_ICONS.update(icons)
    return node


def slicer(name: str, x: int, y: int, w: int, h: int, z: int, table: str, col: str,
           header: str, mode: str = "Dropdown") -> dict:
    return visual(
        name, "slicer", x, y, w, h, z,
        query={"queryState": {"Values": {"projections": [column(table, col)]}}},
        objects={
            "general": [{"properties": {"orientation": lit(0)}}],
            "data": [{"properties": {"mode": lit(mode)}}],
            "header": [{"properties": {
                "show": lit(True), "text": lit(header), "textSize": lit(8.5),
                "fontColor": colour(MUTED), "bold": lit(True),
            }}],
            "items": [{"properties": {
                "fontColor": colour(BODY), "textSize": lit(9.5), "background": colour(CARD),
            }}],
        },
    )


def table_visual(name: str, x: int, y: int, w: int, h: int, z: int, fields: list[dict],
                 sort: dict | None, title: str, subtitle: str | None = None,
                 filters: list | None = None, totals: bool = False,
                 columns: list[dict] | None = None) -> dict:
    """A flat ranked table, or with columns= a cross-tab. Built as a matrix: on Desktop 2.157 a
    tableEx generated this way rendered the column fields and silently dropped every measure."""
    rows = [f for f in fields if "Column" in f["field"]]
    values = [f for f in fields if "Measure" in f["field"]]
    state = {"Rows": {"projections": rows}, "Values": {"projections": values}}
    if columns:
        state["Columns"] = {"projections": columns}
    query: dict = {"queryState": state}
    if sort:
        query["sortDefinition"] = sort
    return visual(
        name, "pivotTable", x, y, w, h, z,
        query=query,
        objects={
            "grid": [{"properties": {
                "gridVertical": lit(False), "gridHorizontal": lit(True),
                "gridHorizontalColor": colour(RULE), "rowPadding": lit(3),
            }}],
            "columnHeaders": [{"properties": {
                "fontSize": lit(9.0), "bold": lit(True), "fontColor": colour(INK),
                "backColor": colour(CARD), "alignment": lit("Right"),
            }}],
            "rowHeaders": [{"properties": {
                "fontSize": lit(9.0), "fontColor": colour(BODY), "backColor": colour(CARD),
            }}],
            "values": [{"properties": {
                "fontSize": lit(9.0), "fontColorPrimary": colour(BODY),
                "backColorPrimary": colour(CARD), "backColorSecondary": colour(CARD),
            }}],
            "subTotals": [{"properties": {"rowSubtotals": lit(totals),
                                          "columnSubtotals": lit(totals)}}],
        },
        container=chrome(title, subtitle=subtitle),
        filters=filters,
    )


def chart(name: str, vtype: str, x: int, y: int, w: int, h: int, z: int, category: dict,
          values: list[dict], title: str, subtitle: str | None = None, *,
          series: dict | None = None, tooltips: list[dict] | None = None,
          sort: dict | None = None, colours: list | None = None, labels: list | None = None,
          show_legend: bool = False, filters: list | None = None) -> dict:
    state: dict = {"Category": {"projections": [category]}, "Y": {"projections": values}}
    if series:
        state["Series"] = {"projections": [series]}
    if tooltips:
        state["Tooltips"] = {"projections": tooltips}
    objects: dict = {
        "categoryAxis": axis(), "valueAxis": axis(gridlines=True),
        "legend": legend(show_legend), "labels": labels or no_labels(),
    }
    if vtype == "lineChart":
        objects["lineStyles"] = line_style()
    if colours:
        objects["dataPoint"] = colours
    query: dict = {"queryState": state}
    if sort:
        query["sortDefinition"] = sort
    return visual(name, vtype, x, y, w, h, z, query=query, objects=objects,
                  container=chrome(title, subtitle), filters=filters)


# --------------------------------------------------------------------------------------------
# Masthead
# --------------------------------------------------------------------------------------------


def masthead(slug: str, title: str, standfirst: str, ref: str) -> list[dict]:
    return [
        textbox(f"vBand{slug}", 0, 0, CANVAS_W, 60, 50, [
            [{"text": "", "size": 6, "color": INK}],
        ], background=INK),
        image(f"vMark{slug}", 24, 12, 44, 38, 60, MARK_NAME),
        textbox(f"vWordmark{slug}", 76, 15, 260, 32, 70, [
            [{"text": "Milestone ", "size": 15, "color": CARD, "bold": True},
             {"text": "BI", "size": 15, "color": GOLD, "bold": True}],
        ]),
        textbox(f"vRef{slug}", 1016, 22, 400, 22, 80, [
            [{"text": ref, "size": 8, "color": GOLD, "bold": True, "family": "Consolas",
              "spacing": "2px", "align": "right"}],
        ]),
        textbox(f"vTitle{slug}", 24, 74, 1000, 40, 90, [
            [{"text": title, "size": 22, "color": INK, "bold": True}],
        ]),
        textbox(f"vStand{slug}", 24, 114, 1030, 46, 95, [
            [{"text": standfirst, "size": 10, "color": BODY}],
        ]),
    ]


def page(name: str, display: str) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
        "name": name,
        "displayName": display,
        "displayOption": "FitToPage",
        "height": CANVAS_H,
        "width": CANVAS_W,
        "objects": {
            "background": obj(color=colour(PAPER), transparency=lit(0.0)),
            "displayArea": obj(verticalAlignment=lit("Top")),
        },
    }


MODE_COLOURS = {"Same Day": SLATE, "First Class": GOLD, "Second Class": NAVY,
                "Standard Class": LIGHT}
MARKET_COLOURS = {"LATAM": NAVY, "Europe": GOLD, "Pacific Asia": SLATE, "USCA": LIGHT,
                  "Africa": STEEL}

SL_Y, SL_H = 74, 84
SL1_X, SL2_X, SL_W = 1076, 1246, 170

MONTH = column("Date", "Month Start", "Month")
MONTH_SORT = sort_by(column("Date", "Month Start"), "Ascending")
YEAR_SORT = sort_by(column("Date", "Year"), "Ascending")
MODE_SORT = sort_by(column("Shipping Mode", "Shipping Mode"), "Ascending")


def year_controls(slug: str) -> list[dict]:
    return [
        slicer(f"vYear{slug}", SL1_X, SL_Y, SL_W, SL_H, 400, "Date", "Year", "YEAR"),
        kpi_card(f"vPeriod{slug}", SL2_X, SL_Y, SL_W, SL_H, 410,
                 [m("Report Period", "Figures for")], value_size=11.0),
    ]


# --------------------------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------------------------


def page_overview() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Ovr",
        "Orders and delivery, January 2015 to January 2018",
        "65,752 orders from a sports and outdoor retailer shipping to 164 countries. Sales are "
        "net of discount on orders that shipped - the source's 'Sales' column is neither. "
        "Delivery is counted in orders, not lines. Every figure follows the year slicer.",
        "01 / OVERVIEW",
    )
    v += year_controls("Ovr")

    v.append(kpi_card("vKpiOvr", 24, 176, 1392, 92, 500, [
        m("Net Sales", "Net sales, shipped orders"),
        m("Orders", "Orders"),
        m("Margin %", "Margin"),
        m("Late Rate %", "Shipped late"),
        m("Cancellation Rate %", "Cancelled"),
    ], icons=["coin", "cart", "percent", "clock", "cancel"]))

    v.append(chart(
        "vTrend", "lineChart", 24, 284, 900, 300, 600,
        MONTH, [m("Net Sales")],
        "Net sales by month",
        "Level for 33 months, then a new generator from October 2017 - page 5 shows the join",
        sort=MONTH_SORT, colours=series_colour({"Metrics.Net Sales": NAVY}),
    ))

    v.append(table_visual(
        "vYears", 940, 284, 476, 300, 610,
        [
            column("Date", "Year"),
            m("Orders", "Orders"),
            m("Net Sales", "Net sales"),
            m("Margin %", "Margin"),
            m("Late Rate %", "Late"),
            m("Lines per Order", "Lines/order"),
        ],
        YEAR_SORT,
        "Year by year",
        "2018 is one month of the new series; 2017 is nine months of each",
    ))

    v.append(chart(
        "vDept", "barChart", 24, 600, 452, 276, 620,
        column("Product", "Department"), [m("Net Sales")],
        "Net sales by department",
        "Fan shop and apparel are two thirds of the book",
        tooltips=[m("Margin %", "Margin"), m("Orders")],
        sort=sort_by(m("Net Sales")), colours=series_colour({"Metrics.Net Sales": NAVY}),
        labels=data_labels(units="1000000"),
    ))

    v.append(chart(
        "vModeLate", "barChart", 492, 600, 452, 276, 630,
        column("Shipping Mode", "Shipping Mode"), [m("Late Rate %", "Late")],
        "Share of shipped orders delivered late, by mode",
        tooltips=[m("Shipped Orders", "Shipped"), m("Average Promised Days", "Promised"),
                  m("Average Actual Days", "Actual")],
        sort=MODE_SORT,
        colours=value_colours("Shipping Mode", "Shipping Mode", MODE_COLOURS),
        labels=data_labels(),
    ))

    v.append(note(
        "vFirstClass", 960, 600, 456, 276, 640,
        "First Class is never on time",
        ["It promises one day and takes two - on every one of its 9,602 shipped orders. The "
         "premium mode is the only one with a 100% late rate.",
         "Second Class promises two days and is late 80% of the time. Standard promises four "
         "and is late 40%. The actual days behind them are identical; page 2 shows it.",
         "The fault is the promise, not the warehouse."],
    ))

    return page("pgOverview", "Overview"), v


def page_delivery() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Dlv",
        "The promise against the delivery",
        "Every shipping mode promises a lead time; the file records the days each order took. "
        "Cancelled and suspected-fraud orders are left out - they carry shipping days anyway, "
        "and 1,650 of them would count as late if they were let in.",
        "02 / DELIVERY",
    )
    v += year_controls("Dlv")

    v.append(kpi_card("vKpiDlv", 24, 176, 1392, 92, 500, [
        m("Shipped Orders", "Shipped orders"),
        m("Late Rate %", "Late"),
        m("Average Promised Days", "Days promised, average"),
        m("Average Actual Days", "Days taken, average"),
        m("Average Days Late", "Days late, when late"),
    ], icons=["truck", "clock", "calendar", "hourglass", "clock-alert"]))

    v.append(table_visual(
        "vDays", 24, 284, 900, 300, 600,
        [column("Shipping Mode", "Shipping Mode", "Mode"), m("Shipped Orders", "Orders")],
        None,
        "Shipped orders by mode and by days actually taken",
        "Second Class and Standard Class take 2 to 6 days in equal measure. Only the promise differs",
        totals=True,
        columns=[column("Order Lines", "Actual Days", "Days taken")],
    ))

    v.append(table_visual(
        "vModes", 940, 284, 476, 300, 610,
        [
            column("Shipping Mode", "Shipping Mode", "Mode"),
            m("Average Promised Days", "Promised"),
            m("Average Actual Days", "Actual"),
            m("Late Rate %", "Late"),
            m("Average Days Late", "Days late"),
        ],
        MODE_SORT,
        "What each mode promises, and does",
    ))

    late_month = chart(
        "vLateMonth", "lineChart", 24, 600, 452, 276, 620,
        MONTH, [m("Late Rate %", "Late")],
        "Late rate by month",
        "Flat at 57% for three years - it never responds to anything",
        sort=MONTH_SORT, colours=series_colour({"Metrics.Late Rate %": GOLD}),
    )
    # Pinned to 0-100%. Left to auto-scale, the axis ran 56% to 60% and a flat line read as a
    # volatile one - the opposite of what the caption says.
    late_month["visual"]["objects"]["valueAxis"] = axis(gridlines=True, start=lit(0.0),
                                                        end=lit(1.0))
    v.append(late_month)

    v.append(chart(
        "vNaive", "clusteredBarChart", 492, 600, 452, 276, 630,
        column("Shipping Mode", "Shipping Mode"),
        [m("Late Rate %", "Shipped orders, by status"),
         m("Late Rate % (by days, all orders)", "All orders, by their days")],
        "Two ways to count late",
        "Letting cancellations in moves no rate by 0.1 points",
        sort=MODE_SORT,
        colours=series_colour({"Metrics.Late Rate %": NAVY,
                               "Metrics.Late Rate % (by days, all orders)": LIGHT}),
        show_legend=True,
    ))

    v.append(note(
        "vDlvNote", 960, 600, 456, 276, 640,
        "Paying more buys a different promise, not a faster parcel",
        ["The days taken by Second Class and Standard Class orders are indistinguishable: "
         "about a fifth each at 2, 3, 4, 5 and 6 days. First Class is always 2. Same Day is "
         "0 or 1, half each.",
         "So the late rate is set entirely by the promise. Promise four days and 40% are late; "
         "promise two and 80% are; promise one and every order is.",
         "In a real network the fix is the promise table, and it costs nothing to change."],
    ))

    return page("pgDelivery", "Delivery"), v


def page_products() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Prd",
        "What sells, and what it earns",
        "Net sales and margin by category and product, on shipped orders. One line in five "
        "loses money - and the share barely moves with discount, department or anything else "
        "the report can slice it by.",
        "03 / PRODUCTS",
    )
    v += year_controls("Prd")

    v.append(kpi_card("vKpiPrd", 24, 176, 1392, 92, 500, [
        m("Net Sales", "Net sales"),
        m("Profit", "Profit"),
        m("Margin %", "Margin"),
        m("Discount Rate %", "Discount, of gross"),
        m("Loss-Making Line Share %", "Lines that lose money"),
    ], icons=["coin", "bag", "percent", "tag", "trend-down"]))

    v.append(chart(
        "vCategory", "barChart", 24, 284, 900, 300, 600,
        column("Product", "Category"), [m("Net Sales")],
        "Net sales by category, top 15",
        "Five categories make up most of the book",
        tooltips=[m("Margin %", "Margin"), m("Units")],
        sort=sort_by(m("Net Sales")), colours=series_colour({"Metrics.Net Sales": NAVY}),
        labels=data_labels(units="1000000"),
        filters=[topn_filter("fTopCat", "Product", "Category", 15, m("Net Sales"), "p")],
    ))

    v.append(table_visual(
        "vDepts", 940, 284, 476, 300, 610,
        [
            column("Product", "Department"),
            m("Net Sales", "Net sales"),
            m("Margin %", "Margin"),
            m("Discount Rate %", "Discount"),
            m("Loss-Making Line Share %", "Loss lines"),
        ],
        sort_by(m("Net Sales")),
        "By department",
        "Loss-line share sits near 19% in every one",
    ))

    v.append(table_visual(
        "vProducts", 24, 600, 880, 276, 620,
        [
            column("Product", "Product"),
            m("Units", "Units"),
            m("Net Sales", "Net sales"),
            m("Profit", "Profit"),
            m("Margin %", "Margin"),
            m("Loss-Making Line Share %", "Loss lines"),
        ],
        sort_by(m("Net Sales")),
        "Products, best-selling first",
        "Ten products carry most of the value; the rest is a long tail",
    ))

    v.append(note(
        "vProfitNote", 920, 600, 496, 276, 630,
        "Profit that does not respond to anything",
        ["About 19% of lines lose money whether the discount is 0% or 25%, whether the order "
         "shipped late or early, and in every department, mode and market.",
         "Real margin moves with discount and with freight. This file's does not, which says "
         "the profit column was generated independently of the rest.",
         "So the page reports where the money is and stops short of explaining the losses."],
    ))

    return page("pgProducts", "Products"), v


def page_markets() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Mkt",
        "Where the orders went - and when",
        "Orders by destination market, region and country, with the Spanish country names in "
        "the source translated. Before comparing the markets, look at the first chart: in most "
        "months every order goes to one of them.",
        "04 / MARKETS",
    )
    v += year_controls("Mkt")

    v.append(kpi_card("vKpiMkt", 24, 176, 1392, 92, 500, [
        m("Orders", "Orders"),
        m("Net Sales", "Net sales"),
        m("Average Order Value", "Average order"),
        m("Customers", "Customers"),
        m("Late Rate %", "Shipped late"),
    ], icons=["cart", "coin", "receipt", "people", "clock"]))

    v.append(chart(
        "vCalendar", "hundredPercentStackedColumnChart", 24, 284, 900, 300, 600,
        MONTH, [m("Orders")],
        "Share of each month's orders by market",
        "LATAM, then Europe, then Pacific Asia, then the US: the market is a calendar",
        series=column("Geography", "Market", active=False),
        sort=MONTH_SORT, colours=value_colours("Geography", "Market", MARKET_COLOURS),
        show_legend=True,
    ))

    v.append(table_visual(
        "vMarkets", 940, 284, 476, 300, 610,
        [
            column("Geography", "Market"),
            m("Orders", "Orders"),
            m("Net Sales", "Net sales"),
            m("Margin %", "Margin"),
            m("Late Rate %", "Late"),
        ],
        sort_by(m("Net Sales")),
        "By market",
        "Margin 12% and late rate 57% in all five",
    ))

    v.append(table_visual(
        "vCountries", 24, 600, 880, 276, 620,
        [
            column("Geography", "Country"),
            m("Orders", "Orders"),
            m("Net Sales", "Net sales"),
            m("Average Order Value", "Average order"),
            m("Margin %", "Margin"),
        ],
        sort_by(m("Net Sales")),
        "Destination countries, largest first",
        "164 countries, named in Spanish in the source",
    ))

    v.append(note(
        "vCalNote", 920, 600, 496, 276, 630,
        "A market comparison is a month comparison",
        ["In 26 of the 37 months every order goes to a single market, and in 28 one market "
         "takes 90% or more. LATAM has the first five months to itself; Europe the next five.",
         "So 'LATAM sells more than Africa' mostly means LATAM was given more months. Margin "
         "and late rate are the same everywhere, which is the tell.",
         "The table ranks the markets because readers will ask. The chart is the answer."],
    ))

    return page("pgMarkets", "Markets"), v


def page_quality() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Dq",
        "What the source gets wrong",
        "Every figure in this report rests on decisions about the data. This page shows the "
        "evidence for the four that matter most, so a reviewer can disagree with a decision "
        "rather than having to find it.",
        "05 / DATA QUALITY",
    )

    v.append(kpi_card("vKpiDq", 24, 176, 1392, 92, 500, [
        m("Gross Sales (source column)", "The 'Sales' column, summed"),
        m("Net Sales", "Net sales, shipped"),
        m("Overstatement %", "Overstated by"),
        m("Cancelled Orders", "Cancelled orders"),
        m("Cancelled but Late by Their Dates", "...late by their own dates"),
    ], icons=["database", "coin", "warning", "cancel", "clock-alert"]))

    v.append(chart(
        "vLinesPerOrder", "lineChart", 24, 284, 452, 300, 600,
        MONTH, [m("Lines per Order")],
        "Lines per order, by month",
        "Three for 33 months, then exactly one",
        sort=MONTH_SORT, colours=series_colour({"Metrics.Lines per Order": NAVY}),
    ))

    v.append(chart(
        "vProductsMonth", "columnChart", 492, 284, 452, 300, 610,
        MONTH, [m("Products Sold")],
        "Distinct products sold, by month",
        "100 of 101 products leave with the switch; 17 new ones arrive",
        sort=MONTH_SORT, colours=series_colour({"Metrics.Products Sold": SLATE}),
    ))

    v.append(table_visual(
        "vPayStatus", 960, 284, 456, 300, 620,
        [column("Outcome", "Order Status", "Order status"), m("Orders", "Orders")],
        sort_by(column("Outcome", "Order Status"), "Ascending"),
        "Order status by payment type",
        "Each payment type allows only its own statuses",
        columns=[column("Outcome", "Payment Type", "Paid by")],
    ))

    v.append(note(
        "vRevenueNote", 24, 600, 452, 276, 630,
        "Revenue is not the column called Sales",
        ["'Sales' is price times quantity before discount, on every order including the "
         "cancelled ones. The money that changed hands is 'Order Item Total', on orders that "
         "shipped. Summing 'Sales' overstates it by 16%.",
         "'Order Profit Per Order' is per line, not per order, and 'Benefit per order' and "
         "'Sales per customer' are exact copies of other columns under misleading names."],
    ))

    v.append(note(
        "vLateNote", 492, 600, 452, 276, 640,
        "The late flag is a status, not a risk",
        ["'Late_delivery_risk' is 1 exactly when the delivery status says late - it predicts "
         "nothing. Cancelled orders are never flagged, though 1,650 of them carry shipping days "
         "past their promise.",
         "Delivery measures here use the status and leave cancellations out. Page 2 shows the "
         "rate the day columns alone would give."],
    ))

    v.append(note(
        "vSmallNote", 960, 600, 456, 276, 650,
        "Smaller fixes, all in the ETL",
        ["Countries are in Spanish - 'Estados Unidos', 'Alemania' - and are translated; the "
         "build fails on a name it does not know.",
         "Customer names are placeholders (65,150 lines are 'Mary'), email and password are "
         "masked. All of it is dropped.",
         "The discount rate disagrees with the discount amount on 10,029 lines; measures use "
         "the amounts, which reconcile to the line total."],
    ))

    return page("pgQuality", "Data quality"), v


# --------------------------------------------------------------------------------------------
# Theme and writers
# --------------------------------------------------------------------------------------------


def theme() -> dict:
    return {
        # Desktop caches themes by name, and the name must match the filename exactly.
        "name": THEME_NAME,
        "dataColors": [NAVY, GOLD, SLATE, LIGHT, STEEL, GOOD, BAD, GOLD_TEXT, MUTED],
        "background": PAPER,
        "foreground": BODY,
        "tableAccent": INK,
        "good": GOOD,
        "neutral": MUTED,
        "bad": BAD,
        "textClasses": {
            "title": {"fontFace": "Segoe UI Semibold", "fontSize": 14, "color": INK},
            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 11, "color": INK},
            "label": {"fontFace": "Segoe UI", "fontSize": 9, "color": BODY},
            "callout": {"fontFace": "Segoe UI", "fontSize": 20, "color": INK},
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"show": True, "color": {"solid": {"color": CARD}}}],
                    "border": [{"show": True, "color": {"solid": {"color": RULE}}, "radius": 4}],
                    "padding": [{"top": 8, "bottom": 8, "left": 10, "right": 10}],
                    "dropShadow": [{"show": False}],
                }
            }
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # No BOM: a BOM breaks .platform and PBIR parsing. newline="\n" because write_text otherwise
    # uses the platform ending, and the repo is normalised to LF.
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def rmtree_retry(path: Path) -> None:
    """OneDrive intermittently holds a directory handle open; the files are gone by then."""
    for attempt in range(4):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 3:
                shutil.rmtree(path, ignore_errors=True)
                return
            time.sleep(0.4)


CALENDAR_BOOKMARKS: list[dict] = []


def page_calendar() -> tuple[dict, list[dict]]:
    """The heat-mapped calendar, generated by etl/milestone_calendar.py from CALENDAR."""
    pg, visuals, bookmarks = milestone_calendar.build_page(CALENDAR)
    CALENDAR_BOOKMARKS[:] = bookmarks
    return pg, visuals


def main() -> None:
    if PAGES.exists():
        rmtree_retry(PAGES)

    builders = [page_overview, page_delivery, page_products, page_markets, page_quality, page_calendar]
    order: list[str] = []
    total_visuals = 0

    for build in builders:
        pg, visuals = build()
        page_dir = PAGES / pg["name"]
        write_json(page_dir / "page.json", pg)
        names = set()
        for node in visuals:
            if node["name"] in names:
                print(f"ERROR: duplicate visual name {node['name']} on {pg['name']}",
                      file=sys.stderr)
                sys.exit(1)
            names.add(node["name"])
            write_json(page_dir / "visuals" / node["name"] / "visual.json", node)
        order.append(pg["name"])
        total_visuals += len(visuals)
        print(f"  {pg['name']:14s} {len(visuals):2d} visuals  ({pg['displayName']})")

    stale = [d for d in PAGES.rglob("visuals/*")
             if d.is_dir() and not (d / "visual.json").exists()]
    for d in stale:
        rmtree_retry(d)
        if d.exists():
            print(f"ERROR: could not remove stale visual directory {d}. "
                  f"Close Power BI Desktop and run again.", file=sys.stderr)
            sys.exit(1)
        print(f"  swept stale visual directory {d.name}")

    write_json(PAGES / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": order,
        "activePageName": order[0],
    })

    bookmarks_dir = REPORT / "definition" / "bookmarks"
    if bookmarks_dir.exists():
        rmtree_retry(bookmarks_dir)
    for bm in CALENDAR_BOOKMARKS:
        write_json(bookmarks_dir / f"{bm['name']}.bookmark.json", bm)
    write_json(bookmarks_dir / "bookmarks.json", milestone_pbir.bookmarks_metadata(CALENDAR_BOOKMARKS))

    write_json(REPORT / "definition" / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })

    write_json(REPORT / "definition" / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
        "themeCollection": {
            "baseTheme": {
                "name": "CY25SU12",
                "reportVersionAtImport": {"visual": "2.12.0", "report": "3.4.0",
                                          "page": "2.3.1"},
                "type": "SharedResources",
            },
            "customTheme": {
                "name": THEME_NAME,
                "reportVersionAtImport": {"visual": "2.12.0", "report": "3.4.0",
                                          "page": "2.3.1"},
                "type": "RegisteredResources",
            },
        },
        "objects": {
            "section": [{"properties": {"verticalAlignment": lit("Top")}}],
            "outspacePane": [{"properties": {"expanded": lit(False)}}],
        },
        "resourcePackages": [
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": THEME_NAME, "path": THEME_NAME, "type": "CustomTheme"},
                       {"name": MARK_NAME, "path": MARK_NAME, "type": "Image"}]
                      + [{"name": n, "path": n, "type": "Image"}
                         for n in milestone_icons.resources(USED_ICONS)]},
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY25SU12", "path": "BaseThemes/CY25SU12.json",
                        "type": "BaseTheme"}]},
        ],
        "settings": {"useStylableVisualContainerHeader": True, "useEnhancedTooltips": False},
    })

    RESOURCES.mkdir(parents=True, exist_ok=True)
    write_json(RESOURCES / THEME_NAME, theme())
    shutil.copyfile(ASSETS / "milestone-mark.svg", RESOURCES / MARK_NAME)
    for icon_file, svg in milestone_icons.resources(USED_ICONS).items():
        (RESOURCES / icon_file).write_text(svg, encoding="utf-8", newline="\n")

    write_json(REPORT / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    })

    write_json(REPORT / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": "3a9e5d17-6c42-4b8f-a1d3-9f2b7e4c6a05"},
    })

    write_json(ROOT / f"{NAME}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })

    print(f"\n{len(order)} pages, {total_visuals} visuals written")


if __name__ == "__main__":
    main()
