from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Lifespan setup (DB table creation & crash recovery added in later phases)
    yield
    # Lifespan teardown


app = FastAPI(
    title="Bulk Certificate Generator",
    description="A fault-tolerant bulk certificate generation API.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint to verify service liveness."""
    return {"status": "ok"}
