# Database Choice Justification

## Selected Database: PostgreSQL 16 with PostGIS 3.4

---

## Summary

PostgreSQL with the PostGIS extension is the industry standard for production geospatial systems and the natural choice for this API. It is the only open-source database that combines full relational capabilities with a mature, standards-compliant spatial engine capable of handling the full range of vector operations this API requires.

---

## Why PostgreSQL + PostGIS

### 1. Native spatial types and operations

PostGIS extends PostgreSQL with geometry and geography column types and over 300 spatial functions. The core operations this API depends on — `ST_Intersects`, `ST_Within`, `ST_Area`, `ST_Length`, `ST_Centroid` — are first-class SQL functions executed directly in the database engine, not in application code. This means:

- Spatial filtering happens at the data layer, not after fetching all rows into Python
- Complex spatial aggregations (total road length within a boundary, building count by type within a province) are single SQL queries
- No additional spatial processing library is needed in the API layer

### 2. GIST spatial indexing

PostGIS uses Generalized Search Tree (GIST) indexes on geometry columns. A spatial join between roads (56,600 features) and a country boundary without an index would require comparing every road geometry against the boundary polygon — O(n) per query. With a GIST index, PostGIS uses a bounding box pre-filter to instantly eliminate irrelevant features before applying the exact `ST_Intersects` test, reducing query time from seconds to milliseconds.

Every geometry column in this database has a GIST index. This is non-negotiable for any production geospatial API.

### 3. OGC standards compliance

PostGIS implements the OGC Simple Features specification, the same standard used by GeoServer, QGIS, GDAL, and every serious GIS platform. This means:

- Geometries are stored and returned in standard WKT/WKB/GeoJSON formats
- The API can serve GeoJSON directly from PostGIS without conversion overhead
- Integration with existing GIS infrastructure (GeoServer WMS/WFS, QGIS) requires no data transformation

### 4. Mixed workload capability

This API needs both spatial and non-spatial queries in the same request. For example, "total road length by income group of the country" requires a spatial join (roads within country) combined with a relational filter (country.income_group = 'Low income'). PostGIS handles this in a single query because it sits on top of a full relational engine. A pure spatial database like SpatiaLite or a document store like MongoDB would require multiple round trips or application-layer joins.

### 5. Azure native support

Azure Database for PostgreSQL Flexible Server supports the PostGIS extension natively. Enabling it requires a single SQL command:

```sql
CREATE EXTENSION postgis;
```

No additional infrastructure, no separate spatial service, no licensing cost. The same codebase runs identically on local Docker and Azure with only a connection string change.

### 6. Native vector tile generation

PostGIS 3.x can generate Mapbox Vector Tiles (MVT) directly from the database using `ST_AsMVT` and `ST_AsMVTGeom`. This means the API can serve `/tiles/{z}/{x}/{y}` endpoints without a separate tile server or pre-generated tile cache. For layers with high feature density such as buildings or roads, vector tiles dramatically reduce payload size by simplifying geometries at lower zoom levels and clipping to tile boundaries — all computed in a single PostGIS query. This is critical for frontend performance when rendering tens of thousands of features in Leaflet.

### 7. Spatial clustering

PostGIS supports geometry clustering natively via `ST_ClusterKMeans` and `ST_ClusterDBSCAN`. This allows the API to return clustered point representations of dense datasets (places, POIs, buildings) at lower zoom levels without any application-layer processing. Clustering in the database is significantly more efficient than clustering in Python or JavaScript because it operates directly on indexed geometries without deserializing them first.

### 8. Backend storage for enterprise GIS servers

PostGIS is the standard backend storage for the most widely used enterprise GIS servers — GeoServer, ArcGIS Server, MapServer, and QGIS Server all support PostGIS as a primary data store. This means the same database powering this REST API can simultaneously serve:

- OGC-compliant WMS and WFS endpoints via GeoServer
- Feature services and REST endpoints via ArcGIS Server
- Dynamic map rendering via MapServer

This is a critical architectural advantage in institutional environments like the World Bank, where existing GIS infrastructure built on GeoServer or ArcGIS Enterprise can connect directly to the PostGIS instance without any data duplication or ETL. The database becomes a single source of truth for both the modern REST API and the legacy GIS stack.

### 9. Geometry validation and repair

PostGIS has built-in mechanisms to detect and fix invalid geometries before they cause query failures or incorrect results. `ST_IsValid` checks whether a geometry conforms to the OGC specification — detecting self-intersections, duplicate rings, and unclosed polygons. `ST_MakeValid` attempts to automatically repair invalid geometries while preserving as much of the original shape as possible. In production data pipelines, invalid geometries are common — OSM data, government cadastral exports, and digitized boundaries frequently contain topological errors. PostGIS handles these at the database level rather than requiring manual inspection or external repair tools.

### 10. Geometry simplification and optimization

