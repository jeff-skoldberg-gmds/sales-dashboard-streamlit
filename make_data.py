"""Build the Crooked Crow Pickling Co. demo database (data/crooked_crow.duckdb).

Everything is invented. The shape matches the real sales mart so the dashboard
runs unchanged, and a handful of stories are planted so the demo has something
to find: new chain and club wins, a delisting, price rises, customers going quiet.
Run again any time; the data ends two days before today so periods stay fresh.

    uv run python make_data.py
"""

import datetime as dt
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "data" / "crooked_crow.duckdb"
START = dt.date(2023, 1, 2)
END = dt.date.today() - dt.timedelta(days=2)
SEED = 7

# (brand, class, category, group code, group name, temp, price per oz, pack list, products)
# A pack is (jars per case, ounces per jar). A product may be (name, launch, retire).
LINES = [
    ("Crooked Crow", "Pickles", "Dill Pickles", 101, "Dill Spears & Chips", "Ambient", 0.085,
     [(12, 24), (12, 32), (6, 46)],
     ["Kosher Dill Spears", "Kosher Dill Chips", "Garlic Dill Spears", "Hot Dill Spears",
      "Hot Dill Chips", "Whole Kosher Dills",
      ("Ghost Pepper Dill Spears", "2025-08-18", None)]),
    ("Crooked Crow", "Pickles", "Sweet Pickles", 102, "Sweet & Bread-and-Butter", "Ambient", 0.095,
     [(12, 16), (12, 24)],
     ["Bread & Butter Chips", "Candied Sweet Chips", "Sweet Heat Chips", "Sweet Gherkins",
      ("Sweet Relish", None, "2025-06-30")]),
    ("Crooked Crow", "Pickled Vegetables", "Pickled Vegetables", 103, "Pickled Vegetables",
     "Ambient", 0.14, [(12, 16), (12, 24)],
     ["Pickled Red Onions", "Sliced Pickled Jalapenos", "Dilly Beans", "Pickled Beets",
      "Hot Giardiniera", "Pickled Okra"]),
    ("Crooked Crow", "Pickles", "Snack Pickles", 104, "Pickle Pouches", "Ambient", 0.30,
     [(24, 4)], ["Big Dill Pouch", "Hot Dill Pouch", "Sweet Pickle Pouch"]),
    ("Crooked Crow", "Gift Sets", "Gift Sets", 105, "Gift Sets", "Ambient", 0.20,
     [(6, 40)], ["Holiday Pickle Sampler", "Grill Master Gift Set"]),
    ("Crow's Nest Ferments", "Fermented Foods", "Sauerkraut", 201, "Sauerkraut", "Chilled", 0.15,
     [(12, 16), (6, 32)],
     ["Classic Sauerkraut", "Garlic Dill Sauerkraut", "Caraway Sauerkraut",
      "Beet & Ginger Sauerkraut"]),
    ("Crow's Nest Ferments", "Fermented Foods", "Kimchi", 202, "Kimchi", "Chilled", 0.20,
     [(12, 16)], ["Napa Cabbage Kimchi", "Vegan Kimchi", "Radish Kimchi", "Spicy Kimchi"]),
    ("Crow's Nest Ferments", "Fermented Foods", "Fermented Hot Sauce", 203, "Fermented Hot Sauce",
     "Ambient", 0.45, [(12, 5), (12, 10)],
     ["Red Jalapeno Hot Sauce", "Habanero Mango Hot Sauce", "Smoked Serrano Hot Sauce",
      ("Carolina Reaper Hot Sauce", "2026-05-04", None)]),
    ("Murder of Crows", "Foodservice", "Burger Chips", 301, "Burger Chips & Slices", "Ambient",
     0.045, [(4, 128), (1, 640)],
     ["Crinkle Burger Chips", "Hot Burger Chips", "Sandwich Stackers", "Bread & Butter Burger Chips"]),
    ("Murder of Crows", "Foodservice", "Peppers & Onions", 302, "Sliced Peppers & Onions",
     "Ambient", 0.07, [(4, 128)],
     ["Sliced Jalapenos", "Sliced Banana Peppers", "Pickled Red Onion Slices", "Pepperoncini"]),
]
PRIVATE_LABEL = [
    ("Dill Pickles", "Kosher Dill Spears", (12, 24)), ("Dill Pickles", "Kosher Dill Chips", (12, 32)),
    ("Sweet Pickles", "Bread & Butter Chips", (12, 24)), ("Sauerkraut", "Classic Sauerkraut", (12, 16)),
    ("Pickled Vegetables", "Pickled Red Onions", (12, 16)),
]
CLASS_ORDER = {
    "Pickles": 1, "Pickled Vegetables": 2, "Fermented Foods": 3, "Foodservice": 4, "Gift Sets": 5,
}
BRAND_GROWTH = {
    "Crooked Crow": 0.05, "Crow's Nest Ferments": 0.18, "Murder of Crows": 0.07,
    "Private Label": 0.12,
}
# Month-by-month demand index per class, January first.
SEASON = {
    "Pickles": [0.85, 0.85, 0.9, 1.0, 1.2, 1.35, 1.4, 1.3, 1.05, 0.95, 0.9, 0.9],
    "Pickled Vegetables": [0.9, 0.9, 0.95, 1.0, 1.1, 1.2, 1.2, 1.15, 1.0, 1.0, 1.0, 1.1],
    "Fermented Foods": [1.15, 1.1, 1.05, 1.0, 0.95, 0.9, 0.9, 0.9, 1.0, 1.05, 1.05, 1.1],
    "Foodservice": [0.85, 0.9, 0.95, 1.05, 1.15, 1.25, 1.3, 1.2, 1.05, 1.0, 0.9, 0.85],
    "Gift Sets": [1.0] * 12,
}
# (date, class, multiplier) price steps.
PRICE_STEPS = [
    ("2024-01-01", None, 1.03), ("2025-01-06", None, 1.04),
    ("2026-05-04", "Pickles", 1.06), ("2026-05-04", "Foodservice", 1.04),
]
SEASONAL_ONLY = {"Holiday Pickle Sampler": (10, 12), "Grill Master Gift Set": (5, 7)}

