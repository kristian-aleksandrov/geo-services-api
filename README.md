# Geo Services API

A geospatial REST API serving vector layers with boundary-based spatial analysis and a natural language AI agent interface. Built with FastAPI, PostGIS, and Azure OpenAI as part of a technical assessment for the World Bank Group Senior Technical Lead — Geospatial Solutions role.

---

## Architecture

The API is structured in four layers:

- **Client** — Leaflet.js frontend consuming API endpoints and agent protocol commands
- **Azure Container Apps** — FastAPI application running in a Docker container, auto-scales to zero
- **Repository layer** — abstracts all PostGIS spatial queries behind a clean interface
- **Azure Database for PostgreSQL + PostGIS** — spatial database with GIST indexes on all geometry columns

The AI agent endpoint (`/agent/chat`) sends natural language queries to Azure OpenAI GPT-4o, which autonomously decides which API tools to call, retrieves spatial data, and returns structured commands to the Leaflet frontend via the Agent-to-Frontend protocol.

See `diagrams/architecture.png` for the full architecture diagram.

---

## Tech Stack

| Component | Technology |
|---|---|
| API framework | FastAPI |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Cloud platform | Azure Container Apps + Azure Database for PostgreSQL |
| AI agent | Azure OpenAI GPT-4o (function calling) |
| Data loading | GeoPandas, GeoAlchemy2, SQLAlchemy |
| Runtime | Python 3.11+ |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for local PostGIS)
- PostgreSQL client (pgAdmin or psql)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/geo-services-api.git
cd geo-services-api
```

### 2. Set up environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```
DB_HOST=localhost
DB_PORT=5433
DB_NAME=geo_services
DB_USER=postgres
DB_PASSWORD=your_password_here
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_ENDPOINT=your_endpoint_here
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

### 4. Start PostGIS (local Docker)

```bash
docker run --name postgis-geo \
  -e POSTGRES_PASSWORD=your_password_here \
  -e POSTGRES_DB=geo_services \
  -p 5433:5432 \
  -d postgis/postgis:16-3.4
```

### 5. Load data

Downloads Natural Earth 10m GeoPackage (~500MB) and Geofabrik Bulgaria OSM data (~50MB), loads all layers into PostGIS and creates spatial indexes:

```bash
python scripts/load_natural_earth.py
```

### 6. Run the API

```bash
uvicorn app.main:app --reload
```

API is available at `http://localhost:8000`
Interactive docs at `http://localhost:8000/docs`

---

## API Endpoints

### Boundaries

| Method | Endpoint | Description |
|---|---|---|
| GET | `/boundaries?level=country` | All country boundaries |
| GET | `/boundaries?level=province` | All province/state boundaries |
| GET | `/boundaries/{code}` | Single boundary by ISO code |

### Layers

| Method | Endpoint | Description |
|---|---|---|
| GET | `/layers/roads?boundary=KEN` | Roads within a boundary |
| GET | `/layers/rivers?boundary=KEN` | Rivers within a boundary |
| GET | `/layers/railroads?boundary=KEN` | Railroads within a boundary |
| GET | `/layers/places?boundary=KEN` | Populated places within a boundary |
| GET | `/layers/buildings?boundary=BGR` | Buildings within a boundary (Bulgaria OSM) |
| GET | `/layers/pois?boundary=BGR` | Points of interest within a boundary (Bulgaria OSM) |
| GET | `/layers/protected_areas?boundary=KEN` | Protected areas within a boundary |

### Statistics

| Method | Endpoint | Description |
|---|---|---|
| GET | `/statistics/roads?boundary=KEN` | Total road length by type |
| GET | `/statistics/places?boundary=KEN` | Population statistics |
| GET | `/statistics/pois?boundary=BGR&type=hospital` | POI counts by type |
| GET | `/statistics/buildings?boundary=BGR` | Building counts by type |

### AI Agent

| Method | Endpoint | Description |
|---|---|---|
| POST | `/agent/chat` | Natural language query interface |

Example request:
```json
{
  "message": "How many hospitals are in Burgas province?"
}
```

