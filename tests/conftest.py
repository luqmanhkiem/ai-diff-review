import time

import pytest
from fastapi.testclient import TestClient

from app import config, ratelimit, store
from app.main import app

AUTH = {"Authorization": f"Bearer {config.BEARER_TOKEN}"}


@pytest.fixture
def client():
    store.reset()
    ratelimit.reset()
    with TestClient(app) as c:            # triggers lifespan -> starts workers
        yield c


def submit(client, diff, options=None, headers=None, raw=None):
    body = raw if raw is not None else {"diff": diff}
    if options is not None and raw is None:
        body["options"] = options
    h = dict(AUTH)
    if headers:
        h.update(headers)
    return client.post("/v1/reviews", json=body, headers=h)


def wait_done(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/v1/reviews/{job_id}", headers=AUTH)
        data = r.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")
