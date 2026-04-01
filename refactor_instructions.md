# Stanchion v0.1.1 — Audit Fix Instructions

## Fix 1 — UnboundLocalError in ArmatureRunner (URGENT)

In `stanchion/runner.py`, the `ArmatureRunner.run` method has a latent `UnboundLocalError`. Inside the `while True` retry loop, `input_model` is assigned by `self.registry.validate_input(...)`. If that call raises a `ContractViolation`, the except block then references `input_model` in the `TraceEvent` constructor — but it was never bound.

Fix: assign `input_model = None` before the `while True` loop for each node, then guard the `TraceEvent` construction in the except block: use `input_model.model_dump() if input_model is not None else {}`.

---

## Fix 2 — Misleading class-level annotations on ContractViolation and BudgetExceeded

In `stanchion/contracts.py`, `ContractViolation` subclasses `Exception` and has class-level annotations (`node_id`, `direction`, `raw`, `errors`) that look like dataclass fields but are not. The same pattern exists on `BudgetExceeded` in `stanchion/cost.py`.

Fix: remove the class-level annotations from both classes. The attributes are already set correctly in each `__init__`. Removing the annotations eliminates the misleading implied contract and resolves strict mypy warnings about attribute resolution on exception types.

---

## Fix 3 — ExecutionTrace.diff excludes time-sensitive fields

In `stanchion/trace.py`, `ExecutionTrace.diff` compares `TraceEvent` instances using dataclass equality, which includes `timestamp_utc` and `duration_ms`. This makes `diff` useless for comparing two traces of the same logical execution since those fields will always differ.

Fix: rewrite the diff comparison for matched keys to compare only the logical fields: `node_id`, `run_id`, `attempt`, `input_state`, `output_state`, `failure`, and `failure_message`. Exclude `timestamp_utc` and `duration_ms` from equality when detecting differences.

---

## Fix 4 — LangGraphAdapter discards validated output model

In `stanchion/adapters/langgraph.py`, `LangGraphAdapter._wrap_node` validates the output dict against the contract but discards the validated `BaseModel`, returning the original raw result instead.

Fix: capture the return value of `self._validator(contract, "output", output_dict)` into a variable named `output_model`. Return `output_model.model_dump()` instead of the original `result`. This ensures downstream nodes receive output that has passed through Pydantic validation rather than the raw unvalidated dict.

---

## Fix 5 — Redis key prefix mismatch

In `stanchion/checkpoint.py`, `RedisStore._state_key` and `_schema_key` use the prefix `armature:` — a leftover from a prior rename. The package is named `stanchion`.

Fix: update both `_state_key` and `_schema_key` to use the prefix `stanchion:` instead of `armature:`. Also update the scan pattern in `RedisStore.delete` from `armature:{run_id}:*` to `stanchion:{run_id}:*`.

---

## Fix 6 — Add retry jitter to ArmatureRunner backoff

In `stanchion/runner.py`, `ArmatureRunner.run` calls `asyncio.sleep(policy.backoff_seconds)` with a fixed value. Under concurrent load this causes retry thundering herd.

Fix: replace the fixed sleep with a jittered sleep using `random.uniform(0, policy.backoff_seconds)` from the standard library `random` module. Import `random` at the top of the file.

---

## Fix 7 — Add NodeContext and RetryBudget to public API

In `stanchion/__init__.py`, `NodeContext` and `RetryBudget` from `stanchion.failures` are not imported or included in `__all__`, despite being required by any caller writing custom failure classifiers.

Fix: add `NodeContext` and `RetryBudget` to the imports from `stanchion.failures` and add both names to the `__all__` list, maintaining alphabetical order.

---

## Fix 8 — Pin pytest-asyncio floor version in pyproject.toml

In `pyproject.toml`, the dev dependencies list `pytest-asyncio` without a version constraint. The `asyncio_mode = "auto"` setting in `[tool.pytest.ini_options]` has breaking behavior differences across `pytest-asyncio` versions.

Fix: update the `pytest-asyncio` entry in `[project.optional-dependencies]` dev to `pytest-asyncio>=0.23`.