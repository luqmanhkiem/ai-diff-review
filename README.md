# AI Diff Review Service

An async HTTP service that reviews unified diffs and returns structured findings.
Clients `POST` a diff, the service processes it in the background through a
**provider** (`mock` — deterministic rules, or `llm` — a real model), and results
are available by polling or Server-Sent Events.

Implements the take-home contract in `CANDIDATE-TASK.md`.

## Run locally

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
BEARER_TOKEN=dev-local-token .venv/bin/uvicorn app.main:app --port 8000
```

- `GET /health`, `GET /spec` — public
- All `/v1/*` routes require `Authorization: Bearer <BEARER_TOKEN>`

### Quick check

```bash
curl localhost:8000/health
curl -X POST localhost:8000/v1/reviews \
  -H "Authorization: Bearer dev-local-token" -H "Content-Type: application/json" \
  -d '{"diff":"diff --git a/x.js b/x.js\n--- a/x.js\n+++ b/x.js\n@@ -0,0 +1,1 @@\n+eval(x);\n"}'
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

Covers every scored cross-cutting behaviour: mock rules, chunking equivalence,
caching, idempotency, SSE replay, error taxonomy, injection inertness, rate
limiting, and graceful `llm` failure.

## Configuration (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `BEARER_TOKEN` | `dev-local-token` | token clients must present on `/v1/*` |
| `LLM_API_KEY` | *(empty)* | enables the real `llm` provider; unset ⇒ graceful failure |
| `LLM_BASE_URL` | Gemini v1beta | model endpoint |
| `LLM_MODEL` | `gemini-2.0-flash` | model name |
| `LLM_TIMEOUT_SECONDS` | `20` | per-call timeout |

The `llm` provider targets Google Gemini's generateContent API by default (a free
tier exists). Credentials live only on the server; the client's bearer token
never carries a model key. If the model is unreachable/misconfigured, the job
transitions to `failed` with a clear error and the service never crashes.

## Deploy (Render, free tier)

1. Push this repo to GitHub.
2. Render → New → Blueprint → select the repo (`render.yaml` is picked up).
3. Set `BEARER_TOKEN` (and optionally `LLM_API_KEY`) as env vars in the dashboard.
4. Wait for the health check on `/health` to go green; the public URL is your base URL.

Any Docker host works identically (`docker build -t review . && docker run -p 8000:8000 -e BEARER_TOKEN=... review`).

## Architecture

See `SUBMISSION.md` for the design writeup, verification notes, and AI-tool usage.
```
POST /v1/reviews ─▶ validate ─▶ cache/idempotency ─▶ Job(queued) ─▶ enqueue ─▶ 202
worker pool (≤4) ─▶ parse ─▶ chunk (file boundaries) ─▶ provider ─▶ sort/dedup ─▶ events
GET /v1/reviews/{id}          ─▶ snapshot
GET /v1/reviews/{id}/stream   ─▶ replay event log from 0, then tail
```
