"""Async job queue + a bounded worker pool. MAX_CONCURRENT_JOBS workers pull job
ids off an asyncio.Queue, so at most that many jobs run at once; a queued 5th job
simply waits for a free worker instead of being rejected. Workers drive the job
through its lifecycle and append to the job's event log as they go, which is what
the SSE endpoint streams/replays."""
from __future__ import annotations

import asyncio

from . import config, store
from .models import Finding
from .providers.base import ProviderError
from .providers.llm import get_provider
from .review import run_review

# Created fresh in start_workers() so the queue always binds to the currently
# running event loop (important for tests, where each TestClient uses a new loop).
_queue: asyncio.Queue[str] | None = None
_workers: list[asyncio.Task] = []


def enqueue(job_id: str) -> None:
    if _queue is None:
        raise RuntimeError("worker pool not started")
    _queue.put_nowait(job_id)


async def _process(job_id: str) -> None:
    job = store.get_job(job_id)
    if job is None:
        return
    job.status = "running"
    job.emit("status", {"status": "running"})
    try:
        provider = get_provider(job.provider)
        ordered, usage = await run_review(job.diff, provider)

        # usage reflects the FULL scan; the response list is truncated to maxFindings.
        truncated: list[Finding] = ordered[: job.max_findings]
        job.usage.inputBytes = usage.inputBytes
        job.usage.chunks = usage.chunks
        job.findings = truncated

        for f in truncated:
            job.emit("finding", f.to_dict())

        job.status = "done"
        job.emit("status", {"status": "done"})
        job.emit("done", {"total": len(truncated), "usage": job.usage.to_dict()})
    except ProviderError as e:
        job.status = "failed"
        job.error = str(e)
        job.emit("status", {"status": "failed"})
        job.emit("done", {"total": 0, "usage": job.usage.to_dict(), "error": str(e)})
    except Exception as e:  # never crash the worker; fail the job cleanly
        job.status = "failed"
        job.error = f"internal error: {e}"
        job.emit("status", {"status": "failed"})
        job.emit("done", {"total": 0, "usage": job.usage.to_dict(), "error": job.error})
    finally:
        job.done = True
        job._updated.set()


async def _worker(q: asyncio.Queue[str]) -> None:
    while True:
        job_id = await q.get()
        try:
            await _process(job_id)
        finally:
            q.task_done()


def start_workers() -> None:
    global _queue
    if _workers:
        return
    _queue = asyncio.Queue()
    for _ in range(config.MAX_CONCURRENT_JOBS):
        _workers.append(asyncio.create_task(_worker(_queue)))


async def stop_workers() -> None:
    global _queue
    for w in _workers:
        w.cancel()
    _workers.clear()
    _queue = None
