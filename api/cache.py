import time
from typing import Any, Optional

_store: dict[str, tuple[float, Any]] = {}
TTL = 300  # 5 minutes


def cache_get(key: str) -> Optional[Any]:
    entry = _store.get(key)
    if entry and time.time() - entry[0] < TTL:
        return entry[1]
    return None


def cache_set(key: str, value: Any) -> None:
    _store[key] = (time.time(), value)


def cache_clear() -> None:
    _store.clear()
