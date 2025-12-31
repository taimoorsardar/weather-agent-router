# 🧪 Sketric ML/Backend Engineer Test

## LiveKit Voice Agent Transformation Layer

Build a transformation layer that converts workflow JSON into executable **LiveKit Voice Agents** with MCP server support.

---

## 📋 Your Task

Complete `livekit/workflow_parser/transformation_layer.py` to:

1. **Parse** the workflow JSON (`sample_workflow.json`)
2. **Build** a LiveKit Agent with the configured instructions and model
3. **Attach MCP servers** with `allowed_tools` filtering
4. **Return** an executable agent

---

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="sk-your-key"

# Run the test
python run_agent.py
```

---

## 📁 Project Structure

```
sketric-ml-backend-test/
├── README.md
├── requirements.txt
├── sample_workflow.json      # Example workflow config
├── run_agent.py              # Test runner
└── workflow_parser/
    ├── __init__.py
    └── transformation_layer.py   # 👈 YOUR CODE HERE
```

---

## ✅ Requirements

Your implementation must:

1. **Validate** the workflow JSON structure
2. **Create an Agent class** dynamically using `type()`
3. **Attach MCP servers** with `allowed_tools` filtering
4. **Handle the initial greeting** from trigger node

---

## 📅 Deadline

5 days from receiving this test.

---

Good luck! 🎯
