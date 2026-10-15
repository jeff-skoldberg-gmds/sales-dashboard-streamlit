# The look

Everything here is already true of this project's dashboards. Copy it; don't redesign it.

## Theme

`.streamlit/config.toml` is **the same in every app**. Copy it from
`scaffold/config.toml`. Do not hand-write it.

```toml
[theme]
base = "light"
baseRadius = "0.5rem"
primaryColor = "#0e7c86"
backgroundColor = "#f5f8f6"
secondaryBackgroundColor = "#e2ece8"
textColor = "#16262e"
borderColor = "#bccfc8"
dataframeHeaderBackgroundColor = "#d3e3dc"
codeTextColor = "#b3361b"
codeBackgroundColor = "#e9f0ed"
linkColor = "#0e7c86"
```

The fills and borders are a shade darker than a near-white page would suggest on
purpose: very pale borders leave controls almost invisible on some monitors.

**A theme change does not reach a running Snowflake app.** `config.toml` ships on
deploy, but the app keeps the old colours until it restarts. See
[../../streamlit-in-snowflake/SKILL.md](../../streamlit-in-snowflake/SKILL.md).

## Series colours

```python
SERIES_ORDER = ["#0e7c86", "#c96f12", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
```

One order, shared by every dashboard. Take colours from the front of it. The
sales pages also name individual roles out of it — `SERIES_CURRENT` (teal
`#0e7c86`), `SERIES_PRIOR` (`#9db1ba`), `SERIES_BUDGET` (`#c96f12`) — and a role
keeps its colour wherever it appears. Gains and losses use `GOOD_INK`
(`#17924f`) and `BAD_INK` (`#d03b3b`).

Against the pale page the first and last colours clear 4.5:1, and the middle four
sit at 2 to 3:1. That is why a chart either labels its values or has a table
beside it, never neither.

Supporting ink:

| Name | Value | For |
|---|---|---|
| `INK` | `#16262e` | Labels on or beside data |
| `MUTED_INK` | `#6b7b83` | Axis labels, annotations, bar values |
| `GRID_INK` @ `0.18` | `#6b7b83` | Gridlines, on charts that need a value axis |

## Charts

- Build ranked bars with `ranked_bar`, and render **through `draw_chart`**.
  Never call `st.altair_chart` directly for a static chart: Streamlit stamps
  `autosize: fit` on anything asked to stretch, which throws away the declared
  height on the second paint. `draw_chart` sets `fit-x` instead.
- One series means one hue and no legend — the axis names every bar.
- A legend lists only what is on the chart in front of the reader.

### Bar charts

The reference is `ranked_bar_chart` in `sales_lib.py`. Every bar chart, clickable or not, looks like this:

- **The value sits at the end of every bar**, shortened to three figures and a
  K, M or B (`$70.1M`), in `MUTED_INK`, `dx=6`. The tooltip has the exact
  figure.
- **No value axis and no gridlines.** `axis=None` on the value channel. With
  the number on the bar, an axis is a second, vaguer way to read it.
- The category axis shows labels only: no title, no domain line, no ticks.
- The value scale runs to 1.2× the longest bar, `nice=False`, so the longest
  label fits.
- Horizontal, largest first unless the categories have their own order (age
  bands), rounded on the leading end (`cornerRadiusEnd=3`).
- Clickable bars keep their labels and get a pointer cursor. A click dims the
  other bars to 0.3.

`grid_axis` is for line charts and other charts that need a value axis, not
for bars.

## The filter bar

The page title and every header control share one row built with
`st.container(horizontal=True, vertical_alignment="bottom", gap="small")`, not
`st.columns`. Inside it:

- Button groups (`segmented_control`, `pills`), buttons and the filter popover
  take `width="content"`, so every option shows in full.
- A selectbox or date input takes a fixed pixel width (Period is 170) so its
  value is not cut short.
- The filter popover comes last, so it ends the row on every page.

Fixed column widths clipped options and squeezed controls into each other on
a laptop screen. The flex row wraps a control that does not fit onto a second
line instead. The reference is `render_filter_bar` in
`sales_lib.py`. It needs Streamlit 1.63.0; 1.52.2 has no `wrap`.

## Tiles

Headline numbers are `stat_tile`, never a bare `st.metric`. The height is fixed
at `TILE_PIXELS = 116` because Streamlit will draw tiles of different heights
beside each other and it reads as a rendering glitch.

Every tile that could be misread takes a `note=`, which becomes its tooltip.

## Page furniture

- `st.set_page_config(layout="wide")`.
- A title bar under the nav (`show_title_bar` in `crow_dashboard.py`): company
  name, then the dashboard name, on a teal gradient.
- Logo above the nav via `st.logo(lockup, icon_image=icon, size="large")`, and
  it is skipped when the files are missing so a bad `artifacts:` list does not
  stop the app starting.
- **Top navigation**, not the sidebar: `st.navigation(PAGES, position="top")`,
  wrapped in `try/except TypeError` so an older runtime moves the nav bar rather
  than failing to start.
- `PAGE_STYLE` trims the block container padding and puts a border on popovers.
- `lib.remember_page(navigation)` before `navigation.run()`, so queries carry
  the page in their tag.

## Query tagging

Every statement carries a tag built per statement, not set on the session — the
container runtime serves every viewer from one process over one connection, so
an `ALTER SESSION` would race between viewers. Keys are
`env`, `app`, `run`, `obj`, `user`: the environment, the app's name, one id
per viewer session, the page, and the Snowflake user.

Run everything through `run_query`. It builds the tag outside the cached call,
so one viewer's tag does not get frozen into every later caller's statements.

## Things that do not work here

Learned the hard way; don't re-pitch them.

| | |
|---|---|
| `position: sticky` filter bar | Does nothing in Streamlit 1.52.2. Tried and rolled back |
