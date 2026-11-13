"""Minimal in-process sliding-window rate limiter.

State lives in memory, so limits are per process. That matches how this app
is deployed (a single uvicorn process); a multi-replica deployment would move
the counters to Redis behind the same interface.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        """Record a request for `key`; raise 429 if it exceeds the limit."""
        if self.limit <= 0:
            return  # disabled
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, math.ceil(hits[0] + self.window - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
