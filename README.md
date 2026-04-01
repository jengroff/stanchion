# Stanchion

Framework-agnostic reliability primitives for building robust agent pipelines with explicit contracts, checkpointing, tracing, and failure classification.

## Install

```bash
pip install stanchion
```

## Usage

```python
from pydantic import BaseModel

from stanchion import (
    CheckpointManager,
    ContractRegistry,
    ExecutionBudget,
    InMemoryStore,
    NodeContract,
    RunConfig,
    StanchionRunner,
    default_policy_map,
    stanchion_node,
)


class InputState(BaseModel):
    value: int


class OutputState(BaseModel):
    result: int


registry = ContractRegistry()
contract = NodeContract(node_id="node1", input_schema=InputState, output_schema=OutputState)
registry.register(contract)

store = InMemoryStore()
checkpoint_manager = CheckpointManager(store)
config = RunConfig(run_id="run1", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
runner = StanchionRunner(registry, checkpoint_manager, config)


@stanchion_node("node1", contract)
async def node1(state: InputState) -> dict:
    return {"result": state.value + 1}


result = await runner.run([node1], InputState(value=1))
print(result.final_state)
```

## Documentation

Full documentation including a concepts guide and API reference is available at the [docs site](https://jengroff.github.io/stanchion).

## Development

Run tests:

```bash
python -m pytest tests/ -v --cov=stanchion --cov-fail-under=90
```

Lint and type check:

```bash
ruff check stanchion/ tests/
uv run ty check stanchion/
```

Build the package:

```bash
uv build
```

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Optional extras:

```bash
pip install stanchion[redis]
pip install stanchion[langgraph]
```
