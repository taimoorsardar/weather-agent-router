"""Quick test: can we connect to the Zapier MCP server and list tools?"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def main():
    from livekit.agents import mcp

    with open(Path(__file__).parent.parent / "sample_workflow.json") as f:
        wf = json.load(f)

    # Find the MCP tool node config
    tool_node = next(n for n in wf["nodes"] if n["type"] == "toolNode")
    cfg = tool_node["data"]["config"]

    print(f"URL: {cfg['url']}")
    print(f"Allowed tools: {cfg.get('allowed_tools')}")

    s = mcp.MCPServerHTTP(
        url=cfg["url"],
        headers=cfg.get("headers"),
        timeout=10,
        sse_read_timeout=30,
    )

    try:
        print("\nInitializing MCP server...")
        await asyncio.wait_for(s.initialize(), timeout=15)
        print("✅ Initialized!")

        tools = await s.list_tools()
        print(f"\nTools available ({len(tools)}):")
        for t in tools:
            print(f"  - {t.name}")
    except asyncio.TimeoutError:
        print("❌ Timed out connecting to MCP server")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await s.aclose()

asyncio.run(main())
