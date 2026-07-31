"""Bearer-token auth for every /v1/* route (GET included). /health and /spec
stay public because they carry no data and the scorer probes them unauthenticated."""
import hmac

from fastapi import Request

from . import config
from .errors import ApiError


def require_bearer(request: Request) -> None:
    """FastAPI dependency. Raises 401 (envelope) on missing/malformed/wrong token."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError("unauthorized", "Missing or malformed Authorization header.")
    token = header[len("Bearer "):].strip()
    # Constant-time compare so we don't leak token length/prefix via timing.
    if not hmac.compare_digest(token, config.BEARER_TOKEN):
        raise ApiError("unauthorized", "Invalid bearer token.")
