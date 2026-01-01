# 🧪 Sketric ML/Backend Engineer Test

## LiveKit Voice Agent Transformation Layer

Build a transformation layer that converts workflow JSON into executable **LiveKit Voice Agents** with MCP server support.

---

## 📋 Your Task

Complete `workflow_parser/transformation_layer.py` to:

1. **Parse** the workflow JSON (`sample_workflow.json`)
2. **Build** a LiveKit Agent with the configured instructions and model
3. **Attach MCP servers** with `allowed_tools` filtering
4. **Return** an executable agent

---

## 🚀 Quick Start

```bash
# Sync dependencies
uv sync

# Set your OpenAI API key
export OPENAI_API_KEY="sk-your-key"

# Run the test
uv run python run_agent.py
```

---

## 📁 Project Structure

```
sketric-ml-backend-test/
├── README.md
├── pyproject.toml            # Project config & dependencies
├── uv.lock                   # Locked dependencies
├── requirements.txt          # Fallback for pip users
├── sample_workflow.json      # Example workflow config
├── run_agent.py              # Test runner
└── workflow_parser/
    ├── __init__.py
    └── transformation_layer.py   # 👈 YOUR CODE HERE
```

---

## 📦 Dependencies

Defined in `pyproject.toml`:

- **livekit** >= 1.0.20
- **livekit-agents[openai,silero,turn-detector]** >= 1.3.0
- **livekit-plugins-noise-cancellation**
- **python-dotenv** >= 1.0.0

Requires **Python 3.11+**

---

## ✅ Requirements

Your implementation must:

1. **Validate** the workflow JSON structure
2. **Create an Agent class** dynamically using `type()`
3. **Attach MCP servers** with `allowed_tools` filtering
4. **Handle the initial greeting** from trigger node

---

## 🔧 Workflow JSON Structure

The `sample_workflow.json` contains:

- **triggerNode**: Entry point with voice trigger configuration
- **agentNode**: Agent configuration (name, instructions, model, TTS settings)
- **toolNode**: MCP server configuration with URL and allowed tools
- **edges**: Connections between nodes (default, AgentHandoff)

---

## 📅 Deadline

5 days from receiving this test.

---

Good luck! 🎯
