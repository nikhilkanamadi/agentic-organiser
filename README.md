# Agentic Merchandising OS

Reference implementation of the architecture in
[`agentic_merchandising_os_gcp_bigquery.md`](./agentic_merchandising_os_gcp_bigquery.md) and
[`agentic_merchandising_os_design_doc.md`](./agentic_merchandising_os_design_doc.md).

**Status: Phase 1 MVP** -- runs entirely locally, no cloud account or API key required.

```text
demand anomaly -> investigate -> forecast -> inventory check ->
executive recommendation -> policy gate -> human approval -> execute -> measure outcome
```

## Quickstart

```bash
make setup   # creates .venv, installs fastapi/uvicorn/pydantic/httpx/pytest
make seed    # generates the synthetic "Atlanta denim demand spike" dataset
make test    # runs the unit + golden-scenario test suite
make run     # starts the API on http://localhost:8000
```

Trigger the hero scenario once the server is running:

```bash
curl -X POST http://localhost:8000/v1/events \
  -H "Content-Type: application/json" \
  -d '{"product_id": "P472", "store_id": "ATL127"}'
```

That returns a `workflow_id` + `recommendation_id` in `PENDING_APPROVAL` (the engineered scenario
deliberately lands at confidence = 0.90, which the default policy rule routes to human approval).
Approve it:

```bash
curl -X POST http://localhost:8000/v1/recommendations/<recommendation_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"approver_id": "planner@example.com"}'
```

Inspect the full trace:

```bash
curl http://localhost:8000/v1/workflows/<workflow_id>/trace
```

## What's implemented (Phase 1 scope)

| Design-doc piece | Phase 1 implementation |
|---|---|
| Analytical store (BigQuery) | SQLite, same table shapes (`dim_product`, `dim_store`, `fact_sales`, `fact_inventory`) -- [tools/analytics_store.py](tools/analytics_store.py) |
| Operational store (Cloud SQL) | SQLite, same column shapes as the Postgres DDL in the design doc §10.3-B -- [tools/operational_store.py](tools/operational_store.py) |
| Orchestrator (LangGraph) | Minimal dependency-free state-graph runner, same node/edge/checkpoint concepts -- [orchestration/graph.py](orchestration/graph.py) |
| Demand / Inventory / Executive Agents | [agents/demand.py](agents/demand.py), [agents/inventory.py](agents/inventory.py), [agents/executive.py](agents/executive.py) |
| Model Gateway | Deterministic rationale by default; real Claude call if `ANTHROPIC_API_KEY` is set -- [agents/reasoning.py](agents/reasoning.py) |
| Policy Engine | Deterministic, rule-driven, no LLM -- [tools/policy.py](tools/policy.py) |
| Execution Layer | Mocked, idempotent -- [tools/execution.py](tools/execution.py) |
| API Gateway | FastAPI -- [apps/api/main.py](apps/api/main.py) |
| Golden scenario | [evaluation/golden/atlanta_denim_spike.json](evaluation/golden/atlanta_denim_spike.json), exercised end-to-end in [tests/test_golden_workflow.py](tests/test_golden_workflow.py) |

**Not yet implemented** (planned for later phases per the design doc's rollout plan, §14):
Pricing Agent, Marketing Agent, real Pub/Sub/Dataflow streaming ingestion, real BigQuery/Cloud SQL,
Vertex AI model routing, MCP/A2A boundaries, dashboard frontend, Terraform/GCP deployment, CI/CD pipeline.

## Known Phase 1 limitations (intentional, to be addressed in later phases)

- Single-process, synchronous execution -- no real async checkpointing/resume across process restarts.
- `InventoryAgent.run`'s allocator is not lock-protected against concurrent workflows (design doc EC-4).
- Outcome measurement (`actual` vs `predicted`) is a deterministic simulation (`predicted * 0.95`), since
  there's no live retail system to read real outcomes back from yet.
- No authentication/RBAC on the API -- every endpoint is open, matching a local-dev-only posture.

## Repository layout

```text
agents/            Demand, Inventory, Executive agents + the Model Gateway stub
orchestration/      State-graph runner + the Phase 1 workflow definition
tools/              Typed tool contracts, analytics store, operational store, policy engine, execution
apps/api/           FastAPI gateway
data/seed/          Synthetic dataset generator
evaluation/golden/  Golden scenario definitions
tests/              Unit + end-to-end golden-scenario tests
```
