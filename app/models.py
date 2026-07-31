"""Data shapes. Findings/usage are plain dataclasses (we control their JSON
exactly); the request body is validated loosely because the contract says
'unknown body fields are ignored' and diff-validity is a 422, not a 400."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

Severity = Literal["critical", "high", "medium", "low"]
Category = Literal["security", "correctness", "performance", "style"]
Status = Literal["queued", "running", "done", "failed"]


@dataclass(frozen=True)
class Finding:
    ruleId: str
    path: str
    line: int
    severity: Severity
    category: Category
    title: str
    evidence: str

    @property
    def id(self) -> str:
        # Deterministic identity used for dedup and for the finding's `id` field.
        return f"{self.ruleId}:{self.path}:{self.line}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ruleId": self.ruleId,
            "path": self.path,
            "line": self.line,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "evidence": self.evidence,
        }

    def sort_key(self) -> tuple:
        # Global ordering everywhere: path, then line asc, then ruleId.
        return (self.path, self.line, self.ruleId)


@dataclass
class Usage:
    inputBytes: int = 0
    chunks: int = 0
    cacheHit: bool = False

    def to_dict(self) -> dict:
        return {
            "inputBytes": self.inputBytes,
            "chunks": self.chunks,
            "cacheHit": self.cacheHit,
        }


@dataclass
class Job:
    id: str
    diff: str
    provider: str
    max_findings: int
    body_hash: str                       # hash of {diff, options} — the cache key
    status: Status = "queued"
    findings: list[Finding] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    # Append-only event log powering SSE. Each entry is a ready-to-send SSE dict
    # {"event": ..., "data": {...}}. A late subscriber replays this from index 0,
    # which is why finished-job streams reproduce the live stream identically.
    events: list[dict] = field(default_factory=list)
    # Set whenever a new event is appended so streaming subscribers wake up.
    _updated: asyncio.Event = field(default_factory=asyncio.Event)
    done: bool = False                   # terminal (done|failed) — closes streams

    def emit(self, event: str, data: dict) -> None:
        self.events.append({"event": event, "data": data})
        self._updated.set()

    def snapshot(self) -> dict:
        """Body of GET /v1/reviews/{id}."""
        out = {
            "jobId": self.id,
            "status": self.status,
            "usage": self.usage.to_dict(),
        }
        if self.status == "done":
            out["findings"] = [f.to_dict() for f in self.findings]
        if self.status == "failed" and self.error:
            out["error"] = self.error
        return out
