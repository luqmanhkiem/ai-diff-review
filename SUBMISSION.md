# SUBMISSION

## Architecture (the short version)

An async job service built on FastAPI (Python 3.11), single process, in-memory
state. `POST /v1/reviews` validates the request, checks the idempotency and
content caches, creates a `Job(queued)`, enqueues its id, and returns `202`
immediately. A bounded pool of 4 asyncio workers pulls jobs off an
`asyncio.Queue`, parses the diff, chunks it on file boundaries, runs the selected
provider per chunk, then globally sorts + dedups the findings. Each job owns an
**append-only event log**; workers append `status`/`finding`/`done` events as they
go. `GET /v1/reviews/{id}` returns a snapshot; the SSE endpoint replays that log
from index 0 and then tails new appends — which is why a finished job's stream is
identical to the live one. Everything the pipeline enforces (limits, provider list)
is read from `app/config.py`, so `/spec` can never drift from real behaviour.

## Provider design

A `Provider` protocol (`app/providers/base.py`) exposes one method,
`review_chunk(files) -> list[Finding]`. The pipeline is provider-agnostic:
chunk → review → collect → sort → dedup → truncate all live in `app/review.py`,
so both providers share ordering, dedup and `maxFindings` semantics.

- **`mock`** (`providers/mock.py`) — the scored path. Pure, deterministic pattern
  matching of the 9 rules on added lines only. `line` is the new-file line number
  from the hunk header. MOCK-004 (empty catch) is the one stateful rule: it joins a
  file's added lines with a char→line map and reports on the `catch` line.
- **`llm`** (`providers/llm.py`) — real model (Google Gemini by default) behind the
  same interface. Credentials are server-side env vars; the client bearer token
  never carries a model key. The diff is passed as **delimited data**, never in the
  instruction slot, and model output is validated against the finding schema
  (malformed items dropped). If the model is unset/unreachable it raises
  `ProviderError`, which the worker turns into a `failed` job with a clear message —
  never a crash, and `GET` still returns `200`.

## Caching vs idempotency (deliberately separate)

- **Caching** is keyed on content — a SHA-256 of `{diff, provider, maxFindings}`.
  A byte-identical resubmit (any key or none) creates a new job that **copies** the
  cached findings and reports `usage.cacheHit: true` — so the *result* carries the
  flag as the contract requires, without redoing work.
- **Idempotency** is keyed on the `Idempotency-Key` header, compared against a hash
  of the raw request body: same key + identical body → the same `jobId`; same key +
  different body → `409 idempotency_conflict`.

Validation precedence is strict: `413` (size) → `400` (JSON) → `422` (diff) →
idempotency → cache. Size is checked before parsing so a huge body is never buffered
into the JSON parser.

## How I verified the cross-cutting behaviours

Two layers: `pytest tests/` (29 unit/integration tests, runs in <1s) for the
internal logic, and `scripts/smoke_test.py <url> <token>` — 40 checks over real
HTTP against the running service, which is how I verified the live deployment
before submitting. Specifically:

- **Chunking** (`test_chunking.py`): the same multi-file diff is scanned with a tiny
  chunk budget and with the real 64 KiB budget; findings + ordering are asserted
  **identical**, only `usage.chunks` differs. Separate tests assert file-aligned
  boundaries and that an oversize single file becomes its own chunk.
- **Caching / idempotency** (`test_cache_idem.py`): first run `cacheHit:false`,
  identical resubmit `cacheHit:true` with identical findings; same key+body → same
  jobId; same key+different body → `409`.
- **SSE replay** (`test_sse_replay.py`): two connections to a finished job are parsed
  and asserted **equal**, with exactly one `finding` event per finding and a trailing
  `done`. Stream also enforces auth.
- **Injection inertness** (`test_injection.py`): a diff mixing injection phrases with
  `eval(`/`console.log(` — MOCK-INJ fires *and* the other rules are unaffected.
- **Error taxonomy / lifecycle** (`test_contract.py`): 202/400/413/422/401/404,
  `/spec` equals config, unknown fields ignored, `maxFindings` truncates output while
  `usage` reflects the full scan.
- **Rate limiting** (`test_rate_limit.py`): a POST burst yields `429` + `Retry-After`
  and **never** 5xx; GET storms are never limited.
- **Graceful llm failure**: `provider:llm` with no key → `failed` job, `GET` still 200.

## AI tools used

Built with Claude Code (Claude Opus) as a pair — I drove the design decisions and
spec interpretation; the tool scaffolded modules and tests to my direction. I read
and understood every file; nothing was accepted blind.

## An AI suggestion I rejected (and why)

The tool's first cut stored only the **final findings** on the job and planned to
reconstruct SSE events on demand. I rejected it: the contract says a finished job's
stream must **replay all events identically**, and reconstructing events after the
fact can silently diverge from what a live subscriber saw (ordering, the `status`
transitions, the `done` payload). I replaced it with a single **append-only event
log** that both the live path and replays read from — making "identical" true *by
construction* rather than by best effort. (A second, smaller rejection: an initial
MOCK-002 credential regex matched unquoted assignments like `token = getToken()`;
the rule requires a quoted 16+ char literal, so I tightened it and added a negative
test.)

## What I'd do next with more time

- **Durability / scale-out**: move jobs + cache to Redis so the service survives a
  restart and workers scale horizontally; the three in-memory dicts are the only
  thing tying it to one process.
- **Job eviction / TTL** to bound memory over long runs.
- **Distributed rate limiting** (currently per-process) once multi-instance.
- **Richer `llm` path**: multiple vendors behind the interface, retries with
  backoff, and reconciling model line numbers against the parsed diff.
- **Observability**: structured logs + per-stage metrics (queue depth, chunk counts,
  latency histograms).
- **Diff-parser fuzzing** against real-world `git` and `diff -u` corpora.