CLUB_MIN_OUNCES = 270
CONVENIENCE_CATEGORIES = ["Snack Pickles", "Dill Pickles", "Fermented Hot Sauce"]
FOODSERVICE_CLASSES = ["Foodservice", "Pickles", "Pickled Vegetables"]

# (chain, organization, type, stores, company, orders every n weeks, case size, tier price)
CHAINS = [
    ("Pinecone Markets", "Grocery", "Chain Store", 42, "WHS", 1, 3.2, 0.97),
    ("Kettle & Cart", "Grocery", "Chain Store", 30, "WHS", 1, 2.8, 0.98),
    ("Lantern Foods", "Grocery", "Chain Store", 25, "WHS", 1, 2.6, 0.96),
    ("Harvest Moon Grocers", "Grocery", "Chain Store", 18, "DSD", 1, 2.4, 1.00),
    ("Wild Clover Co-op", "Natural & Co-op", "Chain Store", 14, "DSD", 1, 2.2, 1.03),
    ("Daybreak Natural", "Natural & Co-op", "Chain Store", 12, "DSD", 1, 2.0, 1.03),
    ("Ridgeline Club", "Club", "Club Warehouse", 8, "WHS", 1, 9.0, 0.92),
    ("Summit Warehouse Club", "Club", "Club Warehouse", 6, "WHS", 1, 10.0, 0.91),
    ("QuickNest Convenience", "Convenience", "Chain Store", 35, "DSD", 2, 1.4, 1.04),
    ("Tumbleweed Stops", "Convenience", "Chain Store", 20, "DSD", 2, 1.3, 1.05),
    ("Copperpot Catering Supply", "Foodservice", "Foodservice Operator", 10, "WHS", 1, 4.5, 0.95),
    ("Bluebird Cafes", "Foodservice", "Foodservice Operator", 15, "WHS", 2, 2.0, 1.00),
    ("Evergreen Wholesale", "Distributor", "Distributor", 6, "WHS", 1, 14.0, 0.90),
    ("Northstar Distributing", "Distributor", "Distributor", 5, "WHS", 1, 12.0, 0.90),
]
INDEPENDENT_PREFIX = [
    "Mabel's", "Juniper", "Old Mill", "Corner Cupboard", "The Larder", "Tansy", "Birchwood",
    "Sparrow", "Hickory", "Cobblestone", "Sunnyside", "Bluebell", "Quarry Lane", "Foxglove",
    "Granny Smith's", "Peddler's", "Lark & Ladle", "Marrow", "Wren", "Little Acorn",
    "Dandelion", "Harbor Lights", "Pepper Barn", "Hollyhock", "Saltbox", "Thimble", "Barley",
    "Cricket Hill", "Nutmeg", "Rookery",
]
TOWNS = [
    "Maple Ridge", "Fox Hollow", "Lake Alder", "Stone Bridge", "Pine Harbor", "Cedar Falls",
    "Willow Creek", "Red Barn", "Silver Birch", "Elk Meadow", "Copper Hill", "Mill Pond",
    "Gull Point", "Thistle Green", "Oak Landing", "Raven Rock", "Honey Run", "Briar Glen",
    "Plum Valley", "Frost Gap", "Heron Bay", "Larch Field", "Summer Cove", "Otter Bend",
]
REPS = [
    "Marigold Okafor", "Theo Brandvold", "Priya Nandakumar", "Gus Delacroix",
    "Winnie Tran", "Hector Valdivia", "Odette Lindqvist", "Rufus Abernathy",
]
QUIET_STOPS = {  # independent index -> last order date
    3: "2026-06-13", 8: "2026-07-04", 14: "2026-05-23", 19: "2026-08-08", 22: "2026-07-25",
}


