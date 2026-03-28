# Stanchion

Stanchion is a framework-agnostic reliability library for building robust agent pipelines with explicit contracts, checkpointing, tracing, and failure classification.

## Install

```bash
pip install stanchion
```

## Usage

```python
from pydantic import BaseModel
from stanchion.checkpoint import CheckpointManager, InMemoryStore
from stanchion.contracts import ContractRegistry, NodeContract
from stanchion.cost import ExecutionBudget
from stanchion.failures import default_policy_map
from stanchion.runner import ArmatureRunner, RunConfig, armature_node

class InputState(BaseModel):
    value: int

class OutputState(BaseModel):
    result: int

registry = ContractRegistry()
registry.register(NodeContract(node_id="node1", input_schema=InputState, output_schema=OutputState))

store = InMemoryStore()
checkpoint_manager = CheckpointManager(store)
config = RunConfig(run_id="run1", budget=ExecutionBudget.unlimited(), policy_map=default_policy_map())
runner = ArmatureRunner(registry, checkpoint_manager, config)

@armature_node("node1", NodeContract(node_id="node1", input_schema=InputState, output_schema=OutputState))
async def node1(state: InputState) -> dict:
    return {"result": state.value + 1}

result = await runner.run([node1], InputState(value=1))
print(result.final_state)
```

## Development

Run tests:

```bash
python -m pytest tests/
```

Build the package:

```bash
uv build
```

Install development dependencies:

```bash
pip install -e .[dev]
```

Optional extras:

```bash
pip install stanchion[redis]
pip install stanchion[langgraph]
```
