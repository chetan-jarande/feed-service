from fastapi import FastAPI
from fastapi.responses import JSONResponse

from routers import core, feed, pypi

app = FastAPI(
    title="Python Feed Service",
    version="1.0.0",
    description="Inspect, download, analyze, and publish Python wheels for private Azure DevOps Artifacts feeds.",
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
