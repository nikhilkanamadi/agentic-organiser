"""
Minimal Model Gateway (design doc §10.2 / blueprint §16).

Phase 1 scope: agents need to produce a human-readable rationale string for
each recommendation. Rather than hard-wiring every agent to a specific LLM
provider, this module is the single seam all agents call through.

- If ANTHROPIC_API_KEY is set, rationale generation goes through the real
  Claude API.
- Otherwise it falls back to a deterministic, templated explanation built
  from the same structured inputs. This keeps the MVP runnable with zero
  external dependencies/credentials, and keeps CI/golden-dataset evaluation
  deterministic (no model-sampling flakiness in trajectory tests).

Swapping providers (Vertex AI/Gemini per the GCP blueprint, or another
Claude model) means changing this one module -- never the agents.
"""

from __future__ import annotations

import os


def explain(summary: str, facts: dict) -> str:
    """Produce a short rationale string for a recommendation or decision.

    `summary` is a one-line description of what's being explained.
    `facts` are the structured numbers/strings backing the explanation.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return _explain_via_llm(summary, facts, api_key)
    return _explain_deterministic(summary, facts)


def _explain_deterministic(summary: str, facts: dict) -> str:
    fact_str = "; ".join(f"{k}={v}" for k, v in facts.items())
    return f"{summary} ({fact_str})"


def _explain_via_llm(summary: str, facts: dict, api_key: str) -> str:  # pragma: no cover
    try:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"Explain in one concise sentence, for a merchandising analyst, "
            f"the following decision: {summary}. Supporting facts: {facts}."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception:
        # Never let a model-gateway failure break a deterministic workflow --
        # fall back rather than raise (design doc §9: graceful degradation).
        return _explain_deterministic(summary, facts)
