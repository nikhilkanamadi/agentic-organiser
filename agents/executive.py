"""
Executive Agent.

Responsibilities (blueprint §10): interpret business objective, aggregate
specialist outputs, compare alternatives, generate executive recommendation.
Never bypasses the policy gate (blueprint §10, §37) -- this module only ever
*proposes* RecommendationCandidate objects; tools/policy.py decides whether
they may proceed, and nothing here can override that.
"""

from __future__ import annotations

from agents.reasoning import explain
from tools.analytics_store import get_product
from tools.contracts import ActionType, RecommendationCandidate


def compare_and_recommend(demand_result: dict, inventory_result: dict) -> RecommendationCandidate:
    product_id = demand_result["signal"]["product_id"]
    product = get_product(product_id) or {}
    list_price = float(product.get("list_price", 0))
    cost = float(product.get("cost", 0))

    transfer_units = inventory_result.get("recommended_transfer_units", 0)

    if not inventory_result.get("stockout_risk") or transfer_units <= 0:
        candidate = RecommendationCandidate(
            action_type=ActionType.NO_ACTION,
            payload={"reason": "No stockout risk detected or no viable transfer source."},
            expected_revenue_impact=0.0,
            expected_margin_impact=0.0,
            confidence=min(demand_result["confidence"], inventory_result["confidence"]),
            rationale="",
        )
    else:
        expected_revenue_impact = round(transfer_units * list_price, 2)
        expected_margin_impact = round(transfer_units * (list_price - cost), 2)
        candidate = RecommendationCandidate(
            action_type=ActionType.TRANSFER,
            payload={
                "product_id": product_id,
                "source_store_id": inventory_result["recommended_source_store_id"],
                "destination_store_id": inventory_result["deficit_store_id"],
                "units": transfer_units,
                "transfer_value_usd": inventory_result["transfer_value_usd"],
            },
            expected_revenue_impact=expected_revenue_impact,
            expected_margin_impact=expected_margin_impact,
            confidence=min(demand_result["confidence"], inventory_result["confidence"]),
            rationale="",
        )

    rationale = explain(
        summary=f"Executive recommendation: {candidate.action_type.value} for {product_id}",
        facts={
            "expected_revenue_impact": candidate.expected_revenue_impact,
            "expected_margin_impact": candidate.expected_margin_impact,
            "confidence": candidate.confidence,
            "demand_change": demand_result["signal"]["demand_change"],
            "coverage_days": inventory_result["coverage_days"],
        },
    )
    candidate.rationale = rationale
    return candidate
