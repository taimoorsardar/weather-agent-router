"""
LiveKit Voice Agent Transformation Layer

YOUR TASK: Build a LiveKit Agent and AgentSession from a workflow JSON configuration.

The workflow JSON contains:
- triggerNode: Entry point with initial_message
- agentNode: Agent configuration (name, instructions, model)
- toolNode: MCP server configuration with allowed_tools

You need to:
1. Parse edges to find agent-tool connections
2. Create MCP server instances with allowed_tools filtering (create_mcp_server)
3. Derive session config (model, instructions, etc.) from the workflow yourself
4. Build the Agent and an AgentSession using ctx (vad from ctx.proc.userdata["vad"], STT, LLM, TTS, mcp_servers, turn_detection)
5. Return (Agent, AgentSession). run.py always passes ctx so you can build the session. When ctx is None (e.g. validation), return (agent, None).
"""

import logging
from typing import Dict, List, Optional, Any, Tuple

from livekit.agents import Agent, AgentSession

logger = logging.getLogger(__name__)


async def build_agents_from_workflow(
    workflow_json: Dict[str, Any],
    ctx: Any,
) -> Tuple[Optional[Agent], Optional[AgentSession]]:
    """
    Build a LiveKit Agent and AgentSession from workflow JSON.

    Args:
        workflow_json: Workflow config with 'nodes' and 'edges'
        ctx: JobContext (always passed by run.py). Use ctx.proc.userdata["vad"] for the session. When ctx is None, return (agent, None).

    Returns:
        (Agent, AgentSession or None). When ctx is not None, return a fully built session.
    """
    logger.info("Building agent from workflow...")

    # TODO: Step 1 - Find the entry agent and trigger node

    # TODO: Step 2 - Find MCP tools connected to the agent

    # TODO: Step 3 - Derive session config from workflow; build Agent

    # TODO: Step 4 - When ctx is not None, build AgentSession (vad=ctx.proc.userdata["vad"], stt, llm, tts, mcp_servers, turn_detection)

    # TODO: Step 5 - Return (agent, session or None)

    raise NotImplementedError("TODO: Implement build_agents_from_workflow")



def create_mcp_server(config: Dict[str, Any]):
    """
    Create an MCP server instance from configuration.
    
    Args:
        config: MCP configuration with:
            - url: Server URL (required)
            - type: "sse" or "streamable" (default: "sse")
            - headers: Optional headers dict
            - allowed_tools: Optional list of tool names to expose
            
    Returns:
        MCPServerHTTP instance, or None if config is invalid
        
    Example config:
        {
            "url": "https://mcp.example.com/calendar",
            "type": "streamable",
            "headers": {"Authorization": "Bearer token"},
            "allowed_tools": ["list_events", "create_event"]
        }
    """
    # TODO: Implement MCP server creation
    
    raise NotImplementedError("TODO: Implement create_mcp_server")
