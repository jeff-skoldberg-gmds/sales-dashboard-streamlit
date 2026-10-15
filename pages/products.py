"""Products: which items moved, how the mix shifted, and where one item's price varies.

The replica ranks items by size. This page asks what changed about them, and
adds the question nobody could ask before: the same item leaves the plant at
different prices for different customers, and this is how wide that spread is
and what it is worth.
"""

import altair as alt
import pandas as pd
import streamlit as st

import sales_lib as lib

MOVERS = 12
SPREAD_ITEMS = 15


def headline_tiles(
    frame: pd.DataFrame, current: dict, prior: dict, measure: str
) -> None:
    """Draw the four figures describing the range of items sold.

    Args:
        frame: dimension_change at item grain.
        current: window_totals for the window on screen.
        prior: window_totals for the comparison window.
        measure: The measure on screen.
    """
    current_column, prior_column = lib.measure_pair(frame, measure)
    data = frame.copy()
    data[current_column] = data[current_column].astype(float)
    data[prior_column] = data[prior_column].astype(float)
    added = data[(data[prior_column] == 0) & (data[current_column] != 0)]
    dropped = data[(data[current_column] == 0) & (data[prior_column] != 0)]
    current_price = (
        current["dollars"] / current["cases"] if current["cases"] else None
    )
    prior_price = prior["dollars"] / prior["cases"] if prior["cases"] else None

    tiles = st.columns(4)
    with tiles[0]:
        lib.stat_tile(
            "Items sold",
            lib.number(current["items"]),
            delta=lib.percent(current["items"] - prior["items"], prior["items"]),
            direction=0,
            note=f"Prior window: {lib.number(prior['items'])} distinct items.",
        )
    with tiles[1]:
        lib.stat_tile(
            "Average price per case",
            lib.price(current_price),
            delta=lib.percent(
                (current_price or 0) - (prior_price or 0), prior_price
            ),
            direction=lib.direction_of(current_price, prior_price),
            note=f"Prior window: {lib.price(prior_price)}. Dollars over cases "
                 f"across everything on screen.",
        )
    with tiles[2]:
        lib.stat_tile(
            "Newly sold",
            lib.number(len(added)),
            delta=lib.signed_measure(float(added[current_column].sum()), measure),
            direction=1 if len(added) else 0,
            note="Items invoiced in this window and not in the comparison "
                 "window.",
        )
    with tiles[3]:
        lib.stat_tile(
            "No longer sold",
            lib.number(len(dropped)),
            delta=lib.signed_measure(-float(dropped[prior_column].sum()), measure),
            direction=-1 if len(dropped) else 0,
            note="Items invoiced in the comparison window and not in this one.",
        )


def mix_chart(frame: pd.DataFrame, measure: str) -> None:
    """Draw each product class's share of the total, then and now.

    Shares rather than totals, because in a window where everything fell every
    bar falls and the picture says nothing about the blend. A rule joins the two
    points so the direction is read without checking a legend, and the point
    that moved is the filled one.

    Args:
        frame: dimension_change at product class grain.
        measure: The measure on screen.
    """
    current_column, prior_column = lib.measure_pair(frame, measure)
    data = frame.copy()
    current_total = float(data[current_column].astype(float).sum())
    prior_total = float(data[prior_column].astype(float).sum())
    if not current_total or not prior_total:
        lib.caption("Nothing matches these filters in one of the windows.")
        return
    data["NOW"] = data[current_column].astype(float) / current_total * 100
    data["THEN"] = data[prior_column].astype(float) / prior_total * 100
    data["SHIFT"] = data["NOW"] - data["THEN"]
    data["SHIFT_TEXT"] = [f"{v:+.1f} pts" for v in data["SHIFT"]]
    order = data.sort_values("NOW", ascending=False)["LABEL"].tolist()

    position = alt.Y("LABEL:N", sort=order, title=None)
    tooltip = [
        alt.Tooltip("LABEL:N", title="Product class"),
        alt.Tooltip("THEN:Q", title="Share before", format=".1f"),
        alt.Tooltip("NOW:Q", title="Share now", format=".1f"),
        alt.Tooltip("SHIFT_TEXT:N", title="Shift"),
    ]
    base = alt.Chart(data)
    rule = base.mark_rule(color=lib.MUTED_INK, strokeWidth=2).encode(
        y=position,
        x=alt.X(
            "THEN:Q",
            title=f"Share of {measure.lower()}",
            axis=alt.Axis(format=".0f", labelExpr="datum.value + '%'"),
        ),
        x2="NOW:Q",
        tooltip=tooltip,
    )
    before = base.mark_point(
        size=90, filled=True, color=lib.SERIES_PRIOR, opacity=1
    ).encode(y=position, x=alt.X("THEN:Q"), tooltip=tooltip)
    after = base.mark_point(
        size=110, filled=True, color=lib.SERIES_CURRENT, opacity=1
    ).encode(y=position, x=alt.X("NOW:Q"), tooltip=tooltip)
    labels = base.mark_text(align="left", dx=12, color=lib.MUTED_INK).encode(
        y=position,
        x=alt.X("NOW:Q"),
        text="SHIFT_TEXT:N",
    )
    lib.draw_chart(
        (rule + before + after + labels).properties(height=max(len(data) * 30, 180))
    )


