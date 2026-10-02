"""
Typed tool contracts for every agent-callable capability.

Design-doc references:
  - §10.2 Backend: "Typed tool contracts (Pydantic models) ... enforce input/output
    schema + auth + side-effect classification centrally."
  - §13 Security: an agent cannot invent a new action type or exceed declared tool
    bounds — enforced here by making every tool input/output a closed Pydantic schema.

Every tool contract declares:
  name, side_effect classification (READ | WRITE), and the input/output schema.
Agents never call raw SQL or raw APIs directly — only these typed functions.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SideEffect(str, Enum):
    READ = "READ"
    WRITE = "WRITE"


# ---------------------------------------------------------------------------
# query_sales / demand signal tools (Demand Agent)
# ---------------------------------------------------------------------------

class QuerySalesInput(BaseModel):
    product_id: str
    store_id: str
    recent_window_days: int = Field(default=7, ge=1, le=90)
    baseline_window_days: int = Field(default=28, ge=7, le=180)


class QuerySalesOutput(BaseModel):
    product_id: str
    store_id: str
    units_recent: int
    units_baseline_avg: float
    revenue_recent: float
    demand_change: float  # fractional change, e.g. 0.41 == +41%
    data_as_of: date


class DemandForecastInput(BaseModel):
    product_id: str
    store_id: str
    horizon_days: int = Field(default=14, ge=1, le=90)


class DemandForecastOutput(BaseModel):
    product_id: str
    store_id: str
    expected_units: float
    confidence_low: float
    confidence_high: float
    confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# inventory tools (Inventory Agent)
# ---------------------------------------------------------------------------

class GetInventoryInput(BaseModel):
    product_id: str
    store_ids: list[str]


class InventoryPosition(BaseModel):
    store_id: str
    on_hand: int
    reserved: int
    in_transit: int
    available: int
    data_as_of: date


class GetInventoryOutput(BaseModel):
    product_id: str
    positions: list[InventoryPosition]


class OptimizeAllocationInput(BaseModel):
    product_id: str
    deficit_store_id: str
    units_needed: int


class AllocationCandidate(BaseModel):
    source_store_id: str
    units_available_to_transfer: int
    transfer_value_usd: float


class OptimizeAllocationOutput(BaseModel):
    product_id: str
    deficit_store_id: str
    units_needed: int
    candidates: list[AllocationCandidate]
    recommended_transfer_units: int


# ---------------------------------------------------------------------------
# executive / recommendation
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    NO_ACTION = "NO_ACTION"
    TRANSFER = "TRANSFER"
    PRICE_CHANGE = "PRICE_CHANGE"
    MARKETING_BUDGET = "MARKETING_BUDGET"


class RecommendationCandidate(BaseModel):
    action_type: ActionType
    payload: dict
    expected_revenue_impact: float
    expected_margin_impact: float
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

class PolicyResult(str, Enum):
    PASS = "PASS"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class PolicyEvaluation(BaseModel):
    result: PolicyResult
    reason: str
    matched_rule: Optional[str] = None


# ---------------------------------------------------------------------------
# execution (WRITE side-effect, requires idempotency key)
# ---------------------------------------------------------------------------

class CreateInventoryTransferInput(BaseModel):
    idempotency_key: str
    product_id: str
    source_store_id: str
    destination_store_id: str
    units: int = Field(gt=0)


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"


class ExecutionResult(BaseModel):
    execution_id: str
    status: ExecutionStatus
    detail: str


TOOL_REGISTRY = {
    "query_sales": SideEffect.READ,
    "get_demand_forecast": SideEffect.READ,
    "get_inventory": SideEffect.READ,
    "optimize_allocation": SideEffect.READ,
    "create_inventory_transfer": SideEffect.WRITE,
}
