import importlib
from typing import NamedTuple, Protocol
from pydantic import BaseModel


class CheckpointStore(Protocol):
    def save(self, run_id: str, node_id: str, state: BaseModel) -> None:
        ...

    def load(self, run_id: str, node_id: str) -> BaseModel | None:
        ...

    def delete(self, run_id: str) -> None:
        ...


class CheckpointKey(NamedTuple):
    run_id: str
    node_id: str


class InMemoryStore:
    def __init__(self) -> None:
        self._states: dict[CheckpointKey, str] = {}
        self._schemas: dict[CheckpointKey, type[BaseModel]] = {}

    def save(self, run_id: str, node_id: str, state: BaseModel) -> None:
        self._states[CheckpointKey(run_id, node_id)] = state.model_dump_json()
        self._schemas[CheckpointKey(run_id, node_id)] = type(state)

    def load(self, run_id: str, node_id: str) -> BaseModel | None:
        key = CheckpointKey(run_id, node_id)
        raw = self._states.get(key)
        schema = self._schemas.get(key)
        if raw is None or schema is None:
            return None
        return schema.model_validate_json(raw)

    def delete(self, run_id: str) -> None:
        keys = [key for key in self._states if key.run_id == run_id]
        for key in keys:
            self._states.pop(key, None)
            self._schemas.pop(key, None)

    def save_typed(self, run_id: str, node_id: str, state: BaseModel, schema: type[BaseModel]) -> None:
        if not issubclass(schema, BaseModel):
            raise TypeError("schema must be a BaseModel type")
        if not isinstance(state, schema):
            state = schema.model_validate(state.model_dump())
        self._states[CheckpointKey(run_id, node_id)] = state.model_dump_json()
        self._schemas[CheckpointKey(run_id, node_id)] = schema

    def load_typed(self, run_id: str, node_id: str, schema: type[BaseModel]) -> BaseModel | None:
        raw = self._states.get(CheckpointKey(run_id, node_id))
        if raw is None:
            return None
        return schema.model_validate_json(raw)


def _schema_ref(schema: type[BaseModel]) -> str:
    return f"{schema.__module__}:{schema.__qualname__}"


def _resolve_schema(ref: str) -> type[BaseModel]:
    module_name, qualname = ref.split(":", 1)
    module = importlib.import_module(module_name)
    attr = module
    for part in qualname.split("."):
        attr = getattr(attr, part)
    if not issubclass(attr, BaseModel):
        raise TypeError("resolved schema is not a BaseModel")
    return attr


class RedisStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 3600) -> None:
        try:
            import redis
        except ImportError as exc:
            raise ImportError("redis is required for RedisStore; install with pip install redis") from exc
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds

    def _state_key(self, run_id: str, node_id: str) -> str:
        return f"stanchion:{run_id}:{node_id}"

    def _schema_key(self, run_id: str, node_id: str) -> str:
        return f"stanchion:{run_id}:{node_id}:schema"

    def save(self, run_id: str, node_id: str, state: BaseModel) -> None:
        payload = state.model_dump_json()
        self._client.setex(self._state_key(run_id, node_id), self._ttl, payload)
        self._client.setex(self._schema_key(run_id, node_id), self._ttl, _schema_ref(type(state)))

    def load(self, run_id: str, node_id: str) -> BaseModel | None:
        payload = self._client.get(self._state_key(run_id, node_id))
        if payload is None:
            return None
        schema_ref = self._client.get(self._schema_key(run_id, node_id))
        if schema_ref is None:
            return None
        schema = _resolve_schema(schema_ref)
        return schema.model_validate_json(payload)

    def delete(self, run_id: str) -> None:
        pattern = f"stanchion:{run_id}:*"
        for key in self._client.scan_iter(match=pattern):
            self._client.delete(key)

    def save_typed(self, run_id: str, node_id: str, state: BaseModel, schema: type[BaseModel]) -> None:
        if not issubclass(schema, BaseModel):
            raise TypeError("schema must be a BaseModel type")
        payload = state.model_dump_json()
        self._client.setex(self._state_key(run_id, node_id), self._ttl, payload)
        self._client.setex(self._schema_key(run_id, node_id), self._ttl, _schema_ref(schema))

    def load_typed(self, run_id: str, node_id: str, schema: type[BaseModel]) -> BaseModel | None:
        payload = self._client.get(self._state_key(run_id, node_id))
        if payload is None:
            return None
        return schema.model_validate_json(payload)


class CheckpointManager:
    def __init__(self, store: CheckpointStore) -> None:
        self._store = store

    def checkpoint(self, run_id: str, node_id: str, state: BaseModel) -> None:
        self._store.save(run_id, node_id, state)

    def resume(self, run_id: str, node_id: str, schema: type[BaseModel]) -> BaseModel | None:
        if hasattr(self._store, "load_typed"):
            return self._store.load_typed(run_id, node_id, schema)
        result = self._store.load(run_id, node_id)
        if result is None:
            return None
        if not isinstance(result, schema):
            raise TypeError("loaded state does not match schema")
        return result

    def clear(self, run_id: str) -> None:
        self._store.delete(run_id)
