# Agentic Merchandising OS — GCP + BigQuery

> **Prototype architecture and implementation blueprint for a Gap-like omnichannel retailer.**
>
> This document describes a reference implementation inspired by Gap Inc.'s publicly documented agentic-AI engineering direction and Google Cloud's published agentic architecture patterns. It is **not** Gap Inc.'s internal architecture.

## 1. Executive Summary

Build an **Agentic Merchandising Operating System (AMOS)** that continuously turns retail signals into bounded, auditable business actions.

The system should answer:

> **What changed, why did it change, what should the retailer do, what is the expected financial impact, and can the system safely execute the action?**

The prototype focuses on one closed-loop use case:

**Demand anomaly → investigation → demand forecast → inventory optimization → pricing/marketing analysis → executive recommendation → policy gate → human approval → execution → outcome measurement.**

The design intentionally separates:

- **LLM reasoning** — interpretation, planning, routing, explanation.
- **ML/statistical models** — forecasting and prediction.
- **Optimization** — inventory allocation and constrained decisions.
- **Deterministic business rules** — financial and policy controls.
- **Agents** — orchestration and tool use.
- **BigQuery** — governed analytical system of record.
- **GCP runtime** — scalable deployment and observability.

---

# 2. Why This Architecture

Gap Inc. has publicly described an enterprise agentic direction spanning product creation, sourcing, supply chain, AI-ready data, MCP/A2A interoperability, trust frameworks, evaluation gates, golden datasets, cost-aware model routing, Vertex AI, BigQuery, GKE and Cloud Run.

Relevant public Gap Inc. engineering requirements include:

- AI/ML-backed multi-agent workflows.
- Agent-ready structured and unstructured data.
- MCP/A2A integration patterns.
- Agent harness and reference architecture.
- Trust frameworks and tool contracts.
- LLM-as-judge and golden datasets.
- Grounded and entitlement-aware agents.
- Human gates against nondeterministic failures.
- Cost-aware model routing.
- Vertex AI / GCP.
- BigQuery and governed semantic layers.
- Cloud Run, GKE, Terraform and CI/CD.

Google Cloud's current architecture guidance similarly separates the system into:

1. Frontend
2. Agent development framework
3. Tools
4. Memory
5. Agent design/orchestration
6. Agent runtime
7. Models/model runtime

This project maps those principles to retail merchandising.

---

# 3. Strategic Objective

The business objective is not:

> "Build a chatbot."

It is:

> **Continuously improve profitable revenue while reducing inventory risk and operational friction.**

Core optimization objective:

\[
\max J =
\alpha R +
\beta GM +
\gamma CLV -
\delta I -
\epsilon M -
\zeta S
\]

Where:

- \(R\) = revenue
- \(GM\) = gross margin
- \(CLV\) = customer lifetime value
- \(I\) = inventory carrying / excess inventory cost
- \(M\) = markdown cost
- \(S\) = stockout/service-level penalty

Subject to:

\[
Margin \ge Margin_{min}
\]

\[
InventoryRisk \le Risk_{max}
\]

\[
ActionCost \le Budget
\]

\[
Authorization(Action) = True
\]

\[
Policy(Action) = True
\]

The LLM should **not** directly optimize these equations. It should coordinate the systems that do.

---

# 4. High-Level Architecture

