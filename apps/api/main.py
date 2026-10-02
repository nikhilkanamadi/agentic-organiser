"""
API Gateway (design doc §10.2, §10.5) -- Phase 1 subset.

Run: uvicorn apps.api.main:app --reload --port 8000
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from orchestration import workflow
from tools import analytics_store, operational_store

app = FastAPI(
    title="Agentic Merchandising OS -- Phase 1 MVP",
    version="0.1.0",
    description="Demand anomaly -> inventory -> executive -> policy -> approval -> execution -> measurement.",
)


@app.on_event("startup")
def _startup() -> None:
    analytics_store.init_schema()
    operational_store.init_schema()


# ---------------------------------------------------------------------------
# Events (design doc FR-1/FR-2; blueprint §8, §23)
# ---------------------------------------------------------------------------

class EventIn(BaseModel):
    product_id: str
    store_id: str
    event_id: str | None = None


@app.post("/v1/events")
def post_event(event: EventIn):
    event_id = event.event_id or str(uuid.uuid4())
    try:
        result = workflow.handle_event(event_id, event.product_id, event.store_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


# ---------------------------------------------------------------------------
# Workflows (design doc FR-11, FR-13)
# ---------------------------------------------------------------------------

@app.get("/v1/workflows")
def list_workflows(status: str | None = None):
    return operational_store.list_workflows(status=status)


@app.get("/v1/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    wf = operational_store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@app.get("/v1/workflows/{workflow_id}/trace")
def get_trace(workflow_id: str):
    wf = operational_store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"workflow_id": workflow_id, "trace": operational_store.get_trace(workflow_id)}


# ---------------------------------------------------------------------------
# Recommendations / Approvals (design doc FR-8, FR-9; UC-2)
# ---------------------------------------------------------------------------

@app.get("/v1/recommendations")
def list_recommendations(status: str | None = None):
    if status == "PROPOSED" or status is None:
        return operational_store.list_pending_recommendations()
    raise HTTPException(status_code=400, detail="Only status=PROPOSED is supported in Phase 1")


@app.get("/v1/recommendations/{recommendation_id}")
def get_recommendation(recommendation_id: str):
    rec = operational_store.get_recommendation(recommendation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


class ApprovalIn(BaseModel):
    approver_id: str
    comment: str | None = None


@app.post("/v1/recommendations/{recommendation_id}/approve")
def approve_recommendation(recommendation_id: str, body: ApprovalIn):
    try:
        return workflow.approve_recommendation(recommendation_id, body.approver_id, body.comment)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/v1/recommendations/{recommendation_id}/reject")
def reject_recommendation(recommendation_id: str, body: ApprovalIn):
    try:
        return workflow.reject_recommendation(recommendation_id, body.approver_id, body.comment)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}
