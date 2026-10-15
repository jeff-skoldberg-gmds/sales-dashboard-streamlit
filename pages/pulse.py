"""Pulse: the whole business on one page, from the figures down to the arithmetic.

The page runs from the glance to the detail, and a reader can stop at any point
and have an answer. Six figures. Where the line has been running, against last
year and against plan, and then the same question over six years with the season
taken out. What moved, in red and green. What the number is made of, ranked, with
last year ticked on every bar. Which items were repriced and which moved on
volume. And at the foot, the two bridges that account for the whole change,
which are the arithmetic behind everything above them.

**The written headlines are behind the button on the filter bar.** They are the
page in sentences -- every number in them is drawn somewhere on it -- and they
sit in a modal because a reader who wants the charts should not have to scroll
past a paragraph to reach them, and a reader who wants the paragraph wants all
of it at once. Nothing about it is generated when the page opens: it is
arithmetic dropped into fixed sentences, and a sentence is left out when its
number is too small to be worth a reader's attention.

Both bridges tie exactly. The parts are computed and the last bar is whatever is
left, so each staircase lands on the closing figure -- there is no bar here that
was rounded to make the picture work.

Everything drills: clicking a bar or a row opens that one thing.

**The two bridges and the two item tables are about dollars whatever the measure
toggle says.** Price times volume is dollars; there is no price in a case and
no mix in a case count. Everything else on the page follows the toggle as usual.
"""

import altair as alt
import pandas as pd
import streamlit as st

import sales_lib as lib

MOVERS = 10
MATERIAL_SHARE = 0.05
TOP_ROWS = 10
BRIDGE_HEIGHT = 360
TREND_HEIGHT = 220
TABLE_HEIGHT = 250

HISTORY_MONTHS = 72
ROLLING_MONTHS = 12

DRIVERS = (
    ("superchain_customer", "Chains"),
    ("customer_number", "Customers"),
    ("sales_representative", "Sales representatives"),
    ("product_class", "Product classes"),
    ("pack_size", "Pack sizes"),
    ("brand", "Brands"),
    ("item_number", "Items"),
    ("product_group", "Product groups"),
    ("organization", "Organizations"),
    ("promoted_product_group_description", "PPGs"),
)
DRIVER_BARS = 10
DRIVER_COLUMNS = 3
DRIVER_HEIGHT = 240


def headline_tiles(
    current: dict, prior: dict, budget: dict | None, measure: str, period: dict
) -> None:
    """Draw the six figures the page opens with.

    The row is read left to right as one sentence: here is the number, here is
    what it was promised to be, here is what it was last year, and here are the
    three things that between them explain any gap. Price, customer count and
    item count move for different reasons from each other, and between them they
    separate a quarter that lost a customer from one that sold the same
    customers less, and both from one that simply sold cheaper.

    The first tile carries no delta of its own. Its two neighbors are that
    delta, measured against the two bases anybody asks about, and a tile that
    repeated one of them would be the same number twice in twelve inches.

    Average price per case is always dollars over cases and never follows the
    measure toggle, because it can only mean one thing.

    Args:
        current: window_totals for the window on screen.
        prior: window_totals for the comparison window.
        budget: budget_total for the window, or None.
        measure: The measure on screen.
        period: The window pair from build_period.
    """
    key = {"Dollars": "dollars", "Cases": "cases"}[measure]
    current_price = (
        current["dollars"] / current["cases"] if current["cases"] else None
    )
    prior_price = prior["dollars"] / prior["cases"] if prior["cases"] else None
    change = current[key] - prior[key]
    plan, plan_delta, plan_direction, plan_note = budget_position(
        current, budget, measure, period
    )

    tiles = st.columns(6)
    with tiles[0]:
        lib.stat_tile(
            f"{measure}, {period['short'].lower()}",
            lib.format_measure(current[key], measure),
            note=f"{period['start']:%d %b %Y} to {period['end']:%d %b %Y}, on "
                 f"the filters above.",
        )
    with tiles[1]:
        lib.stat_tile(
            "Vs budget",
            plan,
            delta=plan_delta,
            direction=plan_direction,
            note=plan_note,
        )
    with tiles[2]:
        lib.stat_tile(
            "Vs last year",
            lib.percent(change, prior[key]),
            delta=lib.signed_compact(change, measure),
            direction=lib.direction_of(current[key], prior[key]),
            note=f"{period['prior_label'].capitalize()}: "
                 f"{lib.format_measure(prior[key], measure)}.",
        )
    with tiles[3]:
        lib.stat_tile(
            "Average price per case",
            lib.price(current_price),
            delta=lib.percent(
                (current_price or 0) - (prior_price or 0), prior_price
            ),
            direction=lib.direction_of(current_price, prior_price),
            note=f"Prior window: {lib.price(prior_price)}. Always dollars over "
                 f"cases, whatever the measure toggle says.",
        )
    with tiles[4]:
        lib.stat_tile(
            "Customers buying",
            lib.number(current["customers"]),
            delta=lib.percent(
                current["customers"] - prior["customers"], prior["customers"]
            ),
            direction=0,
            note=f"Prior window: {lib.number(prior['customers'])} customers "
                 f"placed at least one order.",
        )
    with tiles[5]:
        lib.stat_tile(
            "Items sold",
            lib.number(current["items"]),
            delta=lib.percent(current["items"] - prior["items"], prior["items"]),
            direction=0,
            note=f"Prior window: {lib.number(prior['items'])} distinct items "
                 f"were invoiced.",
        )


