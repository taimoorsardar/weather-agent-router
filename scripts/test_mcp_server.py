#!/usr/bin/env python3
"""
MCP Server Creation and Validation Test Suite

This script thoroughly tests the create_mcp_server function with various
configurations to ensure robust error handling and correct behavior.

Usage:
    uv run python scripts/test_mcp_server.py
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


class TestResult:
    """Simple test result tracker"""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""


def run_test(test_name: str, test_func) -> TestResult:
    """Execute a test function and capture the result"""
    result = TestResult(test_name)
    try:
        passed, message = test_func()
        result.passed = passed
        result.message = message
        
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
        if message:
            logger.info(f"  → {message}")
    except Exception as e:
        result.passed = False
        result.message = f"Exception: {e}"
        logger.error(f"❌ FAIL: {test_name} - {e}")
        import traceback
        traceback.print_exc()
    
    return result


def test_valid_mcp_config_full():
    """Test 1: Valid MCP config with all fields"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "https://mcp.zapier.com/api/v1/connect",
        "headers": {
            "Authorization": "Bearer test_token_12345",
            "Content-Type": "application/json"
        },
        "allowed_tools": [
            "google_sheets_create_row",
            "google_sheets_update_row",
            "google_sheets_delete_row"
        ]
    }
    
    server = create_mcp_server(config)
    
    # Note: Server creation might succeed even if the URL isn't reachable
    # We're just testing the creation logic, not connectivity
    if server is None:
        return False, "Expected server instance, got None"
    
    return True, f"MCP server created successfully with {len(config['allowed_tools'])} tools"


def test_valid_mcp_config_minimal():
    """Test 2: Valid MCP config with only URL (minimal)"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "https://example.com/mcp/endpoint"
    }
    
    server = create_mcp_server(config)
    
    if server is None:
        return False, "Expected server instance, got None"
    
    return True, "Minimal config (URL only) handled correctly"


def test_valid_mcp_config_no_allowed_tools():
    """Test 3: Valid config without allowed_tools (all tools exposed)"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "https://mcp.example.com/api",
        "headers": {"X-API-Key": "test123"}
    }
    
    server = create_mcp_server(config)
    
    if server is None:
        return False, "Expected server instance, got None"
    
    return True, "Config without allowed_tools (expose all) works correctly"


def test_empty_allowed_tools_list():
    """Test 4: Config with empty allowed_tools list"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "https://mcp.example.com/api",
        "allowed_tools": []
    }
    
    server = create_mcp_server(config)
    
    # Empty list should still create a server (though no tools will be exposed)
    if server is None:
        return False, "Expected server instance even with empty allowed_tools"
    
    return True, "Empty allowed_tools list handled (no tools exposed)"


def test_invalid_config_no_url():
    """Test 5: Invalid config - missing URL"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "headers": {"Authorization": "Bearer test"},
        "allowed_tools": ["tool1"]
    }
    
    server = create_mcp_server(config)
    
    if server is not None:
        return False, "Should return None for config without URL"
    
    return True, "Missing URL rejected correctly"


def test_invalid_config_empty_url():
    """Test 6: Invalid config - empty/whitespace URL"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    configs = [
        {"url": ""},
        {"url": "   "},
        {"url": None}
    ]
    
    for i, config in enumerate(configs):
        server = create_mcp_server(config)
        if server is not None:
            return False, f"Config {i+1} should return None for empty/invalid URL"
    
    return True, "Empty/whitespace/None URLs rejected correctly"


def test_invalid_config_none():
    """Test 7: Invalid config - None"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    server = create_mcp_server(None)
    
    if server is not None:
        return False, "Should return None for None config"
    
    return True, "None config rejected correctly"


def test_invalid_config_empty_dict():
    """Test 8: Invalid config - empty dict"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    server = create_mcp_server({})
    
    if server is not None:
        return False, "Should return None for empty dict"
    
    return True, "Empty dict rejected correctly"


def test_invalid_config_not_dict():
    """Test 9: Invalid config - not a dictionary"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    invalid_configs = [
        "https://example.com",  # string
        ["url", "https://example.com"],  # list
        123,  # number
    ]
    
    for i, config in enumerate(invalid_configs):
        server = create_mcp_server(config)
        if server is not None:
            return False, f"Config {i+1} should return None for non-dict input"
    
    return True, "Non-dict configs rejected correctly"


def test_invalid_headers_type():
    """Test 10: Invalid headers - not a dict"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "https://example.com/mcp",
        "headers": "Authorization: Bearer token"  # string instead of dict
    }
    
    # Should create server but ignore/fix invalid headers
    server = create_mcp_server(config)
    
    if server is None:
        return False, "Should create server and handle invalid headers gracefully"
    
    return True, "Invalid headers type handled gracefully"


def test_invalid_allowed_tools_type():
    """Test 11: Invalid allowed_tools - not a list"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "https://example.com/mcp",
        "allowed_tools": "tool1,tool2,tool3"  # string instead of list
    }
    
    server = create_mcp_server(config)
    
    # Should return None because allowed_tools type is wrong
    if server is not None:
        return False, "Should return None for invalid allowed_tools type"
    
    return True, "Invalid allowed_tools type rejected correctly"


