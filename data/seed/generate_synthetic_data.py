"""
Phase 1 synthetic retail dataset generator.

Seeds a small, deterministic dataset into the local analytics store (SQLite,
standing in for BigQuery -- see tools/analytics_store.py) that reproduces the
"Atlanta denim demand spike" scenario used throughout both design docs:

  Product P472 (denim) at store ATL127:
    - 28-day baseline rate: 10 units/day
    - Most recent 7 days: ~14.1 units/day  -> demand_change ~= +41%
    - Inventory at ATL127 is low (near stockout); other stores are well
      stocked -> a transfer is the obvious inventory recommendation.

All other product/store combinations get a flat, unremarkable baseline so the
anomaly detector has true negatives to not fire on.

Run: python -m data.seed.generate_synthetic_data
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from tools.analytics_store import DB_PATH, reset

PRODUCTS = [
    # product_id, brand, category, subcategory, color, cost, list_price
    ("P472", "GapCo", "Bottoms", "Denim", "Indigo", 22.00, 58.00),
    ("P100", "GapCo", "Footwear", "Sneakers", "White", 18.00, 54.00),
    ("P200", "GapCo", "Outerwear", "Jacket", "Black", 35.00, 98.00),
]

STORES = [
    # store_id, city, state, region
    ("ATL127", "Atlanta", "GA", "Southeast"),
    ("NYC045", "New York", "NY", "Northeast"),
    ("CHI089", "Chicago", "IL", "Midwest"),
    ("LAX210", "Los Angeles", "CA", "West"),
    ("SEA150", "Seattle", "WA", "Northwest"),
]

TOTAL_DAYS = 42          # history window generated
BASELINE_DAYS = 28       # matches QuerySalesInput default baseline_window_days
RECENT_DAYS = 7          # matches QuerySalesInput default recent_window_days

HERO_PRODUCT = "P472"
HERO_STORE = "ATL127"
HERO_BASELINE_RATE = 10   # units/day for the 28-day baseline window
HERO_RECENT_UNITS = [14, 14, 14, 14, 14, 14, 15]  # sums to 99 -> ~+41.4%
FLAT_RATE = 6             # units/day for every unremarkable combo


def _insert_sale(conn, txn_id, sale_date, store_id, product_id, qty, unit_price, cost):
    net_sales = round(qty * unit_price, 2)
    total_cost = round(qty * cost, 2)
    conn.execute(
        "INSERT INTO fact_sales "
        "(transaction_id, sale_date, store_id, product_id, channel, quantity, "
        " unit_price, discount, net_sales, cost) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (txn_id, sale_date.isoformat(), store_id, product_id, "store",
         qty, unit_price, 0.0, net_sales, total_cost),
    )


def generate() -> None:
    reset()
    conn = sqlite3.connect(DB_PATH)
    try:
        for p in PRODUCTS:
            conn.execute(
                "INSERT INTO dim_product (product_id, brand, category, subcategory, color, cost, list_price) "
                "VALUES (?,?,?,?,?,?,?)",
                p,
            )
        for s in STORES:
            conn.execute(
                "INSERT INTO dim_store (store_id, city, state, region) VALUES (?,?,?,?)",
                s,
            )

        price_lookup = {p[0]: (p[5], p[6]) for p in PRODUCTS}  # product_id -> (cost, list_price)
        today = date.today()
        txn_seq = 0

        for product_id, _, _, _, _, cost, list_price in PRODUCTS:
            for store_id, *_ in STORES:
                for day_offset in range(TOTAL_DAYS, 0, -1):
                    sale_date = today - timedelta(days=day_offset)
                    days_from_end = day_offset  # 1 = most recent day generated

                    if product_id == HERO_PRODUCT and store_id == HERO_STORE and days_from_end <= RECENT_DAYS:
                        qty = HERO_RECENT_UNITS[RECENT_DAYS - days_from_end]
                    elif product_id == HERO_PRODUCT and store_id == HERO_STORE:
                        qty = HERO_BASELINE_RATE
                    else:
                        qty = FLAT_RATE

                    if qty <= 0:
                        continue
                    txn_seq += 1
                    _insert_sale(
                        conn,
                        f"T{txn_seq:06d}",
                        sale_date,
                        store_id,
                        product_id,
                        qty,
                        list_price,
                        cost,
                    )

        # Inventory snapshot as of "today" (the latest sale date generated = today - 1)
        as_of = (today - timedelta(days=1)).isoformat()
        for product_id, *_ in PRODUCTS:
            for store_id, *_ in STORES:
                if product_id == HERO_PRODUCT and store_id == HERO_STORE:
                    on_hand = 40     # low -- roughly 3 days of coverage at the new demand rate
                elif product_id == HERO_PRODUCT:
                    on_hand = 200    # healthy coverage elsewhere -- transfer candidates
                else:
                    on_hand = 120
                conn.execute(
                    "INSERT INTO fact_inventory "
                    "(as_of_date, store_id, product_id, on_hand, reserved, in_transit, available) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (as_of, store_id, product_id, on_hand, 0, 0, on_hand),
                )

        conn.commit()
        print(f"Seeded {txn_seq} sales transactions and "
              f"{len(PRODUCTS) * len(STORES)} inventory positions into {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    generate()
