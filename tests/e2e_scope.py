import asyncio
import os
import subprocess
import sys
import time

os.environ["PDCA_MCP_DATABASE_URL"] = "postgresql://postgres:H1UaJoeo-aSF-zpM6V-0ARP@10.100.0.176:5432/pdca"
os.environ["PDCA_MCP_API_KEYS"] = "admin-key:admin:,april-key:sales:April"
os.environ["PYTHONPATH"] = r"D:\pdca-mcp\src" + os.pathsep + os.environ.get("PYTHONPATH", "")

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = 8899
URL = f"http://127.0.0.1:{PORT}/mcp"


async def call(key, tool, args):
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with streamablehttp_client(URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                r = await session.call_tool(tool, args)
                return eval(r.content[0].text)
    except BaseException as e:
        return f"EXC {type(e).__name__}"


async def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "pdca_mcp.server", "--transport", "http", "--port", str(PORT)],
        env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(5)

    admin_stores = await call("admin-key", "query_stores", {"region": ""})
    april_stores = await call("april-key", "query_stores", {"region": ""})
    april_sell_out = await call("april-key", "query_sell_out", {"month": "2026-08"})

    print("admin key 门店数:", len(admin_stores) if isinstance(admin_stores, list) else admin_stores)
    print("April key 门店数:", len(april_stores) if isinstance(april_stores, list) else april_stores)
    print("April 门店 sales_owner 集合:", sorted({s["sales_owner"] for s in april_stores}) if isinstance(april_stores, list) else "-")

    proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
