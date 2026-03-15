# Geo Services API

A geospatial REST API for Bulgaria providing boundary-based spatial analysis and a natural language AI agent interface. Built with FastAPI, PostGIS, and Azure OpenAI as a technical assessment for the World Bank Group Senior Technical Lead — Geospatial Solutions role.

## Live Demo

| | |
|---|---|
| 🗺️ **Map + Chat** | https://geo-services-api.onrender.com/map |
| 📖 **API Docs** | https://geo-services-api.onrender.com/docs |

> Note: The app runs on Render free tier and may take 30-60 seconds to wake up after inactivity.

---

## Architecture

```
Leaflet Frontend (served by FastAPI at /map)
        ↓ HTTP
Render Web Service — FastAPI (Docker)
    ├── /boundaries  → countries, provinces, municipalities
    ├── /layers      → roads, rivers, places, buildings, pois
    ├── /statistics  → spatial aggregations via PostGIS
    └── /agent/chat  → Azure OpenAI GPT-4o (tool calling)
        ↓ SQLAlchemy
Repository Layer (geo_repository.py)
        ↓
Azure Database for PostgreSQL 16 + PostGIS 3.4
```

The AI agent endpoint accepts natural language queries, autonomously calls the appropriate API tools, and returns both a human-readable answer and structured map commands to the Leaflet frontend via the Agent-to-Frontend protocol.

See `docs/agent_protocol.md` for the full protocol specification.
See `docs/database_justification.md` for the PostGIS selection rationale.
See `diagrams/api_architecture.drawio` for the full architecture diagram.

---

## Tech Stack

| Component | Technology |
|---|---|
| API framework | FastAPI |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Cloud platform | Azure Container Apps + Azure Database for PostgreSQL |
| AI agent | Azure OpenAI GPT-4o (function/tool calling) |
| Data loading | GeoPandas, GeoAlchemy2, SQLAlchemy |
| Frontend | Leaflet.js |
| Container | Docker |
| Runtime | Python 3.11 |

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

Downloads all datasets and loads them into PostGIS:

```bash
python scripts/load_data.py
```

Downloads automatically:
- World Bank Official Boundaries Admin 1 and Admin 2
- Natural Earth 10m GeoPackage
- Geofabrik OpenStreetMap Bulgaria

### 6. Run the API

```bash
uvicorn app.main:app --reload
```

- API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

### 7. Open the frontend

Open `frontend/index.html` in your browser. Make sure the API is running first.

---

## Data Sources

| Dataset | Source | Coverage | License |
|---|---|---|---|
| Country boundaries | Natural Earth 10m | Global | Public domain |
| Province boundaries (Admin 1) | World Bank Official Boundaries | Global | World Bank |
| Municipality boundaries (Admin 2) | World Bank Official Boundaries | Global | World Bank |
| Roads, rivers, railroads, places | Natural Earth 10m | Global | Public domain |
| Buildings | OpenStreetMap via Geofabrik | Bulgaria | ODbL |
| Points of interest | OpenStreetMap via Geofabrik | Bulgaria | ODbL |

Using World Bank Official Boundaries for Admin 1 and Admin 2 ensures the API uses the same authoritative boundary definitions as World Bank operational systems.

---

## Database Schema

All tables live in the `geo` schema.

| Table | Source | Description |
|---|---|---|
| `geo.countries` | Natural Earth | Country boundaries with population and economy data |
| `geo.provinces` | World Bank Admin 1 | Province/oblast boundaries |
| `geo.municipalities` | World Bank Admin 2 | Municipality boundaries |
| `geo.roads` | Natural Earth 10m | Global road network |
| `geo.rivers` | Natural Earth 10m | Rivers and lake centerlines |
| `geo.railroads` | Natural Earth 10m | Global railroad network |
| `geo.places` | Natural Earth 10m | Populated places |
| `geo.buildings` | OSM Bulgaria | Building footprints |
| `geo.pois` | OSM Bulgaria | Points of interest (hospitals, schools, etc.) |

### Boundary code formats

| Level | Format | Example |
|---|---|---|
| Country | ISO 3166-1 alpha-3 | `BGR` |
| Province | World Bank Admin 1 | `BGR002` (Burgas oblast) |
| Municipality | World Bank Admin 2 | `BGR002002` (Burgas municipality) |

### Spatial queries

All layer queries use PostGIS `ST_Intersects` joins at query time. Features are not pre-assigned boundary codes, which correctly handles cross-boundary features.

Road length calculations use `ST_Intersection` to clip geometries to the exact boundary extent before measuring — avoiding the overcounting that occurs when summing pre-calculated lengths for cross-boundary roads.

---

## API Endpoints

### Boundaries

