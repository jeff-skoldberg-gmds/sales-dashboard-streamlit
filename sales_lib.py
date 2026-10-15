"""Shared data access, period logic, formatting and charts for the sales dashboard.

Every page reads RPT_SALES_FILTERED from the analytics database the app is
deployed into, and every query built here applies `where is_reportable`. That
flag is the reporting contract, and it keeps internal transfers, samples and
non-food lines out of every figure.

Two things shape this app, and both live here.

**One filter bar, shared by every page.** The widget keys are prefixed `sales_`
rather than by page, so a period, a measure and a set of filters chosen anywhere
follow the reader through the whole app. This app is walked page to page while chasing one question, and re-picking the same
customer five times is the fastest way to lose the thread. Every page therefore
offers exactly the same filters, which is also what makes shared keys safe: a
stored selection is always still a legal option on the next page.

**Periods are trailing windows against a matched prior year**, not a year and
month picker. A trailing window ends at the last *complete* week or month, so a
half-finished period never reads as a collapse, and the comparison window is
shifted by 364 days -- 52 whole weeks -- rather than by a calendar year, so
Saturday-ending weeks line up with Saturday-ending weeks. Year to date and a
custom range shift by a calendar year instead, because those are month and date
ranges rather than week counts.
"""

import calendar
import datetime as dt
import json
import re
import textwrap
from pathlib import Path
from typing import NamedTuple

import altair as alt
import duckdb
import numpy as np
import pandas as pd
import streamlit as st

SALES_VIEW = "rpt_sales_filtered"
BUDGET_MONTHLY_VIEW = "rpt_budget_filtered"
BUDGET_WEEKLY_VIEW = "rpt_budget_weekly"

KEY = "sales"

BAR_SELECTION = "bar_click"
SELECTION_EPOCH = "_selection_epoch"
DRILL_PENDING = "_pending_drill"
NOTE_PENDING = "_pending_note"
DRILL_SHOWN = "_drill_shown"
SCOPE_STACK = "_scope_stack"
ORIGIN = "_drill_origin"
PAGE = "_page"

PAGE_FILES = {
    "Pulse": "pages/pulse.py",
    "Customers": "pages/customers.py",
    "Products": "pages/products.py",
    "Detail": "pages/detail.py",
    "Documentation": "pages/documentation.py",
}

DETAIL_PAGE = PAGE_FILES["Detail"]

HEADER_KEY = "sales_header"
PERIOD_WIDTH = 170
DATES_WIDTH = 230

OPTION_YEARS = 3

HEADER_BUTTONS = {
    "branded": "Branded",
}

FILTER_BUTTONS = {
    "product_class": "Product Class",
}

FILTER_FIELDS = {
    "organization": "Organization",
    "superchain_customer": "Superchain / Customer",
    "customer_name": "Customer",
    "sales_representative": "Sales Representative",
    "brand": "Brand",
    "item": "Item",
    "product_category": "Product Category",
    "product_group": "Product Group",
    "pl_hierarchy": "P&L Hierarchy",
    "pl_sub_hierarchy": "P&L Sub-Hierarchy",
    "pack_size": "Pack Size",
    "dairy_deli": "Temperature",
    "company": "WHS / DSD",
    "promoted_product_group_description": "PPG",
}

FILTER_COLUMNS = {**HEADER_BUTTONS, **FILTER_BUTTONS, **FILTER_FIELDS}

GROUPABLE = {
    "product_class": "product_class",
    "product_category": "product_category",
    "product_group": "product_group",
    "brand": "brand",
    "pl_hierarchy": "pl_hierarchy",
    "pack_size": "pack_size",
    "promoted_product_group_description": "promoted_product_group_description",
    "organization": "organization",
    "superchain_customer": "superchain_customer",
    "sales_representative": "sales_representative",
    "customer_number": "customer_name",
    "item_number": "item_description",
}

MEASURES = {
    "Dollars": ("invoiced_dollars", "money"),
    "Cases": ("case_quantity", "number"),
}

DEFAULT_MEASURE = "Dollars"

SERIES_CURRENT = "#0e7c86"
SERIES_PRIOR = "#9db1ba"
SERIES_BUDGET = "#c96f12"
GOOD_INK = "#17924f"
BAD_INK = "#d03b3b"
MUTED_INK = "#6b7b83"

# Vega's default gridline grey is invisible against the pale page.
GRID_INK = "#6b7b83"
GRID_OPACITY = 0.18

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

PERIODS = ["4 weeks", "13 weeks", "26 weeks", "52 weeks", "Year to date", "Custom range"]

WEEK_PRESETS = {"4 weeks": 4, "13 weeks": 13, "26 weeks": 26, "52 weeks": 52}

# A quarter is the shortest window in which a seasonal business is readable
# and the longest most people will call recent, so it is where the app opens.
DEFAULT_PERIOD = "13 weeks"

PRIOR_YEAR_DAYS = 364


DB_PATH = Path(__file__).parent / "data" / "crooked_crow.duckdb"

MACROS = (
    "create or replace temp macro iff(c, a, b) as case when c then a else b end",
    "create or replace temp macro date_from_parts(y, m, d) as make_date(y, m, d)",
    "create or replace temp macro dateadd_day(n, d) as (cast(d as date) + to_days(cast(n as integer)))::date",
    "create or replace temp macro dateadd_week(n, d) as (cast(d as date) + to_days(7 * cast(n as integer)))::date",
    "create or replace temp macro dateadd_month(n, d) as (cast(d as date) + to_months(cast(n as integer)))::date",
    "create or replace temp macro dateadd_year(n, d) as (cast(d as date) + to_years(cast(n as integer)))::date",
    "create or replace temp macro datediff_day(a, b) as date_diff('day', cast(a as date), cast(b as date))",
)


def translate(sql: str) -> str:
    """Rewrite the Snowflake spellings the pages use into their DuckDB macros.

    Args:
        sql: A statement written for Snowflake.

    Returns:
        The same statement with `dateadd(unit, ...)` and `datediff(day, ...)`
        pointed at macros that take the unit in their name.
    """
    sql = re.sub(r"\bdateadd\(\s*(day|week|month|year)\s*,", r"dateadd_\1(", sql)
    return re.sub(r"\bdatediff\(\s*day\s*,", "datediff_day(", sql)


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    """Open the demo database once and share it between viewers.

    Returns:
        A read-only DuckDB connection.
    """
    return duckdb.connect(str(DB_PATH), read_only=True)


def source_schema() -> str:
    """Return the schema every relation lives in.

    Returns:
        DuckDB's default schema; the demo has no builds to choose between.
    """
    return "main"


def source() -> str:
    """Return the sales reporting view every page reads.

    Returns:
        The relation name.
    """
    return SALES_VIEW


def budget_source(weekly: bool) -> str:
    """Return the budget relation.

    Args:
        weekly: Whether the weekly allocation is wanted rather than the monthly.

    Returns:
        The relation name.
    """
    return BUDGET_WEEKLY_VIEW if weekly else BUDGET_MONTHLY_VIEW


@st.cache_data(ttl=3600)
def relations_present(database: str, schema: str) -> set:
    """Return which relations exist, so a missing budget draws nothing.

    Args:
        database: Unused; kept so the pages' calls need no change.
        schema: Unused for the same reason.

    Returns:
        The lower-case names of the tables the demo database holds.
    """
    frame = run_query("select table_name as t from information_schema.tables")
    return {str(name).lower() for name in frame["T"].tolist()}


def app_database() -> str:
    """Return a placeholder database name, unused by the demo's queries.

    Returns:
        A fixed name.
    """
    return "crooked_crow"


def source_picker() -> bool:
    """Say there is always a build to read.

    Returns:
        True.
    """
    return True


PAGE_KEY = "_demo_page"


def remember_page(page) -> None:
    """Record the page about to run.

    Args:
        page: The StreamlitPage that st.navigation selected.
    """
    st.session_state[PAGE_KEY] = page.title


