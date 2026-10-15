"""Shared helpers for a Streamlit dashboard. Copy, rename, fill in.

This is the starting point for a new app. It carries the two things every
dashboard here shares and must not reinvent: the house look, and the drill-through -- click a bar, get a modal, leave the page cut to
what you clicked.

Everything an app has to change is in the FILL THIS IN block at the top.
Everything below it should be left alone; if a new app needs it to behave
differently, that is worth a conversation before it becomes a fourth variant.

The reasoning behind the drill lives in the skill, not here:
../reference/drill-through.md.
"""

import json
import os
import re
import uuid
from typing import NamedTuple

import altair as alt
import pandas as pd
import streamlit as st

# Everything one app changes is above SERIES_ORDER. Below it is the house style.
APP_NAME = "MY_DASHBOARD"

RELATION = "rpt_my_thing"

MEASURES = {
    "Dollars": ("dollars", "money"),
    "Pounds": ("pounds", "number"),
}
DEFAULT_MEASURE = "Dollars"

DETAIL_NAME = "Detail"

PAGE_FILES = {
    "Overview": "pages/overview.py",
    "Detail": "pages/detail.py",
    "Documentation": "pages/documentation.py",
}

# What a drill on each column is called, in the modal and on its chip.
DIMENSION_NOUNS = {
    "customer_name": "Customer",
    "item_description": "Item",
}

# What a modal breaks its pick down by, answering the second question first.
SPLIT_BY = {
    "customer_name": "item_description",
    "item_description": "customer_name",
}

