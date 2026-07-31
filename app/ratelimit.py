"""Per-token rate limiter for POST /v1/reviews only (GETs are never limited).
Sliding-window log: we keep submission timestamps per bearer token and allow up
to RATE_LIMIT_PER_MINUTE + RATE_LIMIT_BURST in any trailing 60s. Over that we
raise 429 with a Retry-After header — we shed load, never 5xx."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from . import config
from .errors import ApiError

_WINDOW = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def check(token: str) -> None:
    now = time.time()
    dq = _hits[token]
    while dq and now - dq[0] >= _WINDOW:
        dq.popleft()

    limit = config.RATE_LIMIT_PER_MINUTE + config.RATE_LIMIT_BURST
    if len(dq) >= limit:
        retry_after = max(1, int(_WINDOW - (now - dq[0])) + 1)
        raise ApiError(
            "rate_limited",
            "Submission rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )
    dq.append(now)


def reset() -> None:
    _hits.clear()