def week_ending(day: dt.date) -> dt.date:
    """Return the Saturday that ends the week a date falls in.

    Args:
        day: Any date.

    Returns:
        The Saturday on or after it, the way the real mart defines it.
    """
    iso = day.isoweekday()
    return day + dt.timedelta(days=6 if iso == 7 else 6 - iso)


def build_items() -> pd.DataFrame:
    """Return the item master, one row per sellable pack.

    Returns:
        A frame with every item attribute the reporting view carries, plus the
        helper columns the sales generator needs (price, launch, retire).
    """
    rows = []
    number = 10001
    for brand, klass, category, code, group, temp, per_oz, packs, flavours in LINES:
        for flavour in flavours:
            name, launch, retire = (flavour, None, None) if isinstance(flavour, str) else flavour
            for units, oz in packs:
                rows.append(dict(
                    brand=brand, branded="Branded", product_class=klass, product_category=category,
                    product_group_code=code, product_group_name=group, dairy_deli=temp,
                    flavour=name, units=units, oz=oz, case_price=round(units * oz * per_oz, 2),
                    launch=launch, retire=retire,
                ))
    for category, flavour, (units, oz) in PRIVATE_LABEL:
        base = next(l for l in LINES if l[2] == category or l[4] == category)
        rows.append(dict(
            brand="Private Label", branded="Private Label", product_class=base[1],
            product_category=base[2], product_group_code=base[3], product_group_name=base[4],
            dairy_deli=base[5], flavour=flavour, units=units, oz=oz,
            case_price=round(units * oz * base[6] * 0.82, 2), launch=None, retire=None,
        ))
    items = pd.DataFrame(rows)
    items["item_number"] = range(number, number + len(items))
    items["pack_size"] = items["units"].astype(str) + "/" + items["oz"].astype(str) + " OZ"
    prefix = items["brand"].map(lambda b: "".join(w[0] for w in b.replace("&", "").split()))
    items["item"] = prefix + "-" + items["product_group_code"].astype(str) + "-" + (
        items["item_number"] % 1000
    ).astype(str).str.zfill(3)
    items["item_description"] = (
        items["brand"].where(items["brand"] != "Private Label", "Store Brand") + " "
        + items["flavour"] + " " + items["pack_size"]
    )
    items["product_group"] = items["product_group_code"].astype(str) + " - " + items["product_group_name"]
    items["pl_hierarchy"] = items["product_class"]
    items["pl_sub_hierarchy"] = items["product_category"]
    items["product_class_sort_order"] = items["product_class"].map(CLASS_ORDER)
    items["promoted_product_group_description"] = (
        items["brand"].str.split().str[0] + " " + items["product_category"] + " " + items["oz"].astype(str) + " OZ"
    )
    items["global_item_master_skey"] = items["item_number"] * 7 + 1001
    items["case_lbs"] = items["units"] * items["oz"] / 16
    return items