```text
                    ┌──────────────────────────────┐
                    │ Merchandising Control Center │
                    │ React / Next.js              │
                    └──────────────┬───────────────┘
                                   │
                              HTTPS / API
                                   │
                    ┌──────────────▼───────────────┐
                    │ API / Workflow Gateway       │
                    │ FastAPI                      │
                    └──────────────┬───────────────┘
                                   │
                     ┌─────────────▼─────────────┐
                     │ Agent Orchestrator        │
                     │ LangGraph / ADK           │
                     │ Durable State + Routing   │
                     └─────────────┬─────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       │                           │                           │
       ▼                           ▼                           ▼
┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│ Demand Agent │           │ Inventory    │           │ Pricing      │
│              │           │ Agent        │           │ Agent        │
└──────┬───────┘           └──────┬───────┘           └──────┬───────┘
       │                          │                          │
       └──────────────────────────┼──────────────────────────┘
                                  ▼
                        ┌─────────────────────┐
                        │ Decision / Policy   │
                        │ Engine              │
                        └──────────┬──────────┘
                                   │
                           Human approval
                                   │
                        ┌──────────▼──────────┐
                        │ Execution Tool      │
                        │ APIs / Events       │
                        └──────────┬──────────┘
                                   │
                                   ▼
                              Retail systems
```

---

# 5. GCP Reference Architecture

```text
                         INTERNET / USERS
                                │
                                ▼
                        Cloud Load Balancing
                                │
                                ▼
                         Cloud Run / GKE
                                │
                         Agent API Layer
                                │
                     ┌──────────▼──────────┐
                     │ Agent Runtime       │
                     │ ADK / LangGraph     │
                     └──────────┬──────────┘
                                │
                ┌───────────────┼────────────────┐
                │               │                │
                ▼               ▼                ▼
             Gemini         Tool Gateway        Memory
           Vertex AI            │              / State
                                │
                ┌───────────────┼────────────────┐
                │               │                │
                ▼               ▼                ▼
             BigQuery       Cloud SQL          APIs
                │
                ▼
          Semantic Layer
                │
                ▼
        Looker / BI / Agents

Event Sources
     │
     ▼
   Pub/Sub
     │
     ▼
 Dataflow / SQL / ELT
     │
     ▼
  BigQuery
```

Recommended runtime options:

### Prototype

**Cloud Run**

Simple container deployment, fast iteration and low operational overhead.

### Scale / platform engineering

**GKE**

Use when the system requires deeper Kubernetes control, custom networking, specialized runtimes or platform-level orchestration.

### Managed agent runtime

Evaluate **Gemini Enterprise Agent Platform / Agent Runtime** when managed agent sessions, deployment and evaluation capabilities reduce platform work.

---

# 6. BigQuery as the Data Backbone

BigQuery should be the analytical backbone, not merely a database queried by an LLM.

## Data zones

```text
RAW
 │
 ▼
STAGING
 │
 ▼
CURATED
 │
 ▼
SEMANTIC
 │
 ▼
AGENT-READY
```

### RAW

Original operational events.

```text
raw_transactions
raw_inventory_events
raw_product_events
raw_customer_events
raw_campaign_events
raw_store_events
```

### CURATED

Clean business entities.

```text
dim_customer
dim_product
dim_store
dim_campaign
fact_sales
fact_inventory
fact_returns
fact_promotions
```

### SEMANTIC

Business definitions.

```text
metric_revenue
metric_gross_margin
metric_inventory_turnover
metric_stockout_rate
metric_conversion
metric_return_rate
```

### AGENT-READY

Precomputed context and features.

```text
agent_product_context
agent_store_context
agent_customer_context
agent_inventory_context
agent_demand_signals
agent_campaign_context
agent_policy_context
```

---

# 7. Recommended BigQuery Schema

## `dim_product`

```sql
product_id STRING
brand STRING
category STRING
subcategory STRING
gender STRING
color STRING
size_group STRING
cost NUMERIC
list_price NUMERIC
launch_date DATE
lifecycle_stage STRING
supplier_id STRING
```

## `dim_store`

```sql
store_id STRING
brand STRING
city STRING
state STRING
region STRING
store_type STRING
square_feet INT64
latitude FLOAT64
longitude FLOAT64
```

## `fact_sales`

```sql
transaction_id STRING
timestamp TIMESTAMP
store_id STRING
product_id STRING
customer_id STRING
channel STRING
quantity INT64
unit_price NUMERIC
discount NUMERIC
net_sales NUMERIC
cost NUMERIC
```

