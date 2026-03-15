# Geo Services API

A geospatial REST API providing boundary-based spatial analysis and a natural language AI agent interface. Built with FastAPI, PostGIS, and Azure OpenAI as a technical assessment for the World Bank Group Senior Technical Lead — Geospatial Solutions role.

> **Data availability note:** Rich spatial data (buildings, points of interest, detailed road network) is focused on **Bulgaria**. Global layers (country boundaries, major roads, rivers, railroads, populated places) are available worldwide via Natural Earth 10m. Administrative boundaries at province and municipality level use World Bank Official Boundaries globally.

---

## Live Demo

| | |
|---|---|
| 🗺️ **Map + Chat** | https://geo-services-api.onrender.com/map |
| 📖 **API Docs** | https://geo-services-api.onrender.com/docs |

> The demo runs on Render's free tier and may take 30–60 seconds to wake up after inactivity. The PostgreSQL + PostGIS database and Azure OpenAI GPT-4o model are hosted on Azure (Sweden Central).

---

## Architecture

```
Leaflet Frontend  (served at /map)
        ↓ HTTP
Render Web Service — FastAPI Docker container
    ├── /boundaries  → countries, provinces, municipalities
    ├── /layers      → roads, rivers, railroads, places, buildings, pois
    ├── /statistics  → spatial aggregations via PostGIS
    └── /agent/chat  → Azure OpenAI GPT-4o (tool calling)
        ↓ SQLAlchemy + psycopg2
Repository Layer (geo_repository.py)
        ↓ SSL
Azure Database for PostgreSQL 16 + PostGIS 3.4 (Sweden Central)
```

The AI agent endpoint accepts natural language queries, autonomously calls the appropriate API tools, and returns both a human-readable answer and structured map commands to the Leaflet frontend via the Agent-to-Frontend protocol.

**Intended production deployment:** Azure Container Apps (Dockerfile included). The demo uses Render due to time constraints during the assessment period, while the database and AI model remain on Azure.

See `docs/agent_protocol.md` for the full protocol specification.
See `docs/database_justification.md` for the PostGIS selection rationale.
See `diagrams/architecture_final.drawio` for the full architecture diagram.

---

## Tech Stack

| Component | Technology |
|---|---|
| API framework | FastAPI |
| Database | PostgreSQL 16 + PostGIS 3.4 (Azure) |
| AI agent | Azure OpenAI GPT-4o (function/tool calling) |
| App hosting | Render (Docker) — Azure Container Apps intended |
| Data loading | GeoPandas, GeoAlchemy2, SQLAlchemy |
| Frontend | Leaflet.js (dark theme, chat panel, stats) |
| Container | Docker |
| Runtime | Python 3.11 |
| CI/CD | GitHub → Render auto-deploy on push |

---

## Data Coverage

| Layer | Coverage | Source | License |
|---|---|---|---|
| Country boundaries | **Global** | Natural Earth 10m | Public domain |
| Province boundaries (Admin 1) | **Global** | World Bank Official Boundaries | World Bank |
| Municipality boundaries (Admin 2) | **Global** | World Bank Official Boundaries | World Bank |
| Roads, rivers, railroads | **Global** (major only) | Natural Earth 10m | Public domain |
| Populated places | **Global** (major cities) | Natural Earth 10m | Public domain |
| Building footprints | **Bulgaria only** | OpenStreetMap via Geofabrik | ODbL |
| Points of interest | **Bulgaria only** | OpenStreetMap via Geofabrik | ODbL |

**Why Bulgaria focus?** OSM data via Geofabrik provides the richest feature set for spatial analysis — hospitals, schools, buildings, detailed POIs. The Geofabrik Bulgaria extract was selected as the primary demo dataset. Extending to other countries requires only adding additional Geofabrik country extracts to `scripts/load_data.py`.

World Bank Official Boundaries were chosen for Admin 1 and Admin 2 to ensure the API uses the same authoritative boundary definitions as World Bank operational systems.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for local PostGIS)
- PostgreSQL client (pgAdmin or psql)

### 1. Clone the repository

```bash
git clone https://github.com/kristian-aleksandrov/geo-services-api.git
cd geo-services-api
```

### 2. Set up Python environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
DB_HOST=localhost
DB_PORT=5433
DB_NAME=geo_services
DB_USER=postgres
DB_PASSWORD=your_password

AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o

FRONTEND_LIBRARY=leaflet
FRONTEND_VERSION=1.9
FRONTEND_CAPABILITIES=zoom_to,add_layer,remove_layer,highlight_boundary,show_stat,show_chart,clear_map
```

### 4. Start PostGIS

```bash
docker run --name postgis-geo \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=geo_services \
  -p 5433:5432 \
  -d postgis/postgis:16-3.4