def build_customers(rng: np.random.Generator) -> pd.DataFrame:
    """Return the customer master, one row per delivery point.

    Args:
        rng: The random generator, so the names and reps repeat run to run.

    Returns:
        A frame of customers with the attributes the reporting view carries and
        the helper columns (cadence, size, price tier, active dates).
    """
    rows = []
    number = 400001
    for chain, org, kind, stores, company, every, size, tier in CHAINS:
        for index in range(stores):
            town = TOWNS[(index * 5 + len(chain)) % len(TOWNS)]
            rows.append(dict(
                customer_number=number, customer_name=f"{chain} #{index + 1:03d} - {town}",
                superchain_customer=chain, customer_type_description=kind, organization=org,
                company=company, every=every, size=size * rng.uniform(0.75, 1.3), tier=tier,
                chain=chain, store=index,
            ))
            number += 1
    for index in range(34):
        name = f"{INDEPENDENT_PREFIX[index % len(INDEPENDENT_PREFIX)]} {['Market', 'Grocer', 'Pantry', 'General Store'][index % 4]}"
        rows.append(dict(
            customer_number=number, customer_name=name, superchain_customer=name,
            customer_type_description="Independent", organization="Independent",
            company="DSD" if index % 3 else "WHS", every=1 if index % 3 == 0 else 2,
            size=rng.uniform(0.7, 1.6), tier=rng.uniform(1.02, 1.08), chain="Independent",
            store=index,
        ))
        number += 1
    customers = pd.DataFrame(rows)
    chains = sorted(customers["chain"].unique())
    rep_for = {c: REPS[i % len(REPS)] for i, c in enumerate(chains)}
    customers["sales_representative"] = customers["chain"].map(rep_for)
    ind = customers["chain"] == "Independent"
    customers.loc[ind, "sales_representative"] = [REPS[i % len(REPS)] for i in range(ind.sum())]
    customers["company_number"] = customers["company"].map({"WHS": 100, "DSD": 200})
    customers["customers_skey"] = customers["customer_number"] * 3 + 17
    customers["start"] = START
    customers["stop"] = None
    customers["dropped_category"] = None
    return customers


def plant_stories(customers: pd.DataFrame) -> pd.DataFrame:
    """Mark the account-level events the demo is meant to surface.

    Args:
        customers: The customer master from build_customers.

    Returns:
        The same frame with start, stop and dropped_category set for the
        stories: Pinecone opens stores, Lantern is a new win, Harvest Moon
        closes some, Kettle & Cart drops sweet pickles, Summit Warehouse Club is a new club win, five independents go quiet.
    """
    c = customers
    pine = c["chain"] == "Pinecone Markets"
    late = pine & (c["store"] >= 26)
    c.loc[late, "start"] = [
        dt.date(2025, 3, 3) + dt.timedelta(days=int(i * 35)) for i in range(late.sum())
    ]
    c.loc[c["chain"] == "Lantern Foods", "start"] = [
        dt.date(2025, 6, 9) + dt.timedelta(days=int(i * 4)) for i in range(25)
    ]
    closing = (c["chain"] == "Harvest Moon Grocers") & (c["store"] >= 12)
    c.loc[closing, "stop"] = dt.date(2026, 3, 14)
    c.loc[c["chain"] == "Kettle & Cart", "dropped_category"] = "Sweet Pickles"
    summit = c["chain"] == "Summit Warehouse Club"
    c.loc[summit, "start"] = [
        dt.date(2025, 5, 5) + dt.timedelta(days=int(i * 14)) for i in range(summit.sum())
    ]
    for index, stop in QUIET_STOPS.items():
        c.loc[(c["chain"] == "Independent") & (c["store"] == index), "stop"] = dt.date.fromisoformat(stop)
    c.loc[(c["chain"] == "Independent") & (c["store"] < 20), "every"] = 1
    return c


