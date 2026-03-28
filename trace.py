import dataclasses
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterator
from pydantic import BaseModel
from stanchion.failures import FailureClass


@dataclass
class TraceEvent:
    node_id: str
    run_id: str
    attempt: int
    timestamp_utc: datetime
    input_state: dict
    output_state: dict | None
    duration_ms: int
    failure: FailureClass | None = None
    failure_message: str | None = None


class ExecutionTrace:
    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def append(self, event: TraceEvent) -> None:
        self._events.append(event)

    def events_for(self, node_id: str) -> list[TraceEvent]:
        return [event for event in self._events if event.node_id == node_id]

    def failures(self) -> list[TraceEvent]:
        return [event for event in self._events if event.failure is not None]

    def to_json(self) -> str:
        def default(value):
            if isinstance(value, BaseModel):
                return value.model_dump()
            if isinstance(value, datetime):
                return value.isoformat()
            if dataclasses.is_dataclass(value):
                return dataclasses.asdict(value)
            raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
        return json.dumps([dataclasses.asdict(event) for event in self._events], default=default)

    def diff(self, other: "ExecutionTrace") -> list[str]:
        left = {(event.node_id, event.attempt): event for event in self._events}
        right = {(event.node_id, event.attempt): event for event in other._events}
        differences: list[str] = []
        for key in sorted(set(left) | set(right)):
            if key not in left:
                differences.append(f"Extra event in other trace: {key[0]} attempt {key[1]}")
                continue
            if key not in right:
                differences.append(f"Missing event in other trace: {key[0]} attempt {key[1]}")
                continue
            if left[key] != right[key]:
                differences.append(f"Difference for {key[0]} attempt {key[1]}: {left[key]} != {right[key]}")
        return differences

    def replay(self) -> Iterator[TraceEvent]:
        yield from self._events

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[TraceEvent]:
        return iter(self._events)


class RunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    RESUMED = "RESUMED"


@dataclass
class ExecutionResult:
    run_id: str
    status: RunStatus
    final_state: BaseModel | None
    trace: ExecutionTrace
    total_cost_usd: float
    total_tokens: int
