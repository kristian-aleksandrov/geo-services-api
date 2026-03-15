"""
Geo Services API
================
Main FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.routers import boundaries, layers, statistics, agent

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Geo Services API",
    description=(
        "Vector geospatial layers with boundary-based spatial analysis "
        "and a natural language AI agent interface. "
        "Data sourced from Natural Earth 10m and OpenStreetMap."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — allow Leaflet frontend to call the API from any origin
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Frontend — serve static files
# ---------------------------------------------------------------------------
import os
if os.path.exists("frontend"):
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.get("/map", include_in_schema=False)
def serve_frontend():
    return FileResponse("frontend/index.html")

# ---------------------------------------------------------------------------
# Routers
# Prefixes are defined inside each router — do not add them here again.
# ---------------------------------------------------------------------------

app.include_router(boundaries.router)
app.include_router(layers.router)
app.include_router(statistics.router)
app.include_router(agent.router)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root():
    return {
        "status":  "ok",
        "message": "Geo Services API is running",
        "docs":    "/docs",
        "version": "1.0.0",
    }
