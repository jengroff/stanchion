"""Stanchion — framework-agnostic reliability primitives for agent pipelines.

Provides contracts, checkpointing, cost tracking, failure classification,
and execution tracing for building robust LLM agent systems.
"""

from stanchion.checkpoint import CheckpointManager, CheckpointStore, InMemoryStore, RedisStore
from stanchion.contracts import BoundaryValidator, ContractRegistry, ContractViolation, NodeContract
from stanchion.cost import BudgetExceeded, CostTracker, ExecutionBudget, ModelHint, NodeUsage
from stanchion.failures import (
    Classifier,
    FailureClass,
    FailurePolicy,
    NodeContext,
    RetryBudget,
    classify,
    default_policy_map,
)
from stanchion.runner import ArmatureRunner, RunConfig, StanchionRunner, armature_node, stanchion_node
from stanchion.trace import ExecutionResult, ExecutionTrace, RunStatus, TraceEvent

__version__ = "0.1.1"

__all__ = [
    "ArmatureRunner",  # backwards-compatible alias
    # Contracts
    "BoundaryValidator",
    # Cost
    "BudgetExceeded",
    # Checkpointing
    "CheckpointManager",
    "CheckpointStore",
    # Failures
    "Classifier",
    "ContractRegistry",
    "ContractViolation",
    "CostTracker",
    "ExecutionBudget",
    # Trace
    "ExecutionResult",
    "ExecutionTrace",
    "FailureClass",
    "FailurePolicy",
    "InMemoryStore",
    "ModelHint",
    "NodeContext",
    "NodeContract",
    "NodeUsage",
    "RedisStore",
    "RetryBudget",
    "RunConfig",
    "RunStatus",
    # Runner
    "StanchionRunner",
    "TraceEvent",
    "armature_node",  # backwards-compatible alias
    "classify",
    "default_policy_map",
    "stanchion_node",
]