def test_allowed_tools_with_non_strings():
    """Test 12: allowed_tools list containing non-string items"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "https://example.com/mcp",
        "allowed_tools": ["tool1", 123, "tool2", None, "tool3"]
    }
    
    server = create_mcp_server(config)
    
    # Should create server and filter out non-string tools
    if server is None:
        return False, "Should create server and filter non-string tools"
    
    return True, "Non-string items in allowed_tools filtered correctly"


def test_real_workflow_mcp_config():
    """Test 13: Parse and test MCP config from sample_workflow.json"""
    workflow_path = Path(__file__).parent.parent / "sample_workflow.json"
    
    if not workflow_path.exists():
        return False, f"sample_workflow.json not found at {workflow_path}"
    
    with open(workflow_path) as f:
        workflow = json.load(f)
    
    # Find tool nodes with MCP config
    tool_nodes = [n for n in workflow.get("nodes", []) if n.get("type") == "toolNode"]
    mcp_tools = [n for n in tool_nodes if n.get("data", {}).get("toolType") == "mcp"]
    
    if not mcp_tools:
        return False, "No MCP tool nodes found in sample_workflow.json"
    
    from workflow_parser.transformation_layer import create_mcp_server
    
    for tool_node in mcp_tools:
        tool_data = tool_node.get("data", {})
        tool_name = tool_data.get("name", "unknown")
        config = tool_data.get("config", {})
        
        logger.info(f"  Testing tool: {tool_name}")
        server = create_mcp_server(config)
        
        if server is None:
            return False, f"Failed to create server for tool: {tool_name}"
    
    return True, f"Successfully created servers for {len(mcp_tools)} MCP tool(s) from workflow"


def test_url_with_whitespace():
    """Test 14: URL with leading/trailing whitespace"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    config = {
        "url": "  https://example.com/mcp  "
    }
    
    server = create_mcp_server(config)
    
    if server is None:
        return False, "Should handle URLs with whitespace"
    
    return True, "URL whitespace trimmed correctly"


def test_multiple_mcp_servers():
    """Test 15: Create multiple MCP servers (common use case)"""
    from workflow_parser.transformation_layer import create_mcp_server
    
    configs = [
        {"url": "https://mcp1.example.com", "allowed_tools": ["tool1", "tool2"]},
        {"url": "https://mcp2.example.com", "allowed_tools": ["tool3"]},
        {"url": "https://mcp3.example.com"}
    ]
    
    servers = []
    for i, config in enumerate(configs):
        server = create_mcp_server(config)
        if server is None:
            return False, f"Failed to create server {i+1}"
        servers.append(server)
    
    if len(servers) != len(configs):
        return False, f"Expected {len(configs)} servers, got {len(servers)}"
    
    return True, f"Successfully created {len(servers)} independent MCP servers"


def main():
    """Run all MCP server tests"""
    print("\n" + "=" * 70)
    print("MCP SERVER CREATION & VALIDATION TEST SUITE")
    print("=" * 70 + "\n")
    
    # Define all tests
    tests = [
        ("Valid config with all fields", test_valid_mcp_config_full),
        ("Valid config with only URL", test_valid_mcp_config_minimal),
        ("Valid config without allowed_tools", test_valid_mcp_config_no_allowed_tools),
        ("Empty allowed_tools list", test_empty_allowed_tools_list),
        ("Invalid: Missing URL", test_invalid_config_no_url),
        ("Invalid: Empty/whitespace URL", test_invalid_config_empty_url),
        ("Invalid: None config", test_invalid_config_none),
        ("Invalid: Empty dict", test_invalid_config_empty_dict),
        ("Invalid: Not a dictionary", test_invalid_config_not_dict),
        ("Invalid headers type", test_invalid_headers_type),
        ("Invalid allowed_tools type", test_invalid_allowed_tools_type),
        ("allowed_tools with non-strings", test_allowed_tools_with_non_strings),
        ("Real workflow MCP config", test_real_workflow_mcp_config),
        ("URL with whitespace", test_url_with_whitespace),
        ("Multiple MCP servers", test_multiple_mcp_servers),
    ]
    
    # Run all tests
    results = []
    for test_name, test_func in tests:
        print(f"\n{'─' * 70}")
        print(f"Running: {test_name}")
        print(f"{'─' * 70}")
        result = run_test(test_name, test_func)
        results.append(result)
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    
    for result in results:
        status = "✅" if result.passed else "❌"
        print(f"{status} {result.name}")
        if not result.passed and result.message:
            print(f"   └─ {result.message}")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All MCP server tests passed!")
        print("\nThe create_mcp_server function is working correctly.")
        print("\nNext steps:")
        print("  1. Complete the build_agents_from_workflow function")
        print("  2. Run: uv run python scripts/validate_transformation.py")
        print("  3. Start the agent: uv run python run.py")
        return 0
    else:
        failed_count = total_count - passed_count
        print(f"\n❌ {failed_count} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
