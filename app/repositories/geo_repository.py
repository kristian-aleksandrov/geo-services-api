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
        """
        filters = []
        params  = {}
        if continent:
            filters.append("continent = :continent")
            params["continent"] = continent
        if region_wb:
            filters.append("region_wb = :region_wb")
            params["region_wb"] = region_wb

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        sql = text(f"""
            SELECT name, formal_name, code, continent, region_wb,
                   pop_est, income_group, economy, sovereignt, type,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.countries
            {where}
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {
                    "name":         row["name"],
                    "formal_name":  row["formal_name"],
                    "code":         row["code"],
                    "continent":    row["continent"],
                    "region_wb":    row["region_wb"],
                    "pop_est":      row["pop_est"],
                    "income_group": row["income_group"],
                    "economy":      row["economy"],
                    "sovereignt":   row["sovereignt"],
                    "type":         row["type"],
                }
            }
            for row in rows
        ]

    def get_country_by_code(self, code: str) -> Optional[dict]:
        """
        Return a single country boundary by ISO 3166-1 alpha-3 code.

        Args:
            code:  ISO alpha-3 country code (e.g. 'KEN', 'BGR')

        Returns:
            GeoJSON feature dict or None if not found.
        """
        sql = text("""
            SELECT name, formal_name, code, continent, region_wb,
                   pop_est, income_group, economy, sovereignt, type,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.countries
            WHERE code = :code
        """)
        row = self.db.execute(sql, {"code": code}).mappings().fetchone()
        if not row:
            return None
        return {
            "type": "Feature",
            "geometry": row["geometry"],
            "properties": {
                "name":         row["name"],
                "formal_name":  row["formal_name"],
                "code":         row["code"],
                "continent":    row["continent"],
                "region_wb":    row["region_wb"],
                "pop_est":      row["pop_est"],
                "income_group": row["income_group"],
                "economy":      row["economy"],
                "sovereignt":   row["sovereignt"],
                "type":         row["type"],
            }
        }

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
        """
        filters = []
        params  = {}
        if country_code:
            filters.append("country_code = :country_code")
            params["country_code"] = country_code

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        sql = text(f"""
            SELECT name, code, country_code, type, type_en,
                   region, area_sqkm, lat, lon,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.provinces
            {where}
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {
                    "name":         row["name"],
                    "code":         row["code"],
                    "country_code": row["country_code"],
                    "type":         row["type"],
                    "type_en":      row["type_en"],
                    "region":       row["region"],
                    "area_sqkm":    row["area_sqkm"],
                    "lat":          row["lat"],
                    "lon":          row["lon"],
                }
            }
            for row in rows
        ]

    def get_province_by_code(self, code: str) -> Optional[dict]:
        """
        Return a single province by ISO 3166-2 code.

        Args:
            code:  ISO 3166-2 code (e.g. 'BG-02' for Burgas)

        Returns:
            GeoJSON feature dict or None if not found.
        """
        sql = text("""
            SELECT name, code, country_code, type, type_en,
                   region, area_sqkm, lat, lon,
                   ST_AsGeoJSON(geometry)::json AS geometry
            FROM geo.provinces
            WHERE code = :code
        """)
        row = self.db.execute(sql, {"code": code}).mappings().fetchone()
        if not row:
            return None
        return {
            "type": "Feature",
            "geometry": row["geometry"],
            "properties": {
                "name":         row["name"],
                "code":         row["code"],
                "country_code": row["country_code"],
                "type":         row["type"],
                "type_en":      row["type_en"],
                "region":       row["region"],
                "area_sqkm":    row["area_sqkm"],
                "lat":          row["lat"],
                "lon":          row["lon"],
            }
        }


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
        table  = "countries" if boundary_level == "country" else "provinces"
        col    = "code"
        params = {"boundary_code": boundary_code}

        filters = []
        if road_type:
            filters.append("r.type = :road_type")
            params["road_type"] = road_type
        extra = ("AND " + " AND ".join(filters)) if filters else ""

        sql = text(f"""
            SELECT r.name, r.type, r.feature_class, r.length_km,
                   r.expressway, r.toll, r.level, r.local_type, r.country_code,
                   ST_AsGeoJSON(r.geometry)::json AS geometry
            FROM geo.roads r
            JOIN geo.{table} b ON ST_Intersects(r.geometry, b.geometry)
            WHERE b.{col} = :boundary_code
            {extra}
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {
                    "name":          row["name"],
                    "type":          row["type"],
                    "feature_class": row["feature_class"],
                    "length_km":     row["length_km"],
                    "expressway":    row["expressway"],
                    "toll":          row["toll"],
                    "level":         row["level"],
                    "local_type":    row["local_type"],
                    "country_code":  row["country_code"],
                }
            }
            for row in rows
        ]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        sql = text(f"""
            SELECT r.name, r.name_en, r.type,
                   ST_AsGeoJSON(r.geometry)::json AS geometry
            FROM geo.rivers r
            JOIN geo.{table} b ON ST_Intersects(r.geometry, b.geometry)
            WHERE b.code = :boundary_code
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {"name": row["name"], "name_en": row["name_en"], "type": row["type"]}
            }
            for row in rows
        ]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        sql = text(f"""
            SELECT r.code, r.type, r.category, r.electric, r.multi_track,
                   ST_AsGeoJSON(r.geometry)::json AS geometry
            FROM geo.railroads r
            JOIN geo.{table} b ON ST_Intersects(r.geometry, b.geometry)
            WHERE b.code = :boundary_code
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {
                    "code":        row["code"],
                    "type":        row["type"],
                    "category":    row["category"],
                    "electric":    row["electric"],
                    "multi_track": row["multi_track"],
                }
            }
            for row in rows
        ]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        filters = []
        if min_population:
            filters.append("p.population >= :min_population")
            params["min_population"] = min_population
        extra = ("AND " + " AND ".join(filters)) if filters else ""

        sql = text(f"""
            SELECT p.name, p.name_ascii, p.country_code, p.country_name,
                   p.admin1_name, p.type, p.population, p.is_capital,
                   p.is_megacity, p.is_world_city, p.timezone, p.lat, p.lon,
                   ST_AsGeoJSON(p.geometry)::json AS geometry
            FROM geo.places p
            JOIN geo.{table} b ON ST_Intersects(p.geometry, b.geometry)
            WHERE b.code = :boundary_code
            {extra}
            ORDER BY p.population DESC NULLS LAST
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {
                    "name":          row["name"],
                    "name_ascii":    row["name_ascii"],
                    "country_code":  row["country_code"],
                    "country_name":  row["country_name"],
                    "admin1_name":   row["admin1_name"],
                    "type":          row["type"],
                    "population":    row["population"],
                    "is_capital":    row["is_capital"],
                    "is_megacity":   row["is_megacity"],
                    "is_world_city": row["is_world_city"],
                    "timezone":      row["timezone"],
                    "lat":           row["lat"],
                    "lon":           row["lon"],
                }
            }
            for row in rows
        ]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        filters = []
        if building_type:
            filters.append("b.type = :building_type")
            params["building_type"] = building_type
        extra = ("AND " + " AND ".join(filters)) if filters else ""

        sql = text(f"""
            SELECT b.name, b.type,
                   ST_AsGeoJSON(b.geometry)::json AS geometry
            FROM geo.buildings b
            JOIN geo.{table} bnd ON ST_Intersects(b.geometry, bnd.geometry)
            WHERE bnd.code = :boundary_code
            {extra}
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {"name": row["name"], "type": row["type"]}
            }
            for row in rows
        ]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        filters = []
        if poi_type:
            filters.append("p.type = :poi_type")
            params["poi_type"] = poi_type
        extra = ("AND " + " AND ".join(filters)) if filters else ""

        sql = text(f"""
            SELECT p.name, p.type,
                   ST_AsGeoJSON(p.geometry)::json AS geometry
            FROM geo.pois p
            JOIN geo.{table} b ON ST_Intersects(p.geometry, b.geometry)
            WHERE b.code = :boundary_code
            {extra}
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {"name": row["name"], "type": row["type"]}
            }
            for row in rows
        ]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        sql = text(f"""
            SELECT pa.name, pa.feature_class, pa.type, pa.region,
                   ST_AsGeoJSON(pa.geometry)::json AS geometry
            FROM geo.protected_areas pa
            JOIN geo.{table} b ON ST_Intersects(pa.geometry, b.geometry)
            WHERE b.code = :boundary_code
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {
                    "name":          row["name"],
                    "feature_class": row["feature_class"],
                    "type":          row["type"],
                    "region":        row["region"],
                }
            }
            for row in rows
        ]


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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        filters = []
        if poi_type:
            filters.append("p.type = :poi_type")
            params["poi_type"] = poi_type
        extra = ("AND " + " AND ".join(filters)) if filters else ""

        sql = text(f"""
            SELECT p.type, COUNT(*) AS count
            FROM geo.pois p
            JOIN geo.{table} b ON ST_Intersects(p.geometry, b.geometry)
            WHERE b.code = :boundary_code
            {extra}
            GROUP BY p.type
            ORDER BY count DESC
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [{"type": row["type"], "count": row["count"]} for row in rows]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        sql = text(f"""
            SELECT b.type, COUNT(*) AS count
            FROM geo.buildings b
            JOIN geo.{table} bnd ON ST_Intersects(b.geometry, bnd.geometry)
            WHERE bnd.code = :boundary_code
            GROUP BY b.type
            ORDER BY count DESC
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [{"type": row["type"], "count": row["count"]} for row in rows]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        sql = text(f"""
            SELECT r.type,
                   ROUND(
                       SUM(
                           ST_Length(
                               ST_Intersection(r.geometry, b.geometry)::geography
                           ) / 1000
                       )::numeric, 2
                   ) AS total_km
            FROM geo.roads r
            JOIN geo.{table} b ON ST_Intersects(r.geometry, b.geometry)
            WHERE b.code = :boundary_code
            GROUP BY r.type
            ORDER BY total_km DESC
        """)
        rows = self.db.execute(sql, params).mappings().fetchall()
        return [{"type": row["type"], "total_km": float(row["total_km"])} for row in rows]

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
        table  = "countries" if boundary_level == "country" else "provinces"
        params = {"boundary_code": boundary_code}
        sql = text(f"""
            SELECT COUNT(*)        AS place_count,
                   SUM(p.population) AS total_population,
                   (
                       SELECT p2.name FROM geo.places p2
                       JOIN geo.{table} b2 ON ST_Intersects(p2.geometry, b2.geometry)
                       WHERE b2.code = :boundary_code
                       ORDER BY p2.population DESC NULLS LAST
                       LIMIT 1
                   ) AS largest_city
            FROM geo.places p
            JOIN geo.{table} b ON ST_Intersects(p.geometry, b.geometry)
            WHERE b.code = :boundary_code
        """)
        row = self.db.execute(sql, params).mappings().fetchone()
        return {
            "place_count":       int(row["place_count"] or 0),
            "total_population":  int(row["total_population"] or 0),
            "largest_city":      row["largest_city"],
        }

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
        table = "countries" if level == "country" else "provinces"
        sql = text(f"""
            SELECT ROUND(
                (ST_Area(geometry::geography) / 1000000)::numeric, 2
            ) AS area_km2
            FROM geo.{table}
            WHERE code = :code
        """)
        row = self.db.execute(sql, {"code": code}).mappings().fetchone()
        if not row:
            return 0.0
        return float(row["area_km2"])
