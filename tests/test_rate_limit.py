"""Rate limiting applies to POST only, returns 429 + Retry-After over budget,
and never 5xx. GETs are never limited."""
from conftest import AUTH, submit
from helpers import one_file_diff

from app import config

DIFF = one_file_diff("f.js", ["console.log(1);"])


def test_post_burst_gets_429_never_5xx(client):
    limit = config.RATE_LIMIT_PER_MINUTE + config.RATE_LIMIT_BURST
    codes = [submit(client, DIFF).status_code for _ in range(limit + 5)]
    assert all(c < 500 for c in codes)          # never 5xx under burst
    assert 429 in codes                          # sheds beyond budget
    # The first `limit` submissions succeed.
    assert codes[:limit] == [202] * limit


def test_429_carries_retry_after(client):
    limit = config.RATE_LIMIT_PER_MINUTE + config.RATE_LIMIT_BURST
    last = None
    for _ in range(limit + 3):
        last = submit(client, DIFF)
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "rate_limited"
    assert "retry-after" in {k.lower() for k in last.headers.keys()}


def test_gets_not_rate_limited(client):
    # A GET storm never trips the limiter.
    for _ in range(100):
        r = client.get("/v1/reviews/nope", headers=AUTH)
        assert r.status_code == 404
