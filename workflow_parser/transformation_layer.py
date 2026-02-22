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
import json as _json
import logging
from typing import Dict, List, Optional, Any, Tuple

from openai import AsyncOpenAI
from livekit.agents import Agent, AgentSession, function_tool, mcp
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

    # 3. Build MCP tool wrappers (each tool = a @function_tool that calls MCP on-demand)
    mcp_tools = _build_mcp_tool_wrappers(edges, entry_agent_node["id"], nodes_by_id)

    # Collect MCP tool names for instructions
    mcp_tool_names = [getattr(getattr(t, '__livekit_tool_info', None), 'name', '?') for t in mcp_tools]

    # 4. Build delegation tools (entry agent stays in control, delegates queries internally)
    delegation_tools = _build_delegation_tools(edges, entry_agent_node["id"], nodes_by_id)

    # Combine all tools
    all_tools = delegation_tools + mcp_tools

    # 5. Enhance instructions with capability context so the LLM knows what it can do
    base_instructions = agent_data.get("instructions", "You are a helpful assistant.")
    instructions = _enhance_instructions(base_instructions, delegation_tools, mcp_tools, mcp_tool_names)

    # 6. Build the entry Agent (no mcp_servers — tools are wrapped as function_tools)
    agent = Agent(
        instructions=instructions,
        tools=all_tools,
    )
    logger.info(f"Entry agent built with {len(delegation_tools)} delegation + {len(mcp_tools)} MCP tool(s)")

    # 6. Build AgentSession (only when ctx is available)
    if ctx is None:
        logger.info("No ctx — returning (agent, None)")
        return (agent, None)

    session = _build_session(ctx, agent_data)
    return (agent, session)


def _build_delegation_tools(
    edges: List[Dict],
    source_id: str,
    nodes_by_id: Dict[str, Dict],
) -> List:
    """Create delegation tools for AgentHandoff edges from *source_id*.

    Delegation pattern: the entry agent stays in control. When it calls a
    delegation tool, an internal LLM call is made with the target agent's
    instructions. The result is returned as text, so the entry agent can
    incorporate it into its response. No permanent agent switching occurs.
    """
    tools = []
    for edge in edges:
        if edge.get("type") != "AgentHandoff" or edge.get("source") != source_id:
            continue

        target_node = nodes_by_id.get(edge.get("target"))
        if not target_node or target_node.get("type") != "agentNode":
            continue

        target_data = target_node.get("data", {})
        if not target_data.get("is_enabled", True):
            continue

        target_name = target_data.get("name", "Agent")
        handoff_desc = target_data.get(
            "handoff_description",
            f"Delegate to {target_name}",
        )

        tool = _make_delegation_tool(target_name, handoff_desc, target_data)
        tools.append(tool)
        logger.info(f"Registered delegation tool → {target_name}")

    return tools


def _enhance_instructions(
    base: str,
    handoff_tools: List,
    mcp_tools: List,
    mcp_tool_names: Optional[List[str]] = None,
) -> str:
    """Append capability context to the agent's instructions.

    The LLM needs to know what tools it has and when to use them,
    especially for handoffs — otherwise it just says "I can't do that."
    """
    extras = []

    # MCP tools go FIRST so the LLM prioritizes them over delegation
    if mcp_tools:
        lines = [
            "PRIORITY TOOLS — You have direct access to these tools via MCP servers. "
            "You MUST use these tools FIRST when the user asks about spreadsheets, "
            "Google Sheets, creating rows, columns, or any data operations. "
            "Do NOT delegate these tasks to other agents."
        ]
        if mcp_tool_names:
            lines.append("Your available MCP tools:")
            for t in mcp_tool_names:
                lines.append(f"  - `{t}`")
            lines.append(
                "Call these tools directly. Do NOT say you can't do it. "
                "Do NOT delegate spreadsheet/data tasks to the web search agent."
            )
        extras.append("\n".join(lines))

    if handoff_tools:
        lines = [
            "You can also delegate tasks to specialized agents "
            "(ONLY for tasks that your MCP tools cannot handle):"
        ]
        for t in handoff_tools:
            info = getattr(t, "__livekit_tool_info", None)
            name = info.name if info else getattr(t, "__name__", "unknown")
            desc = info.description if info else getattr(t, "__doc__", "")
            lines.append(f"  - Call `{name}` — {desc}")
        lines.append(
            "Only use delegation when the request is clearly outside your MCP tool capabilities "
            "(e.g. general knowledge questions, web lookups)."
        )
        extras.append("\n".join(lines))

    if not extras:
        return base

    return base.rstrip() + "\n\n" + "\n\n".join(extras)


