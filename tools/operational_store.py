"""
Local stand-in for the Cloud SQL (Postgres) operational store defined in
design doc §10.3-B: workflow lifecycle, per-agent run records, candidate
recommendations, human approvals, idempotent executions, and versioned
policy rules.

Implemented in SQLite for Phase 1 (zero external services). Column shapes
intentionally mirror the Postgres DDL in the design doc 1:1 so a Phase 2
Cloud SQL adapter can be swapped in behind these same functions without
touching agent/orchestrator/API code.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "operational.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    status TEXT NOT NULL,
    product_id TEXT,
    store_ids TEXT,              -- JSON array
    risk_score REAL,
    expected_revenue REAL,
    expected_margin REAL,
    trace_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    agent_name TEXT NOT NULL,
    input TEXT,                  -- JSON
    output TEXT,                 -- JSON
    confidence REAL,
    latency_ms INTEGER,
    cost_usd REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    action_type TEXT NOT NULL,
    payload TEXT NOT NULL,       -- JSON
    expected_impact TEXT,        -- JSON
    policy_result TEXT,
    policy_reason TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL REFERENCES recommendations(recommendation_id),
    approver_id TEXT,
    decision TEXT,
    comment TEXT,
    decided_at TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL REFERENCES recommendations(recommendation_id),
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    result TEXT,                 -- JSON
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    condition TEXT NOT NULL,     -- JSON
    action TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);
"""

DEFAULT_POLICY_RULES = [
    {
        "name": "high_value_transfer_requires_approval",
        "condition": {"field": "transfer_value_usd", "op": ">", "value": 10000},
        "action": "REQUIRE_APPROVAL",
    },
    {
        "name": "deep_markdown_requires_approval",
        "condition": {"field": "markdown_percentage", "op": ">", "value": 30},
        "action": "REQUIRE_APPROVAL",
    },
    {
        # Blueprint §19 Level 2 autonomy: auto-execution requires confidence
        # STRICTLY greater than 0.90 -- so anything <= 0.90 must be approved.
        "name": "low_confidence_requires_approval",
        "condition": {"field": "confidence", "op": "<=", "value": 0.90},
        "action": "REQUIRE_APPROVAL",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        existing = conn.execute("SELECT COUNT(*) AS c FROM policy_rules").fetchone()["c"]
        if existing == 0:
            for i, rule in enumerate(DEFAULT_POLICY_RULES, start=1):
                conn.execute(
                    "INSERT INTO policy_rules (rule_id, name, condition, action, active, version, updated_by, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        rule["name"],
                        json.dumps(rule["condition"]),
                        rule["action"],
                        1,
                        1,
                        "system:seed",
                        _now(),
                    ),
                )
        conn.commit()


def reset() -> None:
    with _connect() as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS executions; DROP TABLE IF EXISTS approvals; "
            "DROP TABLE IF EXISTS recommendations; DROP TABLE IF EXISTS agent_runs; "
            "DROP TABLE IF EXISTS workflows; DROP TABLE IF EXISTS policy_rules;"
        )
        conn.commit()
    init_schema()


# ---------------------------------------------------------------------------
# workflows
# ---------------------------------------------------------------------------

def create_workflow(event_id: str, product_id: str, store_ids: list[str], trace_id: str) -> str:
    workflow_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO workflows (workflow_id, event_id, status, product_id, store_ids, "
            " risk_score, expected_revenue, expected_margin, trace_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (workflow_id, event_id, "RUNNING", product_id, json.dumps(store_ids),
             None, None, None, trace_id, _now(), _now()),
        )
        conn.commit()
    return workflow_id


def update_workflow(workflow_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with _connect() as conn:
        conn.execute(
            f"UPDATE workflows SET {set_clause} WHERE workflow_id = ?",
            (*fields.values(), workflow_id),
        )
        conn.commit()


def get_workflow(workflow_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)).fetchone()
        return dict(row) if row else None


def list_workflows(status: Optional[str] = None) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM workflows WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# agent runs (trace)
# ---------------------------------------------------------------------------

def record_agent_run(
    workflow_id: str,
    agent_name: str,
    input_data: dict,
    output_data: dict,
    confidence: float | None,
    latency_ms: int,
    cost_usd: float,
    status: str,
) -> str:
    run_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO agent_runs (run_id, workflow_id, agent_name, input, output, "
            " confidence, latency_ms, cost_usd, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, workflow_id, agent_name, json.dumps(input_data), json.dumps(output_data),
             confidence, latency_ms, cost_usd, status, _now()),
        )
        conn.commit()
    return run_id


def get_trace(workflow_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_runs WHERE workflow_id = ? ORDER BY created_at ASC", (workflow_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# recommendations / approvals / executions
# ---------------------------------------------------------------------------

def create_recommendation(
    workflow_id: str,
    action_type: str,
    payload: dict,
    expected_impact: dict,
    policy_result: str,
    policy_reason: str,
    status: str,
) -> str:
    recommendation_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO recommendations (recommendation_id, workflow_id, action_type, payload, "
            " expected_impact, policy_result, policy_reason, status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (recommendation_id, workflow_id, action_type, json.dumps(payload),
             json.dumps(expected_impact), policy_result, policy_reason, status, _now()),
        )
        conn.commit()
    return recommendation_id


def get_recommendation(recommendation_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        return dict(row) if row else None


def update_recommendation_status(recommendation_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE recommendations SET status = ? WHERE recommendation_id = ?",
            (status, recommendation_id),
        )
        conn.commit()


def list_pending_recommendations() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recommendations WHERE status = 'PROPOSED' ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def record_approval(
    recommendation_id: str, approver_id: str, decision: str, comment: str | None
) -> str:
    approval_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO approvals (approval_id, recommendation_id, approver_id, decision, "
            " comment, decided_at, expires_at) VALUES (?,?,?,?,?,?,?)",
            (approval_id, recommendation_id, approver_id, decision, comment, _now(), None),
        )
        conn.commit()
    return approval_id


def record_execution(
    recommendation_id: str, idempotency_key: str, status: str, result: dict
) -> tuple[str, bool]:
    """Returns (execution_id, was_newly_created). If the idempotency_key already
    exists, the prior execution is returned untouched -- this is the idempotency
    guarantee required by design doc §9 / blueprint §31."""
    with _connect() as conn:
        existing = conn.execute(
            "SELECT * FROM executions WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            return existing["execution_id"], False

        execution_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO executions (execution_id, recommendation_id, idempotency_key, status, "
            " result, executed_at) VALUES (?,?,?,?,?,?)",
            (execution_id, recommendation_id, idempotency_key, status, json.dumps(result), _now()),
        )
        conn.commit()
        return execution_id, True


def get_active_policy_rules() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM policy_rules WHERE active = 1").fetchall()
        return [{**dict(r), "condition": json.loads(r["condition"])} for r in rows]
