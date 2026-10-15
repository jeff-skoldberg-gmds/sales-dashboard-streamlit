---
name: streamlit-dashboards
description: "Use for ALL work on the Streamlit dashboards in this project: building a new dashboard, adding a page or a chart to an existing one, anything about how they look or how drilling works. Required entry point: do not write a new app, a new page, a bar chart, a stat tile, a theme file or a drill modal without loading this first. Triggers: new dashboard, new Streamlit app, add a page, add a chart, bar chart, drill, drill-through, drill down, click a bar, modal, dialog, st.dialog, filter chip, scope chip, stat tile, KPI tile, brand colors, theme, config.toml, st.navigation, snowflake.yml artifacts, sales_lib, crow_dashboard. For deploying or restarting an app in Snowflake, load streamlit-in-snowflake instead."
---

# The dashboards

This project is one Streamlit app, **Crooked Crow Pickling Co.** (a fictional
company), and it is the reference for the pattern. Anything built next to it is
meant to look and behave the same. A reader who learns to drill on Sales must not
have to learn it again on another dashboard.

This skill is what keeps that true. Two things are not open for reinvention:

1. **The look** — theme, palette, logo, top nav, tiles, charts. See
   [reference/branding.md](reference/branding.md).
2. **The drill-through** — click a bar, a modal opens, the page underneath is
   already cut to what you clicked, and the modal offers three ways on. See
   [reference/drill-through.md](reference/drill-through.md).

Building a whole new app: [new-dashboard/SKILL.md](new-dashboard/SKILL.md).
Deploying to Snowflake, and making a deployed app pick up new code:
[../streamlit-in-snowflake/SKILL.md](../streamlit-in-snowflake/SKILL.md).

## Where things are

| | |
|---|---|
| `crow_dashboard.py` | Entry point: logo, title bar, top nav |
| `sales_lib.py` | Everything shared: data access, periods, filter bar, charts, drill. The reference for anything chart-shaped |
| `pages/` | Pulse, Customers, Products, Detail, Documentation |
| `scaffold/` | A blank app with the branding and the whole drill already in it |

`sales_lib.py` reads a local DuckDB file here, so its data layer (`run_query`,
`translate`) differs from the Snowflake version the scaffold carries. The charts,
filter bar and drill are the same. An app that ships separately keeps its own
copy of the lib, so **a change to the pattern is a change to every copy**.

## The drill in one paragraph

Every bar chart drills, and so does every table whose rows are one thing each. A
click puts what it picked in force across the whole app as a SQL predicate, and
queues a modal. The modal opens on the next run, over the page it has already
filtered. It says what the thing is worth, what share of the screen it was, and
what it breaks into. It ends with three ways out: **return filtered**, **return
unfiltered**, **see the rows**. Every drill in force shows as an orange chip
under the filter bar, with a cross that drops it. Clicking a bar you already
drilled takes that drill back.

Nothing about a drill is written into a filter widget. Read
[reference/drill-through.md](reference/drill-through.md) before you touch any of
it — there are four Streamlit behaviours that will each cost you an afternoon.

## Filters and drills in the URL

Every filter widget carries `bind="query-params"` alongside its `key=`. That
turns a filtered page into a link: copy it out of the address bar and it
reproduces whatever filters are set, and a reader can save one as a bookmark
instead of re-clicking the same filters every visit. A filter left at its
default drops out of the URL, keeping it clean for readers who never touch it.

Skip it on a widget whose `format_func` label is not stable. Binding stores
the *formatted* value in the URL, not the raw one, so a filter whose option
labels carry a total that moves with the measure toggle would break a saved
link once the total changed. Plain multiselects and segmented controls, with no
`format_func`, don't have this problem.

The drills in force ride along too, but by hand rather than through `bind` —
a drill lives in `SCOPE_STACK`, not a widget, so there is nothing for `bind`
to attach to. `page_header` seeds the stack from the URL once per session and
writes it back after the chips are drawn, in `_seed_scope_from_query_params`
and `_sync_scope_to_query_params`. A drill built from `scopes=` (several
overlapping flags, one predicate each) is left out of the URL on purpose: its
predicate belongs to the page that clicked it, not to the library, so there
is no generic way to rebuild it from a link on a later visit. A plain
column/value drill round-trips fully.

## Checklist for any dashboard change

- [ ] `.streamlit/config.toml` matches the theme in branding.md
- [ ] Charts use `ranked_bar` and render through `draw_chart`
- [ ] Every bar has its value at its end, with no value axis and no gridlines, clickable ones included (see branding.md, *Bar charts*)
- [ ] Headline numbers use `stat_tile`, never a bare `st.metric`
- [ ] Every bar chart and every aggregate table is drillable
- [ ] The modal offers all three ways out
- [ ] Drills show as chips and each chip drops only itself
- [ ] The Detail page calls `apply_pending_measure()` first and `back_button()` after the header
- [ ] The filter bar is one wrapping row: `st.container(horizontal=True)`, controls at `width="content"`, never `st.columns` (see branding.md, *The filter bar*)
- [ ] Every filter widget carries `bind="query-params"` (skip one whose `format_func` label can change)
- [ ] `page_header` seeds and syncs the drill stack against the URL (skip a `scopes=` drill)
- [ ] Every new file is listed under `artifacts:` in `snowflake.yml`
- [ ] No `uv.lock` beside an app that deploys to Snowflake

## Running one

Locally, from the project folder:

```bash
cd /home/me/sales-demo-dashboard
uv run streamlit run crow_dashboard.py
```

An app that reads Snowflake needs `ANALYTICS_DATABASE` (and `ANALYTICS_SCHEMA`
if it reads a personal schema) set first, and refuses to start rather than guess
which database to read.

Deploying, the compute pool, and who can see each app:
[../streamlit-in-snowflake/SKILL.md](../streamlit-in-snowflake/SKILL.md).