def budget_position(
    current: dict, budget: dict | None, measure: str, period: dict
) -> tuple[str, str | None, int, str]:
    """Work out what the budget tile says, including when it has nothing to say.

    A budget tile that goes blank without explaining itself gets read as a
    broken query, and this one goes blank in three different situations: the
    reader picked cases, which the workbook does not hold; they picked a custom
    range, which no budget can be cut to honestly; or the window sits in a year
    finance has not budgeted. So the tile always draws, and the tooltip says
    which of those it is.

    Args:
        current: window_totals for the window on screen.
        budget: budget_total for the window, or None.
        measure: The measure on screen.
        period: The window pair from build_period.

    Returns:
        A tuple of (value, delta, direction, tooltip) for stat_tile.
    """
    key = {"Dollars": "dollars"}.get(measure)
    if key is None:
        return (
            "n/a", None, 0,
            "The budget holds dollars only, so there is "
            "nothing to hold cases against.",
        )
    if budget is None or not budget[key]:
        return (
            "n/a", None, 0,
            "There is no budget for this window. Budget is stated for week "
            "windows and year to date, and only for the years the finance "
            "workbook covers. A custom range gets none at all, because an "
            "arbitrary range cuts through both the weekly and the monthly "
            "budget and nobody could tell which days it missed.",
        )
    plan = budget[key]
    gap = current[key] - plan
    source = "weekly allocation" if period["budget"] == "weekly" else "monthly budget"
    return (
        lib.percent(gap, plan),
        lib.signed_compact(gap, measure),
        lib.direction_of(current[key], plan),
        f"Budget for this window is {lib.format_measure(plan, measure)}, from "
        f"the {source}, on the filters above.",
    )


def price_and_volume(current: dict, prior: dict) -> tuple[float, float]:
    """Split the change in dollars into the part that is price and the part that is volume.

    With one average price per window this is exact rather than an
    approximation: volume is the change in cases valued at last year's price,
    price is this year's cases revalued by the change in price, and the two add
    to the change in dollars with nothing left over. The item bridge further
    down the page splits the volume half again, into how much was sold and what
    was sold.

    Args:
        current: window_totals for the window on screen.
        prior: window_totals for the comparison window.

    Returns:
        A tuple of (volume effect, price effect) in dollars, both zero when
        either window sold no cases.
    """
    if not prior["cases"] or not current["cases"]:
        return 0.0, 0.0
    prior_price = prior["dollars"] / prior["cases"]
    current_price = current["dollars"] / current["cases"]
    volume = (current["cases"] - prior["cases"]) * prior_price
    price = current["cases"] * (current_price - prior_price)
    return volume, price


