"""Customers: who moved, who is biggest, who has stopped buying, how concentrated.

Three questions the replica's top-ten table cannot answer. Who moved is not who
is biggest -- the largest account is usually the same account as last year, and
the interesting names are the ones that changed. How concentrated the book is
decides how much a single conversation is worth. And who has stopped is the only
thing on this dashboard that is a list of things to do rather than a description
of what happened.

Every chart and table here drills: click a bar or a row and the account opens.
"""

import altair as alt
import pandas as pd
import streamlit as st

import sales_lib as lib

MOVERS = 12
TOP_ACCOUNTS = 10
TOP_CHAINS = 10
QUIET_ROWS = 25
DATE_FORMAT = "DD MMM YYYY"


def headline_tiles(
    frame: pd.DataFrame, current: dict, prior: dict, measure: str
) -> None:
    """Draw the four counts that describe the customer base.

    Args:
        frame: dimension_change at customer grain.
        current: window_totals for the window on screen.
        prior: window_totals for the comparison window.
        measure: The measure on screen.
    """
    current_column, prior_column = lib.measure_pair(frame, measure)
    data = frame.copy()
    data[current_column] = data[current_column].astype(float)
    data[prior_column] = data[prior_column].astype(float)
    won = data[(data[prior_column] == 0) & (data[current_column] != 0)]
    gone = data[(data[current_column] == 0) & (data[prior_column] != 0)]

    ranked = data.sort_values(current_column, ascending=False)
    total = float(ranked[current_column].sum())
    top_now = float(ranked[current_column].head(TOP_ACCOUNTS).sum())
    prior_ranked = data.sort_values(prior_column, ascending=False)
    prior_total = float(prior_ranked[prior_column].sum())
    top_then = float(prior_ranked[prior_column].head(TOP_ACCOUNTS).sum())

    tiles = st.columns(4)
    with tiles[0]:
        lib.stat_tile(
            "Customers buying",
            lib.number(current["customers"]),
            delta=lib.percent(
                current["customers"] - prior["customers"], prior["customers"]
            ),
            direction=0,
            note=f"Prior window: {lib.number(prior['customers'])}.",
        )
    with tiles[1]:
        lib.stat_tile(
            "Won",
            lib.number(len(won)),
            delta=lib.signed_measure(float(won[current_column].sum()), measure),
            direction=1 if len(won) else 0,
            note="Accounts that bought in this window and not in the comparison "
                 "window. The delta is what they bought.",
        )
    with tiles[2]:
        lib.stat_tile(
            "Did not come back",
            lib.number(len(gone)),
            delta=lib.signed_measure(-float(gone[prior_column].sum()), measure),
            direction=-1 if len(gone) else 0,
            note="Accounts that bought in the comparison window and not in this "
                 "one. The delta is what they used to buy.",
        )
    with tiles[3]:
        lib.stat_tile(
            f"Top {TOP_ACCOUNTS} share",
            lib.share(top_now, total),
            delta=f"{lib.share(top_then, prior_total)} before",
            direction=0,
            note=f"How much of {measure.lower()} the {TOP_ACCOUNTS} largest "
                 f"accounts carry. Rising concentration means the book depends "
                 f"on fewer conversations.",
        )


