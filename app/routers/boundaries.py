"""
boundaries.py
-------------
Router for administrative boundary endpoints.

Serves country and province geometries as GeoJSON FeatureCollections.
The Leaflet frontend passes responses directly to L.geoJSON() to draw
boundary outlines on the map.

All data access is delegated to BoundaryRepository — no SQL here.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.geo_repository import BoundaryRepository
from app.models.schemas import GeoJSONFeatureCollection

router = APIRouter(prefix="/boundaries", tags=["Boundaries"])


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------

@router.get("/countries", response_model=GeoJSONFeatureCollection)
def get_countries(
    continent: Optional[str] = None,
    region_wb: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Return all country boundaries as a GeoJSON FeatureCollection.

    Optional filters:
    - **continent**: Africa, Asia, Europe, North America, South America, Oceania, Antarctica
    - **region_wb**: World Bank region (e.g. Sub-Saharan Africa, Europe & Central Asia)

    Example:
        GET /boundaries/countries?continent=Africa
        GET /boundaries/countries?region_wb=Sub-Saharan%20Africa
    """
    repo = BoundaryRepository(db)
    features = repo.get_countries(continent=continent, region_wb=region_wb)
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


@router.get("/countries/{code}", response_model=GeoJSONFeatureCollection)
def get_country_by_code(
    code: str,
    db: Session = Depends(get_db),
):
    """
    Return a single country boundary by ISO 3166-1 alpha-3 code.

    Example:
        GET /boundaries/countries/KEN
        GET /boundaries/countries/BGR
    """
    repo = BoundaryRepository(db)
    feature = repo.get_country_by_code(code=code.upper())
    if not feature:
        raise HTTPException(status_code=404, detail=f"Country '{code}' not found.")
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=[feature],
        count=1,
    )


# ---------------------------------------------------------------------------
# Provinces
# ---------------------------------------------------------------------------

@router.get("/provinces", response_model=GeoJSONFeatureCollection)
def get_provinces(
    country_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Return province/state boundaries as a GeoJSON FeatureCollection.

    Optional filters:
    - **country_code**: ISO 3166-1 alpha-3 code of the parent country (e.g. BGR)

    Example:
        GET /boundaries/provinces?country_code=BGR
        GET /boundaries/provinces?country_code=KEN
    """
    repo = BoundaryRepository(db)
    features = repo.get_provinces(country_code=country_code.upper() if country_code else None)
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=features,
        count=len(features),
    )


@router.get("/provinces/{code}", response_model=GeoJSONFeatureCollection)
def get_province_by_code(
    code: str,
    db: Session = Depends(get_db),
):
    """
    Return a single province by ISO 3166-2 code.

    Example:
        GET /boundaries/provinces/BG-02     (Burgas, Bulgaria)
        GET /boundaries/provinces/US-CA     (California, USA)
    """
    repo = BoundaryRepository(db)
    feature = repo.get_province_by_code(code=code.upper())
    if not feature:
        raise HTTPException(status_code=404, detail=f"Province '{code}' not found.")
    return GeoJSONFeatureCollection(
        type="FeatureCollection",
        features=[feature],
        count=1,
    )