def compose_read(
    current: dict,
    prior: dict,
    budget: dict | None,
    classes: pd.DataFrame,
    customers: pd.DataFrame,
    quiet: pd.DataFrame,
    period: dict,
) -> list[str]:
    """Write the page's opening paragraph as a list of findings.

    Each sentence restates a number that is already drawn somewhere on the page,
    which is the whole discipline here: the paragraph is a reading aid, not a
    second source of truth that can drift from the charts under it. A finding is
    dropped rather than softened when its number is not worth saying -- a class
    that moved a fifth of a percent, a comparison against a base of zero -- so a
    quiet quarter produces a short paragraph rather than a padded one.

    The paragraph is always about dollars, whatever the measure toggle says.
    Cases are on the tiles, but "how did we do" is a money question,
    and a paragraph that changed its subject with a toggle would be read as
    though it had not.

    Args:
        current: window_totals for the window on screen.
        prior: window_totals for the comparison window.
        budget: budget_total for the window, or None.
        classes: dimension_change by product class.
        customers: dimension_change by customer.
        quiet: quiet_accounts for the window's end.
        period: The window pair from build_period.

    Returns:
        Markdown lines, in the order they should be read. Empty when the window
        holds no sales at all.
    """
    if not current["dollars"] and not prior["dollars"]:
        return []

    change = current["dollars"] - prior["dollars"]
    lines = [
        f"Dollars are **{lib.percent(change, prior['dollars'])}** against "
        f"{period['prior_label']}: {lib.money(current['dollars'])} now, "
        f"{lib.money(prior['dollars'])} then, a "
        f"{'gain' if change >= 0 else 'shortfall'} of {lib.money(abs(change))}."
    ]

    volume, price = price_and_volume(current, prior)
    if volume or price:
        prior_price = prior["dollars"] / prior["cases"]
        current_price = current["dollars"] / current["cases"]
        carrier = "price" if abs(price) > abs(volume) else "volume"
        lines.append(
            f"**Mostly {carrier}**: {lib.signed_measure(volume, 'Dollars')} "
            f"from volume and {lib.signed_measure(price, 'Dollars')} from "
            f"price. Cases are "
            f"{lib.percent(current['cases'] - prior['cases'], prior['cases'])} "
            f"and the realized price per case is "
            f"{lib.percent(current_price - prior_price, prior_price)}, at "
            f"{lib.price(current_price)}."
        )

    moved = movers(classes, "Dollars")
    if not moved.empty:
        floor = abs(change) * MATERIAL_SHARE
        best = float(moved.iloc[0]["CHANGE"])
        worst = float(moved.iloc[-1]["CHANGE"])
        parts = []
        if best > 0 and best >= floor:
            parts.append(
                f"**{moved.iloc[0]['LABEL']}** is up the most, "
                f"{lib.signed_measure(best, 'Dollars')}"
            )
        if worst < 0 and abs(worst) >= floor:
            parts.append(
                f"**{moved.iloc[-1]['LABEL']}** is down the most, "
                f"{lib.signed_measure(worst, 'Dollars')}"
            )
        if parts:
            lines.append(". ".join(parts) + ".")

    concentration = customer_concentration(customers, change)
    if concentration:
        lines.append(concentration)

    if budget is not None and budget["dollars"]:
        gap = current["dollars"] - budget["dollars"]
        lines.append(
            f"Against plan the window is "
            f"**{lib.percent(gap, budget['dollars'])}**: "
            f"{lib.money(current['dollars'])} against a budget of "
            f"{lib.money(budget['dollars'])}."
        )

    if not quiet.empty:
        at_risk = float(quiet["TRAILING_YEAR_DOLLARS"].sum())
        lines.append(
            f"**{len(quiet)} accounts have gone quiet**, together worth "
            f"{lib.money(at_risk)} of the last twelve months' sales. They are "
            f"listed on the Customers page."
        )
    return lines


def movers(frame: pd.DataFrame, measure: str) -> pd.DataFrame:
    """Return a change frame with its signed change, largest gain first.

    Args:
        frame: A frame from dimension_change.
        measure: A key of lib.MEASURES.

    Returns:
        The frame with a CHANGE column, sorted descending. Rows that did not
        move at all are dropped, since a bar of zero length is a row of wasted
        height.
    """
    current, prior = lib.measure_pair(frame, measure)
    moved = frame.copy()
    moved["CHANGE"] = moved[current].astype(float) - moved[prior].astype(float)
    moved = moved[moved["CHANGE"] != 0]
    return moved.sort_values("CHANGE", ascending=False)


def customer_concentration(customers: pd.DataFrame, change: float) -> str | None:
    """Say how much of the overall change sits in a handful of accounts.

    A total that moved because three accounts moved is a different business
    problem from the same total moving because six hundred accounts each drifted
    a little, and the two are indistinguishable on any chart of totals. So the
    gaining accounts are ranked and the top three's share of the whole gain is
    stated outright.

    Args:
        customers: dimension_change by customer.
        change: The overall dollar change, used as the denominator.

    Returns:
        A markdown sentence, or None when the change is too small to divide up
        or moved the opposite way from its own top accounts.
    """
    if not change:
        return None
    moved = movers(customers, "Dollars")
    if moved.empty:
        return None
    side = moved.head(3) if change > 0 else moved.tail(3)
    contribution = float(side["CHANGE"].sum())
    if contribution / change < 0.2:
        return None
    names = ", ".join(str(name) for name in side["LABEL"])
    word = "gain" if change > 0 else "shortfall"
    return (
        f"{len(side)} accounts carry **{lib.share(contribution, change)} of "
        f"the {word}**: {names}."
    )


