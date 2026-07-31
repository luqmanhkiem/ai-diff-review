"""Public, unauthenticated endpoints: /health and /spec. /spec reads the same
config constants the pipeline enforces, so its declared limits can never drift
from actual behaviour."""
import time

from fastapi import APIRouter

from .. import config

router = APIRouter()
_STARTED = time.time()


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": config.VERSION,
        "uptimeSeconds": round(time.time() - _STARTED, 3),
    }


@router.get("/spec")
def spec() -> dict:
    return {
        "specVersion": config.SPEC_VERSION,
        "providers": config.PROVIDERS,
        "limits": config.spec_limits(),
    }
