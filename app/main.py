import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.models
from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.routers import jobs
from app.services.certificate_generator import register_fonts
from app.services.job_processor import recover_interrupted_jobs

# Configure application logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bulk_cert.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: creates schema, registers fonts, and recovers interrupted jobs."""
    # 1. Initialize DB schema and fonts
    Base.metadata.create_all(bind=engine)
    register_fonts()

    # 2. Check demo failure switch
    if settings.ENABLE_DEMO_FAILURES:
        logger.warning(
            "ENABLE_DEMO_FAILURES is active. Recipients prefixed with 'FAILME' "
            "will simulate transient failures."
        )

    # 3. Crash recovery on startup
    if settings.RECOVER_ON_STARTUP:
        recovered = recover_interrupted_jobs(SessionLocal)
        if recovered:
            logger.info("Recovered %d interrupted jobs on startup: %s", len(recovered), recovered)

    yield


app = FastAPI(
    title="Bulk Certificate Generator",
    description="A fault-tolerant bulk certificate generation API.",
    version="1.0.0",
    lifespan=lifespan,
)

# Register API routers
app.include_router(jobs.router, prefix="/api")


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Health check endpoint that verifies API liveness and database connectivity."""
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "database": "ok"},
        )
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "error"},
        )
