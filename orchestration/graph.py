"""
Minimal, dependency-free state-graph runner.

Stands in for LangGraph (design doc §10.2 / blueprint §14) for Phase 1, so
the disk-constrained local dev environment doesn't need the full
langchain/langgraph dependency chain. Mirrors the same core concepts the
design doc requires:

  - nodes are plain functions: state -> state
  - edges are linear, or conditional via a router function
  - every node transition is checkpointed (callback) before moving on,
    satisfying blueprint §31's "checkpoint" failure-handling requirement

Swapping this module for real LangGraph in a later phase means replacing
this file only -- the node functions in orchestration/workflow.py don't need
to change, since they're plain `dict -> dict` functions either way.
"""

from __future__ import annotations

from typing import Callable, Optional

NodeFn = Callable[[dict], dict]
RouterFn = Callable[[dict], Optional[str]]


class StateGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, str] = {}
        self._conditional: dict[str, RouterFn] = {}
        self._start: Optional[str] = None

    def add_node(self, name: str, fn: NodeFn) -> "StateGraph":
        self._nodes[name] = fn
        return self

    def set_start(self, name: str) -> "StateGraph":
        self._start = name
        return self

    def add_edge(self, from_node: str, to_node: str) -> "StateGraph":
        self._edges[from_node] = to_node
        return self

    def add_conditional_edge(self, from_node: str, router: RouterFn) -> "StateGraph":
        self._conditional[from_node] = router
        return self

    def run(
        self,
        initial_state: dict,
        on_checkpoint: Callable[[str, dict], None] | None = None,
        stop_after: str | None = None,
    ) -> dict:
        """Run the graph from its start node. If `stop_after` names a node,
        execution halts right after that node runs (used for the human
        approval boundary, where the rest of the graph resumes later from a
        separate entry point rather than blocking this call)."""
        if self._start is None:
            raise ValueError("Graph has no start node")
        state = dict(initial_state)
        current = self._start
        steps = 0
        while current is not None:
            steps += 1
            if steps > 100:
                raise RuntimeError("Graph exceeded max steps -- possible cycle")
            fn = self._nodes.get(current)
            if fn is None:
                raise ValueError(f"Unknown node: {current}")
            state = fn(state)
            if on_checkpoint:
                on_checkpoint(current, state)
            if stop_after is not None and current == stop_after:
                break
            if current in self._conditional:
                current = self._conditional[current](state)
            else:
                current = self._edges.get(current)
        return state
