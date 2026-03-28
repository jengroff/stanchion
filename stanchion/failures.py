from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable
from pydantic import BaseModel
from stanchion.contracts import ContractViolation


class FailureClass(StrEnum):
    RECOVERABLE = "RECOVERABLE"
    TERMINAL = "TERMINAL"
    AMBIGUOUS = "AMBIGUOUS"


class FailurePolicy(BaseModel):
    max_retries: int = 3
    backoff_seconds: float = 1.0
    fallback_node_id: str | None = None


PolicyMap = dict[FailureClass, FailurePolicy]


def default_policy_map() -> PolicyMap:
    return {
        FailureClass.RECOVERABLE: FailurePolicy(max_retries=3, backoff_seconds=1.0),
        FailureClass.TERMINAL: FailurePolicy(max_retries=0, backoff_seconds=0.0),
        FailureClass.AMBIGUOUS: FailurePolicy(max_retries=1, backoff_seconds=0.5),
    }


@dataclass
class NodeContext:
    node_id: str
    attempt: int
    run_id: str


Classifier = Callable[[Exception, NodeContext], FailureClass | None]


def classify(exc: Exception, context: NodeContext, classifiers: list[Classifier] | None = None) -> FailureClass:
    if classifiers:
        for classifier in classifiers:
            result = classifier(exc, context)
            if result is not None:
                return result
    if isinstance(exc, ContractViolation):
        return FailureClass.TERMINAL
    try:
        from stanchion.cost import BudgetExceeded
    except ImportError:
        BudgetExceeded = None
    if BudgetExceeded is not None and isinstance(exc, BudgetExceeded):
        return FailureClass.RECOVERABLE
    if isinstance(exc, TimeoutError):
        return FailureClass.RECOVERABLE
    if isinstance(exc, ValueError):
        return FailureClass.AMBIGUOUS
    return FailureClass.AMBIGUOUS


class RetryBudget:
    def __init__(self) -> None:
        self._counts: defaultdict[tuple[str, str], int] = defaultdict(int)

    def increment(self, run_id: str, node_id: str) -> int:
        self._counts[(run_id, node_id)] += 1
        return self._counts[(run_id, node_id)]

    def exhausted(self, run_id: str, node_id: str, policy: FailurePolicy) -> bool:
        return self._counts[(run_id, node_id)] >= policy.max_retries
