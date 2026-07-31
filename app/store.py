"""In-memory state. Deliberate tradeoff for a single-instance 48h service:
simple, fast, and everything the contract needs (jobs, content cache, idempotency
keys) is process-local. Swap these three dicts for Redis to scale horizontally.

Concurrency note: FastAPI/uvicorn run these handlers on one asyncio event loop,
so plain dict access is safe without locks as long as we never `await` in the
middle of a read-modify-write. The critical sections here don't."""
from __future__ import annotations

from typing import Optional

from .models import Job

# jobId -> Job
jobs: dict[str, Job] = {}

# content hash of {diff, options} -> jobId (the cache)
cache_index: dict[str, str] = {}

# Idempotency-Key -> {"body_hash": str, "job_id": str}
idempotency_index: dict[str, dict] = {}


def get_job(job_id: str) -> Optional[Job]:
    return jobs.get(job_id)


def put_job(job: Job) -> None:
    jobs[job.id] = job
    cache_index[job.body_hash] = job.id


def find_cached_job(body_hash: str) -> Optional[Job]:
    job_id = cache_index.get(body_hash)
    return jobs.get(job_id) if job_id else None


def reset() -> None:
    """Test helper — clear all state."""
    jobs.clear()
    cache_index.clear()
    idempotency_index.clear()
