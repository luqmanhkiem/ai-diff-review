"""Caching (content-keyed) and idempotency (header-keyed) are distinct."""
from conftest import AUTH, submit, wait_done
from helpers import one_file_diff

DIFF = one_file_diff("src/app.js", ["eval(x);", "console.log(1);"])


def test_cache_hit_on_identical_resubmit(client):
    r1 = submit(client, DIFF)
    d1 = wait_done(client, r1.json()["jobId"])
    assert d1["usage"]["cacheHit"] is False

    r2 = submit(client, DIFF)                     # byte-identical, no key
    d2 = wait_done(client, r2.json()["jobId"])
    assert d2["usage"]["cacheHit"] is True
    assert d2["findings"] == d1["findings"]       # identical findings


def test_idempotency_same_key_same_body(client):
    h = {"Idempotency-Key": "abc-123"}
    r1 = submit(client, DIFF, headers=h)
    r2 = submit(client, DIFF, headers=h)
    assert r1.json()["jobId"] == r2.json()["jobId"]


def test_idempotency_same_key_different_body(client):
    h = {"Idempotency-Key": "conflict-key"}
    submit(client, DIFF, headers=h)
    other = one_file_diff("src/app.js", ["console.log(2);"])
    r = submit(client, other, headers=h)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "idempotency_conflict"