## `fact_inventory`

```sql
timestamp TIMESTAMP
location_id STRING
product_id STRING
on_hand INT64
reserved INT64
in_transit INT64
available INT64
```

## `fact_events`

```sql
event_id STRING
event_time TIMESTAMP
event_type STRING
entity_type STRING
entity_id STRING
payload JSON
```

---

# 8. Real-Time Data Path

For a real-time merchandising system:

```text
POS / E-commerce / Inventory
          │
          ▼
       Pub/Sub
          │
          ▼
      Dataflow
          │
          ├──────────────► BigQuery
          │
          └──────────────► Real-time signal processor
                                   │
                                   ▼
                            Agent trigger
```

Example:

```text
Event:
Product 472
Atlanta
Sales velocity +41%
```

The event enters Pub/Sub.

A streaming process evaluates:

```text
current_velocity
baseline_velocity
inventory_coverage
conversion_delta
margin
```

If anomaly score exceeds threshold:

```text
trigger = TRUE
```

The orchestration workflow begins.

---

# 9. Agent Topology

Use specialized agents rather than one giant agent.

```text
                    ROOT / EXECUTIVE AGENT
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   Demand Agent         Inventory Agent       Customer Agent
        │                     │                     │
        ▼                     ▼                     ▼
   Forecasting          Allocation            Segmentation
        │                     │                     │
        └──────────────┬──────┴──────────────┬──────┘
                       │                     │
                       ▼                     ▼
                 Pricing Agent        Marketing Agent
                       │                     │
                       └──────────┬──────────┘
                                  ▼
                         Decision Agent
                                  │
                                  ▼
                           Policy Engine
                                  │
                                  ▼
                          Human Approval
                                  │
                                  ▼
                             Executor
```

---

# 10. Agent Responsibilities

## Executive Agent

Responsibilities:

- Interpret business objective.
- Route work.
- Aggregate specialist outputs.
- Compare alternatives.
- Generate executive recommendation.
- Never bypass policy gates.

Tools:

```text
get_business_objective()
get_agent_results()
compare_scenarios()
calculate_expected_impact()
request_human_approval()
```

---

## Demand Agent

Responsibilities:

- Detect anomalies.
- Query historical demand.
- Run forecasts.
- Identify demand drivers.
- Quantify uncertainty.

Tools:

```text
query_sales()
get_demand_forecast()
get_trend_signals()
get_promotion_history()
```

---

## Inventory Agent

Responsibilities:

- Determine inventory coverage.
- Identify stockout risk.
- Find transferable inventory.
- Recommend allocation.

Tools:

```text
get_inventory()
get_distribution_center_inventory()
get_store_inventory()
optimize_allocation()
```

---

## Pricing Agent

Responsibilities:

- Estimate price response.
- Evaluate markdown exposure.
- Calculate margin impact.
- Recommend bounded price changes.

Tools:

```text
estimate_elasticity()
calculate_margin()
simulate_price()
get_pricing_policy()
```

---

## Marketing Agent

Responsibilities:

- Evaluate campaign performance.
- Estimate incremental conversion.
- Recommend budget movement.
- Create experiment hypotheses.

Tools:

```text
get_campaign_performance()
estimate_incremental_roi()
simulate_budget()
```

---

# 11. Agent Tool Contract

Every tool should have:

```text
name
description
input schema
output schema
authorization requirement
side-effect classification
timeout
retry policy
audit metadata
```

Example:

```json
{
  "name": "get_inventory",
  "description": "Return inventory availability for products and locations.",
  "input_schema": {
    "product_ids": ["string"],
    "location_ids": ["string"]
  },
  "side_effect": "READ",
  "authorization": "inventory.read"
}
```

For mutations:

```json
{
  "name": "create_inventory_transfer",
  "side_effect": "WRITE",
  "authorization": "inventory.transfer",
  "human_approval": true
}
```