```

### 5. Load data

```bash
python scripts/load_data.py
```

Downloads and loads automatically:
- World Bank Official Boundaries Admin 1 and Admin 2 (global)
- Natural Earth 10m GeoPackage (global)
- Geofabrik OpenStreetMap Bulgaria (buildings + POIs)

### 6. Run the API

```bash
uvicorn app.main:app --reload
```

- API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- Map frontend: open `frontend/index.html` in your browser

---

## Database Schema

All tables live in the `geo` schema.

| Table | Source | Records | Description |
|---|---|---|---|
| `geo.countries` | Natural Earth | 258 | Country boundaries + population, economy, WB region |
| `geo.provinces` | World Bank Admin 1 | 3,591 | Province/oblast boundaries |
| `geo.municipalities` | World Bank Admin 2 | 39,370 | Municipality boundaries |
| `geo.roads` | Natural Earth 10m | 56,600+ | Global road network |
| `geo.rivers` | Natural Earth 10m | 1,473 | Rivers and lake centerlines |
| `geo.railroads` | Natural Earth 10m | 25,413 | Global railroad network |
| `geo.places` | Natural Earth 10m | 7,342 | Populated places |
| `geo.buildings` | OSM Bulgaria | 801,199 | Building footprints (Bulgaria) |
| `geo.pois` | OSM Bulgaria | 33,126 | Points of interest (Bulgaria) |

### Boundary code formats

| Level | Format | Example |
|---|---|---|
| Country | ISO 3166-1 alpha-3 | `BGR` |
| Province | World Bank Admin 1 | `BGR002` (Burgas oblast) |
| Municipality | World Bank Admin 2 | `BGR002002` (Burgas municipality) |

### Spatial query design

All layer queries use `ST_Intersects` for filtering combined with `ST_Intersection` to clip geometries to the exact boundary extent before returning them. This correctly handles cross-boundary features and ensures road length statistics measure only the portion inside the requested boundary — not the full length of roads that cross the boundary.

All geometry stored in EPSG:4326. Area calculations cast to `geography` type for accurate metric results: `ST_Area(geometry::geography) / 1000000`.

---

## API Endpoints

### Boundaries

```
GET /boundaries/countries                         All countries
GET /boundaries/countries/{code}                  Single country by ISO code (e.g. BGR)
GET /boundaries/provinces?country_code=BGR        All Bulgarian provinces
GET /boundaries/provinces?name=Burgas             Search by name
GET /boundaries/provinces/{code}                  Single province (e.g. BGR002)
GET /boundaries/municipalities?country_code=BGR   All Bulgarian municipalities
GET /boundaries/municipalities?name=Burgas        Search by name
GET /boundaries/municipalities/{code}             Single municipality (e.g. BGR002002)
```

### Layers

```
GET /layers/roads?boundary=BGR&boundary_level=country
GET /layers/rivers?boundary=BGR002&boundary_level=province
GET /layers/railroads?boundary=BGR
GET /layers/places?boundary=BGR&min_population=50000
GET /layers/buildings?boundary=BGR002002&boundary_level=municipality  ← Bulgaria only
GET /layers/pois?boundary=BGR002&boundary_level=province&poi_type=hospital  ← Bulgaria only
```

All layer endpoints return GeoJSON FeatureCollections compatible with Leaflet's `L.geoJSON()`.

### Statistics

```
GET /statistics/pois?boundary=BGR002&boundary_level=province&poi_type=hospital  ← Bulgaria only
GET /statistics/buildings?boundary=BGR002002&boundary_level=municipality  ← Bulgaria only
GET /statistics/roads?boundary=BGR&boundary_level=country
GET /statistics/places?boundary=BGR&boundary_level=country
GET /statistics/area?boundary=BGR002&boundary_level=province
```

### AI Agent

```
POST /agent/chat
Content-Type: application/json

