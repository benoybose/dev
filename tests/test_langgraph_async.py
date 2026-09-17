import asyncio
from typing import TypedDict

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("langgraph")

from langgraph.graph import END, START, StateGraph

from devx.agents.langgraph_supervisor import ConfiguredGraph


class CounterState(TypedDict):
    value: int


def test_configured_graph_uses_async_sqlite_checkpoint_for_ainvoke(tmp_path):
    builder = StateGraph(CounterState)

    def increment(state: CounterState) -> CounterState:
        return {"value": state["value"] + 1}

    builder.add_node("increment", increment)
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    graph = ConfiguredGraph(
        builder.compile(),
        "async-test",
        graph_builder=builder,
        session_db=tmp_path / "checkpoints.db",
    )

    result = asyncio.run(graph.ainvoke({"value": 1}))

    assert result["value"] == 2