def concentration_curve(frame: pd.DataFrame, measure: str) -> None:
    """Draw how much of the book sits in how few accounts, this window and last.

    Accounts are ranked largest first and the curve reads cumulatively: at 10%
    of accounts the line says what share of sales those accounts carry. Two
    curves rather than one, because the shape on its own is hard to judge -- a
    steep curve is normal in this business, and the question is whether it got
    steeper.

    Ranking is done inside each window separately. The point is the shape of the
    book, not the fate of particular accounts, and holding last year's order
    would draw this year's curve out of sequence and bend it into nonsense.

    Args:
        frame: dimension_change at customer grain.
        measure: The measure on screen.
    """
    current_column, prior_column = lib.measure_pair(frame, measure)
    rows = []
    for column, label in (
        (current_column, "This window"),
        (prior_column, "Comparison window"),
    ):
        values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        values = values[values > 0].sort_values(ascending=False)
        if values.empty:
            continue
        total = float(values.sum())
        running = values.cumsum() / total * 100
        count = len(values)
        rows.append(
            pd.DataFrame(
                {
                    "ACCOUNTS": [(i + 1) / count * 100 for i in range(count)],
                    "SHARE": running.tolist(),
                    "SERIES": label,
                    "RANK": list(range(1, count + 1)),
                }
            )
        )
    if not rows:
        lib.caption("Nothing matches these filters.")
        return
    data = pd.concat(rows)
    scale = alt.Scale(
        domain=["This window", "Comparison window"],
        range=[lib.SERIES_CURRENT, lib.SERIES_PRIOR],
    )
    chart = (
        alt.Chart(data)
        .mark_line(strokeWidth=2.5)
        .encode(
            x=alt.X(
                "ACCOUNTS:Q",
                title="Share of accounts, largest first",
                axis=alt.Axis(format=".0f", labelExpr="datum.value + '%'"),
            ),
            y=alt.Y(
                "SHARE:Q",
                title=f"Share of {measure.lower()}",
                axis=alt.Axis(format=".0f", labelExpr="datum.value + '%'"),
            ),
            color=alt.Color(
                "SERIES:N", scale=scale, title=None,
                legend=alt.Legend(orient="top", labelColor=lib.MUTED_INK),
            ),
            tooltip=[
                alt.Tooltip("SERIES:N", title=None),
                alt.Tooltip("RANK:Q", title="Largest accounts", format=",.0f"),
                alt.Tooltip("SHARE:Q", title="Share of sales", format=".1f"),
            ],
        )
        .properties(height=300)
    )
    lib.draw_chart(chart)


