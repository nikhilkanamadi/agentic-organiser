"""
Local stand-in for the BigQuery analytical backbone (design doc §10.3-A).

Schema mirrors the CURATED zone tables defined in the blueprint
(`agentic_merchandising_os_gcp_bigquery.md` §7): dim_product, dim_store,
fact_sales, fact_inventory — implemented here in SQLite so Phase 1 runs with
zero external services. Swap this module for a `google-cloud-bigquery` backed
adapter in Phase 2 without changing any agent code: agents only ever call the
functions below, never raw SQL.

This is also where the "governed view" principle from blueprint §21 is
enforced: agents cannot run arbitrary SQL against this module — only the
typed read functions below, each with a bounded window and no PII columns.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from tools.contracts import (
    GetInventoryInput,
    GetInventoryOutput,
    InventoryPosition,
    QuerySalesInput,
    QuerySalesOutput,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "synthetic.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_product (
    product_id TEXT PRIMARY KEY,
    brand TEXT,
    category TEXT,
    subcategory TEXT,
    color TEXT,
    cost NUMERIC,
    list_price NUMERIC
);

CREATE TABLE IF NOT EXISTS dim_store (
    store_id TEXT PRIMARY KEY,
    city TEXT,
    state TEXT,
    region TEXT
);

CREATE TABLE IF NOT EXISTS fact_sales (
    transaction_id TEXT PRIMARY KEY,
    sale_date TEXT NOT NULL,
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    channel TEXT,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC NOT NULL,
    discount NUMERIC DEFAULT 0,
    net_sales NUMERIC NOT NULL,
    cost NUMERIC NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fact_sales_product_store_date
    ON fact_sales (product_id, store_id, sale_date);

CREATE TABLE IF NOT EXISTS fact_inventory (
    as_of_date TEXT NOT NULL,
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    on_hand INTEGER NOT NULL,
    reserved INTEGER NOT NULL DEFAULT 0,
    in_transit INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL,
    PRIMARY KEY (as_of_date, store_id, product_id)
);
"""


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def reset() -> None:
    """Drop and recreate all tables -- used by the seed script for a clean reseed."""
    with _connect() as conn:
        conn.executescript(
            """
            DROP TABLE IF EXISTS dim_product;
            DROP TABLE IF EXISTS dim_store;
            DROP TABLE IF EXISTS fact_sales;
            DROP TABLE IF EXISTS fact_inventory;
            """
        )
        conn.commit()
    init_schema()


# ---------------------------------------------------------------------------
# Governed read tools -- the ONLY interface agents are allowed to use.
# ---------------------------------------------------------------------------

def query_sales(inp: QuerySalesInput) -> QuerySalesOutput:
    """
    Demand-velocity query: compares trailing `recent_window_days` units sold
    against the prior `baseline_window_days` average daily rate, scaled to the
    same window length. Mirrors blueprint §22's BigQuery demand-velocity SQL.
    """
    with _connect() as conn:
        latest_row = conn.execute(
            "SELECT MAX(sale_date) AS d FROM fact_sales "
            "WHERE product_id = ? AND store_id = ?",
            (inp.product_id, inp.store_id),
        ).fetchone()
        if latest_row is None or latest_row["d"] is None:
            raise ValueError(
                f"No sales history for product={inp.product_id} store={inp.store_id}"
            )
        latest_date = date.fromisoformat(latest_row["d"])

        recent_start = (latest_date.toordinal() - inp.recent_window_days + 1)
        baseline_start = (latest_date.toordinal() - inp.recent_window_days - inp.baseline_window_days + 1)
        baseline_end = (latest_date.toordinal() - inp.recent_window_days)

        recent = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS units, COALESCE(SUM(net_sales), 0) AS revenue "
            "FROM fact_sales WHERE product_id = ? AND store_id = ? AND sale_date >= ?",
            (inp.product_id, inp.store_id, date.fromordinal(recent_start).isoformat()),
        ).fetchone()

        baseline = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS units FROM fact_sales "
            "WHERE product_id = ? AND store_id = ? AND sale_date >= ? AND sale_date <= ?",
            (
                inp.product_id,
                inp.store_id,
                date.fromordinal(baseline_start).isoformat(),
                date.fromordinal(baseline_end).isoformat(),
            ),
        ).fetchone()

        units_recent = int(recent["units"])
        revenue_recent = float(recent["revenue"])
        baseline_total = float(baseline["units"])
        baseline_avg_scaled = (
            (baseline_total / inp.baseline_window_days) * inp.recent_window_days
            if inp.baseline_window_days > 0
            else 0.0
        )

        demand_change = (
            (units_recent - baseline_avg_scaled) / baseline_avg_scaled
            if baseline_avg_scaled > 0
            else 0.0
        )

        return QuerySalesOutput(
            product_id=inp.product_id,
            store_id=inp.store_id,
            units_recent=units_recent,
            units_baseline_avg=round(baseline_avg_scaled, 2),
            revenue_recent=round(revenue_recent, 2),
            demand_change=round(demand_change, 4),
            data_as_of=latest_date,
        )


def get_inventory(inp: GetInventoryInput) -> GetInventoryOutput:
    with _connect() as conn:
        positions: list[InventoryPosition] = []
        for store_id in inp.store_ids:
            row = conn.execute(
                "SELECT * FROM fact_inventory WHERE product_id = ? AND store_id = ? "
                "ORDER BY as_of_date DESC LIMIT 1",
                (inp.product_id, store_id),
            ).fetchone()
            if row is None:
                continue
            positions.append(
                InventoryPosition(
                    store_id=store_id,
                    on_hand=row["on_hand"],
                    reserved=row["reserved"],
                    in_transit=row["in_transit"],
                    available=row["available"],
                    data_as_of=date.fromisoformat(row["as_of_date"]),
                )
            )
        return GetInventoryOutput(product_id=inp.product_id, positions=positions)


def get_product(product_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM dim_product WHERE product_id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row else None


def all_store_ids(exclude: str | None = None) -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT store_id FROM dim_store").fetchall()
        return [r["store_id"] for r in rows if r["store_id"] != exclude]