def rolling_chart(frame: pd.DataFrame, measure: str) -> None:
    """Draw the rolling twelve-month total, which is the trend with no season in it.

    A rolling year always contains one of every month, so the seasonal swing
    that dominates a monthly chart cancels out and what is left is the direction
    of the business. Each point is the twelve months ending there, so the line
    turns a year after the business does -- it is slow on purpose, and it is the
    chart to argue with rather than the one to react to.

    The first eleven months have no year behind them and are left off entirely
    rather than drawn from a partial total, which would start the line at
    whatever January happened to be.

    This is the one chart on the page that does not answer the period picker. It
    takes the window's end date and looks back six years from it, because a
    trend read over thirteen weeks is not a trend.

    Args:
        frame: A frame from monthly_history.
        measure: The measure on screen.
    """
    if len(frame) <= ROLLING_MONTHS:
        lib.caption("Not enough history behind these filters to roll up a year.")
        return
    data = frame.copy()
    data["VALUE"] = data[measure.upper()].astype(float)
    data["ROLLING"] = data["VALUE"].rolling(ROLLING_MONTHS).sum()
    data = data.dropna(subset=["ROLLING"])
    data["LABEL"] = lib.bucket_labels(data["BUCKET"].tolist(), "month")
    data["TEXT"] = [lib.format_measure(v, measure) for v in data["ROLLING"]]
    order = data["LABEL"].tolist()

    base = alt.Chart(data).encode(
        x=alt.X(
            "LABEL:N", sort=order, title=None,
            axis=alt.Axis(labelAngle=-45, labelOverlap=True),
        ),
        y=alt.Y(
            "ROLLING:Q",
            title=f"{measure}, twelve months ending",
            axis=alt.Axis(format=lib.axis_format(measure)),
            scale=alt.Scale(zero=False),
        ),
    )
    line = base.mark_line(color=lib.SERIES_CURRENT, strokeWidth=3)
    hover = base.mark_circle(size=60, opacity=0).encode(
        tooltip=[
            alt.Tooltip("LABEL:N", title="Twelve months ending"),
            alt.Tooltip("TEXT:N", title=measure),
        ]
    )
    lib.draw_chart((line + hover).properties(height=TREND_HEIGHT))


def show_trend(drill: lib.Drill, period: dict, measure: str) -> None:
    """Draw the window against the same window a year earlier, with budget on it.

    Two lines and a target is the whole chart. It is the one picture on the page
    a reader can take in without being told how to read it, and every extra
    series spent on it is paid for out of that.

    Budget is drawn per bucket rather than as a single flat rule across the
    chart. A flat rule is only honest for a business with no season, and this one
    has one: laid flat, a budget that finance built to rise through the autumn
    would accuse every summer week of missing plan. Where a bucket has no budget
    behind it the dashed line simply stops, which is the truth about that bucket.

    Args:
        drill: The scope this page is drawn under.
        period: The window pair from build_period.
        measure: The measure on screen.
    """
    pair = lib.window_pair_series(drill)
    if pair.empty:
        lib.caption("Not enough of either window to draw a line.")
        return
    plan = lib.budget_series(drill.where, drill.params, period)
    label = None
    if not plan.empty and measure == "Dollars":
        by_bucket = plan.set_index(pd.to_datetime(plan["BUCKET"]))[
            measure.upper()
        ].astype(float)
        budgeted = pd.to_datetime(pair["BUCKET"]).map(by_bucket)
        if budgeted.notna().any():
            pair["BUDGET"] = budgeted
            label = "Budget"
    lib.draw_chart(
        lib.trend_chart(
            pair, measure, "This year", "A year earlier",
            height=TREND_HEIGHT, budget_label=label,
        )
    )
    lib.caption(trend_note(period, label is not None))


def trend_note(period: dict, budgeted: bool) -> str:
    """Write the line under the trend chart, saying what the budget line is or is not.

    Args:
        period: The window pair from build_period.
        budgeted: Whether a budget line was drawn.

    Returns:
        A caption, as markdown.
    """
    bucket = "week" if period["bucket"] == "week" else "month"
    opening = (
        f"Each point is one {bucket}, this window in blue against "
        f"{period['prior_label']} in grey."
    )
    if not budgeted:
        return (
            f"{opening} No budget line: budget is dollars only, for week "
            f"windows and year to date, in the years the finance workbook "
            f"covers."
        )
    if period["budget"] == "weekly" and bucket == "month":
        return (
            f"{opening} The dashed green line is budget, from the weekly "
            f"allocation, with each budget week counted into the month its "
            f"Saturday falls in -- so the window's total is exact and a month "
            f"boundary can be a few days out."
        )
    return f"{opening} The dashed green line is budget."


def driver_frame(frame: pd.DataFrame, measure: str) -> pd.DataFrame:
    """Cut one dimension down to the bars worth drawing in the driver grid.

    Ranked by this window rather than by the change, because this grid answers
    what the number is made of and not what moved it -- the bridges and the
    tornado charts further down are the ones that answer that. The change is
    still carried, on the tooltip, since a big name going backwards is the first
    thing anybody wants to know about a big name.

    Args:
        frame: A frame from dimension_change.
        measure: The measure on screen.

    Returns:
        The top DRIVER_BARS rows by this window's measure, carrying VALUE, the
        key and a NOTE column of display strings. Rows that sold nothing in this
        window are dropped, since a bar of no length is a wasted row of height.
    """
    current, prior = lib.measure_pair(frame, measure)
    data = frame.copy()
    data["VALUE"] = data[current].astype(float)
    data["WAS"] = data[prior].astype(float)
    data = data[data["VALUE"] > 0].nlargest(DRIVER_BARS, "VALUE")
    data["NOTE"] = [
        f"{lib.signed_measure(value - was, measure)} "
        f"({lib.percent(value - was, was)})"
        for value, was in zip(data["VALUE"], data["WAS"])
    ]
    return data


