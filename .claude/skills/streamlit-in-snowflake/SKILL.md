---
name: streamlit-in-snowflake
description: "Use for deploying a Streamlit app to Snowflake, getting a deployed app to pick up new code (the restart, or bounce), first-deploy setup, who can see an app, cost of the compute pool, and testing a dashboard headlessly. Required entry point: do not hand-write snow streamlit flags, ALTER STREAMLIT statements or a restart procedure without loading this first. Triggers: snow streamlit deploy, deploy the dashboard, bounce, restart the app, app shows old code, MAIN_FILE, container runtime, ARTIFACT_REPOSITORIES, SYSTEM_COMPUTE_POOL_CPU, uv.lock, owner's rights, GRANT USAGE ON STREAMLIT, AppTest, headless test."
---

# Streamlit in Snowflake

Placeholders used below: `<conn>` your Snowflake CLI connection, `<ROLE>` the role
that owns the app, `<DB>` the database it lives in, `<APP>` the app's name.
Deploy only when asked.

## Deploy

From the app's own folder, so its `snowflake.yml` is found:

```bash
snow streamlit deploy -c <conn> --role <ROLE> --env database=<DB> --replace --prune
```

`--replace` overwrites the app. `--prune` removes stage files that no longer
exist locally, and without it a deleted page keeps being served. The build
bundle goes to `output/` beside the app; keep it out of git.

Get the link to hand out. `get-url` takes the fully qualified name, not the
`snowflake.yml` entity id. The entity id silently resolves against your default
database and gives you a URL for an app that does not exist.

```bash
snow streamlit get-url <DB>.STREAMLIT.<APP> -c <conn>
```

**Every file the app needs at runtime must be listed under `artifacts:`** in
`snowflake.yml`, including `pyproject.toml`, `.streamlit/config.toml` and the
images. An unlisted file is simply not there when the app starts.

## A deploy does not restart the app

On the container runtime, `snow streamlit deploy` replaces files on the stage and
nothing else. The running process keeps its old code and its old theme. This
applies to `.py` files, not just `config.toml`, and an imported module such as
`sales_lib.py` stays cached until the process is replaced. **Deploy, then bounce,
whatever changed.**

Point the app at another file and straight back, both statements in one call so
the entrypoint is wrong only for the moment between them:

```bash
snow sql -c <conn> --role <ROLE> -q "
ALTER STREAMLIT <DB>.STREAMLIT.<APP> SET MAIN_FILE = 'pages/<any other page>.py';
ALTER STREAMLIT <DB>.STREAMLIT.<APP> SET MAIN_FILE = '<entry file>.py';"
```

The app is down about a minute. `503 no healthy upstream` while that happens is
the restart, not a fault.

Why this works: the container watches the app's metadata, not its files, and a
deploy leaves the metadata unchanged. Changing `MAIN_FILE` is a change it can see.

These do **not** restart it: a redeploy, editing `pyproject.toml`, a hard browser
refresh, and `ALTER SERVICE ... SUSPEND` (the service is system-managed and no
role holds `OPERATE` on it, ACCOUNTADMIN included).

### Prove it landed

Do not conclude from the stage contents, and do not trust `updated_on` on the
service, which also moves for a plain deploy. Two checks settle it.

The container must have started after the stage write, with no restarts:

```bash
snow sql -c <conn> --role <ROLE> -q "SHOW SERVICES IN COMPUTE POOL SYSTEM_COMPUTE_POOL_CPU;"
snow sql -c <conn> --role <ROLE> -q "SHOW SERVICE CONTAINERS IN SERVICE <DB>.STREAMLIT.<service>;"
```

Apps run as services named `STPLATSTREAMLIT...`. A `READY` container whose
`start_time` is after the deploy, with `restart_count` 0, read the new files.

Then prove it from the app's own SQL. Grep the query history for a string only
the new code emits:

```sql
SELECT START_TIME, LEFT(QUERY_TEXT, 120)
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME > DATEADD(hour, -3, CURRENT_TIMESTAMP())
  AND USER_NAME ILIKE 'STPLAT%'
  AND QUERY_TEXT ILIKE '%<something only the new code says>%'
ORDER BY START_TIME DESC;
```

`ACCOUNT_USAGE` lags by up to 45 minutes, so for a quick answer rely on the
container start time and open the app.

### The local server

Running `uv run streamlit run <app>.py` on a laptop reloads `.py` changes when you
rerun from the browser, but it reads `.streamlit/config.toml` only at startup. A
theme change needs the server stopped and started again.

## First deploy

```bash
snow sql -c <conn> --role <ROLE> -q "CREATE SCHEMA IF NOT EXISTS <DB>.STREAMLIT;"
snow streamlit deploy -c <conn> --role <ROLE> --env database=<DB>
```

The container has no route to public PyPI, so an app that names package versions
needs Snowflake's mirror attached, once per app. It cannot be written in
`snowflake.yml`, and it only works once the app is on the container runtime:

```bash
snow sql -c <conn> --role <ROLE> -q "ALTER STREAMLIT <DB>.STREAMLIT.<APP> SET
  ARTIFACT_REPOSITORIES = (snowflake.snowpark.pypi_shared_repository);"
```

Setting it on a warehouse-runtime app fails with `ARTIFACT_REPOSITORIES are only
supported by Streamlit applications running in the container runtime`. So a first
deploy builds a container that cannot install its pins. Expect that first build
to fail, attach the repository, and deploy again. Nothing is broken in between.