The agent autonomously decides which tools to call, retrieves the data, and returns both a natural language answer and structured Leaflet map commands.

See `docs/agent_protocol.md` for the full Agent-to-Frontend protocol specification.

---

## Database Schema

All tables live in the `geo` schema in PostgreSQL.

### Tables

| Table | Source | Records | Description |
|---|---|---|---|
| `geo.countries` | Natural Earth 10m | 258 | Country boundaries (Admin 0) |
| `geo.provinces` | Natural Earth 10m | 4,596 | Province/state boundaries (Admin 1) |
| `geo.roads` | Natural Earth 10m | 56,600 | Global road network |
| `geo.rivers` | Natural Earth 10m | 1,473 | Rivers and lake centerlines |
| `geo.railroads` | Natural Earth 10m | 25,413 | Global railroad network |
| `geo.places` | Natural Earth 10m | 7,342 | Populated places |
| `geo.protected_areas` | Natural Earth 10m | 61 | Parks and protected lands |
| `geo.buildings` | OSM via Geofabrik | — | Building footprints (Bulgaria) |
| `geo.pois` | OSM via Geofabrik | — | Points of interest (Bulgaria) |

### Spatial queries

All layer queries use PostGIS spatial joins rather than pre-assigned boundary codes. This correctly handles cross-boundary features (e.g. a river crossing multiple countries) and keeps the schema clean:

```sql
SELECT r.* FROM geo.roads r
JOIN geo.countries c ON ST_Intersects(r.geometry, c.geometry)
WHERE c.code = 'KEN'
```

### Indexes

Every geometry column has a GIST spatial index. Commonly filtered columns have B-tree attribute indexes. This combination makes spatial queries fast even on large datasets.

---

## Data Sources

