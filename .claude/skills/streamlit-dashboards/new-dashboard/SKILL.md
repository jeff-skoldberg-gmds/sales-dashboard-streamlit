---
name: new-dashboard
description: Build a new Streamlit dashboard, branded and drilling like the existing one. Loaded by the streamlit-dashboards skill.
---

# Building a new dashboard

Start by copying `../scaffold/`. It is a working app with the branding and the
whole drill-through already in it, and a `FILL THIS IN` block at the top of
`dashboard_lib.py` holding everything one app changes.

## 1. Before you write anything

Answer these. If you cannot, ask.

- **What one relation does it read?** Every dashboard here reads one mart
  relation, and every page reads it through the same lib. If the answer is two,
  the mart is the thing to fix first.
- **What is the measure toggle?** Dollars/cases, dollars/credits. There is
  always one, and it travels with a drill.
- **What is the Detail page?** Every drill has to end somewhere. Name the grain
  of the rows before you build anything that leads to them.
- **Which columns can be drilled, and what does each break down into?** That is
  `DIMENSION_NOUNS` and `SPLIT_BY`.

## 2. Copy and rename

```bash
cp -r /home/me/sales-demo-dashboard/.claude/skills/streamlit-dashboards/scaffold \
      <new-app-folder>
cd <new-app-folder>
mkdir -p .streamlit assets && mv config.toml .streamlit/
# put your logo files at assets/lockup.png and assets/icon.png
mv my_dashboard.py <app>.py && mv dashboard_lib.py <app>_lib.py
```

Then fix the `import dashboard_lib as lib` lines and `main_file` /
`artifacts:` in `snowflake.yml`, and fill in its `<DATABASE>` and `<WAREHOUSE>`.

## 3. Fill in the block

Top of the lib: `APP_NAME`, `RELATION`, `_mart_schema`'s schema name,
`MEASURES`, `PAGE_FILES`, `DIMENSION_NOUNS`, `SPLIT_BY`.

## 4. Write the pages

Every page starts with `lib.page_header(...)` and draws under the `Drill` it
returns. Nothing else may build a WHERE clause.

Order the pages the way the question is asked, not the way the data is shaped.
Detail last but one, Documentation last.

Replace the scaffold's filter bar in `page_header` with whatever this app
filters on. **Keep the order**: record the page, open the modal, draw the
filters, draw the chips, return the Drill.

Give every filter widget `bind="query-params"` next to its `key=`, and call
the scaffold's `_seed_scope_from_query_params()` / `_sync_scope_to_query_params()`
around the drill stack, so a filtered, drilled page is a shareable link — see
the parent skill's *Filters and drills in the URL*.

## 5. The files it needs

| File | Note |
|---|---|
| `<app>.py` | Entry point. Top nav, logo, `remember_page` |
| `<app>_lib.py` | Everything shared. One per app, not a package |
| `pages/*.py` | One per page. `pages/detail.py` is where drills end |
| `pyproject.toml` | Pinned. **Never a `uv.lock` beside it** |
| `.streamlit/config.toml` | The same as the other apps |
| `assets/lockup.png`, `assets/icon.png` | Your logo and its small icon |
| `snowflake.yml` | Every file above listed under `artifacts:` |
| `README.md` | What it answers, what the colours mean, how to drill, how to run it |

**A file not listed under `artifacts:` is simply not there when the app starts.**
That is the single most common way one of these fails on deploy.

Change its dependencies with `uv add` run in its own folder.

## 6. Check it

```bash
cd <new-app-folder>
ANALYTICS_DATABASE=<database> ANALYTICS_SCHEMA=<schema> \
uv run streamlit run <app>.py
```

Then walk the checklist in the parent `SKILL.md`. Click a bar and confirm all
three ways out of the modal work, that the chip appears, and that clicking the
same bar again clears it.

To test without a browser, see *Testing headlessly* in
[../../streamlit-in-snowflake/SKILL.md](../../streamlit-in-snowflake/SKILL.md).
Do not deploy unless asked.
