"""
Phase 1 MVP workflow:

    detect_anomaly -> investigate_demand -> analyze_inventory ->
    aggregate_options -> policy_check -> [human_approval | auto] ->
    execute -> measure_outcome

Mirrors the LangGraph `MerchandisingState` / workflow sequence defined in the
blueprint (§14) and the end-to-end walkthrough in §32, scoped to the Phase 1
MVP agent pair (Demand + Inventory + Executive), per blueprint §35 "do not
start with six agents."

The human-approval boundary is modeled as two separate entry points rather
than one blocking call, since approval can arrive seconds or days later:
  - `handle_event(...)` runs analysis through the policy gate and either
    auto-proceeds to execution or stops in PENDING_APPROVAL.
  - `approve_recommendation(...)` / `reject_recommendation(...)` resume from
    that stop point once a human decides.
"""

from __future__ import annotations

import time
import uuid

from agents import demand, executive, inventory
from orchestration.graph import StateGraph
from tools import operational_store, policy
from tools.contracts import ActionType, CreateInventoryTransferInput, PolicyResult
from tools.execution import create_inventory_transfer


def _trace(workflow_id: str, agent_name: str, input_data: dict, output_data: dict,
           confidence: float | None, latency_ms: int, status: str = "OK") -> None:
    operational_store.record_agent_run(
        workflow_id=workflow_id,
        agent_name=agent_name,
        input_data=input_data,
        output_data=output_data,
        confidence=confidence,
        latency_ms=latency_ms,
        cost_usd=0.0,  # Phase 1 reasoning is deterministic/local; no model spend to track yet.
        status=status,
    )


# ---------------------------------------------------------------------------
# Analysis graph: detect_anomaly is run by the caller (handle_event) before a
# workflow even exists, since a non-anomalous event should never create one.
# ---------------------------------------------------------------------------

def _node_investigate_demand(state: dict) -> dict:
    t0 = time.perf_counter()
    result = demand.run(state["product_id"], state["store_id"])
    latency_ms = int((time.perf_counter() - t0) * 1000)
    _trace(state["workflow_id"], "DemandAgent",
           {"product_id": state["product_id"], "store_id": state["store_id"]},
           result, result["confidence"], latency_ms)
    state["demand_result"] = result
    return state


def _node_analyze_inventory(state: dict) -> dict:
    t0 = time.perf_counter()
    daily_rate = state["demand_result"]["signal"]["units_recent"] / 7
    result = inventory.run(state["product_id"], state["store_id"], daily_rate)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    _trace(state["workflow_id"], "InventoryAgent",
           {"product_id": state["product_id"], "deficit_store_id": state["store_id"],
            "daily_demand_rate": daily_rate},
           result, result["confidence"], latency_ms, status=result["status"])
    state["inventory_result"] = result
    return state


def _node_aggregate_options(state: dict) -> dict:
    t0 = time.perf_counter()
    candidate = executive.compare_and_recommend(state["demand_result"], state["inventory_result"])
    latency_ms = int((time.perf_counter() - t0) * 1000)
    _trace(state["workflow_id"], "ExecutiveAgent",
           {"demand_result": state["demand_result"], "inventory_result": state["inventory_result"]},
           candidate.model_dump(mode="json"), candidate.confidence, latency_ms)
    state["candidate"] = candidate
    return state


def _node_policy_check(state: dict) -> dict:
    t0 = time.perf_counter()
    evaluation = policy.evaluate(state["candidate"])
    latency_ms = int((time.perf_counter() - t0) * 1000)
    _trace(state["workflow_id"], "PolicyEngine",
           state["candidate"].model_dump(mode="json"),
           evaluation.model_dump(mode="json"), None, latency_ms)
    state["policy_evaluation"] = evaluation
    return state


_analysis_graph = (
    StateGraph()
    .add_node("investigate_demand", _node_investigate_demand)
    .add_node("analyze_inventory", _node_analyze_inventory)
    .add_node("aggregate_options", _node_aggregate_options)
    .add_node("policy_check", _node_policy_check)
    .set_start("investigate_demand")
    .add_edge("investigate_demand", "analyze_inventory")
    .add_edge("analyze_inventory", "aggregate_options")
    .add_edge("aggregate_options", "policy_check")
)


# ---------------------------------------------------------------------------
# Entry point 1: event arrives -> anomaly check -> analysis -> policy gate
# ---------------------------------------------------------------------------