def _make_delegation_tool(
    target_name: str,
    description: str,
    target_data: Dict,
) -> Any:
    """Create a @function_tool that delegates to a specialist agent via an
    internal LLM call and returns the text response.

    The entry agent stays in control the entire time — no agent switching.
    The LLM passes the user's query, we call OpenAI with the target agent's
    instructions, and return the result as text for the entry agent to use.
    """
    fn_name = f"ask_{'_'.join(target_name.lower().split())}"
    model = target_data.get("model", "gpt-4o-mini")
    target_instructions = target_data.get("instructions", "You are a helpful assistant.")

    async def _delegation_fn(query: str) -> str:
        logger.info(f"Delegation → {target_name} | query: {query[:80]}")
        try:
            client = AsyncOpenAI()
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": target_instructions},
                    {"role": "user", "content": query},
                ],
            )
            result = response.choices[0].message.content or ""
            logger.info(f"Delegation ← {target_name} | response: {result[:80]}")
            return result
        except Exception as e:
            logger.exception(f"Delegation to {target_name} failed: {e}")
            return f"Sorry, I couldn't reach {target_name} right now."

    _delegation_fn.__name__ = fn_name
    _delegation_fn.__qualname__ = fn_name
    _delegation_fn.__doc__ = description
    return function_tool(_delegation_fn, name=fn_name, description=description)


# ---------------------------------------------------------------------------
# MCP tool wrappers — each allowed_tool becomes a @function_tool
# ---------------------------------------------------------------------------

def _build_mcp_tool_wrappers(
    edges: List[Dict],
    agent_id: str,
    nodes_by_id: Dict[str, Dict],
) -> List:
    """Create @function_tool wrappers for each MCP tool defined in the workflow.

    Instead of passing MCPServerHTTP to the Agent (which requires a persistent
    SSE connection that may time out), we create a regular @function_tool for
    each allowed_tool. When called, the tool makes a fresh MCP connection,
    calls the tool, and returns the result.

    This ensures the tools ALWAYS appear in the LLM's tool schema.
    """
    tools = []
    for edge in edges:
        if edge.get("source") != agent_id or edge.get("sourceHandle") != "tools":
            continue
        tool_node = nodes_by_id.get(edge.get("target"))
        if not tool_node or tool_node.get("type") != "toolNode":
            continue

        data = tool_node.get("data", {})
        if data.get("toolType") != "mcp" or not data.get("is_enabled", True):
            continue

        config = data.get("config", {})
        url = config.get("url", "")
        headers = config.get("headers")
        allowed = config.get("allowed_tools", [])

        if not url or not isinstance(allowed, list):
            continue

        for tool_name in allowed:
            if not isinstance(tool_name, str):
                continue
            tool = _make_mcp_tool_wrapper(tool_name, url, headers)
            tools.append(tool)

    logger.info(f"Created {len(tools)} MCP tool wrapper(s)")
    return tools


def _make_mcp_tool_wrapper(tool_name: str, url: str, headers: Optional[Dict]) -> Any:
    """Create a @function_tool that calls a single MCP tool via a fresh connection.

    Each call creates a fresh MCP connection → initializes → calls tool → closes.
    The tool takes an 'instructions' parameter — a natural-language description
    of what to do (e.g. "Create a spreadsheet named Expenses").
    """
    description = (
        f"MCP tool: {tool_name.replace('_', ' ')}. "
        "Pass a clear natural-language instruction describing what to do."
    )

    async def _mcp_call(instructions: str) -> str:
        logger.info(f"MCP tool call → {tool_name} | instructions: {instructions[:100]}")
        parsed = {"instructions": instructions}

        server = mcp.MCPServerHTTP(
            url=url,
            headers=headers,
            timeout=30,
            sse_read_timeout=60,
            client_session_timeout_seconds=60,
        )
        # Force Streamable HTTP transport — Zapier (and many modern MCP servers)
        # use Streamable HTTP, not SSE. The SDK auto-detects only for URLs ending
        # in /mcp, but Zapier's URL ends in /connect, causing an SSE timeout.
        server._use_streamable_http = True
        try:
            await asyncio.wait_for(server.initialize(), timeout=30.0)
            # Use the internal MCP client to call the tool
            tool_result = await asyncio.wait_for(
                server._client.call_tool(tool_name, parsed),
                timeout=30.0,
            )
            if tool_result.isError:
                error_str = "\n".join(str(part) for part in tool_result.content)
                logger.warning(f"MCP tool error ← {tool_name}: {error_str}")
                return f"Tool error: {error_str}"

            result = "\n".join(str(part) for part in tool_result.content)
            logger.info(f"MCP tool result ← {tool_name} | {result[:100]}")
            return result
        except asyncio.TimeoutError:
            msg = f"MCP tool {tool_name} timed out (30s) connecting to server"
            logger.warning(msg)
            return msg
        except Exception as e:
            msg = f"MCP tool {tool_name} failed: {e}"
            logger.exception(msg)
            return msg
        finally:
            try:
                await server.aclose()
            except Exception:
                pass

    _mcp_call.__name__ = tool_name
    _mcp_call.__qualname__ = tool_name
    _mcp_call.__doc__ = description
    return function_tool(_mcp_call, name=tool_name, description=description)


# ---------------------------------------------------------------------------
# MCP server with allowed_tools filtering (kept for create_mcp_server validation)
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
            timeout=30,
            sse_read_timeout=300,
            client_session_timeout_seconds=300,
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

def _build_session(ctx, agent_data: Dict) -> Optional[AgentSession]:
    """Build an AgentSession with STT, LLM, TTS, VAD, and turn detection."""
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
            turn_detection=turn_detector.EnglishModel(),
        )
        logger.info("AgentSession built successfully")
        return session
    except Exception as e:
        logger.exception(f"Failed to build AgentSession: {e}")
        return None
