import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["PDCA_MCP_DATABASE_URL"] = os.environ["PDCA_MCP_TEST_DATABASE_URL"]
os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp.client.stdio import stdio_client, StdioServerParameters


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pdca_mcp.server"],
        env=os.environ.copy(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            r = await session.call_tool("query_stores", {"region": "东南亚"})
            print("stores(东南亚) 条数:", json.loads(r.content[0].text).get("count") if r.content else "?")

            r2 = await session.call_tool("query_sell_in", {"month": "2026-08"})
            print("sell_in 请求成功:", not r2.isError)


if __name__ == "__main__":
    from mcp import ClientSession
    asyncio.run(main())
