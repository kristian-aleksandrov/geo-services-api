"""
agent.py
--------
AI agent logic for the /agent/chat endpoint.

Implements a GPT-4o tool-calling loop:
  1. Send user message + tool definitions to GPT-4o
  2. GPT-4o decides which tools to call
  3. Execute each tool call against the API
  4. Send results back to GPT-4o
  5. Repeat until GPT-4o has enough data and returns a final answer
  6. Build Agent-to-Frontend protocol commands from the tool call results
  7. Return answer + commands to the router

The agent never accesses the database directly.
All data is retrieved by calling the API endpoints via execute_tool().
"""

import os
import json
import uuid
from pathlib import Path
from openai import AzureOpenAI
from dotenv import load_dotenv

# Explicitly find and load .env from the project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.agent.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    frontend_config,
)

# ---------------------------------------------------------------------------
# Azure OpenAI client
# ---------------------------------------------------------------------------
# Client is created lazily inside run_agent() so missing credentials
# do not crash the app at startup. All other endpoints remain available
# even without Azure OpenAI configured.

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


def get_openai_client() -> AzureOpenAI:
    """
    Create an AzureOpenAI client from environment variables.
    Called inside run_agent() rather than at module level so the app
    starts cleanly even when Azure credentials are not yet configured.
    """
    api_key  = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

    if not api_key or not endpoint:
        raise ValueError(
            "Azure OpenAI credentials not configured. "
            "Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT in .env"
        )

    return AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version="2024-02-01",
    )

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
# This tells GPT-4o its role, what data it has access to, and how to
# format its responses. It reads the frontend capabilities so it knows
# which commands it can include in the response.

SYSTEM_PROMPT = f"""
You are a geospatial AI assistant for a World Bank geo services API.
You have access to the following data for analysis:
- Country boundaries (global, Natural Earth — use ISO alpha-3 codes e.g. BGR, KEN, USA)
- Province/region boundaries (global, World Bank Official Boundaries — use WB codes e.g. BGR001, BGR002)
- Municipality boundaries (global, World Bank Official Boundaries — use WB codes e.g. BGR002001)
- Roads, rivers, railroads, populated places (global, Natural Earth)
- Buildings and points of interest — hospitals, schools, pharmacies,
  banks, restaurants and more (Bulgaria only, OpenStreetMap via Geofabrik)

IMPORTANT workflow — always follow this order:
1. Determine the correct boundary level from the user's message:
   - "country" / "Bulgaria" / nation names → level="country"
   - "province" / "oblast" / "region" → level="province"
   - "municipality" / "city" / "town" / "commune" → level="municipality"
   - If ambiguous, prefer "municipality" for specific city names, "province" for region names
2. Call get_boundary_by_name with the correct level to get the boundary code.
3. Use the returned code AND level for all subsequent tool calls.
4. Never guess or hardcode boundary codes — always look them up by name first.
5. For buildings use count_buildings tool. For POIs (hospitals, schools etc.) use count_pois.

Examples:
  "hospitals in Bulgaria" → get_boundary_by_name(name="Bulgaria", level="country") → count_pois(boundary_level="country", poi_type="hospital")
  "hospitals in Burgas province" → get_boundary_by_name(name="Burgas", level="province") → count_pois(boundary_level="province", poi_type="hospital")
  "hospitals in Burgas municipality" → get_boundary_by_name(name="Burgas", level="municipality") → count_pois(boundary_level="municipality", poi_type="hospital")
  "buildings in Veliko Tarnovo municipality" → get_boundary_by_name(name="Veliko Tarnovo", level="municipality") → count_buildings(boundary_level="municipality")
  "buildings in Bulgaria" → get_boundary_by_name(name="Bulgaria", level="country") → count_buildings(boundary_level="country")
  "highways in Bulgaria" → get_boundary_by_name(name="Bulgaria", level="country") → road_statistics(boundary_level="country")
  "rivers in Veliko Tarnovo" → get_boundary_by_name(name="Veliko Tarnovo", level="province") → get_layer(layer="rivers")
  "show railroads in Bulgaria" → get_boundary_by_name(name="Bulgaria", level="country") → get_layer(layer="railroads")
  "cities in Bulgaria" → get_boundary_by_name(name="Bulgaria", level="country") → get_layer(layer="places")

Tool selection guide:
  - "city of X" / "show me X city" / "zoom to X" → get_place (searches places table)
  - "X province" / "X oblast" / "X region" → get_boundary_by_name with level="province"
  - "X municipality" / "X commune" → get_boundary_by_name with level="municipality"
  - hospitals/schools/pharmacies/amenities → count_pois
  - building footprints/structures → count_buildings
  - road LENGTH statistics → road_statistics
  - rivers/railroads/places/roads to SHOW on map → get_layer
  - road length AND show on map → road_statistics (map layer added automatically)

IMPORTANT data coverage limitations:
- Buildings and POIs (hospitals, schools etc.) are ONLY available for Bulgaria.
  If the user asks about POIs in any other country, explain this clearly.
- Roads, rivers, railroads and places are global datasets.
- When a query returns no results, always explain why rather than staying silent.

IMPORTANT Bulgarian boundary disambiguation:
- "Sofia city" or "city of Sofia" or "Sofia capital" → use BGR022 (Sofia-city province)
- "Sofia province" or "Sofia region" → use BGR021 (Sofia province surrounding the capital)
- "Burgas city" or "city of Burgas" → search at municipality level
- When a place name is ambiguous between province and municipality, prefer municipality
  unless the user explicitly says "province" or "oblast" or "region"
- Never ask the user to clarify between Sofia province and Sofia-city — default to BGR022

When answering questions:
1. Use the available tools to retrieve accurate data — never guess or make up statistics.
2. Always call get_boundary first when the user mentions a specific country or province,
   so you can zoom the map to the correct location.
3. For counting questions (how many hospitals, schools etc.) use count_pois.
4. For road length questions use road_statistics.
5. For population questions use population_statistics.
6. For area/size questions use boundary_area.
7. When the user asks to show or display a layer, use get_layer.

The frontend supports these map commands: {', '.join(frontend_config.capabilities)}
Only include commands from this list in your response.

Always respond in clear, concise English suitable for a professional audience.
After retrieving data, provide a direct answer followed by relevant context.
NEVER include JSON, code blocks, or technical data in your answer text.
NEVER embed map commands or coordinates in the answer — the protocol handles that automatically.
Keep answers conversational and factual. Example: "Burgas is a city in Bulgaria with a population of 195,966."
"""


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------
# After the tool-calling loop finishes, we inspect what tools were called
# and what data they returned to build the appropriate map commands.

