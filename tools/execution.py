"""
Mock Execution Layer.

Design-doc references:
  - §9: every write action requires an idempotency_key; retries re-check
    current state rather than blindly resubmitting.
  - §10.4: ExecutionResult / executions table is the system of record for
    "what was actually done", independent of what was merely recommended.

Stands in for the real business APIs (OMS/inventory system) that Phase 2
would call for real. The contract (CreateInventoryTransferInput /
ExecutionResult) is what a real adapter would also implement, so swapping
this module out later doesn't change the orchestrator or agents.
"""

from __future__ import annotations

from tools.contracts import CreateInventoryTransferInput, ExecutionResult, ExecutionStatus
from tools.operational_store import record_execution


def create_inventory_transfer(
    recommendation_id: str, inp: CreateInventoryTransferInput
) -> ExecutionResult:
    # Simulated downstream call -- in Phase 2 this becomes a real OMS/WMS API call.
    # The mock is synchronous, so we record the final SUCCESS state directly;
    # a real adapter with an async downstream call would insert PENDING first
    # and update to SUCCESS/FAILED once the call resolves.
    detail = (
        f"Transferred {inp.units} units of {inp.product_id} "
        f"from {inp.source_store_id} to {inp.destination_store_id}."
    )
    execution_id, is_new = record_execution(
        recommendation_id=recommendation_id,
        idempotency_key=inp.idempotency_key,
        status=ExecutionStatus.SUCCESS.value,
        result={"detail": detail},
    )

    if not is_new:
        # Idempotent replay: same key already executed, do not re-submit to
        # the (mock) downstream system a second time.
        return ExecutionResult(
            execution_id=execution_id,
            status=ExecutionStatus.SUCCESS,
            detail="Idempotent replay: transfer already executed for this key.",
        )

    return ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.SUCCESS,
        detail=detail,
    )