def handle_event(event_id: str, product_id: str, store_id: str) -> dict:
    anomaly = demand.detect_anomaly(product_id, store_id)
    if not anomaly["triggered"]:
        return {"workflow_id": None, "status": "NO_ANOMALY", "anomaly": anomaly}

    trace_id = str(uuid.uuid4())
    workflow_id = operational_store.create_workflow(
        event_id=event_id, product_id=product_id, store_ids=[store_id], trace_id=trace_id
    )

    state = {
        "workflow_id": workflow_id,
        "product_id": product_id,
        "store_id": store_id,
        "anomaly": anomaly,
    }
    state = _analysis_graph.run(state)

    candidate = state["candidate"]
    evaluation = state["policy_evaluation"]

    recommendation_id = operational_store.create_recommendation(
        workflow_id=workflow_id,
        action_type=candidate.action_type.value,
        payload=candidate.payload,
        expected_impact={
            "revenue": candidate.expected_revenue_impact,
            "margin": candidate.expected_margin_impact,
            "confidence": candidate.confidence,
        },
        policy_result=evaluation.result.value,
        policy_reason=evaluation.reason,
        status="PROPOSED",
    )

    if evaluation.result == PolicyResult.DENY:
        operational_store.update_recommendation_status(recommendation_id, "DENIED")
        operational_store.update_workflow(workflow_id, status="POLICY_DENIED")
        return {
            "workflow_id": workflow_id,
            "recommendation_id": recommendation_id,
            "status": "POLICY_DENIED",
            "reason": evaluation.reason,
        }

    if evaluation.result == PolicyResult.APPROVAL_REQUIRED:
        operational_store.update_workflow(workflow_id, status="PENDING_APPROVAL")
        return {
            "workflow_id": workflow_id,
            "recommendation_id": recommendation_id,
            "status": "PENDING_APPROVAL",
            "candidate": candidate.model_dump(mode="json"),
            "reason": evaluation.reason,
        }

    # PolicyResult.PASS -> bounded auto-execution (blueprint §19 Level 2 autonomy)
    operational_store.update_recommendation_status(recommendation_id, "AUTO_APPROVED")
    result = _execute_and_measure(
        workflow_id, recommendation_id, candidate.action_type, candidate.payload,
        candidate.expected_revenue_impact, candidate.expected_margin_impact,
    )
    return {
        "workflow_id": workflow_id,
        "recommendation_id": recommendation_id,
        "status": "COMPLETED",
        "execution": result,
    }


# ---------------------------------------------------------------------------
# Entry point 2: human decision arrives later for a PENDING_APPROVAL workflow
# ---------------------------------------------------------------------------

def approve_recommendation(recommendation_id: str, approver_id: str, comment: str | None = None) -> dict:
    rec = operational_store.get_recommendation(recommendation_id)
    if rec is None:
        raise ValueError(f"No such recommendation: {recommendation_id}")
    if rec["status"] != "PROPOSED":
        raise ValueError(f"Recommendation {recommendation_id} is not awaiting approval "
                          f"(status={rec['status']})")

    operational_store.record_approval(recommendation_id, approver_id, "APPROVE", comment)
    operational_store.update_recommendation_status(recommendation_id, "APPROVED")

    import json
    payload = json.loads(rec["payload"])
    impact = json.loads(rec["expected_impact"]) if rec["expected_impact"] else {}

    result = _execute_and_measure(
        rec["workflow_id"], recommendation_id, ActionType(rec["action_type"]), payload,
        impact.get("revenue", 0.0), impact.get("margin", 0.0),
    )
    return {
        "workflow_id": rec["workflow_id"],
        "recommendation_id": recommendation_id,
        "status": "COMPLETED",
        "execution": result,
    }


def reject_recommendation(recommendation_id: str, approver_id: str, comment: str | None = None) -> dict:
    rec = operational_store.get_recommendation(recommendation_id)
    if rec is None:
        raise ValueError(f"No such recommendation: {recommendation_id}")
    if rec["status"] != "PROPOSED":
        raise ValueError(f"Recommendation {recommendation_id} is not awaiting approval "
                          f"(status={rec['status']})")

    operational_store.record_approval(recommendation_id, approver_id, "REJECT", comment)
    operational_store.update_recommendation_status(recommendation_id, "REJECTED")
    operational_store.update_workflow(rec["workflow_id"], status="REJECTED")
    return {"workflow_id": rec["workflow_id"], "recommendation_id": recommendation_id, "status": "REJECTED"}


# ---------------------------------------------------------------------------
# Shared execution + outcome-measurement tail (blueprint §32 steps 11-14)
# ---------------------------------------------------------------------------

def _execute_and_measure(
    workflow_id: str, recommendation_id: str, action_type: ActionType, payload: dict,
    expected_revenue: float, expected_margin: float,
) -> dict:
    if action_type == ActionType.TRANSFER:
        idempotency_key = f"txn-{recommendation_id}"
        t0 = time.perf_counter()
        exec_result = create_inventory_transfer(
            recommendation_id,
            CreateInventoryTransferInput(
                idempotency_key=idempotency_key,
                product_id=payload["product_id"],
                source_store_id=payload["source_store_id"],
                destination_store_id=payload["destination_store_id"],
                units=payload["units"],
            ),
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        _trace(workflow_id, "ExecutionLayer", payload, exec_result.model_dump(mode="json"),
               None, latency_ms, status=exec_result.status.value)
        execution_summary = exec_result.model_dump(mode="json")
    else:
        execution_summary = {"detail": "No execution required for NO_ACTION."}

    # Outcome measurement (blueprint §32 step 13-14 / design doc FR-12): Phase 1
    # has no live retail system to observe, so actual outcome is a deterministic
    # simulation (predicted * 0.95) purely to exercise the predicted-vs-actual
    # evaluation path end to end. Phase 2 replaces this with real outcome events
    # read back from BigQuery.
    actual_revenue = round(expected_revenue * 0.95, 2)
    actual_margin = round(expected_margin * 0.95, 2)
    evaluation_summary = {
        "predicted_revenue": expected_revenue,
        "actual_revenue": actual_revenue,
        "predicted_margin": expected_margin,
        "actual_margin": actual_margin,
        "revenue_forecast_error_pct": (
            round((actual_revenue - expected_revenue) / expected_revenue, 4)
            if expected_revenue else 0.0
        ),
    }
    _trace(workflow_id, "EvaluationService", {"expected_revenue": expected_revenue,
                                               "expected_margin": expected_margin},
           evaluation_summary, None, 0)

    operational_store.update_recommendation_status(recommendation_id, "EXECUTED")
    operational_store.update_workflow(
        workflow_id, status="COMPLETED",
        expected_revenue=expected_revenue, expected_margin=expected_margin,
    )

    return {"execution": execution_summary, "evaluation": evaluation_summary}