This is essential for enterprise agent safety.

---

# 12. MCP

Use MCP as the standardized tool boundary where appropriate.

```text
Agent
  │
  ▼
MCP Client
  │
  ▼
MCP Server
  │
  ├── BigQuery
  ├── Inventory API
  ├── Pricing API
  ├── Campaign API
  └── Logistics API
```

Benefits:

- standardized tool interface
- discoverability
- authorization boundary
- observability
- easier replacement of backend systems

---

# 13. A2A

Use A2A when agents need independent service boundaries.

Example:

```text
Executive Agent
      │
      │ A2A
      ▼
Demand Agent Service
      │
      │ A2A
      ▼
Inventory Agent Service
```

The key distinction:

**MCP = agent ↔ tool**

**A2A = agent ↔ agent**

---

# 14. LangGraph Implementation

Recommended first implementation:

```text
LangGraph
   │
   ├── StateGraph
   │
   ├── checkpointing
   │
   ├── conditional routing
   │
   ├── human interrupts
   │
   └── tool execution
```

Example state:

```python
class MerchandisingState(TypedDict):
    event_id: str
    product_id: str
    store_ids: list[str]

    demand_signal: dict
    inventory_signal: dict
    pricing_signal: dict
    marketing_signal: dict

    recommendations: list[dict]

    risk_score: float
    expected_revenue: float
    expected_margin: float

    approval_required: bool
    approved: bool

    execution_result: dict
```

Workflow:

```text
START
  ↓
detect_anomaly
  ↓
investigate_demand
  ↓
forecast
  ↓
analyze_inventory
  ↓
analyze_pricing
  ↓
analyze_marketing
  ↓
aggregate_options
  ↓
policy_check
  ↓
human_approval
  ↓
execute
  ↓
measure_outcome
  ↓
END
```

---

# 15. ADK Implementation

Maintain the same business contracts while allowing ADK as an alternative orchestration implementation.

```text
Application Contract
       │
       ├───────────────┐
       ▼               ▼
   LangGraph          ADK
       │               │
       └───────┬───────┘
               ▼
          Common Tools
               │
               ▼
            GCP APIs
```

This gives the project **framework portability**.

The architecture should not become dependent on one orchestration framework.

---

# 16. Model Gateway

Do not hard-code every agent to one model.

Create:

```text
Agent
  ↓
Model Gateway
  ↓
Model Router
  ├── fast / low-cost model
  ├── reasoning model
  └── multimodal model
```

Routing dimensions:

```text
task complexity
latency
cost
context size
reasoning requirement
data sensitivity
```

Example:

```python
if task.complexity == "low":
    model = "fast_model"

elif task.requires_reasoning:
    model = "reasoning_model"

elif task.requires_vision:
    model = "multimodal_model"
```

Track:

```text
input_tokens
output_tokens
latency
model_cost
tool_calls
success_rate
```

---

# 17. Agent Memory

Use different memory types.

## Operational state

LangGraph checkpoint / runtime session.

## Long-term business knowledge

BigQuery + governed knowledge store.

## Semantic retrieval

Vector index for:

- product documents
- vendor information
- tech packs
- policy documents
- merchandising knowledge

## Episodic memory

Store:

```text
decision
context
action
outcome
timestamp
agent
confidence
```

This allows:

> "What happened the last time we increased inventory for this category?"

---

# 18. Policy Engine

Never rely on an LLM for authorization.

```text
Agent recommendation
       │
       ▼
Policy Engine
       │
       ├── identity
       ├── entitlement
       ├── financial limit
       ├── inventory limit
       ├── pricing rule
       ├── compliance
       └── approval requirement
```

Example:

```python
if transfer_value > 50_000:
    approval_required = True

if markdown_percentage > 30:
    approval_required = True

if agent_role != "inventory":
    deny("Unauthorized action")
```

---

# 19. Human-in-the-Loop

Three autonomy classes:

