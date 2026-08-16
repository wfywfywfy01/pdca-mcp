import asyncio
import os
import sys

os.environ["PDCA_MCP_DATABASE_URL"] = "postgresql://postgres:H1UaJoeo-aSF-zpM6V-0ARP@10.100.0.176:5432/pdca"
os.environ["PYTHONPATH"] = r"D:\pdca-mcp\src" + os.pathsep + os.environ.get("PYTHONPATH", "")

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "pdca_mcp.server"], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r = await session.call_tool("query_stores", {"region": ""})
            print("content blocks:", len(r.content))
            for i, c in enumerate(r.content[:3]):
                print(f"  block[{i}] type={type(c).__name__} text={getattr(c,'text','')[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
