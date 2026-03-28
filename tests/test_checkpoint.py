import builtins
import sys
import pytest
from pydantic import BaseModel
from stanchion.checkpoint import CheckpointManager, InMemoryStore, RedisStore


class SampleState(BaseModel):
    value: int
    label: str


def test_in_memory_store_save_load_round_trip():
    store = InMemoryStore()
    state = SampleState(value=7, label="seven")
    store.save("run1", "node1", state)
    loaded = store.load("run1", "node1")
    assert isinstance(loaded, SampleState)
    assert loaded.model_dump() == state.model_dump()


def test_in_memory_store_load_missing_returns_none():
    store = InMemoryStore()
    assert store.load("run1", "node1") is None


def test_in_memory_store_delete_clears_run_keys():
    store = InMemoryStore()
    store.save("run1", "node1", SampleState(value=1, label="a"))
    store.save("run1", "node2", SampleState(value=2, label="b"))
    store.delete("run1")
    assert store.load("run1", "node1") is None
    assert store.load("run1", "node2") is None


def test_checkpoint_manager_resume_returns_none_on_cold_start():
    manager = CheckpointManager(InMemoryStore())
    assert manager.resume("run1", "node1", SampleState) is None


def test_redis_store_raises_import_error_when_redis_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("No module named redis")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match="redis is required for RedisStore"):
        RedisStore("redis://localhost")
