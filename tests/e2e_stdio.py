import asyncio
import os
import sys

os.environ["PDCA_MCP_DATABASE_URL"] = "postgresql://postgres:H1UaJoeo-aSF-zpM6V-0ARP@10.100.0.176:5432/pdca"
os.environ["PYTHONPATH"] = r"D:\pdca-mcp\src" + os.pathsep + os.environ.get("PYTHONPATH", "")
sys.path.insert(0, r"D:\pdca-mcp\src")

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
            print("stores(东南亚) 条数:", len(r.content[0].text and eval(r.content[0].text)) if r.content else "?")

            r2 = await session.call_tool("query_sell_in", {"month": "2026-08"})
            print("sell_in 结果:", r2.content[0].text[:200] if r2.content else "?")


if __name__ == "__main__":
    from mcp import ClientSession
    asyncio.run(main())
