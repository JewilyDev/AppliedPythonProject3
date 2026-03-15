from datetime import datetime, timedelta, timezone
from typing import Any


class SimpleTTLCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, datetime]] = {}

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if not item:
            return None
        value, expires_at = item
        if datetime.now(timezone.utc) >= expires_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._data[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


redirect_cache = SimpleTTLCache()
stats_cache = SimpleTTLCache()


def invalidate_link_caches(short_code: str) -> None:
    redirect_cache.delete(short_code)
    stats_cache.delete(short_code)

