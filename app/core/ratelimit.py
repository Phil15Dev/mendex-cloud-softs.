"""Attempt limiter. Redis-backed when REDIS_URL is set (shared by all workers), in-memory otherwise."""
import logging
import time
import uuid

from .config import settings

log = logging.getLogger("app.ratelimit")


class MemoryLimiter:
    def __init__(self, name: str, limit: int, window: int):
        self.name, self.limit, self.window, self.hits = name, limit, window, {}

    def _prune(self, key):
        now = time.monotonic()
        self.hits[key] = [t for t in self.hits.get(key, []) if now - t < self.window]
        return self.hits[key]

    def blocked(self, key) -> bool:
        return len(self._prune(key)) >= self.limit

    def retry_minutes(self, key) -> int:
        hits = self._prune(key)
        return 1 if not hits else max(1, int((self.window - (time.monotonic() - hits[0])) // 60) + 1)

    def fail(self, key) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key) -> None:
        self.hits.pop(key, None)

    def clear(self) -> None:
        self.hits.clear()


class RedisLimiter:
    def __init__(self, client, name: str, limit: int, window: int):
        self.r, self.name, self.limit, self.window = client, name, limit, window
        self.fallback = MemoryLimiter(name, limit, window)  # used only if Redis is unreachable

    def _k(self, key):
        return f"rl:{self.name}:{key}"

    def _safe(self, fn, fallback):
        try:
            return fn()
        except Exception:  # Redis down: keep working with per-process limits and say so
            log.error("redis unavailable, using in-memory rate limit for %s", self.name)
            return fallback()

    def blocked(self, key) -> bool:
        def go():
            k, now = self._k(key), time.time()
            self.r.zremrangebyscore(k, 0, now - self.window)
            return self.r.zcard(k) >= self.limit
        return self._safe(go, lambda: self.fallback.blocked(key))

    def retry_minutes(self, key) -> int:
        def go():
            first = self.r.zrange(self._k(key), 0, 0, withscores=True)
            return 1 if not first else max(1, int((self.window - (time.time() - first[0][1])) // 60) + 1)
        return self._safe(go, lambda: self.fallback.retry_minutes(key))

    def fail(self, key) -> None:
        def go():
            k, now = self._k(key), time.time()
            pipe = self.r.pipeline()
            pipe.zadd(k, {f"{now}:{uuid.uuid4().hex[:8]}": now})
            pipe.zremrangebyscore(k, 0, now - self.window)
            pipe.expire(k, self.window)
            pipe.execute()
        self._safe(go, lambda: self.fallback.fail(key))

    def reset(self, key) -> None:
        self._safe(lambda: self.r.delete(self._k(key)), lambda: self.fallback.reset(key))

    def clear(self) -> None:
        def go():
            for k in self.r.scan_iter(f"rl:{self.name}:*"):
                self.r.delete(k)
        self._safe(go, lambda: None)
        self.fallback.clear()


_client = None


def redis_client():
    global _client
    if _client is None and settings.redis_url:
        import redis
        _client = redis.Redis.from_url(settings.redis_url, socket_timeout=1, socket_connect_timeout=1)
    return _client


def make_limiter(name: str, limit: int, window: int = 15 * 60):
    client = redis_client()
    return RedisLimiter(client, name, limit, window) if client else MemoryLimiter(name, limit, window)