Moving an existing warehouse-runtime app is tidier, because it is one statement:

```bash
snow sql -c <conn> --role <ROLE> -q "ALTER STREAMLIT <DB>.STREAMLIT.<APP> SET
  RUNTIME_NAME = 'SYSTEM\$ST_CONTAINER_RUNTIME_PY3_11'
  COMPUTE_POOL = SYSTEM_COMPUTE_POOL_CPU
  ARTIFACT_REPOSITORIES = (snowflake.snowpark.pypi_shared_repository);"
```

## Pin the Streamlit version, and never ship a uv.lock

An app that names no Streamlit version gets whatever the runtime shipped with,
which can be years old and can predate keywords your laptop has. Pin it exactly
in `pyproject.toml` (`streamlit[snowflake]==<version>`; the extra pulls in
Snowpark). The container runtime is Python 3.11 only.

**Do not ship a `uv.lock`.** A lock written on a laptop records public PyPI as the
source of every wheel, uv prefers that to the attached repository, and the
container dies trying to reach a CDN it has no route to:

```
Failed to retrieve packages from the package server. Have you enabled External
Access Integration (EAI)? ... failed to lookup address information: Name does
not resolve
```

The hint about an EAI is a red herring. Keep `uv.lock` out of `artifacts:` and
out of the deployed folder. A dependency change takes effect only when the
container is rebuilt, so give a redeploy a few minutes before judging it.

## Who can see the app, and what it can read

Streamlit in Snowflake runs with **owner's rights**. Queries run as the role that
deployed the app, not as the viewer, and **with no secondary roles**. So:

- A viewer needs `USAGE` on the app and nothing on the tables underneath:
  `GRANT USAGE ON STREAMLIT <DB>.STREAMLIT.<APP> TO ROLE <VIEWER_ROLE>;`
- The owner role must be able to read the data on its own. A role that reads a
  table fine at a terminal, through a secondary role, cannot read it from inside
  the app. Reproduce what the app sees with `USE SECONDARY ROLES NONE;`.
- **An app deployed under the wrong role must be dropped and redeployed.**
  `GRANT OWNERSHIP ON STREAMLIT` is not supported, and `--replace` updates in
  place and keeps the old owner, reporting success while changing nothing.
  Redeploying under the same name gives back the same URL.

## Renaming an app

A rename changes the app's URL, which carries the object name. The `url_id` form
of the link follows the object, so only that form survives. A rename and a
redeploy also leave `MAIN_FILE` as it was, so the app can point at a file the
deploy removed. Check it after any rename:

```bash
snow sql -c <conn> --role <ROLE> -q "ALTER STREAMLIT <DB>.STREAMLIT.<APP>
  SET MAIN_FILE = '<entry file>.py';"
```

## What it costs

Container-runtime apps run on a compute pool node, about three apps to a node,
and the queries still run on the app's `query_warehouse`. A fourth app starts a
second node and doubles the line, so check `SHOW STREAMLITS IN ACCOUNT` against
`SHOW COMPUTE POOLS` before adding one.

Snowflake documents that an idle app shuts down after three days. **In the
account this skill came from, it did not.** The service ran at its full rate for
weeks with no viewer, and the pool could not suspend because a service was still
on it. Check yours with `SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` before
trusting the timer. The fix that worked was suspending the pool on a schedule
(for example a task running `ALTER COMPUTE POOL <pool> SUSPEND` each evening),
which stops every node on it. A suspended app comes back when a real viewer
opens it; resuming the pool or toggling `MAIN_FILE` does not start it.

## Testing headlessly

`streamlit.testing.v1.AppTest` runs a page without a browser, which is the only
route when no browser can launch. Run it from the app's folder with the app's own
pins, so it tests the Streamlit version the account runs:

```bash
uv run python <harness>.py
```

- Run each page file directly: `AppTest.from_file("pages/<page>.py")`. There is
  no need to go through `st.navigation`. Running a page directly skips the entry
  file, so anything it sets (the page name in the query tag) will be missing.
- `AppTest` does not put the app folder on `sys.path` the way `streamlit run`
  does. Add `sys.path.insert(0, os.getcwd())` first, or the page's
  `import <app>_lib` fails.
- Drive widgets with `.set_value(...)` or `.select(...)` then `.run()`. A sweep
  over every period and measure on every page is cheap and finds real bugs.
- `st.switch_page` raises `Could not find page` under a page-level run. That is
  an artifact of the test, not a defect.
- **Instances in one process share state.** A drill applied in one `AppTest` can
  show up as a wrong figure in the next. Run a scenario in its own process when a
  number matters, and doubt a surprising figure from a multi-case harness.
- To control the data, stand DuckDB in for Snowflake. This project already does:
  `translate` and `MACROS` in `sales_lib.py` rewrite the few Snowflake-only calls
  (`iff`, `dateadd`, `datediff`, `date_from_parts`, `array_agg`).
- A dialog cannot write `st.session_state[k]` when the widget keyed `k` was drawn
  earlier in the same run. Queue the value under another key and apply it at the
  top of the next run, before any widget exists.
- Streamlit 1.52.2's `AppTest` had two bugs: `Multiselect.indices` and
  `ButtonGroup.indices` raised `ValueError`, and a button inside `st.dialog` got
  a full rerun that dropped the queued dialog. Neither showed up on 1.63.0.
  Recheck on the version you pin.
