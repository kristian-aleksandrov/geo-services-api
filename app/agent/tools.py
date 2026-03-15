"""
tools.py
--------
GPT-4o tool definitions and frontend adapter registry.

This module defines:
  1. STYLE_ADAPTERS   — translates neutral style properties to
                        library-specific equivalents (Level 1)
  2. FrontendConfig   — reads deployment-time frontend config from
                        environment variables (Level 2)
  3. TOOL_DEFINITIONS — GPT-4o function/tool schemas. These tell the
                        model what tools are available, what they do,
                        and what parameters they accept.
  4. execute_tool()   — dispatches tool calls from GPT-4o to the
                        correct statistics/layer API endpoint.
"""

import os
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ---------------------------------------------------------------------------
# 1. Style Adapter Registry (Level 1)
# ---------------------------------------------------------------------------
# Maps neutral style properties to library-specific equivalents.
# The agent always reasons in neutral terms internally:
#   color, size, opacity, intent
# At response time the correct adapter is applied based on FRONTEND_LIBRARY.

STYLE_ADAPTERS = {
    "leaflet": {
        "color":   "color",
        "size":    "radius",
        "opacity": "fillOpacity",
        "weight":  "weight",
    },
    "mapboxgl": {
        "color":   "circle-color",
        "size":    "circle-radius",
        "opacity": "circle-opacity",
        "weight":  "line-width",
    },
    "googlemaps": {
        "color":   "fillColor",
        "size":    "scale",
        "opacity": "fillOpacity",
        "weight":  "strokeWeight",
    },
    "arcgis": {
        "color":   "color",
        "size":    "size",
        "opacity": "opacity",
        "weight":  "width",
    },
    "openlayers": {
        "color":   "fill",
        "size":    "radius",
        "opacity": "opacity",
        "weight":  "width",
    },
}

# Semantic intent → colour mapping (library-neutral)
INTENT_COLORS = {
    "highlight": "#2980b9",
    "danger":    "#e74c3c",
    "success":   "#27ae60",
    "neutral":   "#7f8c8d",
}


def apply_style_adapter(neutral_style: dict, library: str) -> dict:
    """
    Translate a neutral style dict to library-specific property names.

    Args:
        neutral_style:  Dict with neutral keys (color, size, opacity, intent)
        library:        Target library identifier

    Returns:
        Dict with library-specific property names.

    Example (neutral → leaflet):
        {"color": "#e74c3c", "size": 6} → {"color": "#e74c3c", "radius": 6}

    Example (neutral → mapboxgl):
        {"color": "#e74c3c", "size": 6} → {"circle-color": "#e74c3c", "circle-radius": 6}
    """
    adapter = STYLE_ADAPTERS.get(library, STYLE_ADAPTERS["leaflet"])
    result = {}

    # Resolve intent to color if present
    if "intent" in neutral_style:
        neutral_style["color"] = INTENT_COLORS.get(
            neutral_style.pop("intent"), INTENT_COLORS["neutral"]
        )

    for neutral_key, value in neutral_style.items():
        mapped_key = adapter.get(neutral_key, neutral_key)
        result[mapped_key] = value

    # MapboxGL wraps paint properties in a paint object
    if library == "mapboxgl":
        return {"paint": result}

    return result


# ---------------------------------------------------------------------------
# 2. Frontend Configuration (Level 2)
# ---------------------------------------------------------------------------
# Read deployment-time frontend config from environment variables.
# These are set once at deployment — never passed per request.

class FrontendConfig:
    """
    Reads frontend library and capabilities from environment variables.

    Environment variables:
        FRONTEND_LIBRARY      — e.g. leaflet, mapboxgl, googlemaps
        FRONTEND_VERSION      — e.g. 1.9
        FRONTEND_CAPABILITIES — comma-separated command types

    Usage:
        config = FrontendConfig()
        if config.supports("show_chart"):
            commands.append(chart_command)
    """

    def __init__(self):
        self.library = os.getenv("FRONTEND_LIBRARY", "leaflet")
        self.version = os.getenv("FRONTEND_VERSION", "")
        raw_caps = os.getenv(
            "FRONTEND_CAPABILITIES",
            "zoom_to,add_layer,remove_layer,highlight_boundary,show_stat,show_chart,clear_map"
        )
        self.capabilities = [c.strip() for c in raw_caps.split(",")]

    def supports(self, command: str) -> bool:
        """Return True if this frontend supports the given command type."""
        return command in self.capabilities

    def translate_style(self, neutral_style: dict) -> dict:
        """Apply the style adapter for this frontend's library."""
        return apply_style_adapter(neutral_style, self.library)


