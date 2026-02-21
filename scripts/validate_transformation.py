#!/usr/bin/env python3
"""
Validation script for transformation layer

This script validates that the transformation layer can successfully parse
the sample workflow and build agents/sessions.

Usage:
    uv run python scripts/validate_transformation.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def load_workflow():
    """Load the sample workflow JSON"""
    workflow_path = Path(__file__).parent.parent / "sample_workflow.json"
    with open(workflow_path) as f:
        return json.load(f)


async def validate_without_context():
    """Test building agent without context (should return agent, None)"""
    logger.info("=" * 60)
    logger.info("TEST 1: Building agent without context")
    logger.info("=" * 60)
    
    from workflow_parser.transformation_layer import build_agents_from_workflow
    
    workflow = load_workflow()
    agent, session = await build_agents_from_workflow(workflow, ctx=None)
    
    if agent is None:
        logger.error("❌ FAIL: agent is None")
        return False
    
    if session is not None:
        logger.error("❌ FAIL: session should be None when ctx is None")
        return False
    
    logger.info("✅ PASS: Agent built successfully without context")
    return True


async def validate_workflow_parsing():
    """Test workflow parsing logic"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Workflow parsing validation")
    logger.info("=" * 60)
    
    workflow = load_workflow()
    
    # Check structure
    if "nodes" not in workflow:
        logger.error("❌ FAIL: No 'nodes' in workflow")
        return False
    
    if "edges" not in workflow:
        logger.error("❌ FAIL: No 'edges' in workflow")
        return False
    
    nodes = workflow["nodes"]
    edges = workflow["edges"]
    
    logger.info(f"Found {len(nodes)} nodes and {len(edges)} edges")
    
    # Find trigger node
    trigger_nodes = [n for n in nodes if n.get("type") == "triggerNode"]
    if not trigger_nodes:
        logger.error("❌ FAIL: No trigger node found")
        return False
    
    logger.info(f"Found trigger node: {trigger_nodes[0]['id']}")
    
    # Find agent nodes
    agent_nodes = [n for n in nodes if n.get("type") == "agentNode"]
    if not agent_nodes:
        logger.error("❌ FAIL: No agent nodes found")
        return False
    
    logger.info(f"Found {len(agent_nodes)} agent node(s)")
    for agent in agent_nodes:
        logger.info(f"  - {agent['id']}: {agent['data'].get('name')}")
    
    # Find tool nodes
    tool_nodes = [n for n in nodes if n.get("type") == "toolNode"]
    if not tool_nodes:
        logger.warning("⚠️  WARNING: No tool nodes found")
    else:
        logger.info(f"Found {len(tool_nodes)} tool node(s)")
        for tool in tool_nodes:
            logger.info(f"  - {tool['id']}: {tool['data'].get('name')}")
    
    logger.info("✅ PASS: Workflow structure is valid")
    return True


async def validate_mcp_config():
    """Test MCP server configuration"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: MCP configuration validation")
    logger.info("=" * 60)
    
    from workflow_parser.transformation_layer import create_mcp_server
    
    # Test 1: Valid config
    valid_config = {
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer test"},
        "allowed_tools": ["tool1", "tool2"]
    }
    
    logger.info("Testing valid MCP config...")
    # Note: This might fail at runtime if livekit.agents.mcp isn't available
    # but the validation logic should work
    try:
        server = create_mcp_server(valid_config)
        if server is None:
            logger.warning("⚠️  MCP server creation returned None (might need runtime environment)")
        else:
            logger.info("✅ Valid config handled correctly")
    except Exception as e:
        logger.warning(f"⚠️  MCP server creation error (expected without full environment): {e}")
    
    # Test 2: Invalid config (missing URL)
    invalid_config = {
        "headers": {"Authorization": "Bearer test"}
    }
    
    logger.info("Testing invalid MCP config (missing URL)...")
    server = create_mcp_server(invalid_config)
    if server is not None:
        logger.error("❌ FAIL: Should return None for config without URL")
        return False
    
    logger.info("✅ PASS: Invalid config rejected correctly")
    
    # Test 3: Empty config
    logger.info("Testing empty MCP config...")
    server = create_mcp_server({})
    if server is not None:
        logger.error("❌ FAIL: Should return None for empty config")
        return False
    
    logger.info("✅ PASS: Empty config rejected correctly")
    
    # Test 4: None config
    logger.info("Testing None config...")
    server = create_mcp_server(None)
    if server is not None:
        logger.error("❌ FAIL: Should return None for None config")
        return False
    
    logger.info("✅ PASS: None config rejected correctly")
    
    return True


async def main():
    """Run all validation tests"""
    print("\n" + "=" * 60)
    print("TRANSFORMATION LAYER VALIDATION")
    print("=" * 60)
    
    workflow_path = Path(__file__).parent.parent / "sample_workflow.json"
    if not workflow_path.exists():
        logger.error(f"❌ Workflow file not found: {workflow_path}")
        sys.exit(1)
    
    tests = [
        ("Workflow Parsing", validate_workflow_parsing),
        ("MCP Configuration", validate_mcp_config),
        ("Agent Without Context", validate_without_context),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"❌ {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed_count}/{total} tests passed")
    
    if passed_count == total:
        print("\n🎉 All validation tests passed!")
        print("\nNext steps:")
        print("1. Configure .env with your LiveKit and OpenAI credentials")
        print("2. Run: uv run python scripts/setup.py")
        print("3. Run: uv run python run.py")
        print("4. Test: uv run python scripts/join_room.py my-room")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
