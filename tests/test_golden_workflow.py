"""
Golden scenario (evaluation/golden/atlanta_denim_spike.json), run as an
end-to-end CI test per design doc §11: "golden-dataset evaluation" gate that
must pass before any deploy.
"""

from orchestration import workflow
from tools import operational_store


def test_atlanta_denim_spike_end_to_end():
    # 1. Event arrives -> anomaly detected -> full analysis -> policy gate.
    result = workflow.handle_event("evt-1", "P472", "ATL127")

    assert result["status"] == "PENDING_APPROVAL", (
        "Expected the hero scenario to land in PENDING_APPROVAL "
        f"(confidence <= 0.90 policy rule); got {result}"
    )
    workflow_id = result["workflow_id"]
    recommendation_id = result["recommendation_id"]
    assert workflow_id and recommendation_id

    candidate = result["candidate"]
    assert candidate["action_type"] == "TRANSFER"
    assert candidate["payload"]["destination_store_id"] == "ATL127"
    assert candidate["payload"]["units"] > 0
    assert candidate["expected_revenue_impact"] > 0

    # Full trace exists even before approval (demand, inventory, executive, policy).
    trace = operational_store.get_trace(workflow_id)
    agents_seen = {r["agent_name"] for r in trace}
    assert agents_seen == {"DemandAgent", "InventoryAgent", "ExecutiveAgent", "PolicyEngine"}

    wf = operational_store.get_workflow(workflow_id)
    assert wf["status"] == "PENDING_APPROVAL"

    # 2. Human approves -> execution + outcome measurement.
    approval_result = workflow.approve_recommendation(recommendation_id, "planner@example.com")
    assert approval_result["status"] == "COMPLETED"
    assert approval_result["execution"]["execution"]["status"] == "SUCCESS"

    wf_after = operational_store.get_workflow(workflow_id)
    assert wf_after["status"] == "COMPLETED"

    final_trace = operational_store.get_trace(workflow_id)
    final_agents_seen = {r["agent_name"] for r in final_trace}
    assert "ExecutionLayer" in final_agents_seen
    assert "EvaluationService" in final_agents_seen

    # 3. Idempotency: approving again must fail cleanly, not double-execute.
    try:
        workflow.approve_recommendation(recommendation_id, "planner@example.com")
        assert False, "second approval should have raised"
    except ValueError:
        pass


def test_non_anomalous_event_creates_no_workflow():
    result = workflow.handle_event("evt-2", "P472", "NYC045")
    assert result["workflow_id"] is None
    assert result["status"] == "NO_ANOMALY"
    assert operational_store.list_workflows() == []


def test_rejection_path_does_not_execute():
    result = workflow.handle_event("evt-3", "P472", "ATL127")
    recommendation_id = result["recommendation_id"]

    reject_result = workflow.reject_recommendation(recommendation_id, "planner@example.com", "not now")
    assert reject_result["status"] == "REJECTED"

    wf = operational_store.get_workflow(result["workflow_id"])
    assert wf["status"] == "REJECTED"

    trace = operational_store.get_trace(result["workflow_id"])
    agents_seen = {r["agent_name"] for r in trace}
    assert "ExecutionLayer" not in agents_seen