def show_drivers(
    where: str, params: tuple, period: dict, drill: lib.Drill, measure: str
) -> None:
    """Draw the grid of ranked bars over every slice the business is run by.

    Ten small charts rather than one big one, because "who and what is behind
    this number" is ten questions in a business that sells through chains, to
    accounts, via representatives, out of organizations, in classes, pack sizes,
    groups, PPGs, brands and items -- and a reader who has to change a dropdown
    nine times to see them has been given a form to fill in rather than an answer.

    Four of the ten are drawn from frames the page has already fetched for the
    paragraph, the movers and the bridges. dimension_change is cached on its
    arguments, and the arguments here are the same ones, so those four cost
    nothing.

    Args:
        where: The filter bar's predicate.
        params: Bind parameters for that predicate.
        period: The window pair from build_period.
        drill: The scope this page is drawn under.
        measure: The measure on screen.
    """
    lib.section(
        "What is it made of?",
        f"The {DRIVER_BARS} largest of each slice by {measure.lower()} in this "
        f"window. The slate tick on each bar is that same slice over "
        f"{period['prior_label']}, so a bar that has outrun its tick has grown. "
        f"Hover for the figures; click any bar to open it.",
    )
    columns = st.columns(DRIVER_COLUMNS)
    for position, (dimension, heading) in enumerate(DRIVERS):
        with columns[position % DRIVER_COLUMNS]:
            st.markdown(f"###### {heading}")
            frame = lib.dimension_change(where, params, dimension, period)
            ranked = driver_frame(frame, measure) if not frame.empty else frame
            if ranked.empty:
                lib.caption("Nothing sold here in this window.")
                continue
            lib.drillable_ranked(
                ranked, drill, name=f"driver_{dimension}", column=dimension,
                height=DRIVER_HEIGHT, note=("Change on last year", "NOTE"),
                prior="WAS",
            )


def split_items(frame: pd.DataFrame) -> dict:
    """Split every item into the four ways it can have changed the total.

    An item that sold cases in both windows has a realized price in
    both, so its change divides into price and volume. An item that appears in
    only one window has no pair to compare and is its own bar. An item that has
    dollars in both windows but no cases in one of them -- a charge with
    no weight against it -- has no price either way, and goes to the residual.

    Args:
        frame: A dimension_change frame at item grain.

    Returns:
        A dict with the `paired` frame and the `new` and `lost` dollar totals.
    """
    data = frame.copy()
    for column in ("CY_DOLLARS", "PY_DOLLARS", "CY_CASES", "PY_CASES"):
        data[column] = data[column].astype(float)
    paired = data[(data["CY_CASES"] > 0) & (data["PY_CASES"] > 0)]
    new = data[(data["PY_DOLLARS"] == 0) & (data["CY_DOLLARS"] != 0)]
    lost = data[(data["CY_DOLLARS"] == 0) & (data["PY_DOLLARS"] != 0)]
    return {
        "paired": paired,
        "new": float(new["CY_DOLLARS"].sum()),
        "lost": float(lost["PY_DOLLARS"].sum()),
        "new_count": len(new),
        "lost_count": len(lost),
    }


def price_volume_mix(paired: pd.DataFrame, prior_total: float) -> dict:
    """Split the paired items' change into volume, mix and price.

    Volume is the change in total cases valued at the prior window's average
    price across everything: what the money would have done if the business had
    sold the same blend of things, just more or less of it.

    Mix is what selling a different blend did at prior prices. A business that
    sells the same cases but moves them from club and distributor packs into retail jars
    earns more without charging anyone a cent more, and volume alone would report
    that as flat. This is the term that usually surprises people.

    Price is this window's cases revalued by each item's own change in realized
    price. It is item by item on purpose: a shift between a cheap item and an
    expensive one is mix, not a price rise, and folding the two together is the
    most common way this analysis is got wrong.

    Args:
        paired: Items with cases in both windows.
        prior_total: Prior-window dollars for the paired items, which sets the
            average price the volume and mix terms are valued at.

    Returns:
        A dict with `volume`, `mix` and `price` in dollars, all zero when the
        prior window sold no cases.
    """
    prior_cases = float(paired["PY_CASES"].sum())
    current_cases = float(paired["CY_CASES"].sum())
    if not prior_cases:
        return {"volume": 0.0, "mix": 0.0, "price": 0.0}
    average = prior_total / prior_cases
    at_prior_price = float(
        (paired["CY_CASES"] * paired["PY_DOLLARS"] / paired["PY_CASES"]).sum()
    )
    return {
        "volume": (current_cases - prior_cases) * average,
        "mix": at_prior_price - current_cases * average,
        "price": float(paired["CY_DOLLARS"].sum()) - at_prior_price,
    }


