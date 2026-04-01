import asyncio
import random
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Awaitable, Callable
from pydantic import BaseModel, Field
from stanchion.checkpoint import CheckpointManager
from stanchion.contracts import ContractRegistry, NodeContract
from stanchion.cost import CostTracker, ModelHint, NodeUsage, ExecutionBudget
from stanchion.failures import (
    FailureClass,
    NodeContext,
    PolicyMap,
    RetryBudget,
    classify,
    default_policy_map,
)
from stanchion.trace import ExecutionResult, ExecutionTrace, RunStatus, TraceEvent


class RunConfig(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    budget: ExecutionBudget
    policy_map: PolicyMap = Field(default_factory=default_policy_map)
    model_hints: dict[str, ModelHint] = Field(default_factory=dict)
    resume_from: str | None = None


def armature_node(node_id: str, contract: NodeContract):
    def decorator(func: Callable[[BaseModel], Awaitable[dict[str, Any]]]):
        setattr(func, "_armature_node_id", node_id)
        setattr(func, "_armature_contract", contract)
        return func
    return decorator


class ArmatureRunner:
    def __init__(self, registry: ContractRegistry, checkpoint_manager: CheckpointManager, config: RunConfig) -> None:
        self.registry = registry
        self.checkpoint_manager = checkpoint_manager
        self.config = config
        self.cost_tracker = CostTracker()
        self.retry_budget = RetryBudget()
        self.trace = ExecutionTrace()

    async def run(self, node_sequence: list[Callable[[BaseModel], Awaitable[dict[str, Any]]]], initial_state: BaseModel) -> ExecutionResult:
        current_state = initial_state
        start_index = 0
        if self.config.resume_from is not None:
            for index, node in enumerate(node_sequence):
                if self._node_id(node) == self.config.resume_from:
                    start_index = index
                    break
            else:
                return ExecutionResult(
                    run_id=self.config.run_id,
                    status=RunStatus.PARTIAL,
                    final_state=current_state,
                    trace=self.trace,
                    total_cost_usd=self.cost_tracker.total_cost_usd,
                    total_tokens=self.cost_tracker.total_tokens,
                )
            if start_index > 0:
                previous = node_sequence[start_index - 1]
                prev_contract = self._node_contract(previous)
                loaded = self.checkpoint_manager.resume(self.config.run_id, getattr(previous, "_armature_node_id"), prev_contract.output_schema)
                if loaded is not None:
                    current_state = loaded
        for node in node_sequence[start_index:]:
            node_id = self._node_id(node)
            contract = self._node_contract(node)
            attempt = 1
            input_model = None
            while True:
                input_model = self.registry.validate_input(node_id, current_state.model_dump())
                start_ts = datetime.now(timezone.utc)
                try:
                    output = await node(input_model)
                    if isinstance(output, tuple) and len(output) == 2:
                        output_raw, tokens_used = output
                    else:
                        output_raw = output
                        tokens_used = 0
                    output_model = self.registry.validate_output(node_id, output_raw)
                    duration_ms = int((datetime.now(timezone.utc) - start_ts).total_seconds() * 1000)
                    self.cost_tracker.record(NodeUsage(node_id=node_id, tokens_used=tokens_used, cost_usd=0.0, latency_ms=duration_ms))
                    self.cost_tracker.check_budget(self.config.budget, node_id)
                    self.checkpoint_manager.checkpoint(self.config.run_id, node_id, output_model)
                    self.trace.append(TraceEvent(node_id=node_id, run_id=self.config.run_id, attempt=attempt, timestamp_utc=start_ts, input_state=input_model.model_dump(), output_state=output_model.model_dump(), duration_ms=duration_ms))
                    current_state = output_model
                    break
                except Exception as exc:
                    duration_ms = int((datetime.now(timezone.utc) - start_ts).total_seconds() * 1000)
                    failure_class = classify(exc, NodeContext(node_id=node_id, attempt=attempt, run_id=self.config.run_id))
                    self.trace.append(TraceEvent(node_id=node_id, run_id=self.config.run_id, attempt=attempt, timestamp_utc=start_ts, input_state=input_model.model_dump() if input_model is not None else {}, output_state=None, duration_ms=duration_ms, failure=failure_class, failure_message=str(exc)))
                    policy = self.config.policy_map.get(failure_class) or default_policy_map()[failure_class]
                    if failure_class is FailureClass.TERMINAL:
                        return ExecutionResult(
                            run_id=self.config.run_id,
                            status=RunStatus.FAILED,
                            final_state=current_state,
                            trace=self.trace,
                            total_cost_usd=self.cost_tracker.total_cost_usd,
                            total_tokens=self.cost_tracker.total_tokens,
                        )
                    self.retry_budget.increment(self.config.run_id, node_id)
                    if self.retry_budget.exhausted(self.config.run_id, node_id, policy):
                        return ExecutionResult(
                            run_id=self.config.run_id,
                            status=RunStatus.PARTIAL,
                            final_state=current_state,
                            trace=self.trace,
                            total_cost_usd=self.cost_tracker.total_cost_usd,
                            total_tokens=self.cost_tracker.total_tokens,
                        )
                    if policy.backoff_seconds > 0:
                        await asyncio.sleep(random.uniform(0, policy.backoff_seconds))
                    attempt += 1
                    continue
        status = RunStatus.RESUMED if self.config.resume_from is not None else RunStatus.COMPLETED
        return ExecutionResult(
            run_id=self.config.run_id,
            status=status,
            final_state=current_state,
            trace=self.trace,
            total_cost_usd=self.cost_tracker.total_cost_usd,
            total_tokens=self.cost_tracker.total_tokens,
        )

    def _node_id(self, node: Callable[..., Any]) -> str:
        node_id = getattr(node, "_armature_node_id", None)
        if node_id is None:
            raise TypeError("Node is missing armature node_id")
        return node_id

    def _node_contract(self, node: Callable[..., Any]) -> NodeContract:
        contract = getattr(node, "_armature_contract", None)
        if contract is not None:
            return contract
        return self.registry.get(self._node_id(node))
