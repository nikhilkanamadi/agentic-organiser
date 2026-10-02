# Agentic Merchandising OS — Design Document

> **Companion document to** [`agentic_merchandising_os_gcp_bigquery.md`](./agentic_merchandising_os_gcp_bigquery.md).
> That document is the architecture *blueprint* (why, high-level shape, GCP mapping). This document is the
> engineering **design doc**: requirements, concrete architecture decisions, data/API contracts, cloud
> configuration, CI/CD, use cases, edge cases, and error-handling strategy needed to actually build it.

| | |
|---|---|
| **Status** | Draft v1 |
| **Owner** | Merchandising Platform Engineering |
| **Scope** | MVP → Phase 3 (production-grade, pre-scale) |
| **Related** | `agentic_merchandising_os_gcp_bigquery.md` |

---

## 1. Purpose & Scope

Design a production-shaped (but prototype-scale) system that turns retail signals into bounded, auditable,
human-governed business actions — starting with one closed loop:

```text
demand anomaly → investigation → forecast → inventory optimization →
pricing/marketing analysis → executive recommendation → policy gate →
human approval → execution → outcome measurement → learning
```

**In scope:** event ingestion, anomaly detection, multi-agent analysis, policy enforcement, human approval
workflow, execution against (initially mocked) business APIs, full observability/audit trail, evaluation
pipeline, dashboard UI, GCP deployment, CI/CD.

**Out of scope (this doc):** actual integration contracts with Gap-like legacy ERP/OMS/PIM systems (treated as
mocked APIs behind the Execution Layer), full A2A federation across independently-owned agent services,
multi-tenant SaaS packaging.

---

## 2. Goals / Non-Goals