def item_effects(paired: pd.DataFrame) -> pd.DataFrame:
    """Return each paired item's own price and volume effect.

    Per item the split is exact and needs no portfolio term: the price effect is
    this window's cases times the item's own change in price, the volume effect
    is the change in its cases at its own prior price, and the two add to the
    item's change in dollars. Mix only exists once items are added together --
    it is the difference between what the items did and what their total did --
    so it has no per-item column here, and inventing one would be arithmetic
    with no meaning behind it.

    Args:
        paired: Items with cases in both windows.

    Returns:
        The frame with PRIOR_PRICE, CURRENT_PRICE, PRICE_EFFECT, VOLUME_EFFECT
        and CHANGE columns added.
    """
    data = paired.copy()
    data["PRIOR_PRICE"] = data["PY_DOLLARS"] / data["PY_CASES"]
    data["CURRENT_PRICE"] = data["CY_DOLLARS"] / data["CY_CASES"]
    data["PRICE_EFFECT"] = data["CY_CASES"] * (
        data["CURRENT_PRICE"] - data["PRIOR_PRICE"]
    )
    data["VOLUME_EFFECT"] = (data["CY_CASES"] - data["PY_CASES"]) * data[
        "PRIOR_PRICE"
    ]
    data["CHANGE"] = data["CY_DOLLARS"] - data["PY_DOLLARS"]
    return data


