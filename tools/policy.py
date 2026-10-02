"""
Deterministic Policy Engine.

Design-doc references:
  - §10.2: "Standalone deterministic service (rules + thresholds from Postgres
    config, no LLM involved) ... never embedded in agent code."
  - §9 error handling: "Policy violation detected -> hard fail closed: action
    blocked, no partial execution."
  - §13 security: RBAC/policy is defense-in-depth, re-checked here independent
    of whatever an agent decided.

This module NEVER calls an LLM. Rules are plain comparisons loaded from the
operational store's policy_rules table (admin-editable without redeploy, per
design doc §10.5 /v1/policies and use case UC-5).
"""

from __future__ import annotations

from tools.contracts import PolicyEvaluation, PolicyResult, RecommendationCandidate
from tools.operational_store import get_active_policy_rules

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate(candidate: RecommendationCandidate) -> PolicyEvaluation:
    """
    Evaluate a single recommendation candidate against all active policy
    rules. Fails closed: if a rule's field is missing from the candidate's
    evaluation context, the rule is skipped (treated as not matched) rather
    than raising -- but an explicit DENY always wins over APPROVAL_REQUIRED,
    and APPROVAL_REQUIRED always wins over PASS.
    """
    context = _evaluation_context(candidate)
    rules = get_active_policy_rules()

    outcome = PolicyResult.PASS
    reason = "No policy rule matched; within autonomous bounds."
    matched_rule = None

    for rule in rules:
        field = rule["condition"].get("field")
        op = rule["condition"].get("op")
        threshold = rule["condition"].get("value")
        if field not in context or op not in _OPS:
            continue

        if _OPS[op](context[field], threshold):
            rule_action = rule["action"]
            if rule_action == "DENY":
                return PolicyEvaluation(
                    result=PolicyResult.DENY,
                    reason=f"Denied by rule '{rule['name']}': {field} {op} {threshold} "
                           f"(actual={context[field]})",
                    matched_rule=rule["name"],
                )
            if rule_action == "REQUIRE_APPROVAL" and outcome != PolicyResult.DENY:
                outcome = PolicyResult.APPROVAL_REQUIRED
                reason = (
                    f"Approval required by rule '{rule['name']}': {field} {op} {threshold} "
                    f"(actual={context[field]})"
                )
                matched_rule = rule["name"]

    return PolicyEvaluation(result=outcome, reason=reason, matched_rule=matched_rule)


def _evaluation_context(candidate: RecommendationCandidate) -> dict:
    payload = candidate.payload or {}
    return {
        "confidence": candidate.confidence,
        "transfer_value_usd": payload.get("transfer_value_usd", 0),
        "markdown_percentage": payload.get("markdown_percentage", 0),
        "expected_revenue_impact": candidate.expected_revenue_impact,
        "expected_margin_impact": candidate.expected_margin_impact,
    }
