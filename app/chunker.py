"""Chunking. Diffs over CHUNK_BYTES are split into chunks of at most CHUNK_BYTES,
ONLY on file boundaries — one file's diff never spans two chunks. A single file
larger than CHUNK_BYTES becomes its own (over-size) chunk rather than being split
mid-file, because rules like the multi-line empty-catch depend on seeing a whole
file's hunks together.

Chunking is purely an iteration strategy: findings are collected across all chunks
and then globally sorted/deduped, so the result is identical to an unchunked scan.
Only `usage.chunks` observes the boundary count."""
from __future__ import annotations

from . import config
from .diff_parser import FileDiff


def chunk_files(files: list[FileDiff], chunk_bytes: int = config.CHUNK_BYTES) -> list[list[FileDiff]]:
    """Greedily pack whole files into chunks of at most `chunk_bytes`."""
    chunks: list[list[FileDiff]] = []
    current: list[FileDiff] = []
    current_size = 0

    for fd in files:
        size = fd.byte_size
        if size > chunk_bytes:
            # Oversize single file: flush what we have, then it stands alone.
            if current:
                chunks.append(current)
                current, current_size = [], 0
            chunks.append([fd])
            continue
        if current and current_size + size > chunk_bytes:
            chunks.append(current)
            current, current_size = [], 0
        current.append(fd)
        current_size += size

    if current:
        chunks.append(current)
    return chunks
