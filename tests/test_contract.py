"""Contract-level status codes and the error envelope taxonomy."""
from conftest import AUTH, submit, wait_done
from helpers import one_file_diff

from app import config


def test_health_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body and "uptimeSeconds" in body


def test_spec_matches_config(client):
    r = client.get("/spec")
    assert r.status_code == 200
    body = r.json()
    assert body["providers"] == ["mock", "llm"]
    assert body["limits"] == config.spec_limits()


def test_auth_required_on_all_v1(client):
    # No token on GET or POST -> 401 envelope.
    for method, url in [("get", "/v1/reviews/xyz"), ("post", "/v1/reviews")]:
        r = getattr(client, method)(url)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def test_invalid_json(client):
    r = client.post("/v1/reviews", content="{not json", headers={**AUTH, "Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_json"


def test_invalid_diff(client):
    r = submit(client, "this is not a diff at all")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_diff"


def test_missing_diff(client):
    r = submit(client, None, raw={"options": {"provider": "mock"}})
    assert r.status_code == 422


def test_payload_too_large(client):
    big = "+" + "a" * (config.MAX_PAYLOAD_BYTES + 10)
    r = submit(client, one_file_diff("f.js", [big]))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_unknown_job_404(client):
    r = client.get("/v1/reviews/does-not-exist", headers=AUTH)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_unknown_fields_ignored(client):
    diff = one_file_diff("f.js", ["console.log(1);"])
    r = submit(client, None, raw={"diff": diff, "extra": "ignored", "options": {"maxFindings": 5}})
    assert r.status_code == 202
    data = wait_done(client, r.json()["jobId"])
    assert data["status"] == "done"


def test_max_findings_truncates_but_usage_full(client):
    diff = one_file_diff("f.js", [f"console.log({i});" for i in range(10)])
    r = submit(client, diff, options={"maxFindings": 3})
    data = wait_done(client, r.json()["jobId"])
    assert len(data["findings"]) == 3          # truncated output
    assert data["usage"]["inputBytes"] > 0     # usage reflects full scan
