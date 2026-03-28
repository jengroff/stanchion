import pytest
from pydantic import BaseModel
from stanchion.checkpoint import CheckpointManager, InMemoryStore
from stanchion.contracts import ContractRegistry, NodeContract
from stanchion.cost import ExecutionBudget
from stanchion.failures import FailureClass, default_policy_map
from stanchion.runner import ArmatureRunner, RunConfig, armature_node
from stanchion.trace import RunStatus


class InputState(BaseModel):
    value: int


class NodeOneOutput(BaseModel):
    result: int


class NodeTwoOutput(BaseModel):
    total: int


@pytest.mark.asyncio
async def test_happy_path_full_sequence():
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    registry.register(NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    @armature_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return {"result": state.value + 1}

    @armature_node("node2", NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    async def node2(state: NodeOneOutput) -> dict:
        return {"total": state.result * 2}

    config = RunConfig(run_id="run1", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
    runner = ArmatureRunner(registry, manager, config)
    result = await runner.run([node1, node2], InputState(value=3))

    assert result.status == RunStatus.COMPLETED
    assert result.final_state.total == 8
    assert len(result.trace) == 2
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_terminal_failure_returns_failed_with_partial_trace():
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    @armature_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return {"bad": "value"}

    config = RunConfig(run_id="run2", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
    runner = ArmatureRunner(registry, manager, config)
    result = await runner.run([node1], InputState(value=1))

    assert result.status == RunStatus.FAILED
    assert len(result.trace) == 1
    assert list(result.trace)[0].failure == FailureClass.TERMINAL


@pytest.mark.asyncio
async def test_recoverable_retries_then_returns_partial():
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    call_count = {"node1": 0}

    @armature_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        call_count["node1"] += 1
        raise TimeoutError("transient")

    config = RunConfig(run_id="run3", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
    runner = ArmatureRunner(registry, manager, config)
    result = await runner.run([node1], InputState(value=1))

    assert result.status == RunStatus.PARTIAL
    assert call_count["node1"] == 3
    assert len(result.trace) == 3
    assert all(event.failure == FailureClass.RECOVERABLE for event in result.trace)


@pytest.mark.asyncio
async def test_resume_skips_completed_nodes_and_loads_checkpoint():
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    registry.register(NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    @armature_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return {"result": state.value + 2}

    @armature_node("node2", NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    async def node2(state: NodeOneOutput) -> dict:
        return {"total": state.result * 3}

    config1 = RunConfig(run_id="run4", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
    runner1 = ArmatureRunner(registry, manager, config1)
    first = await runner1.run([node1, node2], InputState(value=1))
    assert first.status == RunStatus.COMPLETED
    assert len(first.trace) == 2

    call_count = {"node1": 0, "node2": 0}

    @armature_node("node2", NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    async def resumed_node2(state: NodeOneOutput) -> dict:
        call_count["node2"] += 1
        return {"total": state.result * 5}

    @armature_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def counted_node1(state: InputState) -> dict:
        call_count["node1"] += 1
        raise AssertionError("node1 should not run")

    config2 = RunConfig(run_id="run4", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map(), resume_from="node2")
    runner2 = ArmatureRunner(registry, manager, config2)
    result = await runner2.run([counted_node1, resumed_node2], InputState(value=1))

    assert result.status == RunStatus.RESUMED
    assert len(result.trace) == 1
    assert result.final_state.total == 15
    assert call_count["node1"] == 0
    assert call_count["node2"] == 1
