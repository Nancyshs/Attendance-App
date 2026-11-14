"""Tiny in-process sliding-window rate limiter.

Used only for unauthenticated endpoints (login, trainee token exchange) to blunt
brute force attempts. It is per worker process, which is good enough as a first
line of defence; the real protection is the long random QR token / bcrypt.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import settings


def client_ip(request: Request) -> str:
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Records a hit; returns False when the key is over its limit."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            # opportunistic cleanup to keep memory bounded
            if len(self._hits) > 5000:
                for k in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(k, None)
            return True

    def check(self, key: str) -> None:
        if not self.hit(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="محاولات كثيرة. انتظر دقيقة ثم حاول مرة أخرى.",
            )

    def peek_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return False
            while q and now - q[0] > self.window:
                q.popleft()
            return len(q) >= self.limit
