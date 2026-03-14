"""
agent.py (router)
-----------------
Router for the /agent/chat endpoint.

Accepts a natural language message, runs the GPT-4o tool-calling agent,
and returns a structured response following the Agent-to-Frontend protocol.

See docs/agent_protocol.md for the full protocol specification.
"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import AgentChatRequest, AgentChatResponse
from app.agent.agent import run_agent

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest):
    """
    Natural language geospatial query interface.

    Accepts a plain English question and returns:
    - **answer**: Natural language response
    - **commands**: Ordered map commands for the Leaflet frontend
    - **tools_used**: API tools the agent called to answer the question
    - **data**: Raw data from tool calls

    The agent autonomously decides which API tools to call, retrieves
    spatial data from PostGIS via the statistics and layers endpoints,
    and returns both a human-readable answer and structured map commands.

    Frontend library and capabilities are configured at deployment time
    via environment variables — not passed per request.
    See docs/agent_protocol.md for the full protocol specification.

    Example request:
    ```json
    {"message": "How many hospitals are in Burgas province?"}
    ```

    Example response:
    ```json
    {
      "answer": "There are 29 hospitals in Burgas province.",
      "commands": [
        {"action": "zoom_to",    "params": {"boundary_code": "BG-02", "boundary_level": "province"}},
        {"action": "show_stat",  "params": {"label": "Hospitals in BG-02", "value": 29, "unit": "facilities"}}
      ],
      "tools_used": ["get_boundary", "count_pois"]
    }
    ```
    """
    try:
        result = run_agent(
            message=request.message,
            conversation_id=request.conversation_id,
        )
        return AgentChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