def build_commands(tool_calls_log: list[dict]) -> list[dict]:
    """
    Build Agent-to-Frontend protocol commands from the tool call log.

    Each entry in tool_calls_log is:
        {"name": "count_pois", "args": {...}, "result": {...}}

    Returns an ordered list of protocol commands. Only includes command
    types declared in frontend_config.capabilities.
    """
    commands      = []
    seen_zooms    = set()   # avoid duplicate zoom_to for same boundary
    highlighted   = set()   # avoid duplicate highlight for same boundary

    # Always clear the map at the start of each agent response
    if frontend_config.supports("clear_map") and tool_calls_log:
        commands.append({"action": "clear_map", "params": {}})

    # --- First pass: build a name lookup from get_boundary_by_name results ---
    # Maps boundary_code -> human name for use in labels
    name_lookup = {}
    for call in tool_calls_log:
        if call["name"] == "get_boundary_by_name":
            best = call["result"].get("best_match", {})
            if best.get("code"):
                name_lookup[best["code"]] = best.get("name", best["code"])

    def label_for(code):
        return name_lookup.get(code, code)

    # --- Second pass: build commands ---
    for call in tool_calls_log:
        name   = call["name"]
        args   = call["args"]
        result = call["result"]

        # Resolve boundary_code from args or from result (get_boundary_by_name)
        if name == "get_boundary_by_name":
            best           = result.get("best_match", {})
            boundary_code  = best.get("code")
            boundary_level = args.get("level", "province")
        else:
            boundary_code  = args.get("boundary_code") or args.get("code")
            boundary_level = args.get("boundary_level") or args.get("level", "country")

        # get_place — zoom to city coordinates (no boundary_code needed)
        if name == "get_place":
            best = result.get("best_match", {})
            if best:
                if frontend_config.supports("zoom_to"):
                    commands.append({
                        "action": "zoom_to",
                        "params": {
                            "lat":  best.get("lat"),
                            "lon":  best.get("lon"),
                            "zoom": 12,
                        }
                    })
                # Highlight the municipality boundary as city footprint approximation
                if best.get("municipality_code") and frontend_config.supports("highlight_boundary"):
                    commands.append({
                        "action": "highlight_boundary",
                        "params": {
                            "boundary_code":  best["municipality_code"],
                            "boundary_level": "municipality",
                            "style": frontend_config.translate_style({
                                "intent":  "highlight",
                                "size":    2,
                                "opacity": 0.2,
                            })
                        }
                    })
                if frontend_config.supports("show_stat") and best.get("population"):
                    commands.append({
                        "action": "show_stat",
                        "params": {
                            "label": f"{best['name']} population",
                            "value": best["population"],
                            "unit":  "people",
                        }
                    })
            continue

        # Skip remaining commands if no boundary code
        if not boundary_code:
            continue

        # zoom_to — once per unique boundary
        if boundary_code not in seen_zooms:
            if frontend_config.supports("zoom_to"):
                commands.append({
                    "action": "zoom_to",
                    "params": {
                        "boundary_code":  boundary_code,
                        "boundary_level": boundary_level,
                    }
                })
            seen_zooms.add(boundary_code)

        # highlight_boundary — when boundary was looked up
        if name in ("get_boundary", "get_boundary_by_name"):
            if boundary_code not in highlighted and frontend_config.supports("highlight_boundary"):
                commands.append({
                    "action": "highlight_boundary",
                    "params": {
                        "boundary_code":  boundary_code,
                        "boundary_level": boundary_level,
                        "style": frontend_config.translate_style({
                            "intent":  "highlight",
                            "size":    2,
                            "opacity": 0.15,
                        })
                    }
                })
                highlighted.add(boundary_code)

        # add_layer — explicit get_layer call
        if name == "get_layer":
            layer       = args.get("layer")
            filter_type = args.get("filter_type")
            filter_dict = {}
            if filter_type:
                if layer == "pois":
                    filter_dict["poi_type"] = filter_type
                elif layer == "roads":
                    filter_dict["road_type"] = filter_type
                elif layer == "buildings":
                    filter_dict["building_type"] = filter_type

            # Layer-specific colors
            layer_colors = {
                "roads":      "#f0a500",
                "rivers":     "#58a6ff",
                "railroads":  "#bc8cff",
                "places":     "#3fb950",
                "pois":       "#f85149",
                "buildings":  "#e3b341",
            }
            color = layer_colors.get(layer, "#8b949e")

            if frontend_config.supports("add_layer"):
                commands.append({
                    "action": "add_layer",
                    "params": {
                        "layer":          layer,
                        "boundary_code":  boundary_code,
                        "boundary_level": boundary_level,
                        "filter":         filter_dict,
                        "style": frontend_config.translate_style({
                            "color":   color,
                            "size":    4,
                            "opacity": 0.8,
                        })
                    }
                })

            # Show feature count as stat
            feature_count = result.get("count", 0)
            if feature_count and frontend_config.supports("show_stat"):
                display_layer = filter_type or layer
                commands.append({
                    "action": "show_stat",
                    "params": {
                        "label":         f"{display_layer.capitalize()} in {label_for(boundary_code)}",
                        "value":         feature_count,
                        "unit":          "features",
                        "boundary_code": boundary_code,
                    }
                })

        # count_pois — show stat AND auto-add POI layer on map
        if name == "count_pois":
            total    = result.get("total", 0)
            poi_type = args.get("poi_type")
            display  = f"{poi_type.capitalize()}s" if poi_type else "POIs"

            if frontend_config.supports("show_stat"):
                commands.append({
                    "action": "show_stat",
                    "params": {
                        "label":         f"{display} in {label_for(boundary_code)}",
                        "value":         total,
                        "unit":          "facilities",
                        "boundary_code": boundary_code,
                    }
                })

            # Auto-add POI layer to map
            if frontend_config.supports("add_layer") and poi_type:
                commands.append({
                    "action": "add_layer",
                    "params": {
                        "layer":          "pois",
                        "boundary_code":  boundary_code,
                        "boundary_level": boundary_level,
                        "filter":         {"poi_type": poi_type},
                        "style": frontend_config.translate_style({
                            "intent":  "danger",
                            "size":    6,
                            "opacity": 0.9,
                        })
                    }
                })

        # count_buildings — show stat and add buildings layer
        if name == "count_buildings":
            total = result.get("total", 0)
            if frontend_config.supports("show_stat"):
                commands.append({
                    "action": "show_stat",
                    "params": {
                        "label":         f"Buildings in {label_for(boundary_code)}",
                        "value":         total,
                        "unit":          "buildings",
                        "boundary_code": boundary_code,
                    }
                })
            if frontend_config.supports("add_layer"):
                commands.append({
                    "action": "add_layer",
                    "params": {
                        "layer":          "buildings",
                        "boundary_code":  boundary_code,
                        "boundary_level": boundary_level,
                        "filter":         {},
                        "style": frontend_config.translate_style({
                            "color":   "#e3b341",
                            "size":    4,
                            "opacity": 0.7,
                        })
                    }
                })

        # road_statistics — show stat + chart
        if name == "road_statistics":
            total_km  = result.get("total_km", 0)
            breakdown = result.get("breakdown", [])

            if frontend_config.supports("show_stat"):
                commands.append({
                    "action": "show_stat",
                    "params": {
                        "label":         f"Total roads in {label_for(boundary_code)}",
                        "value":         total_km,
                        "unit":          "km",
                        "boundary_code": boundary_code,
                    }
                })
            if frontend_config.supports("show_chart") and breakdown:
                commands.append({
                    "action": "show_chart",
                    "params": {
                        "chart_type": "bar",
                        "title":      f"Road length by type — {label_for(boundary_code)}",
                        "data":       [{"label": r["type"], "value": r["total_km"]} for r in breakdown],
                        "unit":       "km",
                    }
                })
            # Auto-add roads layer
            if frontend_config.supports("add_layer"):
                commands.append({
                    "action": "add_layer",
                    "params": {
                        "layer":          "roads",
                        "boundary_code":  boundary_code,
                        "boundary_level": boundary_level,
                        "filter":         {},
                        "style": frontend_config.translate_style({
                            "color":   "#f0a500",
                            "size":    2,
                            "opacity": 0.8,
                        })
                    }
                })

        # population_statistics
        if name == "population_statistics" and frontend_config.supports("show_stat"):
            commands.append({
                "action": "show_stat",
                "params": {
                    "label":         f"Population in {label_for(boundary_code)}",
                    "value":         result.get("total_population", 0),
                    "unit":          "people",
                    "boundary_code": boundary_code,
                }
            })

        # boundary_area
        if name == "boundary_area" and frontend_config.supports("show_stat"):
            commands.append({
                "action": "show_stat",
                "params": {
                    "label":         f"Area of {label_for(boundary_code)}",
                    "value":         result.get("area_km2", 0),
                    "unit":          "km²",
                    "boundary_code": boundary_code,
                }
            })

    return commands


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def run_agent(message: str, conversation_id: str = None) -> dict:
    """
    Run the GPT-4o tool-calling loop for a user message.

    Flow:
      1. Build the initial messages list with system prompt + user message
      2. Send to GPT-4o with tool definitions
      3. If GPT-4o requests tool calls — execute them and loop
      4. When GPT-4o returns finish_reason="stop" — extract the answer
      5. Build protocol commands from the tool call log
      6. Return the full agent protocol response

    Args:
        message:         Natural language query from the user
        conversation_id: Optional token for multi-turn conversations

    Returns:
        Dict matching AgentChatResponse schema:
        {
            "version":          "1.0",
            "conversation_id":  str,
            "frontend_library": str,
            "answer":           str,
            "commands":         list,
            "tools_used":       list,
            "data":             dict,
        }
    """
    conversation_id = conversation_id or str(uuid.uuid4())[:8]

    client = get_openai_client()

    messages = [
        {"role": "system",  "content": SYSTEM_PROMPT},
        {"role": "user",    "content": message},
    ]

    tool_calls_log = []   # track all tool calls and their results
    tools_used     = []   # names of tools called (for transparency)
    raw_data       = {}   # raw results keyed by tool name

    # Tool-calling loop
    max_iterations = 10   # safety limit — prevents infinite loops
    iteration      = 0

    while iteration < max_iterations:
        iteration += 1

        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )

        choice = response.choices[0]

        # GPT-4o wants to call one or more tools
        if choice.finish_reason == "tool_calls":
            # Add GPT-4o's tool call message to the conversation
            messages.append(choice.message)

            for tool_call in choice.message.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                # Execute the tool
                try:
                    result = execute_tool(name, args)
                except Exception as e:
                    result = {"error": str(e)}

                # Log for command building and transparency
                tool_calls_log.append({"name": name, "args": args, "result": result})
                if name not in tools_used:
                    tools_used.append(name)
                raw_data[name] = result

                # Add tool result to conversation so GPT-4o can use it
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_call.id,
                    "content":      json.dumps(result),
                })

        # GPT-4o has a final answer
        elif choice.finish_reason == "stop":
            answer = choice.message.content
            commands = build_commands(tool_calls_log)

            return {
                "version":          "1.0",
                "conversation_id":  conversation_id,
                "frontend_library": frontend_config.library,
                "answer":           answer,
                "commands":         commands,
                "tools_used":       tools_used,
                "data":             raw_data,
            }

        else:
            # Unexpected finish reason — return what we have
            break

    # Safety fallback if loop exits without a stop
    return {
        "version":          "1.0",
        "conversation_id":  conversation_id,
        "frontend_library": frontend_config.library,
        "answer":           "I was unable to complete the analysis. Please try again.",
        "commands":         [],
        "tools_used":       tools_used,
        "data":             raw_data,
    }
