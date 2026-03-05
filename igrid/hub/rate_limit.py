"""Sliding-window rate limiter with flood detection. No external dependencies."""
from __future__ import annotations
import time
from collections import defaultdict, deque


class RateLimiter:
    """In-memory sliding-window rate limiter.

    Tracks request timestamps per key (IP or operator_id).
    - Sustained rate: max_requests in window_s (e.g. 60 req/min)
    - Burst/flood:    burst_threshold in burst_window_s (e.g. 200 in 10s)
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_s: int = 60,
        burst_threshold: int = 200,
        burst_window_s: int = 10,
    ):
        self.max_requests = max_requests
        self.window_s = window_s
        self.burst_threshold = burst_threshold
        self.burst_window_s = burst_window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, bool]:
        """Check whether a request from *key* is allowed.

        Returns (allowed, is_flood):
          allowed=False  → rate limit exceeded (HTTP 429)
          is_flood=True  → burst threshold exceeded (trigger suspension)
        """
        now = time.monotonic()
        dq = self._hits[key]

        # Prune entries older than the sustained window
        cutoff = now - self.window_s
        while dq and dq[0] < cutoff:
            dq.popleft()

        # Record this request
        dq.append(now)

        # Flood detection (burst)
        burst_cutoff = now - self.burst_window_s
        burst_count = sum(1 for t in dq if t >= burst_cutoff)
        is_flood = burst_count >= self.burst_threshold

        # Sustained rate check
        allowed = len(dq) <= self.max_requests

        return allowed, is_flood

    def reset(self, key: str) -> None:
        """Clear rate-limit state for a key (e.g. after manual unblock)."""
        self._hits.pop(key, None)

    def cleanup(self) -> int:
        """Remove keys with no recent activity. Returns number of keys removed."""
        now = time.monotonic()
        stale = [k for k, dq in self._hits.items()
                 if not dq or dq[-1] < now - self.window_s]
        for k in stale:
            del self._hits[k]
        return len(stale)
