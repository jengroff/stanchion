"""Framework-agnostic agent reliability primitives."""

from stanchion.checkpoint import CheckpointManager, CheckpointStore, InMemoryStore, RedisStore
from stanchion.contracts import BoundaryValidator, ContractRegistry, ContractViolation, NodeContract
from stanchion.cost import BudgetExceeded, CostTracker, ExecutionBudget, ModelHint, NodeUsage
from stanchion.failures import (
    FailureClass,
    FailurePolicy,
    NodeContext,
    RetryBudget,
    classify,
    default_policy_map,
)
from stanchion.runner import ArmatureRunner, RunConfig, armature_node
from stanchion.trace import ExecutionResult, ExecutionTrace, RunStatus, TraceEvent

__version__ = "0.1.1"

__all__ = [
    "ArmatureRunner",
    "BoundaryValidator",
    "BudgetExceeded",
    "CheckpointManager",
    "CheckpointStore",
    "ContractRegistry",
    "ContractViolation",
    "CostTracker",
    "ExecutionBudget",
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
    "TraceEvent",
    "armature_node",
    "classify",
    "default_policy_map",
]
