# Stanchion

**Framework-agnostic reliability primitives for agent pipelines.**

Stanchion gives you the building blocks to make LLM agent pipelines robust:
contract validation, checkpointing, retry policies, cost tracking, and
execution tracing — without tying you to any particular agent framework.

## Install

```bash
pip install stanchion
```

Optional extras:

```bash
pip install stanchion[redis]       # Redis-backed checkpointing
pip install stanchion[langgraph]   # LangGraph adapter
```

## Quick Start

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


# 1. Define contracts
registry = ContractRegistry()
contract = NodeContract(node_id="double", input_schema=InputState, output_schema=OutputState)
registry.register(contract)

# 2. Decorate your node
@stanchion_node("double", contract)
async def double(state: InputState) -> dict:
    return {"result": state.value * 2}

# 3. Configure and run
store = InMemoryStore()
config = RunConfig(
    budget=ExecutionBudget.unlimited(),
    policy_map=default_policy_map(),
)
runner = StanchionRunner(registry, CheckpointManager(store), config)
result = await runner.run([double], InputState(value=5))

print(result.status)       # COMPLETED
print(result.final_state)  # result=10
```

## Next Steps

- [Concepts](concepts.md) — understand the architecture and design decisions
- [API Reference](api/runner.md) — full API documentation