PostGIS provides `ST_Simplify` and `ST_SimplifyPreserveTopology` for reducing the vertex count of overly complex geometries. This is critical for two reasons: first, highly detailed geometries (coastlines, administrative boundaries digitized at 1:1000 scale) can contain thousands of vertices that are invisible at typical map zoom levels and dramatically slow down spatial operations. Second, simplified geometries reduce API payload size and frontend rendering time without any visible quality loss. `ST_SimplifyPreserveTopology` ensures that simplification never produces invalid geometries or causes boundaries to collapse — shared edges between adjacent polygons remain coincident after simplification. For a geospatial API serving data across multiple zoom levels, geometry optimization is not optional — it is a prerequisite for fast and accurate analysis.

### 11. Ecosystem maturity

PostGIS has been in production since 2001 and is used by organizations including the UN, NASA, OpenStreetMap, and the World Bank itself. The Python ecosystem support is comprehensive — SQLAlchemy + GeoAlchemy2 provide a typed ORM layer, GeoPandas handles bulk data loading, and Shapely handles geometry manipulation. Every tool in this stack is battle-tested and actively maintained.

---

## Alternatives Considered

### MongoDB with GeoJSON

MongoDB is the most common NoSQL alternative considered for geospatial APIs. It supports 2dsphere indexes and basic spatial queries (`$geoIntersects`, `$geoWithin`). It was rejected because:

- Limited spatial function library — no equivalent to `ST_Length`, `ST_Area`, `ST_Buffer`, or spatial aggregations
- No mixed spatial/relational queries in a single operation — joining POIs to boundaries by location while also filtering by income group requires multiple round trips
- Not OGC compliant — geometries are stored as GeoJSON documents, not typed geometry columns, which breaks interoperability with GeoServer and ArcGIS
- No geometry validation or repair functions — invalid geometries from OSM or digitized sources must be handled entirely in application code
- No native vector tile generation

### Snowflake with H3 / geography type

Snowflake supports a native `GEOGRAPHY` type and spatial functions including `ST_INTERSECTS`, `ST_AREA`, and `ST_DISTANCE`. It is a strong platform for large-scale geospatial analytics and is used in production for exactly that purpose. It was not selected here because:

- Optimized for analytical workloads (OLAP), not transactional API serving — cold query startup time makes it unsuitable as a backend for a low-latency REST API
- No GIST spatial indexing — Snowflake uses partition pruning and micro-partition metadata rather than traditional spatial indexes, which is efficient at scale but adds latency for single-record lookups
- No PostGIS-compatible geometry types — integration with GeoServer, ArcGIS Server, and the Python GeoPandas/GeoAlchemy2 stack requires additional transformation layers
- Significantly higher cost for a moderate-size dataset like this one

Snowflake would be the right choice if this API were backed by a continental or global dataset requiring petabyte-scale analytics, or if the primary consumers were BI tools and dashboards rather than a map frontend.

---

## Schema Design Decisions

### Separate tables for countries and provinces

Administrative boundaries are stored in two separate tables (`geo.countries` and `geo.provinces`) rather than a single table with a `level` column. This decision was made to:

- Avoid schema mismatch when appending layers with different column sets
- Allow each table to have exactly the columns relevant to its level
- Enable cleaner, more explicit spatial joins in the repository layer

### Spatial joins over pre-assigned boundary codes

Layer tables (roads, rivers, places etc.) do not store a `boundary_code` foreign key. Instead, the API uses `ST_Intersects` joins at query time:

```sql
SELECT r.* FROM geo.roads r
JOIN geo.countries c ON ST_Intersects(r.geometry, c.geometry)
WHERE c.code = 'KEN'
```

This approach is more correct because:

- A road or river can cross multiple boundaries — pre-assigning a single boundary code loses this information
- Spatial joins are fast with GIST indexes — the performance cost is negligible
- The schema stays normalized — no denormalized boundary codes that can go stale

### EPSG:4326 as the universal CRS

All geometries are stored in WGS84 (EPSG:4326). This is the coordinate reference system used by Leaflet, GeoJSON, GPS, and every web mapping library. Storing in a projected CRS would require reprojection on every API response. The only tradeoff is that area and length calculations in EPSG:4326 use angular units — this is handled by casting to `geography` type for metric calculations:

```sql
SELECT ST_Area(geometry::geography) / 1000000 AS area_km2
FROM geo.countries WHERE code = 'KEN'
```

---

## Repository Pattern

The repository pattern is used to abstract all database access behind a clean interface. The API routers never write SQL directly — they call repository methods that encapsulate the spatial query logic. This provides:

- **Testability** — repository methods can be mocked in unit tests without a database connection
- **Maintainability** — SQL changes are isolated to one file
- **Flexibility** — the underlying database can be swapped without changing router code
- **Clarity** — business logic in routers, data access logic in repository

See `app/repositories/geo_repository.py` for the full implementation.
