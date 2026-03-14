# Agent-to-Frontend Protocol Specification

**Version:** 1.0  
**Endpoint:** `POST /agent/chat`  
**Author:** Geo Services API — World Bank Technical Assessment

---

## 1. Overview

The Agent-to-Frontend Protocol defines the message schema returned by the
`/agent/chat` endpoint. It is the contract between the AI agent backend and
any frontend application that consumes it.

The protocol is designed around three principles:

- **Frontend-agnostic** — commands describe *what* to do, never *how* to do
  it in a specific library. A Leaflet app, a MapboxGL app, an ArcGIS JS app,
  Google Maps, or a mobile application all receive the same command vocabulary
  and implement each command using their own mapping API.

- **Self-describing** — every command carries all the data needed to execute
  it. The frontend never needs a follow-up request just to understand a command.

- **Composable** — a single agent response can contain multiple commands that
  the frontend executes in sequence, producing a coordinated map experience
  from a single natural language query.

The protocol achieves true frontend portability through two mechanisms:

- **Style Adapter Registry (Level 1)** — the backend maps neutral style
  properties to library-specific equivalents based on the configured frontend
  library.

- **Capability Registry (Level 2)** — the deployment configuration declares
  which commands the frontend supports. The agent only sends commands the
  frontend can handle, and falls back to text for unsupported operations.

Both mechanisms are configured **once at deployment time** via environment
variables — not per request. The frontend library, version, and capabilities
are deployment constants that never change during the lifetime of the
application. Including them in every request would be redundant and
architecturally incorrect.

---

## 2. Transport Mechanism

### Choice: REST + JSON over HTTP

The protocol uses standard HTTP POST with a JSON request body and a JSON
response. This decision is justified on the following grounds:

**Simplicity and universality** — every HTTP client in every language and
framework can consume a REST/JSON endpoint without additional dependencies.
A Leaflet app running in a browser, a MapboxGL app, an ArcGIS mobile app,
a Python data pipeline, and a Power BI custom connector can all call the
same endpoint identically.

**Statelessness** — each request is fully self-contained. The frontend sends
the message and receives the complete response. There is no session state to
manage on the server between requests. This makes the API horizontally
scalable — any container instance can handle any request.

