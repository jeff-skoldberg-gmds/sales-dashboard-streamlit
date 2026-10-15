"""The page a reader lands on. Every bar here drills."""

import streamlit as st

import dashboard_lib as lib

BREAKDOWNS = (
    ("By customer", "customer_name", "Who bought it."),
    ("By item", "item_description", "What they bought."),
)


def breakdown(drill: lib.Drill, dimension: str, limit: int = 10):
    """Return one dimension's ranked totals under the scope in force.

    Args:
        drill: The page scope, from page_header.
        dimension: The relation column to group by.
        limit: How many bars to draw.

    Returns:
        A DataFrame carrying the dimension column and a `VALUE` column.
    """
    return lib.run_query(
        f"select {dimension}, sum({lib.measure_column(drill.measure)}) as value"
        f" from {lib.SOURCE} where {drill.where} and {dimension} is not null"
        f" group by all order by value desc nulls last limit {limit}",
        drill.params,
    )


def main() -> None:
    """Render the Overview page.

    Args:
        None.

    Returns:
        None.
    """
    drill = lib.page_header("Overview", name="Overview")

    tiles = st.columns(2)
    with tiles[0]:
        lib.stat_tile(drill.measure, lib.format_measure(lib.total(drill), drill.measure))

    for heading, dimension, caption in BREAKDOWNS:
        st.markdown(f"### {heading}")
        st.caption(caption)
        rows = breakdown(drill, dimension)
        lib.drillable_chart(
            rows, dimension.upper(), drill,
            name=f"overview_{dimension}", height=max(160, 30 * len(rows)),
        )


main()