def paired_effects(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the per-item price and volume effects the item tables rank.

    Computed on its own rather than handed back by the bridge, because the
    tables are drawn above the bridge now and a function that draws a chart is
    the wrong place to fetch another section's numbers from.

    Args:
        frame: A dimension_change frame at item grain.

    Returns:
        The items with cases in both windows, carrying their effects.
        Empty when no item has a price in both windows.
    """
    paired = split_items(frame)["paired"]
    return item_effects(paired) if not paired.empty else paired


def show_item_bridge(frame: pd.DataFrame, period: dict) -> None:
    """Draw the price, volume and mix bridge.

    Args:
        frame: A dimension_change frame at item grain.
        period: The window pair from build_period.
    """
    parts = split_items(frame)
    paired = parts["paired"]
    prior_total = float(frame["PY_DOLLARS"].astype(float).sum())
    current_total = float(frame["CY_DOLLARS"].astype(float).sum())
    effects = price_volume_mix(paired, float(paired["PY_DOLLARS"].sum()))

    named = (
        effects["volume"] + effects["mix"] + effects["price"]
        + parts["new"] - parts["lost"]
    )
    residual = (current_total - prior_total) - named

    lib.draw_chart(
        lib.bridge_chart(
            [
                (period["prior_label"].capitalize(), prior_total, "anchor"),
                ("Volume", effects["volume"], "step"),
                ("Mix", effects["mix"], "step"),
                ("Price", effects["price"], "step"),
                (f"New items ({parts['new_count']})", parts["new"], "step"),
                (f"Items dropped ({parts['lost_count']})", -parts["lost"], "step"),
                ("Everything else", residual, "step"),
                (period["label"], current_total, "anchor"),
            ],
            "Dollars",
            height=BRIDGE_HEIGHT,
            compact=True,
        )
    )
    lib.caption(
        f"**Volume** is the change in cases at last year's average price. "
        f"**Mix** is what selling a different blend did at last year's prices. "
        f"**Price** is this year's cases at each item's own change in price. "
        f"**Everything else** is {lib.money(residual)}: items with sales in "
        f"both windows but no cases in one of them, plus rounding. The "
        f"bars add to {lib.money(current_total - prior_total)} exactly, because "
        f"the last one is whatever the others left over. Bar labels are rounded "
        f"to fit; hover for the exact figure."
    )


def effect_table(
    frame: pd.DataFrame, column: str, heading: str, price_columns: bool
) -> tuple[pd.DataFrame, list]:
    """Build a table of the items that contributed most to one effect.

    Both tails are shown rather than the top of one: the items that pushed the
    total up and the items that pulled it down are the same question asked twice,
    and a table of gainers alone has been read as "these are the problems" more
    than once.

    Args:
        frame: Paired items carrying their per-item effects.
        column: The effect column to rank on.
        heading: Name for that effect's column in the output.
        price_columns: Whether to show the two realized prices, which belong on
            a price table and only add width to a volume one.

    Returns:
        A tuple of the display frame, biggest positive contribution first, and
        the item number behind each of its rows.
    """
    ranked = frame.reindex(
        frame[column].abs().sort_values(ascending=False).index
    ).head(TOP_ROWS * 2)
    ranked = ranked.sort_values(column, ascending=False)
    rows = []
    for _, row in ranked.iterrows():
        entry = {"Item": row["LABEL"], heading: lib.signed_measure(row[column], "Dollars")}
        if price_columns:
            entry["Was"] = lib.price(row["PRIOR_PRICE"])
            entry["Now"] = lib.price(row["CURRENT_PRICE"])
        else:
            entry["Cases was"] = lib.number(row["PY_CASES"])
            entry["Cases now"] = lib.number(row["CY_CASES"])
        entry["Sales change"] = lib.signed_measure(row["CHANGE"], "Dollars")
        rows.append(entry)
    return pd.DataFrame(rows), ranked["DIM"].tolist()


def customer_bridge(frame: pd.DataFrame, period: dict) -> None:
    """Draw the same change split by what happened to the customer base.

    Four things can move a total at customer grain and they need different
    responses: customers won, customers lost, existing customers buying more,
    existing customers buying less. A business that grew because it won accounts
    and a business that grew because its accounts grew look identical on any
    chart of totals, and they are not the same business.

    Args:
        frame: A dimension_change frame at customer grain.
        period: The window pair from build_period.
    """
    data = frame.copy()
    for column in ("CY_DOLLARS", "PY_DOLLARS"):
        data[column] = data[column].astype(float)
    prior_total = float(data["PY_DOLLARS"].sum())
    current_total = float(data["CY_DOLLARS"].sum())

    won = data[(data["PY_DOLLARS"] == 0) & (data["CY_DOLLARS"] != 0)]
    gone = data[(data["CY_DOLLARS"] == 0) & (data["PY_DOLLARS"] != 0)]
    kept = data[(data["CY_DOLLARS"] != 0) & (data["PY_DOLLARS"] != 0)].copy()
    kept["CHANGE"] = kept["CY_DOLLARS"] - kept["PY_DOLLARS"]
    grew = kept[kept["CHANGE"] > 0]
    shrank = kept[kept["CHANGE"] < 0]

    lib.draw_chart(
        lib.bridge_chart(
            [
                (period["prior_label"].capitalize(), prior_total, "anchor"),
                (f"Won ({len(won)})", float(won["CY_DOLLARS"].sum()), "step"),
                (f"Lost ({len(gone)})", -float(gone["PY_DOLLARS"].sum()), "step"),
                (f"Bought more ({len(grew)})", float(grew["CHANGE"].sum()), "step"),
                (
                    f"Bought less ({len(shrank)})",
                    float(shrank["CHANGE"].sum()),
                    "step",
                ),
                (period["label"], current_total, "anchor"),
            ],
            "Dollars",
            height=BRIDGE_HEIGHT,
            compact=True,
        )
    )
    lib.caption(
        f"{len(kept):,} accounts bought in both windows, {len(won):,} are new "
        f"and {len(gone):,} did not come back. Won and lost are measured against "
        f"this window only, so an account that buys twice a year and did not "
        f"happen to buy in either window is in neither bar. The Customers page "
        f"names the ones that stopped."
    )


def show_bridges(
    items: pd.DataFrame, customers: pd.DataFrame, period: dict
) -> None:
    """Draw both bridges beside each other.

    They sit in one row rather than one above the other because they are the
    same change read two ways, and a reader comparing them should not have to
    scroll between them. Side by side each has about half the width it had
    alone, which is why both are drawn compact.

    Args:
        items: A dimension_change frame at item grain.
        customers: A dimension_change frame at customer grain.
        period: The window pair from build_period.
    """
    lib.section(
        "Does it all add up?",
        "The move from last year's sales to this year's, accounted for twice "
        "over: by what was sold, and by who bought it. Every figure above this "
        "is a part of one of these two staircases. Both are dollars whatever "
        "the measure toggle says, because price times volume is dollars.",
    )
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("###### Where did the dollars go?")
        show_item_bridge(items, period)
    with right:
        st.markdown("###### Was it the customers or the customer base?")
        customer_bridge(customers, period)


def show_item_tables(effects: pd.DataFrame, drill: lib.Drill) -> None:
    """Draw the two tables naming the items behind the price and volume bars.

    Args:
        effects: Paired items carrying their per-item effects.
        drill: The drill scope, already pinned to dollars.
    """
    heads = st.columns(2)
    with heads[0]:
        lib.section(
            "Which items were repriced?",
            "This window's cases at each item's own change in realized price, "
            "in dollars. A blend of pack sizes or customers can move a realized "
            "price without any list price changing.",
        )
    with heads[1]:
        lib.section(
            "Which items moved on volume?",
            "The change in each item's cases, valued at last year's price for "
            "that item, in dollars.",
        )
    tables = st.columns(2)
    with tables[0]:
        table, keys = effect_table(effects, "PRICE_EFFECT", "Price effect", True)
        lib.drillable_table(
            table, "Item", drill, name="price_effect",
            column="item_number", keys=keys, height=TABLE_HEIGHT,
        )
    with tables[1]:
        table, keys = effect_table(effects, "VOLUME_EFFECT", "Volume effect", False)
        lib.drillable_table(
            table, "Item", drill, name="volume_effect",
            column="item_number", keys=keys, height=TABLE_HEIGHT,
        )


def show_mover_charts(
    classes: pd.DataFrame,
    chains: pd.DataFrame,
    drill: lib.Drill,
    measure: str,
    period: dict,
) -> None:
    """Draw the two tornado charts of what moved, by class and by superchain.

    Superchain rather than ship-to customer, because one chain's stores would
    otherwise fill the chart: filtered to Retail Branded, four of the top five
    were Publix ship-tos.

    Args:
        classes: dimension_change by product class.
        chains: dimension_change by superchain.
        drill: The drill scope, following the measure toggle.
        measure: The measure on screen.
        period: The window pair from build_period.
    """
    # Without the wider gap the left chart's axis labels touch the right chart.
    left, right = st.columns(2, gap="large")
    with left:
        lib.section(
            "Which product classes moved?",
            f"Change in {measure.lower()} against {period['prior_label']}.",
        )
        moved = movers(classes, measure)
        if moved.empty:
            lib.caption("Nothing moved in either direction.")
        else:
            lib.drillable_tornado(
                moved, drill, name="pulse_class", column="product_class",
                height=300,
            )
    with right:
        lib.section(
            "Which superchains moved?",
            f"The {MOVERS} largest gains and the {MOVERS} largest losses.",
        )
        moved = movers(chains, measure)
        if moved.empty:
            lib.caption("Nothing moved in either direction.")
        else:
            edges = pd.concat([moved.head(MOVERS), moved.tail(MOVERS)])
            lib.drillable_tornado(
                edges.drop_duplicates("DIM"), drill, name="pulse_chain",
                column="superchain_customer", height=300,
            )


def main() -> None:
    """Render the pulse page.

    The page runs from the glance to the arithmetic: the figures, the line, what
    moved, what it is made of, which items were repriced, and finally the two
    bridges that account for the whole change. A reader can stop anywhere down
    that page and have an answer, which is why the bridges are at the foot -- of
    everything here they are the most exact and the slowest to read.

    The written headlines and the quiet-account query behind them are only
    fetched when the button on the filter bar is pressed, so the readers who
    never open them never pay for them.

    The customer-grain frame is fetched once and handed to all three things that
    need it: the concentration sentence, the driver bars and the customer
    bridge. They are the same numbers read four ways, and
    asking for them four times would only make the page's shape harder to
    follow.
    """
    choices = lib.page_header("Pulse", action="Show headlines")
    if choices is None:
        return
    where, params = choices["where"], choices["params"]
    period, measure = choices["period"], choices["measure"]
    drill = lib.drill_scope(choices)
    dollar_drill = drill._replace(measure="Dollars")

    current = lib.window_totals(where, params, period["start"], period["end"])
    prior = lib.window_totals(
        where, params, period["prior_start"], period["prior_end"]
    )
    if not current["dollars"] and not prior["dollars"]:
        st.info("Nothing matches these filters in either window.")
        return

    budget = lib.budget_total(where, params, period)
    headline_tiles(current, prior, budget, measure, period)

    classes = lib.dimension_change(where, params, "product_class", period)
    customers = lib.dimension_change(where, params, "customer_number", period)
    if choices["action"]:
        quiet = lib.quiet_accounts(where, params, period["end"])
        lines = compose_read(
            current, prior, budget, classes, customers, quiet, period
        )
        if lines:
            lib.queue_note("Headlines", lines)

    left, right = st.columns(2, gap="large")
    with left:
        lib.section(
            "What is the trend?",
            "The shape of the window rather than its total: where the line has been "
            "running, and whether it has been running above or below both last year "
            "and plan.",
        )
        show_trend(drill, period, measure)
    with right:
        lib.section(
            "Is the business growing? (12 month moving average)",
            f"Every point here is a full year of sales, the twelve months ending "
            f"at that point. Adding up a whole year at a time takes the season out, "
            f"and you are left with the "
            f"direction the business is actually heading. **This chart ignores the "
            f"period picker.** It always shows the six years ending "
            f"{period['end']:%d %b %Y}, using the filters above.",
        )
        rolling_chart(
            lib.monthly_history(where, params, period["end"], HISTORY_MONTHS), measure
        )

    chains = lib.dimension_change(where, params, "superchain_customer", period)
    show_mover_charts(classes, chains, drill, measure, period)

    show_drivers(where, params, period, drill, measure)

    items = lib.dimension_change(where, params, "item_number", period)
    if items.empty:
        lib.caption("No items match these filters in either window.")
    else:
        effects = paired_effects(items)
        if not effects.empty:
            show_item_tables(effects, dollar_drill)
        show_bridges(items, customers, period)

    lib.page_footer()


main()
