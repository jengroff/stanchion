# Concepts

Stanchion is built around five core primitives that work together to make
agent pipelines reliable. Each can be used independently, but they compose
naturally when wired through the `StanchionRunner`.

## Contracts

A **contract** defines the expected input and output schemas for a pipeline
node using Pydantic models. Contracts catch data shape issues at node
boundaries before they propagate downstream.

```python
from pydantic import BaseModel
from stanchion import ContractRegistry, NodeContract

class Query(BaseModel):
    text: str
    max_results: int

class SearchResult(BaseModel):
    urls: list[str]
    scores: list[float]

registry = ContractRegistry()
registry.register(NodeContract(
    node_id="search",
    input_schema=Query,
    output_schema=SearchResult,
))
```

When validation fails, a `ContractViolation` is raised with the node ID,
direction (`"input"` or `"output"`), the raw data, and Pydantic's error
details. The runner classifies contract violations as **terminal** failures —
no retries, because the data shape won't fix itself.

## Failure Classification

Not all errors are equal. Stanchion categorizes every exception into one of
three classes:

| Class | Meaning | Default behavior |
|-------|---------|------------------|
| `RECOVERABLE` | Transient failure (timeouts, rate limits) | Retry up to 3 times with jittered backoff |
| `TERMINAL` | Permanent failure (bad data, logic errors) | Stop immediately |
| `AMBIGUOUS` | Unknown — might resolve on retry | Retry once with short backoff |

Built-in rules handle common exceptions:

- `ContractViolation` → `TERMINAL`
- `BudgetExceeded` → `RECOVERABLE`
- `TimeoutError` → `RECOVERABLE`
- `ValueError` → `AMBIGUOUS`
- Everything else → `AMBIGUOUS`

You can override these with **custom classifiers** — callables that inspect the
exception and context, returning a `FailureClass` or `None` to defer:

```python
from stanchion import FailureClass, RunConfig, ExecutionBudget

def classify_rate_limit(exc, ctx):
    if "rate limit" in str(exc).lower():
        return FailureClass.RECOVERABLE
    return None

config = RunConfig(
    budget=ExecutionBudget.unlimited(),
    classifiers=[classify_rate_limit],
)
```

Custom classifiers are checked first, in order. If none return a result,
the built-in rules apply.

## Retry Policies

Each failure class maps to a **retry policy** controlling:

- **max_retries**: How many times to retry before giving up
- **backoff_seconds**: Maximum backoff (actual delay is jittered between 0 and this value)
- **fallback_node_id**: An alternative node to route to (for future use)

```python
from stanchion import FailureClass, FailurePolicy

custom_policies = {
    FailureClass.RECOVERABLE: FailurePolicy(max_retries=5, backoff_seconds=2.0),
    FailureClass.TERMINAL: FailurePolicy(max_retries=0),
    FailureClass.AMBIGUOUS: FailurePolicy(max_retries=2, backoff_seconds=0.5),
}
```

## Checkpointing

After each successful node execution, the output state is **checkpointed**.
If a pipeline fails partway through, you can resume from the last checkpoint
instead of re-running completed nodes:

```python
from stanchion import RunConfig, ExecutionBudget

# First run fails at node3
config1 = RunConfig(run_id="run-123", budget=ExecutionBudget.unlimited())
result = await runner.run([node1, node2, node3], initial_state)
# result.status == PARTIAL or FAILED

# Resume from node3 — node1 and node2 are skipped, their output loaded from checkpoint
config2 = RunConfig(run_id="run-123", budget=ExecutionBudget.unlimited(), resume_from="node3")
result = await runner.run([node1, node2, node3], initial_state)
# result.status == RESUMED
```

Two storage backends are included:

- **`InMemoryStore`**: For testing and short-lived pipelines. State is kept in-process.
- **`RedisStore`**: For durable, distributed pipelines. Requires `pip install stanchion[redis]`.

Implement the `CheckpointStore` protocol to add your own backend (Postgres,
S3, DynamoDB, etc.).

## Cost Tracking

Stanchion tracks three resource dimensions across your pipeline:

- **Tokens**: Total LLM tokens consumed
- **Cost (USD)**: Total monetary cost
- **Latency (ms)**: Total wall-clock time

Set budget limits on any dimension. When a limit is exceeded, `BudgetExceeded`
is raised — classified as `RECOVERABLE` by default.

```python
from stanchion import ExecutionBudget

budget = ExecutionBudget(
    max_tokens_total=10_000,
    max_cost_usd=0.50,
    max_latency_ms=30_000,
)
```

Nodes can report token usage by returning a tuple:

```python
@stanchion_node("summarize", contract)
async def summarize(state: Input) -> dict:
    result = await llm.generate(state.text)
    return ({"summary": result.text}, result.usage.total_tokens)
```

## Execution Tracing

Every node execution attempt is recorded as a `TraceEvent` capturing:

- Node ID, run ID, and attempt number
- Timestamp and duration
- Input and output state (as dicts)
- Failure class and message (if failed)

The `ExecutionTrace` provides filtering, diffing, replay, and JSON
serialization:

```python
result = await runner.run(nodes, state)

# Inspect failures
for event in result.trace.failures():
    print(f"{event.node_id} attempt {event.attempt}: {event.failure_message}")

# Compare two runs
diffs = trace_a.diff(trace_b)

# Export for monitoring
json_payload = result.trace.to_json()
```

## Pipeline Execution

The `StanchionRunner` ties everything together. For each node in the
sequence it:

1. Validates input against the contract
2. Executes the async node function
3. Validates output against the contract
4. Records resource usage and checks the budget
5. Saves a checkpoint
6. Records a trace event

On failure, it classifies the exception, applies the retry policy, and either
retries with jittered backoff, stops with a terminal status, or gives up after
exhausting retries.

```
Input State → [Contract] → Node → [Contract] → [Budget] → [Checkpoint] → Output State
                              ↑                                              |
                              └──────── retry (if recoverable) ──────────────┘
```
