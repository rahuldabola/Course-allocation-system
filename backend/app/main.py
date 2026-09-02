"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import allocation, assistant, courses, dashboard, students
from .seed import ensure_categories


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic (see backend/migrations); run
    # `alembic upgrade head` before starting the app (the Docker image and
    # docker-compose do this automatically). Startup just seeds base categories.
    ensure_categories()
    yield


app = FastAPI(title="AI Course Allocation System", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(students.router)
app.include_router(courses.router)
app.include_router(allocation.router)
app.include_router(dashboard.router)
app.include_router(assistant.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
