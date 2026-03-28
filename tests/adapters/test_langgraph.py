import asyncio
from typing import Any
import pytest
from pydantic import BaseModel
from stanchion.adapters.langgraph import LangGraphAdapter, armature_langgraph_node
from stanchion.contracts import ContractRegistry, NodeContract, ContractViolation


class StateModel(BaseModel):
    x: int


class OutputModel(BaseModel):
    y: int


class MockStateGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Any] = {}

    def add_node(self, name: str, fn: Any) -> None:
        self.nodes[name] = fn

    def execute(self, name: str, state: Any) -> Any:
        result = self.nodes[name](state)
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return result


@pytest.fixture
def registry():
    reg = ContractRegistry()
    reg.register(NodeContract(node_id="node1", input_schema=StateModel, output_schema=OutputModel))
    return reg


def test_wrap_intercepts_node_and_validates(registry):
    graph = MockStateGraph()

    @armature_langgraph_node("node1", NodeContract(node_id="node1", input_schema=StateModel, output_schema=OutputModel))
    async def node1(state: StateModel) -> dict:
        return {"y": state.x + 1}

    graph.add_node("node1", node1)
    adapter = LangGraphAdapter(registry, object())
    wrapped = adapter.wrap(graph)
    output = wrapped.execute("node1", StateModel(x=1))
    assert output == {"y": 2}


def test_wrap_raises_contract_violation_on_bad_output(registry):
    graph = MockStateGraph()

    @armature_langgraph_node("node1", NodeContract(node_id="node1", input_schema=StateModel, output_schema=OutputModel))
    async def node1(state: StateModel) -> dict:
        return {"z": state.x}

    graph.add_node("node1", node1)
    adapter = LangGraphAdapter(registry, object())
    wrapped = adapter.wrap(graph)

    with pytest.raises(ContractViolation):
        wrapped.execute("node1", StateModel(x=1))


def test_wrap_passthrough_on_valid_state(registry):
    graph = MockStateGraph()

    @armature_langgraph_node("node1", NodeContract(node_id="node1", input_schema=StateModel, output_schema=OutputModel))
    async def node1(state: StateModel) -> dict:
        return {"y": state.x * 2}

    graph.add_node("node1", node1)
    adapter = LangGraphAdapter(registry, object())
    wrapped = adapter.wrap(graph)
    assert wrapped.execute("node1", {"x": 2}) == {"y": 4}