def build_quiet_table(frame: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Turn the quiet-account result into the displayed table.

    Args:
        frame: The result of lib.quiet_accounts.

    Returns:
        A tuple of the display frame, largest trailing-year sales first, and the
        customer number behind each of its rows so a click can drill on the
        account rather than on its name.
    """
    rows = []
    for _, row in frame.head(QUIET_ROWS).iterrows():
        gap = float(row["TYPICAL_GAP_DAYS"] or 0)
        rows.append(
            {
                "Customer": row["CUSTOMER_NAME"],
                "Last bought": pd.Timestamp(row["LAST_WEEK"]),
                "Quiet for": weeks_phrase(int(row["DAYS_QUIET"]) // 7),
                "Usually buys every": (
                    weeks_phrase(round(gap / 7)) if gap else "n/a"
                ),
                "Last 12 months": round(float(row["TRAILING_YEAR_DOLLARS"])),
            }
        )
    return pd.DataFrame(rows), frame.head(QUIET_ROWS)["CUSTOMER_NUMBER"].tolist()


def weeks_phrase(count: int) -> str:
    """Return a week count with its noun agreeing.

    Args:
        count: A number of weeks.

    Returns:
        A phrase such as "1 week" or "18 weeks".
    """
    return "1 week" if count == 1 else f"{count:,} weeks"


def build_won_table(frame: pd.DataFrame, measure: str) -> tuple[pd.DataFrame, list]:
    """Turn the newly won accounts into the displayed table.

    Args:
        frame: dimension_change at customer grain.
        measure: The measure on screen.

    Returns:
        A tuple of the display frame, largest first, and the customer number
        behind each of its rows.
    """
    current_column, prior_column = lib.measure_pair(frame, measure)
    data = frame.copy()
    data[current_column] = data[current_column].astype(float)
    data[prior_column] = data[prior_column].astype(float)
    won = data[(data[prior_column] == 0) & (data[current_column] > 0)]
    won = won.sort_values(current_column, ascending=False).head(QUIET_ROWS)
    shown = pd.DataFrame(
        [
            {
                "Customer": row["LABEL"],
                measure: row[current_column],
                "Cases": float(row["CY_CASES"]),
            }
            for _, row in won.iterrows()
        ]
    )
    return shown, won["DIM"].tolist()


def number_format(measure: str) -> str:
    """Return the table number format for a measure.

    Args:
        measure: The measure on screen.

    Returns:
        A Streamlit NumberColumn format.
    """
    return "dollar" if measure == "Dollars" else "localized"


def top_chains(frame: pd.DataFrame, measure: str) -> pd.DataFrame:
    """Cut superchains down to the largest few in this window.

    Args:
        frame: dimension_change at superchain grain.
        measure: The measure on screen.

    Returns:
        The TOP_CHAINS rows by this window's measure, carrying VALUE, WAS for
        the prior-year tick and a NOTE of the change for the tooltip.
    """
    current, prior = lib.measure_pair(frame, measure)
    data = frame.copy()
    data["VALUE"] = data[current].astype(float)
    data["WAS"] = data[prior].astype(float)
    data = data[data["VALUE"] > 0].nlargest(TOP_CHAINS, "VALUE")
    data["NOTE"] = [
        f"{lib.signed_measure(value - was, measure)} "
        f"({lib.percent(value - was, was)})"
        for value, was in zip(data["VALUE"], data["WAS"])
    ]
    return data


def main() -> None:
    """Render the customers page."""
    choices = lib.page_header("Customers")
    if choices is None:
        return
    where, params = choices["where"], choices["params"]
    period, measure = choices["period"], choices["measure"]
    drill = lib.drill_scope(choices)

    customers = lib.dimension_change(where, params, "customer_number", period)
    if customers.empty:
        st.info("Nothing matches these filters in either window.")
        return
    current = lib.window_totals(where, params, period["start"], period["end"])
    prior = lib.window_totals(
        where, params, period["prior_start"], period["prior_end"]
    )
    headline_tiles(customers, current, prior, measure)

    chains = lib.dimension_change(where, params, "superchain_customer", period)
    current_column, prior_column = lib.measure_pair(chains, measure)
    moved = chains.copy()
    moved["CHANGE"] = moved[current_column].astype(float) - moved[
        prior_column
    ].astype(float)
    moved = moved[moved["CHANGE"] != 0].sort_values("CHANGE", ascending=False)

    left, right = st.columns([3, 2])
    with left:
        lib.section(
            "Which superchains moved?",
            f"The {MOVERS} largest gains and the {MOVERS} largest losses in "
            f"{measure.lower()}. Not the largest superchains, the ones that "
            f"changed.",
        )
        if moved.empty:
            lib.caption("No superchain moved in either direction.")
        else:
            edges = pd.concat([moved.head(MOVERS), moved.tail(MOVERS)])
            lib.drillable_tornado(
                edges.drop_duplicates("DIM"), drill, name="cust_movers",
                column="superchain_customer", height=460,
            )
    with right:
        lib.section(
            f"Top {TOP_CHAINS} superchains",
            f"The largest by {measure.lower()} in this window. The slate tick is "
            f"the same superchain over {period['prior_label']}.",
        )
        ranked = top_chains(chains, measure)
        if ranked.empty:
            lib.caption("No superchain bought in this window.")
        else:
            lib.drillable_ranked(
                ranked, drill, name="cust_top_chains",
                column="superchain_customer", height=460,
                note=("Change on last year", "NOTE"), prior="WAS",
            )

    lib.section(
        "Who has gone quiet?",
        f"Accounts with no order for more than three times their own usual gap "
        f"between orders, ranked by what they were worth over the last twelve "
        f"months. Measured to {period['end']:%d %b %Y}, the end of the window, "
        f"so a part week does not put anyone on this list.",
    )
    quiet = lib.quiet_accounts(where, params, period["end"])
    if quiet.empty:
        lib.caption("No account has gone quiet against its own buying rhythm.")
    else:
        lib.caption(
            f"**{len(quiet):,} accounts**, together worth "
            f"{lib.money(float(quiet['TRAILING_YEAR_DOLLARS'].sum()))} over the "
            f"last twelve months. The {min(QUIET_ROWS, len(quiet))} largest:"
        )
        table, keys = build_quiet_table(quiet)
        lib.drillable_table(
            table, "Customer", drill, name="quiet",
            column="customer_number", keys=keys,
            column_config={
                "Last bought": st.column_config.DateColumn(format=DATE_FORMAT),
                "Last 12 months": st.column_config.NumberColumn(format="dollar"),
            },
        )

    lib.section(
        "Who is new?",
        "Accounts that bought in this window and not in the comparison window.",
    )
    won, won_keys = build_won_table(customers, measure)
    if won.empty:
        lib.caption("No account bought for the first time in this window.")
    else:
        lib.drillable_table(
            won, "Customer", drill, name="won",
            column="customer_number", keys=won_keys,
            column_config={
                measure: st.column_config.NumberColumn(
                    format=number_format(measure)
                ),
                "Cases": st.column_config.NumberColumn(format="localized"),
            },
        )

    lib.section(
        "How concentrated is the book?",
        "Cumulative share of sales as accounts are added largest first.",
    )
    concentration_curve(customers, measure)

    lib.page_footer()


main()