def price_index(day: pd.Series, klass: pd.Series) -> np.ndarray:
    """Return the list-price multiplier in force on each row.

    Args:
        day: Delivery dates.
        klass: Product class of each row.

    Returns:
        A float array, 1.0 before the first price step.
    """
    out = np.ones(len(day))
    for when, only, bump in PRICE_STEPS:
        hit = (day >= pd.Timestamp(when)).to_numpy().copy()
        if only:
            hit &= (klass == only).to_numpy()
        out = np.where(hit, out * bump, out)
    return out


def build_sales(items: pd.DataFrame, customers: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Simulate invoice lines for every customer across the whole period.

    Args:
        items: The item master.
        customers: The customer master, stories planted.
        rng: The random generator.

    Returns:
        One row per customer, item and delivery date, with measures filled in.
    """
    frames = []
    item_weight = rng.lognormal(0, 0.7, len(items))
    items = items.assign(weight=item_weight)
    t0 = pd.Timestamp(START)
    for cust in customers.itertuples():
        n_items = int(np.clip(rng.normal(22 if cust.organization != "Independent" else 14, 6), 8, 50))
        if cust.organization in ("Club", "Distributor"):
            pool = items[items["units"] * items["oz"] >= CLUB_MIN_OUNCES]
        elif cust.organization == "Convenience":
            pool = items[items["product_category"].isin(CONVENIENCE_CATEGORIES)]
        elif cust.organization == "Foodservice":
            pool = items[items["product_class"].isin(FOODSERVICE_CLASSES)]
        else:
            pool = items
        pick = rng.choice(
            len(pool), size=min(n_items, len(pool)), replace=False,
            p=(pool["weight"] / pool["weight"].sum()).to_numpy(),
        ) if len(pool) > n_items else np.arange(len(pool))
        carry = pool.iloc[pick]
        first = pd.Timestamp(cust.start)
        last = pd.Timestamp(cust.stop) if cust.stop is not None else pd.Timestamp(END)
        weekday = int(rng.integers(0, 5))
        weeks = pd.date_range(max(first, t0).normalize(), last, freq="7D")
        weeks = weeks[(np.arange(len(weeks)) % cust.every) == 0]
        skip = rng.random(len(weeks)) < 0.06
        days = (weeks[~skip] + pd.to_timedelta((weekday - weeks[~skip].weekday) % 7, unit="D"))
        days = days[(days <= last) & (days <= pd.Timestamp(END))]
        if len(days) == 0:
            continue
        grid = pd.MultiIndex.from_product([days, carry["item_number"]], names=["delivery_date", "item_number"]).to_frame(index=False)
        grid = grid.merge(items, on="item_number")
        buy_p = rng.uniform(0.45, 0.9, len(carry))
        grid["p"] = grid["item_number"].map(dict(zip(carry["item_number"], buy_p)))
        if cust.dropped_category:
            gone = (grid["product_category"] == cust.dropped_category) & (grid["brand"] == "Crooked Crow")
            grid = grid[~(gone & (grid["delivery_date"] >= pd.Timestamp("2026-02-02")))]
        grid = grid[rng.random(len(grid)) < grid["p"].to_numpy()]
        grid = grid[(grid["launch"].isna()) | (grid["delivery_date"] >= pd.to_datetime(grid["launch"]))]
        grid = grid[(grid["retire"].isna()) | (grid["delivery_date"] <= pd.to_datetime(grid["retire"]))]
        month = grid["delivery_date"].dt.month
        for flavour, (m1, m2) in SEASONAL_ONLY.items():
            mask = grid["flavour"] == flavour
            inside = (month >= m1) & (month <= m2) if m1 <= m2 else (month >= m1) | (month <= m2)
            grid = grid[~(mask & ~inside)]
            month = grid["delivery_date"].dt.month
        if grid.empty:
            continue
        years = (grid["delivery_date"] - t0).dt.days / 365.25
        growth = np.exp(grid["brand"].map(BRAND_GROWTH).to_numpy() * years.to_numpy())
        season = np.array([SEASON[k][m - 1] for k, m in zip(grid["product_class"], grid["delivery_date"].dt.month)])
        ramp = np.where(
            (grid["delivery_date"] - first).dt.days.to_numpy() < 56,
            0.5 + (grid["delivery_date"] - first).dt.days.to_numpy() / 112, 1.0,
        ) if first > t0 else 1.0
        mean_cases = cust.size * growth * season * ramp * grid["weight"].to_numpy() ** 0.35
        cases = np.maximum(1, np.round(rng.gamma(2.5, mean_cases / 2.5))).astype(int)
        promo = np.where(rng.random(len(grid)) < 0.07, rng.uniform(0.08, 0.15, len(grid)), 0.0)
        price = (
            grid["case_price"].to_numpy() * price_index(grid["delivery_date"], grid["product_class"])
            * cust.tier * rng.normal(1, 0.012, len(grid)) * (1 - promo)
        )
        frame = pd.DataFrame({
            "customers_skey": cust.customers_skey, "customer_number": cust.customer_number,
            "delivery_date": grid["delivery_date"].dt.date.to_numpy(),
            "item_number": grid["item_number"].to_numpy(),
            "cases": cases, "price": price,
        })
        frames.append(frame)
    sales = pd.concat(frames, ignore_index=True)
    sales["invoiced_dollars"] = (sales["cases"] * sales["price"]).round(2)
    return sales.drop(columns="price")


def finish_sales(sales: pd.DataFrame, items: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Join the dimensions on and add the derived columns of the real view.

    Args:
        sales: Output of build_sales.
        items: The item master.
        customers: The customer master.

    Returns:
        A frame whose columns match rpt_sales_filtered.
    """
    item_cols = [
        "item_number", "global_item_master_skey", "item", "item_description", "product_class",
        "product_class_sort_order", "product_category", "product_group_code", "product_group",
        "brand", "branded", "pl_hierarchy", "pl_sub_hierarchy", "pack_size", "dairy_deli",
        "promoted_product_group_description", "units", "case_lbs",
    ]
    cust_cols = [
        "customer_number", "customer_name", "superchain_customer", "customer_type_description",
        "organization", "sales_representative", "company", "company_number",
    ]
    df = sales.merge(items[item_cols], on="item_number").merge(customers[cust_cols], on="customer_number")
    day = pd.to_datetime(df["delivery_date"])
    df["delivery_date"] = day.dt.date
    df["delivery_year"] = day.dt.year
    df["delivery_month"] = day.dt.month
    df["delivery_month_name"] = day.dt.strftime("%B")
    df["delivery_week_ending"] = [week_ending(d) for d in df["delivery_date"]]
    df["customers_skey"] = df["customer_number"] * 3 + 17
    df["sales_details_skey"] = np.arange(1, len(df) + 1)
    df["sales_headers_skey"] = pd.factorize(df["customer_number"].astype(str) + df["delivery_date"].astype(str))[0] + 1
    df["case_quantity"] = df["cases"].astype(float)
    df["unit_quantity"] = df["cases"] * df["units"]
    df["pounds"] = (df["cases"] * df["case_lbs"]).round(2)
    df["pounds_priced"] = df["pounds"]
    df["kilograms"] = df["pounds"] * 0.45359237
    for flag in (
        "is_invoiced", "is_saleable_item", "is_reportable_customer_type", "is_reportable_organization",
        "is_food_item", "is_reportable_product_group", "is_reportable_company", "is_reportable",
    ):
        df[flag] = True
    return df.drop(columns=["cases", "units", "case_lbs"]).sort_values(["delivery_date", "customer_number", "item_number"])


def build_budget(sales: pd.DataFrame, items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Derive a monthly budget and its weekly allocation from past sales.

    Each budget line is the same customer and item a year earlier plus a plan
    growth rate, so it tracks the business without matching it. Months past
    the end of the data are budgeted from the year before.

    Args:
        sales: The finished sales frame.
        items: The item master.

    Returns:
        A tuple of (monthly budget, weekly budget) frames.
    """
    base = sales.assign(month=pd.to_datetime(sales["delivery_date"]).dt.to_period("M").dt.to_timestamp())
    keys = [c for c in sales.columns if c in (
        "customers_skey", "customer_number", "customer_name", "superchain_customer",
        "customer_type_description", "organization", "sales_representative", "company", "company_number",
        "global_item_master_skey", "item_number", "item", "item_description", "product_class",
        "product_class_sort_order", "product_category", "product_group_code", "product_group", "brand",
        "branded", "pl_hierarchy", "pl_sub_hierarchy", "pack_size", "dairy_deli",
        "promoted_product_group_description",
    )]
    monthly = base.groupby(keys + ["month"], as_index=False)[["invoiced_dollars", "pounds"]].sum()
    shifted = monthly.assign(month=monthly["month"] + pd.DateOffset(years=1))
    shifted = shifted[shifted["month"].dt.year >= 2024]
    rng = np.random.default_rng(SEED + 1)
    noise = rng.normal(1.05, 0.05, len(shifted))
    shifted["budget_dollars"] = (shifted["invoiced_dollars"] * noise).round(2)
    shifted["budget_pounds"] = (shifted["pounds"] * noise).round(2)
    shifted = shifted[shifted["month"] <= pd.Timestamp(dt.date(END.year, 12, 1))]
    shifted = shifted[shifted["budget_dollars"] > 0].drop(columns=["invoiced_dollars", "pounds"])
    shifted = shifted.rename(columns={"month": "budget_month"})
    shifted["delivery_year"] = shifted["budget_month"].dt.year
    shifted["delivery_month"] = shifted["budget_month"].dt.month
    shifted["delivery_month_name"] = shifted["budget_month"].dt.strftime("%B")
    shifted["budget_month"] = shifted["budget_month"].dt.date
    shifted["is_reportable"] = True

    days = pd.DataFrame({"d": pd.date_range(shifted["budget_month"].min(), dt.date(END.year, 12, 31))})
    days["budget_month"] = days["d"].dt.to_period("M").dt.to_timestamp().dt.date
    days["n"] = days.groupby("budget_month")["d"].transform("size")
    days["delivery_week_ending"] = [week_ending(d.date()) for d in days["d"]]
    per_week = days.groupby(["budget_month", "delivery_week_ending"], as_index=False).agg(days=("d", "size"), n=("n", "first"))
    per_week["share"] = per_week["days"] / per_week["n"]
    weekly = shifted.merge(per_week, on="budget_month")
    weekly["budget_dollars"] = weekly["budget_dollars"] * weekly["share"]
    weekly["budget_pounds"] = weekly["budget_pounds"] * weekly["share"]
    weekly = weekly.drop(columns=["days", "n", "share"])
    return shifted, weekly


def write(frames: dict[str, pd.DataFrame]) -> None:
    """Write each frame to the DuckDB file, replacing what was there.

    Args:
        frames: Table name to frame.
    """
    OUT.parent.mkdir(exist_ok=True)
    OUT.unlink(missing_ok=True)
    con = duckdb.connect(str(OUT))
    for name, frame in frames.items():
        con.register("src", frame)
        con.execute(f"create table {name} as select * from src")
        con.unregister("src")
    con.close()


def main() -> None:
    """Generate the data and write the database."""
    rng = np.random.default_rng(SEED)
    items = build_items()
    customers = plant_stories(build_customers(rng))
    sales = finish_sales(build_sales(items, customers, rng), items, customers)
    monthly, weekly = build_budget(sales, items)
    write({"rpt_sales_filtered": sales, "rpt_budget_filtered": monthly, "rpt_budget_weekly": weekly})
    print(f"{len(items)} items, {len(customers)} customers, {len(sales):,} sales rows")
    print(f"data {sales['delivery_date'].min()} to {sales['delivery_date'].max()}")
    print(f"last 52 weeks ${sales[sales['delivery_date'] > END - dt.timedelta(days=364)]['invoiced_dollars'].sum():,.0f}")
    print(f"budget rows {len(monthly):,} monthly, {len(weekly):,} weekly")


if __name__ == "__main__":
    main()
