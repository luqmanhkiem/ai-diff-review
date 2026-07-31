"""Central configuration. Every limit here is also reported verbatim by GET /spec,
so /spec can never drift from real behaviour: both read the same constants."""
import os

# Service identity
VERSION = "1.0.0"
SPEC_VERSION = "1.0"

# The bearer token we hand to the scorer at submission. Override in production
# via the BEARER_TOKEN env var; the default is only for local development.
BEARER_TOKEN = os.getenv("BEARER_TOKEN", "dev-local-token")

# Hard limits — these are the numbers /spec advertises and the pipeline enforces.
MAX_PAYLOAD_BYTES = 1_048_576          # 1 MiB — POST bodies larger than this => 413
CHUNK_BYTES = 65_536                    # 64 KiB — file-boundary chunk ceiling
MAX_CONCURRENT_JOBS = 4                 # worker pool size
RATE_LIMIT_PER_MINUTE = 30             # sustained POST /v1/reviews submissions/min

# Small burst allowance on top of the sustained rate so a legitimate client that
# briefly bunches requests is not punished; beyond this we return 429.
RATE_LIMIT_BURST = 10

# Default review options
DEFAULT_PROVIDER = "mock"
DEFAULT_MAX_FINDINGS = 100
PROVIDERS = ["mock", "llm"]

# LLM provider config (optional). If LLM_API_KEY is unset or the endpoint is
# unreachable, the llm path fails the job gracefully instead of crashing.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))


def spec_limits() -> dict:
    """The exact object GET /spec exposes under `limits`."""
    return {
        "maxPayloadBytes": MAX_PAYLOAD_BYTES,
        "chunkBytes": CHUNK_BYTES,
        "maxConcurrentJobs": MAX_CONCURRENT_JOBS,
        "rateLimitPerMinute": RATE_LIMIT_PER_MINUTE,
    }
