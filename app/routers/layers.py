"""
layers.py
---------
Router for vector layer endpoints.

Serves spatial features clipped to a boundary as GeoJSON FeatureCollections.
Every endpoint requires a boundary code — the repository uses ST_Intersects
to filter features to the requested geographic extent.

Leaflet frontend passes responses directly to L.geoJSON() to render layers.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.geo_repository import LayerRepository
from app.models.schemas import GeoJSONFeatureCollection

router = APIRouter(prefix="/layers", tags=["Layers"])


# ---------------------------------------------------------------------------
# Roads
# ---------------------------------------------------------------------------

@router.get("/roads", response_model=GeoJSONFeatureCollection)
def get_roads(
    boundary: str,
    boundary_level: str = "country",
    road_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Return roads intersecting a boundary as a GeoJSON FeatureCollection.

    - **boundary**: ISO code of the boundary (e.g. KEN, BGR, BG-02)
    - **boundary_level**: country or province (default: country)
    - **road_type**: Optional filter (e.g. Major Highway, Secondary Highway)

    Example:
        GET /layers/roads?boundary=BGR
        GET /layers/roads?boundary=BG-02&boundary_level=province&road_type=Major%20Highway
    """
    repo = LayerRepository(db)
    features = repo.get_roads(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
        road_type=road_type,
    )
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


# ---------------------------------------------------------------------------
# Rivers
# ---------------------------------------------------------------------------

@router.get("/rivers", response_model=GeoJSONFeatureCollection)
def get_rivers(
    boundary: str,
    boundary_level: str = "country",
    db: Session = Depends(get_db),
):
    """
    Return rivers intersecting a boundary as a GeoJSON FeatureCollection.

    - **boundary**: ISO code of the boundary (e.g. KEN, BGR)
    - **boundary_level**: country or province (default: country)

    Example:
        GET /layers/rivers?boundary=EGY
    """
    repo = LayerRepository(db)
    features = repo.get_rivers(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
    )
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


# ---------------------------------------------------------------------------
# Railroads
# ---------------------------------------------------------------------------

@router.get("/railroads", response_model=GeoJSONFeatureCollection)
def get_railroads(
    boundary: str,
    boundary_level: str = "country",
    db: Session = Depends(get_db),
):
    """
    Return railroads intersecting a boundary as a GeoJSON FeatureCollection.

    - **boundary**: ISO code of the boundary
    - **boundary_level**: country or province (default: country)

    Example:
        GET /layers/railroads?boundary=BGR
    """
    repo = LayerRepository(db)
    features = repo.get_railroads(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
    )
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------

@router.get("/places", response_model=GeoJSONFeatureCollection)
def get_places(
    boundary: str,
    boundary_level: str = "country",
    min_population: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Return populated places within a boundary as a GeoJSON FeatureCollection.

    - **boundary**: ISO code of the boundary
    - **boundary_level**: country or province (default: country)
    - **min_population**: Optional minimum population filter

    Example:
        GET /layers/places?boundary=BGR
        GET /layers/places?boundary=BGR&min_population=50000
    """
    repo = LayerRepository(db)
    features = repo.get_places(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
        min_population=min_population,
    )
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


# ---------------------------------------------------------------------------
# Buildings (Bulgaria OSM)
# ---------------------------------------------------------------------------

@router.get("/buildings", response_model=GeoJSONFeatureCollection)
def get_buildings(
    boundary: str,
    boundary_level: str = "province",
    building_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Return building footprints within a boundary (Bulgaria OSM data).

    - **boundary**: ISO code of the boundary (e.g. BGR, BG-02)
    - **boundary_level**: country or province (default: province)
    - **building_type**: Optional filter by building type

    Example:
        GET /layers/buildings?boundary=BG-02
        GET /layers/buildings?boundary=BGR&boundary_level=country
    """
    repo = LayerRepository(db)
    features = repo.get_buildings(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
        building_type=building_type,
    )
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


# ---------------------------------------------------------------------------
# POIs (Bulgaria OSM)
# ---------------------------------------------------------------------------

@router.get("/pois", response_model=GeoJSONFeatureCollection)
def get_pois(
    boundary: str,
    boundary_level: str = "province",
    poi_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Return points of interest within a boundary (Bulgaria OSM data).

    - **boundary**: ISO code of the boundary (e.g. BGR, BG-02)
    - **boundary_level**: country or province (default: province)
    - **poi_type**: Optional filter (e.g. hospital, school, pharmacy, bank)

    Example:
        GET /layers/pois?boundary=BG-02&poi_type=hospital
        GET /layers/pois?boundary=BGR&boundary_level=country&poi_type=school
    """
    repo = LayerRepository(db)
    features = repo.get_pois(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
        poi_type=poi_type,
    )
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


# ---------------------------------------------------------------------------
# Protected Areas
# ---------------------------------------------------------------------------

@router.get("/protected_areas", response_model=GeoJSONFeatureCollection)
def get_protected_areas(
    boundary: str,
    boundary_level: str = "country",
    db: Session = Depends(get_db),
):
    """
    Return protected areas intersecting a boundary as a GeoJSON FeatureCollection.

    - **boundary**: ISO code of the boundary
    - **boundary_level**: country or province (default: country)

    Example:
        GET /layers/protected_areas?boundary=KEN
    """
    repo = LayerRepository(db)
    features = repo.get_protected_areas(
        boundary_code=boundary.upper(),
        boundary_level=boundary_level,
    )
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )
