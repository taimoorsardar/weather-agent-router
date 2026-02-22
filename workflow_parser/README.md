# Workflow Parser — Transformation Layer

## What It Does

The transformation layer takes a **workflow JSON** (a graph of nodes and edges) and dynamically builds a **LiveKit Voice Agent** with tools, delegation capabilities, and a fully configured audio session.

```
Workflow JSON  ──►  transformation_layer.py  ──►  (Agent, AgentSession)
```

The agent can:
- Call **MCP tools** (e.g. Google Sheets via Zapier) directly
- **Delegate** to specialist agents (e.g. Web Search) without losing control
- Speak and listen using OpenAI STT/TTS with voice activity detection

---

## Workflow JSON Structure

The workflow is a directed graph with 3 node types and 2 edge types:

```
┌─────────────┐   default    ┌─────────────┐   tools     ┌─────────────┐
│ triggerNode  │ ───────────► │  agentNode   │ ──────────► │  toolNode   │
│ (entry point)│              │ (Google Sheet │             │ (MCP config)│
└─────────────┘              │   Agent)      │             └─────────────┘
                             └──────┬────────┘
                                    │ AgentHandoff
                                    ▼
                             ┌─────────────┐
                             │  agentNode   │
                             │ (Web Search  │
                             │   Agent)     │
                             └─────────────┘
```

**Nodes:**
| Type | Purpose | Key Fields |
|------|---------|------------|
| `triggerNode` | Entry point — where the workflow starts | — |
| `agentNode` | Agent config | `name`, `instructions`, `model`, `tts_config`, `handoff_description`, `is_enabled` |
| `toolNode` | MCP tool server config | `toolType: "mcp"`, `config: {url, headers, allowed_tools}` |

**Edges:**
| Type | From → To | Purpose |
|------|-----------|---------|
| `default` (sourceHandle: `tools`) | agentNode → toolNode | Connects agent to its MCP tools |
| `AgentHandoff` | agentNode → agentNode | Defines delegation capability between agents |

---

## Exported Functions

The package exports two functions via `__init__.py`:

```python
from workflow_parser import build_agents_from_workflow, create_mcp_server
```

### `build_agents_from_workflow(workflow_json, ctx)`

Main entry point. Transforms workflow JSON into a ready-to-use agent and session.

**Parameters:**
- `workflow_json` — dict with `nodes` and `edges` lists
- `ctx` — LiveKit job context (or `None` for validation/testing)

**Returns:** `(Agent, AgentSession)` or `(Agent, None)` if `ctx` is `None`

**What it does (step by step):**
1. Finds the `triggerNode` in the workflow
2. Follows the edge from trigger to find the **entry agent** (`agentNode`)
3. Builds **MCP tool wrappers** — one `@function_tool` per allowed MCP tool
4. Builds **delegation tools** — one `@function_tool` per AgentHandoff edge
5. Enhances the agent's instructions with tool/delegation context
6. Constructs the `Agent` with all tools
7. Constructs the `AgentSession` with STT, LLM, TTS, VAD, and turn detection

### `create_mcp_server(config)`

Validates an MCP config dict and creates a filtered `MCPServerHTTP` instance.

**Parameters:**
- `config` — dict with required `url` (str) and optional `headers` (dict), `allowed_tools` (list[str])

**Returns:** `_FilteredMCPServer` instance or `None` if config is invalid

**Validation rules:**
- `url` must be a non-empty string
- `headers` must be a dict (ignored if not)
- `allowed_tools` must be a list of strings (rejected if not a list)

---

## Internal Functions

### MCP Tool Wrappers

#### `_build_mcp_tool_wrappers(edges, agent_id, nodes_by_id)`

Scans edges for `toolNode` connections from the agent, reads each tool node's config, and creates a `@function_tool` wrapper for every tool name in `allowed_tools`.

**Why wrappers instead of passing `MCPServerHTTP` to the Agent?**

The LiveKit SDK's native `mcp_servers` parameter requires a **persistent SSE connection** to the MCP server. If the server is slow or the connection drops, the tools silently disappear from the LLM's tool schema — so the agent never calls them.

By wrapping each tool as a `@function_tool`, the tools **always appear** in the schema. Each call creates a fresh connection, calls the tool, and closes.

#### `_make_mcp_tool_wrapper(tool_name, url, headers)`

Creates a single `@function_tool` for one MCP tool. The generated function:

