"""Detail: the rows behind a number on any other page.

This is the drill-through target. Every modal in the app closes with a button
through to here, carrying whatever it was showing, and it is also a page in its
own right, reachable from the nav with nothing drilled into -- "show me the rows
where X" is a question people arrive with as often as they drill into it.

Every other page in this dashboard aggregates. This one deliberately stops
aggregating: the answer to "why is that bar so tall" is usually a readable
handful of specific lines, and a reader who cannot get to them stops trusting
the bar.

The grain is a week, not a delivery date. One row is one customer buying one
item in one week, which is the grain the weekly reports are read at; the invoice
line underneath it carries a sequence number nobody asks for. Weeks end Saturday,
so filtering to a month can return a week ending in the next month -- only that
month's rows are in the total, which still ties exactly.
"""

import pandas as pd
import streamlit as st

import sales_lib as lib

SHOWN_ROWS = 1000

COLUMNS = {
    "DELIVERY_WEEK_ENDING": "Week ending",
    "CUSTOMER_NAME": "Customer",
    "SUPERCHAIN_CUSTOMER": "Superchain",
    "ITEM_DESCRIPTION": "Item",
    "PRODUCT_CLASS": "Class",
    "BRAND": "Brand",
    "PACK_SIZE": "Pack",
    "SALES_REPRESENTATIVE": "Rep",
    "INVOICED_DOLLARS": "Dollars",
    "CASE_QUANTITY": "Cases",
}


def headline_tiles(where: str, params: tuple, period: dict, count: int) -> None:
    """Draw what the rows on this page add up to.

    The totals come from the same predicate the rows do, so a reader who has
    drilled in can check the figure they clicked against the figure here before
    reading a single line.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        period: The window pair from build_period.
        count: How many rows match, at week grain.
    """
    totals = lib.window_totals(where, params, period["start"], period["end"])
    price = totals["dollars"] / totals["cases"] if totals["cases"] else None
    tiles = st.columns(4)
    with tiles[0]:
        lib.stat_tile("Rows", lib.number(count))
    with tiles[1]:
        lib.stat_tile("Dollars", lib.money(totals["dollars"]))
    with tiles[2]:
        lib.stat_tile("Cases", lib.number(totals["cases"]))
    with tiles[3]:
        lib.stat_tile("Average sell price", lib.price(price))


def build_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Turn the extract into the table shown on screen.

    Only the columns a person reads are shown. The extract carries twenty
    dimensions because a spreadsheet is pivoted on whichever one the question
    needs, but twenty columns on screen is a horizontal scrollbar and nothing
    legible; the download is the whole thing.

    Args:
        frame: The result of lib.raw_extract.

    Returns:
        A DataFrame of display values, most recent week first.
    """
    shown = frame.head(SHOWN_ROWS).copy()
    shown["DELIVERY_WEEK_ENDING"] = [
        f"{pd.Timestamp(v):%d %b %Y}" for v in shown["DELIVERY_WEEK_ENDING"]
    ]
    for column in ("INVOICED_DOLLARS", "CASE_QUANTITY"):
        formatter = lib.money if column == "INVOICED_DOLLARS" else lib.number
        shown[column] = [formatter(float(v)) for v in shown[column]]
    return shown[list(COLUMNS)].rename(columns=COLUMNS)


def main() -> None:
    """Render the detail page."""
    choices = lib.page_header("Detail")
    if choices is None:
        return
    lib.back_button()
    where, params = choices["where"], choices["params"]
    period = choices["period"]

    scoped, args = lib.window_where(where, params, period["start"], period["end"])
    count = lib.raw_row_count(scoped, args)
    if not count:
        st.info("No rows match these filters in this window.")
        lib.page_footer()
        return

    headline_tiles(where, params, period, count)

    lib.section(
        "The rows",
        "One row per week per customer per item. "
        + (
            f"The {SHOWN_ROWS:,} largest weeks are shown; the download carries "
            f"up to {lib.RAW_ROW_CAP:,}."
            if count > SHOWN_ROWS
            else "All of them are shown."
        ),
    )
    rows = lib.raw_extract(scoped, args)
    st.dataframe(
        build_table(rows).set_index("Week ending"), width="stretch", height=520
    )

    if count > lib.RAW_ROW_CAP:
        st.info(
            f"The download returns the most recent {lib.RAW_ROW_CAP:,} of "
            f"{count:,} rows. For all of them, run the SQL below in Snowsight.",
            icon=":material/download:",
        )
    st.download_button(
        f"Download CSV, {len(rows):,} rows",
        rows.to_csv(index=False).encode("utf-8"),
        file_name=f"sales_{period['start']}_{period['end']}.csv",
        mime="text/csv",
        key=f"{lib.KEY}_download",
    )
    with st.expander("SQL for the full extract"):
        st.code(lib.readable_sql(scoped, args), language="sql")

    lib.page_footer()


main()