@st.cache_data(ttl=3600)
def price_spread(where: str, params: tuple, start, end) -> pd.DataFrame:
    """Return how widely each item's realized price varies across customers.

    Only customer and item pairs taking a material share of the item's cases
    are counted. One pallet at an odd price is a rounding artifact, a
    sample or a freight adjustment, not a pricing pattern, and left in it sets
    the low end of nearly every band.

    The money column is the cases below the item's own volume-weighted average
    price, valued at how far below they were. It is a question, not a verdict:
    a lower price can be a different pack, a different freight arrangement or a
    contract signed years ago, none of which are in this data.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        start: First delivery date in the window.
        end: Last delivery date in the window.

    Returns:
        A DataFrame with ITEM_NUMBER, ITEM, CUSTOMERS, ITEM_PRICE, LOW_PRICE,
        HIGH_PRICE, CASES and BELOW_DOLLARS, largest below-average dollars
        first.
    """
    sql, args = lib.window_where(where, params, start, end)
    query = f"""
        with lines as (
            select item_number,
                   max(item_description) as item_description,
                   customer_number,
                   sum(invoiced_dollars) as dollars,
                   sum(case_quantity) as cases
            from {lib.source()}
            where {sql}
            group by item_number, customer_number
            having sum(case_quantity) > 0
        ),
        material as (
            select *, cases / sum(cases) over (partition by item_number) as share
            from lines
        ),
        kept as (
            select * from material where share >= {lib.SPREAD_MATERIAL_SHARE}
        ),
        totals as (
            select item_number,
                   max(item_description) as item_description,
                   count(*) as customers,
                   sum(dollars) / sum(cases) as item_price,
                   sum(cases) as cases
            from kept
            group by item_number
            having count(*) >= {lib.SPREAD_MIN_CUSTOMERS}
        )
        select totals.item_number,
               totals.item_description as item,
               totals.customers,
               totals.item_price,
               totals.cases,
               min(kept.dollars / kept.cases) as low_price,
               max(kept.dollars / kept.cases) as high_price,
               sum(
                   greatest(totals.item_price - kept.dollars / kept.cases, 0)
                   * kept.cases
               ) as below_dollars
        from kept
        join totals on kept.item_number = totals.item_number
        group by 1, 2, 3, 4, 5
        order by below_dollars desc
    """
    return lib.run_query(query, args)


def spread_chart(frame: pd.DataFrame) -> None:
    """Draw each item's price band as a rule with its average marked on it.

    A band and a point say in one row what a distribution chart says in twenty,
    and the rows are sorted by what the spread is worth rather than by how wide
    it is -- a two-dollar spread on an item nobody buys is not the conversation
    to have first.

    Args:
        frame: The result of price_spread, already ranked.
    """
    data = frame.head(SPREAD_ITEMS).copy()
    if data.empty:
        lib.caption("No item is bought by enough customers to have a spread.")
        return
    data["SPREAD_TEXT"] = [
        f"{lib.price(low)} to {lib.price(high)}"
        for low, high in zip(data["LOW_PRICE"], data["HIGH_PRICE"])
    ]
    data["BELOW_TEXT"] = [lib.money(v) for v in data["BELOW_DOLLARS"]]
    order = data["ITEM"].tolist()

    position = alt.Y("ITEM:N", sort=order, title=None, axis=alt.Axis(labelLimit=300))
    tooltip = [
        alt.Tooltip("ITEM:N", title="Item"),
        alt.Tooltip("SPREAD_TEXT:N", title="Price range"),
        alt.Tooltip("ITEM_PRICE:Q", title="Weighted average", format="$,.3f"),
        alt.Tooltip("CUSTOMERS:Q", title="Customers", format=",.0f"),
        alt.Tooltip("BELOW_TEXT:N", title="Below average"),
    ]
    base = alt.Chart(data)
    band = base.mark_rule(color=lib.SERIES_PRIOR, strokeWidth=6, opacity=0.6).encode(
        y=position,
        x=alt.X(
            "LOW_PRICE:Q",
            title="Realized price per case",
            scale=alt.Scale(zero=False, nice=True),
            axis=alt.Axis(format="$,.2f"),
        ),
        x2="HIGH_PRICE:Q",
        tooltip=tooltip,
    )
    average = base.mark_point(
        shape="diamond", size=110, filled=True, color=lib.SERIES_CURRENT, opacity=1
    ).encode(y=position, x=alt.X("ITEM_PRICE:Q"), tooltip=tooltip)
    lib.draw_chart(
        (band + average).properties(height=max(len(data) * 26, 200))
    )


