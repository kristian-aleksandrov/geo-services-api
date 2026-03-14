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
from openai import AzureOpenAI
from dotenv import load_dotenv

from app.agent.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
    frontend_config,
)

load_dotenv()

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
- Country and province boundaries (global, Natural Earth)
- Roads, rivers, railroads, populated places (global, Natural Earth)
- Buildings and points of interest — hospitals, schools, pharmacies,
  banks, restaurants and more (Bulgaria, OpenStreetMap)
- Protected areas (USA, Natural Earth)

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

    Args:
        tool_calls_log:  List of executed tool calls with their results

    Returns:
        List of command dicts following the agent protocol schema.
    """
    commands = []
    seen_boundaries = set()  # avoid duplicate zoom_to for same boundary

    for call in tool_calls_log:
        name   = call["name"]
        args   = call["args"]
        result = call["result"]

        boundary_code  = args.get("boundary_code") or args.get("code")
        boundary_level = args.get("boundary_level") or args.get("level", "country")

        # zoom_to — add once per unique boundary
        if boundary_code and boundary_code not in seen_boundaries:
            if frontend_config.supports("zoom_to"):
                commands.append({
                    "action": "zoom_to",
                    "params": {
                        "boundary_code":  boundary_code,
                        "boundary_level": boundary_level,
                    }
                })
            seen_boundaries.add(boundary_code)

        # highlight_boundary — when we retrieved a boundary
        if name == "get_boundary" and frontend_config.supports("highlight_boundary"):
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

        # add_layer — when we retrieved a vector layer
        if name == "get_layer" and frontend_config.supports("add_layer"):
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

            commands.append({
                "action": "add_layer",
                "params": {
                    "layer":          layer,
                    "boundary_code":  boundary_code,
                    "boundary_level": boundary_level,
                    "filter":         filter_dict,
                    "style": frontend_config.translate_style({
                        "intent":  "neutral",
                        "size":    5,
                        "opacity": 0.8,
                    })
                }
            })

        # show_stat — when we counted POIs
        if name == "count_pois" and frontend_config.supports("show_stat"):
            total    = result.get("total", 0)
            poi_type = args.get("poi_type", "POI")
            commands.append({
                "action": "show_stat",
                "params": {
                    "label":         f"{poi_type.capitalize()}s in {boundary_code}",
                    "value":         total,
                    "unit":          "facilities",
                    "boundary_code": boundary_code,
                }
            })

        # show_stat + show_chart — when we got road statistics
        if name == "road_statistics":
            total_km  = result.get("total_km", 0)
            breakdown = result.get("breakdown", [])

            if frontend_config.supports("show_stat"):
                commands.append({
                    "action": "show_stat",
                    "params": {
                        "label":         f"Total roads in {boundary_code}",
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
                        "title":      f"Road length by type — {boundary_code}",
                        "data": [
                            {"label": row["type"], "value": row["total_km"]}
                            for row in breakdown
                        ],
                        "unit": "km",
                    }
                })

        # show_stat — when we got population statistics
        if name == "population_statistics" and frontend_config.supports("show_stat"):
            commands.append({
                "action": "show_stat",
                "params": {
                    "label":         f"Population in {boundary_code}",
                    "value":         result.get("total_population", 0),
                    "unit":          "people",
                    "boundary_code": boundary_code,
                }
            })

        # show_stat — when we calculated boundary area
        if name == "boundary_area" and frontend_config.supports("show_stat"):
            commands.append({
                "action": "show_stat",
                "params": {
                    "label":         f"Area of {boundary_code}",
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
