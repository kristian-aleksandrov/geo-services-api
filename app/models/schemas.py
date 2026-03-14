"""
schemas.py
----------
Pydantic response models for all API endpoints.

These models define the exact shape of every API response.
FastAPI uses them to:
  - Validate outgoing data
  - Generate the OpenAPI/Swagger documentation automatically
  - Serialize Python dicts to JSON

Every endpoint declares its response_model so the reviewer
sees exactly what the API returns just by reading the code.
"""

from typing import Optional, Any
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# GeoJSON building blocks
# ---------------------------------------------------------------------------

class GeoJSONGeometry(BaseModel):
    """
    A GeoJSON geometry object as returned by PostGIS ST_AsGeoJSON().
    The 'type' field is the geometry type (Point, LineString, Polygon etc.)
    and 'coordinates' holds the raw coordinate array.
    """
    type: str
    coordinates: Any  # nested lists of floats — shape varies by geometry type


class GeoJSONFeature(BaseModel):
    """
    A single GeoJSON Feature — one geometry with its properties.
    This is the standard unit returned by all /layers and /boundaries endpoints.
    """
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    """
    A GeoJSON FeatureCollection — the standard wrapper for multiple features.
    All /boundaries and /layers endpoints return this format so the
    Leaflet frontend can pass the response directly to L.geoJSON().
    """
    type: str = "FeatureCollection"
    features: list[GeoJSONFeature]
    count: int  # total number of features returned


# ---------------------------------------------------------------------------
# Boundary schemas
# ---------------------------------------------------------------------------

class CountryProperties(BaseModel):
    """Properties returned for each country feature."""
    name: str
    formal_name: Optional[str]
    code: str                        # ISO 3166-1 alpha-3 (e.g. KEN)
    continent: Optional[str]
    region_wb: Optional[str]         # World Bank region
    income_group: Optional[str]
    economy: Optional[str]
    pop_est: Optional[int]
    pop_year: Optional[int]
    sovereignt: Optional[str]
    type: Optional[str]


class ProvinceProperties(BaseModel):
    """Properties returned for each province/state feature."""
    name: str
    code: str                        # ISO 3166-2 (e.g. BG-02)
    country_code: str                # Parent country ISO alpha-3
    type: Optional[str]
    type_en: Optional[str]
    region: Optional[str]
    area_sqkm: Optional[float]
    lat: Optional[float]
    lon: Optional[float]


# ---------------------------------------------------------------------------
# Layer schemas
# ---------------------------------------------------------------------------

class RoadProperties(BaseModel):
    """Properties returned for each road feature."""
    name: Optional[str]
    type: Optional[str]
    feature_class: Optional[str]
    length_km: Optional[float]
    expressway: Optional[int]
    toll: Optional[int]
    level: Optional[str]
    local_type: Optional[str]
    country_code: Optional[str]
    continent: Optional[str]


class RiverProperties(BaseModel):
    """Properties returned for each river feature."""
    name: Optional[str]
    name_en: Optional[str]
    type: Optional[str]


class RailroadProperties(BaseModel):
    """Properties returned for each railroad feature."""
    code: Optional[str]
    type: Optional[str]
    category: Optional[str]
    electric: Optional[str]
    multi_track: Optional[str]
    continent: Optional[str]


class PlaceProperties(BaseModel):
    """Properties returned for each populated place feature."""
    name: str
    name_ascii: Optional[str]
    country_code: Optional[str]
    country_name: Optional[str]
    admin1_name: Optional[str]
    type: Optional[str]
    population: Optional[int]
    is_capital: Optional[int]
    is_megacity: Optional[int]
    is_world_city: Optional[int]
    timezone: Optional[str]
    lat: Optional[float]
    lon: Optional[float]


class BuildingProperties(BaseModel):
    """Properties returned for each building feature (Bulgaria OSM)."""
    name: Optional[str]
    type: Optional[str]
    country_code: Optional[str]


class POIProperties(BaseModel):
    """Properties returned for each point of interest (Bulgaria OSM)."""
    name: Optional[str]
    type: Optional[str]              # hospital, school, pharmacy, etc.
    country_code: Optional[str]


class ProtectedAreaProperties(BaseModel):
    """Properties returned for each protected area feature."""
    name: Optional[str]
    feature_class: Optional[str]
    type: Optional[str]
    region: Optional[str]


# ---------------------------------------------------------------------------
# Statistics schemas
# ---------------------------------------------------------------------------

class POITypeCount(BaseModel):
    """Count of POIs of a specific type within a boundary."""
    type: str
    count: int


class POIStatisticsResponse(BaseModel):
    """Response for GET /statistics/pois"""
    boundary_code: str
    total: int
    breakdown: list[POITypeCount]


class BuildingTypeCount(BaseModel):
    """Count of buildings of a specific type within a boundary."""
    type: str
    count: int


class BuildingStatisticsResponse(BaseModel):
    """Response for GET /statistics/buildings"""
    boundary_code: str
    total: int
    breakdown: list[BuildingTypeCount]


class RoadLengthByType(BaseModel):
    """Total road length in km for a specific road type."""
    type: str
    total_km: float


class RoadStatisticsResponse(BaseModel):
    """Response for GET /statistics/roads"""
    boundary_code: str
    total_km: float
    breakdown: list[RoadLengthByType]


class PopulationStatisticsResponse(BaseModel):
    """Response for GET /statistics/places"""
    boundary_code: str
    place_count: int
    total_population: int
    largest_city: Optional[str]


class BoundaryAreaResponse(BaseModel):
    """Response for boundary area calculation."""
    boundary_code: str
    area_km2: float


# ---------------------------------------------------------------------------
# Agent schemas
# ---------------------------------------------------------------------------

class AgentChatRequest(BaseModel):
    """
    Request body for POST /agent/chat.

    Frontend library, version, and capabilities are NOT part of the request.
    They are deployment-time constants read from environment variables:
        FRONTEND_LIBRARY, FRONTEND_VERSION, FRONTEND_CAPABILITIES

    Example:
        {"message": "How many hospitals are in Burgas province?"}
    """
    message: str
    conversation_id: Optional[str] = None  # for multi-turn conversations


class AgentChatResponse(BaseModel):
    """
    Response from POST /agent/chat.

    Contains:
      - answer:   Natural language response from the agent
      - commands: Structured Leaflet map commands (see docs/agent_protocol.md)
      - tools_used: Which API tools the agent called to answer the question
    """
    answer: str
    commands: list[dict[str, Any]]   # Agent-to-Frontend protocol commands
    tools_used: list[str]            # e.g. ["count_pois", "get_province"]
    conversation_id: Optional[str]


# ---------------------------------------------------------------------------
# Health check schema
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Response for GET / health check."""
    status: str
    version: str