### Level 0 — Read

Agent can inspect data.

### Level 1 — Recommend

Agent can produce decisions but cannot execute.

### Level 2 — Bounded autonomy

Agent can execute actions inside strict thresholds.

Example:

```text
<$10K transfer
AND
confidence > 0.90
AND
policy_pass = TRUE

→ automatic execution
```

Otherwise:

```text
→ human approval
```

---

# 20. Evaluation Architecture

This should be a first-class subsystem.

```text
                 Agent Workflow
                       │
                       ▼
                 Trace Collector
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Correctness      Grounding      Policy
        │              │              │
        ▼              ▼              ▼
    Golden Set     LLM Judge       Rules
        └──────────────┼──────────────┘
                       ▼
                  Eval Report
```

Create a golden dataset:

```json
{
  "scenario": "Atlanta denim demand spike",
  "expected_behavior": [
    "detect anomaly",
    "inspect inventory",
    "calculate opportunity",
    "require approval if threshold exceeded"
  ]
}
```

Evaluate:

- tool selection
- SQL correctness
- groundedness
- policy compliance
- trajectory
- final decision
- financial calculation
- latency
- cost

---

# 21. BigQuery Agent Query Pattern

Never let an agent freely query every dataset.

Use governed views:

```text
Agent
 ↓
Semantic Layer
 ↓
Authorized BigQuery View
 ↓
GoogleSQL
 ↓
Result
```

Example:

```sql
SELECT
  product_id,
  store_id,
  SUM(net_sales) AS revenue,
  SUM(quantity) AS units,
  AVG(unit_price) AS avg_price
FROM `retail.curated_sales`
WHERE transaction_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 28 DAY)
GROUP BY product_id, store_id;
```

The system should validate:

- dataset access
- query cost
- row limits
- allowed tables
- PII restrictions
- SQL safety

---

# 22. BigQuery Real-Time Decision Query

Example demand velocity:

```sql
WITH recent AS (
  SELECT
    product_id,
    store_id,
    SUM(quantity) AS units_7d
  FROM `retail.fact_sales`
  WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY product_id, store_id
),
baseline AS (
  SELECT
    product_id,
    store_id,
    SUM(quantity) / 4.0 AS units_7d_baseline
  FROM `retail.fact_sales`
  WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 35 DAY)
    AND timestamp < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY product_id, store_id
)
SELECT
  r.product_id,
  r.store_id,
  r.units_7d,
  b.units_7d_baseline,
  SAFE_DIVIDE(
    r.units_7d - b.units_7d_baseline,
    b.units_7d_baseline
  ) AS demand_change
FROM recent r
JOIN baseline b USING (product_id, store_id);
```

Trigger when:

```text
demand_change > threshold
```

---

# 23. Event-Driven Architecture

Use event types:

```text
SALE_CREATED
INVENTORY_UPDATED
PRODUCT_LAUNCHED
PRICE_CHANGED
CAMPAIGN_STARTED
CAMPAIGN_ENDED
DEMAND_ANOMALY
STOCKOUT_RISK
MARKDOWN_RISK
```

Example:

```json
{
  "event_type": "DEMAND_ANOMALY",
  "product_id": "P472",
  "store_id": "ATL127",
  "timestamp": "2026-10-01T20:00:00Z",
  "demand_change": 0.41
}
```

Pub/Sub publishes the event.

The orchestrator consumes it.

---

# 24. Deployment

## Local

```text
Docker Compose
├── API
├── Agent
├── Postgres
├── Redis
└── UI
```

## GCP development

```text
Cloud Run
BigQuery
Pub/Sub
Artifact Registry
Secret Manager
Cloud Logging
Cloud Monitoring
```

## Production-scale

```text
GKE
BigQuery
Pub/Sub
Dataflow
Vertex AI
Artifact Registry
Secret Manager
Cloud Monitoring
Cloud Trace
IAM
VPC
```

---

