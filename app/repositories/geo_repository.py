"""
geo_repository.py
-----------------
Repository layer for all geospatial database access.

All PostGIS spatial queries are encapsulated here. API routers never
write SQL directly — they call repository methods. This keeps business
logic in routers and data access logic in one place.

Pattern: Repository per domain (boundaries, layers, statistics).
Each method accepts filter parameters and returns GeoJSON-ready dicts.
"""

from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Base repository
# ---------------------------------------------------------------------------

class GeoRepository:
    """Base repository. Holds the database session."""

    def __init__(self, db: Session):
        self.db = db


# ---------------------------------------------------------------------------
# Boundaries repository
# ---------------------------------------------------------------------------

class BoundaryRepository(GeoRepository):
    """
    Handles all queries against geo.countries and geo.provinces.
    """

    def get_countries(
        self,
        continent: Optional[str] = None,
        region_wb: Optional[str] = None,
    ) -> list[dict]:
        """
        Return all country boundaries as GeoJSON features.

        Args:
            continent:  Filter by continent name (e.g. 'Africa')
            region_wb:  Filter by World Bank region (e.g. 'Sub-Saharan Africa')

        Returns:
            List of GeoJSON feature dicts with geometry and properties.

        SQL pattern:
            SELECT name, code, continent, region_wb, pop_est, income_group,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.countries
            WHERE continent = :continent   -- if provided
            AND   region_wb = :region_wb   -- if provided
        """
        raise NotImplementedError

    def get_country_by_code(self, code: str) -> Optional[dict]:
        """
        Return a single country boundary by ISO 3166-1 alpha-3 code.

        Args:
            code:  ISO alpha-3 country code (e.g. 'KEN', 'BGR')

        Returns:
            GeoJSON feature dict or None if not found.

        SQL pattern:
            SELECT name, code, continent, region_wb, pop_est, income_group,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.countries
            WHERE code = :code
        """
        raise NotImplementedError

    def get_provinces(
        self,
        country_code: Optional[str] = None,
    ) -> list[dict]:
        """
        Return province/state boundaries as GeoJSON features.

        Args:
            country_code:  Filter by parent country ISO code (e.g. 'BGR')

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT name, code, country_code, type, area_sqkm,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.provinces
            WHERE country_code = :country_code   -- if provided
        """
        raise NotImplementedError

    def get_province_by_code(self, code: str) -> Optional[dict]:
        """
        Return a single province by ISO 3166-2 code.

        Args:
            code:  ISO 3166-2 code (e.g. 'BG-02' for Burgas)

        Returns:
            GeoJSON feature dict or None if not found.

        SQL pattern:
            SELECT name, code, country_code, type, area_sqkm,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.provinces
            WHERE code = :code
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Layers repository
# ---------------------------------------------------------------------------

class LayerRepository(GeoRepository):
    """
    Handles spatial queries for all vector layers:
    roads, rivers, railroads, places, buildings, pois, protected_areas.

    All methods use ST_Intersects against the appropriate boundary table
    to filter features by geographic extent.
    """

    def get_roads(
        self,
        boundary_code: str,
        boundary_level: str = "country",
        road_type: Optional[str] = None,
    ) -> list[dict]:
        """
        Return roads intersecting a boundary.

        Args:
            boundary_code:   ISO code of the boundary (e.g. 'KEN', 'BG-02')
            boundary_level:  'country' or 'province' — determines which
                             boundary table to join against
            road_type:       Optional filter by road type (e.g. 'Major Highway')

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT r.name, r.type, r.length_km, r.expressway, r.toll,
                   ST_AsGeoJSON(r.geometry)::json AS geometry
            FROM geo.roads r
            JOIN geo.countries c ON ST_Intersects(r.geometry, c.geometry)
            WHERE c.code = :boundary_code
            AND   r.type = :road_type   -- if provided
        """
        raise NotImplementedError

    def get_rivers(
        self,
        boundary_code: str,
        boundary_level: str = "country",
    ) -> list[dict]:
        """
        Return rivers intersecting a boundary.

        Args:
            boundary_code:   ISO code of the boundary
            boundary_level:  'country' or 'province'

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT r.name, r.name_en, r.type,
                   ST_AsGeoJSON(r.geometry)::json AS geometry
            FROM geo.rivers r
            JOIN geo.countries c ON ST_Intersects(r.geometry, c.geometry)
            WHERE c.code = :boundary_code
        """
        raise NotImplementedError

    def get_railroads(
        self,
        boundary_code: str,
        boundary_level: str = "country",
    ) -> list[dict]:
        """
        Return railroads intersecting a boundary.

        Args:
            boundary_code:   ISO code of the boundary
            boundary_level:  'country' or 'province'

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT r.code, r.type, r.category, r.electric, r.multi_track,
                   ST_AsGeoJSON(r.geometry)::json AS geometry
            FROM geo.railroads r
            JOIN geo.countries c ON ST_Intersects(r.geometry, c.geometry)
            WHERE c.code = :boundary_code
        """
        raise NotImplementedError

    def get_places(
        self,
        boundary_code: str,
        boundary_level: str = "country",
        min_population: Optional[int] = None,
    ) -> list[dict]:
        """
        Return populated places within a boundary.

        Args:
            boundary_code:    ISO code of the boundary
            boundary_level:   'country' or 'province'
            min_population:   Optional minimum population filter

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT p.name, p.type, p.population, p.is_capital, p.timezone,
                   ST_AsGeoJSON(p.geometry)::json AS geometry
            FROM geo.places p
            JOIN geo.countries c ON ST_Intersects(p.geometry, c.geometry)
            WHERE c.code = :boundary_code
            AND   p.population >= :min_population   -- if provided
        """
        raise NotImplementedError

    def get_buildings(
        self,
        boundary_code: str,
        boundary_level: str = "country",
        building_type: Optional[str] = None,
    ) -> list[dict]:
        """
        Return building footprints within a boundary (Bulgaria OSM).

        Args:
            boundary_code:   ISO code (e.g. 'BGR' or 'BG-02')
            boundary_level:  'country' or 'province'
            building_type:   Optional filter by building type

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT b.name, b.type,
                   ST_AsGeoJSON(b.geometry)::json AS geometry
            FROM geo.buildings b
            JOIN geo.provinces p ON ST_Intersects(b.geometry, p.geometry)
            WHERE p.code = :boundary_code
            AND   b.type = :building_type   -- if provided
        """
        raise NotImplementedError

    def get_pois(
        self,
        boundary_code: str,
        boundary_level: str = "country",
        poi_type: Optional[str] = None,
    ) -> list[dict]:
        """
        Return points of interest within a boundary (Bulgaria OSM).

        Args:
            boundary_code:   ISO code (e.g. 'BGR' or 'BG-02')
            boundary_level:  'country' or 'province'
            poi_type:        Optional filter by POI type (e.g. 'hospital', 'school')

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT p.name, p.type,
                   ST_AsGeoJSON(p.geometry)::json AS geometry
            FROM geo.pois p
            JOIN geo.provinces pr ON ST_Intersects(p.geometry, pr.geometry)
            WHERE pr.code = :boundary_code
            AND   p.type = :poi_type   -- if provided
        """
        raise NotImplementedError

    def get_protected_areas(
        self,
        boundary_code: str,
        boundary_level: str = "country",
    ) -> list[dict]:
        """
        Return protected areas intersecting a boundary.

        Args:
            boundary_code:   ISO code of the boundary
            boundary_level:  'country' or 'province'

        Returns:
            List of GeoJSON feature dicts.

        SQL pattern:
            SELECT pa.name, pa.type, pa.region,
                   ST_AsGeoJSON(pa.geometry)::json AS geometry
            FROM geo.protected_areas pa
            JOIN geo.countries c ON ST_Intersects(pa.geometry, c.geometry)
            WHERE c.code = :boundary_code
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Statistics repository
# ---------------------------------------------------------------------------

