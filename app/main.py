"""App wiring: register error handlers, mount routes, start the worker pool on
startup. Run with `uvicorn app.main:app`."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import queue
from .errors import ApiError, api_error_handler, unhandled_handler
from .routes import public, reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue.start_workers()
    yield
    await queue.stop_workers()


app = FastAPI(title="AI Diff Review Service", version="1.0.0", lifespan=lifespan)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(Exception, unhandled_handler)

app.include_router(public.router)
app.include_router(reviews.router)
