"""The /v1/reviews endpoints: submit (async), poll, and SSE stream. This is where
the cross-cutting behaviours meet the wire: validation precedence, idempotency,
content caching, and streaming replay."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .. import config, queue, ratelimit, store
from ..auth import require_bearer
from ..diff_parser import InvalidDiff, parse_diff
from ..errors import ApiError
from ..models import Job

router = APIRouter(prefix="/v1", dependencies=[Depends(require_bearer)])


def _token(request: Request) -> str:
    return request.headers.get("authorization", "")[len("Bearer "):].strip()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _semantic_hash(diff: str, provider: str, max_findings: int) -> str:
    canonical = json.dumps(
        {"diff": diff, "provider": provider, "maxFindings": max_findings},
        sort_keys=True, separators=(",", ":"),
    )
    return _sha(canonical.encode("utf-8"))


def _new_job(diff: str, provider: str, max_findings: int, body_hash: str) -> Job:
    return Job(
        id=uuid.uuid4().hex,
        diff=diff,
        provider=provider,
        max_findings=max_findings,
        body_hash=body_hash,
    )


# --- POST /v1/reviews ----------------------------------------------------------

@router.post("/reviews")
async def create_review(request: Request):
    token = _token(request)

    # Rate limit first so bursts are shed cheaply (POST only).
    ratelimit.check(token)

    # 1) Size before anything else — we must not buffer/parse a huge body.
    body = await request.body()
    if len(body) > config.MAX_PAYLOAD_BYTES:
        raise ApiError("payload_too_large", "Request body exceeds 1 MiB limit.")

    # 2) JSON validity.
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError("invalid_json", "Request body is not valid JSON.")
    if not isinstance(parsed, dict):
        raise ApiError("invalid_json", "Request body must be a JSON object.")

    # 3) Diff presence + validity (unknown fields ignored).
    diff = parsed.get("diff")
    if not isinstance(diff, str) or diff.strip() == "":
        raise ApiError("invalid_diff", "Field 'diff' is required and must be a non-empty string.")
    try:
        parse_diff(diff)
    except InvalidDiff as e:
        raise ApiError("invalid_diff", str(e))

    options = parsed.get("options") or {}
    if not isinstance(options, dict):
        options = {}
    provider = options.get("provider", config.DEFAULT_PROVIDER)
    if provider not in config.PROVIDERS:
        provider = config.DEFAULT_PROVIDER
    max_findings = options.get("maxFindings", config.DEFAULT_MAX_FINDINGS)
    if not isinstance(max_findings, int) or isinstance(max_findings, bool) or max_findings < 0:
        max_findings = config.DEFAULT_MAX_FINDINGS

    raw_body_hash = _sha(body)
    semantic_hash = _semantic_hash(diff, provider, max_findings)

    # 4) Idempotency: same key + identical body -> same job; different body -> 409.
    idem_key = request.headers.get("idempotency-key")
    if idem_key:
        prior = store.idempotency_index.get(idem_key)
        if prior:
            if prior["body_hash"] == raw_body_hash:
                job = store.get_job(prior["job_id"])
                if job:
                    return JSONResponse(
                        status_code=202,
                        content={"jobId": job.id, "status": job.status},
                    )
            else:
                raise ApiError("idempotency_conflict",
                               "Idempotency-Key reused with a different body.")

    # 5) Caching: byte-identical {diff, options} already computed -> reuse it.
    cached = store.find_cached_job(semantic_hash)
    if cached and cached.status == "done":
        job = _new_job(diff, provider, max_findings, semantic_hash)
        job.findings = list(cached.findings)
        job.usage.inputBytes = cached.usage.inputBytes
        job.usage.chunks = cached.usage.chunks
        job.usage.cacheHit = True
        job.status = "done"
        job.done = True
        # Pre-populate the event log so the stream replays identically.
        job.emit("status", {"status": "done"})
        for f in job.findings:
            job.emit("finding", f.to_dict())
        job.emit("done", {"total": len(job.findings), "usage": job.usage.to_dict()})
        store.jobs[job.id] = job          # do NOT overwrite the canonical cache entry
        if idem_key:
            store.idempotency_index[idem_key] = {"body_hash": raw_body_hash, "job_id": job.id}
        return JSONResponse(status_code=202, content={"jobId": job.id, "status": "done"})

    # 6) Normal path: create, register, enqueue.
    job = _new_job(diff, provider, max_findings, semantic_hash)
    store.put_job(job)
    if idem_key:
        store.idempotency_index[idem_key] = {"body_hash": raw_body_hash, "job_id": job.id}
    queue.enqueue(job.id)
    return JSONResponse(status_code=202, content={"jobId": job.id, "status": "queued"})


# --- GET /v1/reviews/{jobId} ---------------------------------------------------

@router.get("/reviews/{job_id}")
async def get_review(job_id: str):
    job = store.get_job(job_id)
    if job is None:
        raise ApiError("not_found", "Unknown jobId.")
    return job.snapshot()


# --- GET /v1/reviews/{jobId}/stream -------------------------------------------

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/reviews/{job_id}/stream")
async def stream_review(job_id: str):
    job = store.get_job(job_id)
    if job is None:
        raise ApiError("not_found", "Unknown jobId.")

    async def gen():
        sent = 0
        while True:
            # Replay/emit everything appended since we last looked.
            while sent < len(job.events):
                ev = job.events[sent]
                sent += 1
                yield _sse(ev["event"], ev["data"])
            if job.done and sent >= len(job.events):
                break
            await asyncio.sleep(0.05)      # tail live appends without a shared Event

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