def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a query against the demo database and return the result.

    Args:
        sql: The full SQL statement to run.
        params: Bind parameters, as a tuple so the result can be cached.

    Returns:
        The result as a pandas DataFrame with upper-case column names. Dates
        come back as Python dates, which is what the pages were written for.
    """
    return _run_query(sql, params)


@st.cache_data(ttl=3600)
def _run_query(sql: str, params: tuple) -> pd.DataFrame:
    """Run a query on its own cursor and cache the result.

    Args:
        sql: The full SQL statement to run.
        params: Bind parameters, as a tuple so the result can be cached.

    Returns:
        The result as a pandas DataFrame with upper-case column names.
    """
    cursor = connection().cursor()
    for macro in MACROS:
        cursor.execute(macro)
    table = cursor.execute(
        translate(sql), [bind_value(value) for value in params]
    ).fetch_arrow_table()
    frame = table.to_pandas(date_as_object=True)
    frame.columns = [name.upper() for name in frame.columns]
    return frame


def bind_value(value):
    """Return a value in a type the Snowflake connector will bind.

    A parameter that came out of a DataFrame is a NumPy scalar, not a Python
    one, and the connector rejects those outright: a customer number read from a
    frame and passed straight into a query fails with "Binding data in type
    (int32) is not supported". Every drill takes its key from a frame, so this
    is on the path of every click, and it is done here rather than at each call
    site because run_query is the one place every query in the app goes through.

    Args:
        value: A bind parameter.

    Returns:
        The value as a plain Python type where it was a NumPy one, and
        unchanged otherwise. Dates are left alone -- pandas Timestamps are
        datetimes already, and the connector takes them.
    """
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    if isinstance(value, (dt.date, dt.datetime)):
        return value
    native = getattr(value, "item", None)
    return native() if callable(native) else value


@st.cache_data(ttl=3600)
def filter_options() -> dict:
    """Return the values every filter can take, from one pass over the view.

    Sixteen `select distinct` queries is sixteen scans of a nine-million-row
    view, and a popover builds all sixteen of its widgets on every run whether
    or not anyone opens it, so that cost lands on the first paint of the first
    page. One `array_agg(distinct ...)` per column gathers the lot in a single
    scan instead.

    The lists cover the last OPTION_YEARS years rather than all twenty in the
    fact. A customer who last bought in 2009 is not a filter anyone is looking
    for, and including them makes the longest lists several times longer to
    scroll.

    A Snowflake ARRAY arrives through Snowpark as its JSON text rather than as a
    Python list, so every column is parsed on the way out. Skip that and the
    multiselects offer one option per character.

    Returns:
        A dict of column name to its sorted values, one entry per key of
        FILTER_COLUMNS.
    """
    columns = ", ".join(
        f"list_sort(list(distinct {column}::varchar) filter (where {column} is not null))"
        f" as {column}"
        for column in FILTER_COLUMNS
    )
    frame = run_query(
        f"select {columns} from {source()}"
        f" where is_reportable"
        f" and delivery_date >= dateadd(year, -{OPTION_YEARS},"
        f" (select max(delivery_date) from {source()}))"
    )
    return {
        column: [str(value) for value in frame[column.upper()][0]]
        for column in FILTER_COLUMNS
    }


@st.cache_data(ttl=3600)
def date_bounds() -> tuple[dt.date, dt.date]:
    """Return the first and last delivery date on reportable rows.

    Returns:
        A tuple of (earliest date, latest date).
    """
    frame = run_query(
        f"select min(delivery_date) as lo, max(delivery_date) as hi"
        f" from {source()} where is_reportable"
    )
    return frame["LO"][0], frame["HI"][0]


@st.cache_data(ttl=3600)
def budget_years() -> list[int]:
    """Return every year the budget covers.

    Returns:
        Budget years, ascending. Empty when no budget has been loaded, and when
        the build being read holds no budget view at all.
    """
    if BUDGET_MONTHLY_VIEW not in relations_present(app_database(), source_schema()):
        return []
    frame = run_query(
        f"select distinct delivery_year as y from {budget_source(False)}"
        f" where is_reportable order by 1"
    )
    return [int(y) for y in frame["Y"].tolist()]


def last_complete_week(latest: dt.date) -> dt.date:
    """Return the Saturday ending the last week that has run to its end.

    Weeks end Saturday throughout this project. A week is complete once its
    Saturday has arrived in the data, so the answer is the last Saturday on or
    before the newest delivery date. Trailing windows are anchored here rather
    than on the newest date, because a four-day week against a seven-day week a
    year ago reads as a collapse that has not happened.

    Args:
        latest: The newest delivery date in the fact.

    Returns:
        The Saturday that ends the last complete week.
    """
    return latest - dt.timedelta(days=(latest.weekday() + 2) % 7)


def last_complete_month(latest: dt.date) -> tuple[int, int]:
    """Return the year and month of the last month that has run to its end.

    Args:
        latest: The newest delivery date in the fact.

    Returns:
        A tuple of (year, month).
    """
    if latest.day == calendar.monthrange(latest.year, latest.month)[1]:
        return latest.year, latest.month
    if latest.month == 1:
        return latest.year - 1, 12
    return latest.year, latest.month - 1


def build_period(choice: str, custom: tuple | None = None) -> dict | None:
    """Turn a period choice into the two windows every page compares.

    A week preset ends on the last complete Saturday and runs back a whole
    number of weeks. Its comparison window is shifted by 364 days rather than by
    a calendar year, so a Saturday-ending week is compared against a
    Saturday-ending week and a leap year does not slide the alignment by a day.

    Year to date runs from 1 January to the end of the last complete month, and
    a custom range is whatever was picked; both shift by a calendar year, since
    both are stated in months and dates rather than in weeks.

    The bucket is the unit the trend charts draw. A window of more than about
    ten weeks is drawn by month, which is how the business reads a quarter or a
    year; anything shorter is drawn by week, where a month would be two bars.

    Args:
        choice: One of PERIODS.
        custom: The (start, end) pair from the date picker, for "Custom range".

    Returns:
        A dict with `label`, `short`, `start`, `end`, `prior_start`,
        `prior_end`, `prior_label`, `bucket` and `budget`, or None when a custom
        range is half-picked and there is nothing to draw yet. `short` is the
        window named in two or three words, for somewhere with no room for the
        full label, such as a tile.
    """
    _, latest = date_bounds()

    if choice in WEEK_PRESETS:
        weeks = WEEK_PRESETS[choice]
        end = last_complete_week(latest)
        start = end - dt.timedelta(days=weeks * 7 - 1)
        shift = dt.timedelta(days=PRIOR_YEAR_DAYS)
        return {
            "label": f"{weeks} weeks to {end:%d %b %Y}",
            "short": f"{weeks} weeks",
            "start": start,
            "end": end,
            "prior_start": start - shift,
            "prior_end": end - shift,
            "prior_label": f"same {weeks} weeks a year earlier",
            "bucket": "week" if weeks <= 13 else "month",
            "budget": "weekly",
        }

    if choice == "Year to date":
        year, month = last_complete_month(latest)
        start = dt.date(year, 1, 1)
        end = dt.date(year, month, calendar.monthrange(year, month)[1])
        return {
            "label": f"{year} through {MONTH_NAMES[month - 1]}",
            "short": "Year to date",
            "start": start,
            "end": end,
            "prior_start": dt.date(year - 1, 1, 1),
            "prior_end": dt.date(
                year - 1, month, calendar.monthrange(year - 1, month)[1]
            ),
            "prior_label": f"January to {MONTH_NAMES[month - 1]} {year - 1}",
            "bucket": "month",
            "budget": "monthly",
        }

    if not custom or len(custom) != 2:
        return None
    start, end = custom
    span = (end - start).days
    return {
        "label": f"{start:%d %b %Y} to {end:%d %b %Y}",
        "short": "Selected range",
        "start": start,
        "end": end,
        "prior_start": shift_year(start),
        "prior_end": shift_year(end),
        "prior_label": "the same dates a year earlier",
        "bucket": "week" if span <= 100 else "month",
        "budget": None,
    }


def shift_year(day: dt.date) -> dt.date:
    """Return the same calendar date one year earlier.

    Args:
        day: The date to shift.

    Returns:
        The date a year earlier, moved to 28 February when the original was a
        29 February that the earlier year does not have.
    """
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def build_where(selections: dict) -> tuple[str, tuple]:
    """Turn the filter bar's selections into a SQL predicate and its parameters.

    Only keys present in FILTER_COLUMNS become predicates, and only their values
    travel as bind parameters, so a selection can never reach SQL as text. An
    empty selection means "no restriction" rather than "match nothing", which is
    what a cleared multiselect should do.

    Args:
        selections: Column name to the list of chosen values.

    Returns:
        A tuple of (predicate SQL beginning with `is_reportable`, parameters).
    """
    clauses = ["is_reportable"]
    params: list = []
    for column, chosen in selections.items():
        if column not in FILTER_COLUMNS or not chosen:
            continue
        placeholders = ", ".join("?" for _ in chosen)
        clauses.append(f"{column} in ({placeholders})")
        params.extend(chosen)
    return " and ".join(clauses), tuple(params)


def render_filter_bar(title: str, *, action: str | None = None) -> dict | None:
    """Draw the page heading and the whole app's filter bar on a single row.

    Heading, period, measure, organization, branded and a filter popover share
    one row, and no page carries an `st.title`: the top navigation bar already names the page, and
    stacked control rows push the first real number into the bottom third of a
    1080p screen.

    Every widget key here is prefixed with the app rather than the page, so the
    reader's period, measure and filters follow them from page to page. That is
    only safe because every page offers the identical filter set -- a key reused
    against a shorter option list would drop a selection the reader could still
    see in the count.

    Organization and Branded sit on the row rather than in the popover because
    readers switch them as often as the measure. The row
    is a wrapping flex container with every control at its natural width, so a
    narrow window moves controls onto a second line instead of clipping their
    options. The popover is labeled with how many of its own filters are on, because a filter
    you cannot see is a filter you will forget. The count comes from session state,
    which necessarily holds the previous run's values, since the label is drawn
    before the widgets inside it.

    Whatever the drills in force have picked is ANDed on here too, so every page
    of the app honors them, and `scope_chips` names each one on a chip that
    drops it.
    It is kept out of the filter widgets deliberately -- see the Drill docstring.

    The filter widgets carry `bind="query-params"`, so their key doubles as a
    URL parameter name and a link copied out of the address bar reproduces
    whatever filters are set. Period and measure are not bound -- only the
    filters were asked for as a "saved view" link.

    A page with something of its own to offer -- Pulse's written headlines --
    puts it here as a button rather than as a block of page. It belongs on this
    row because it is a control and not a finding, and because a paragraph that
    sat permanently between the tiles and the first chart pushed both down the
    screen for the readers who never read it. It sits to the left of the filter
    popover so that the popover ends the row on every page, whether or not the
    page has such a button.

    Args:
        title: Page heading, rendered inline at the left of the row.
        action: Label for a button drawn just left of the filter popover, or
            None to draw none. Whether it was clicked comes back as `action`.

    Returns:
        A dict with `where`, `params`, `measure`, `period` and `action`, or None
        when a custom range is half-picked and the page has nothing to draw.
    """
    options = filter_options()
    earliest, latest = date_bounds()

    bar = st.container(horizontal=True, vertical_alignment="bottom", gap="small")
    with bar:
        st.markdown(f"### {title}", width="content")

        choice = st.selectbox(
            "Period", PERIODS, index=PERIODS.index(DEFAULT_PERIOD),
            key=f"{KEY}_period", width=PERIOD_WIDTH,
        )

        custom = None
        if choice == "Custom range":
            custom = st.date_input(
                "Delivery dates",
                value=(latest.replace(day=1), latest),
                min_value=earliest,
                max_value=latest,
                key=f"{KEY}_custom",
                width=DATES_WIDTH,
            )

        measure = st.segmented_control(
            "Measure", list(MEASURES), default=DEFAULT_MEASURE,
            key=f"{KEY}_measure", width="content",
        ) or DEFAULT_MEASURE

        chosen: dict = {}
        for column, label in HEADER_BUTTONS.items():
            chosen[column] = st.segmented_control(
                label, options[column], selection_mode="multi",
                key=f"{KEY}_{column}", bind="query-params", width="content",
            )

        asked = st.button(action, width="content") if action else False

        active = sum(
            len(st.session_state.get(f"{KEY}_{column}", []))
            for column in (*FILTER_BUTTONS, *FILTER_FIELDS)
        )
        with st.popover(
            f"Filters ({active})" if active else "Filters", width="content"
        ):
            for column, label in FILTER_BUTTONS.items():
                chosen[column] = st.segmented_control(
                    label, options[column], selection_mode="multi",
                    key=f"{KEY}_{column}", bind="query-params",
                )
            left, right = st.columns(2)
            for index, (column, label) in enumerate(FILTER_FIELDS.items()):
                with left if index % 2 == 0 else right:
                    chosen[column] = st.multiselect(
                        label, options[column], key=f"{KEY}_{column}",
                        bind="query-params",
                    )

    period = build_period(choice, custom)
    if period is None:
        st.info("Pick an end date to complete the range.")
        return None

    where, params = build_where(chosen)
    scope, scope_params, _ = carried_scope()
    if scope:
        where, params = f"({where}) and {scope}", (*params, *scope_params)
    return {
        "where": where, "params": params, "measure": measure, "period": period,
        "action": asked,
    }


def page_header(title: str, *, action: str | None = None) -> dict | None:
    """Draw a page's whole header: filter bar, drill badge and period caption.

    Every page opens with the same four things in the same order, so they are
    one call rather than four every page has to remember to make in the right
    sequence.

    A modal a click queued is opened here, before the page under it is drawn.
    That page is being redrawn with the drill in force, which means every figure
    on it is a fresh query, and the reader who clicked the bar is waiting on the
    modal rather than on the page behind it. Opening the modal first puts it on
    screen while those queries are still running; opening it last would make
    every drill cost the reader the whole page refresh before anything appeared.

    The page's own name is recorded here, so that a drill modal leading off to
    the Detail page can offer the reader a way back to the page they left
    without every page having to name itself twice. It is forgotten as soon as
    the reader is anywhere but Detail, so that walking back into Detail from the
    nav a day later is not offered a way back to a page they have long left.

    The drills in force are round-tripped through the URL too, the same as the
    filters -- see `_sync_scope_to_query_params`. A link copied mid-drill
    reopens on it.

    The filter bar, chips and caption sit in one keyed container that the app's
    stylesheet pins under the nav bar, so a reader scrolled halfway down still
    sees which measure, period and filters the charts are drawn under.

    Args:
        title: Page heading.
        action: Label for a button on the filter bar row, or None for none.

    Returns:
        What render_filter_bar returned, or None when the page has nothing to
        draw -- either no build to read at all, or a half-picked custom range.
    """
    if not source_picker():
        return None
    _seed_scope_from_query_params()
    st.session_state[PAGE] = title
    st.session_state[DRILL_SHOWN] = open_pending_drill()
    if PAGE_FILES.get(title) != DETAIL_PAGE:
        st.session_state.pop(ORIGIN, None)
    with st.container(key=HEADER_KEY):
        choices = render_filter_bar(title, action=action)
        if choices is None:
            return None
        scope_chips()
        _sync_scope_to_query_params()
        period_caption(choices["period"], choices["measure"])
    return choices


def period_caption(period: dict, measure: str) -> None:
    """Write the line naming both windows, under the filter bar.

    Every figure on every page is one window against the other, so which two
    windows those are is said once, in words, rather than implied by column
    headings.

    Args:
        period: The window pair from build_period.
        measure: The measure on screen.
    """
    caption(
        f"**{period['label']}** against {period['prior_label']}. "
        f"{period['start']:%d %b %Y} to {period['end']:%d %b %Y} against "
        f"{period['prior_start']:%d %b %Y} to {period['prior_end']:%d %b %Y}. "
        f"Measure: {measure.lower()}."
    )


def window_where(where: str, params: tuple, start: dt.date, end: dt.date) -> tuple:
    """Extend a filter predicate with one window's date bounds.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        start: First delivery date in the window.
        end: Last delivery date in the window.

    Returns:
        A tuple of (predicate SQL, parameters).
    """
    return f"{where} and delivery_date between ? and ?", (*params, start, end)


def both_windows_where(where: str) -> str:
    """Return the predicate covering a page's two windows in one scan.

    Args:
        where: The filter bar's predicate.

    Returns:
        Predicate SQL with four date placeholders, in current-then-prior order.
    """
    return (
        f"{where} and (delivery_date between ? and ?"
        f" or delivery_date between ? and ?)"
    )


def window_dates(period: dict) -> tuple:
    """Return a period's four dates in the order both_windows_where expects.

    Args:
        period: The window pair from build_period.

    Returns:
        A tuple of (start, end, prior_start, prior_end).
    """
    return (
        period["start"], period["end"], period["prior_start"], period["prior_end"]
    )


@st.cache_data(ttl=3600)
def window_totals(where: str, params: tuple, start: dt.date, end: dt.date) -> dict:
    """Return one window's headline figures.

    All three measures come back whichever one is selected, because average sell
    price needs dollars and cases together and the tiles show it beside the
    measure the reader picked.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        start: First delivery date in the window.
        end: Last delivery date in the window.

    Returns:
        A dict with `dollars`, `cases`, `customers` and `items`.
    """
    sql, args = window_where(where, params, start, end)
    frame = run_query(
        f"select coalesce(sum(invoiced_dollars), 0) as dollars,"
        f" coalesce(sum(case_quantity), 0) as cases,"
        f" count(distinct customer_number) as customers,"
        f" count(distinct item_number) as items"
        f" from {source()} where {sql}",
        args,
    )
    row = frame.iloc[0]
    return {
        "dollars": float(row["DOLLARS"]),
        "cases": float(row["CASES"]),
        "customers": int(row["CUSTOMERS"]),
        "items": int(row["ITEMS"]),
    }


def bucket_expression(bucket: str) -> str:
    """Return the SQL that groups rows into a trend chart's buckets.

    Args:
        bucket: "week" or "month".

    Returns:
        The expression to group and order by.

    Raises:
        KeyError: If the bucket is not one this app draws.
    """
    return {
        "week": "delivery_week_ending",
        "month": "date_trunc('month', delivery_date)::date",
    }[bucket]


@st.cache_data(ttl=3600)
def bucket_series(
    where: str, params: tuple, start: dt.date, end: dt.date, bucket: str
) -> pd.DataFrame:
    """Return a window's measures bucketed by week or month.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        start: First delivery date in the window.
        end: Last delivery date in the window.
        bucket: "week" or "month".

    Returns:
        A DataFrame with BUCKET, DOLLARS, CASES, CUSTOMERS and ITEMS,
        oldest bucket first.
    """
    sql, args = window_where(where, params, start, end)
    expression = bucket_expression(bucket)
    return run_query(
        f"select {expression} as bucket,"
        f" sum(invoiced_dollars) as dollars,"
        f" sum(case_quantity) as cases,"
        f" count(distinct customer_number) as customers,"
        f" count(distinct item_number) as items"
        f" from {source()} where {sql} group by 1 order by 1",
        args,
    )


@st.cache_data(ttl=3600)
def dimension_change(
    where: str, params: tuple, dimension: str, period: dict
) -> pd.DataFrame:
    """Return both windows' measures for every value of one dimension.

    This is the workhorse behind the movers, the mix charts and both bridges:
    one scan covering the two windows, grouped by whatever the page is asking
    about. Grouping and labeling columns are looked up in GROUPABLE rather than
    interpolated from the caller, so a page can only group by a column named
    there.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        dimension: A key of GROUPABLE.
        period: The window pair from build_period.

    Returns:
        A DataFrame with DIM, LABEL and CY_/PY_ columns for dollars and
        cases. Labels are made unique, because two rows sharing one label do not
        merely read badly -- a categorical axis collapses them into one bar and
        silently drops the smaller.

    Raises:
        KeyError: If the dimension is not one of GROUPABLE.
    """
    if dimension not in GROUPABLE:
        raise KeyError(f"{dimension} is not a groupable column")
    label = GROUPABLE[dimension]
    start, end, prior_start, prior_end = window_dates(period)
    windows = (
        "delivery_date between ? and ?",
        "delivery_date between ? and ?",
    )
    measures = ", ".join(
        f"sum(iff({windows[side]}, {column}, 0)) as {prefix}_{name}"
        for side, prefix in ((0, "cy"), (1, "py"))
        for column, name in (
            ("invoiced_dollars", "dollars"),
            ("case_quantity", "cases"),
        )
    )
    args: list = []
    for _ in range(2):
        args.extend([start, end])
    for _ in range(2):
        args.extend([prior_start, prior_end])
    args.extend(params)
    args.extend([start, end, prior_start, prior_end])
    frame = run_query(
        f"select {dimension} as dim, max({label}) as label, {measures}"
        f" from {source()} where {both_windows_where(where)}"
        f" group by 1",
        tuple(args),
    )
    return disambiguate(frame)


def disambiguate(frame: pd.DataFrame) -> pd.DataFrame:
    """Make a change frame's labels unique by suffixing the ones that repeat.

    Two items can carry the same description and two customers the same name.
    On a table that is confusing; on a chart it is wrong, because a categorical
    axis treats one label as one category and quietly stacks the second row on
    top of the first.

    Args:
        frame: A frame with DIM and LABEL columns.

    Returns:
        The frame with repeated labels suffixed by their key. Labels that are
        already unique are left exactly as they were, so the common case reads
        as the business writes it.
    """
    data = frame.copy()
    data["LABEL"] = data["LABEL"].fillna("(none)").astype(str)
    repeated = data["LABEL"].duplicated(keep=False)
    data.loc[repeated, "LABEL"] = (
        data.loc[repeated, "LABEL"] + " (" + data.loc[repeated, "DIM"].astype(str) + ")"
    )
    return data


@st.cache_data(ttl=3600)
def budget_total(where: str, params: tuple, period: dict) -> dict | None:
    """Return the budgeted dollars for the window on screen.

    Which budget view answers depends on how the window was stated. A week
    preset reads the weekly allocation, since its bounds are Saturdays; year to
    date reads the monthly budget, since its bounds are month ends and the
    weekly allocation splits the month that straddles them. A custom range gets
    no budget at all -- an arbitrary range cuts through both, and a budget that
    is right to within a few days is worse than no budget, because nobody can
    tell which days it missed.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        period: The window pair from build_period.

    Returns:
        A dict with `dollars`, or None when this window has no
        budget it can state exactly, or when the build being read holds no
        budget view at all.
    """
    kind = period["budget"]
    if kind is None:
        return None
    view = BUDGET_WEEKLY_VIEW if kind == "weekly" else BUDGET_MONTHLY_VIEW
    if view not in relations_present(app_database(), source_schema()):
        return None
    if period["start"].year not in budget_years():
        return None
    if kind == "weekly":
        relation = budget_source(True)
        clause = "delivery_week_ending between ? and ?"
        args = (*params, period["start"] + dt.timedelta(days=6), period["end"])
    else:
        relation = budget_source(False)
        clause = "delivery_year = ? and delivery_month <= ?"
        args = (*params, period["end"].year, period["end"].month)
    frame = run_query(
        f"select coalesce(sum(budget_dollars), 0) as dollars,"
        f" from {relation} where {where} and {clause}",
        args,
    )
    row = frame.iloc[0]
    return {"dollars": float(row["DOLLARS"])}


@st.cache_data(ttl=3600)
def budget_series(where: str, params: tuple, period: dict) -> pd.DataFrame:
    """Return the window's budget bucketed the way the trend chart draws it.

    Which view answers, and which windows get an answer at all, is decided
    exactly as budget_total decides it, so the line drawn here adds up to the
    figure on the tile. A custom range gets nothing, for the reason given there.

    One case needs saying. A 26 or 52 week window is drawn by month but budgeted
    by week, so each budget week is counted into the month its Saturday falls
    in. The window's total is unaffected -- every week is counted once -- but a
    week split across two months lands wholly in one of them, so a month
    boundary can be a few days out either way.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        period: The window pair from build_period.

    Returns:
        A DataFrame with BUCKET and DOLLARS, oldest bucket first, using
        the same bucket dates bucket_series returns. Empty when this window has
        no budget it can state exactly.
    """
    kind = period["budget"]
    if kind is None:
        return pd.DataFrame()
    view = BUDGET_WEEKLY_VIEW if kind == "weekly" else BUDGET_MONTHLY_VIEW
    if view not in relations_present(app_database(), source_schema()):
        return pd.DataFrame()
    if period["start"].year not in budget_years():
        return pd.DataFrame()
    if kind == "weekly":
        relation = budget_source(True)
        bucket = (
            "delivery_week_ending" if period["bucket"] == "week"
            else "date_trunc('month', delivery_week_ending)::date"
        )
        clause = "delivery_week_ending between ? and ?"
        args = (*params, period["start"] + dt.timedelta(days=6), period["end"])
    else:
        relation = budget_source(False)
        bucket = "date_from_parts(delivery_year, delivery_month, 1)"
        clause = "delivery_year = ? and delivery_month <= ?"
        args = (*params, period["end"].year, period["end"].month)
    return run_query(
        f"select {bucket} as bucket,"
        f" coalesce(sum(budget_dollars), 0) as dollars"
        f" from {relation} where {where} and {clause}"
        f" group by 1 order by 1",
        args,
    )


def measure_column(measure: str) -> str:
    """Return the view column a measure aggregates.

    Args:
        measure: A key of MEASURES.

    Returns:
        The column to sum.
    """
    return MEASURES[measure][0]


def measure_pair(frame: pd.DataFrame, measure: str) -> tuple[str, str]:
    """Return the current and prior column names for a measure on a change frame.

    Args:
        frame: A frame from dimension_change.
        measure: A key of MEASURES.

    Returns:
        A tuple of (current column, prior column).

    Raises:
        KeyError: If the frame does not carry that measure.
    """
    suffix = {"Dollars": "DOLLARS", "Cases": "CASES"}[measure]
    for name in (f"CY_{suffix}", f"PY_{suffix}"):
        if name not in frame.columns:
            raise KeyError(f"{name} is not on this frame")
    return f"CY_{suffix}", f"PY_{suffix}"


def money(value: float) -> str:
    """Format a number as whole dollars, with negatives in parentheses.

    Args:
        value: The dollar amount.

    Returns:
        A display string such as "$1,234" or "($1,234)", or "--" when missing.
    """
    if value is None or pd.isna(value):
        return "--"
    if value < 0:
        return f"(${abs(value):,.0f})"
    return f"${value:,.0f}"


def number(value: float) -> str:
    """Format a number with thousands separators and no decimals.

    Args:
        value: The quantity.

    Returns:
        A display string such as "1,234", or "--" when missing.
    """
    if value is None or pd.isna(value):
        return "--"
    return f"{value:,.0f}"


def price(value: float) -> str:
    """Format a number as a per-case price to the cent.

    Args:
        value: The price.

    Returns:
        A display string such as "$2.25", or "n/a" when missing.
    """
    if value is None or pd.isna(value):
        return "n/a"
    return f"${value:,.2f}"


def compact(value: float) -> str:
    """Return a number shortened to a K, M or B suffix.

    Bar labels sit inside the plot beside the bar they belong to, so they are
    written short -- three significant figures and a suffix rather than the
    eleven characters a full dollar figure takes. The tooltip still carries the
    exact number.

    Args:
        value: The number.

    Returns:
        The shortened number, such as "70.1M", or "--" when missing.
    """
    if value is None or pd.isna(value):
        return "--"
    for cutoff, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= cutoff:
            scaled = value / cutoff
            return (
                f"{scaled:,.0f}{suffix}" if abs(scaled) >= 100
                else f"{scaled:,.1f}{suffix}"
            )
    return f"{value:,.0f}"


def compact_measure(value: float, measure: str) -> str:
    """Format a value short enough to sit at the end of a bar.

    Args:
        value: The number to format.
        measure: A key of MEASURES.

    Returns:
        The shortened number, with a currency symbol for dollars and a minus
        sign on anything negative. Positives are left unsigned; use
        signed_compact for a label that has to declare its own direction.
    """
    if value is None or pd.isna(value):
        return "--"
    short = compact(abs(value))
    body = f"${short}" if MEASURES[measure][1] == "money" else short
    return f"-{body}" if value < 0 else body


def signed_compact(value: float, measure: str) -> str:
    """Format a change short, with its sign always in front.

    Args:
        value: The signed change.
        measure: A key of MEASURES.

    Returns:
        A display string such as "+$1.2M" or "-$1.2M", or "--" when missing.
    """
    if value is None or pd.isna(value):
        return "--"
    body = compact_measure(abs(value), measure)
    return f"+{body}" if value >= 0 else f"-{body}"


def format_measure(value: float, measure: str) -> str:
    """Format a value in the style its measure calls for.

    Args:
        value: The number to format.
        measure: A key of MEASURES.

    Returns:
        Dollars formatted as currency, cases as plain counts.
    """
    return money(value) if MEASURES[measure][1] == "money" else number(value)


def signed_measure(value: float, measure: str) -> str:
    """Format a change so its sign is the first thing read.

    Args:
        value: The signed change.
        measure: A key of MEASURES.

    Returns:
        A display string such as "+$1,234" or "-$1,234".
    """
    if value is None or pd.isna(value):
        return "--"
    body = format_measure(abs(value), measure)
    return f"+{body}" if value >= 0 else f"-{body}"


def percent(numerator: float, denominator: float) -> str:
    """Format a ratio as a percentage to one decimal place.

    Args:
        numerator: The change amount.
        denominator: The base the change is measured against.

    Returns:
        A display string such as "+12.4%", or "n/a" when the base is zero.
    """
    if not denominator or pd.isna(denominator) or pd.isna(numerator):
        return "n/a"
    share = numerator / denominator * 100
    return f"{share:+,.1f}%"


def share(numerator: float, denominator: float) -> str:
    """Format a part of a whole as a percentage, without a sign.

    Args:
        numerator: The part.
        denominator: The whole.

    Returns:
        A display string such as "47%", or "n/a" when the whole is zero.
    """
    if not denominator or pd.isna(denominator) or pd.isna(numerator):
        return "n/a"
    return f"{numerator / denominator * 100:,.0f}%"


def plain(text: str) -> str:
    """Escape a string so Streamlit's markdown reads it as words rather than math.

    Streamlit treats a pair of dollar signs on one line as LaTeX. A sentence
    carrying two money figures therefore renders as italic mathematics with the
    spaces between the numbers stripped out, which is how "$225,975,394 against
    $243,702,295" arrives on screen as one run-together formula. Anything built
    out of money() and shown through markdown, a caption or a help tooltip has
    to come through here first. Values written into charts, tables and metrics
    must not, since those are not markdown and would show the backslash.

    Args:
        text: The assembled display string.

    Returns:
        The same string with its dollar signs escaped.
    """
    return text.replace("$", r"\$")


def caption(text: str) -> None:
    """Write a caption, escaping money so it does not render as mathematics.

    Args:
        text: The caption, as markdown.
    """
    st.caption(plain(text))


def direction_of(current: float, prior: float, higher_is_better: bool = True) -> int:
    """Return the arrow direction for a change.

    Args:
        current: The current window's figure.
        prior: The comparison window's figure.
        higher_is_better: Whether an increase should read as good.

    Returns:
        1 for good, -1 for bad, 0 when there is nothing to compare against.
    """
    if not prior or current is None or prior is None:
        return 0
    rising = current >= prior
    return 1 if rising == higher_is_better else -1


def axis_format(measure: str) -> str:
    """Return the d3 number format for a measure's axis labels.

    Args:
        measure: A key of MEASURES.

    Returns:
        A d3-format string, with a currency symbol for money measures.
    """
    return "$.3~s" if MEASURES[measure][1] == "money" else ".3~s"


def value_format(measure: str) -> str:
    """Return the d3 number format for a measure inside a tooltip.

    Args:
        measure: A key of MEASURES.

    Returns:
        A d3-format string carrying the figure in full.
    """
    return "$,.0f" if MEASURES[measure][1] == "money" else ",.0f"


def draw_chart(chart: alt.Chart) -> None:
    """Render a chart at the container's width and its own declared height.

    **Always render through here rather than calling `st.altair_chart` directly.**
    Streamlit stamps `autosize: fit` onto a chart asked to stretch, and `fit`
    sizes both axes to the container, so the height the chart declares is
    honored on the first paint and thrown away when the frontend measures. A
    chart inside a fixed-height container then collapses to a few pixels.
    `fit-x` fits the width and leaves the height alone, which is what every
    chart in this app wants; Streamlit only fills in `autosize` when the spec
    has none, so declaring it here wins.

    Args:
        chart: A chart that has already declared its height in pixels.
    """
    st.altair_chart(
        chart.properties(autosize={"type": "fit-x", "contains": "padding"}),
        width="stretch",
    )


TILE_PIXELS = 132


def stat_tile(
    label: str,
    value: str,
    *,
    delta: str | None = None,
    direction: int = 0,
    note: str | None = None,
    height: int = TILE_PIXELS,
) -> None:
    """Draw one headline number as a bordered tile.

    The figure is a plain `st.metric`, so the label, the value, the colored
    delta pill and the `?` tooltip behave like every other metric in Streamlit.

    **Every tile in a row is given the same fixed height.** Sizing cards to
    their content leaves a row a few pixels out of true whenever one card's
    label wraps and its neighbors' do not, which reads as a rendering glitch.

    Args:
        label: Name of the measure.
        value: The figure, already formatted.
        delta: Change against the comparison window, already formatted, keeping
            its sign so the native pill can color it.
        direction: 1 if the delta is good, -1 if bad, 0 for neutral. Customer
            and item counts pass 0 because consolidating both was deliberate,
            so a smaller count is not a loss.
        note: Context for the help tooltip, such as the prior window's figure.
        height: Fixed height in pixels, the same for every tile in the row.
    """
    with st.container(border=True, height=height):
        st.metric(
            label,
            value,
            delta=delta,
            delta_color="off" if direction == 0 else "normal",
            help=plain(note) if note else None,
        )


def bucket_labels(buckets: list, bucket: str) -> list[str]:
    """Turn bucket dates into the short labels the charts print.

    Args:
        buckets: The bucket dates, oldest first.
        bucket: "week" or "month".

    Returns:
        Labels such as "Jul 26" for months and "12 Jul" for weeks.
    """
    pattern = "%b %y" if bucket == "month" else "%d %b"
    return [pd.Timestamp(value).strftime(pattern) for value in buckets]


LABEL_LIMIT = 260
MIN_ROW_PIXELS = 20


def category_axis() -> alt.Axis:
    """Return the category axis for a ranked bar, with every label kept.

    Vega drops a label that overlaps its neighbour and cuts a long one short
    with an ellipsis, and either way a bar is left with no name. Both are
    turned off here; bar_height gives each row room instead.

    Returns:
        An axis showing every label in full, with no title, domain or ticks.
    """
    return alt.Axis(
        labelLimit=0, labelOverlap=False, domain=False, ticks=False, title=None
    )


def bar_height(height: int, rows: int) -> int:
    """Return a bar chart height that leaves each row room for its label.

    Args:
        height: The height the page asked for, in pixels.
        rows: How many bars the chart draws.

    Returns:
        The larger of the requested height and MIN_ROW_PIXELS per bar.
    """
    return max(height, rows * MIN_ROW_PIXELS)


def tornado_chart(
    frame: pd.DataFrame,
    dimension: str,
    value: str,
    measure: str,
    *,
    height: int = 340,
    selectable: bool = False,
    hint: str | None = None,
) -> alt.LayerChart | alt.Chart:
    """Build diverging bars of gains and losses about a zero line.

    Gains run right in green, losses left in red, sorted so the biggest gain is
    at the top and the biggest loss at the bottom. The shape is the point: a
    reader sees in one glance whether the change is a broad drift or two or
    three names, which a ranked table of the same numbers never shows.

    Each bar's label sits on its outer end, so it moves to the left of a losing
    bar rather than crossing the zero line into the gaining ones. That is two
    text layers with a filter each rather than one layer with a conditional
    alignment, because a mark property driven by an expression is the part of
    this spec most likely to change shape between Vega-Lite versions.

    A selectable chart looks the same. It did not until Streamlit 1.55, which is
    where clicks on a layered chart started being reported (streamlit#8643);
    before that a clickable chart gave up the zero rule and both text layers for
    one bar mark and a gridded value axis.

    Args:
        frame: Data carrying the label column and a signed value column.
        dimension: Name of the label column.
        value: Name of the signed numeric column.
        measure: A key of MEASURES, for labeling and number format.
        height: Chart height in pixels.
        selectable: Whether clicking a bar should select its category. A
            selectable chart must be drawn with clickable_chart rather than
            draw_chart. It dims the bars the reader did not pick.
        hint: A line to add to the tooltip of every bar, or None for none.

    Returns:
        The chart, ready to pass to draw_chart or, when selectable, to
        clickable_chart.
    """
    labeled = frame.copy()
    labeled["BAR_LABEL"] = [compact_measure(v, measure) for v in labeled[value]]
    labeled["SIDE"] = ["up" if v >= 0 else "down" for v in labeled[value]]
    numbers = pd.to_numeric(labeled[value], errors="coerce")
    reach = float(numbers.abs().max()) if numbers.notna().any() else 1.0

    tooltip = [
        alt.Tooltip(f"{dimension}:N", title=None),
        alt.Tooltip(
            f"{value}:Q", title=f"{measure} change", format=value_format(measure)
        ),
    ]
    if hint:
        labeled[HINT_COLUMN] = hint
        tooltip.append(alt.Tooltip(f"{HINT_COLUMN}:N", title=None))

    span = reach * 1.3
    value_axis = None

    base = alt.Chart(labeled).encode(
        x=alt.X(
            f"{value}:Q", title=None, axis=value_axis,
            scale=alt.Scale(domain=[-span, span], nice=False),
        ),
        y=alt.Y(
            f"{dimension}:N", title=None,
            sort=alt.EncodingSortField(field=value, op="max", order="descending"),
            axis=category_axis(),
        ),
        tooltip=tooltip,
    )
    paint = alt.Color(
        "SIDE:N", legend=None,
        scale=alt.Scale(domain=["up", "down"], range=[GOOD_INK, BAD_INK]),
    )
    bars = base.mark_bar(
        cornerRadiusEnd=3, **({"cursor": "pointer"} if selectable else {})
    ).encode(color=paint)
    if selectable:
        picker = alt.selection_point(
            name=BAR_SELECTION, fields=[dimension], on="click"
        )
        bars = bars.add_params(picker).encode(
            opacity=alt.condition(picker, alt.value(1.0), alt.value(0.3)),
        )
    gains = base.transform_filter(alt.datum[value] >= 0).mark_text(
        align="left", dx=6, color=MUTED_INK
    ).encode(text="BAR_LABEL:N")
    losses = base.transform_filter(alt.datum[value] < 0).mark_text(
        align="right", dx=-6, color=MUTED_INK
    ).encode(text="BAR_LABEL:N")
    rule = alt.Chart(pd.DataFrame({"zero": [0]})).mark_rule(
        color=MUTED_INK, strokeWidth=1
    ).encode(x=alt.X("zero:Q", title=None, axis=None))
    return (rule + bars + gains + losses).properties(
        height=bar_height(height, len(labeled))
    )


def wrap_label(label: str, width: int) -> str:
    """Break a chart label into newline-separated lines of at most `width`.

    A word longer than the width is left on its own line rather than broken
    across two, since a hyphenated number reads as a different number.

    Args:
        label: The label to wrap.
        width: Longest line, in characters.

    Returns:
        The label with newlines between its lines.
    """
    return "\n".join(textwrap.wrap(label, width, break_long_words=False)) or label


def bridge_chart(
    steps: list, measure: str, *, height: int = 380, compact: bool = False
) -> alt.LayerChart:
    """Build a waterfall from an opening figure to a closing one.

    Each step is a floating bar spanning the running total before it to the
    running total after it, so the eye follows one staircase from where the
    business was to where it is. The two anchors -- the opening and closing
    figures -- are drawn from zero in the neutral series color, because a total
    is not itself good or bad.

    Color is not carrying anything position does not already say, so a reader
    who cannot separate the two hues still gets the chart.

    `compact` is for a bridge in a half-width column. Nothing about the
    arithmetic changes; the drawing gives up the room it no longer has. Bar
    values are written to three significant figures and a suffix, because eight
    figures like $243,702,295 sitting over bars a hundred pixels apart run into
    each other, and two overlapping numbers are worth less than one rounded one.
    The exact figure stays in the tooltip. Bars narrow for the same reason.

    Category labels are wrapped onto as many lines as they need and drawn
    upright rather than turned and clipped at a pixel limit. A label like
    "Items dropped (26)" is the name of the bar; ending it in an ellipsis makes
    the reader hover to find out what they are looking at. Wrapping costs a few
    pixels under the axis and nothing else, and the axis grows to fit.

    Args:
        steps: Tuples of (label, value, kind) where kind is "anchor" for a bar
            drawn from zero and "step" for one that floats on the running total.
        measure: A key of MEASURES, for labeling and number format.
        height: Chart height in pixels.
        compact: Draw for a narrow column rather than the full page width.

    Returns:
        The chart, ready to pass to draw_chart.

    Raises:
        ValueError: If a step declares a kind this chart cannot draw.
    """
    rows = []
    running = 0.0
    wrap = 13 if compact else 18
    for label, value, kind in steps:
        if kind == "anchor":
            rows.append(
                {
                    "category": label, "label": wrap_label(label, wrap),
                    "start": 0.0, "end": value,
                    "kind": "Total", "exact": format_measure(value, measure),
                    "text": (
                        compact_measure(value, measure) if compact
                        else format_measure(value, measure)
                    ),
                }
            )
            running = value
        elif kind == "step":
            rows.append(
                {
                    "category": label, "label": wrap_label(label, wrap),
                    "start": running, "end": running + value,
                    "kind": "Increase" if value >= 0 else "Decrease",
                    "exact": signed_measure(value, measure),
                    "text": (
                        signed_compact(value, measure) if compact
                        else signed_measure(value, measure)
                    ),
                }
            )
            running += value
        else:
            raise ValueError(f"{kind} is not a bridge step kind")

    data = pd.DataFrame(rows)
    order = data["label"].tolist()
    scale = alt.Scale(
        domain=["Increase", "Decrease", "Total"],
        range=[GOOD_INK, BAD_INK, SERIES_CURRENT],
    )
    base = alt.Chart(data).encode(
        x=alt.X(
            "label:N", sort=order, title=None,
            axis=alt.Axis(
                labelAngle=0,
                labelLimit=0,
                labelExpr="split(datum.label, '\\n')",
                labelFontSize=10 if compact else 11,
                labelLineHeight=12,
            ),
        ),
        tooltip=[
            alt.Tooltip("category:N", title=None),
            alt.Tooltip("exact:N", title=measure),
        ],
    )
    bars = base.mark_bar(size=22 if compact else 34).encode(
        y=alt.Y("start:Q", title=measure, axis=alt.Axis(format=axis_format(measure))),
        y2="end:Q",
        color=alt.Color("kind:N", scale=scale, title=None, legend=None),
    )
    captions = base.mark_text(
        dy=-8, fontSize=10 if compact else 11, color=MUTED_INK
    ).encode(y=alt.Y("end:Q"), text="text:N")
    return (bars + captions).properties(height=height)


def trend_chart(
    frame: pd.DataFrame,
    measure: str,
    current_label: str,
    prior_label: str,
    *,
    height: int = 320,
    budget_label: str | None = None,
) -> alt.LayerChart:
    """Build the two-line chart of a window against its comparison window.

    The prior year is drawn in a muted slate rather than a second bright color.
    It is the reference the current line is read against, not a series competing
    for attention, and two saturated lines make the reader work out which one
    they care about every time they glance at the chart.

    Budget, where there is one, is a third line: green and dashed, so it reads
    as the target the two solid lines are measured against rather than as a
    third thing that happened. A bucket with no budget behind it leaves a gap in
    that line rather than dropping to zero.

    Args:
        frame: Data with LABEL, CURRENT and PRIOR columns, oldest bucket first,
            and a BUDGET column when a budget line is wanted.
        measure: A key of MEASURES, for labeling and number format.
        current_label: Name of the current window, for the legend.
        prior_label: Name of the comparison window, for the legend.
        height: Chart height in pixels.
        budget_label: Name of the budget series for the legend, or None to draw
            no budget line. Ignored when the frame carries no BUDGET column.

    Returns:
        The chart, ready to pass to draw_chart.
    """
    order = frame["LABEL"].tolist()
    names = {"PRIOR": prior_label, "CURRENT": current_label}
    budgeted = bool(budget_label) and "BUDGET" in frame.columns
    if budgeted:
        names["BUDGET"] = budget_label
    long = frame.melt(
        id_vars="LABEL", value_vars=list(names),
        var_name="SERIES", value_name="VALUE",
    )
    long["SERIES"] = long["SERIES"].map(names)
    domain = [current_label, prior_label] + ([budget_label] if budgeted else [])
    scale = alt.Scale(
        domain=domain,
        range=[SERIES_CURRENT, SERIES_PRIOR] + ([SERIES_BUDGET] if budgeted else []),
    )
    base = alt.Chart(long).encode(
        x=alt.X("LABEL:N", sort=order, title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(
            "VALUE:Q", title=measure, axis=alt.Axis(format=axis_format(measure)),
            scale=alt.Scale(zero=False),
        ),
        color=alt.Color(
            "SERIES:N", scale=scale, title=None,
            legend=alt.Legend(orient="top", labelColor=MUTED_INK),
        ),
    )
    line = base.mark_line(strokeWidth=2.5, point=False)
    if budgeted:
        line = line.encode(
            strokeDash=alt.StrokeDash(
                "SERIES:N",
                scale=alt.Scale(domain=domain, range=[[1, 0], [1, 0], [6, 4]]),
                legend=None,
            )
        )
    hover = base.mark_circle(size=52, opacity=0).encode(
        tooltip=[
            alt.Tooltip("LABEL:N", title="Period"),
            alt.Tooltip("SERIES:N", title=None),
            alt.Tooltip("VALUE:Q", title=measure, format=value_format(measure)),
        ]
    )
    return (line + hover).properties(height=height)


def show_table(frame: pd.DataFrame, index: str) -> None:
    """Render a display-ready table with its first column as row labels.

    The height fits the rows exactly, up to a cap, because a dataframe left to
    itself picks a default height and scrolls inside it -- which puts a scroll
    region inside a scrolling page and leaves the reader with two scrollbars and
    no idea how much table is left.

    Row labels come from `set_index` rather than `hide_index`, which does not
    exist on the older Streamlit builds Snowflake falls back to when
    environment.yml does not pin a version.

    Args:
        frame: A DataFrame of display strings.
        index: Name of the column to use as the row label.
    """
    height = min(len(frame) * 35 + 38, 560)
    st.dataframe(frame.set_index(index), width="stretch", height=height)


def section(heading: str, note: str | None = None) -> None:
    """Write a section heading and its one-line explanation.

    Headings are written as the question the section answers rather than as the
    name of the chart underneath, because a reader scanning the page is looking
    for their question and not for a chart type.

    Args:
        heading: The question this section answers.
        note: How to read what follows, or None when it needs no explanation.
    """
    st.markdown(f"##### {heading}")
    if note:
        caption(note)


RAW_ROW_CAP = 100_000

RAW_DIMENSIONS = (
    "delivery_week_ending, customer_number, customer_name, superchain_customer,"
    " organization, sales_representative, company, item_number, item_description,"
    " product_class, product_category, product_group, brand, branded, pl_hierarchy,"
    " pl_sub_hierarchy, pack_size, dairy_deli, promoted_product_group_description"
)

RAW_AGGREGATES = (
    "sum(invoiced_dollars) as invoiced_dollars,"
    " sum(case_quantity) as case_quantity"
)


@st.cache_data(ttl=3600)
def raw_row_count(where: str, params: tuple) -> int:
    """Return how many rows the extract would hold at week grain.

    Args:
        where: The page's predicate, including its window.
        params: Bind parameters for that predicate.

    Returns:
        The number of week-by-dimension combinations that match.
    """
    frame = run_query(
        f"select count(*) as n from ("
        f"select {RAW_DIMENSIONS} from {source()} where {where} group by all)",
        params,
    )
    return int(frame["N"][0])


@st.cache_data(ttl=3600)
def raw_extract(where: str, params: tuple) -> pd.DataFrame:
    """Return the page's data rolled up to the week, newest first, capped.

    The grain is `delivery_week_ending` rather than the delivery date, so a
    customer buying the same item on Tuesday and Thursday is one line. That is
    the grain the weekly reports are read at, and the detail line underneath
    carries an invoice sequence number nobody asks for.

    Args:
        where: The page's predicate, including its window.
        params: Bind parameters for that predicate.

    Returns:
        Up to RAW_ROW_CAP rows, most recent week first.
    """
    return run_query(
        f"select {RAW_DIMENSIONS}, {RAW_AGGREGATES} from {source()} where {where}"
        f" group by all order by delivery_week_ending desc limit {RAW_ROW_CAP}",
        params,
    )


def readable_sql(where: str, params: tuple) -> str:
    """Rebuild the extract query with its parameters inlined, for display only.

    Args:
        where: The page's predicate, with `?` placeholders.
        params: The values those placeholders carry.

    Returns:
        A SQL string someone can paste into Snowsight to pull the whole extract.
    """
    filled = where
    for value in params:
        literal = str(value) if isinstance(value, (int, float)) else f"'{value}'"
        filled = filled.replace("?", literal, 1)
    return (
        f"select {RAW_DIMENSIONS},\n    {RAW_AGGREGATES}\n"
        f"from {source()}\nwhere {filled}\ngroup by all\n"
        f"order by delivery_week_ending desc;"
    )


def page_footer() -> None:
    """Draw the standing caveat every page carries, and open any queued note.

    A note is opened from here rather than from the header because the button
    that asks for one is on the page itself: it is pressed and answered within
    the same run, and the answer is written from what the page has just worked
    out.

    Only one dialog can be open at a time, so a note gives way to a drill the
    header has already opened. In practice they cannot both be queued -- one is
    a bar click and the other a button, and a click reruns before the button
    could be pressed -- but a rule that only holds in practice is the kind that
    stops holding.
    """
    st.divider()
    caption(
        "Invoiced Dollars, net of line discounts, on rows flagged `is_reportable` "
        "in `rpt_sales_filtered`. Trade spend is not netted off."
        " The rows behind every "
        "figure are on the **Detail** page."
    )
    if not st.session_state.pop(DRILL_SHOWN, False):
        open_pending_note()


SPREAD_MATERIAL_SHARE = 0.01
SPREAD_MIN_CUSTOMERS = 3

QUIET_LOOKBACK_WEEKS = 104
QUIET_MIN_WEEKS = 12
QUIET_MIN_GAPS = 3
QUIET_FLOOR_DAYS = 21


@st.cache_data(ttl=3600)
def quiet_accounts(where: str, params: tuple, anchor: dt.date) -> pd.DataFrame:
    """Return customers that have stopped buying, judged against their own rhythm.

    A fixed cutoff -- "no order in eight weeks" -- flags every customer who buys
    quarterly and misses every customer who used to buy weekly and has been
    silent for a month. So each customer is measured against the median gap
    between their own buying weeks over the last two years, and is called quiet
    only when the silence has run past QUIET_MIN_GAPS of those gaps. The
    QUIET_FLOOR_DAYS floor stops a weekly buyer being flagged for missing a
    single week, which is a delivery schedule rather than a lost account.

    Customers with fewer than QUIET_MIN_WEEKS buying weeks are left out
    entirely. There is no rhythm to measure against a handful of orders, and a
    list of one-off buyers who did not come back is not a list anyone can act
    on.

    The value at stake is the customer's own trailing-year sales, so the ranking
    puts the largest silences first rather than the longest.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        anchor: The last complete day the window ends on; silence is measured to
            here rather than to today, so a partial week does not read as a
            customer going quiet.

    Returns:
        A DataFrame with CUSTOMER_NUMBER, CUSTOMER_NAME, ACTIVE_WEEKS,
        LAST_WEEK, DAYS_QUIET, TYPICAL_GAP_DAYS and TRAILING_YEAR_DOLLARS,
        largest trailing-year sales first.
    """
    query = f"""
        with weeks as (
            select customer_number,
                   max(customer_name) as customer_name,
                   delivery_week_ending,
                   sum(invoiced_dollars) as dollars
            from {source()}
            where {where}
              and delivery_week_ending
                  between dateadd(week, -{QUIET_LOOKBACK_WEEKS - 1}, ?) and ?
            group by customer_number, delivery_week_ending
        ),
        gaps as (
            select customer_number,
                   delivery_week_ending,
                   datediff(
                       day,
                       lag(delivery_week_ending) over (
                           partition by customer_number order by delivery_week_ending
                       ),
                       delivery_week_ending
                   ) as gap_days
            from weeks
        ),
        profile as (
            select weeks.customer_number,
                   max(weeks.customer_name) as customer_name,
                   count(*) as active_weeks,
                   max(weeks.delivery_week_ending) as last_week,
                   median(gaps.gap_days) as typical_gap_days,
                   sum(
                       iff(
                           weeks.delivery_week_ending > dateadd(week, -52, ?),
                           weeks.dollars,
                           0
                       )
                   ) as trailing_year_dollars
            from weeks
            left join gaps
              on weeks.customer_number = gaps.customer_number
             and weeks.delivery_week_ending = gaps.delivery_week_ending
            group by weeks.customer_number
        )
        select customer_number,
               customer_name,
               active_weeks,
               last_week,
               datediff(day, last_week, ?) as days_quiet,
               typical_gap_days,
               trailing_year_dollars
        from profile
        where active_weeks >= {QUIET_MIN_WEEKS}
          and trailing_year_dollars > 0
          and datediff(day, last_week, ?)
              > greatest({QUIET_FLOOR_DAYS}, typical_gap_days * {QUIET_MIN_GAPS})
        order by trailing_year_dollars desc
    """
    return run_query(query, (*params, anchor, anchor, anchor, anchor, anchor))


@st.cache_data(ttl=3600)
def monthly_history(
    where: str, params: tuple, end: dt.date, months: int
) -> pd.DataFrame:
    """Return whole months of history back from a window's end.

    The month `end` falls in is included only when `end` is its last day, so a
    trend never finishes on a part month. Every trailing window this app builds
    already ends on a complete week or a complete month, but a week-anchored
    window rarely ends on a month end, and a half month drawn beside whole ones
    looks like a collapse.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        end: The last day the history may cover.
        months: How many whole months to return.

    Returns:
        A DataFrame with BUCKET, DOLLARS and CASES, oldest month first.
    """
    last_day = calendar.monthrange(end.year, end.month)[1]
    if end.day == last_day:
        final = end
    elif end.month == 1:
        final = dt.date(end.year - 1, 12, 31)
    else:
        previous = end.month - 1
        final = dt.date(end.year, previous, calendar.monthrange(end.year, previous)[1])
    first = final.replace(day=1)
    for _ in range(months - 1):
        first = (first - dt.timedelta(days=1)).replace(day=1)
    sql, args = window_where(where, params, first, final)
    return run_query(
        f"select date_trunc('month', delivery_date)::date as bucket,"
        f" sum(invoiced_dollars) as dollars,"
        f" sum(case_quantity) as cases"
        f" from {source()} where {sql} group by 1 order by 1",
        args,
    )


DRILL_NOUNS = {
    "product_class": "Product class",
    "product_category": "Product category",
    "product_group": "Product group",
    "customer_number": "Customer",
    "superchain_customer": "Superchain / customer",
    "sales_representative": "Sales representative",
    "item_number": "Item",
    "brand": "Brand",
}

FIRST_BREAKDOWN = {
    "customer_number": ("product_class", "What do they buy?"),
    "superchain_customer": ("product_class", "What do they buy?"),
    "sales_representative": ("product_class", "What do they sell?"),
    "item_number": ("superchain_customer", "Which chains buy it?"),
}

DEFAULT_FIRST = ("customer_number", "Who buys it?")

CARRIER = {
    "item_number": ("customer_number", "customer"),
}

DEFAULT_CARRIER = ("item_number", "item")

DRILL_ROWS = 12
BREAKDOWN_BARS = 8

CLEAR_HINT = "Click again to clear this filter"
HINT_COLUMN = "HINT"


class Drill(NamedTuple):
    """Everything a click needs to open a modal and lead on to the rows.

    A page builds one of these from its filter bar and hands it to every chart
    and table it draws. A chart showing less than the page does narrows it
    first, so the modal a bar opens counts the rows that bar drew.

    **Everything a drill picks travels as a predicate with a label, and nothing
    it picks is written into the filter widgets.** The inventory dashboard does
    the opposite, writing what it can into the target page's controls, because
    each of its pages carries its own filters. Here one filter bar serves every
    page, so a drill that wrote into it would silently re-filter the whole app
    from a single click, and writing widget state is only legal before the
    widget is drawn -- which a drill taken from the page that owns those widgets
    cannot promise. A predicate has neither problem: it is applied by every
    page, shown as a chip on every page, and dropped by clicking that chip.
    """

    where: str
    params: tuple
    measure: str
    period: dict
    scope: str
    scope_params: tuple
    scope_label: str

    def narrow(self, predicate: str, params: tuple = (), label: str = "") -> "Drill":
        """Return this drill scoped by a further predicate.

        Args:
            predicate: SQL to AND onto the drill's predicate.
            params: Bind parameters for it.
            label: Short human name for what the predicate keeps, shown in the
                modal and as a badge. Empty leaves it unnamed.

        Returns:
            A new Drill. The original is unchanged.
        """
        return self._replace(
            where=f"({self.where}) and {predicate}",
            params=(*self.params, *params),
            scope=f"({self.scope}) and {predicate}" if self.scope else predicate,
            scope_params=(*self.scope_params, *params),
            scope_label=" and ".join(
                part for part in (self.scope_label, label) if part
            ),
        )

    def pick(self, column: str, value, label: str | None = None) -> "Drill":
        """Return this drill scoped to one value of one column.

        Args:
            column: The view column the clicked bars are values of.
            value: The value clicked.
            label: What to badge it as, or None to badge it with the value.

        Returns:
            A new Drill. The original is unchanged.
        """
        return self.narrow(f"{column} = ?", (value,), label or str(value))

def drill_scope(choices: dict) -> Drill:
    """Return the drill context a page's charts are drawn with.

    The scope is seeded from whatever a previous drill left in session state, so
    a second drill lands on top of the first rather than replacing it, and what
    is stored when the reader asks to see the rows is the whole chain.

    Args:
        choices: What render_filter_bar returned.

    Returns:
        A Drill holding the page's predicate, measure and window, narrowed by
        nothing new yet.
    """
    scope, scope_params, scope_label = carried_scope()
    return Drill(
        choices["where"], choices["params"], choices["measure"], choices["period"],
        scope, scope_params, scope_label,
    )


def scope_levels() -> list:
    """Return the drills in force, outermost first.

    Returns:
        One (column, value, label) per click still in force.
    """
    return st.session_state.get(SCOPE_STACK, [])


def carried_scope() -> tuple[str, tuple, str]:
    """Return the predicate the drills in force add to every page.

    Each drill is held as the one pick it is rather than as the chain it was
    taken in, so that any one of them can be dropped without rebuilding the
    others. The chain is composed here instead, which is the only place that
    wants it whole.

    Returns:
        The predicate, its bind parameters, and the label to name it with. All
        three are empty when no drill is in force.
    """
    levels = scope_levels()
    if not levels:
        return ("", (), "")
    return (
        " and ".join(f"{column} = ?" for column, _, _ in levels),
        tuple(value for _, value, _ in levels),
        " and ".join(label for _, _, label in levels),
    )


def push_scope(column: str, value, label: str) -> None:
    """Put what a click picked in force across every page.

    Args:
        column: The view column the click landed on.
        value: The key value it picked, as it will be bound to SQL.
        label: What to name it, on the chip and in the modal.
    """
    st.session_state[SCOPE_STACK] = [*scope_levels(), (column, value, label)]


def drop_scope(position: int) -> None:
    """Drop one drill, leaving every other one in force.

    Args:
        position: Which drill to drop, as an index into scope_levels.
    """
    levels = list(scope_levels())
    if 0 <= position < len(levels):
        levels.pop(position)
    st.session_state[SCOPE_STACK] = levels


def scope_index(column: str, value) -> int | None:
    """Return where a pick sits among the drills in force, if it is one of them.

    A click on something already drilled into is the reader taking that drill
    back, wherever in the chain it sits. Only the innermost is usually reachable
    -- the page is cut to it, so the others have nothing left to click -- but a
    click that can undo any of them needs no rule about which.

    Args:
        column: The view column a click landed on.
        value: The key value it picked.

    Returns:
        The index of the matching drill, or None when this is a new pick.
    """
    for position, (held, picked, _) in enumerate(scope_levels()):
        if held == column and picked == value:
            return position
    return None


SCOPE_PARAM = f"{KEY}_scope"


def _seed_scope_from_query_params() -> None:
    """Seed the drill stack from the URL, once per session.

    Scope lives in plain session state rather than a widget, so nothing stops
    writing it after other widgets have drawn -- unlike the filter bar, which
    can only take a URL value before its widgets exist. Seeding is skipped once
    SCOPE_STACK already has an entry, so a reader's own clicks always win over
    whatever the link was opened with.
    """
    if SCOPE_STACK in st.session_state:
        return
    raw = st.query_params.get(SCOPE_PARAM)
    if not raw:
        return
    try:
        levels = json.loads(raw)
    except ValueError:
        return
    if not isinstance(levels, list):
        return
    parsed = [
        tuple(level) for level in levels
        if isinstance(level, list) and len(level) == 3
        and all(isinstance(part, str) for part in level)
    ]
    if parsed:
        st.session_state[SCOPE_STACK] = parsed


def _sync_scope_to_query_params() -> None:
    """Keep the URL's drill param equal to the drill stack.

    Called once per run, after the chips are drawn, so it catches every way the
    stack can change -- a bar click, a chip's cross, Clear all -- without a
    matching write at each of those call sites.
    """
    levels = scope_levels()
    if levels:
        st.query_params[SCOPE_PARAM] = json.dumps(list(levels), separators=(",", ":"))
    else:
        st.query_params.pop(SCOPE_PARAM, None)


def chart_key(name: str) -> str:
    """Return the widget key a selectable chart or table should be drawn under.

    Streamlit does not allow a selection to be cleared from Python, so the only
    way to clear one is to draw the widget under a different key: a new key
    means a new widget, and a new widget starts with nothing selected. The epoch
    this appends is bumped by clear_selections once a click has been acted on.

    That does two things. Coming back to a page does not re-fire the drill the
    reader already took, and clicking the same bar a second time still counts as
    a change -- without the reset it would not, because Streamlit only reruns
    when the selection differs from the one it already holds.

    Args:
        name: Stable name for the widget within its page.

    Returns:
        The widget key, carrying the current epoch.
    """
    return f"{name}_{st.session_state.get(SELECTION_EPOCH, 0)}"


def clear_selections() -> None:
    """Drop every selection from the next run onward.

    Call this as soon as a click has been acted on, while still in the run that
    handled it.
    """
    st.session_state[SELECTION_EPOCH] = st.session_state.get(SELECTION_EPOCH, 0) + 1


def apply_click(chart: Drill, column: str, picked, label: str) -> None:
    """Act on a click on a bar or a row, and start the run that shows the result.

    A click does two things at once. It puts what it picked in force across the
    whole app, so closing the modal leaves the reader looking at a dashboard cut
    to the thing they clicked rather than at the dashboard they clicked on; and
    it queues the modal that opens over it. A click on whatever the innermost
    drill already holds is read as the reader taking it back, so the same bar
    both applies a drill and clears it.

    The rerun is what makes the modal open over the filtered page rather than
    over the one the click was taken on: the page beneath was already drawn
    unfiltered by the time the click reached here, and nothing else would draw
    it again -- dismissing a dialog does not rerun the app, so a page left wrong
    here stays wrong until the reader touches something else. page_header opens
    the modal at the top of that rerun, so the reader sees it while the page
    behind it is still being redrawn rather than after.

    Selections are cleared on the way out because a bar that stays selected
    would reopen its own modal on the next rerun, and because Streamlit only
    reports a selection that differs from the one the widget already holds --
    without the reset, clicking the same bar again would not register at all,
    and there would be no way to clear a drill from the chart that took it.

    Args:
        chart: The drill the clicked widget was drawn under.
        column: The view column the clicked values belong to.
        picked: The key value the reader clicked, which is the view's own key
            rather than the label shown on the bar.
        label: What the bar or row was labeled, for the modal's heading and the
            chip.
    """
    held = scope_index(column, picked)
    if held is not None:
        drop_scope(held)
    else:
        scoped = chart.pick(column, picked, label)
        push_scope(column, picked, label)
        st.session_state[DRILL_PENDING] = {
            "chart": chart, "scoped": scoped, "column": column,
            "value": label, "picked": picked,
        }
    clear_selections()
    st.rerun()


def clickable_chart(chart: alt.Chart, key: str, dimension: str) -> str | None:
    """Draw a chart whose bars can be clicked, and return the category clicked.

    Args:
        chart: A chart built with `selectable=True`.
        key: Widget key, which should come from chart_key.
        dimension: Name of the column the selection carries.

    Returns:
        The category the reader clicked, or None when nothing is selected.
    """
    event = st.altair_chart(
        chart.properties(autosize={"type": "fit-x", "contains": "padding"}),
        width="stretch",
        key=key,
        on_select="rerun",
    )
    selected = (event.selection or {}).get(BAR_SELECTION)
    rows = selected if isinstance(selected, list) else []
    picked = [
        row[dimension] for row in rows if isinstance(row, dict) and dimension in row
    ]
    return str(picked[0]) if picked else None


def drillable_tornado(
    frame: pd.DataFrame,
    drill: Drill,
    *,
    name: str,
    column: str,
    height: int = 340,
    label: str = "LABEL",
    value: str = "CHANGE",
    key: str = "DIM",
) -> None:
    """Draw a tornado whose bars drill when clicked.

    Args:
        frame: Data carrying the label, signed value and key columns.
        drill: The scope this chart is drawn under.
        name: Stable name for this chart within its page.
        column: The view column the key values belong to.
        height: Chart height in pixels.
        label: Name of the display-label column.
        value: Name of the signed numeric column.
        key: Name of the column holding the value to scope on, which is the
            view's own key rather than the label -- two customers can share a
            name, and a drill has to land on the one that was clicked.
    """
    picked = clickable_chart(
        tornado_chart(
            frame, label, value, drill.measure, height=height, selectable=True,
            hint=clear_hint(frame, column, key),
        ),
        chart_key(name),
        label,
    )
    open_click(frame, drill, picked, column=column, label=label, key=key)


def drillable_ranked(
    frame: pd.DataFrame,
    drill: Drill,
    *,
    name: str,
    column: str,
    height: int = 230,
    label: str = "LABEL",
    value: str = "VALUE",
    key: str = "DIM",
    note: tuple[str, str] | None = None,
    prior: str | None = None,
) -> None:
    """Draw ranked bars whose bars drill when clicked.

    Args:
        frame: Data carrying the label, value and key columns, already cut to
            the rows worth drawing.
        drill: The scope this chart is drawn under.
        name: Stable name for this chart within its page.
        column: The view column the key values belong to.
        height: Chart height in pixels.
        label: Name of the display-label column.
        value: Name of the numeric column.
        key: Name of the column holding the value to scope on, which is the
            view's own key rather than the label.
        note: A (title, column) pair to add to the tooltip.
        prior: Name of a column holding the same figure a year earlier, marked
            on each bar as a tick.
    """
    picked = clickable_chart(
        ranked_bar_chart(
            frame, label, value, drill.measure, height=height, selectable=True,
            note=note, prior=prior, hint=clear_hint(frame, column, key),
        ),
        chart_key(name),
        label,
    )
    open_click(frame, drill, picked, column=column, label=label, key=key)


def clear_hint(frame: pd.DataFrame, column: str, key: str) -> str | None:
    """Return the tooltip line a chart drawn on its own drill should carry.

    A page cut to one customer draws its customers chart with one bar, and that
    bar is the drill: clicking it takes the drill back. Nothing on screen says
    so, and the chip at the top of the page is the only other way out, so the
    tooltip says it -- at the moment the reader is hovering the bar wondering
    what it is, and without spending a pixel until then.

    The line is offered only when every bar on the chart is a drill in force,
    which is the case a filtered page produces. A chart with one drilled bar
    among others would need the line on that bar alone, and Vega has no way to
    leave a tooltip field off a single row; the blank line it would show on all
    the others is worse than saying nothing.

    Args:
        frame: The data behind the chart.
        column: The view column its keys belong to.
        key: Name of the column holding those keys.

    Returns:
        The line to add to every bar's tooltip, or None when the chart is not
        wholly a drill in force.
    """
    if frame.empty:
        return None
    held = all(
        scope_index(column, bind_value(value)) is not None for value in frame[key]
    )
    return CLEAR_HINT if held else None


def open_click(
    frame: pd.DataFrame,
    drill: Drill,
    picked: str | None,
    *,
    column: str,
    label: str,
    key: str,
) -> None:
    """Act on a clicked bar, if a bar was clicked.

    Args:
        frame: The data behind the chart that was clicked.
        drill: The scope that chart was drawn under.
        picked: The category the reader clicked, or None when nothing is
            selected.
        column: The view column the key values belong to.
        label: Name of the display-label column.
        key: Name of the column holding the value to scope on.
    """
    if picked is None:
        return
    row = frame[frame[label] == picked]
    if row.empty:
        return
    apply_click(drill, column, bind_value(row.iloc[0][key]), picked)


def drillable_table(
    frame: pd.DataFrame,
    index: str,
    drill: Drill,
    *,
    name: str,
    column: str,
    keys: list,
    height: int | None = None,
    column_config: dict | None = None,
) -> None:
    """Draw a table whose rows drill when clicked.

    Half the drill surfaces in this app are tables rather than charts, because
    the charts that carry the most information -- the bridges, the price bands,
    the dumbbells -- are layered, and Streamlit will not report clicks on a
    layered chart (streamlit#8643). A table has no such limit, so the table
    beside such a chart is where its rows are reached.

    Args:
        frame: The display-ready table.
        index: Name of the column used as the row label.
        drill: The scope this table is drawn under.
        name: Stable name for this table within its page.
        column: The view column the keys belong to.
        keys: The value to scope on for each row, in the frame's own order.
        height: Fixed height in pixels. The default fits every row up to a cap,
            which is right for a table that is the answer; pass a shorter one
            for a table that is a reference beside something else, and let the
            reader scroll it.
        column_config: Streamlit column settings. Pass one for any date or
            number column, so the table sorts it by value rather than as text.
    """
    height = height or min(len(frame) * 35 + 38, 560)
    event = st.dataframe(
        frame.set_index(index),
        width="stretch",
        height=height,
        column_config=column_config,
        key=chart_key(name),
        on_select="rerun",
        selection_mode="single-row",
    )
    rows = (event.selection or {}).get("rows") or []
    position = rows[0] if rows else None
    if position is None or position >= len(keys):
        return
    picked = str(frame.iloc[position][index])
    apply_click(drill, column, bind_value(keys[position]), picked)


def scope_chips() -> None:
    """Draw one chip per drill in force, each dropping only itself.

    A predicate the reader can neither see nor clear is worse than one they
    never had, and these arrived from single clicks on charts they may have
    since scrolled past. The row is orange because it is the one part of the
    page's scope that the filter popover cannot show or undo.

    One chip per pick rather than one badge for all of them, because two drills
    are two decisions and a reader who wants to keep the customer and drop the
    item should not have to take both back and click the customer again. Each
    chip carries its own cross, which is the gesture people already know from
    every other filter chip they use, and needs neither the chart the drill came
    from nor a memory of which bar it was.

    The "Clear all" button only appears once there is more than one chip, since
    with a single drill it would be a second button doing what the chip beside
    it already does.
    """
    levels = scope_levels()
    if not levels:
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(plain(":orange-badge[Drilled into]"), width="content")
        for position, (column, value, label) in enumerate(levels):
            if st.button(
                plain(label),
                key=f"{KEY}_drop_{column}_{value}",
                icon=":material/close:",
                help="Drops this drill. Clicking its bar again does the same.",
            ):
                drop_scope(position)
                clear_selections()
                st.rerun()
        if len(levels) > 1 and st.button(
            "Clear all", key=f"{KEY}_clear_scope", type="tertiary"
        ):
            st.session_state.pop(SCOPE_STACK, None)
            clear_selections()
            st.rerun()


def open_rows() -> None:
    """Send the reader from a drill modal to the rows behind it.

    The scope the modal was showing is already in force -- the click that opened
    it put it there -- so this only has to remember which page the reader is
    leaving, which is what back_button offers them on the way home.
    """
    st.session_state[ORIGIN] = st.session_state.get(PAGE)
    clear_selections()
    st.switch_page(DETAIL_PAGE)


def back_button() -> None:
    """Draw the button back to the page a drill led away from, if there is one.

    Detail is reached both from the nav and from a modal on some other page, and
    a reader who arrived by the second route has no way back to the chart they
    were reading: the nav will return them to the page, but the browser's back
    button is the only thing that knows which page it was, and half of them will
    not think to use it.
    """
    origin = st.session_state.get(ORIGIN)
    if origin not in PAGE_FILES:
        return
    if st.button(
        f"Back to {origin}", icon=":material/arrow_back:", key=f"{KEY}_back"
    ):
        st.session_state.pop(ORIGIN, None)
        st.switch_page(PAGE_FILES[origin])


def queue_note(title: str, lines: list[str]) -> None:
    """Hold a page's written note until the page under it has finished drawing.

    Args:
        title: The modal's heading.
        lines: The findings, in the order they should be read.
    """
    st.session_state[NOTE_PENDING] = {"title": title, "lines": lines}


def note_body(lines: list[str]) -> None:
    """Fill a note modal with the findings a page computed.

    Args:
        lines: The findings, as markdown.
    """
    st.markdown(plain("\n".join(f"- {line}" for line in lines)))


def open_pending_note() -> None:
    """Open the note modal a button queued, if a button queued one.

    Taken rather than read, for the same reason a queued drill is: a later
    rerun must not bring the modal back after the reader has dismissed it.
    """
    pending = st.session_state.pop(NOTE_PENDING, None)
    if not pending:
        return
    st.dialog(pending["title"], width="large")(note_body)(lines=pending["lines"])


def open_pending_drill() -> bool:
    """Open the modal a click queued, if a click queued one.

    The drill is taken rather than read: a modal Streamlit is not told to close
    stays open across the reader's next few interactions with it, and a later
    full rerun -- a filter moving, the measure changing -- must not bring the
    modal back once they have dismissed it.

    The dialog is decorated here rather than at import because a dialog's title
    is fixed when it is decorated, and this one names whatever was clicked.

    Returns:
        True when a modal was opened.
    """
    pending = st.session_state.pop(DRILL_PENDING, None)
    if not pending:
        return False
    noun = DRILL_NOUNS.get(
        pending["column"], pending["column"].replace("_", " ").capitalize()
    )
    st.dialog(noun, width="large")(drill_body)(**pending)
    return True


def window_pair_series(drill: Drill) -> pd.DataFrame:
    """Return a drill's two windows bucketed and laid side by side.

    The two windows are matched in length by construction, so the buckets are
    aligned by position from the most recent backwards. Aligning on the date
    would need the same 364-day arithmetic the windows were built with, and
    would drop a bucket every time a month-bucketed window met a leap year.

    Args:
        drill: The scope to draw.

    Returns:
        A DataFrame with BUCKET, LABEL, CURRENT and PRIOR, oldest bucket first,
        empty when either window is empty. BUCKET is the current window's
        bucket date, which is what a budget line is joined on.
    """
    period = drill.period
    bucket = period["bucket"]
    current = bucket_series(
        drill.where, drill.params, period["start"], period["end"], bucket
    )
    prior = bucket_series(
        drill.where, drill.params, period["prior_start"], period["prior_end"], bucket
    )
    if current.empty or prior.empty:
        return pd.DataFrame()
    column = drill.measure.upper()
    depth = min(len(current), len(prior))
    recent = current.tail(depth).reset_index(drop=True)
    matched = prior.tail(depth).reset_index(drop=True)
    return pd.DataFrame(
        {
            "BUCKET": recent["BUCKET"],
            "LABEL": bucket_labels(recent["BUCKET"].tolist(), bucket),
            "CURRENT": recent[column].astype(float),
            "PRIOR": matched[column].astype(float),
        }
    )


def drill_body(
    chart: Drill, scoped: Drill, column: str, value: str, picked
) -> None:
    """Fill a drill modal with one clicked thing's position.

    Every modal shows the same four things -- the headline figures, how it has
    run, what it splits into, and what moved inside it -- so one body serves
    every chart and table in the app, and only the two dimensions change with
    what was clicked.

    The modal inherits the filters and the window of the thing that opened it
    rather than starting fresh, so its numbers always reconcile to the bar.

    The caption names the scope the chart already carried, not the one the click
    just added. The heading directly above it is that one, and a modal reading
    "25KG NFDM LOW HEAT GRADE A BAG, within 25KG NFDM LOW HEAT GRADE A BAG" is
    only telling you what you clicked, twice.

    Realized price is shown in the movers table only when an item was clicked.
    One item's price across its customers is a comparison; a price across
    different items is a number with no meaning.

    A modal is a dead end unless it offers a way further in, so it closes with a
    button through to the Detail page carrying the whole scope with it.

    It opens with the two ways back out, because the click that opened it has
    already filtered the page underneath and the reader deserves to be told so
    in the one place they are certainly looking. Each names the page it returns
    to and the state it returns in, so neither asks anyone to work out what
    dismissing the modal would do. The cross in the corner does what the first
    of them does.

    Args:
        chart: The drill the widget was drawn under, which is the denominator of
            the share tile.
        scoped: That drill narrowed to what the reader clicked.
        column: The view column the clicked values belong to.
        value: What the reader clicked.
        picked: The key value behind that label, which is what identifies this
            drill among the ones in force.
    """
    return_options(chart, scoped, column, picked)

    measure = scoped.measure
    period = scoped.period
    key = {"Dollars": "dollars", "Cases": "cases"}[measure]
    current = window_totals(
        scoped.where, scoped.params, period["start"], period["end"]
    )
    prior = window_totals(
        scoped.where, scoped.params, period["prior_start"], period["prior_end"]
    )

    st.markdown(plain(f"### {value}"))
    caption(
        f"{period['label']} against {period['prior_label']}"
        + (f", within {chart.scope_label}." if chart.scope_label else ".")
    )
    if not current[key] and not prior[key]:
        st.info("Nothing here matches the page's filters in either window.")
        return

    price_now = current["dollars"] / current["cases"] if current["cases"] else None
    price_then = prior["dollars"] / prior["cases"] if prior["cases"] else None

    tiles = st.columns(3)
    with tiles[0]:
        stat_tile(
            measure,
            format_measure(current[key], measure),
            delta=percent(current[key] - prior[key], prior[key]),
            direction=direction_of(current[key], prior[key]),
            note=f"Prior window: {format_measure(prior[key], measure)}",
        )
    with tiles[1]:
        label, figure, note = share_tile(chart, scoped, current[key], key)
        stat_tile(label, figure, note=note)
    with tiles[2]:
        stat_tile(
            "Average price per case",
            price(price_now),
            delta=percent((price_now or 0) - (price_then or 0), price_then),
            direction=direction_of(price_now, price_then),
            note=f"Prior window: {price(price_then)}",
        )

    first, heading = FIRST_BREAKDOWN.get(column, DEFAULT_FIRST)
    left, right = st.columns(2)
    with left:
        st.markdown("##### How has it run?")
        pair = window_pair_series(scoped)
        if pair.empty:
            caption("Nothing to draw over time here.")
        else:
            draw_chart(
                trend_chart(
                    pair, measure, "This window", "A year earlier", height=230
                )
            )
    with right:
        st.markdown(f"##### {heading}")
        draw_breakdown(scoped, first, measure)

    carrier, noun = CARRIER.get(column, DEFAULT_CARRIER)
    st.markdown("##### What moved inside it?")
    show_movers(scoped, carrier, noun, measure, prices=column == "item_number")

    if st.button("See the rows", type="primary"):
        open_rows()


def return_options(chart: Drill, scoped: Drill, column: str, picked) -> None:
    """Draw a drill modal's two ways back to the page it was opened from.

    Both buttons name the state they return in rather than the action they take,
    since "keep" and "drop" mean nothing until you already know a click filtered
    the page. Naming the page as well is what makes the pair read as a way home
    from a modal rather than as two more filters.

    Args:
        chart: The drill the clicked widget was drawn under, whose label names
            what is still in force when this drill is dropped.
        scoped: That drill narrowed to what the reader clicked.
        column: The view column the clicked values belong to.
        picked: The key value the reader clicked.
    """
    page = st.session_state.get(PAGE) or "the dashboard"
    kept, dropped = st.columns(2)
    if kept.button(
        plain(f"Return to {page}, filtered on {scoped.scope_label}"),
        icon=":material/filter_alt:",
        key=f"{KEY}_return_filtered",
        width="stretch",
    ):
        st.rerun()
    if dropped.button(
        plain(
            f"Return to {page}, filtered on {chart.scope_label}"
            if chart.scope_label
            else f"Return to {page}, unfiltered"
        ),
        icon=":material/filter_alt_off:",
        key=f"{KEY}_return_unfiltered",
        width="stretch",
    ):
        held = scope_index(column, picked)
        if held is not None:
            drop_scope(held)
        clear_selections()
        st.rerun()


def share_tile(chart: Drill, scoped: Drill, figure: float, key: str) -> tuple:
    """Return the label, value and note for a drill modal's share tile.

    The denominator is everything the chart's own filters cover over the same
    window -- not the company, and not the page's window if those ever differ.
    It is named for what it divides by, because a share whose denominator you
    have to guess is worse than no share at all.

    Args:
        chart: The drill the widget was drawn under, which is the denominator.
        scoped: That drill narrowed to what the reader clicked.
        figure: The clicked thing's measure over the modal's window.
        key: The window_totals key for the measure on screen.

    Returns:
        A tuple of (label, formatted value, help text).
    """
    period = scoped.period
    whole = window_totals(
        chart.where, chart.params, period["start"], period["end"]
    )[key]
    return (
        "Share of the total",
        share(figure, whole),
        f"{format_measure(figure, scoped.measure)} of "
        f"{format_measure(whole, scoped.measure)}, which is everything this "
        f"page's filters cover over the same window. Not a share of the "
        f"company: change a filter and this moves.",
    )


def draw_breakdown(drill: Drill, dimension: str, measure: str) -> None:
    """Draw one of a drill modal's breakdown bars.

    Args:
        drill: The scope the modal is showing.
        dimension: The column to break the scope down by.
        measure: The measure on screen.
    """
    frame = dimension_change(drill.where, drill.params, dimension, drill.period)
    if frame.empty:
        caption("Nothing to break down here.")
        return
    current, _ = measure_pair(frame, measure)
    ranked = frame.copy()
    ranked["VALUE"] = ranked[current].astype(float)
    ranked = ranked[ranked["VALUE"] > 0].nlargest(BREAKDOWN_BARS, "VALUE")
    if ranked.empty:
        caption("Nothing to break down here.")
        return
    draw_chart(ranked_bar_chart(ranked, "LABEL", "VALUE", measure, height=230))


def show_movers(
    drill: Drill, dimension: str, noun: str, measure: str, *, prices: bool
) -> None:
    """List what moved most inside a drill, in both directions.

    Args:
        drill: The scope the modal is showing.
        dimension: The column to rank.
        noun: What one row is, for the column heading.
        measure: The measure on screen.
        prices: Whether to carry realized price then and now, which is only
            comparable when every row is the same item.
    """
    frame = dimension_change(drill.where, drill.params, dimension, drill.period)
    if frame.empty:
        caption("Nothing inside this to rank.")
        return
    current, prior = measure_pair(frame, measure)
    data = frame.copy()
    data["CHANGE"] = data[current].astype(float) - data[prior].astype(float)
    data = data.reindex(data["CHANGE"].abs().sort_values(ascending=False).index)
    data = data[data["CHANGE"] != 0].head(DRILL_ROWS)
    if data.empty:
        caption("Nothing inside this moved in either direction.")
        return
    rows = []
    for _, row in data.sort_values("CHANGE", ascending=False).iterrows():
        entry = {
            noun.capitalize(): row["LABEL"],
            "Now": format_measure(float(row[current]), measure),
            "Before": format_measure(float(row[prior]), measure),
            "Change": signed_measure(float(row["CHANGE"]), measure),
        }
        if prices:
            now_cases, then_cases = float(row["CY_CASES"]), float(row["PY_CASES"])
            entry["Price now"] = price(
                float(row["CY_DOLLARS"]) / now_cases if now_cases else None
            )
            entry["Price before"] = price(
                float(row["PY_DOLLARS"]) / then_cases if then_cases else None
            )
        rows.append(entry)
    show_table(pd.DataFrame(rows), noun.capitalize())


def ranked_bar_chart(
    frame: pd.DataFrame,
    dimension: str,
    value: str,
    measure: str,
    *,
    height: int = 230,
    selectable: bool = False,
    note: tuple[str, str] | None = None,
    prior: str | None = None,
    hint: str | None = None,
) -> alt.LayerChart | alt.Chart:
    """Build a horizontal bar chart of one measure by one dimension.

    Every bar carries its own value at its end, so the chart draws no value axis
    and no gridlines: once the number is on the bar, an axis is a second and
    vaguer way of reading the same figure. The scale runs a fifth past the
    longest bar so the label has room before the chart's edge.

    A selectable chart keeps its labels. It did not until Streamlit 1.55, which
    is where clicks on a layered chart started being reported (streamlit#8643);
    before that a clickable chart traded its labels for a value axis.

    Args:
        frame: Data carrying the label column and the value column.
        dimension: Name of the label column.
        value: Name of the numeric column.
        measure: A key of MEASURES, for the tooltip's number format.
        height: Chart height in pixels.
        selectable: Whether clicking a bar should select its category. A
            selectable chart must be drawn with clickable_chart rather than
            draw_chart.
        note: A (title, column) pair to add to the tooltip, where the column
            holds display strings. This is where a ranked bar says something its
            length cannot, such as how the figure moved against last year.
        prior: Name of a column holding the same figure a year earlier, marked
            on each bar as a slate tick. See bullet_rows for why that tick is
            drawn as a bar rather than as the rule it looks like.
        hint: A line to add to the tooltip of every bar, or None for none. The
            tooltip is where this app says something about a bar without
            spending screen space on it.

    Returns:
        The chart, ready to pass to draw_chart or, when selectable, to
        clickable_chart.
    """
    labeled = frame.copy()
    labeled["BAR_LABEL"] = [compact_measure(v, measure) for v in labeled[value]]
    numbers = pd.to_numeric(labeled[value], errors="coerce")
    top = float(numbers.max()) if numbers.notna().any() else 1.0
    if prior is not None:
        reach = pd.to_numeric(labeled[prior], errors="coerce")
        top = max(top, float(reach.max()) if reach.notna().any() else 0.0)

    span = top * 1.25 if top > 0 else 1.0
    value_axis = None

    tooltip = [
        alt.Tooltip(f"{dimension}:N", title=None),
        alt.Tooltip(f"{value}:Q", title=measure, format=value_format(measure)),
    ]
    if note:
        tooltip.append(alt.Tooltip(f"{note[1]}:N", title=note[0]))
    if hint:
        labeled[HINT_COLUMN] = hint
        tooltip.append(alt.Tooltip(f"{HINT_COLUMN}:N", title=None))

    if prior is not None:
        labeled = bullet_rows(labeled, value, prior, span)
        tooltip.insert(
            2,
            alt.Tooltip(
                f"{prior}:Q", title="A year earlier", format=value_format(measure)
            ),
        )

    horizontal = (
        alt.X(
            "START:Q", title=None, axis=value_axis,
            scale=alt.Scale(domain=[0, span], nice=False),
        )
        if prior is not None
        else alt.X(
            f"{value}:Q", title=None, axis=value_axis,
            scale=alt.Scale(domain=[0, span], nice=False),
        )
    )
    base = alt.Chart(labeled).encode(
        x=horizontal,
        y=alt.Y(
            f"{dimension}:N", title=None,
            sort=alt.EncodingSortField(field=value, op="max", order="descending"),
            axis=category_axis(),
        ),
        tooltip=tooltip,
    )
    if prior is not None:
        base = base.encode(
            x2="END:Q",
            color=alt.Color(
                "SERIES:N", legend=None,
                scale=alt.Scale(
                    domain=[THIS_WINDOW, LAST_YEAR],
                    range=[SERIES_CURRENT, SERIES_PRIOR],
                ),
            ),
        )
    mark = {"cornerRadiusEnd": 3}
    if selectable:
        mark["cursor"] = "pointer"
    if prior is None:
        mark["color"] = SERIES_CURRENT
    bars = base.mark_bar(**mark)
    if selectable:
        picker = alt.selection_point(
            name=BAR_SELECTION, fields=[dimension], on="click"
        )
        bars = bars.add_params(picker).encode(
            opacity=alt.condition(picker, alt.value(1.0), alt.value(0.3))
        )
    text = base
    if prior is not None:
        # The bars' own colour and x2 encodings would paint the text blue and
        # centre it inside the bar, so the label layer is built from scratch.
        now = labeled[labeled["SERIES"] == THIS_WINDOW].copy()
        now["LABEL_AT"] = np.maximum(
            now["END"], pd.to_numeric(now[prior], errors="coerce").fillna(0) + span * TICK_SHARE
        )
        text = alt.Chart(now).encode(
            x=alt.X(
                "LABEL_AT:Q", title=None, axis=value_axis,
                scale=alt.Scale(domain=[0, span], nice=False),
            ),
            y=base.encoding.y,
            tooltip=tooltip,
        )
    labels = text.mark_text(align="left", dx=6, color=MUTED_INK).encode(
        text="BAR_LABEL:N"
    )
    rows = labeled[dimension].nunique()
    return (bars + labels).properties(height=bar_height(height, rows))


THIS_WINDOW = "This window"
LAST_YEAR = "A year earlier"
TICK_SHARE = 0.004


def bullet_rows(
    frame: pd.DataFrame, value: str, prior: str, span: float
) -> pd.DataFrame:
    """Return a bar frame with a last-year tick added as a second row per bar.

    The tick looks like a rule laid across the bar and is drawn as a bar: a
    floating one, a few pixels wide, centered on last year's figure. It has to
    be, because a rule would be a second layer, and Streamlit will not report a
    click on a layered chart (streamlit#8643) -- so an honest rule here would
    cost the whole grid its drill-through. One mark keeps both.

    Its width is a fixed share of the axis rather than a fixed number of pixels,
    because the data has no idea how wide the chart will be drawn. That is the
    one thing here that is approximate, and it is approximate in the drawing
    rather than in the figure: the tick's center is exactly last year.

    A bar with nothing behind it a year ago gets no tick. A tick sitting at zero
    reads as the bar's own left edge, which is worse than no tick at all.

    Args:
        frame: The ranked bars, one row each.
        value: Name of this window's numeric column.
        prior: Name of the same figure a year earlier.
        span: The value axis's upper bound, which sets the tick's width.

    Returns:
        The frame with SERIES, START and END columns, and one extra row per bar
        that had sales a year earlier.
    """
    now = frame.copy()
    now["SERIES"] = THIS_WINDOW
    now["START"] = 0.0
    now["END"] = pd.to_numeric(now[value], errors="coerce")

    ticks = frame[pd.to_numeric(frame[prior], errors="coerce") > 0].copy()
    if ticks.empty:
        return now
    half = span * TICK_SHARE
    ticks["SERIES"] = LAST_YEAR
    ticks["START"] = pd.to_numeric(ticks[prior], errors="coerce") - half
    ticks["END"] = pd.to_numeric(ticks[prior], errors="coerce") + half
    return pd.concat([now, ticks], ignore_index=True)