```
GET /boundaries/countries                         All countries
GET /boundaries/countries/{code}                  Single country by ISO code
GET /boundaries/provinces?country_code=BGR        All Bulgarian provinces
GET /boundaries/provinces?name=Burgas             Search by name
GET /boundaries/provinces/{code}                  Single province by WB code
GET /boundaries/municipalities?country_code=BGR   All Bulgarian municipalities
GET /boundaries/municipalities?name=Burgas        Search by name
GET /boundaries/municipalities/{code}             Single municipality by WB code
```

### Layers

```
GET /layers/roads?boundary=BGR&boundary_level=country
GET /layers/rivers?boundary=BGR002&boundary_level=province
GET /layers/railroads?boundary=BGR
GET /layers/places?boundary=BGR&min_population=50000
GET /layers/buildings?boundary=BGR002002&boundary_level=municipality
GET /layers/pois?boundary=BGR002&boundary_level=province&poi_type=hospital
```

All layer endpoints return GeoJSON FeatureCollections compatible with `L.geoJSON()`.

### Statistics

```
GET /statistics/pois?boundary=BGR002&boundary_level=province&poi_type=hospital
GET /statistics/buildings?boundary=BGR002002&boundary_level=municipality
GET /statistics/roads?boundary=BGR&boundary_level=country
GET /statistics/places?boundary=BGR&boundary_level=country
GET /statistics/area?boundary=BGR002&boundary_level=province
```

### AI Agent

```
POST /agent/chat
Content-Type: application/json

{"message": "How many hospitals are in Burgas province?"}
```

Returns a natural language answer plus structured Leaflet map commands. See `docs/agent_protocol.md` for the full protocol specification.

---

## AI Agent

The agent uses Azure OpenAI GPT-4o with function/tool calling. It autonomously decides which tools to call, retrieves spatial data from PostGIS, and returns both a human-readable answer and structured map commands.

### Available tools

| Tool | Description |
|---|---|
| `get_boundary_by_name` | Look up a boundary code by place name |
| `get_boundary` | Retrieve a boundary by code |
| `count_pois` | Count POIs by type within a boundary |
| `count_buildings` | Count buildings within a boundary |
| `road_statistics` | Road length by type using ST_Intersection |
| `population_statistics` | Population summary for an area |
| `boundary_area` | Area in km² using ST_Area(::geography) |
| `get_layer` | Retrieve a vector layer for map display |

### Example queries

- "How many hospitals are in Burgas province?"
- "How many buildings are in Veliko Tarnovo municipality?"
- "Show me the roads in Bulgaria"
- "What is the area of Sofia province?"
- "What is the largest city in Bulgaria?"

---

## Agent-to-Frontend Protocol

The agent returns structured JSON commands alongside the natural language answer. The frontend executes these commands in order to update the map.

```json
{
  "answer": "There are 29 hospitals in Burgas province.",
  "commands": [
    {"action": "zoom_to",          "params": {"boundary_code": "BGR002", "boundary_level": "province"}},
    {"action": "highlight_boundary","params": {"boundary_code": "BGR002", "boundary_level": "province"}},
    {"action": "add_layer",        "params": {"layer": "pois", "boundary_code": "BGR002", "filter": {"poi_type": "hospital"}}},
    {"action": "show_stat",        "params": {"label": "Hospitals in Burgas", "value": 29, "unit": "facilities"}}
  ],
  "tools_used": ["get_boundary_by_name", "count_pois"]
}
```

The protocol is frontend-agnostic. Style hints are translated to library-specific properties at response time via the Style Adapter Registry. See `docs/agent_protocol.md` for the complete specification.

---

## Deployment

### Docker

```bash
docker build -t geo-services-api .
docker run -p 8000:8000 --env-file .env geo-services-api
```

### Azure Container Apps

```bash
# Build and push to Azure Container Registry
az acr build --registry yourregistry --image geo-services-api .

# Deploy to Container Apps
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
│   ├── main.py
│   ├── routers/
│   │   ├── boundaries.py
│   │   ├── layers.py
│   │   ├── statistics.py
│   │   └── agent.py
│   ├── repositories/
│   │   └── geo_repository.py
│   ├── models/
│   │   └── schemas.py
│   ├── agent/
│   │   ├── tools.py
│   │   └── agent.py
│   └── db/
│       └── database.py
├── scripts/
│   └── load_data.py
├── frontend/
│   └── index.html
├── diagrams/
│   └── api_architecture.drawio
├── docs/
│   ├── database_justification.md
│   └── agent_protocol.md
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Planned Extensions

- **Global Forest Watch integration** — forest coverage and deforestation alerts per boundary, relevant for EUDR compliance monitoring
- **Broader OSM coverage** — extend buildings and POIs beyond Bulgaria using Geofabrik extracts for additional countries
- **Vector tile serving** — `ST_AsMVT` endpoints for high-performance rendering of large datasets
- **World Database on Protected Areas (WDPA)** — global protected areas replacing the current NPS-only dataset
- **SSE streaming** — Server-Sent Events for long-running agent queries with progress updates
