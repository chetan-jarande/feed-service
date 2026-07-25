from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from dependencies import create_http_session
from logger import get_logger
from routers import core, feed, pypi

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown events."""
    logger.info("Initiating Feed Service startup sequence...")
    session = create_http_session()
    app.state.http_session = session
    logger.info("Application startup complete. HTTP connection pool initialized.")
    try:
        yield
    finally:
        logger.info("Initiating Feed Service shutdown sequence...")
        session.close()
        logger.info("HTTP connection pool closed. Shutdown sequence complete.")


app = FastAPI(
    title="Python Feed Service",
    version="1.0.0",
    description="Inspect, download, analyze, and publish Python wheels for private Azure DevOps Artifacts feeds.",
    lifespan=lifespan,
)

# --- API Routers ---
app.include_router(core.router)
app.include_router(pypi.router)
app.include_router(feed.router)


# --- Root Endpoint ---
@app.get("/", tags=["Root"])
def read_root() -> JSONResponse:
    """Root endpoint providing basic service information."""
    return JSONResponse(
        content={
            "message": "Welcome to Python Feed Service",
            "docs_url": "/docs",
            "status": "operational",
        }
    )


# --- Health Check Endpoint ---
@app.get(
    "/health",
    description="Endpoint for Service Availability.",
    tags=["Health Check"],
)
def service_status_check() -> JSONResponse:
    """Provides the operational status of the service."""
    return JSONResponse(content={"status": "ok", "service": "Python Feed Service"}, status_code=200)
