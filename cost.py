from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel


@dataclass
class ModelHint:
    node_id: str
    preferred_model: str
    fallback_model: str | None = None
    max_tokens: int | None = None


class ExecutionBudget(BaseModel):
    max_tokens_total: int | None = None
    max_cost_usd: float | None = None
    max_latency_ms: int | None = None

    @classmethod
    def unlimited(cls) -> "ExecutionBudget":
        return cls(max_tokens_total=None, max_cost_usd=None, max_latency_ms=None)


@dataclass
class NodeUsage:
    node_id: str
    tokens_used: int
    cost_usd: float
    latency_ms: int


class BudgetExceeded(Exception):
    dimension: Literal["tokens", "cost", "latency"]
    limit: float
    actual: float
    node_id: str

    def __init__(self, dimension: Literal["tokens", "cost", "latency"], limit: float, actual: float, node_id: str):
        self.dimension = dimension
        self.limit = limit
        self.actual = actual
        self.node_id = node_id
        super().__init__(f"Budget exceeded {dimension} for {node_id}: {actual} > {limit}")


class CostTracker:
    def __init__(self) -> None:
        self._usage: dict[str, NodeUsage] = {}

    def record(self, usage: NodeUsage) -> None:
        existing = self._usage.get(usage.node_id)
        if existing is None:
            self._usage[usage.node_id] = usage
            return
        self._usage[usage.node_id] = NodeUsage(
            node_id=usage.node_id,
            tokens_used=existing.tokens_used + usage.tokens_used,
            cost_usd=existing.cost_usd + usage.cost_usd,
            latency_ms=existing.latency_ms + usage.latency_ms,
        )

    def check_budget(self, budget: ExecutionBudget, node_id: str) -> None:
        usage = self._usage.get(node_id)
        if usage is None:
            return
        if budget.max_tokens_total is not None and self.total_tokens > budget.max_tokens_total:
            raise BudgetExceeded("tokens", float(budget.max_tokens_total), float(self.total_tokens), node_id)
        if budget.max_cost_usd is not None and usage.cost_usd > budget.max_cost_usd:
            raise BudgetExceeded("cost", float(budget.max_cost_usd), float(usage.cost_usd), node_id)
        if budget.max_latency_ms is not None and usage.latency_ms > budget.max_latency_ms:
            raise BudgetExceeded("latency", float(budget.max_latency_ms), float(usage.latency_ms), node_id)

    @property
    def total_tokens(self) -> int:
        return sum(usage.tokens_used for usage in self._usage.values())

    @property
    def total_cost_usd(self) -> float:
        return sum(usage.cost_usd for usage in self._usage.values())

    def summary(self) -> dict[str, NodeUsage]:
        return dict(self._usage)
