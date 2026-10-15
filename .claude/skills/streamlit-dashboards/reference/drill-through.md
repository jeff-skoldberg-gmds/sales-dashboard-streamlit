# The drill-through

One design, three implementations. Read this before changing any of them.

## What the reader gets

1. **Every bar chart drills.** So does every table whose rows are one thing
   each. A list of individual records does not — that is where a drill ends.
2. **A click cuts the whole app**, not just the chart. Every page ANDs the pick
   on. Nothing navigates away, so the reader never loses the page they were on.
3. **A modal opens over the page it has already filtered.** It shows the one
   thing clicked: its total, its share of what was on screen, and what it breaks
   down into.
4. **The modal offers three ways on**, and this is the part that is easiest to
   leave half-built:
   - *Return to Overview, filtered on Pinecone Markets* — keeps the drill.
   - *Return to Overview, unfiltered* — drops it. If other drills are still in
     force it names them instead: *filtered on 1-2 years*.
   - *See the rows* — carries the whole scope to the Detail page.

   The cross in the corner does what the first one does.
5. **Drills stack, and every one shows as a chip** under the filter bar, with a
   cross that drops only itself. *Clear all* appears past one.
6. **Clicking a bar you already drilled takes that drill back.** The same bar
   applies and clears.
7. **The Detail page offers a way back** to the page the drill came from.

Buttons name the state they return in, not the action they take. "Keep" and
"drop" mean nothing until you already know a click filtered the page.

## The one rule

**A drill travels as a SQL predicate. It is never written into a filter
widget.**

Writing a widget's state is only legal before that widget has been drawn, and a
drill taken on the page that owns those widgets cannot promise that ordering —
it raises `StreamlitAPIException`. A predicate has no ordering problem: every
page ANDs it on, shows it as a chip, and a click on the chip drops it.

The exception is a per-page control the Detail page owns its own copy of — the
measure, and any checkbox that only the Detail page uses. Those are handed over in session
state and written by the destination page **before it draws anything**
(`apply_pending_measure()` on the first line). A reader who drills from a
dollars chart and lands on a pounds page has been shown a different number than
the one they clicked.

## The shape

```
page_header(title, name=...)
  ├─ record the page name          (so Detail can offer a way back)
  ├─ open_pending_drill()          ← the modal a click queued, opened FIRST
  ├─ draw the filter bar
  ├─ scope_chips()
  └─ return a Drill                (page filters AND every drill in force)

drillable_chart(rows, "CUSTOMER_NAME", drill, name="overview_customer")
  └─ on click → apply_click(drill, bar_level(...), column)
        ├─ already drilled? drop_scope() and stop
        ├─ else push_scope() and queue DRILL_PENDING
        ├─ clear_selections()
        └─ st.rerun()              ← the modal opens on the NEXT run

drill_body(chart, scoped, column, value, level_key)
  ├─ return_options(level_key)     ← the two ways home, at the top
  ├─ tiles: the figure, its share of `chart`
  ├─ a breakdown from SPLIT_BY[column]
  └─ "See the rows" → open_rows(scoped) → switch_page(Detail)
```

Two `Drill`s travel into the modal. `chart` is what the clicked chart was drawn
under and is the **denominator of the share tile**; `scoped` is that narrowed to
the bar. A chart showing less than its page does — off-grade stock, the next
ninety days — narrows `chart` first, so the modal's numbers reconcile to the bar
rather than to the page.

## The four Streamlit behaviours behind all of it

Each of these is the reason for a line that otherwise looks like superstition.

**1. A chart's selection cannot be cleared from Python.** So `chart_key(name)`
appends an epoch that `clear_selections()` bumps. A new key is a new widget, and
a new widget starts with nothing selected. Without it: returning to a page
re-fires the drill the reader already took, and clicking the same bar twice does
nothing the second time.

**2. Dismissing a dialog does not rerun the app.** So `apply_click` calls
`st.rerun()` itself. The page underneath was drawn unfiltered before the click
arrived; without the rerun it stays wrong until the reader touches something
else.

**3. While a modal is open, Streamlit reruns only the modal.** So the pending
drill is `pop`ped, not read. A later full rerun — a filter moving, the measure
changing — must not bring the modal back.

**4. A dialog's title is fixed when it is decorated.** So `st.dialog(...)` is
applied inside `open_pending_drill()` at call time, not at import. The title
names whatever was clicked.

And one ordering rule: **open the modal before drawing the page under it.** That
page is re-running every one of its queries with the new drill in force. Open
the modal first and it is on screen while they run; open it last and every drill
costs the reader a full page refresh before anything appears.

## Bars that are not a column's values

Some bars are predicates rather than one column's values, such as five
overlapping yes/no flags. `Level` holds a predicate and a key, not a
column and a value, so those sit in the same stack as everything else. Pass the
per-bar predicates as `scopes=` to `bar_level`.

Some bars are labelled with one thing and scoped on another — Cost's Runs page
labels a bar with what the run was while the column holds an opaque id. Pass
`values={label: value}` to `drillable_chart`.

## Where it lives

| | |
|---|---|
| `sales_lib.py` | The reference: `Drill`, `drill_body`, `return_options`, and the chart types (ranked bar, tornado, bridge, bullet) |
| `scaffold/dashboard_lib.py` | The whole thing in one file for a new app |

## When you change it

Change it in all three. They deploy separately and share no package, so nothing
will tell you that one has drifted.
