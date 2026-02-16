# 🧪 Sketric ML/Backend Engineer Test

## LiveKit Voice Agent Transformation Layer

Build a transformation layer that converts workflow JSON into a **LiveKit Voice Agent** with MCP support. Then run and test it with the provided scripts.

---

## Simple setup (3 steps)

### 1. Implement the agent

Complete **`workflow_parser/transformation_layer.py`**:

- **`build_agents_from_workflow(workflow_json, ctx)`** – **ctx is always passed by run.py.** Parse the workflow and derive session config yourself. Build a LiveKit `Agent` and an **`AgentSession`** (STT, LLM, TTS, vad from `ctx.proc.userdata["vad"]`, MCP servers with `allowed_tools`, turn_detection). Return `(Agent, AgentSession)`. When ctx is None, return `(agent, None)`.
- **`create_mcp_server(config)`** – Create an MCP server from config (url, type, headers, allowed_tools).

See the docstrings and TODOs in that file. Use **`sample_workflow.json`** as the reference workflow.

### 2. Configure and run the server

**One-time setup**

- Copy `.env.example` to `.env` and fill in your keys (see [Environment](#environment)).
- Install deps and download the turn-detector model (required for voice):
  ```bash
  uv sync
  uv run python scripts/setup.py
  ```
  This checks dependencies and downloads the turn-detector models required for voice.

**Run the agent**

```bash
uv sync
uv run python run.py
```

This loads `sample_workflow.json`, builds the agent via your **transformation_layer**, and starts the LiveKit voice server. Keep this terminal open.

### 3. Test your agent

In **another terminal** (same project, same `.env`):

```bash
uv run python scripts/join_room.py my-room
```

Open the **printed URL** in your browser, allow the microphone. The agent joins the room; talk to it and confirm it behaves as expected.

---

## Environment

Create a `.env` in the project root (see `.env.example`):

| Variable | Description |
|----------|-------------|
| `LIVEKIT_URL` | Your LiveKit project URL (e.g. `wss://your-project-xxx.livekit.cloud`) |
| `LIVEKIT_API_KEY` | Project API key from LiveKit Cloud |
| `LIVEKIT_API_SECRET` | Project API secret from LiveKit Cloud |
| `OPENAI_API_KEY` | OpenAI API key for the agent LLM |

Get LiveKit values from [LiveKit Cloud](https://cloud.livekit.io) → your project → Settings.

---

## Project structure

```
sketric-ml-backend-test/
├── README.md
├── .env.example
├── pyproject.toml
├── sample_workflow.json      # Example workflow
├── run.py                    # Starts LiveKit server (loads agent from transformation_layer)
├── scripts/
│   └── join_room.py          # Print a join URL to test your agent
└── workflow_parser/
    └── transformation_layer.py   # 👈 YOUR CODE HERE
```

---

## Requirements

Your implementation must:

1. **Validate** the workflow JSON structure.
2. **Build a LiveKit Agent** (instructions from the entry agent node).
3. **Create MCP servers** with `allowed_tools` filtering (use `create_mcp_server`) and attach them to the **AgentSession**.
4. **Return** `(Agent, AgentSession)` from `build_agents_from_workflow(workflow_json, ctx)`. run.py **always passes ctx**; derive session config from the workflow and build the session using ctx (e.g. vad from `ctx.proc.userdata["vad"]`). When ctx is None, return `(agent, None)`.

---

## Workflow JSON (reference)

`sample_workflow.json` includes:

- **triggerNode** – Entry point (voice).
- **agentNode** – Agent config: name, instructions, model, TTS.
- **toolNode** – MCP config: url, type, headers, allowed_tools.
- **edges** – Links between nodes (trigger → agent, agent → tools, etc.).

---

## Deadline

5 days from receiving this test.

Good luck.
