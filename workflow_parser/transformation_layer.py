"""
LiveKit Voice Agent Transformation Layer

Builds a LiveKit Agent and AgentSession from a workflow JSON.

Workflow JSON contains:
- triggerNode: Entry point (voice trigger)
- agentNode: Agent config (name, instructions, model, tts_config)
- toolNode: MCP tool config (url, headers, allowed_tools)
- edges: Connections between nodes
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple

from livekit.agents import Agent, AgentSession, mcp
from livekit.plugins.openai import STT, LLM, TTS

try:
    from livekit.plugins.turn_detector import english as turn_detector
except ImportError:
    turn_detector = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def build_agents_from_workflow(
    workflow_json: Dict[str, Any],
    ctx: Any,
) -> Tuple[Optional[Agent], Optional[AgentSession]]:
    """
    Parse workflow JSON → build Agent + AgentSession.

    Returns (Agent, AgentSession) when ctx is provided,
    or (Agent, None) when ctx is None (validation mode).
    """
    nodes = workflow_json.get("nodes", [])
    edges = workflow_json.get("edges", [])

    if not nodes:
        logger.error("No nodes found in workflow")
        return (None, None)

    # Build lookup map for O(1) node access
    nodes_by_id = {n["id"]: n for n in nodes}

    # 1. Find trigger node
    trigger = _find_node_by_type(nodes, "triggerNode")
    if not trigger:
        logger.error("No triggerNode found")
        return (None, None)

    # 2. Find entry agent (connected to trigger)
    entry_agent_node = _find_target(edges, trigger["id"], nodes_by_id, "agentNode")
    if not entry_agent_node:
        logger.error("No agentNode connected to trigger")
        return (None, None)

    agent_data = entry_agent_node.get("data", {})
    if not agent_data.get("is_enabled", True):
        logger.error(f"Entry agent '{agent_data.get('name')}' is disabled")
        return (None, None)

    logger.info(f"Entry agent: {agent_data.get('name')} | model: {agent_data.get('model')}")

    # 3. Collect MCP servers from connected tool nodes
    mcp_servers = _build_mcp_servers(edges, entry_agent_node["id"], nodes_by_id)

    # 4. Pre-initialize MCP servers (prevents session.start() from hanging)
    if ctx is not None and mcp_servers:
        mcp_servers = await _pre_init_mcp_servers(mcp_servers, timeout=15.0)

    # 5. Build Agent
    agent = Agent(instructions=agent_data.get("instructions", "You are a helpful assistant."))

    # 6. Build AgentSession (only when ctx is available)
    if ctx is None:
        logger.info("No ctx — returning (agent, None)")
        return (agent, None)

    session = _build_session(ctx, agent_data, mcp_servers)
    return (agent, session)


# ---------------------------------------------------------------------------
# MCP server with allowed_tools filtering
# ---------------------------------------------------------------------------

class _FilteredMCPServer(mcp.MCPServerHTTP):
    """Wraps MCPServerHTTP to filter tools to an allowed list."""

    def __init__(self, url: str, headers=None, allowed_tools: list[str] | None = None, **kw):
        super().__init__(url=url, headers=headers, **kw)
        self._allowed_tools = set(allowed_tools) if allowed_tools else None

    async def list_tools(self):
        all_tools = await super().list_tools()
        if self._allowed_tools is None:
            return all_tools
        filtered = [t for t in all_tools if t.name in self._allowed_tools]
        logger.info(f"Filtered tools: {len(filtered)}/{len(all_tools)} exposed")
        return filtered


def create_mcp_server(config: Dict[str, Any]):
    """
    Create an MCPServerHTTP from a config dict.

    Required key:  url (str)
    Optional keys: headers (dict), allowed_tools (list[str])

    Returns MCPServerHTTP (with tool filtering) or None on invalid config.
    """
    if not config or not isinstance(config, dict):
        logger.warning("Invalid MCP config: expected a dict")
        return None

    url = config.get("url")
    if not url or not isinstance(url, str) or not url.strip():
        logger.warning("Invalid MCP config: missing or empty 'url'")
        return None
    url = url.strip()

    # Headers — must be a dict, default to None
    headers = config.get("headers")
    if headers and not isinstance(headers, dict):
        logger.warning(f"MCP {url}: headers is not a dict, ignoring")
        headers = None

    # Allowed tools — must be a list of strings if present
    allowed_tools = config.get("allowed_tools")
    if allowed_tools is not None:
        if not isinstance(allowed_tools, list):
            logger.warning(f"MCP {url}: allowed_tools is not a list, rejecting")
            return None
        allowed_tools = [t for t in allowed_tools if isinstance(t, str)]

    try:
        server = _FilteredMCPServer(
            url=url,
            headers=headers,
            allowed_tools=allowed_tools if allowed_tools else None,
            timeout=10,
            sse_read_timeout=30,
            client_session_timeout_seconds=10,
        )
        logger.info(f"Created MCP server: {url}  (tools: {len(allowed_tools) if allowed_tools else 'all'})")
        return server
    except Exception as e:
        logger.exception(f"Failed to create MCP server for {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_node_by_type(nodes: List[Dict], node_type: str) -> Optional[Dict]:
    """Return the first node matching *node_type*."""
    for n in nodes:
        if n.get("type") == node_type:
            return n
    return None


def _find_target(
    edges: List[Dict],
    source_id: str,
    nodes_by_id: Dict[str, Dict],
    target_type: str,
) -> Optional[Dict]:
    """Find the first connected target node of *target_type* from *source_id*."""
    for edge in edges:
        if edge.get("source") == source_id:
            target = nodes_by_id.get(edge.get("target"))
            if target and target.get("type") == target_type:
                return target
    return None


def _build_mcp_servers(
    edges: List[Dict],
    agent_id: str,
    nodes_by_id: Dict[str, Dict],
) -> List:
    """Collect MCP servers from tool nodes connected to *agent_id*."""
    servers = []
    for edge in edges:
        if edge.get("source") != agent_id or edge.get("sourceHandle") != "tools":
            continue
        tool_node = nodes_by_id.get(edge.get("target"))
        if not tool_node or tool_node.get("type") != "toolNode":
            continue

        data = tool_node.get("data", {})
        if data.get("toolType") != "mcp" or not data.get("is_enabled", True):
            continue

        server = create_mcp_server(data.get("config", {}))
        if server:
            servers.append(server)

    logger.info(f"Total MCP servers: {len(servers)}")
    return servers


async def _pre_init_mcp_servers(servers: List, timeout: float = 15.0) -> List:
    """Pre-initialize MCP servers with a timeout so session.start() doesn't hang."""
    if not servers:
        return []

    ready = []
    for server in servers:
        try:
            await asyncio.wait_for(server.initialize(), timeout=timeout)
            ready.append(server)
            logger.info(f"MCP server initialized: {server._url}")
        except asyncio.TimeoutError:
            logger.warning(f"MCP server timed out during init ({timeout}s), skipping")
            await server.aclose()
        except Exception as e:
            logger.warning(f"MCP server init failed: {e}, skipping")
            await server.aclose()

    logger.info(f"MCP servers ready: {len(ready)}/{len(servers)}")
    return ready


def _build_session(ctx, agent_data: Dict, mcp_servers: List) -> Optional[AgentSession]:
    """Build an AgentSession with STT, LLM, TTS, VAD, MCP, and turn detection."""
    try:
        vad = ctx.proc.userdata.get("vad")
        if not vad:
            logger.warning("VAD not found in ctx.proc.userdata")

        if turn_detector is None:
            logger.error("turn_detector not installed — run: uv run python scripts/setup.py")
            return None

        tts_cfg = agent_data.get("tts_config", {})

        session = AgentSession(
            stt=STT(),
            llm=LLM(model=agent_data.get("model", "gpt-4o-mini")),
            tts=TTS(voice=tts_cfg.get("voice", "nova")),
            vad=vad,
            mcp_servers=mcp_servers or None,
            turn_detection=turn_detector.EnglishModel(),
        )
        logger.info("AgentSession built successfully")
        return session
    except Exception as e:
        logger.exception(f"Failed to build AgentSession: {e}")
        return None
