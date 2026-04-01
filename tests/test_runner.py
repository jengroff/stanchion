import pytest
from pydantic import BaseModel

from stanchion.checkpoint import CheckpointManager, InMemoryStore
from stanchion.contracts import ContractRegistry, NodeContract
from stanchion.cost import ExecutionBudget
from stanchion.failures import FailureClass, FailurePolicy, default_policy_map
from stanchion.runner import ArmatureRunner, RunConfig, StanchionRunner, armature_node, stanchion_node
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

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return {"result": state.value + 1}

    @stanchion_node("node2", NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    async def node2(state: NodeOneOutput) -> dict:
        return {"total": state.result * 2}

    config = RunConfig(run_id="run1", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
    runner = StanchionRunner(registry, manager, config)
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

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return {"bad": "value"}

    config = RunConfig(run_id="run2", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
    runner = StanchionRunner(registry, manager, config)
    result = await runner.run([node1], InputState(value=1))

    assert result.status == RunStatus.FAILED
    assert len(result.trace) == 1
    assert next(iter(result.trace)).failure == FailureClass.TERMINAL
    # On failure, final_state should be the last valid state (the input)
    assert result.final_state is not None


@pytest.mark.asyncio
async def test_recoverable_retries_then_returns_partial():
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    call_count = {"node1": 0}

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        call_count["node1"] += 1
        raise TimeoutError("transient")

    policy_map = default_policy_map()
    policy_map[FailureClass.RECOVERABLE] = FailurePolicy(max_retries=3, backoff_seconds=0.0)
    config = RunConfig(run_id="run3", budget=ExecutionBudget.unlimited(), policy_map=policy_map)
    runner = StanchionRunner(registry, manager, config)
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

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return {"result": state.value + 2}

    @stanchion_node("node2", NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    async def node2(state: NodeOneOutput) -> dict:
        return {"total": state.result * 3}

    config1 = RunConfig(run_id="run4", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
    runner1 = StanchionRunner(registry, manager, config1)
    first = await runner1.run([node1, node2], InputState(value=1))
    assert first.status == RunStatus.COMPLETED
    assert len(first.trace) == 2

    call_count = {"node1": 0, "node2": 0}

    @stanchion_node("node2", NodeContract(node_id="node2", input_schema=NodeOneOutput, output_schema=NodeTwoOutput))
    async def resumed_node2(state: NodeOneOutput) -> dict:
        call_count["node2"] += 1
        return {"total": state.result * 5}

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def counted_node1(state: InputState) -> dict:
        call_count["node1"] += 1
        raise AssertionError("node1 should not run")

    config2 = RunConfig(
        run_id="run4", budget=ExecutionBudget.unlimited(),
        policy_map=default_policy_map(), resume_from="node2",
    )
    runner2 = StanchionRunner(registry, manager, config2)
    result = await runner2.run([counted_node1, resumed_node2], InputState(value=1))

    assert result.status == RunStatus.RESUMED
    assert len(result.trace) == 1
    assert result.final_state.total == 15
    assert call_count["node1"] == 0
    assert call_count["node2"] == 1


@pytest.mark.asyncio
async def test_backwards_compat_aliases():
    """Verify ArmatureRunner and armature_node still work."""
    assert ArmatureRunner is StanchionRunner
    assert armature_node is stanchion_node


@pytest.mark.asyncio
async def test_custom_classifier_is_used():
    """Verify custom classifiers from RunConfig are passed to classify()."""
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        raise ValueError("custom classified")

    def make_terminal(exc, ctx):
        if isinstance(exc, ValueError):
            return FailureClass.TERMINAL
        return None

    config = RunConfig(
        run_id="run_classifier",
        budget=ExecutionBudget.unlimited(),
        classifiers=[make_terminal],
    )
    runner = StanchionRunner(registry, manager, config)
    result = await runner.run([node1], InputState(value=1))

    # ValueError would normally be AMBIGUOUS (1 retry), but our classifier makes it TERMINAL
    assert result.status == RunStatus.FAILED
    assert len(result.trace) == 1
    assert next(iter(result.trace)).failure == FailureClass.TERMINAL


@pytest.mark.asyncio
async def test_budget_exceeded_during_run():
    """Verify budget enforcement triggers during a run."""
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return ({"result": state.value + 1}, 100)  # 100 tokens

    config = RunConfig(
        run_id="run_budget",
        budget=ExecutionBudget(max_tokens_total=50),
        policy_map={
            FailureClass.RECOVERABLE: FailurePolicy(max_retries=0, backoff_seconds=0.0),
            FailureClass.TERMINAL: FailurePolicy(max_retries=0, backoff_seconds=0.0),
            FailureClass.AMBIGUOUS: FailurePolicy(max_retries=0, backoff_seconds=0.0),
        },
    )
    runner = StanchionRunner(registry, manager, config)
    result = await runner.run([node1], InputState(value=1))

    # BudgetExceeded is RECOVERABLE, but with 0 retries it becomes PARTIAL
    assert result.status == RunStatus.PARTIAL


@pytest.mark.asyncio
async def test_empty_node_sequence():
    """An empty node sequence should complete immediately with the initial state."""
    registry = ContractRegistry()
    store = InMemoryStore()
    manager = CheckpointManager(store)

    config = RunConfig(run_id="run_empty", budget=ExecutionBudget.unlimited())
    runner = StanchionRunner(registry, manager, config)
    result = await runner.run([], InputState(value=42))

    assert result.status == RunStatus.COMPLETED
    assert result.final_state.value == 42
    assert len(result.trace) == 0


@pytest.mark.asyncio
async def test_tuple_return_with_tokens():
    """Verify nodes can return (dict, tokens) tuples."""
    registry = ContractRegistry()
    registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    store = InMemoryStore()
    manager = CheckpointManager(store)

    @stanchion_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=NodeOneOutput))
    async def node1(state: InputState) -> dict:
        return ({"result": state.value + 1}, 42)

    config = RunConfig(run_id="run_tokens", budget=ExecutionBudget.unlimited())
    runner = StanchionRunner(registry, manager, config)
    result = await runner.run([node1], InputState(value=1))

    assert result.status == RunStatus.COMPLETED
    assert result.total_tokens == 42
    assert result.final_state.result == 2
