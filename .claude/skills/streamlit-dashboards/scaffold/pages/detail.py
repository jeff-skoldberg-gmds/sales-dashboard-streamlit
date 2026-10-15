"""The rows behind every other page, and where a drill ends."""

import streamlit as st

import dashboard_lib as lib

lib.apply_pending_measure()

COLUMNS = {
    "CUSTOMER_NAME": "Customer",
    "ITEM_DESCRIPTION": "Item",
    "DOLLARS": "Dollars",
    "POUNDS": "Pounds",
}

LIMIT = 2000


def rows(drill: lib.Drill):
    """Return the largest rows matching the filters and any drills.

    Capped rather than paged. The point of this page is the head of the
    distribution, and anyone who needs all of it should query the relation
    directly rather than pull it through a browser.

    Args:
        drill: The page scope, from page_header.

    Returns:
        A DataFrame of the top rows by the chosen measure.
    """
    return lib.run_query(
        f"select {', '.join(COLUMNS)} from {lib.SOURCE} where {drill.where}"
        f" order by {lib.measure_column(drill.measure)} desc nulls last limit {LIMIT}",
        drill.params,
    )


def main() -> None:
    """Render the Detail page.

    Args:
        None.

    Returns:
        None.
    """
    drill = lib.page_header("Detail", name=lib.DETAIL_NAME)
    lib.back_button()

    frame = rows(drill)
    st.caption(f"The {LIMIT:,} largest rows matching the filters, {len(frame):,} shown.")
    st.dataframe(frame.rename(columns=COLUMNS), width="stretch", hide_index=True)


main()
