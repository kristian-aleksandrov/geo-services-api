"""
statistics.py
-------------
Router for spatial statistics endpoints.

Returns aggregated summaries — counts, lengths, populations — rather than
raw geometries. These power sidebars, charts, and info panels in the frontend
and are also called as tools by the AI agent.

All spatial aggregations are performed in PostGIS via StatisticsRepository.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.geo_repository import StatisticsRepository
from app.models.schemas import (
    POIStatisticsResponse,
    BuildingStatisticsResponse,
    RoadStatisticsResponse,
    PopulationStatisticsResponse,
    BoundaryAreaResponse,
)

router = APIRouter(prefix="/statistics", tags=["Statistics"])


# ---------------------------------------------------------------------------
# POI statistics
# ---------------------------------------------------------------------------

@router.get("/pois", response_model=POIStatisticsResponse)
def pois_statistics(
    boundary: str,
    boundary_level: str = "province",
    poi_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Count POIs within a boundary, grouped by type.

    - **boundary**: ISO code of the boundary (e.g. BG-02 for Burgas)
    - **boundary_level**: country or province (default: province)
    - **poi_type**: If provided, return count for this type only

    Example:
        GET /statistics/pois?boundary=BG-02
        GET /statistics/pois?boundary=BG-02&poi_type=hospital  → {"total": 29}
    """
    repo = StatisticsRepository(db)
    breakdown = repo.count_pois_by_type(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
        poi_type=poi_type,
    )
    return POIStatisticsResponse(
        boundary_code=boundary.upper(),
        total=sum(item["count"] for item in breakdown),
        breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# Building statistics
# ---------------------------------------------------------------------------

@router.get("/buildings", response_model=BuildingStatisticsResponse)
def buildings_statistics(
    boundary: str,
    boundary_level: str = "province",
    db: Session = Depends(get_db),
):
    """
    Count buildings within a boundary, grouped by type.

    - **boundary**: ISO code of the boundary
    - **boundary_level**: country or province (default: province)

    Example:
        GET /statistics/buildings?boundary=BG-02
    """
    repo = StatisticsRepository(db)
    breakdown = repo.count_buildings_by_type(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
    )
    return BuildingStatisticsResponse(
        boundary_code=boundary.upper(),
        total=sum(item["count"] for item in breakdown),
        breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# Road statistics
# ---------------------------------------------------------------------------

@router.get("/roads", response_model=RoadStatisticsResponse)
def roads_statistics(
    boundary: str,
    boundary_level: str = "country",
    db: Session = Depends(get_db),
):
    """
    Total road length in km within a boundary, grouped by road type.

    Uses ST_Intersection to clip road geometries to the exact boundary extent
    before measuring length. This correctly handles cross-boundary roads.

    - **boundary**: ISO code of the boundary
    - **boundary_level**: country or province (default: country)

    Example:
        GET /statistics/roads?boundary=BGR
    """
    repo = StatisticsRepository(db)
    breakdown = repo.road_length_by_type(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
    )
    return RoadStatisticsResponse(
        boundary_code=boundary.upper(),
        total_km=sum(item["total_km"] for item in breakdown),
        breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# Population statistics
# ---------------------------------------------------------------------------

@router.get("/places", response_model=PopulationStatisticsResponse)
def places_statistics(
    boundary: str,
    boundary_level: str = "country",
    db: Session = Depends(get_db),
):
    """
    Population statistics for places within a boundary.

    Returns total population, place count, and the name of the largest city.

    - **boundary**: ISO code of the boundary
    - **boundary_level**: country or province (default: country)

    Example:
        GET /statistics/places?boundary=BGR
        GET /statistics/places?boundary=BG-02&boundary_level=province
    """
    repo = StatisticsRepository(db)
    result = repo.population_summary(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
    )
    return PopulationStatisticsResponse(
        boundary_code=boundary.upper(),
        **result,
    )


# ---------------------------------------------------------------------------
# Boundary area
# ---------------------------------------------------------------------------

@router.get("/area", response_model=BoundaryAreaResponse)
def boundary_area(
    boundary: str,
    boundary_level: str = "country",
    db: Session = Depends(get_db),
):
    """
    Calculate the area of a boundary in square kilometres.

    Uses ST_Area(geometry::geography) for accurate metric area calculation.

    - **boundary**: ISO code of the boundary
    - **boundary_level**: country or province (default: country)

    Example:
        GET /statistics/area?boundary=BGR
        GET /statistics/area?boundary=BG-02&boundary_level=province
    """
    repo = StatisticsRepository(db)
    area = repo.boundary_area_km2(
        code=boundary.upper(),
        level=boundary_level,
    )
    return BoundaryAreaResponse(
        boundary_code=boundary.upper(),
        area_km2=area,
    )