| Dataset | Source | License |
|---|---|---|
| Natural Earth 10m vectors | [naturalearthdata.com](https://www.naturalearthdata.com) | Public domain |
| OSM Bulgaria buildings | [Geofabrik](https://download.geofabrik.de/europe/bulgaria.html) | ODbL |
| OSM Bulgaria POIs | [Geofabrik](https://download.geofabrik.de/europe/bulgaria.html) | ODbL |

---

## Data Layer Column Mapping

All layers are loaded from the Natural Earth 10m GeoPackage and Geofabrik OSM extracts. Only relevant columns are retained and renamed for clean, consistent API responses.

### geo.countries
Source: `ne_10m_admin_0_countries`

| Original | Renamed | Description |
|---|---|---|
| `NAME` | `name` | Common country name |
| `FORMAL_EN` | `formal_name` | Full formal name |
| `ADM0_ISO` | `code` | ISO 3166-1 alpha-3 code (KEN, GBR) |
| `POP_EST` | `pop_est` | Estimated population |
| `POP_YEAR` | `pop_year` | Year of population estimate |
| `ECONOMY` | `economy` | World Bank economy classification |
| `INCOME_GRP` | `income_group` | World Bank income group |
| `CONTINENT` | `continent` | Continent name |
| `REGION_WB` | `region_wb` | World Bank regional classification |
| `TYPE` | `type` | Country type |
| `SOVEREIGNT` | `sovereignt` | Sovereign state name |

### geo.provinces
Source: `ne_10m_admin_1_states_provinces`

| Original | Renamed | Description |
|---|---|---|
| `name` | `name` | Province/state name |
| `iso_3166_2` | `code` | ISO 3166-2 code (BG-02) |
| `adm0_a3` | `country_code` | Parent country ISO code |
| `type` | `type` | Administrative unit type |
| `type_en` | `type_en` | English type name |
| `region` | `region` | Region name |
| `area_sqkm` | `area_sqkm` | Area in square kilometres |
| `latitude` | `lat` | Centroid latitude |
| `longitude` | `lon` | Centroid longitude |

### geo.roads
Source: `ne_10m_roads`

| Original | Renamed | Description |
|---|---|---|
| `type` | `type` | Road classification |
| `featurecla` | `feature_class` | Natural Earth feature class |
| `length_km` | `length_km` | Pre-calculated length in km |
| `expressway` | `expressway` | Whether the road is an expressway |
| `toll` | `toll` | Whether the road is a toll road |
| `level` | `level` | Road hierarchy (Federal, State, Regional) |
| `localtype` | `local_type` | Local road type |
| `sov_a3` | `country_code` | Sovereign country ISO code |
| `continent` | `continent` | Continent name |

### geo.rivers
Source: `ne_10m_rivers_lake_centerlines`

| Original | Renamed | Description |
|---|---|---|
| `name` | `name` | River name |
| `name_en` | `name_en` | English name |
| `featurecla` | `type` | Feature class |

### geo.railroads
Source: `ne_10m_railroads`

| Original | Renamed | Description |
|---|---|---|
| `rwdb_rr_id` | `code` | Railroad identifier |
| `category` | `category` | Railroad category |
| `featurecla` | `type` | Feature class |
| `electric` | `electric` | Electrified railroad |
| `mult_track` | `multi_track` | Multiple tracks |
| `continent` | `continent` | Continent name |

### geo.places
Source: `ne_10m_populated_places`

| Original | Renamed | Description |
|---|---|---|
| `NAME` | `name` | Place name |
| `NAMEASCII` | `name_ascii` | ASCII name for search |
| `ADM0_A3` | `country_code` | Country ISO code |
| `ADM0NAME` | `country_name` | Country name |
| `ADM1NAME` | `admin1_name` | Province/state name |
| `ADM0CAP` | `is_capital` | National capital flag |
| `FEATURECLA` | `type` | Place type |
| `POP_MAX` | `population` | Maximum population estimate |
| `LATITUDE` | `lat` | Latitude |
| `LONGITUDE` | `lon` | Longitude |
| `TIMEZONE` | `timezone` | Timezone |
| `MEGACITY` | `is_megacity` | Megacity flag |
| `WORLDCITY` | `is_world_city` | World city flag |

### geo.buildings
Source: Geofabrik OSM Bulgaria (`gis_osm_buildings_a_free_1.shp`)

| Original | Renamed | Description |
|---|---|---|
| `name` | `name` | Building name |
| `type` | `type` | Building type (residential, commercial, etc.) |
| — | `country_code` | Added by loader: BGR |

### geo.pois
Source: Geofabrik OSM Bulgaria (`gis_osm_pois_a_free_1.shp`)

| Original | Renamed | Description |
|---|---|---|
| `name` | `name` | POI name |
| `fclass` | `type` | POI type (hospital, school, pharmacy, etc.) |
| — | `country_code` | Added by loader: BGR |

### geo.protected_areas
Source: `ne_10m_parks_and_protected_lands_area`

| Original | Renamed | Description |
|---|---|---|
| `name` | `name` | Area name |
| `featurecla` | `feature_class` | Feature class |
| `unit_type` | `type` | Protection type |
| `nps_region` | `region` | NPS administrative region |

---

## Planned Extensions

- **Global Forest Watch integration** — forest coverage percentage and total forest area per boundary using the GFW API, relevant for EUDR compliance monitoring and carbon market verification (dMRV)
- **Broader OSM coverage** — extend buildings and POIs beyond Bulgaria to other countries using Geofabrik extracts
- **Digital Twins pilot** — 3D building visualization for selected urban areas
- **WDPA global protected areas** — replace NPS-only protected areas dataset with the World Database on Protected Areas for global coverage

---

## Repository Structure

```
geo-services-api/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── routers/
│   │   ├── boundaries.py
│   │   ├── layers.py
│   │   ├── statistics.py
│   │   └── agent.py
│   ├── repositories/
│   │   └── geo_repository.py    # Database interface layer
│   ├── models/
│   │   └── schemas.py           # Pydantic response models
│   ├── agent/
│   │   ├── tools.py             # Tool definitions for GPT-4o
│   │   └── agent.py             # Agent logic
│   └── db/
│       └── database.py          # DB connection
├── scripts/
│   └── load_natural_earth.py    # Data loader
├── diagrams/
│   └── architecture.png
├── docs/
│   └── agent_protocol.md        # Agent-to-Frontend protocol spec
├── .env.example
├── Dockerfile
├── requirements.txt
└── README.md
```