# One order shared by every dashboard here, validated against the cream page.
SERIES_ORDER = ["#0e7c86", "#c96f12", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

MUTED_INK = "#8b8b8b"
INK = "#282828"

# Vega's default gridline grey is invisible against the cream page.
GRID_INK = "#767065"
GRID_OPACITY = 0.18

LABEL_LIMIT = 260

TILE_PIXELS = 116
TILE_METRIC_PIXELS = 66

PAGE_STYLE = """
<style>
  .block-container { padding-top: 3rem; padding-bottom: 1rem; }
  .block-container h3 { margin-bottom: 0.25rem; }
  [data-testid="stPopoverBody"] {
    border: 1px solid rgba(128, 128, 128, 0.45);
    border-radius: 0.5rem;
  }
</style>
"""

PAGE_KEY = "_dashboard_page"
RUN_KEY = "_dashboard_run"
MEASURE_KEY = f"{APP_NAME.lower()}_measure"

SELECTION_EPOCH = "_selection_epoch"
DRILL_PENDING = "_pending_drill"
SCOPE_STACK = "_scope_stack"
ORIGIN = "_drill_origin"
PAGE = "_current_page"
DETAIL_MEASURE = "_detail_measure"

BAR_SELECTION = "bar"


def get_session():
    """Return a Snowpark session, whether running in Snowflake or locally.

    The container runtime serves every viewer from one app process, and the
    session get_active_session() hands back is not safe to share across those
    threads, so Snowflake's migration guide replaces it with st.connection.
    Locally there is no Snowflake connection for st.connection to find, so a
    session is built from the default connection in the developer's
    connections.toml -- no connection name is hardcoded, because each developer
    names theirs differently.

    Args:
        None.

    Returns:
        A Snowpark Session connected to the account.

    Raises:
        Exception: Whatever Snowpark raises if neither route can connect.
    """
    try:
        return st.connection("snowflake").session()
    except Exception:
        from snowflake.snowpark import Session

        return Session.builder.create()


def _analytics_database() -> str:
    """Return the analytics database this app should read.

    Streamlit in Snowflake runs an app in the database the app object lives in,
    so an app deployed into DEMO.STREAMLIT reads DEMO. Locally a connection
    usually carries no database at all, which is what ANALYTICS_DATABASE is for.

    Args:
        None.

    Returns:
        The database name, unquoted.

    Raises:
        RuntimeError: If the session has no database and no override was given.
            Guessing a default here is how an app would silently read the wrong
            database, so this fails instead.
    """
    override = os.getenv("ANALYTICS_DATABASE")
    if override:
        return override.strip('"')

    database = get_session().get_current_database()
    if not database:
        raise RuntimeError(
            "This session has no current database, so there is no way to tell "
            "which database to read. Set ANALYTICS_DATABASE, e.g. MY_DATABASE."
        )
    return database.strip('"')


def _mart_schema(database: str) -> str:
    """Return the schema holding this app's relation.

    A developer reading from a personal schema overrides it with
    ANALYTICS_SCHEMA.

    Args:
        database: The database being read.

    Returns:
        The schema holding the relation.
    """
    return "my_schema"


DATABASE = _analytics_database()
SCHEMA = os.getenv("ANALYTICS_SCHEMA") or _mart_schema(DATABASE)
SOURCE = f"{DATABASE}.{SCHEMA}.{RELATION}"


def remember_page(page) -> None:
    """Record the page about to run, so its queries can be tagged with it.

    The default page's `url_path` is the empty string, because it answers on the
    app's root URL, so the title is what names it.

    Args:
        page: The StreamlitPage that st.navigation selected.

    Returns:
        None.
    """
    name = re.sub(r"[^a-z0-9]+", "_", (page.url_path or page.title).lower())
    st.session_state[PAGE_KEY] = name.strip("_") or "unknown"


def viewer() -> str:
    """Return the Snowflake user looking at the app.

    Owner's rights means `QUERY_HISTORY.USER_NAME` is the app's own generated
    pseudo-user, not the person, so the tag is the only place the viewer can
    come from. Running outside Snowflake there is nobody to name.

    Args:
        None.

    Returns:
        The viewer's Snowflake user name, or `unknown`.
    """
    return getattr(st.user, "user_name", None) or "unknown"


def query_tag() -> str:
    """Return the query tag for the statement about to run.

    Built per statement rather than set on the session. The container runtime
    serves every viewer from one process over one shared connection, so an
    ALTER SESSION would race between viewers sitting on different pages, and
    the account default would be what landed in QUERY_HISTORY. `run` is one id
    per viewer session, which makes a single visit costable the way a task
    graph run is. The keys are `env`, `app`, `run`, `obj` and `user`.

    Args:
        None.

    Returns:
        The tag as compact JSON.
    """
    database = (get_session().get_current_database() or "").strip('"').upper()
    if RUN_KEY not in st.session_state:
        st.session_state[RUN_KEY] = uuid.uuid4().hex[:16]
    return json.dumps(
        {
            "env": database.removesuffix("_ANALYTICS").lower() or "unknown",
            "app": f"{database}.STREAMLIT.{APP_NAME}" if database else APP_NAME,
            "run": st.session_state[RUN_KEY],
            "obj": st.session_state.get(PAGE_KEY, "unknown"),
            "user": viewer(),
        },
        separators=(",", ":"),
    )


def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a query and return the result.

    The tag is built out here rather than inside the cached call, because
    st.cache_data would otherwise freeze whichever viewer missed the cache
    first into every later caller's statements.

    Args:
        sql: The full SQL statement to run.
        params: Bind parameters, as a tuple so the result can be cached.

    Returns:
        The result as a pandas DataFrame with upper-case column names.
    """
    return _run_query(sql, params, query_tag())


@st.cache_data(ttl=3600)
def _run_query(sql: str, params: tuple, _tag: str) -> pd.DataFrame:
    """Run a query and cache the result.

    Args:
        sql: The full SQL statement to run.
        params: Bind parameters, as a tuple so the result can be cached.
        _tag: The query tag. Underscored so st.cache_data leaves it out of the
            cache key, keeping one entry per statement rather than one per
            page and viewer.

    Returns:
        The result as a pandas DataFrame with upper-case column names.
    """
    return get_session().sql(sql, params=list(params)).to_pandas(
        statement_params={"QUERY_TAG": _tag}
    )


def measure_column(measure: str) -> str:
    """Return the relation column a measure reads.

    Args:
        measure: A key of MEASURES.

    Returns:
        The column name.
    """
    return MEASURES[measure][0]


def money(value: float) -> str:
    """Return a dollar figure written the way the dashboards write it.

    Args:
        value: The figure, or None.

    Returns:
        The formatted string, or `--` when there is nothing to show.
    """
    if value is None or pd.isna(value):
        return "--"
    return f"${value:,.0f}"


def number(value: float) -> str:
    """Return a plain count or weight, thousands separated.

    Args:
        value: The figure, or None.

    Returns:
        The formatted string, or `--` when there is nothing to show.
    """
    if value is None or pd.isna(value):
        return "--"
    return f"{value:,.0f}"


def format_measure(value: float, measure: str) -> str:
    """Return a figure formatted the way its measure is written.

    Args:
        value: The figure, or None.
        measure: A key of MEASURES.

    Returns:
        The formatted string.
    """
    return {"money": money, "number": number}[MEASURES[measure][1]](value)


def percent(part: float, whole: float) -> str:
    """Return one figure's share of another.

    Args:
        part: The numerator.
        whole: The denominator.

    Returns:
        The share to one decimal place, or `--` when it cannot be taken.
    """
    if not whole or pd.isna(whole) or part is None or pd.isna(part):
        return "--"
    return f"{100 * part / whole:,.1f}%"


def draw_chart(chart: alt.Chart) -> None:
    """Render a chart at the container's width and its own declared height.

    Always render through here rather than calling `st.altair_chart` directly.
    Streamlit stamps `autosize: fit` onto a chart asked to stretch, and `fit`
    sizes both axes to the container, so a declared height is honoured on first
    paint and thrown away once the frontend measures. `fit-x` fits the width and
    leaves the height alone.

    Args:
        chart: A chart that has already declared its height in pixels.

    Returns:
        None.
    """
    st.altair_chart(
        chart.properties(autosize={"type": "fit-x", "contains": "padding"}),
        width="stretch",
    )


def stat_tile(label: str, value: str, *, note: str | None = None) -> None:
    """Draw one headline number as a bordered tile of fixed height.

    The height is fixed rather than sized to content because Streamlit will
    happily draw tiles of different heights beside each other, and the result
    reads as a rendering glitch.

    Args:
        label: Name of the measure.
        value: The figure, already formatted.
        note: Context for the help tooltip.

    Returns:
        None.
    """
    with st.container(border=True, height=TILE_PIXELS):
        st.metric(label, value, help=note, height=TILE_METRIC_PIXELS)


def grid_axis(title: str, **kwargs) -> alt.Axis:
    """Return an axis styled to recede behind the data.

    Args:
        title: The axis title.
        **kwargs: Any other Altair axis property to set or override.

    Returns:
        The configured axis.
    """
    return alt.Axis(
        title=title,
        gridColor=GRID_INK,
        gridOpacity=GRID_OPACITY,
        domainColor=GRID_INK,
        tickColor=GRID_INK,
        labelColor=INK,
        **kwargs,
    )


def compact(value: float, measure: str) -> str:
    """Return a figure short enough to sit at the end of a bar.

    Three significant figures and a K, M or B suffix; the tooltip carries the
    exact number.

    Args:
        value: The figure, or None.
        measure: A key of MEASURES, which decides the dollar sign.

    Returns:
        The shortened figure, such as "$70.1M", or `--`.
    """
    if value is None or pd.isna(value):
        return "--"
    short = f"{value:,.0f}"
    for cutoff, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= cutoff:
            scaled = value / cutoff
            short = f"{scaled:,.0f}{suffix}" if abs(scaled) >= 100 else f"{scaled:,.1f}{suffix}"
            break
    return f"${short}" if MEASURES[measure][1] == "money" else short


def ranked_bar(frame: pd.DataFrame, dimension: str, measure: str, *,
               height: int, selectable: bool = False,
               sort: list | None = None) -> alt.Chart:
    """Return a ranked horizontal bar chart with each value at the end of its bar.

    Drawn the way every bar chart here is drawn. Once the number is on the bar,
    a value axis is a second and vaguer way of reading it, so there is none,
    and no gridlines. The scale runs a fifth past the longest bar so its label
    fits. Clicks on this layered chart are reported from Streamlit 1.55 on
    (streamlit#8643), so a clickable chart keeps its labels too.

    Args:
        frame: Rows carrying the dimension column and a `VALUE` column.
        dimension: Name of the dimension column, upper case.
        measure: A key of MEASURES, used to format the labels.
        height: Chart height in pixels.
        selectable: Whether bars accept clicks. Picking one dims the others.
        sort: A fixed order for the bars, such as the age bands. Defaults to
            largest first.

    Returns:
        The chart, before draw_chart or clickable_chart sets its autosize.
    """
    frame = frame.copy()
    frame["LABEL"] = [compact(v, measure) for v in frame["VALUE"]]
    values = pd.to_numeric(frame["VALUE"], errors="coerce")
    top = float(values.max()) if values.notna().any() else 0.0
    bottom = min(0.0, float(values.min()) if values.notna().any() else 0.0)
    noun = DIMENSION_NOUNS.get(dimension.lower(), dimension.title())

    base = alt.Chart(frame).encode(
        x=alt.X("VALUE:Q", title=None, axis=None,
                scale=alt.Scale(domain=[bottom, top * 1.2 if top > 0 else 1.0], nice=False)),
        y=alt.Y(
            f"{dimension}:N", title=None,
            sort=sort if sort is not None else alt.EncodingSortField(
                field="VALUE", op="max", order="descending"),
            axis=alt.Axis(labelLimit=LABEL_LIMIT, labelColor=INK, domain=False, ticks=False),
        ),
        tooltip=[
            alt.Tooltip(f"{dimension}:N", title=noun),
            alt.Tooltip("VALUE:Q", title=measure,
                        format="$,.0f" if MEASURES[measure][1] == "money" else ",.0f"),
        ],
    )
    bars = base.mark_bar(
        cornerRadiusEnd=3, color=SERIES_ORDER[0],
        **({"cursor": "pointer"} if selectable else {}),
    )
    if selectable:
        picker = alt.selection_point(name=BAR_SELECTION, fields=[dimension], on="click")
        bars = bars.add_params(picker).encode(
            opacity=alt.condition(picker, alt.value(1.0), alt.value(0.3)),
        )
    labels = base.mark_text(align="left", dx=6, color=MUTED_INK).encode(text="LABEL:N")
    return (bars + labels).properties(height=height)


class Level(NamedTuple):
    """One drill in force, held as the predicate it applies and its name.

    A drill is stored as a predicate rather than as a column and a value so that
    picks from different charts can sit in one stack -- including bars that are
    not a column's values at all, such as a set of overlapping flags. The key is
    what makes two clicks on the same bar the same drill, so it must not depend
    on which chart or page the click came from.
    """

    key: str
    predicate: str
    params: tuple
    label: str


class Drill(NamedTuple):
    """Everything a bar click needs to open a modal and lead on to the rows.

    A page builds one from its filter bar and hands it to every chart it draws.
    A chart showing less than the page does narrows it first, so the modal a bar
    opens counts the rows the bar drew.

    **Everything a drill picks travels as a predicate, and nothing it picks is
    written into a filter widget.** Writing widget state is only legal before
    the widget is drawn, which a drill taken from the page that owns those
    widgets cannot promise. A predicate has no such ordering: every page ANDs it
    on, shows it as a chip, and a click on the chip drops it.

    `measure` travels because the Detail page has to open on the measure the
    reader drilled from, or the number they land on is not the number they
    clicked.
    """

    where: str
    params: tuple
    measure: str

    def narrow(self, predicate: str, params: tuple = ()) -> "Drill":
        """Return this drill scoped by a further predicate.

        Args:
            predicate: SQL to AND onto the drill's predicate.
            params: Bind parameters for it.

        Returns:
            A new Drill. The original is unchanged.
        """
        return self._replace(
            where=f"({self.where}) and {predicate}",
            params=(*self.params, *params),
        )


def bar_level(column: str, picked: str, value: str | None = None) -> Level:
    """Return the drill one clicked bar stands for.

    Args:
        column: The relation column the bars are values of.
        picked: The bar's label, which is what the chip and modal are named
            with.
        value: What to scope on, when that is not the label itself -- a bar
            labelled with something readable while the column holds an id.

    Returns:
        The Level that click puts in force.
    """
    scope_value = picked if value is None else value
    return Level(f"{column}={scope_value}", f"{column} = ?", (scope_value,), picked)


def scope_levels() -> list:
    """Return the drills in force, outermost first.

    Args:
        None.

    Returns:
        One Level per click still in force.
    """
    return st.session_state.get(SCOPE_STACK, [])


def carried_scope() -> tuple[str, tuple]:
    """Return the predicate the drills in force add to every page.

    Each drill is held as the one pick it is rather than as the chain it was
    taken in, so any one of them can be dropped without rebuilding the others.

    Args:
        None.

    Returns:
        The predicate and its bind parameters, both empty when nothing is
        drilled.
    """
    levels = scope_levels()
    if not levels:
        return ("", ())
    return (
        " and ".join(level.predicate for level in levels),
        tuple(value for level in levels for value in level.params),
    )


def scope_label(*, without: str | None = None) -> str:
    """Return the drills in force written out, for a button or a caption.

    Args:
        without: Key of a drill to leave out, which is how the modal's second
            button names the state it returns in.

    Returns:
        The labels joined with `and`, or an empty string when nothing is left.
    """
    return " and ".join(
        level.label for level in scope_levels() if level.key != without
    )


def push_scope(level: Level) -> None:
    """Put what a click picked in force across every page.

    Args:
        level: The drill that click stands for.

    Returns:
        None.
    """
    st.session_state[SCOPE_STACK] = [*scope_levels(), level]


def drop_scope(position: int) -> None:
    """Drop one drill, leaving every other one in force.

    Args:
        position: Which drill to drop, as an index into scope_levels.

    Returns:
        None.
    """
    levels = list(scope_levels())
    if 0 <= position < len(levels):
        levels.pop(position)
    st.session_state[SCOPE_STACK] = levels


def scope_index(key: str) -> int | None:
    """Return where a pick sits among the drills in force, if it is one of them.

    A click on something already drilled into is the reader taking that drill
    back, wherever in the chain it sits.

    Args:
        key: The key of the Level a click stands for.

    Returns:
        The index of the matching drill, or None when this is a new pick.
    """
    for position, level in enumerate(scope_levels()):
        if level.key == key:
            return position
    return None


SCOPE_PARAM = f"{APP_NAME.lower()}_scope"


def _seed_scope_from_query_params() -> None:
    """Seed the drill stack from the URL, once per session.

    Skipped once SCOPE_STACK already has an entry, so a reader's own clicks
    always win over the link the page was opened with.

    Args:
        None.

    Returns:
        None.
    """
    if SCOPE_STACK in st.session_state:
        return
    raw = st.query_params.get(SCOPE_PARAM)
    if not raw:
        return
    try:
        rows = json.loads(raw)
    except ValueError:
        return
    levels = [
        Level(f"{c}={v}", f"{c} = ?", (v,), lb) for row in rows
        if isinstance(row, list) and len(row) == 3
        and all(isinstance(part, str) for part in row)
        for c, v, lb in [row]
    ]
    if levels:
        st.session_state[SCOPE_STACK] = levels


def _sync_scope_to_query_params() -> None:
    """Keep the URL's drill param equal to the drill stack.

    Call once per run, after the chips are drawn, so every way the stack can
    change -- a bar click, a chip's cross, Clear all -- is caught here rather
    than at each call site.

    Args:
        None.

    Returns:
        None.
    """
    rows = [[level.key.split("=", 1)[0], *level.params, level.label]
            for level in scope_levels()]
    if rows:
        st.query_params[SCOPE_PARAM] = json.dumps(rows, separators=(",", ":"))
    else:
        st.query_params.pop(SCOPE_PARAM, None)


def chart_key(name: str) -> str:
    """Return the widget key a selectable chart should be drawn under.

    Streamlit does not allow a chart's selection to be cleared from Python, so
    the only way to clear one is to draw the chart as a different widget: a new
    key means a new widget, and a new widget starts with nothing selected. The
    epoch appended here is bumped by clear_selections once a click has been
    acted on. Without it, returning to a page re-fires the drill the reader
    already took, and clicking the same bar twice does nothing the second time.

    Args:
        name: Stable name for the chart within its page.

    Returns:
        The widget key, carrying the current epoch.
    """
    return f"{name}_{st.session_state.get(SELECTION_EPOCH, 0)}"


def clear_selections() -> None:
    """Drop every selectable chart's selection from the next run onward.

    Args:
        None.

    Returns:
        None.
    """
    st.session_state[SELECTION_EPOCH] = st.session_state.get(SELECTION_EPOCH, 0) + 1


def apply_click(chart: Drill, level: Level, column: str) -> None:
    """Act on a click on a bar, and start the run that shows the result.

    A click does two things at once: it puts what it picked in force across the
    whole app, so closing the modal leaves the reader looking at a dashboard cut
    to the thing they clicked; and it queues the modal that opens over it. A
    click on a bar a drill already holds is read as taking that drill back, so
    the same bar both applies and clears.

    The rerun is what makes the modal open over the filtered page rather than
    the one the click was taken on. Dismissing a dialog does not rerun the app,
    so a page left wrong here would stay wrong until the reader touched
    something else.

    Args:
        chart: The drill the clicked chart was drawn under.
        level: The drill the clicked bar stands for.
        column: The relation column the bars are values of, which names the
            modal.

    Returns:
        None.
    """
    held = scope_index(level.key)
    if held is not None:
        drop_scope(held)
    else:
        push_scope(level)
        st.session_state[DRILL_PENDING] = {
            "chart": chart,
            "scoped": chart.narrow(level.predicate, level.params),
            "column": column,
            "value": level.label,
            "level_key": level.key,
        }
    clear_selections()
    st.rerun()


def clickable_chart(chart: alt.Chart, key: str, dimension: str) -> str | None:
    """Draw a chart whose bars can be clicked, and return the category clicked.

    Args:
        chart: A chart built by ranked_bar with `selectable=True`.
        key: Widget key, which should come from chart_key.
        dimension: Name of the dimension column the selection carries.

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
    picked = [row[dimension] for row in rows if isinstance(row, dict) and dimension in row]
    return str(picked[0]) if picked else None


def drillable_chart(frame: pd.DataFrame, dimension: str, drill: Drill, *,
                    name: str, height: int = 240, column: str | None = None,
                    values: dict | None = None) -> None:
    """Draw a ranked bar chart whose bars drill when clicked.

    This is what every bar chart on the dashboard is drawn with.

    Args:
        frame: Rows carrying the dimension column and a `VALUE` column.
        dimension: Name of the dimension column in `frame`, upper case.
        drill: The scope this chart is drawn under.
        name: Stable name for this chart within its page, used for its key.
        height: Chart height in pixels.
        column: The relation column to scope on, when the bars are not values
            of the column they are labelled with. Defaults to `dimension`
            lowered.
        values: Bar label to the value to scope on, for that same case.

    Returns:
        None.
    """
    if frame.empty:
        st.caption("Nothing in this window.")
        return
    picked = clickable_chart(
        ranked_bar(frame, dimension, drill.measure, height=height, selectable=True),
        chart_key(name), dimension,
    )
    if picked is None:
        return
    target = column or dimension.lower()
    apply_click(drill, bar_level(target, picked, (values or {}).get(picked)), target)


def drillable_table(frame: pd.DataFrame, index: str, drill: Drill, *,
                    name: str, column: str, keys: list,
                    height: int | None = None) -> None:
    """Draw a table whose rows drill when clicked.

    Only aggregate tables drill -- a row here stands for the same thing a bar
    stands for. A list of individual rows is where a drill ends, so it stays
    unclickable.

    Args:
        frame: The display-ready table.
        index: Name of the column used as the row label.
        drill: The scope this table is drawn under.
        name: Stable name for this table within its page.
        column: The relation column the keys belong to.
        keys: The value to scope on for each row, in the frame's own order.
        height: Fixed height in pixels. The default fits every row up to a cap.

    Returns:
        None.
    """
    event = st.dataframe(
        frame.set_index(index),
        width="stretch",
        height=height or min(len(frame) * 35 + 38, 560),
        key=chart_key(name),
        on_select="rerun",
        selection_mode="single-row",
    )
    rows = (event.selection or {}).get("rows") or []
    position = rows[0] if rows else None
    if position is None or position >= len(keys):
        return
    apply_click(drill, bar_level(column, str(keys[position])), column)


def scope_chips() -> None:
    """Draw one chip per drill in force, each dropping only itself.

    A predicate the reader can neither see nor clear is worse than one they
    never had, and these arrive from single clicks on charts they may have
    scrolled past. One chip per pick rather than one badge for all of them,
    because two drills are two decisions.

    Args:
        None.

    Returns:
        None.
    """
    levels = scope_levels()
    if not levels:
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(":orange-badge[Drilled into]", width="content")
        for position, level in enumerate(levels):
            if st.button(
                level.label,
                key=f"drop_{level.key}",
                icon=":material/close:",
                help="Drops this drill. Clicking its bar again does the same.",
            ):
                drop_scope(position)
                clear_selections()
                st.rerun()
        if len(levels) > 1 and st.button("Clear all", key="clear_scope", type="tertiary"):
            st.session_state.pop(SCOPE_STACK, None)
            clear_selections()
            st.rerun()


def total(drill: Drill) -> float:
    """Return the measure summed over everything a drill covers.

    Args:
        drill: The scope to sum over.

    Returns:
        The total, as a float.
    """
    column = measure_column(drill.measure)
    frame = run_query(
        f"select coalesce(sum({column}), 0) as value from {SOURCE} where {drill.where}",
        drill.params,
    )
    return float(frame["VALUE"].iloc[0])


def return_options(level_key: str) -> None:
    """Draw a drill modal's two ways back to the page it was opened from.

    The click that opened this modal has already filtered the page underneath,
    and the modal is the one place the reader is certainly looking, so it is
    where they are told so. Both buttons name the state they return in rather
    than the action they take, since "keep" and "drop" mean nothing until you
    already know a click filtered the page. Naming the page as well is what
    makes the pair read as a way home rather than as two more filters. The cross
    in the corner does what the first of them does.

    Args:
        level_key: The key of the drill this modal is showing, which is the one
            the second button drops.

    Returns:
        None.
    """
    page = st.session_state.get(PAGE) or "the dashboard"
    remaining = scope_label(without=level_key)
    kept, dropped = st.columns(2)
    if kept.button(
        f"Return to {page}, filtered on {scope_label()}",
        icon=":material/filter_alt:",
        key="return_filtered",
        width="stretch",
    ):
        st.rerun()
    if dropped.button(
        f"Return to {page}, filtered on {remaining}" if remaining
        else f"Return to {page}, unfiltered",
        icon=":material/filter_alt_off:",
        key="return_unfiltered",
        width="stretch",
    ):
        position = scope_index(level_key)
        if position is not None:
            drop_scope(position)
        clear_selections()
        st.rerun()


def drill_body(chart: Drill, scoped: Drill, column: str, value: str,
               level_key: str) -> None:
    """Fill a drill modal with one bar's position.

    One body serves every chart on the dashboard: the same headline figures, the
    same share of what was on screen, and a breakdown whose column comes from
    SPLIT_BY, so only what is being broken down changes with what was clicked.

    It opens with the two ways back out, because the click that opened it has
    already filtered the page underneath, and closes with the way through to the
    rows -- a modal is a dead end unless it offers a way further in.

    Args:
        chart: The drill the clicked chart was drawn under, which is the
            denominator of the share tile.
        scoped: That drill narrowed to the bar the reader clicked.
        column: The relation column the bar was a value of.
        value: The bar's label.
        level_key: The key of the drill this modal is showing.

    Returns:
        None.
    """
    return_options(level_key)

    figure = total(scoped)
    whole = total(chart)

    st.markdown(f"### {value}")
    tiles = st.columns(2)
    with tiles[0]:
        stat_tile(scoped.measure, format_measure(figure, scoped.measure))
    with tiles[1]:
        stat_tile(
            "Share of what is on screen", percent(figure, whole),
            note=f"Out of {format_measure(whole, scoped.measure)}, which is "
                 "everything this page's filters covered before this drill.",
        )

    split = SPLIT_BY.get(column)
    if split and split != column:
        rows = run_query(
            f"select {split} as {split}, sum({measure_column(scoped.measure)}) as value"
            f" from {SOURCE} where {scoped.where} and {split} is not null"
            " group by all order by value desc nulls last limit 10",
            scoped.params,
        )
        if not rows.empty:
            st.markdown(f"##### By {DIMENSION_NOUNS.get(split, split).lower()}")
            draw_chart(ranked_bar(rows, split.upper(), scoped.measure,
                                  height=max(130, 26 * len(rows))))

    if st.button("See the rows", icon=":material/table_rows:", type="primary"):
        open_rows(scoped)


def open_pending_drill() -> None:
    """Open the modal a bar click queued, if a click queued one.

    Called at the top of the run the click started, so the modal is on screen
    while the page it filtered redraws behind it. The drill is taken rather than
    read: while a modal is open Streamlit reruns only the modal, so a later full
    rerun must not bring it back.

    The dialog is decorated here rather than at import because a dialog's title
    is fixed when it is decorated, and this one names whatever was clicked.

    Args:
        None.

    Returns:
        None.
    """
    pending = st.session_state.pop(DRILL_PENDING, None)
    if not pending:
        return
    column = pending["column"]
    title = DIMENSION_NOUNS.get(column, column.replace("_", " ").capitalize())
    st.dialog(title, width="large")(drill_body)(**pending)


def open_rows(drill: Drill) -> None:
    """Send the reader from a drill modal to the rows behind it.

    The scope the modal was showing is already in force on every page, so the
    only thing that has to travel is the measure, which Detail owns its own copy
    of. A reader who drills from a dollars chart and lands on a pounds page has
    been shown a different number than the one they clicked.

    Args:
        drill: The scope the modal was showing.

    Returns:
        None.
    """
    origin = st.session_state.get(PAGE)
    if origin != DETAIL_NAME:
        st.session_state[ORIGIN] = origin
        st.session_state[DETAIL_MEASURE] = drill.measure
    clear_selections()
    st.switch_page(PAGE_FILES[DETAIL_NAME])


def apply_pending_measure() -> None:
    """Set Detail's measure from the drill that opened it, before a widget exists.

    Streamlit refuses to write a widget's state once that widget has been drawn,
    so this has to run at the very top of the page, above every other call.

    Args:
        None.

    Returns:
        None.
    """
    pending = st.session_state.pop(DETAIL_MEASURE, None)
    if pending:
        st.session_state[MEASURE_KEY] = pending


def back_button() -> None:
    """Draw the button back to the page a drill led away from, if there is one.

    Detail is reached both from the nav and from a modal on another page, and a
    reader who arrived the second way has no way back to the chart they were
    reading: the nav returns them to the page, but only the browser's back
    button knows which page it was.

    Args:
        None.

    Returns:
        None.
    """
    origin = st.session_state.get(ORIGIN)
    if origin not in PAGE_FILES:
        return
    if st.button(f"Back to {origin}", icon=":material/arrow_back:", type="tertiary"):
        st.session_state.pop(ORIGIN, None)
        st.switch_page(PAGE_FILES[origin])


def page_header(title: str, *, name: str) -> Drill:
    """Draw a page's header: any queued modal, the filter bar and the chips.

    Every page opens with the same things in the same order, so they are one
    call rather than several each page has to remember to make in sequence. The
    modal is opened before the page under it is drawn, so it appears while that
    page's queries are still running rather than after them.

    Replace the filter bar below with whatever this dashboard filters on. What
    must not change is the order: record the page, open the modal, seed and
    draw the filters, draw the chips, sync the URL, then return a Drill
    carrying the drills in force. Keep every control in the one wrapping row
    (see branding.md, *The filter bar*). Give each filter widget `bind="query-params"`
    next to its `key=` so a filtered page is a shareable link -- skip it only
    on a widget whose `format_func` label can change under the reader (see the
    skill).

    Args:
        title: Page heading.
        name: The page's display name, used to offer a way back from Detail.

    Returns:
        The Drill every chart on the page should be drawn under.
    """
    _seed_scope_from_query_params()
    st.session_state[PAGE] = name
    if name != DETAIL_NAME:
        st.session_state.pop(ORIGIN, None)
    open_pending_drill()

    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        st.markdown(f"## {title}", width="content")
        measure = st.selectbox(
            "Measure", list(MEASURES),
            index=list(MEASURES).index(DEFAULT_MEASURE), key=MEASURE_KEY,
            width=200,
        )
    scope_chips()
    _sync_scope_to_query_params()

    where, params = "1=1", ()
    drilled, drilled_params = carried_scope()
    if drilled:
        where, params = f"{where} and {drilled}", (*params, *drilled_params)
    return Drill(where=where, params=params, measure=measure)