# Singleton — instantiated once at module load
frontend_config = FrontendConfig()


# ---------------------------------------------------------------------------
# 3. GPT-4o Tool Definitions
# ---------------------------------------------------------------------------
# These schemas are sent to GPT-4o with every /agent/chat request.
# GPT-4o reads the name and description to decide when to call each tool,
# and the parameters schema to know what arguments to provide.
#
# IMPORTANT: description fields are the most critical part — they tell
# GPT-4o exactly when and how to use each tool.

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_place",
            "description": (
                "Search for a city, town or populated place by name in the places table. "
                "Use this when the user says 'city of X', 'town of X', or asks about a "
                "specific urban settlement rather than an administrative boundary. "
                "Returns the place location, population and type. "
                "Use this for: show me Sofia city, zoom to Plovdiv, where is Varna."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the city or town (e.g. Sofia, Plovdiv, Varna)"
                    },
                    "country_code": {
                        "type": "string",
                        "description": "Optional ISO alpha-3 country code (e.g. BGR)"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_boundary_by_name",
            "description": (
                "Search for a boundary (country, province, or municipality) by name. "
                "Use this when the user mentions a place name like 'Burgas', 'Kenya', 'Sofia'. "
                "Returns the boundary code and metadata needed for subsequent queries. "
                "Always call this first when the user mentions a place name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the boundary to search for (e.g. 'Burgas', 'Kenya', 'Sofia')"
                    },
                    "level": {
                        "type": "string",
                        "enum": ["country", "province", "municipality"],
                        "description": "Administrative level to search in"
                    },
                    "country_code": {
                        "type": "string",
                        "description": "Optional ISO alpha-3 country code to narrow the search (e.g. BGR for Bulgaria)"
                    }
                },
                "required": ["name", "level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_boundary",
            "description": (
                "Retrieve a boundary geometry (country or province) by ISO code. "
                "Use this when the user asks about a specific country or region, "
                "or when you need to zoom to a location on the map. "
                "For countries use ISO 3166-1 alpha-3 codes (e.g. BGR, KEN, USA). "
                "For provinces use ISO 3166-2 codes (e.g. BG-02 for Burgas, BG-03 for Varna)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "ISO code of the boundary (e.g. BGR, BG-02)"
                    },
                    "level": {
                        "type": "string",
                        "enum": ["country", "province"],
                        "description": "Whether this is a country or province boundary"
                    }
                },
                "required": ["code", "level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_buildings",
            "description": (
                "Count building footprints within a boundary, grouped by building type. "
                "Use this when the user asks how many buildings, houses, residential buildings, "
                "commercial buildings, or structures are in a specific area. "
                "Only available for Bulgaria. Returns total count and breakdown by building type."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "boundary_code": {
                        "type": "string",
                        "description": "WB or ISO code of the boundary"
                    },
                    "boundary_level": {
                        "type": "string",
                        "enum": ["country", "province", "municipality"],
                        "description": "Administrative level: country, province, or municipality"
                    }
                },
                "required": ["boundary_code", "boundary_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_pois",
            "description": (
                "Count points of interest within a boundary, grouped by type. "
                "Use this for amenities and facilities like hospitals, schools, pharmacies, "
                "banks, restaurants, hotels — NOT for buildings or structures. "
                "Works at country, province, and municipality level. "
                "Only available for Bulgaria (OSM data). "
                "Returns a total count and a breakdown by POI type."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "boundary_code": {
                        "type": "string",
                        "description": "ISO code of the boundary (e.g. BG-02 for Burgas, BGR for Bulgaria)"
                    },
                    "boundary_level": {
                        "type": "string",
                        "enum": ["country", "province", "municipality"],
                        "description": "Administrative level: country, province, or municipality"
                    },
                    "poi_type": {
                        "type": "string",
                        "description": (
                            "Type of POI to count. Common values: hospital, school, "
                            "pharmacy, bank, supermarket, restaurant, hotel. "
                            "Omit to get counts for all POI types."
                        )
                    }
                },
                "required": ["boundary_code", "boundary_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "road_statistics",
            "description": (
                "Calculate total road length in kilometres within a boundary, "
                "grouped by road type. Uses ST_Intersection to measure only the "
                "portion of each road inside the boundary — cross-boundary roads "
                "are clipped correctly. "
                "Use this when the user asks about road length, highway kilometres, "
                "or road infrastructure in a specific area."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "boundary_code": {
                        "type": "string",
                        "description": "ISO code of the boundary"
                    },
                    "boundary_level": {
                        "type": "string",
                        "enum": ["country", "province", "municipality"],
                        "description": "Administrative level: country, province, or municipality"
                    }
                },
                "required": ["boundary_code", "boundary_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "population_statistics",
            "description": (
                "Get population statistics for populated places within a boundary. "
                "Returns total population, number of places, and the name of the "
                "largest city. "
                "Use this when the user asks about population, cities, or urban "
                "centres in a specific area."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "boundary_code": {
                        "type": "string",
                        "description": "ISO code of the boundary"
                    },
                    "boundary_level": {
                        "type": "string",
                        "enum": ["country", "province", "municipality"],
                        "description": "Administrative level: country, province, or municipality"
                    }
                },
                "required": ["boundary_code", "boundary_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "boundary_area",
            "description": (
                "Calculate the area of a boundary in square kilometres. "
                "Use this when the user asks about the size or area of a country "
                "or province."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "boundary_code": {
                        "type": "string",
                        "description": "ISO code of the boundary"
                    },
                    "boundary_level": {
                        "type": "string",
                        "enum": ["country", "province", "municipality"],
                        "description": "Administrative level: country, province, or municipality"
                    }
                },
                "required": ["boundary_code", "boundary_level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_layer",
            "description": (
                "Retrieve a vector layer (roads, rivers, railroads, places, "
                "buildings, pois, protected_areas) for a given boundary. "
                "Use this when the user asks to show, display, or visualise a "
                "specific layer on the map."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {
                        "type": "string",
                        "enum": [
                            "roads", "rivers", "railroads", "places",
                            "buildings", "pois"
                        ],
                        "description": "The layer to retrieve"
                    },
                    "boundary_code": {
                        "type": "string",
                        "description": "ISO code of the boundary"
                    },
                    "boundary_level": {
                        "type": "string",
                        "enum": ["country", "province", "municipality"],
                        "description": "Administrative level: country, province, or municipality"
                    },
                    "filter_type": {
                        "type": "string",
                        "description": (
                            "Optional type filter. For pois: hospital, school etc. "
                            "For roads: Major Highway, Secondary Highway etc."
                        )
                    }
                },
                "required": ["layer", "boundary_code", "boundary_level"]
            }
        }
    },
]


# ---------------------------------------------------------------------------
# 4. Tool Executor
# ---------------------------------------------------------------------------
# Dispatches tool calls from GPT-4o to the correct API endpoint.
# The agent calls execute_tool(name, args) and gets back a dict result
# which it then passes back to GPT-4o as a tool result message.

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def execute_tool(name: str, args: dict) -> dict:
    """
    Execute a tool call by querying PostGIS directly.

    All tools query the database directly rather than calling the API via HTTP.
    The agent runs inside the same server process — calling itself via HTTP
    causes a connection abort on the same thread.

    Args:
        name:  Tool name matching a key in TOOL_DEFINITIONS
        args:  Arguments dict as provided by GPT-4o

    Returns:
        Dict result suitable for passing back to GPT-4o as a tool result.
    """
    from sqlalchemy import create_engine, text as sa_text
    from sqlalchemy.orm import sessionmaker

    db_url = (
        f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    engine = create_engine(db_url)
    db = sessionmaker(bind=engine)()

    try:
        if name == "get_place":
            search_name  = args["name"]
            country_code = args.get("country_code")
            params_db    = {"name": f"%{search_name}%"}
            country_filter = ""
            if country_code:
                country_filter = "AND country_code = :country_code"
                params_db["country_code"] = country_code
            rows = db.execute(sa_text(f"""
                SELECT name, name_ascii, country_code, country_name,
                       type, population, is_capital, lat, lon
                FROM geo.places
                WHERE LOWER(name) LIKE LOWER(:name)
                {country_filter}
                ORDER BY population DESC NULLS LAST
                LIMIT 5
            """), params_db).mappings().fetchall()
            if rows:
                results = [dict(r) for r in rows]
                best = results[0]
                # Try to find matching municipality boundary
                if best.get("lat") and best.get("lon"):
                    muni_row = db.execute(sa_text("""
                        SELECT code, name FROM geo.municipalities
                        WHERE ST_Within(
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                            geometry
                        )
                        LIMIT 1
                    """), {"lat": best["lat"], "lon": best["lon"]}).mappings().fetchone()
                    if muni_row:
                        best["municipality_code"] = muni_row["code"]
                        best["municipality_name"] = muni_row["name"]
                return {"found": True, "results": results, "best_match": best}
            return {"found": False, "search_name": search_name}

        elif name == "get_boundary_by_name":
            search_name  = args["name"]
            level        = args["level"]
            country_code = args.get("country_code")
            table = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(level, "provinces")

            # countries table uses 'code' for ISO alpha-3, no country_code column
            # provinces and municipalities have 'country_code' column
            params_db = {"name": f"%{search_name}%"}
            country_filter = ""
            if country_code and level != "country":
                country_filter = "AND country_code = :country_code"
                params_db["country_code"] = country_code

            # Select correct columns per table
            if level == "country":
                select_cols = "code, name, code AS country_code"
            else:
                select_cols = "code, name, country_code"

            rows = db.execute(sa_text(f"""
                SELECT {select_cols}
                FROM geo.{table}
                WHERE LOWER(name) LIKE LOWER(:name)
                {country_filter}
                ORDER BY name
                LIMIT 5
            """), params_db).mappings().fetchall()
            if rows:
                results = [{"code": r["code"], "name": r["name"], "country_code": r["country_code"], "level": level} for r in rows]
                return {"found": True, "level": level, "results": results, "best_match": results[0]}
            return {"found": False, "level": level, "search_name": search_name}

        elif name == "get_boundary":
            level = args["level"]
            code  = args["code"]
            table = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(level, "provinces")
            row = db.execute(
                sa_text(f"SELECT name, code FROM geo.{table} WHERE code = :code"),
                {"code": code}
            ).mappings().fetchone()
            if row:
                return {"found": True, "code": code, "level": level, "name": row["name"]}
            return {"found": False, "code": code, "level": level}

        elif name == "count_buildings":
            bc  = args["boundary_code"]
            bl  = args["boundary_level"]
            tbl = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(bl, "provinces")
            rows = db.execute(sa_text(f"""
                SELECT b.type, COUNT(*) AS count
                FROM geo.buildings b
                JOIN geo.{tbl} bnd ON ST_Intersects(b.geometry, bnd.geometry)
                WHERE bnd.code = :boundary_code
                GROUP BY b.type ORDER BY count DESC
            """), {"boundary_code": bc}).mappings().fetchall()
            bd = [{"type": r["type"], "count": r["count"]} for r in rows]
            return {"boundary_code": bc, "total": sum(r["count"] for r in bd), "breakdown": bd}

        elif name == "count_pois":
            bc  = args["boundary_code"]
            bl  = args["boundary_level"]
            pt  = args.get("poi_type")
            tbl = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(bl, "provinces")
            pdb = {"boundary_code": bc}
            ext = "AND p.type = :poi_type" if pt else ""
            if pt:
                pdb["poi_type"] = pt
            rows = db.execute(sa_text(f"""
                SELECT p.type, COUNT(*) AS count
                FROM geo.pois p
                JOIN geo.{tbl} b ON ST_Intersects(p.geometry, b.geometry)
                WHERE b.code = :boundary_code {ext}
                GROUP BY p.type ORDER BY count DESC
            """), pdb).mappings().fetchall()
            bd = [{"type": r["type"], "count": r["count"]} for r in rows]
            return {"boundary_code": bc, "total": sum(r["count"] for r in bd), "breakdown": bd}

        elif name == "road_statistics":
            bc  = args["boundary_code"]
            bl  = args["boundary_level"]
            tbl = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(bl, "provinces")
            rows = db.execute(sa_text(f"""
                SELECT r.type,
                       ROUND(SUM(ST_Length(
                           ST_Intersection(r.geometry, b.geometry)::geography
                       ) / 1000)::numeric, 2) AS total_km
                FROM geo.roads r
                JOIN geo.{tbl} b ON ST_Intersects(r.geometry, b.geometry)
                WHERE b.code = :boundary_code
                GROUP BY r.type ORDER BY total_km DESC
            """), {"boundary_code": bc}).mappings().fetchall()
            bd = [{"type": r["type"], "total_km": float(r["total_km"])} for r in rows]
            return {"boundary_code": bc, "total_km": round(sum(r["total_km"] for r in bd), 2), "breakdown": bd}

        elif name == "population_statistics":
            bc  = args["boundary_code"]
            bl  = args["boundary_level"]
            tbl = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(bl, "provinces")
            row = db.execute(sa_text(f"""
                SELECT COUNT(*) AS place_count,
                       SUM(p.population) AS total_population,
                       (SELECT p2.name FROM geo.places p2
                        JOIN geo.{tbl} b2 ON ST_Intersects(p2.geometry, b2.geometry)
                        WHERE b2.code = :boundary_code
                        ORDER BY p2.population DESC NULLS LAST LIMIT 1) AS largest_city
                FROM geo.places p
                JOIN geo.{tbl} b ON ST_Intersects(p.geometry, b.geometry)
                WHERE b.code = :boundary_code
            """), {"boundary_code": bc}).mappings().fetchone()
            return {
                "boundary_code":    bc,
                "place_count":      int(row["place_count"] or 0),
                "total_population": int(row["total_population"] or 0),
                "largest_city":     row["largest_city"],
            }

        elif name == "boundary_area":
            bc  = args["boundary_code"]
            bl  = args["boundary_level"]
            tbl = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(bl, "provinces")
            row = db.execute(sa_text(f"""
                SELECT ROUND((ST_Area(geometry::geography) / 1000000)::numeric, 2) AS area_km2
                FROM geo.{tbl} WHERE code = :code
            """), {"code": bc}).mappings().fetchone()
            return {"boundary_code": bc, "area_km2": float(row["area_km2"]) if row else 0.0}

        elif name == "get_layer":
            # Return metadata + feature count.
            # The frontend fetches actual GeoJSON directly from /layers/{layer}.
            layer       = args["layer"]
            bc          = args["boundary_code"]
            bl          = args["boundary_level"]
            ft          = args.get("filter_type")
            tbl         = {"country": "countries", "province": "provinces", "municipality": "municipalities"}.get(bl, "provinces")

            # Map layer name to geo table
            layer_table = {
                "roads": "roads", "rivers": "rivers", "railroads": "railroads",
                "places": "places", "buildings": "buildings", "pois": "pois"
            }.get(layer, layer)

            # Count features in boundary
            type_col = "fclass" if layer == "pois" else "type"
            filter_clause = ""
            count_params = {"boundary_code": bc}
            if ft and layer in ("pois", "roads", "buildings"):
                col = {"pois": "type", "roads": "type", "buildings": "type"}.get(layer, "type")
                filter_clause = f"AND l.{col} = :filter_type"
                count_params["filter_type"] = ft

            try:
                count_row = db.execute(sa_text(f"""
                    SELECT COUNT(*) AS count
                    FROM geo.{layer_table} l
                    JOIN geo.{tbl} b ON ST_Intersects(l.geometry, b.geometry)
                    WHERE b.code = :boundary_code
                    {filter_clause}
                """), count_params).mappings().fetchone()
                count = int(count_row["count"]) if count_row else 0
            except Exception:
                count = 0

            return {
                "layer":          layer,
                "boundary_code":  bc,
                "boundary_level": bl,
                "filter_type":    ft,
                "count":          count,
                "status":         "ready",
            }

        else:
            raise ValueError(f"Unknown tool: {name}")

    finally:
        db.close()
        engine.dispose()