def build_spread_table(frame: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Turn the price spread result into the displayed table.

    Args:
        frame: The result of price_spread, already ranked.

    Returns:
        A tuple of the display frame and the item number behind each of its
        rows, so a click drills on the item rather than on its description.
    """
    shown = pd.DataFrame(
        [
            {
                "Item": row["ITEM"],
                "Customers": lib.number(row["CUSTOMERS"]),
                "Low": lib.price(row["LOW_PRICE"]),
                "Average": lib.price(row["ITEM_PRICE"]),
                "High": lib.price(row["HIGH_PRICE"]),
                "Cases": lib.number(row["CASES"]),
                "Below average": lib.money(row["BELOW_DOLLARS"]),
            }
            for _, row in frame.head(SPREAD_ITEMS).iterrows()
        ]
    )
    return shown, frame.head(SPREAD_ITEMS)["ITEM_NUMBER"].tolist()


def main() -> None:
    """Render the products page."""
    choices = lib.page_header("Products")
    if choices is None:
        return
    where, params = choices["where"], choices["params"]
    period, measure = choices["period"], choices["measure"]
    drill = lib.drill_scope(choices)

    items = lib.dimension_change(where, params, "item_number", period)
    if items.empty:
        st.info("Nothing matches these filters in either window.")
        return
    current = lib.window_totals(where, params, period["start"], period["end"])
    prior = lib.window_totals(
        where, params, period["prior_start"], period["prior_end"]
    )
    headline_tiles(items, current, prior, measure)

    current_column, prior_column = lib.measure_pair(items, measure)
    moved = items.copy()
    moved["CHANGE"] = moved[current_column].astype(float) - moved[
        prior_column
    ].astype(float)
    moved = moved[moved["CHANGE"] != 0].sort_values("CHANGE", ascending=False)

    left, right = st.columns([3, 2])
    with left:
        lib.section(
            "Which items moved?",
            f"The {MOVERS} largest gains and the {MOVERS} largest losses in "
            f"{measure.lower()}.",
        )
        if moved.empty:
            lib.caption("No item moved in either direction.")
        else:
            edges = pd.concat([moved.head(MOVERS), moved.tail(MOVERS)])
            lib.drillable_tornado(
                edges.drop_duplicates("DIM"), drill, name="item_movers",
                column="item_number", height=460,
            )
    with right:
        lib.section(
            "Did the mix shift?",
            "Each product class's share of the total, then and now. A shift in "
            "share moves dollars even when nothing was repriced.",
        )
        mix_chart(
            lib.dimension_change(where, params, "product_class", period), measure
        )

    lib.section(
        "How much does one item's price vary between customers?",
        f"The band is what customers actually paid per case; the diamond is the "
        f"item's volume-weighted average. Customers taking less than "
        f"{lib.SPREAD_MATERIAL_SHARE:.0%} of an item's cases are left out, and an item "
        f"needs {lib.SPREAD_MIN_CUSTOMERS} customers to appear. Ranked by what the cases "
        f"below the average are worth.",
    )
    spread = price_spread(where, params, period["start"], period["end"])
    spread_chart(spread)
    if not spread.empty:
        lib.caption(
            "**A lower price is a question, not a finding.** Pack, freight terms "
            "and contract age all move a realized price and none of them are in "
            "this data."
        )
        table, keys = build_spread_table(spread)
        lib.drillable_table(
            table, "Item", drill, name="spread", column="item_number", keys=keys
        )

    lib.page_footer()


main()