{"message": "How many hospitals are in Burgas province?"}
{"message": "Show me the roads in Bulgaria"}
{"message": "What is the area of Sofia province?"}
{"message": "How many buildings are in Veliko Tarnovo municipality?"}
```

---

## AI Agent

The agent uses Azure OpenAI GPT-4o with function/tool calling. It autonomously decides which tools to call, retrieves spatial data from PostGIS, and returns both a human-readable answer and structured map commands.

### Available tools

| Tool | Description |
|---|---|
| `get_place` | Find a city/town by name in the places table, zoom map to coordinates |
| `get_boundary_by_name` | Look up a boundary code by place name at any admin level |
| `get_boundary` | Retrieve a boundary by WB/ISO code |
| `count_pois` | Count POIs by type within a boundary (Bulgaria only) |
| `count_buildings` | Count buildings within a boundary (Bulgaria only) |
| `road_statistics` | Road length by type using ST_Intersection clipping |
| `population_statistics` | Population summary for an area |
| `boundary_area` | Area in km² using ST_Area(::geography) |
| `get_layer` | Retrieve a vector layer for map display with feature count |

### Example queries that work

- "How many hospitals are in Burgas province?" → 29
- "How many hospitals are in Bulgaria?" → 392
- "How many buildings are in Veliko Tarnovo municipality?"
- "Show me the roads in Bulgaria"
- "What is the area of Sofia province?"
- "What is the largest city in Bulgaria?"
- "Show me the city of Sofia"
- "Show me schools in Burgas province"

---

## Agent-to-Frontend Protocol

The agent returns structured JSON commands alongside the natural language answer. The frontend executes these commands in order to update the map.

```json
{
  "version": "1.0",
  "answer": "There are 29 hospitals in Burgas province.",
  "commands": [
    {"action": "zoom_to",           "params": {"boundary_code": "BGR002", "boundary_level": "province"}},
    {"action": "highlight_boundary","params": {"boundary_code": "BGR002", "boundary_level": "province"}},
    {"action": "add_layer",         "params": {"layer": "pois", "boundary_code": "BGR002", "filter": {"poi_type": "hospital"}}},
    {"action": "show_stat",         "params": {"label": "Hospitals in Burgas", "value": 29, "unit": "facilities"}}
  ],
  "tools_used": ["get_boundary_by_name", "count_pois"]
}
```

The protocol is **frontend-agnostic**. It includes a Style Adapter Registry that translates neutral style properties (`color`, `size`, `opacity`) to library-specific equivalents (Leaflet, MapboxGL, Google Maps, ArcGIS JS) at response time, and a Capability Registry that ensures the agent only sends commands the frontend declares it supports.

Frontend library and capabilities are configured **once at deployment time** via environment variables — not per request.

See `docs/agent_protocol.md` for the complete specification including transport mechanism justification and multi-frontend extension path.

---

## Deployment

### Docker (local)

```bash
docker build -t geo-services-api .
docker run -p 8000:8000 --env-file .env geo-services-api
```

### Azure Container Apps (intended production)

```bash
az acr build --registry yourregistry --image geo-services-api .
az containerapp create \
  --name geo-services-api \
  --resource-group geo-services-rg \
  --image yourregistry.azurecr.io/geo-services-api \
  --env-vars DB_HOST=... AZURE_OPENAI_API_KEY=...
```

---

## Repository Structure

```
geo-services-api/
├── app/
│   ├── main.py                   FastAPI entry point, serves frontend at /map
│   ├── routers/
│   │   ├── boundaries.py         Countries, provinces, municipalities
│   │   ├── layers.py             Roads, rivers, buildings, POIs etc.
│   │   ├── statistics.py         Spatial aggregations
│   │   └── agent.py              /agent/chat endpoint
│   ├── repositories/
│   │   └── geo_repository.py     All PostGIS queries — repository pattern
│   ├── models/
│   │   └── schemas.py            Pydantic response models
│   ├── agent/
│   │   ├── tools.py              GPT-4o tool definitions + style adapter registry
│   │   └── agent.py              Tool-calling loop + command builder
│   └── db/
│       └── database.py           SQLAlchemy connection + get_db() dependency
├── scripts/
│   └── load_data.py              Downloads and loads all datasets into PostGIS
├── frontend/
│   └── index.html                Leaflet map + chat panel (served at /map)
├── diagrams/
│   └── architecture_final.drawio Full architecture diagram
├── docs/
│   ├── database_justification.md PostGIS selection rationale (11 reasons)
│   └── agent_protocol.md         Agent-to-Frontend protocol specification
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Planned Extensions

- **Broader OSM coverage** — extend buildings and POIs beyond Bulgaria by adding additional Geofabrik country extracts to `load_data.py`
- **Global Forest Watch integration** — forest coverage and deforestation alerts per boundary, relevant for EUDR compliance and carbon market verification
- **Vector tile serving** — `ST_AsMVT` endpoints for high-performance rendering of dense feature layers
- **World Database on Protected Areas (WDPA)** — global protected areas dataset
- **SSE streaming** — Server-Sent Events for long-running agent queries with progress updates (e.g. "analyse all 28 Bulgarian provinces by hospital density")
- **pgRouting network analysis** — connectivity queries such as "is there a railroad between Pleven and Veliko Tarnovo"
