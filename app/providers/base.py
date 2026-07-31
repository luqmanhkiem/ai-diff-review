"""Provider interface. Both `mock` and `llm` implement the same async method so
the pipeline (chunk -> review -> collect -> sort -> dedup) is provider-agnostic.
A provider reviews ONE chunk (a list of file diffs) and returns raw findings;
ordering, dedup and truncation happen once, globally, in review.py."""
from __future__ import annotations

from typing import Protocol

from ..diff_parser import FileDiff
from ..models import Finding


class Provider(Protocol):
    name: str

    async def review_chunk(self, files: list[FileDiff]) -> list[Finding]:
        ...


class ProviderError(Exception):
    """Raised when a provider cannot complete (e.g. llm model unreachable).
    The worker catches this and marks the job `failed` with a clear message."""
