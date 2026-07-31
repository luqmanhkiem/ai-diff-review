"""Error envelope + the machine-code vocabulary. Every non-2xx response in the
service goes through ApiError so the body is always {"error": {"code","message"}}
with a code drawn from the fixed set below."""
from fastapi import Request
from fastapi.responses import JSONResponse

# The only codes the contract permits.
CODES = {
    "unauthorized": 401,
    "payload_too_large": 413,
    "invalid_json": 400,
    "invalid_diff": 422,
    "idempotency_conflict": 409,
    "not_found": 404,
    "rate_limited": 429,
    "internal": 500,
}


class ApiError(Exception):
    """Raise anywhere; the handler renders the correct status + envelope."""

    def __init__(self, code: str, message: str, headers: dict | None = None):
        self.code = code
        self.message = message
        self.status = CODES[code]
        self.headers = headers or {}
        super().__init__(message)


def envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=envelope(exc.code, exc.message),
        headers=exc.headers,
    )


async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    # Last line of defence: any unexpected error still returns the envelope,
    # never a bare stack trace, and never leaks internals to the client.
    return JSONResponse(
        status_code=500,
        content=envelope("internal", "An unexpected error occurred."),
    )
