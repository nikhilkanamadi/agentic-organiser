from tools.contracts import ActionType, PolicyResult, RecommendationCandidate
from tools.policy import evaluate


def _candidate(**overrides) -> RecommendationCandidate:
    base = dict(
        action_type=ActionType.TRANSFER,
        payload={"transfer_value_usd": 1000, "markdown_percentage": 0},
        expected_revenue_impact=5000,
        expected_margin_impact=2000,
        confidence=0.95,
        rationale="test",
    )
    base.update(overrides)
    return RecommendationCandidate(**base)


def test_low_value_high_confidence_passes_without_approval():
    result = evaluate(_candidate())
    assert result.result == PolicyResult.PASS


def test_high_value_transfer_requires_approval():
    candidate = _candidate(payload={"transfer_value_usd": 50_000, "markdown_percentage": 0})
    result = evaluate(candidate)
    assert result.result == PolicyResult.APPROVAL_REQUIRED
    assert "high_value_transfer_requires_approval" == result.matched_rule


def test_low_confidence_requires_approval():
    candidate = _candidate(confidence=0.70)
    result = evaluate(candidate)
    assert result.result == PolicyResult.APPROVAL_REQUIRED
    assert "low_confidence_requires_approval" == result.matched_rule


def test_deep_markdown_requires_approval():
    candidate = _candidate(
        action_type=ActionType.PRICE_CHANGE,
        payload={"transfer_value_usd": 0, "markdown_percentage": 45},
    )
    result = evaluate(candidate)
    assert result.result == PolicyResult.APPROVAL_REQUIRED
    assert "deep_markdown_requires_approval" == result.matched_rule
