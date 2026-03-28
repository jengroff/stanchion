import json
from datetime import datetime, timezone
from stanchion.failures import FailureClass
from stanchion.trace import ExecutionResult, ExecutionTrace, RunStatus, TraceEvent
from pydantic import BaseModel


class FinalState(BaseModel):
    status: str


def test_append_and_iterate():
    trace = ExecutionTrace()
    event = TraceEvent(
        node_id="node1",
        run_id="run1",
        attempt=1,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={"foo": "bar"},
        output_state={"baz": 1},
        duration_ms=50,
    )
    trace.append(event)
    assert len(trace) == 1
    assert list(trace)[0] is event


def test_failures_filters_correctly():
    trace = ExecutionTrace()
    trace.append(TraceEvent(
        node_id="node1",
        run_id="run1",
        attempt=1,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={},
        output_state=None,
        duration_ms=10,
        failure=FailureClass.TERMINAL,
        failure_message="oops",
    ))
    trace.append(TraceEvent(
        node_id="node1",
        run_id="run1",
        attempt=2,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={},
        output_state={"ok": True},
        duration_ms=20,
    ))
    failures = trace.failures()
    assert len(failures) == 1
    assert failures[0].failure == FailureClass.TERMINAL


def test_diff_detects_node_id_mismatch():
    left = ExecutionTrace()
    right = ExecutionTrace()
    left.append(TraceEvent(
        node_id="node1",
        run_id="run1",
        attempt=1,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={"a": 1},
        output_state=None,
        duration_ms=10,
    ))
    right.append(TraceEvent(
        node_id="node2",
        run_id="run1",
        attempt=1,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={"a": 1},
        output_state=None,
        duration_ms=10,
    ))
    diffs = left.diff(right)
    assert any("Missing event in other trace: node1 attempt 1" in item for item in diffs)
    assert any("Extra event in other trace: node2 attempt 1" in item for item in diffs)


def test_to_json_round_trips_with_base_model_in_state():
    trace = ExecutionTrace()
    trace.append(TraceEvent(
        node_id="node1",
        run_id="run1",
        attempt=1,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={"state": FinalState(status="ok")},
        output_state=None,
        duration_ms=10,
    ))
    payload = trace.to_json()
    loaded = json.loads(payload)
    assert isinstance(loaded, list)
    assert loaded[0]["node_id"] == "node1"
    assert loaded[0]["input_state"]["state"]["status"] == "ok"


def test_replay_yields_events_in_order():
    trace = ExecutionTrace()
    event1 = TraceEvent(
        node_id="node1",
        run_id="run1",
        attempt=1,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={},
        output_state=None,
        duration_ms=5,
    )
    event2 = TraceEvent(
        node_id="node1",
        run_id="run1",
        attempt=2,
        timestamp_utc=datetime.now(timezone.utc),
        input_state={},
        output_state=None,
        duration_ms=6,
    )
    trace.append(event1)
    trace.append(event2)
    assert list(trace.replay()) == [event1, event2]


def test_execution_result_dataclass():
    trace = ExecutionTrace()
    result = ExecutionResult(
        run_id="run1",
        status=RunStatus.COMPLETED,
        final_state=FinalState(status="done"),
        trace=trace,
        total_cost_usd=0.0,
        total_tokens=0,
    )
    assert result.run_id == "run1"
    assert result.status == RunStatus.COMPLETED
    assert result.final_state.status == "done"