# 25. Repository Structure

```text
agentic-merchandising-os/
│
├── README.md
├── ARCHITECTURE.md
├── CONTRIBUTING.md
├── Makefile
├── pyproject.toml
├── .env.example
│
├── apps/
│   ├── api/
│   ├── agent-runtime/
│   └── dashboard/
│
├── agents/
│   ├── executive/
│   ├── demand/
│   ├── inventory/
│   ├── pricing/
│   ├── customer/
│   └── marketing/
│
├── orchestration/
│   ├── langgraph/
│   ├── adk/
│   ├── state/
│   └── routing/
│
├── tools/
│   ├── bigquery/
│   ├── inventory/
│   ├── pricing/
│   ├── marketing/
│   └── policy/
│
├── models/
│   ├── demand/
│   ├── elasticity/
│   └── ranking/
│
├── data/
│   ├── schemas/
│   ├── seed/
│   └── synthetic/
│
├── sql/
│   ├── staging/
│   ├── curated/
│   ├── semantic/
│   └── agent_ready/
│
├── evaluation/
│   ├── golden/
│   ├── judges/
│   ├── scenarios/
│   └── reports/
│
├── infra/
│   ├── terraform/
│   ├── cloudrun/
│   ├── gke/
│   ├── pubsub/
│   └── bigquery/
│
├── observability/
│   ├── dashboards/
│   ├── traces/
│   └── alerts/
│
└── tests/
    ├── unit/
    ├── integration/
    ├── agent/
    ├── policy/
    └── evaluation/
```

---

# 26. CI/CD

```text
Developer
   ↓
GitHub
   ↓
Pull Request
   ↓
Unit tests
   ↓
Agent tests
   ↓
Golden dataset evaluation
   ↓
Security scan
   ↓
Container build
   ↓
Artifact Registry
   ↓
Staging
   ↓
Integration tests
   ↓
Production approval
   ↓
Cloud Run / GKE
```

Do not deploy an agent simply because its unit tests pass.

Require:

```text
functional tests
+
trajectory tests
+
policy tests
+
golden dataset
+
cost test
+
latency test
```

---

# 27. Observability

Every agent run should emit:

```text
trace_id
workflow_id
agent_id
user_id
tenant
model
model_version
tool
tool_latency
token_usage
cost
decision
confidence
policy_result
approval
execution_result
```

Example:

```text
workflow_id = wf_82913

ExecutiveAgent
  ├── DemandAgent
  │     ├── BigQuery: 142ms
  │     └── Forecast: 820ms
  │
  ├── InventoryAgent
  │     └── Allocation: 1.2s
  │
  ├── PricingAgent
  │     └── Simulation: 640ms
  │
  └── PolicyEngine
        └── APPROVAL_REQUIRED
```

---

# 28. SLOs

Prototype targets:

| Metric | Target |
|---|---:|
| API availability | 99.9% |
| Read-only decision latency | <10s |
| Agent workflow completion | >99% |
| Tool success | >99.5% |
| Policy violations | 0 |
| Unauthorized writes | 0 |
| SQL failures | <1% |
| Golden-set pass rate | >95% |
| Cost per workflow | tracked |

Production targets should be established from real workload measurements rather than assumed.

---

# 29. Security

Use:

```text
IAM
Workload Identity
Secret Manager
VPC
service accounts
least privilege
audit logs
encryption
policy engine
data classification
```

Agent identity should be explicit.

Do not give:

```text
ExecutiveAgent
→ *
```

Instead:

```text
ExecutiveAgent
→ analytics.read
→ scenario.read
→ approval.request

InventoryAgent
→ inventory.read
→ inventory.optimize
→ inventory.transfer.request
```

---

# 30. PII and Data Governance

Separate:

```text
Customer identity
Customer behavioral features
Aggregated business metrics
```

Agents should generally operate on the minimum data necessary.

Prefer:

```text
customer_segment = "high_value_denim_buyer"
```

