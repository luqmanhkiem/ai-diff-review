"""Pipeline orchestration: parse -> chunk -> provider per chunk -> collect ->
global sort -> dedup by id. Chunking is invisible to the result: we merge every
chunk's findings and order them once, so chunked and unchunked scans of the same
diff are byte-for-byte identical. Truncation to maxFindings happens in the worker
(so `usage` can still report the full count)."""
from __future__ import annotations

from .chunker import chunk_files
from .diff_parser import parse_diff
from .models import Finding, Usage
from .providers.base import Provider


def dedup_and_sort(findings: list[Finding]) -> list[Finding]:
    by_id: dict[str, Finding] = {}
    for f in findings:
        by_id.setdefault(f.id, f)          # dedup by id, keep first
    return sorted(by_id.values(), key=lambda f: f.sort_key())


async def run_review(diff: str, provider: Provider) -> tuple[list[Finding], Usage]:
    """Returns the FULL ordered/deduped finding list plus usage. May raise
    diff_parser.InvalidDiff (caller validated already) or ProviderError."""
    files = parse_diff(diff)
    chunks = chunk_files(files)

    collected: list[Finding] = []
    for chunk in chunks:
        collected.extend(await provider.review_chunk(chunk))

    ordered = dedup_and_sort(collected)
    usage = Usage(
        inputBytes=len(diff.encode("utf-8")),
        chunks=len(chunks),
        cacheHit=False,
    )
    return ordered, usage