**Cacheability** — common agent responses (e.g. "show all hospitals in
Bulgaria") can be cached at the Azure API Management layer or CDN, reducing
latency and backend load for repeated queries.

**Tooling** — REST/JSON integrates natively with OpenAPI/Swagger documentation,
API gateways, load balancers, and monitoring tools without configuration.

### When to consider alternatives

**WebSockets** would be appropriate if the agent streams its response token by
token (like a typing effect). The current implementation returns the complete
response when the tool-calling loop finishes. If streaming is added in a future
version, the protocol commands section of the response would remain identical —
only the transport layer would change.

**Server-Sent Events (SSE)** would be appropriate for long-running agent tasks
that need to push progress updates to the frontend while the agent is still
executing tool calls. For example: "Analyse all 28 Bulgarian provinces and rank
them by hospital density" would benefit from SSE so the frontend can show
progress rather than waiting for a single response. This is identified as a
planned extension.

---

## 3. Frontend Configuration — Deployment Time

The frontend library, version, and capabilities are **not part of the request
schema**. They are deployment-time constants set once in the server environment
and never change during the lifetime of the application.

```bash
# Server environment variables — set once at deployment

FRONTEND_LIBRARY=leaflet
FRONTEND_VERSION=1.9
FRONTEND_CAPABILITIES=zoom_to,add_layer,remove_layer,highlight_boundary,show_stat,show_chart,clear_map
```

| Variable | Description |
|---|---|
| `FRONTEND_LIBRARY` | Mapping library identifier. Supported: `leaflet`, `mapboxgl`, `googlemaps`, `arcgis`, `openlayers` |
| `FRONTEND_VERSION` | Library version. Used for forward compatibility. |
| `FRONTEND_CAPABILITIES` | Comma-separated list of command types the frontend has implemented. The agent only sends commands in this list. |

The agent reads these variables at startup and applies the correct style
adapter and capability filter to every response automatically.

**Why not in the request?** Frontend library and capabilities are properties
of the deployed application, not of the user's query. A Leaflet app does not
suddenly become a MapboxGL app between requests. Sending this configuration
on every request would be redundant, wasteful, and architecturally incorrect.

### Multi-tenant extension (Option B)

For deployments where multiple different frontends call the same backend —
for example a Leaflet web app, a MapboxGL dashboard, and a mobile app all
sharing one API — each frontend registers once via a setup endpoint and
receives an API key:

```
POST /frontend/register
{"library": "mapboxgl", "capabilities": [...]}
→ {"api_key": "fe_mapbox_7k2p"}
```

Subsequent requests include only the key:
```json
{"message": "Show hospitals in Burgas", "api_key": "fe_mapbox_7k2p"}
```

The backend looks up the frontend configuration from the key. This pattern
is identified as a planned extension for multi-tenant deployments.

---

## 4. Request Schema

```json
POST /agent/chat
Content-Type: application/json

{
  "message": "How many hospitals are in Burgas province?",
  "conversation_id": "conv_abc123"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | ✅ | Natural language query from the user |
| `conversation_id` | string | ❌ | Token for multi-turn conversations. Omit for a new conversation. |

---

## 5. Style Adapter Registry (Level 1)

When `frontend.library` is provided, the agent translates neutral style
properties into library-specific equivalents before returning commands.
This allows the same backend to serve correctly styled commands to any
supported mapping library without the frontend doing any translation.

### Neutral style properties

The agent always reasons in neutral terms internally:

| Neutral property | Meaning |
|---|---|
| `color` | Primary colour (stroke or fill) |
| `size` | Point radius or line weight |
| `opacity` | Fill or stroke opacity (0–1) |
| `intent` | Semantic hint: `highlight`, `danger`, `neutral`, `success` |

### Library translation table

| Neutral | Leaflet | MapboxGL | Google Maps | ArcGIS JS |
|---|---|---|---|---|
| `color` | `color` | `circle-color` / `line-color` | `fillColor` / `strokeColor` | `color` |
| `size` | `radius` / `weight` | `circle-radius` / `line-width` | `scale` / `strokeWeight` | `size` |
| `opacity` | `fillOpacity` | `circle-opacity` / `line-opacity` | `fillOpacity` | `opacity` |

### Example — same query, three frontends

**Leaflet** (`"library": "leaflet"`):
```json
{
  "action": "add_layer",
  "params": {
    "layer": "pois",
    "boundary_code": "BG-02",
    "filter": {"poi_type": "hospital"},
    "style": {"color": "#e74c3c", "radius": 6, "fillOpacity": 0.8}
  }
}
```

**MapboxGL** (`"library": "mapboxgl"`):
```json
{
  "action": "add_layer",
  "params": {
    "layer": "pois",
    "boundary_code": "BG-02",
    "filter": {"poi_type": "hospital"},
    "style": {
      "paint": {"circle-color": "#e74c3c", "circle-radius": 6, "circle-opacity": 0.8}
    }
  }
}
```

**Google Maps** (`"library": "googlemaps"`):
```json
{
  "action": "add_layer",
  "params": {
    "layer": "pois",
    "boundary_code": "BG-02",
    "filter": {"poi_type": "hospital"},
    "style": {
      "icon": {"path": "CIRCLE", "fillColor": "#e74c3c", "scale": 6, "fillOpacity": 0.8}
    }
  }
}
```

The backend applies the correct adapter at response time. The frontend
receives style hints already formatted for its library.

---

## 6. Capability Registry (Level 2)

When `frontend.capabilities` is provided, the agent only sends commands the
frontend has declared it can handle. For any unsupported command type, the
agent incorporates the information into the `answer` text instead.

### Example — frontend without chart support

**Request:**
```json
{
  "message": "Show me road length by type in Bulgaria",
  "frontend": {
    "library": "leaflet",
    "capabilities": ["zoom_to", "add_layer", "highlight_boundary", "show_stat"]
  }
}
```

Because `show_chart` is not in `capabilities`, the agent includes the
breakdown in the answer text instead of sending a chart command:

**Response:**
```json
{
  "answer": "Bulgaria has approximately 5,463 km of roads. Major Highways account for 412 km, Secondary Highways for 1,840 km, and local roads for the remainder.",
  "commands": [
    {"action": "zoom_to",   "params": {"boundary_code": "BGR", "boundary_level": "country"}},
    {"action": "add_layer", "params": {"layer": "roads", "boundary_code": "BGR"}},
    {"action": "show_stat", "params": {"label": "Total road length", "value": 5463, "unit": "km"}}
  ]
}
```

### Capability fallback rules

| Unsupported command | Agent fallback |
|---|---|
| `show_chart` | Include breakdown data in `answer` text |
| `show_stat` | Include statistic in `answer` text |
| `highlight_boundary` | Skip — boundary visible from `zoom_to` |
| `add_layer` | Describe the layer in `answer` text |
| `zoom_to` | Skip — frontend stays at current view |

---

## 7. Response Schema

```json
{
  "version": "1.0",
  "conversation_id": "conv_abc123",
  "frontend_library": "leaflet",
  "answer": "There are 29 hospitals in Burgas province.",
  "commands": [ ... ],
  "tools_used": ["count_pois", "get_province"],
  "data": { ... }
}
```

| Field | Type | Description |
|---|---|---|
| `version` | string | Protocol version. Frontends should check this for compatibility. |
| `conversation_id` | string | Echo of the request conversation_id, or a new token if none was provided. |
| `frontend_library` | string | Echo of the requested library. Confirms which style adapter was applied. |
| `answer` | string | Natural language response. Always present. Suitable for display in a chat panel. |
| `commands` | array | Ordered list of map commands. Only contains command types in `frontend.capabilities`. |
| `tools_used` | array | Names of the API tools the agent called. Useful for debugging and transparency. |
| `data` | object | Raw data from tool calls. Frontends may use this to build custom UI components. |

---

## 8. Command Schema

Each item in the `commands` array follows this structure:

```json
{
  "action": "string",
  "params": { ... }
}
```

Commands are ordered. The frontend executes them in sequence.

---

## 9. Command Vocabulary

### `zoom_to`
Pan and zoom the map to fit a boundary or coordinate.

```json
{
  "action": "zoom_to",
  "params": {
    "boundary_code": "BG-02",
    "boundary_level": "province",
    "bbox": [27.09, 42.23, 27.93, 42.84]
  }
}
```

| Param | Type | Description |
|---|---|---|
| `boundary_code` | string | ISO code of the boundary to fit |
| `boundary_level` | string | country or province |
| `bbox` | array | [minLon, minLat, maxLon, maxLat] — universal alternative to zoom level, compatible with all libraries |
| `lat` / `lon` | float | Coordinate to centre on (alternative to boundary_code) |

---

### `add_layer`
Fetch a vector layer from the API and add it to the map.

```json
{
  "action": "add_layer",
  "params": {
    "layer": "pois",
    "boundary_code": "BG-02",
    "boundary_level": "province",
    "filter": {"poi_type": "hospital"},
    "style": { ... }
  }
}
```

The style block is translated by the Style Adapter Registry. See Section 4.

The frontend fetches the layer by calling:
```
GET /layers/{layer}?boundary={boundary_code}&boundary_level={boundary_level}&{filter params}
```

| Param | Type | Description |
|---|---|---|
| `layer` | string | roads, rivers, railroads, places, buildings, pois, protected_areas |
| `boundary_code` | string | ISO code of the boundary |
| `boundary_level` | string | country or province |
| `filter` | object | Optional query parameter filters |
| `style` | object | Library-specific style hints from the adapter |

---

### `remove_layer`
Remove a previously added layer from the map.

```json
{"action": "remove_layer", "params": {"layer": "pois"}}
```

---

### `highlight_boundary`
Visually highlight a boundary without zooming.

```json
{
  "action": "highlight_boundary",
  "params": {
    "boundary_code": "BG-02",
    "boundary_level": "province",
    "style": { ... }
  }
}
```

Style translated by the adapter. Neutral input: `color`, `size`, `opacity`.

---

### `show_stat`
Display a statistic in the frontend's info panel or sidebar.

```json
{
  "action": "show_stat",
  "params": {
    "label": "Hospitals in Burgas",
    "value": 29,
    "unit": "facilities",
    "boundary_code": "BG-02"
  }
}
```

---

### `show_chart`
Instruct the frontend to render a chart from structured data.

```json
{
  "action": "show_chart",
  "params": {
    "chart_type": "bar",
    "title": "Road length by type in Bulgaria",
    "data": [
      {"label": "Major Highway",     "value": 412.5},
      {"label": "Secondary Highway", "value": 1840.2},
      {"label": "Road",              "value": 3210.8}
    ],
    "unit": "km"
  }
}
```

---

### `clear_map`
Remove all agent-added layers and reset to base state.

```json
{"action": "clear_map", "params": {}}
```

---

## 10. Full Response Example

**Request** (frontend config set via `FRONTEND_LIBRARY=mapboxgl` at deployment):
```json
{
  "message": "Show me hospitals in Burgas province and tell me how many there are",
  "conversation_id": "conv_x7k2p"
}
```

**Response:**
```json
{
  "version": "1.0",
  "conversation_id": "conv_x7k2p",
  "frontend_library": "mapboxgl",
  "answer": "There are 29 hospitals in Burgas province. I have highlighted the province and added hospital locations to the map.",
  "commands": [
    {
      "action": "zoom_to",
      "params": {
        "boundary_code": "BG-02",
        "boundary_level": "province",
        "bbox": [27.09, 42.23, 27.93, 42.84]
      }
    },
    {
      "action": "highlight_boundary",
      "params": {
        "boundary_code": "BG-02",
        "boundary_level": "province",
        "style": {
          "paint": {"line-color": "#2980b9", "line-width": 3, "fill-opacity": 0.15}
        }
      }
    },
    {
      "action": "add_layer",
      "params": {
        "layer": "pois",
        "boundary_code": "BG-02",
        "boundary_level": "province",
        "filter": {"poi_type": "hospital"},
        "style": {
          "paint": {"circle-color": "#e74c3c", "circle-radius": 6, "circle-opacity": 0.9}
        }
      }
    },
    {
      "action": "show_stat",
      "params": {
        "label": "Hospitals in Burgas",
        "value": 29,
        "unit": "facilities",
        "boundary_code": "BG-02"
      }
    }
  ],
  "tools_used": ["get_province", "count_pois"],
  "data": {
    "pois": {"boundary_code": "BG-02", "total": 29, "breakdown": [{"type": "hospital", "count": 29}]}
  }
}
```

---

## 11. Frontend Implementation Contract

Any frontend that implements this protocol must:

1. **Declare** its library and capabilities in the `frontend` block of every request
2. **Display** the `answer` field in a chat or response panel
3. **Execute** each item in `commands` in order using its own mapping library API
4. For `add_layer` — fetch the layer from the API using the provided params and render it
5. For `show_stat` and `show_chart` — render in a sidebar or info panel
6. **Handle** unknown action types gracefully — log and skip rather than crash
7. **Check** the `version` field and surface a warning if the major version is unsupported

The frontend does **not** need to understand the agent's reasoning or tool calls.
It only needs to consume `answer` and `commands`.

---

## 12. Adding a New Frontend Library

To integrate a new mapping library:

1. Add the library identifier to the Style Adapter Registry in `app/agent/tools.py`
2. Define property mappings for `color`, `size`, and `opacity`
3. The frontend declares `"library": "your_library"` in requests
4. All style hints in responses are automatically translated

No changes to the protocol schema, command vocabulary, or agent logic are required.

---

## 13. Versioning

The `version` field is included in every response. Breaking changes to the
command vocabulary increment the major version (1.0 → 2.0). Additive changes
(new command types) increment the minor version (1.0 → 1.1).

Frontends should check the major version and surface a warning if they receive
a version they were not built against.