**Goals**
- Separate LLM reasoning from ML prediction, optimization, and deterministic policy (carried over from the
  blueprint's core principle).
- Every consequential action is traceable, policy-checked, and (above a threshold) human-approved.
- Framework portability: orchestration logic isn't hard-locked to LangGraph.
- Ship a working MVP (2 agents + policy + approval + execution + BigQuery) before adding breadth.

**Non-Goals**
- Fully autonomous (no-human) execution at any dollar threshold in the MVP.
- Real-time (<1s) decisioning — the loop is near-real-time (seconds–minutes), not millisecond trading-style.
- Multi-region/multi-tenant isolation in the initial build.

---

## 3. System Overview (Canonical Architecture)

One consolidated diagram, replacing the three overlapping ones in the blueprint doc (§4, §33, §39 there said the
same thing three ways):

```text
 RETAIL EVENTS (POS · Web · Inventory · CRM · Campaign)
        │
        ▼
      Pub/Sub  ──────────────► Dead-letter topic (poison events)
        │
        ▼
  Dataflow / Streaming ETL ─────────────► BigQuery (RAW → STAGING → CURATED → SEMANTIC → AGENT-READY)
        │                                           │
        ▼                                           │
  Anomaly Detector (streaming)                       │
        │ trigger                                    │
        ▼                                            │
┌─────────────────────────────────────────┐          │
│         Agent Orchestrator               │◄─────────┘ (governed read access)
│   LangGraph (primary) / ADK (alt impl)   │
│   Durable state in Cloud SQL (Postgres)  │
└───────────────┬───────────────────────────┘
                │ fan-out
    ┌───────────┼────────────┬─────────────┐
    ▼           ▼            ▼             ▼
 Demand      Inventory    Pricing      Marketing
  Agent        Agent       Agent         Agent
    └───────────┼────────────┴─────────────┘
                ▼
         Executive Agent  (aggregate, compare, recommend)
                ▼
         Policy / Trust Engine  (deterministic — never an LLM)
                ▼
      ┌─────────┴─────────┐
      ▼                   ▼
 Auto-execute          Human Approval
 (bounded, logged)      (dashboard / Slack)
      └─────────┬─────────┘
                ▼
        Execution Layer (idempotent calls to business APIs / MCP tools)
                ▼
          Business systems (mocked initially)
                ▼
          Outcome events ──► BigQuery ──► Evaluation ──► Golden dataset / learning
```

Cross-cutting (touch every box above): **Observability** (traces/metrics/logs), **IAM/Policy enforcement**,
**Model Gateway** (routing + cost tracking).

---

## 4. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | Ingest POS, e-commerce, inventory, campaign, and customer events in near-real-time via Pub/Sub. |
| FR-2 | Detect demand anomalies per product/store using configurable velocity-change and z-score thresholds. |
| FR-3 | Generate demand forecasts with confidence intervals for the affected product/store/channel scope. |
| FR-4 | Compute inventory coverage (on-hand, in-transit, DC) and identify transfer/replenishment candidates. |
| FR-5 | Simulate price/markdown scenarios and compute expected margin and elasticity-based demand response. |
| FR-6 | Evaluate active campaign performance and estimate incremental ROI of budget reallocation. |
| FR-7 | Aggregate specialist agent outputs into one or more ranked recommendations with quantified expected financial impact (revenue, margin, risk). |
| FR-8 | Evaluate every recommendation against deterministic policy rules (financial limit, inventory limit, pricing bounds, compliance, entitlement) before any execution path. |
| FR-9 | Require human approval when action value, markdown %, or confidence breaches configured thresholds; otherwise allow bounded auto-execution. |
| FR-10 | Execute approved actions via idempotent calls to downstream business APIs/tools; record result. |
| FR-11 | Persist a complete workflow trace (inputs, every agent's input/output, policy result, approval decision, execution result, cost, latency) for every run. |
| FR-12 | Measure actual outcome vs. predicted outcome after execution and write both to an evaluation/learning dataset. |
| FR-13 | Provide a dashboard to view active anomalies, pending approvals, recommendation detail with financial impact, and historical workflow outcomes. |
| FR-14 | Enforce role-based access control for read / recommend / approve / execute / admin actions, per agent and per human user. |
| FR-15 | Provide exportable audit logs of all recommendations, approvals, and executions. |
| FR-16 | Support configuration of policy thresholds and autonomy tiers by an authorized admin without code deploy. |
| FR-17 | Run a defined golden-dataset evaluation suite against any new agent/model/prompt version before it is promoted. |
| FR-18 | Allow a human to query episodic memory ("what happened last time we did X for category Y") via the dashboard. |

---

## 5. Non-Functional Requirements

| Category | Requirement | Target |
|---|---|---|
| Availability | API/dashboard uptime | 99.9% |
| Latency | End-to-end agent analysis (anomaly → recommendation ready), excluding human wait | p95 < 10s for MVP scope; reassess once Marketing/Pricing simulation is added — see §12 risk |
| Latency | Dashboard read queries | p95 < 1.5s |
| Reliability | Workflow completion rate (no unhandled failure) | > 99% |
| Reliability | Tool/API call success rate | > 99.5% |
| Correctness | Policy violations reaching execution | 0 (hard requirement — tested in CI, see §10) |
| Correctness | Unauthorized writes | 0 |
| Correctness | SQL/tool failures | < 1% of calls |
| Quality | Golden-dataset pass rate before promotion | > 95% |
| Cost | Cost per workflow | tracked per-run; budget alert if trailing 7-day avg exceeds target |
| Security | Data at rest/in transit | encrypted; least-privilege IAM per agent identity |
| Auditability | Every executed action traceable to approving identity + policy result | 100% |
| Scalability | Target scale for MVP→Phase 3 | ~500 stores, ~50k SKUs, ~5M transactions/day sustained, bursts to 3x |
| Maintainability | Orchestration framework portability | business logic/tool contracts independent of LangGraph vs ADK |
| Extensibility | New agent/tool onboarding | no change to policy engine or execution layer contracts required |
| Usability | Time for an approver to review a pending action | median < 60s to decision from dashboard open |

---

## 6. Actors / Personas

- **Merchandiser / Planner** — reviews recommendations, approves/rejects high-value actions.
- **Category Manager** — sets category-level thresholds, reviews outcomes.
- **Platform/Ops Engineer** — monitors SLOs, incident response, manages deploys.
- **Compliance/Risk Admin** — configures and audits policy rules.
- **Data Scientist** — maintains forecasting/elasticity models, reviews eval reports.
- **System Agents** — Demand, Inventory, Pricing, Marketing, Executive (non-human actors with explicit scoped identities — see §13).

---

## 7. Use Cases

### UC-1: Detect and Resolve a Demand Spike (primary flow)
- **Actor:** System (triggered), Merchandiser (approver)
- **Preconditions:** Streaming anomaly detector active; policy thresholds configured.
- **Main flow:**
  1. POS events push sales velocity for Product 472 in Atlanta up 41% vs. baseline.
  2. Anomaly detector flags `DEMAND_ANOMALY`, publishes event, Orchestrator creates `workflow_id`.
  3. Demand Agent queries BigQuery, runs forecast, returns expected demand + CI.
  4. Inventory Agent checks store/DC/in-transit inventory, proposes transfer candidates.
  5. Pricing Agent and Marketing Agent evaluate in parallel (margin impact, campaign ROI).
  6. Executive Agent ranks options (do nothing / transfer / price change / marketing boost) with expected impact.
  7. Policy Engine evaluates each candidate action; flags any requiring approval.
  8. Dashboard surfaces pending approval to Merchandiser; Merchandiser approves transfer of 240 units.
  9. Execution Layer calls `create_inventory_transfer` idempotently.
  10. Outcome (fulfilled sales, resulting stock levels) streams back to BigQuery.
  11. Evaluation service compares predicted vs. actual outcome; writes to golden/learning dataset.
- **Postconditions:** Workflow marked `COMPLETED`; trace fully persisted.
- **Exceptions:** see §8 Edge Cases (EC-1, EC-4, EC-6).

### UC-2: Approve or Reject a High-Value Recommendation
- **Actor:** Merchandiser
- **Preconditions:** Workflow in `PENDING_APPROVAL` state.
- **Main flow:** Approver opens workflow detail, reviews agent trace + financial impact + policy rationale,
  clicks Approve or Reject (with required comment on reject).
- **Postconditions:** On approve → Execution Layer triggered. On reject → workflow closed as `REJECTED`,
  reason logged, feeds back into evaluation dataset as a negative example.
- **Exceptions:** Approval window expires (see EC-5).

### UC-3: Auto-Execute a Bounded Action
- **Actor:** System only
- **Preconditions:** Action value < $10K AND confidence > 0.90 AND policy pass = true (Level 2 autonomy, §19 of
  blueprint).
- **Main flow:** Policy Engine approves without human step; Execution Layer executes; event logged with
  `approval_type = AUTO`.
- **Postconditions:** Action executed; still fully traced and reversible per §12.

### UC-4: Investigate a Past Decision
- **Actor:** Category Manager
- **Main flow:** Asks dashboard/assistant "what happened the last time we increased inventory for denim in
  Atlanta?" → queries episodic memory store → returns prior workflow(s), decision, outcome, confidence.

### UC-5: Configure Policy Thresholds
- **Actor:** Compliance/Risk Admin
- **Main flow:** Admin updates `markdown_percentage` approval threshold from 30% to 25% via admin UI → change
  versioned, audited, takes effect on next policy evaluation (no redeploy).

### UC-6: Promote a New Agent/Model Version
- **Actor:** Data Scientist / Platform Engineer
- **Main flow:** New prompt/model for Demand Agent runs against golden dataset in CI → pass rate ≥95% and no
  policy-test regressions → promoted to staging → canary in prod behind a flag → full rollout.
- **Exceptions:** Pass rate below threshold → blocked from promotion, reported to owner.

### UC-7: Monitor System Health
- **Actor:** Platform/Ops Engineer
- **Main flow:** Views SLO dashboard (latency, tool success rate, policy violations, cost/workflow); receives
  alert when a threshold breaches; drills into trace viewer for root cause.

---

## 8. Edge Cases

| # | Edge Case | Handling |
|---|---|---|
| EC-1 | Duplicate event delivery (Pub/Sub at-least-once) triggers duplicate workflow | Dedupe on `event_id` with a short-TTL idempotency cache before workflow creation. |
| EC-2 | Anomaly caused by bad data (duplicate POS transaction, test transaction, data entry error) | Demand Agent cross-checks against data-quality signals (duplicate transaction IDs, outlier single-store single-SKU spikes) before forecasting; low-confidence anomalies routed to a "needs review" queue instead of a full workflow. |
| EC-3 | Partial agent failure (e.g., Pricing Agent times out) | Executive Agent proceeds with remaining signals, marks pricing signal `UNAVAILABLE`, lowers overall confidence, and — if confidence drops below auto-execute threshold — forces human approval rather than guessing. |
| EC-4 | Two concurrent workflows compete for the same limited inventory (e.g., two stores both spike) | Inventory Agent's `optimize_allocation` is the single allocator of record; workflows serialize through it (row-level lock on the product/DC inventory record) rather than each assuming full availability. |
| EC-5 | Human approver unavailable; time-sensitive opportunity expires | Approval requests carry an expiry; on expiry, workflow auto-escalates to a secondary approver, then falls back to "opportunity expired — logged, no action," never silently auto-executes above its tier. |
| EC-6 | Executed action later found wrong (bad forecast, policy loophole) | Every write action has a defined compensating action (e.g., reverse transfer, revert price) in the tool contract; Ops can trigger a compensating workflow referencing the original `workflow_id`. |
| EC-7 | In-transit inventory not yet reflected / stale inventory snapshot | Inventory signal carries a `data_as_of` timestamp and staleness flag; Policy Engine requires a freshness threshold for any transfer decision above a value threshold. |
| EC-8 | Model/LLM provider outage or degraded latency | Model Gateway falls back to a secondary model/provider tier; if all unavailable, workflow pauses in `BLOCKED_ON_MODEL` state (not failed) and resumes from checkpoint. |
| EC-9 | Historical event replay / backfill triggers false anomalies | Replay events carry a `replay=true` flag; anomaly detector and orchestrator both ignore replay-flagged events for live triggering (replay only feeds batch BigQuery tables). |
| EC-10 | Negative or impossible inventory values from returns/system errors | Validation layer clamps/flags impossible values (negative on-hand) before they reach agents; flagged rows routed to data-quality alerting, excluded from decisioning until corrected. |
| EC-11 | Golden-dataset pass rate silently drifts over time without a new deploy (model provider changes model behind a stable ID) | Scheduled (not just pre-deploy) golden-set evaluation run nightly; drift alert if pass rate drops below threshold even with no code change. |
| EC-12 | Multi-currency/multi-region store data mixed in one workflow | Store/product dimension carries currency and locale; all financial aggregation normalizes to a reporting currency before cross-store comparison; mixed-currency comparisons are flagged, not silently summed. |
| EC-13 | Policy Engine and Executive Agent disagree (agent recommends, policy denies) | Denial is terminal for that action — not negotiable by the agent. The denial + reason is surfaced in the trace and dashboard as a first-class outcome, not hidden. |

---

## 9. Error Handling & Resilience Strategy

| Failure class | Technique |
|---|---|
| Transient tool/API/network errors | Timeout + exponential backoff with jitter; bounded retry count (e.g., 3) per tool contract. |
| Non-idempotent side effects (transfers, price changes, budget moves) | Mandatory `idempotency_key` per action, generated from `workflow_id` + `action_id`; downstream mock APIs must honor it. |
| Repeated downstream failures | Circuit breaker per external dependency; opens after N consecutive failures, short-circuits to a fallback/human-escalation path, half-open probes to recover. |
| Unprocessable/poison events | Dead-letter queue per Pub/Sub subscription; alert + manual replay tooling, never silently dropped. |
| Long-running workflow crash/restart | LangGraph checkpointing persists state after each node; orchestrator resumes from last checkpoint rather than restarting the workflow. |
| Malformed or out-of-schema tool input/output | JSON-schema validation at the tool boundary (both directions); reject before execution, log full payload for debugging, surface a typed error to the calling agent. |
| Unsafe/unbounded BigQuery queries from agents | Query validated against: allowed dataset/view list, byte-scanned cost ceiling, row-limit, no raw PII columns; rejected queries are logged and returned as a structured policy error, not a raw SQL error. |
| Agent/LLM produces an out-of-contract action (e.g., invents a tool, exceeds declared bounds) | Executive output is schema-validated against the allowed action taxonomy before it ever reaches the Policy Engine; anything non-conforming is discarded and the workflow flagged `AGENT_CONTRACT_VIOLATION` for review — never passed through. |
| Model provider outage/rate limit | Model Gateway fallback chain (reasoning model → fast model → cached/last-known heuristic); workflow pauses rather than fails if no fallback is safe. |
| Financial mutation retried blindly | Explicitly disallowed — retries on write actions always re-check the idempotency key and current state before resubmitting, never "retry on timeout" blindly. |
| Policy violation detected | Hard fail closed: action blocked, no partial execution, reason logged and surfaced; this path has 0-tolerance SLO (§5). |
| Human approval timeout | See EC-5 — escalate, then expire-safe (no default-approve). |
| Data-quality anomalies (negative inventory, duplicate transactions) | Validated and quarantined at ingestion (Dataflow validation step) before reaching curated tables; never silently "fixed" without an audit trail. |
| Observability pipeline itself failing | Trace writes are best-effort async but never block the critical path; a trace-write failure is itself alerted on separately so silent loss of audit trail is detected. |

**General principles carried from the blueprint:** agents are probabilistic, infrastructure is not; every
side-effecting action is idempotent; policy failures fail closed; nothing executes without a trace.

---

## 10. Architecture Decisions

### 10.1 Frontend — "Merchandising Control Center"

| Concern | Choice | Rationale |
|---|---|---|
| Framework | Next.js 14+ (App Router), React, TypeScript | SSR for dashboard shell, good DX, matches blueprint's stated stack. |
| Data fetching | TanStack Query | Caching + refetch semantics fit polling/long-lived workflow views. |
| Live updates | Server-Sent Events (or WebSocket) from API Gateway for workflow/approval state changes | Approval queue needs near-real-time updates without full polling overhead. |
| UI components | Headless component library (e.g., shadcn/ui) + Tailwind | Fast to build, consistent design system. |
| Charts | Lightweight charting lib (e.g., Recharts) for financial-impact and SLO views | Matches evaluation/observability needs. |
| Auth | Google Identity Platform / OIDC via IAP in front of the dashboard | Centralizes auth, integrates with GCP IAM-based RBAC. |

**Key pages:** Live anomaly/workflow feed · Workflow detail (full agent trace, financial impact, policy
rationale, approve/reject) · Approval queue · Policy admin · Evaluation/golden-dataset reports · Episodic
memory / "what happened last time" search · SLO & cost dashboards · Audit log export.

### 10.2 Backend

| Concern | Choice | Rationale |
|---|---|---|
| API Gateway | FastAPI (Python), deployed behind Cloud Load Balancing | Async-friendly, OpenAPI out of the box, matches team's Python-centric stack (agents, ML). |
| Orchestration | LangGraph as primary; ADK maintained as a second implementation behind the same application contract | Blueprint's own framework-portability principle (§15); avoids lock-in. |
| Agent runtime | Containerized agent services (or in-process LangGraph nodes for MVP, split to separate services only when scale/ownership requires it) | Start simple (MVP, §35 of blueprint); split later via A2A if agents need independent deploy cadence. |
| Tool layer | Typed tool contracts (Pydantic models) behind MCP where standardization helps (BigQuery, external APIs) | Matches blueprint §11/§12; enforces input/output schema + auth + side-effect classification centrally. |
| Model access | Model Gateway service in front of Vertex AI (Gemini family) with routing by complexity/cost/latency | Blueprint §16; keeps agents model-agnostic. |
| Policy engine | Standalone deterministic service (rules + thresholds from Postgres config, no LLM involved) | Must be independently testable/auditable; never embedded in agent code. |
| Async/background work | Cloud Tasks / Pub/Sub for execution-layer calls and outcome-measurement jobs | Decouples execution latency from the interactive workflow path. |
| Auth/RBAC | Backed by Identity Platform; role checks enforced in API Gateway + re-checked in Policy Engine (defense in depth) | No single layer is trusted alone for authorization. |

### 10.3 Database Design

Two distinct data stores, matching two distinct jobs — **analytical system of record** vs. **operational
workflow state** (the blueprint only specified the former):

**A. BigQuery — analytical backbone** (zones as defined in the blueprint doc §6-7): `RAW → STAGING → CURATED →
SEMANTIC → AGENT-READY`. Agents only ever read through governed SEMANTIC/AGENT-READY views, never raw tables
(see blueprint §21 and EC above on unsafe queries).

**B. Cloud SQL (Postgres) — operational/transactional state.** BigQuery is not fit for row-level locking,
low-latency transactional reads, or approval workflow state. Proposed schema:

```sql
-- workflow lifecycle
workflows (
  workflow_id UUID PRIMARY KEY,
  event_id TEXT NOT NULL,
  status TEXT NOT NULL,            -- RUNNING | PENDING_APPROVAL | APPROVED | REJECTED | EXECUTED | FAILED | EXPIRED
  product_id TEXT,
  store_ids TEXT[],
  risk_score NUMERIC,
  expected_revenue NUMERIC,
  expected_margin NUMERIC,
  trace_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- per-agent execution record within a workflow
agent_runs (
  run_id UUID PRIMARY KEY,
  workflow_id UUID REFERENCES workflows(workflow_id),
  agent_name TEXT NOT NULL,
  input JSONB,
  output JSONB,
  confidence NUMERIC,
  latency_ms INT,
  cost_usd NUMERIC,
  status TEXT,                     -- OK | TIMEOUT | ERROR | UNAVAILABLE
  created_at TIMESTAMPTZ DEFAULT now()
);

-- candidate actions proposed by the Executive Agent
recommendations (
  recommendation_id UUID PRIMARY KEY,
  workflow_id UUID REFERENCES workflows(workflow_id),
  action_type TEXT NOT NULL,       -- TRANSFER | PRICE_CHANGE | MARKETING_BUDGET | NO_ACTION
  payload JSONB NOT NULL,
  expected_impact JSONB,
  policy_result TEXT,              -- PASS | DENY | APPROVAL_REQUIRED
  policy_reason TEXT,
  status TEXT,                     -- PROPOSED | APPROVED | REJECTED | AUTO_APPROVED | EXPIRED
  created_at TIMESTAMPTZ DEFAULT now()
);

-- human decisions
approvals (
  approval_id UUID PRIMARY KEY,
  recommendation_id UUID REFERENCES recommendations(recommendation_id),
  approver_id TEXT,
  decision TEXT,                   -- APPROVE | REJECT
  comment TEXT,
  decided_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);

-- idempotent execution record
executions (
  execution_id UUID PRIMARY KEY,
  recommendation_id UUID REFERENCES recommendations(recommendation_id),
  idempotency_key TEXT UNIQUE NOT NULL,
  status TEXT,                     -- PENDING | SUCCESS | FAILED | COMPENSATED
  result JSONB,
  executed_at TIMESTAMPTZ
);

-- versioned, admin-editable policy configuration
policy_rules (
  rule_id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  condition JSONB NOT NULL,        -- e.g. {"field": "transfer_value", "op": ">", "value": 50000}
  action TEXT NOT NULL,            -- REQUIRE_APPROVAL | DENY
  active BOOLEAN DEFAULT TRUE,
  version INT NOT NULL,
  updated_by TEXT,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- RBAC
users (user_id TEXT PRIMARY KEY, email TEXT, role TEXT, active BOOLEAN);
```

**C. Cache/session:** Memorystore (Redis) for idempotency-check caching, SSE/session state, and hot read-through
cache for dashboard polling.

**D. Semantic/episodic memory:** Vertex AI Vector Search (or equivalent) for document retrieval (policy docs,
tech packs) and episodic decision memory (UC-4), as specified in blueprint §17.

### 10.4 Cloud Configuration (GCP)

| Layer | Service | Purpose |
|---|---|---|
| Compute (prototype) | Cloud Run | API gateway + orchestrator, fast iteration. |
| Compute (scale, Phase 4) | GKE | When independent agent services, custom networking, or platform-level orchestration is needed. |
| Messaging | Pub/Sub (+ dead-letter topics) | Event ingestion, workflow triggers, outcome events. |
| Streaming ETL | Dataflow | Validation, enrichment, BigQuery load. |
| Analytical store | BigQuery | RAW→AGENT-READY zones; governed views only exposed to agents. |
| Operational store | Cloud SQL (Postgres) | Workflow/approval/policy state (§10.3). |
| Cache | Memorystore (Redis) | Idempotency cache, session/read-through cache. |
| Models | Vertex AI (Gemini family) + Vertex AI Vector Search | LLM reasoning, embeddings, semantic memory. |
| Secrets | Secret Manager | API keys, DB credentials, model credentials. |
| Identity | IAM + Workload Identity + Identity Platform/IAP | Per-agent and per-human-role least-privilege access. |
| Networking | VPC, Serverless VPC Connector, Cloud Armor (WAF) on the public dashboard/API | Isolation + basic edge protection. |
| Registry | Artifact Registry | Container images. |
| Build | Cloud Build (or GitHub Actions runners) | CI build/test/deploy steps. |
| IaC | Terraform | All of the above provisioned declaratively (`infra/terraform` per blueprint repo layout). |
| Observability | Cloud Logging, Cloud Monitoring, Cloud Trace | Structured logs, SLO dashboards, distributed tracing across agents/tools. |

**Agent identity example (least privilege, from blueprint §29, retained as a hard requirement):**

```text
ExecutiveAgent  → analytics.read, scenario.read, approval.request
InventoryAgent  → inventory.read, inventory.optimize, inventory.transfer.request
PricingAgent    → pricing.read, pricing.simulate
MarketingAgent  → campaign.read, campaign.simulate
```
No agent identity is ever granted a blanket `*` scope.

### 10.5 API Design (key endpoints)

```text
POST   /v1/events                       (internal, Pub/Sub push subscription target)
GET    /v1/workflows                    list / filter workflows
GET    /v1/workflows/{id}               workflow detail
GET    /v1/workflows/{id}/trace         full agent trace
POST   /v1/workflows/{id}/approve       {approver_id, comment}
POST   /v1/workflows/{id}/reject        {approver_id, reason}
GET    /v1/recommendations?status=...   approval queue
GET    /v1/policies                     list policy rules
POST   /v1/policies                     create/update rule (admin role only)
GET    /v1/memory/search?query=...      episodic/semantic memory search (UC-4)
GET    /v1/metrics/slo                  SLO dashboard data
GET    /v1/evaluations/latest           golden-dataset eval report
```

All write endpoints require `Idempotency-Key` header and enforce RBAC server-side (not just in the UI).

---

## 11. CI/CD

```text
Developer → PR → GitHub Actions:
   ├── lint + type-check
   ├── unit tests
   ├── agent trajectory tests (does the graph take the expected path for fixed scenarios?)
   ├── policy tests (0-tolerance: deny-path tests must all pass)
   ├── golden-dataset evaluation (≥95% pass rate gate)
   ├── SAST + dependency/container security scan
   ├── terraform plan (infra changes only) — posted to PR for review
   └── build + push container → Artifact Registry
PR merged to main →
   ├── terraform apply (dev/staging, auto)
   ├── deploy to staging (Cloud Run revision / GKE)
   ├── integration tests against staging (incl. mocked business APIs)
   ├── nightly golden-dataset drift check (scheduled, not just pre-deploy — see EC-11)
   └── manual production approval gate
   → deploy to prod:
        Cloud Run: new revision, gradual traffic shift (canary %), auto-rollback on error-rate/latency SLO breach
        GKE (Phase 4): rolling/canary deploy via standard k8s strategy
```

**Branching:** trunk-based with short-lived feature branches; `main` always deployable to staging.
**Environments:** `dev` (ephemeral, per-PR optional) → `staging` → `prod`.
**Rollback:** previous Cloud Run revision kept warm; Terraform state versioned; DB migrations must be
backward-compatible for one release (no destructive migration in the same release as the code that needs it).
**Gate that cannot be bypassed:** policy tests and golden-dataset threshold — a green build with a failing
policy test or sub-threshold golden set must not be deployable, per blueprint §26 ("do not deploy an agent
simply because its unit tests pass").

---

## 12. Observability & SLOs

Carried from the blueprint (§27-28) with the trace-loss safeguard added in §9: every workflow emits
`trace_id, workflow_id, agent_id, tool, tool_latency, token_usage, cost, decision, confidence, policy_result,
approval, execution_result`. SLO targets are listed in §5 above as the authoritative table (consolidating the
blueprint's SLO table into this doc's NFRs).

**Known risk to monitor explicitly:** the <10s end-to-end latency target (NFR, §5) assumes a sequential
Demand→Inventory→Pricing→Marketing→Executive chain. Instrument per-agent latency from day one so this target is
validated against real measurements before being treated as committed, not just assumed as in the original
blueprint.

---

## 13. Security & Compliance

- Least-privilege, explicit per-agent IAM scopes (§10.4) — no agent ever gets a wildcard grant.
- Defense-in-depth RBAC: enforced in API Gateway *and* re-checked in Policy Engine.
- **Prompt-injection / tool-use safety** (gap identified in review of the original blueprint, addressed here):
  - Any externally-sourced text that enters an agent's context (product descriptions, campaign copy, customer
    event payloads) is treated as untrusted data, never as instructions.
  - Executive Agent output is schema-validated against a closed action taxonomy before reaching the Policy
    Engine (§9) — an agent cannot invent a new action type or exceed declared tool bounds.
  - Tool calls are capability-scoped per agent identity; even a fully "convinced" agent cannot call a tool
    outside its granted scope.
- PII minimization: agents operate on aggregated/segment-level data (`customer_segment = "high_value_denim_buyer"`)
  rather than raw PII, per blueprint §30; raw PII lives in governed, separately access-controlled views.
- All data encrypted at rest and in transit; secrets only via Secret Manager, never in env files/images.
- Full audit trail is immutable (append-only) and exportable for compliance review.

---

## 14. Rollout Plan (condensed from blueprint §34-36)

1. **MVP:** Demand Agent + Inventory Agent + Executive Agent + Policy Engine + Human Approval + mocked
   execution, synthetic BigQuery dataset, Cloud Run, golden scenarios in CI. (Definition of Done: see blueprint
   §36 checklist — still authoritative.)
2. **Phase 2:** Add Pricing + Marketing agents, real Pub/Sub/Dataflow streaming path, Vertex AI model gateway.
3. **Phase 3:** MCP/A2A boundaries if agents need independent ownership/deploy cadence, full observability +
   evaluation pipeline, cost-aware model routing.
4. **Phase 4:** GKE migration if/when scale or platform needs exceed Cloud Run, advanced forecasting/
   optimization, bounded autonomous execution at higher tiers.

---

## 15. Open Questions / Assumptions

- Is this single-tenant (one retailer) for the foreseeable scope, or should multi-tenancy be designed in now?
  **Assumption: single-tenant for MVP/Phase 2–3.**
- What is the real SLA for the downstream business APIs (inventory/pricing/campaign systems) the Execution
  Layer will eventually call? Mocked APIs in MVP should match the latency/error profile of the real ones once
  known, to avoid false confidence in the <10s target.
- Who owns policy threshold changes in production (Compliance/Risk Admin role) — confirm org ownership before
  Phase 2.
- Model provider strategy: single provider (Gemini via Vertex AI) vs. multi-provider fallback — affects Model
  Gateway design in §10.2.

---

## 16. Appendix: Tech Stack Summary

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, TanStack Query, Tailwind, shadcn/ui, Recharts |
| API Gateway | FastAPI (Python) |
| Orchestration | LangGraph (primary), ADK (secondary implementation) |
| Agents/Tools | Python, Pydantic schemas, MCP for standardized tool boundary |
| Models | Vertex AI (Gemini family), Vertex AI Vector Search |
| Operational DB | Cloud SQL (Postgres) |
| Analytical DB | BigQuery |
| Cache | Memorystore (Redis) |
| Messaging | Pub/Sub |
| Streaming ETL | Dataflow |
| Compute | Cloud Run (prototype) → GKE (scale) |
| IaC | Terraform |
| CI/CD | GitHub Actions + Cloud Build |
| Observability | Cloud Logging, Cloud Monitoring, Cloud Trace |
| Security | IAM, Workload Identity, Secret Manager, Identity Platform/IAP, Cloud Armor |
