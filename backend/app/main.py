"""FastAPI application entrypoint."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import settings
from .database import SessionLocal
from .routers import allocation, assistant, auth, courses, dashboard, meta, students
from .seed import bootstrap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic (see backend/migrations); `alembic upgrade head`
    # runs before the app starts (the Docker image does this automatically).
    # Startup seeds base categories, bootstrap users and, in demo mode, sample data.
    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
    log.info(
        "Started v%s (env=%s, demo_mode=%s, llm=%s)",
        __version__,
        settings.environment,
        settings.demo_mode,
        settings.effective_llm_provider,
    )
    yield


app = FastAPI(
    title="AI Course Allocation System",
    version=__version__,
    description=(
        "Merit + reservation based course seat allocation with an AI reporting assistant. "
        "Sign in via `POST /auth/login`, then click **Authorize** and paste the token."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # auth is a bearer header, not cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Total-Count", "Content-Disposition", "Retry-After"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    if request.url.path != "/health":
        log.info(
            "%s %s -> %d (%.0f ms)",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(meta.router)
app.include_router(auth.router)
app.include_router(students.router)
app.include_router(courses.router)
app.include_router(allocation.router)
app.include_router(dashboard.router)
app.include_router(assistant.router)