1. Takes an `instructions` parameter (natural-language description of what to do)
2. Creates a fresh `MCPServerHTTP` connection
3. Forces **Streamable HTTP transport** (Zapier and modern MCP servers use this, not SSE)
4. Calls `server._client.call_tool(name, {"instructions": instructions})`
5. Returns the result text or an error message
6. Closes the connection in `finally`

**Transport fix:** The SDK auto-detects transport by URL suffix (`/mcp` = Streamable HTTP, anything else = SSE). Zapier's URL ends in `/connect`, so it defaults to SSE which hangs. We force `server._use_streamable_http = True`.

---

### Delegation Tools

#### `_build_delegation_tools(edges, source_id, nodes_by_id)`

Scans edges for `AgentHandoff` connections from the entry agent. For each target agent, creates a delegation tool.

#### `_make_delegation_tool(target_name, description, target_data)`

Creates a `@function_tool` named `ask_{agent_name}` that:

1. Takes a `query` string from the entry agent
2. Makes an internal `AsyncOpenAI` API call using the target agent's `instructions` and `model`
3. Returns the response text to the entry agent

**Why delegation instead of permanent handoff?**

The LiveKit SDK supports permanent agent handoffs (returning an `Agent` from a tool switches to it). But this means:
- The user gets "stuck" with the specialist agent
- The specialist can't route back to the entry agent
- The SDK waits for the next user message before the new agent runs

With delegation, the **entry agent stays in control** — it asks the specialist, gets a text answer, and incorporates it into its own response. Simpler and more predictable.

---

### Instruction Enhancement

#### `_enhance_instructions(base, handoff_tools, mcp_tools, mcp_tool_names)`

Appends capability context to the agent's system prompt so the LLM knows what tools it has. Without this, the LLM would say "I can't do that" because it doesn't know about its tools.

**Ordering matters:** MCP tools are listed **first** as "PRIORITY TOOLS" with explicit instructions to use them before delegating. This prevents the LLM from routing Google Sheets requests to the web search agent.

Structure of enhanced instructions:
```
{original instructions}

PRIORITY TOOLS — You have direct access to these tools via MCP servers...
  - google_sheets_create_spreadsheet
  - google_sheets_create_worksheet
  ...

You can also delegate tasks to specialized agents...
  - Call ask_web_search_agent — Handoff to this agent for web search queries
```

---

### Graph Traversal Helpers

#### `_find_node_by_type(nodes, node_type)`

Returns the first node matching the given type. Used to find the `triggerNode`.

#### `_find_target(edges, source_id, nodes_by_id, target_type)`

Follows edges from `source_id` and returns the first connected node of `target_type`. Used to find the entry agent connected to the trigger.

---

### Session Builder

#### `_build_session(ctx, agent_data)`

Constructs an `AgentSession` with:

| Component | Implementation | Source |
|-----------|---------------|--------|
| STT | `openai.STT()` | OpenAI Whisper |
| LLM | `openai.LLM(model=...)` | Model from agent config |
| TTS | `openai.TTS(voice=...)` | Voice from `tts_config` (default: `nova`) |
| VAD | `silero.VAD` | Pre-loaded in `_prewarm()` |
| Turn Detection | `english.EnglishModel()` | End-of-utterance detection |

---

### MCP Server Validation

#### `_FilteredMCPServer` (class)

Subclasses `MCPServerHTTP` and overrides `list_tools()` to filter the returned tools to only those in `allowed_tools`. Used by `create_mcp_server()` for validation purposes.

---

## How `run.py` Uses It

```python
# 1. Load workflow JSON
workflow = load_workflow(Path("sample_workflow.json"))

# 2. Build agent + session from workflow
agent, session = await build_agents_from_workflow(workflow, ctx)

# 3. Start the voice session
await session.start(agent=agent, room=ctx.room, room_options=...)
```

Additional features in `run.py`:
- **Duplicate prevention:** `_on_request` handler tracks active rooms and rejects duplicate dispatches
- **Plugin registration:** Imports `silero`, `noise_cancellation`, `openai`, `turn_detector` on the main thread
- **VAD prewarming:** Loads the Silero VAD model once in `_prewarm()`, shared across all sessions

---

## Testing

```bash
# MCP server validation tests (15 tests)
.venv\Scripts\python.exe scripts/test_mcp_server.py

# Transformation layer validation tests (3 tests)
.venv\Scripts\python.exe scripts/validate_transformation.py

# Live test — start server, then join a room
.venv\Scripts\python.exe run.py
.venv\Scripts\python.exe scripts/join_room.py my-room
```
