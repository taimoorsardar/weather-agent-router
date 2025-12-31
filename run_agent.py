"""
Test runner for the transformation layer.

This script loads the sample workflow and builds an agent from it.
You can use this to test your implementation.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Load workflow and build agent."""
    
    # Load the sample workflow
    workflow_path = Path(__file__).parent / "sample_workflow.json"
    
    if not workflow_path.exists():
        logger.error(f"Workflow file not found: {workflow_path}")
        return
    
    with open(workflow_path) as f:
        workflow_json = json.load(f)
    
    logger.info(f"Loaded workflow with {len(workflow_json['nodes'])} nodes and {len(workflow_json['edges'])} edges")
    
    # Print workflow summary
    print("\n" + "=" * 60)
    print("WORKFLOW SUMMARY")
    print("=" * 60)
    
    for node in workflow_json["nodes"]:
        node_type = node["type"]
        node_id = node["id"]
        node_name = node["data"].get("name", "")
        
        if node_type == "triggerNode":
            initial_msg = node["data"].get("initial_message", "")[:50]
            print(f"📍 Trigger: {node_id}")
            print(f"   Initial message: \"{initial_msg}...\"")
        elif node_type == "agentNode":
            model = node["data"].get("model", "unknown")
            print(f"🤖 Agent: {node_name} ({node_id})")
            print(f"   Model: {model}")
        elif node_type == "toolNode":
            tool_type = node["data"].get("toolType", "unknown")
            if tool_type == "mcp":
                url = node["data"].get("config", {}).get("url", "")
                allowed = node["data"].get("config", {}).get("allowed_tools", [])
                print(f"🔧 MCP Tool: {node_name} ({node_id})")
                print(f"   URL: {url}")
                print(f"   Allowed tools: {allowed}")
    
    print("\nEdges:")
    for edge in workflow_json["edges"]:
        edge_type = edge.get("type", "default")
        print(f"   {edge['source']} → {edge['target']} ({edge_type})")
    
    print("=" * 60 + "\n")
    
    # Try to build the agent
    try:
        from workflow_parser import build_agents_from_workflow
        
        logger.info("Building agent from workflow...")
        agent = await build_agents_from_workflow(workflow_json)
        
        if agent:
            print("✅ SUCCESS! Agent created successfully.")
            print(f"   Agent class: {type(agent).__name__}")
            
            # Check for MCP servers
            if hasattr(agent, '_mcp_servers'):
                print(f"   MCP servers attached: {len(agent._mcp_servers)}")
            
            # Check for on_enter method
            if hasattr(agent, 'on_enter'):
                print("   Has on_enter greeting: Yes")
            
        else:
            print("❌ FAILED: Agent creation returned None")
            
    except NotImplementedError as e:
        print(f"⚠️  NOT IMPLEMENTED: {e}")
        print("\n👉 Your task: Implement the functions in livekit/workflow_parser/transformation_layer.py")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())