over exposing raw personal information.

Use governed BigQuery datasets/views and centralized access policies.

---

# 31. Failure Handling

Agents are probabilistic.

The infrastructure cannot be.

Design for:

```text
timeout
retry
backoff
checkpoint
idempotency
circuit breaker
dead-letter queue
human escalation
```

Never retry a financial mutation blindly.

Use:

```text
idempotency_key
```

for every side-effecting action.

---

# 32. Example End-to-End Workflow

### Event

```text
DENIM_DEMAND_SPIKE
Atlanta
+41%
```

### Step 1

Pub/Sub receives event.

### Step 2

Orchestrator creates:

```text
workflow_id
```

### Step 3

Demand Agent queries BigQuery.

### Step 4

Forecast service calculates:

```text
expected demand
confidence interval
```

### Step 5

Inventory Agent checks:

```text
store inventory
DC inventory
in-transit inventory
```

### Step 6

Pricing Agent evaluates:

```text
price elasticity
margin
markdown risk
```

### Step 7

Marketing Agent evaluates:

```text
campaign ROI
customer response
```

### Step 8

Executive Agent compares:

```text
do nothing
transfer inventory
increase marketing
change price
```

### Step 9

Policy Engine evaluates.

### Step 10

Human approves.

### Step 11

Execution service performs action.

### Step 12

Outcome enters BigQuery.

### Step 13

Evaluation service compares:

```text
predicted outcome
vs
actual outcome
```

### Step 14

Result becomes part of the evaluation/learning dataset.

---

# 33. The Closed-Loop System

The complete system becomes:

```text
             SENSE
               │
               ▼
            BigQuery
               │
               ▼
           DETECT
               │
               ▼
          ORCHESTRATE
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
    Demand  Inventory  Pricing
       └───────┼────────┘
               ▼
             DECIDE
               │
               ▼
           GOVERN
               │
               ▼
            APPROVE
               │
               ▼
            EXECUTE
               │
               ▼
             SELL
               │
               ▼
           MEASURE
               │
               └──────────────► LEARN
```

That feedback loop is the heart of the application.

---

# 34. Prototype Phases

## Phase 1 — Offline simulation

Build:

- synthetic retail dataset
- BigQuery schema
- demand anomaly detector
- LangGraph workflow
- 3 agents
- dashboard

Target:

```text
DEMAND
→ INVENTORY
→ EXECUTIVE
→ HUMAN APPROVAL
```

## Phase 2 — GCP deployment

Add:

- BigQuery
- Pub/Sub
- Cloud Run
- Vertex AI
- Artifact Registry
- Secret Manager

## Phase 3 — Production architecture

Add:

- MCP
- A2A
- policy engine
- agent identity
- observability
- evaluation
- golden datasets
- model gateway
- cost routing

## Phase 4 — Scale

Add:

- GKE
- multi-agent services
- real-time Dataflow
- advanced forecasting
- inventory optimization
- autonomous bounded actions

---

# 35. First MVP

Do **not** start with six agents.

Build this:

```text
             Demand Event
                  │
                  ▼
             Orchestrator
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   Demand Agent        Inventory Agent
        │                   │
        └─────────┬─────────┘
                  ▼
          Executive Agent
                  │
                  ▼
            Policy Engine
                  │
                  ▼
          Human Approval
                  │
                  ▼
              Execute
                  │
                  ▼
             BigQuery
```

Use:

```text
Python
LangGraph
FastAPI
BigQuery
Pub/Sub
Vertex AI / Gemini
Cloud Run
Terraform
Docker
GitHub Actions
```

Then introduce ADK as a second orchestration implementation.

---

# 36. Definition of Done

The MVP is complete when:

