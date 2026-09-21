"""The Calendar page's report-specific half. Everything else is etl/milestone_calendar.py.

The calendar is shaded by late orders: the day an order was placed, counted if it shipped and
arrived after its promised date. The second figure in each cell is the orders shipped that day,
so a dark cell on a busy day and a dark cell on a quiet one can be told apart.
"""

from milestone_calendar import Config

CALENDAR = Config(
    value="[Late Orders]",
    value_noun="late orders",
    money=False,
    count="[Shipped Orders]",
    count_one="shipped",
    count_many="shipped",
    title="Late-delivery calendar",
    ref="06 / CALENDAR",
    card_label="LATE ORDERS IN VIEW",
    total_icon="clock",
    peak_icon="clock-alert",
    peak_word="Worst",
    big_word="Worst",
    active_day="active day",
    none_note="no late orders",
    higher_is_better=False,   # more late orders is worse: a rise is red
    # The clean series ends in September 2017; October 2017 onwards is a different data regime.
    default_month="September",
    default_year=2017,
)