class StatisticsRepository(GeoRepository):
    """
    Handles spatial aggregation queries.
    All methods return summary statistics rather than raw geometries.
    These power the /statistics endpoints and the AI agent tools.
    """

    def count_pois_by_type(
        self,
        boundary_code: str,
        boundary_level: str = "province",
        poi_type: Optional[str] = None,
    ) -> list[dict]:
        """
        Count POIs within a boundary, grouped by type.

        Args:
            boundary_code:   ISO code of the boundary (e.g. 'BG-02' for Burgas)
            boundary_level:  'country' or 'province'
            poi_type:        If provided, return count for this type only

        Returns:
            List of dicts: [{"type": "hospital", "count": 29}, ...]

        SQL pattern (verified working — 29 hospitals in Burgas):
            SELECT p.type, COUNT(*) AS count
            FROM geo.pois p
            JOIN geo.provinces pr ON ST_Intersects(p.geometry, pr.geometry)
            WHERE pr.code = :boundary_code
            AND   p.type = :poi_type   -- if provided
            GROUP BY p.type
            ORDER BY count DESC
        """
        raise NotImplementedError

    def count_buildings_by_type(
        self,
        boundary_code: str,
        boundary_level: str = "province",
    ) -> list[dict]:
        """
        Count buildings within a boundary, grouped by type.

        Args:
            boundary_code:   ISO code of the boundary
            boundary_level:  'country' or 'province'

        Returns:
            List of dicts: [{"type": "residential", "count": 1502}, ...]

        SQL pattern:
            SELECT b.type, COUNT(*) AS count
            FROM geo.buildings b
            JOIN geo.provinces p ON ST_Intersects(b.geometry, p.geometry)
            WHERE p.code = :boundary_code
            GROUP BY b.type
            ORDER BY count DESC
        """
        raise NotImplementedError

    def road_length_by_type(
        self,
        boundary_code: str,
        boundary_level: str = "country",
    ) -> list[dict]:
        """
        Total road length in km within a boundary, grouped by road type.

        Args:
            boundary_code:   ISO code of the boundary
            boundary_level:  'country' or 'province'

        Returns:
            List of dicts: [{"type": "Major Highway", "total_km": 1240.5}, ...]

        SQL pattern:
            -- ST_Intersection clips each road to the portion inside the boundary
            -- before measuring length. This is more accurate than summing the
            -- pre-calculated length_km column, which counts the full geometry
            -- of cross-boundary roads (e.g. a highway running through multiple countries).
            SELECT r.type,
                   ROUND(
                       SUM(
                           ST_Length(
                               ST_Intersection(r.geometry, c.geometry)::geography
                           ) / 1000
                       )::numeric, 2
                   ) AS total_km
            FROM geo.roads r
            JOIN geo.countries c ON ST_Intersects(r.geometry, c.geometry)
            WHERE c.code = :boundary_code
            GROUP BY r.type
            ORDER BY total_km DESC
        """
        raise NotImplementedError

    def population_summary(
        self,
        boundary_code: str,
        boundary_level: str = "country",
    ) -> dict:
        """
        Population statistics for places within a boundary.

        Args:
            boundary_code:   ISO code of the boundary
            boundary_level:  'country' or 'province'

        Returns:
            Dict with total_population, place_count, largest_city.

        SQL pattern:
            SELECT COUNT(*) AS place_count,
                   SUM(population) AS total_population,
                   MAX(name) FILTER (WHERE population = MAX(population)) AS largest_city
            FROM geo.places p
            JOIN geo.countries c ON ST_Intersects(p.geometry, c.geometry)
            WHERE c.code = :boundary_code
        """
        raise NotImplementedError

    def boundary_area_km2(self, code: str, level: str = "country") -> float:
        """
        Calculate the area of a boundary in square kilometres.

        Args:
            code:   ISO code of the boundary
            level:  'country' or 'province'

        Returns:
            Area in km² as a float.

        SQL pattern:
            SELECT ST_Area(geometry::geography) / 1000000 AS area_km2
            FROM geo.countries
            WHERE code = :code
        """
        raise NotImplementedError
