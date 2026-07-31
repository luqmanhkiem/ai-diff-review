"""SSE: a finished job's stream must replay all events identically."""
from conftest import AUTH, submit, wait_done
from helpers import one_file_diff

DIFF = one_file_diff("src/app.js", ["eval(x);", "console.log(1);", "// TODO x"])


def _parse_sse(text: str):
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        ev = {"event": None, "data": None}
        for line in block.splitlines():
            if line.startswith("event: "):
                ev["event"] = line[len("event: "):]
            elif line.startswith("data: "):
                ev["data"] = line[len("data: "):]
        events.append(ev)
    return events


def test_stream_replays_finished_job(client):
    r = submit(client, DIFF)
    job_id = r.json()["jobId"]
    wait_done(client, job_id)

    # Connect twice to the finished job — both replays must be identical.
    t1 = client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH)
    t2 = client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH)
    assert t1.headers["content-type"].startswith("text/event-stream")
    e1, e2 = _parse_sse(t1.text), _parse_sse(t2.text)
    assert e1 == e2

    kinds = [e["event"] for e in e1]
    assert kinds.count("finding") == 3
    assert kinds[-1] == "done"
    assert "status" in kinds


def test_stream_requires_auth(client):
    r = submit(client, DIFF)
    job_id = r.json()["jobId"]
    unauth = client.get(f"/v1/reviews/{job_id}/stream")
    assert unauth.status_code == 401
