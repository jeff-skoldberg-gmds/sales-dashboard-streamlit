# Crooked Crow Pickling Co. sales demo

A copy of a real sales dashboard, rebranded for a fictional pickle and
ferments maker and running on DuckDB. Every name and number is invented.

## Run

```bash
cd /home/me/sales-demo-dashboard
uv run streamlit run crow_dashboard.py
```

## Rebuild the data

`make_data.py` writes `data/crooked_crow.duckdb` (about 500k invoice lines, 280
customers, 85 items). It ends two days before today, so run it again before a
demo to keep the periods fresh. `make_logo.py` redraws the logo.

## The company

- **Crooked Crow**: dill, sweet and snack pickles, pickled vegetables, gift sets.
- **Crow's Nest Ferments**: sauerkraut, kimchi, fermented hot sauce (chilled).
- **Murder of Crows**: gallon and pail foodservice packs.
- **Store brand**: a few pickles, kraut and onions under grocers' own labels.

## Stories planted in the data

- Pinecone Markets opens 16 stores from March 2025, and Lantern Foods is a new
  chain from June 2025. Summit Warehouse Club is a new club win from May 2025.
- Kettle & Cart delists Crooked Crow sweet pickles in February 2026.
- Harvest Moon Grocers closes six stores in March 2026, and five independents
  go quiet through the summer. Customers > Quiet accounts lists them.
- Price rises in January 2024 and 2025, and May 2026 (pickles and foodservice).
- Ghost Pepper Dill Spears launch August 2025, Carolina Reaper Hot Sauce in
  May 2026, and Sweet Relish is retired in June 2025.
- Pickles peak in summer, ferments in January, gift sets from October.

## What changed from the Cabot app

Only the data layer in `sales_lib.py` (`run_query`, `translate`, the filter
option query), the theme, the logo, and the wording. The charts, drilling and
filter bar are untouched.
