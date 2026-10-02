"""
Demand Agent.

Responsibilities (blueprint §10): detect anomalies, query historical demand,
run forecasts, quantify uncertainty.

Phase 1 implementation uses the governed `query_sales` tool only -- it never
touches raw SQL (design doc §13 / blueprint §21).
"""

from __future__ import annotations

from agents.reasoning import explain
from tools.analytics_store import query_sales
from tools.contracts import DemandForecastOutput, QuerySalesInput

ANOMALY_THRESHOLD = 0.25  # +25% velocity change triggers investigation


def detect_anomaly(product_id: str, store_id: str) -> dict:
    """Streaming-signal equivalent of blueprint §8/§22: compute demand_change
    and decide whether it crosses the anomaly trigger threshold."""
    signal = query_sales(QuerySalesInput(product_id=product_id, store_id=store_id))
    return {
        "product_id": product_id,
        "store_id": store_id,
        "demand_change": signal.demand_change,
        "triggered": signal.demand_change >= ANOMALY_THRESHOLD,
        "units_recent": signal.units_recent,
        "units_baseline_avg": signal.units_baseline_avg,
    }


def run(product_id: str, store_id: str) -> dict:
    """Full Demand Agent analysis for an already-triggered anomaly."""
    signal = query_sales(QuerySalesInput(product_id=product_id, store_id=store_id))

    # Naive forecast: project the recent 7-day rate forward with a mild
    # regression toward baseline, and derive a confidence interval from the
    # spread between recent and baseline rates. This is intentionally simple
    # -- Phase 2 swaps in a real forecasting model (design doc gap noted:
    # §16 NFR, forecasting model lifecycle is out of scope for Phase 1).
    daily_recent_rate = signal.units_recent / 7
    daily_baseline_rate = signal.units_baseline_avg / 7 if signal.units_baseline_avg else daily_recent_rate
    projected_daily = (daily_recent_rate * 0.7) + (daily_baseline_rate * 0.3)
    horizon_days = 14
    expected_units = round(projected_daily * horizon_days, 1)
    spread = abs(daily_recent_rate - daily_baseline_rate) * horizon_days * 0.5
    forecast = DemandForecastOutput(
        product_id=product_id,
        store_id=store_id,
        expected_units=expected_units,
        confidence_low=max(0.0, round(expected_units - spread, 1)),
        confidence_high=round(expected_units + spread, 1),
        confidence=0.9 if abs(signal.demand_change) < 1.0 else 0.75,
    )

    rationale = explain(
        summary=f"Demand for {product_id} at {store_id} changed {signal.demand_change:+.1%}",
        facts={
            "units_recent_7d": signal.units_recent,
            "baseline_avg_7d_equiv": signal.units_baseline_avg,
            "forecast_14d_units": forecast.expected_units,
        },
    )

    return {
        "agent": "DemandAgent",
        "signal": signal.model_dump(mode="json"),
        "forecast": forecast.model_dump(mode="json"),
        "confidence": forecast.confidence,
        "rationale": rationale,
        "status": "OK",
    }
