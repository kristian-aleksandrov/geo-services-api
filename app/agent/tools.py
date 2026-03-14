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
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

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
            "name": "count_pois",
            "description": (
                "Count points of interest within a boundary, grouped by type. "
                "Use this when the user asks how many hospitals, schools, pharmacies, "
                "banks, or any other type of facility or amenity are in a specific area. "
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
                        "enum": ["country", "province"],
                        "description": "Whether the boundary is a country or province"
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
                        "enum": ["country", "province"],
                        "description": "Whether the boundary is a country or province"
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
                        "enum": ["country", "province"],
                        "description": "Whether the boundary is a country or province"
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
                        "enum": ["country", "province"],
                        "description": "Whether the boundary is a country or province"
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
                            "buildings", "pois", "protected_areas"
                        ],
                        "description": "The layer to retrieve"
                    },
                    "boundary_code": {
                        "type": "string",
                        "description": "ISO code of the boundary"
                    },
                    "boundary_level": {
                        "type": "string",
                        "enum": ["country", "province"],
                        "description": "Whether the boundary is a country or province"
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
    Execute a tool call by calling the corresponding API endpoint.

    The agent never accesses the database directly — it always goes
    through the API layer. This enforces the same validation and
    business logic as external callers.

    Args:
        name:  Tool name matching a key in TOOL_DEFINITIONS
        args:  Arguments dict as provided by GPT-4o

    Returns:
        Dict result from the API endpoint.

    Raises:
        ValueError if the tool name is not recognised.
    """
    with httpx.Client() as client:

        if name == "get_boundary":
            level = args["level"]
            code = args["code"]
            if level == "country":
                url = f"{API_BASE_URL}/boundaries/countries/{code}"
            else:
                url = f"{API_BASE_URL}/boundaries/provinces/{code}"
            response = client.get(url)
            return response.json()

        elif name == "count_pois":
            params = {
                "boundary": args["boundary_code"],
                "boundary_level": args["boundary_level"],
            }
            if "poi_type" in args:
                params["poi_type"] = args["poi_type"]
            response = client.get(f"{API_BASE_URL}/statistics/pois", params=params)
            return response.json()

        elif name == "road_statistics":
            params = {
                "boundary": args["boundary_code"],
                "boundary_level": args["boundary_level"],
            }
            response = client.get(f"{API_BASE_URL}/statistics/roads", params=params)
            return response.json()

        elif name == "population_statistics":
            params = {
                "boundary": args["boundary_code"],
                "boundary_level": args["boundary_level"],
            }
            response = client.get(f"{API_BASE_URL}/statistics/places", params=params)
            return response.json()

        elif name == "boundary_area":
            params = {
                "boundary": args["boundary_code"],
                "boundary_level": args["boundary_level"],
            }
            response = client.get(f"{API_BASE_URL}/statistics/area", params=params)
            return response.json()

        elif name == "get_layer":
            layer = args["layer"]
            params = {
                "boundary": args["boundary_code"],
                "boundary_level": args["boundary_level"],
            }
            if "filter_type" in args:
                # map to correct query param per layer
                if layer == "pois":
                    params["poi_type"] = args["filter_type"]
                elif layer == "roads":
                    params["road_type"] = args["filter_type"]
                elif layer == "buildings":
                    params["building_type"] = args["filter_type"]
            response = client.get(f"{API_BASE_URL}/layers/{layer}", params=params)
            return response.json()

        else:
            raise ValueError(f"Unknown tool: {name}")
