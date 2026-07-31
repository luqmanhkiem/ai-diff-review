"""Chunking must not change findings: a diff split across chunk boundaries yields
findings identical to an unchunked scan; only usage.chunks differs."""
import asyncio

from app import config
from app.chunker import chunk_files
from app.diff_parser import parse_diff
from app.providers.mock import MockProvider
from app.review import run_review
from helpers import one_file_diff


def _multi_file_diff(n_files: int, lines_per_file: int) -> str:
    parts = []
    for i in range(n_files):
        lines = [f"console.log('f{i} l{j}');" for j in range(lines_per_file)]
        parts.append(one_file_diff(f"src/file_{i:03d}.js", lines))
    return "\n".join(parts)


def test_boundaries_are_file_aligned():
    files = parse_diff(_multi_file_diff(5, 3))
    # Force a tiny chunk budget so packing actually splits.
    chunks = chunk_files(files, chunk_bytes=200)
    # No file appears in two chunks.
    seen = set()
    for ch in chunks:
        for fd in ch:
            assert fd.path not in seen
            seen.add(fd.path)
    assert len(seen) == 5


def test_oversize_single_file_is_own_chunk():
    big_line = "x" * 300
    diff = one_file_diff("big.js", [f"console.log('{big_line}');"])
    files = parse_diff(diff)
    chunks = chunk_files(files, chunk_bytes=100)
    assert len(chunks) == 1
    assert len(chunks[0]) == 1


def test_chunked_equals_unchunked():
    diff = _multi_file_diff(6, 4)
    provider = MockProvider()

    async def run(chunk_bytes):
        files = parse_diff(diff)
        chunks = chunk_files(files, chunk_bytes=chunk_bytes)
        collected = []
        for ch in chunks:
            collected.extend(await provider.review_chunk(ch))
        from app.review import dedup_and_sort
        return [f.to_dict() for f in dedup_and_sort(collected)], len(chunks)

    small, n_small = asyncio.get_event_loop().run_until_complete(run(150))
    big, n_big = asyncio.get_event_loop().run_until_complete(run(config.CHUNK_BYTES))
    assert small == big                 # identical findings + ordering
    assert n_small > n_big              # but different chunk counts


def test_run_review_reports_chunks():
    diff = _multi_file_diff(3, 2)
    ordered, usage = asyncio.get_event_loop().run_until_complete(
        run_review(diff, MockProvider())
    )
    assert usage.chunks >= 1
    assert usage.inputBytes == len(diff.encode("utf-8"))