- [ ] Synthetic retail data is loaded into BigQuery.
- [ ] BigQuery semantic views exist.
- [ ] Demand anomaly is detected.
- [ ] LangGraph workflow starts from an event.
- [ ] Agents query BigQuery through controlled tools.
- [ ] Inventory recommendation is generated.
- [ ] Business impact is calculated deterministically.
- [ ] Policy engine can block execution.
- [ ] Human approval is required for high-value actions.
- [ ] Approved action is executed through a mock business API.
- [ ] Full workflow trace is stored.
- [ ] Golden scenarios run in CI.
- [ ] Application runs in Docker.
- [ ] Application deploys to Cloud Run.
- [ ] Terraform provisions required infrastructure.
- [ ] Cloud Logging/Monitoring captures runtime behavior.
- [ ] Cost and latency are measurable.
- [ ] README contains architecture and deployment instructions.

---

# 37. Engineering Principle

The central design rule:

> **Agents decide how to use capabilities; deterministic systems decide whether an action is valid.**

And:

> **BigQuery provides governed business context; agents provide reasoning and orchestration; ML provides prediction; optimization provides mathematically constrained decisions; policy provides control; humans retain authority over consequential actions.**

That separation is what makes this architecture suitable for an enterprise rather than a chatbot demo.

---

# 38. References

### Gap Inc.

- Gap Inc. — Principal Engineer, Agentic Data & AI:
  https://www.gapinc.com/en-us/jobs/w24/3/principal-engineer%2C-agentic-data-ai

- Gap Inc. — Principal Engineer, Agentic Applications:
  https://www.gapinc.com/en-us/jobs/w24/3-1/principal-engineer%2C-agentic-applications

- Gap Inc. — Sr. Director, AI & Agentic Platform Engineering:
  https://www.gapinc.com/en-us/jobs/w37/6/sr-director-ai-agentic-platform-engineering

### Google Cloud

- Agentic AI architecture overview:
  https://docs.cloud.google.com/architecture/agentic-ai-overview

- Choose agentic AI architecture components:
  https://docs.cloud.google.com/architecture/choose-agentic-ai-architecture-components

- Multi-agent AI system:
  https://docs.cloud.google.com/architecture/multiagent-ai-system

- Orchestrate access to disparate enterprise systems:
  https://docs.cloud.google.com/architecture/agenticai-orchestrate-access-disparate-systems

- Automate data science workflows:
  https://docs.cloud.google.com/architecture/agentic-ai-data-science

- Agent Development Kit:
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk

- Deploy LangGraph agents:
  https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart

- GKE + ADK + Vertex AI:
  https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/agentic-adk-vertex

---

# 39. Final Architecture

```text
                    ┌──────────────────────────────┐
                    │       RETAIL EVENTS         │
                    │ POS · Web · Inventory · CRM │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                                Pub/Sub
                                   │
                                   ▼
                              Dataflow / ELT
                                   │
                                   ▼
                         ┌───────────────────┐
                         │     BigQuery      │
                         │ Governed Data     │
                         │ Semantic Layer    │
                         │ Agent Context     │
                         └─────────┬─────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │ Agent Orchestrator│
                         │ LangGraph / ADK   │
                         └─────────┬─────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
       Demand                  Inventory                 Pricing
        Agent                    Agent                    Agent
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   ▼
                         ┌───────────────────┐
                         │ Executive Agent   │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │ Policy / Trust    │
                         │ Authorization     │
                         └─────────┬─────────┘
                                   ▼
                            HUMAN APPROVAL
                                   │
                                   ▼
                         ┌───────────────────┐
                         │ Execution Layer   │
                         │ APIs / MCP / A2A  │
                         └─────────┬─────────┘
                                   ▼
                            BUSINESS ACTION
                                   │
                                   ▼
                              REAL WORLD
                                   │
                                   ▼
                             OUTCOME DATA
                                   │
                                   └──────────► BigQuery
                                                  │
                                                  ▼
                                            Evaluation
                                                  │
                                                  ▼
                                             LEARNING
```

**This is the target architecture I would use as the engineering blueprint for the prototype.**
