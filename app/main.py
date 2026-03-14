"""
Geo Services API
================
Main FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import boundaries, layers, statistics, agent

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Geo Services API",
    description=(
        "Vector geospatial layers with boundary-based spatial analysis "
        "and a natural language AI agent interface. "
        "Data sourced from Natural Earth 10m."
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
# Routers
# ---------------------------------------------------------------------------

app.include_router(boundaries.router, prefix="/boundaries", tags=["Boundaries"])
app.include_router(layers.router,     prefix="/layers",     tags=["Layers"])
app.include_router(statistics.router, prefix="/statistics", tags=["Statistics"])
app.include_router(agent.router,      prefix="/agent",      tags=["Agent"])

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root():
    return {
        "status": "ok",
        "message": "Geo Services API is running",
        "docs": "/docs",
    }
