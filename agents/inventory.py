"""
Inventory Agent.

Responsibilities (blueprint §10): determine inventory coverage, identify
stockout risk, find transferable inventory, recommend allocation.

Phase 1 allocator (`optimize_allocation`) is a single, deterministic function
so concurrent workflows touching the same product serialize through one
code path -- addresses design-doc edge case EC-4 (two workflows competing
for the same limited inventory). It is not yet lock-protected across
concurrent requests; that's called out explicitly in Phase 1 limitations.
"""

from __future__ import annotations

from agents.reasoning import explain
from tools.analytics_store import all_store_ids, get_inventory, get_product
from tools.contracts import AllocationCandidate, GetInventoryInput

TARGET_COVERAGE_DAYS = 10
MIN_COVERAGE_DAYS_TRIGGER = 5
SOURCE_SAFETY_STOCK = 30  # units a source store must keep for itself


def run(product_id: str, deficit_store_id: str, daily_demand_rate: float) -> dict:
    other_stores = all_store_ids(exclude=deficit_store_id)
    all_positions = get_inventory(
        GetInventoryInput(product_id=product_id, store_ids=[deficit_store_id, *other_stores])
    ).positions
    by_store = {p.store_id: p for p in all_positions}

    deficit_position = by_store.get(deficit_store_id)
    deficit_available = deficit_position.available if deficit_position else 0
    coverage_days = (
        round(deficit_available / daily_demand_rate, 1) if daily_demand_rate > 0 else float("inf")
    )

    stockout_risk = coverage_days < MIN_COVERAGE_DAYS_TRIGGER
    units_needed = 0
    candidates: list[AllocationCandidate] = []
    recommended_transfer_units = 0
    source_store_id = None

    product = get_product(product_id) or {}
    unit_cost = float(product.get("cost", 0))

    if stockout_risk:
        target_available = TARGET_COVERAGE_DAYS * daily_demand_rate
        units_needed = max(0, round(target_available - deficit_available))

        ranked_sources = sorted(
            (p for sid, p in by_store.items() if sid != deficit_store_id),
            key=lambda p: p.available,
            reverse=True,
        )
        for pos in ranked_sources:
            transferable = max(0, pos.available - SOURCE_SAFETY_STOCK)
            if transferable <= 0:
                continue
            candidates.append(
                AllocationCandidate(
                    source_store_id=pos.store_id,
                    units_available_to_transfer=transferable,
                    transfer_value_usd=round(transferable * unit_cost, 2),
                )
            )

        if candidates:
            best = max(candidates, key=lambda c: c.units_available_to_transfer)
            source_store_id = best.source_store_id
            recommended_transfer_units = min(units_needed, best.units_available_to_transfer)

    rationale = explain(
        summary=(
            f"{deficit_store_id} has {coverage_days} days of coverage for {product_id} "
            f"(stockout risk: {stockout_risk})"
        ),
        facts={
            "available_units": deficit_available,
            "daily_demand_rate": round(daily_demand_rate, 2),
            "units_needed": units_needed,
            "recommended_source": source_store_id,
            "recommended_transfer_units": recommended_transfer_units,
        },
    )

    return {
        "agent": "InventoryAgent",
        "deficit_store_id": deficit_store_id,
        "deficit_available": deficit_available,
        "coverage_days": coverage_days,
        "stockout_risk": stockout_risk,
        "units_needed": units_needed,
        "candidates": [c.model_dump() for c in candidates],
        "recommended_source_store_id": source_store_id,
        "recommended_transfer_units": recommended_transfer_units,
        "unit_cost": unit_cost,
        "transfer_value_usd": round(recommended_transfer_units * unit_cost, 2),
        "confidence": 0.95 if deficit_position else 0.4,
        "rationale": rationale,
        "status": "OK" if deficit_position else "UNAVAILABLE",
    }
